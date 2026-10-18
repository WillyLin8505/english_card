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


class Snapshot:
    def __init__(self, body, compressed=None):
        self.body = body
        self.pack = json.loads(body)
        self.version = self.pack['created_at']
        self.etag = 'W/"' + self.version + '"'
        self.gzip = compressed if compressed is not None else gzip.compress(body, compresslevel=6, mtime=0)
        self.delta_from = None
        self.delta_body = None
        self.delta_gzip = None

    def representation(self, since, compressed):
        if since and since == self.delta_from:
            return self.delta_gzip if compressed else self.delta_body
        return self.gzip if compressed else self.body


class SnapshotStore:
    def __init__(self, builder, directory: Path, interval=120):
        self.builder = builder
        self.directory = directory
        self.interval = interval
        self.entries = {}
        self.checked = {}
        self.refreshing = set()
        self.lock = threading.Lock()

    def _path(self, pair):
        # Pair validation belongs to the route; hashing also avoids path input.
        key = hashlib.sha256(encode(pair)).hexdigest()
        return self.directory / (key + '.json.gz')

    def _load(self, pair):
        try:
            compressed = self._path(pair).read_bytes()
            snapshot = Snapshot(gzip.decompress(compressed), compressed)
            if (snapshot.pack['target_language'], snapshot.pack['native_language']) != pair:
                return None
            return snapshot
        except (OSError, ValueError, KeyError, EOFError):
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
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self._path(pair)
            temporary = path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
            temporary.write_bytes(snapshot.gzip)
            temporary.replace(path)
        except OSError:
            logging.warning('Could not persist dictionary snapshot', exc_info=True)
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
                snapshot = self._load(pair)
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
