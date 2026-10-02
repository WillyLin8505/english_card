"""SQLite storage for the word database.

entries    one row per WordEntry (標準化拼字 is the duplicate key)
results    each source's normalized answer for the entry, kept separately
           so every field can show where it came from and what the other
           sources had (spec section 5: 來源追蹤)
overrides  the learner's edits; the fetched values stay in `results` as the
           original (允許使用者覆寫並保留原始值)
verified   fields the learner marked as checked (可信狀態 AI／已核對)

The merged view and the list summary are cached on the entry and rebuilt
whenever its results, edits or settings change.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from model import FIELD_BY_KEY, build_view, summarize
from sources import SOURCES

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    word TEXT NOT NULL UNIQUE,
    lang TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL DEFAULT 'active',          -- active | archived
    tags TEXT NOT NULL DEFAULT '[]',
    note TEXT NOT NULL DEFAULT '',
    primary_sense TEXT,
    default_accent TEXT,
    photo_refs INTEGER NOT NULL DEFAULT 0,          -- PhotoOccurrences in the learning app
    card_refs INTEGER NOT NULL DEFAULT 0,           -- LearningCards in the learning app
    fetch_status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | partial | failed
    fetch_error TEXT,
    fetched_at TEXT,
    extras TEXT NOT NULL DEFAULT '{}',
    view TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    counts TEXT NOT NULL DEFAULT '{}',
    data TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (entry_id, source)
);
CREATE TABLE IF NOT EXISTS overrides (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    edited_at TEXT NOT NULL,
    PRIMARY KEY (entry_id, field)
);
CREATE TABLE IF NOT EXISTS verified (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    PRIMARY KEY (entry_id, field)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(word: str) -> str:
    """標準化拼字: lowercase, single spaces."""
    return re.sub(r"\s+", " ", word.strip().lower())


def duplicate_key(word: str) -> str:
    """Looser key for 可能重複: letters only, simple plurals folded
    ("pine nuts" ~ "pine nut", "well-being" ~ "wellbeing")."""
    w = re.sub(r"[^a-z]", "", word.lower())
    for suffix in ("ies", "es", "s"):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


class DeleteBlocked(Exception):
    def __init__(self, photos: int, cards: int):
        super().__init__(f"仍有 {photos} 張照片、{cards} 張卡片引用這個單字")
        self.photos, self.cards = photos, cards


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    # ── Writes ─────────────────────────────────────────────────────────

    def add_words(self, words: list[str], tags: list[str] = ()) -> tuple[list[int], list[str]]:
        """Adds new words (fetched later by the worker). Returns the new ids
        and the words that already existed."""
        created, dupes = [], []
        with self._db() as db:
            for raw in words:
                word = normalize(raw)
                if not word:
                    continue
                row = db.execute("SELECT id, tags FROM entries WHERE word = ?", (word,)).fetchone()
                if row:
                    dupes.append(word)
                    merged = sorted(set(json.loads(row["tags"])) | set(tags))
                    db.execute("UPDATE entries SET tags = ? WHERE id = ?",
                               (json.dumps(merged, ensure_ascii=False), row["id"]))
                    continue
                t = now()
                cur = db.execute(
                    "INSERT INTO entries (word, tags, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (word, json.dumps(sorted(set(tags)), ensure_ascii=False), t, t))
                created.append(cur.lastrowid)
        for i in created:
            self.rebuild(i)
        return created, dupes

    def save_results(self, entry_id: int, results: dict[str, tuple[dict, dict]], extras: dict) -> None:
        """Stores each source's answer and the fetch outcome."""
        t = now()
        with self._db() as db:
            for source, (data, meta) in results.items():
                db.execute(
                    "INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (entry_id, source, meta.get("status", "error"), meta.get("error"),
                     json.dumps(meta.get("counts") or {}), json.dumps(data, ensure_ascii=False), t))
            statuses = [m.get("status") for _, m in results.values()]
            errors = [f"{SOURCES[s]['name']}：{m.get('error')}" for s, (_, m) in results.items()
                      if m.get("status") == "error"]
            status = ("failed" if statuses and all(s == "error" for s in statuses)
                      else "partial" if errors else "done")
            db.execute("UPDATE entries SET fetch_status = ?, fetch_error = ?, fetched_at = ?, "
                       "extras = ? WHERE id = ?",
                       (status, "；".join(errors) or None, t, json.dumps(extras), entry_id))
        self.rebuild(entry_id)

    def mark_pending(self, ids: list[int]) -> None:
        with self._db() as db:
            db.executemany("UPDATE entries SET fetch_status = 'pending' WHERE id = ?",
                           [(i,) for i in ids])

    def update(self, entry_id: int, **changes) -> None:
        allowed = {"tags", "status", "note", "primary_sense", "default_accent", "photo_refs",
                   "card_refs"}
        sets = {k: v for k, v in changes.items() if k in allowed}
        if "tags" in sets:
            sets["tags"] = json.dumps(sorted(set(sets["tags"])), ensure_ascii=False)
        if not sets:
            return
        with self._db() as db:
            db.execute(f"UPDATE entries SET {', '.join(f'{k} = ?' for k in sets)}, updated_at = ? "
                       "WHERE id = ?", (*sets.values(), now(), entry_id))
        self.rebuild(entry_id)

    def set_override(self, entry_id: int, field: str, value: list) -> None:
        if field not in FIELD_BY_KEY:
            raise KeyError(field)
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO overrides VALUES (?, ?, ?, ?)",
                       (entry_id, field, json.dumps(value, ensure_ascii=False), now()))
            db.execute("UPDATE entries SET updated_at = ? WHERE id = ?", (now(), entry_id))
        self.rebuild(entry_id)

    def clear_override(self, entry_id: int, field: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM overrides WHERE entry_id = ? AND field = ?", (entry_id, field))
            db.execute("UPDATE entries SET updated_at = ? WHERE id = ?", (now(), entry_id))
        self.rebuild(entry_id)

    def set_verified(self, entry_id: int, field: str, on: bool) -> None:
        with self._db() as db:
            if on:
                db.execute("INSERT OR REPLACE INTO verified VALUES (?, ?, ?)", (entry_id, field, now()))
            else:
                db.execute("DELETE FROM verified WHERE entry_id = ? AND field = ?", (entry_id, field))
        self.rebuild(entry_id)

    def delete(self, entry_id: int) -> None:
        """Spec section 5: 刪除 WordEntry 前若仍有照片或卡片引用，必須阻止直接
        刪除並提供封存選項."""
        with self._db() as db:
            row = db.execute("SELECT photo_refs, card_refs FROM entries WHERE id = ?",
                             (entry_id,)).fetchone()
            if row is None:
                return
            if row["photo_refs"] or row["card_refs"]:
                raise DeleteBlocked(row["photo_refs"], row["card_refs"])
            db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def merge(self, target_id: int, other_id: int) -> None:
        """合併重複單字: the other entry's tags, edits and source answers the
        target lacks move to the target, reference counts add up, and the
        other entry goes. Photo contexts and cards live in the learning app
        and stay independent (spec section 5)."""
        if target_id == other_id:
            return
        with self._db() as db:
            t = db.execute("SELECT * FROM entries WHERE id = ?", (target_id,)).fetchone()
            o = db.execute("SELECT * FROM entries WHERE id = ?", (other_id,)).fetchone()
            if t is None or o is None:
                raise KeyError("entry")
            tags = sorted(set(json.loads(t["tags"])) | set(json.loads(o["tags"])))
            note = "\n".join(x for x in (t["note"], o["note"]) if x)
            db.execute("UPDATE entries SET tags = ?, note = ?, photo_refs = ?, card_refs = ?, "
                       "updated_at = ? WHERE id = ?",
                       (json.dumps(tags, ensure_ascii=False), note,
                        t["photo_refs"] + o["photo_refs"], t["card_refs"] + o["card_refs"], now(),
                        target_id))
            db.execute("INSERT OR IGNORE INTO overrides SELECT ?, field, value, edited_at "
                       "FROM overrides WHERE entry_id = ?", (target_id, other_id))
            db.execute("INSERT OR REPLACE INTO results SELECT ?, source, status, error, counts, "
                       "data, fetched_at FROM results WHERE entry_id = ? AND status = 'ok' "
                       "AND source NOT IN (SELECT source FROM results WHERE entry_id = ? "
                       "AND status = 'ok')", (target_id, other_id, target_id))
            db.execute("DELETE FROM entries WHERE id = ?", (other_id,))
        self.rebuild(target_id)

    def rebuild(self, entry_id: int) -> None:
        with self._db() as db:
            row = db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                return
            entry = dict(row)
            results = {r["source"]: {"status": r["status"], "data": json.loads(r["data"]),
                                     "fetched_at": r["fetched_at"]}
                       for r in db.execute("SELECT * FROM results WHERE entry_id = ?", (entry_id,))}
            overrides = {r["field"]: {"value": json.loads(r["value"]), "edited_at": r["edited_at"]}
                         for r in db.execute("SELECT * FROM overrides WHERE entry_id = ?",
                                             (entry_id,))}
            verified = {r["field"]: r["verified_at"]
                        for r in db.execute("SELECT * FROM verified WHERE entry_id = ?", (entry_id,))}
            view = build_view(entry, results, overrides, verified)
            summary = summarize(entry, view)
            db.execute("UPDATE entries SET view = ?, summary = ? WHERE id = ?",
                       (json.dumps(view, ensure_ascii=False), json.dumps(summary, ensure_ascii=False),
                        entry_id))

    def rebuild_all(self) -> None:
        for i in self.ids():
            self.rebuild(i)

    # ── Reads ──────────────────────────────────────────────────────────

    def ids(self, status: str | None = None) -> list[int]:
        with self._db() as db:
            q = "SELECT id FROM entries" + (" WHERE fetch_status = ?" if status else "")
            return [r[0] for r in db.execute(q + " ORDER BY id", (status,) if status else ())]

    def word_of(self, entry_id: int) -> str | None:
        with self._db() as db:
            row = db.execute("SELECT word FROM entries WHERE id = ?", (entry_id,)).fetchone()
            return row[0] if row else None

    def _row(self, r: sqlite3.Row) -> dict:
        return {
            "id": r["id"], "word": r["word"], "status": r["status"], "tags": json.loads(r["tags"]),
            "fetch_status": r["fetch_status"], "extras": json.loads(r["extras"]),
            "summary": json.loads(r["summary"] or "{}"), "updated_at": r["updated_at"],
            "created_at": r["created_at"], "dup": duplicate_key(r["word"]),
        }

    def rows(self) -> list[dict]:
        with self._db() as db:
            return [self._row(r) for r in db.execute("SELECT * FROM entries ORDER BY word")]

    def get(self, entry_id: int) -> dict | None:
        with self._db() as db:
            r = db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if r is None:
                return None
            results = {x["source"]: {"status": x["status"], "error": x["error"],
                                     "counts": json.loads(x["counts"]), "fetched_at": x["fetched_at"],
                                     "data": json.loads(x["data"])}
                       for x in db.execute("SELECT * FROM results WHERE entry_id = ?", (entry_id,))}
        out = self._row(r)
        out.update({
            "note": r["note"], "primary_sense": r["primary_sense"],
            "default_accent": r["default_accent"], "photo_refs": r["photo_refs"],
            "card_refs": r["card_refs"], "fetch_error": r["fetch_error"], "fetched_at": r["fetched_at"],
            "view": json.loads(r["view"] or "{}"), "results": results,
        })
        return out

    def results_matrix(self) -> list[tuple[int, str, str, dict]]:
        """(entry id, source, status, data) for coverage."""
        with self._db() as db:
            return [(r["entry_id"], r["source"], r["status"], json.loads(r["data"]))
                    for r in db.execute("SELECT r.* FROM results r JOIN entries e ON e.id = r.entry_id "
                                        "WHERE e.status = 'active'")]
