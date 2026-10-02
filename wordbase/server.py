"""單字資料庫 — a local web app for the word database of spec-01 sections 5
and 6: words are fetched from the section 6 sources in their priority
order, every field keeps its source, licence and fetch time, and the
section 5 單字管理中心 lets you search, filter, edit, tag, merge, archive
and delete them.

    python wordbase/server.py            # http://127.0.0.1:8771
    python wordbase/server.py --port 8771 --db data/wordbase/other.sqlite

Standard library only (plus `wn` for Open English WordNet; `wordfreq` and
`opencc-python-reimplemented` are used when installed). On first start the
database is seeded with wordbase/seed_words.txt.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from model import FIELDS, GROUPS, MISSING  # noqa: E402
from sources import FETCHERS, SOURCES, extras  # noqa: E402
from store import DeleteBlocked, Store  # noqa: E402

ROOT = HERE.parent
STATIC = HERE / "static"
DEFAULT_DB = ROOT / "data" / "wordbase" / "wordbase.sqlite"
SEED = HERE / "seed_words.txt"


# ── Background fetching ─────────────────────────────────────────────────

class Fetcher:
    """Fetches pending words from every source, a few words at a time."""

    def __init__(self, store: Store, fetchers=FETCHERS, workers: int = 4):
        self.store = store
        self.fetchers = fetchers
        self.workers = workers
        self.current: set[str] = set()
        self._wake = threading.Event()
        self._refresh: set[int] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def kick(self, refresh_ids: list[int] = ()) -> None:
        with self._lock:
            self._refresh.update(refresh_ids)
        self._wake.set()

    def fetch_one(self, entry_id: int) -> None:
        word = self.store.word_of(entry_id)
        if word is None:
            return
        with self._lock:
            refresh = entry_id in self._refresh
            self._refresh.discard(entry_id)
            self.current.add(word)
        results = {}
        try:
            for name, fn in self.fetchers.items():
                try:
                    results[name] = fn(word, refresh)
                except Exception as e:  # noqa: BLE001 — one source never stops the others
                    results[name] = ({}, {"status": "error", "error": f"{type(e).__name__}: {e}"})
            self.store.save_results(entry_id, results, extras(word))
        finally:
            with self._lock:
                self.current.discard(word)

    def _loop(self) -> None:
        while True:
            pending = self.store.ids("pending")
            if not pending:
                self._wake.wait(timeout=30)
                self._wake.clear()
                continue
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                list(pool.map(self.fetch_one, pending))


# ── HTTP ────────────────────────────────────────────────────────────────

def filter_rows(rows: list[dict], q: dict) -> list[dict]:
    def one(name):
        return (q.get(name) or [""])[0]

    term = one("q").strip().lower()
    pos, tag, source, missing = one("pos"), one("tag"), one("source"), one("missing")
    level, status, fetch = one("level"), one("status") or "active", one("fetch")
    out = []
    for r in rows:
        s = r["summary"]
        if status != "all" and r["status"] != status:
            continue
        if term and term not in r["word"] and term not in (s.get("zh") or "") \
                and term not in (s.get("gloss") or "").lower():
            continue
        if pos and pos not in s.get("pos", []):
            continue
        if tag and tag not in r["tags"]:
            continue
        if level and r["extras"].get("cefr") != level:
            continue
        if missing and s.get("has", {}).get(missing, True):
            continue
        if source and source not in r.get("sources_ok", []):
            continue
        if fetch and r["fetch_status"] != fetch:
            continue
        out.append(r)
    sort = one("sort") or "word"
    key = {
        "word": lambda r: r["word"],
        "updated": lambda r: r["updated_at"],
        "created": lambda r: r["created_at"],
        "examples": lambda r: -r["summary"].get("counts", {}).get("examples", 0),
        "level": lambda r: ("A1A2B1B2C1C2".find(r["extras"].get("cefr") or "Z"), r["word"]),
    }.get(sort, lambda r: r["word"])
    out.sort(key=key, reverse=sort in ("updated", "created"))
    return out


def coverage(store: Store, rows: list[dict]) -> dict:
    """Per field and source: how many words that source had data for, and
    how many got the field from any source."""
    ids = {r["id"] for r in rows}
    by_entry: dict[int, dict[str, dict]] = {}
    status: dict[str, dict[str, int]] = {s: {} for s in SOURCES}
    for entry_id, source, st, data in store.results_matrix():
        if entry_id not in ids:
            continue
        by_entry.setdefault(entry_id, {})[source] = data
        status[source][st] = status[source].get(st, 0) + 1
    fields = []
    for f in FIELDS:
        cells = []
        for rank, source in enumerate(dict.fromkeys(s for s, _ in f.sources), 1):
            src_fields = [sf for s, sf in f.sources if s == source]
            found = sum(1 for e in ids if any((by_entry.get(e, {}).get(source) or {}).get(sf)
                                              for sf in src_fields))
            cells.append({"source": source, "rank": rank, "found": found})
        any_ = sum(1 for e in ids if any((by_entry.get(e, {}).get(s) or {}).get(sf)
                                         for s, sf in f.sources))
        fields.append({"key": f.key, "label": f.label, "group": f.group, "cells": cells, "any": any_})
    targets = {k: sum(1 for r in rows if r["summary"].get("has", {}).get(k)) for k in MISSING}
    return {"total": len(ids), "fields": fields, "targets": targets, "status": status}


def make_handler(store: Store, fetcher: Fetcher):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Wordbase/1.0"

        def log_message(self, fmt, *args):  # quiet
            pass

        def _send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def _rows(self) -> list[dict]:
            rows = store.rows()
            ok = {}
            for entry_id, source, st, data in store.results_matrix():
                if st == "ok" and data:
                    ok.setdefault(entry_id, []).append(source)
            for r in rows:
                r["sources_ok"] = ok.get(r["id"], [])
            return rows

        # GET ------------------------------------------------------------
        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            parts = [p for p in url.path.split("/") if p]
            if parts[:1] != ["api"]:
                return self._static(url.path)
            if parts == ["api", "meta"]:
                rows = store.rows()
                tags = sorted({t for r in rows for t in r["tags"]})
                pos = sorted({p for r in rows for p in r["summary"].get("pos", [])})
                return self._json(200, {
                    "sources": SOURCES, "groups": GROUPS, "missing": MISSING, "tags": tags, "pos": pos,
                    "fields": [{"key": f.key, "label": f.label, "group": f.group,
                                "sources": list(dict.fromkeys(s for s, _ in f.sources))}
                               for f in FIELDS],
                })
            if parts == ["api", "status"]:
                return self._json(200, {"pending": len(store.ids("pending")),
                                        "fetching": sorted(fetcher.current),
                                        "total": len(store.ids())})
            if parts == ["api", "entries"]:
                rows = filter_rows(self._rows(), q)
                dup_counts: dict[str, int] = {}
                for r in store.rows():
                    dup_counts[r["dup"]] = dup_counts.get(r["dup"], 0) + 1
                for r in rows:
                    r["maybe_duplicate"] = dup_counts.get(r["dup"], 0) > 1
                if (q.get("dups") or [""])[0]:
                    rows = [r for r in rows if r["maybe_duplicate"]]
                return self._json(200, {"entries": rows})
            if len(parts) == 3 and parts[1] == "entries" and parts[2].isdigit():
                entry = store.get(int(parts[2]))
                return self._json(200, entry) if entry else self._json(404, {"error": "找不到這個單字"})
            if parts == ["api", "coverage"]:
                return self._json(200, coverage(store, filter_rows(self._rows(), q)))
            return self._json(404, {"error": "not found"})

        def _static(self, path: str):
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (STATIC / rel).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        # POST / PATCH / PUT / DELETE -----------------------------------
        def do_POST(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            body = self._body()
            if parts == ["api", "entries"]:
                words = body.get("words") or []
                if isinstance(words, str):
                    words = [w for w in words.replace(",", "\n").splitlines()]
                created, dupes = store.add_words(words, body.get("tags") or [])
                fetcher.kick()
                return self._json(200, {"created": created, "duplicates": dupes})
            if len(parts) == 4 and parts[1] == "entries" and parts[3] == "refetch":
                entry_id = int(parts[2])
                store.mark_pending([entry_id])
                fetcher.kick([entry_id])
                return self._json(200, {"ok": True})
            if len(parts) == 6 and parts[1] == "entries" and parts[3] == "fields" and parts[5] == "verify":
                store.set_verified(int(parts[2]), parts[4], bool(body.get("verified", True)))
                return self._json(200, store.get(int(parts[2])))
            if parts == ["api", "merge"]:
                try:
                    store.merge(int(body["target"]), int(body["other"]))
                except KeyError:
                    return self._json(404, {"error": "找不到要合併的單字"})
                return self._json(200, store.get(int(body["target"])))
            if parts == ["api", "batch"]:
                ids = [int(i) for i in body.get("ids") or []]
                action, tag = body.get("action"), (body.get("tag") or "").strip()
                blocked = []
                for i in ids:
                    entry = store.get(i)
                    if entry is None:
                        continue
                    if action == "tag" and tag:
                        store.update(i, tags=entry["tags"] + [tag])
                    elif action == "untag" and tag:
                        store.update(i, tags=[t for t in entry["tags"] if t != tag])
                    elif action in ("archive", "restore"):
                        store.update(i, status="archived" if action == "archive" else "active")
                    elif action == "refetch":
                        store.mark_pending([i])
                    elif action == "delete":
                        try:
                            store.delete(i)
                        except DeleteBlocked:
                            blocked.append(entry["word"])
                if action == "refetch":
                    fetcher.kick(ids)
                return self._json(200, {"ok": True, "blocked": blocked})
            return self._json(404, {"error": "not found"})

        def do_PATCH(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            if len(parts) == 3 and parts[1] == "entries":
                store.update(int(parts[2]), **self._body())
                return self._json(200, store.get(int(parts[2])))
            return self._json(404, {"error": "not found"})

        def do_PUT(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            if len(parts) == 5 and parts[1] == "entries" and parts[3] == "fields":
                value = self._body().get("value")
                if not isinstance(value, list):
                    return self._json(400, {"error": "value 必須是清單"})
                try:
                    store.set_override(int(parts[2]), parts[4], value)
                except KeyError:
                    return self._json(400, {"error": "沒有這個欄位"})
                return self._json(200, store.get(int(parts[2])))
            return self._json(404, {"error": "not found"})

        def do_DELETE(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            if len(parts) == 5 and parts[1] == "entries" and parts[3] == "fields":
                store.clear_override(int(parts[2]), parts[4])
                return self._json(200, store.get(int(parts[2])))
            if len(parts) == 3 and parts[1] == "entries":
                try:
                    store.delete(int(parts[2]))
                except DeleteBlocked as e:
                    return self._json(409, {"error": str(e), "photos": e.photos, "cards": e.cards})
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "not found"})

    return Handler


def seed(store: Store, path: Path) -> int:
    """Adds the words in [path] (lines; `# 群組` lines become tags)."""
    group, words = None, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#"):
            group = line.lstrip("#").strip()
        elif line:
            words.setdefault(group, []).append(line)
    n = 0
    for group, ws in words.items():
        created, _ = store.add_words(ws, [group] if group else [])
        n += len(created)
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8771)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--no-seed", action="store_true")
    args = ap.parse_args()

    store = Store(args.db)
    if not store.ids() and not args.no_seed and SEED.exists():
        print(f"Seeding {seed(store, SEED)} words from {SEED.name}")
    store.rebuild_all()
    fetcher = Fetcher(store)
    fetcher.start()
    fetcher.kick()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, fetcher))
    print(f"單字資料庫：http://{args.host}:{args.port}/   (資料庫 {args.db})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
