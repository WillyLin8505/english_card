"""Read-only HTTP snapshots: durable last-good content and incremental updates.

The database exporter remains synchronous for QC. HTTP readers never wait for
revalidation once a snapshot exists. A refresh failure retains the last good
snapshot and retries after the polling interval.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
import zlib

import pack_sqlite


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def accepts_gzip(header):
    codings = {}
    for item in header.lower().split(','):
        name, *params = item.strip().split(';')
        q = 1.0
        for param in params:
            if param.strip().startswith('q='):
                try:
                    q = float(param.strip()[2:])
                except ValueError:
                    q = 0.0
        codings[name] = q
    return codings.get('gzip', codings.get('*', 0)) > 0


def matches_etag(header, etag):
    # GET uses weak comparison, including lists and wildcard validators.
    return any(item.strip() == '*' or item.strip().removeprefix('W/') ==
               etag.removeprefix('W/') for item in header.split(','))


def delta(old, new):
    previous = {row['id']: row for row in old['lexemes']}
    return {'delta_version': 1, 'base_version': old['created_at'],
            'metadata': {k: v for k, v in new.items() if k != 'lexemes'},
            # Order also handles deletions and changes in usage ranking.
            'order': [row['id'] for row in new['lexemes']],
            'upserts': [row for row in new['lexemes'] if previous.get(row['id']) != row]}


SQLITE_TYPE = 'application/vnd.sqlite3'
JSON_TYPE = 'application/json; charset=utf-8'


class Snapshot:
    def __init__(self, body, compressed=None, sqlite_path=None):
        # Card #664: only the gzip stays resident. The 600 MB JSON text and its
        # parsed objects (several GB) are rebuilt on demand and dropped again;
        # keeping them took serve_app to 8-9 GB and starved every other request.
        pack = json.loads(body)
        self.version = pack['created_at']
        self.languages = (pack.get('target_language'), pack.get('native_language'))
        del pack
        self.etag = 'W/"' + self.version + '"'
        # Card 672 (issue #772): set to the older code revision's directory name
        # while this snapshot stands in for the current revision's first build.
        self.stale_revision = None
        self.gzip = compressed if compressed is not None else gzip.compress(body, compresslevel=6, mtime=0)
        self.delta_from = None
        self.delta_body = None
        self.delta_gzip = None
        # The phone form (card #428): the slim pack as one SQLite file, built
        # once per version beside the JSON snapshot, and the delta between
        # slim packs that a phone holding the previous version applies itself.
        self.sqlite_path = sqlite_path
        self._sqlite_bytes = None
        self._slim = None
        self._sqlite_lock = threading.Lock()
        self.sqlite_delta_from = None
        self.sqlite_delta_body = None
        self.sqlite_delta_gzip = None

    @property
    def body(self):
        return gzip.decompress(self.gzip)

    @property
    def pack(self):
        return json.loads(self.body)

    def stream(self, compressed, chunk=1 << 20):
        """(length, chunk iterator) of the full JSON, read from the gzip in
        pieces so a download never copies the whole text."""
        data = memoryview(self.gzip)
        if compressed:
            return len(data), (data[i:i + chunk] for i in range(0, len(data), chunk))
        length = int.from_bytes(data[-4:], 'little')  # gzip ISIZE (pack < 4 GB)

        def pieces():
            inflate = zlib.decompressobj(31)
            for i in range(0, len(data), 1 << 16):
                out = inflate.decompress(data[i:i + (1 << 16)])
                if out:
                    yield out
            tail = inflate.flush()
            if tail:
                yield tail
        return length, pieces()

    @property
    def slim(self):
        if self._slim is None:
            self._slim = pack_sqlite.slim_pack(self.pack)
        return self._slim

    def sqlite(self):
        """The SQLite pack bytes: reused from `sqlite_path` when that file is
        this version, else built there (or in a temporary file) on first use."""
        with self._sqlite_lock:
            if self._sqlite_bytes is None:
                path = Path(self.sqlite_path) if self.sqlite_path else None
                if path is not None and path.is_file() and \
                        pack_sqlite.read_meta(path).get('created_at') == self.version:
                    self._sqlite_bytes = path.read_bytes()
                elif path is not None:
                    pack_sqlite.build(self.slim, path)
                    self._sqlite_bytes = path.read_bytes()
                else:
                    import tempfile
                    with tempfile.TemporaryDirectory(prefix='dictionary-sqlite-') as folder:
                        target = pack_sqlite.build(self.slim, Path(folder) / 'pack.sqlite')
                        self._sqlite_bytes = target.read_bytes()
            return self._sqlite_bytes

    def representation(self, since, compressed):
        if since and since == self.delta_from:
            return self.delta_gzip if compressed else self.delta_body
        return self.gzip if compressed else self.body

    def respond(self, since, compressed, fmt='json'):
        """(body, content type, gzipped?) for a GET. `fmt` 'sqlite' answers a
        phone: a JSON delta when it holds the previous version, else the
        whole SQLite file (its rows are already compressed, never gzipped)."""
        if fmt == 'sqlite':
            if since and since == self.sqlite_delta_from:
                return ((self.sqlite_delta_gzip if compressed else self.sqlite_delta_body),
                        JSON_TYPE, compressed)
            return self.sqlite(), SQLITE_TYPE, False
        return self.representation(since, compressed), JSON_TYPE, compressed


class Warming(RuntimeError):
    """No snapshot exists yet; the first build runs in the background."""


class SnapshotStore:
    def __init__(self, builder, directory: Path, interval=120, stale_root: Path | None = None,
                 wait_first=True):
        self.builder = builder
        self.directory = directory
        self.interval = interval
        # Snapshots of earlier code revisions live beside this one (card #380):
        # serve the newest while this revision's first build runs.
        self.stale_root = stale_root
        # False: a cold store raises Warming at once instead of holding the
        # request for minutes (Cloudflare cuts it at 100 s, 524).
        self.wait_first = wait_first
        self.entries = {}
        self.checked = {}
        self.refreshing = set()
        self.lock = threading.Lock()

    def _path(self, pair, directory=None):
        # Pair validation belongs to the route; hashing also avoids path input.
        key = hashlib.sha256(encode(pair)).hexdigest()
        return (directory or self.directory) / (key + '.json.gz')

    @staticmethod
    def _sqlite_path(json_path: Path) -> Path:
        return json_path.with_name(json_path.name[:-len('.json.gz')] + '.sqlite')

    def _load(self, pair, path=None):
        try:
            path = path or self._path(pair)
            compressed = path.read_bytes()
            snapshot = Snapshot(gzip.decompress(compressed), compressed,
                                sqlite_path=self._sqlite_path(path))
            if snapshot.languages != pair:
                return None
            return snapshot
        except (OSError, ValueError, KeyError, EOFError):
            return None

    def _load_stale(self, pair):
        if self.stale_root is None:
            return None
        name = self._path(pair).name
        try:
            paths = [d / name for d in self.stale_root.iterdir()
                     if d.is_dir() and d != self.directory and (d / name).is_file()]
        except OSError:
            return None
        for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True):
            snapshot = self._load(pair, path)
            if snapshot is not None:
                snapshot.stale_revision = path.parent.name
                logging.info('Serving stale dictionary snapshot %s until the rebuild finishes', path)
                return snapshot
        return None

    def _build(self, pair, previous):
        body, _ = self.builder(*pair)
        if previous and previous.body == body:
            previous.stale_revision = None  # same data as the current code builds
            return previous
        snapshot = Snapshot(body)
        if snapshot.languages != pair:
            raise ValueError('Exporter returned the wrong dictionary language pair')
        if previous:
            patch = encode(delta(previous.pack, snapshot.pack))
            compressed = gzip.compress(patch, compresslevel=6, mtime=0)
            if len(compressed) < len(snapshot.gzip) and len(patch) < len(body):
                snapshot.delta_from = previous.version
                snapshot.delta_body, snapshot.delta_gzip = patch, compressed
            # Phones hold the slim pack (card #428): their delta is between
            # slim packs, and always smaller than the SQLite file.
            patch = encode(delta(previous.slim, snapshot.slim))
            snapshot.sqlite_delta_from = previous.version
            snapshot.sqlite_delta_body = patch
            snapshot.sqlite_delta_gzip = gzip.compress(patch, compresslevel=6, mtime=0)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self._path(pair)
            temporary = path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
            temporary.write_bytes(snapshot.gzip)
            temporary.replace(path)
            snapshot.sqlite_path = self._sqlite_path(path)
        except OSError:
            logging.warning('Could not persist dictionary snapshot', exc_info=True)
        try:
            snapshot.sqlite()  # built now, in the refresh thread, not on a phone's request
        except Exception:
            logging.warning('Could not build the SQLite dictionary', exc_info=True)
        return snapshot

    def _refresh(self, pair, previous):
        try:
            snapshot = self._build(pair, previous)
            with self.lock:
                self.entries[pair] = snapshot
        except Exception:
            logging.exception('Dictionary refresh failed; retaining last good snapshot')
        finally:
            with self.lock:
                self.checked[pair] = time.monotonic()
                self.refreshing.discard(pair)

    def get(self, target, native):
        pair = target, native
        with self.lock:
            snapshot = self.entries.get(pair)
            if snapshot is None:
                snapshot = self._load(pair) or self._load_stale(pair)
                if snapshot is None and not self.wait_first:
                    # First installation only: build in the background, answer now.
                    if pair not in self.refreshing:
                        self.refreshing.add(pair)
                        threading.Thread(target=self._refresh, args=(pair, None),
                                         daemon=True, name='dictionary-refresh').start()
                    raise Warming('Dictionary is being prepared')
                if snapshot is None:
                    # First installation only. Warm this before accepting users.
                    snapshot = self._build(pair, None)
                    self.checked[pair] = time.monotonic()
                self.entries[pair] = snapshot
            if (time.monotonic() - self.checked.get(pair, float('-inf')) >= self.interval
                    and pair not in self.refreshing):
                self.refreshing.add(pair)
                threading.Thread(target=self._refresh, args=(pair, snapshot),
                                 daemon=True, name='dictionary-refresh').start()
            return snapshot


class RequestWatch:
    """問題回報 #904: when a request hangs or is slow, leave the evidence behind.

    Every request is registered while it runs. A request that finishes slower than
    `slow_s` is logged (method, path, status, ms, requests in flight). A watchdog
    thread logs once, while a request is still stuck after `stuck_s`, the stack of
    its thread, the in-flight list and the DB pool state, so a request that never
    answers is explained after the fact too.
    """

    def __init__(self, log_path: Path, slow_s: float = 3.0, stuck_s: float = 10.0, pool=None):
        self.log_path, self.slow_s, self.stuck_s, self.pool = Path(log_path), slow_s, stuck_s, pool
        self._lock = threading.Lock()
        self._active: dict[int, dict] = {}
        self._dumped: set[int] = set()

    def _write(self, text: str) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open('a', encoding='utf-8') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + text + '\n')
        except OSError:
            pass

    def _pool_state(self) -> str:
        try:
            return self.pool.status() if self.pool is not None else ''
        except Exception:  # noqa: BLE001 - diagnostics must never break a request
            return ''

    def begin(self, method: str, path: str, host: str = '') -> int:
        key = threading.get_ident()
        with self._lock:
            self._active[key] = {'method': method, 'path': path, 'host': host,
                                 'start': time.monotonic(), 'thread': key}
        return key

    def end(self, key: int, status) -> None:
        with self._lock:
            info = self._active.pop(key, None)
            dumped = key in self._dumped
            self._dumped.discard(key)
            others = len(self._active)
        if info is None:
            return
        ms = round((time.monotonic() - info['start']) * 1000)
        if ms >= self.slow_s * 1000 or dumped:
            self._write(f"SLOW {info['method']} {info['path']} host={info['host']} status={status} "
                        f"{ms}ms others_in_flight={others} pool=[{self._pool_state()}]")

    def check(self) -> None:
        """One watchdog pass (also called by tests)."""
        import sys
        import traceback
        now = time.monotonic()
        with self._lock:
            stuck = [dict(i) for k, i in self._active.items()
                     if now - i['start'] >= self.stuck_s and k not in self._dumped]
            self._dumped.update(i['thread'] for i in stuck)
            inflight = [f"{i['method']} {i['path']} {round(now - i['start'], 1)}s" for i in self._active.values()]
        if not stuck:
            return
        frames = sys._current_frames()
        for i in stuck:
            frame = frames.get(i['thread'])
            stack = ''.join(traceback.format_stack(frame)[-8:]) if frame else '(thread gone)'
            self._write(f"STUCK {i['method']} {i['path']} host={i['host']} {round(now - i['start'], 1)}s "
                        f"threads={threading.active_count()} pool=[{self._pool_state()}]\n"
                        f"  in flight: {inflight}\n{stack}")

    def start(self) -> None:
        def loop():
            while True:
                time.sleep(2)
                try:
                    self.check()
                except Exception:  # noqa: BLE001
                    logging.exception('request watchdog')
        threading.Thread(target=loop, daemon=True, name='request-watch').start()
