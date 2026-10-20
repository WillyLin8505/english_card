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
        self.body = body
        self.pack = json.loads(body)
        self.version = self.pack['created_at']
        self.etag = 'W/"' + self.version + '"'
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
            if (snapshot.pack['target_language'], snapshot.pack['native_language']) != pair:
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
                logging.info('Serving stale dictionary snapshot %s until the rebuild finishes', path)
                return snapshot
        return None

    def _build(self, pair, previous):
        body, _ = self.builder(*pair)
        if previous and previous.body == body:
            return previous
        snapshot = Snapshot(body)
        if (snapshot.pack.get('target_language'), snapshot.pack.get('native_language')) != pair:
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
