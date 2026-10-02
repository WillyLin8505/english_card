"""Build the local Kaikki lookup database from JSONL or JSONL.GZ.

Examples:
  python tools/build_kaikki_index.py raw-data/kaikki-English.jsonl --language en
  python tools/build_kaikki_index.py https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl --language en
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import config  # noqa: E402
from app.text import normalize_lemma  # noqa: E402


def lines(source: str):
    if source.startswith(("https://", "http://")):
        response = urllib.request.urlopen(urllib.request.Request(
            source, headers={"User-Agent": config.USER_AGENT}), timeout=60)
        raw = gzip.GzipFile(fileobj=response) if source.endswith(".gz") else response
        return io.TextIOWrapper(raw, encoding="utf-8")
    raw = open(source, "rb")
    stream = gzip.GzipFile(fileobj=raw) if source.endswith(".gz") else raw
    return io.TextIOWrapper(stream, encoding="utf-8")


def build(source: str, output: Path, language: str, replace: bool = False) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    building = output.with_name(output.name + ".building")
    if building.exists():
        building.unlink()
    if output.exists():
        shutil.copy2(output, building)
    conn = sqlite3.connect(building)
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE IF NOT EXISTS entries (
          id INTEGER PRIMARY KEY,
          language TEXT NOT NULL,
          normalized TEXT NOT NULL,
          payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_entries_lookup
          ON entries(language, normalized);
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    if replace:
        conn.execute("DELETE FROM entries WHERE language = ?", (language,))
    count, batch, started = 0, [], time.monotonic()
    with lines(source) as src:
        for line in src:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            word = str(entry.get("word") or "").strip()
            if not word:
                continue
            batch.append((language, normalize_lemma(word, language),
                          json.dumps(entry, ensure_ascii=False, separators=(",", ":"))))
            if len(batch) >= 5000:
                conn.executemany(
                    "INSERT INTO entries(language, normalized, payload) VALUES (?, ?, ?)", batch)
                conn.commit()
                count += len(batch)
                batch.clear()
                if count % 100000 == 0:
                    rate = count / max(time.monotonic() - started, 0.001)
                    print(f"{count:,} rows ({rate:,.0f}/s)", flush=True)
    if batch:
        conn.executemany(
            "INSERT INTO entries(language, normalized, payload) VALUES (?, ?, ?)", batch)
        count += len(batch)
    conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                 (f"source:{language}", source))
    conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                 (f"rows:{language}", str(count)))
    conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, '1')",
                 (f"complete:{language}",))
    conn.commit()
    conn.execute("PRAGMA optimize")
    conn.close()
    os.replace(building, output)
    print(f"完成：{count:,} rows → {output}")
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="JSONL/JSONL.GZ path or URL")
    parser.add_argument("--language", default="en", choices=("en", "fr", "zh-TW"))
    parser.add_argument("--output", type=Path, default=config.KAIKKI_INDEX)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    build(args.source, args.output, args.language, args.replace)


if __name__ == "__main__":
    main()
