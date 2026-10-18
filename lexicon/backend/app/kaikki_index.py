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


def spelling_candidates(language: str, word: str, path: Path | None = None) -> list[str] | None:
    """Indexed candidates for a single edit, including non-ASCII letters.

    None means no complete dictionary is installed; an empty list is a real
    dictionary result. GLOB's one-character wildcard avoids restricting the
    dictionary to an invented alphabet or loading every headword into RAM.
    The caller still verifies edit distance and ranks learning suitability.
    """
    conn = _connection(path or config.KAIKKI_INDEX)
    if conn is None:
        return None
    try:
        complete = conn.execute('SELECT value FROM metadata WHERE key = ?',
                                (f'complete:{language}',)).fetchone()
        if not complete or complete[0] != '1':
            return None
        word = normalize_lemma(word, language)
        if not word.isalpha():
            return []
        exact = {word[:i] + word[i + 1:] for i in range(len(word))}
        exact.update(word[:i] + word[i + 1] + word[i] + word[i + 2:]
                     for i in range(len(word) - 1))
        found = set()
        if exact:
            marks = ','.join('?' for _ in exact)
            found.update(r[0] for r in conn.execute(
                f'SELECT DISTINCT normalized FROM entries WHERE language = ? '
                f'AND normalized IN ({marks})', (language, *sorted(exact))))
        # Normalized alphabetic headwords contain no GLOB metacharacters.
        patterns = {word[:i] + '?' + word[i + 1:] for i in range(len(word))}
        patterns.update(word[:i] + '?' + word[i:] for i in range(len(word) + 1))
        for pattern in sorted(patterns):
            found.update(r[0] for r in conn.execute(
                'SELECT DISTINCT normalized FROM entries '
                'WHERE language = ? AND normalized GLOB ?', (language, pattern)))
    except sqlite3.OperationalError:
        return None
    return sorted(w for w in found if w != word and w.isalpha())


def wordlist_snapshot(language: str, path: Path | None = None) -> dict | None:
    path = path or config.KAIKKI_INDEX
    conn = _connection(path)
    if conn is None:
        return None
    try:
        metadata = dict(conn.execute('SELECT key,value FROM metadata'))
        if metadata.get(f'complete:{language}') != '1':
            return None
        count = conn.execute('SELECT count(DISTINCT normalized) FROM entries '
                             'WHERE language = ?', (language,)).fetchone()[0]
    except sqlite3.OperationalError:
        return None
    return {'version': 'Kaikki complete indexed headwords', 'path': str(path),
            'url': metadata.get(f'source:{language}'), 'row_count': count,
            'details': {'wordlist': 'kaikki_index', 'complete': True}}
