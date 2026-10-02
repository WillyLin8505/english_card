"""Small read-only lookup layer for a locally indexed Kaikki JSONL dump."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from . import config
from .text import normalize_lemma

_local = threading.local()


def _connection(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    current = getattr(_local, "kaikki", None)
    if current and current[0] == path:
        return current[1]
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA query_only=ON")
    _local.kaikki = (path, conn)
    return conn


def lookup(language: str, word: str, path: Path | None = None) -> list[dict] | None:
    """Return None when no index is installed, and a list for an indexed lookup."""
    conn = _connection(path or config.KAIKKI_INDEX)
    if conn is None:
        return None
    key = normalize_lemma(word, language)
    try:
        complete = conn.execute("SELECT value FROM metadata WHERE key = ?",
                                (f"complete:{language}",)).fetchone()
        if not complete or complete[0] != "1":
            return None
        rows = conn.execute(
            "SELECT payload FROM entries WHERE language = ? AND normalized = ? ORDER BY id",
            (language, key),
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    return [json.loads(row[0]) for row in rows]
