"""跨裝置自動同步 (card #912, 問題回報 #1173): every account has its own small SQLite file of
records and a folder of photo files, next to the #902 backup and gone with the account.

A record is one word, card, photo record, review log… (the App decides what `key` means). The
newest (stamp, device) wins and every accepted change takes the next `seq`, so a device asks for
"everything after the seq I last saw". The same push twice changes nothing. A deleted record stays as
a tombstone, otherwise a device that was offline would upload it again.
"""

import re
import shutil
import sqlite3

from . import config
from .accounts import AccountError
from . import models as m

RECORD_MAX_BYTES = 1024 * 1024
PUSH_MAX_RECORDS = 1000
PUSH_MAX_BYTES = 8 * 1024 * 1024
PULL_MAX_RECORDS = 1000
BLOB_MAX_BYTES = 25 * 1024 * 1024
ACCOUNT_BLOBS_MAX_BYTES = 2 * 1024 * 1024 * 1024

BLOB_ID = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
PHOTO_KEY = re.compile(r"^[^/]+/photos/(.+)$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  key TEXT PRIMARY KEY, stamp INTEGER NOT NULL, device TEXT NOT NULL,
  deleted INTEGER NOT NULL, data TEXT, seq INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS records_seq ON records (seq);
CREATE TABLE IF NOT EXISTS blobs (id TEXT PRIMARY KEY, size INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS counter (one INTEGER PRIMARY KEY CHECK (one = 1), seq INTEGER NOT NULL);
INSERT OR IGNORE INTO counter VALUES (1, 0);
"""


def _root(user: m.User):
    return config.MEDIA / "user_sync"


def _blob_dir(user: m.User):
    return _root(user) / str(user.id)


def _db(user: m.User) -> sqlite3.Connection:
    root = _root(user)
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / f"{user.id}.sqlite3", timeout=30, isolation_level=None)
    con.executescript(SCHEMA)
    return con


def _blob_path(user: m.User, blob_id: str):
    if not BLOB_ID.match(blob_id):
        raise AccountError(422, "照片代號不正確")
    return _blob_dir(user) / blob_id


def _drop_blob(con: sqlite3.Connection, user: m.User, blob_id: str) -> None:
    if BLOB_ID.match(blob_id):
        _blob_path(user, blob_id).unlink(missing_ok=True)
        con.execute("DELETE FROM blobs WHERE id = ?", (blob_id,))


def push(user: m.User, device: str, records: list) -> dict:
    """Stores what is newer than what the account has; returns the keys it took, ignores the rest."""
    if not isinstance(device, str) or not 0 < len(device) <= 64:
        raise AccountError(422, "裝置代號不正確")
    if not isinstance(records, list) or len(records) > PUSH_MAX_RECORDS:
        raise AccountError(413, "一次上傳的紀錄太多")
    accepted = ignored = 0
    con = _db(user)
    try:
        con.execute("BEGIN IMMEDIATE")
        seq = con.execute("SELECT seq FROM counter").fetchone()[0]
        for r in records:
            key, stamp, deleted = r["key"], r["stamp"], bool(r.get("deleted"))
            data = None if deleted else r["data"]
            if not isinstance(key, str) or not 0 < len(key) <= 400 or not isinstance(stamp, int):
                raise AccountError(422, "同步紀錄格式不正確")
            if not deleted and (not isinstance(data, str) or len(data.encode()) > RECORD_MAX_BYTES):
                raise AccountError(422, "同步紀錄格式不正確")
            old = con.execute("SELECT stamp, device FROM records WHERE key = ?", (key,)).fetchone()
            if old is not None and (stamp, device) <= (old[0], old[1]):
                ignored += 1
                continue
            seq += 1
            accepted += 1
            con.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?, ?, ?)",
                        (key, stamp, device, int(deleted), data, seq))
            photo = PHOTO_KEY.match(key)
            if deleted and photo:
                _drop_blob(con, user, photo[1])
        con.execute("UPDATE counter SET seq = ?", (seq,))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return {"accepted": accepted, "ignored": ignored, "seq": seq}


def pull(user: m.User, since: int, limit: int = PULL_MAX_RECORDS, device: str | None = None) -> dict:
    """Records after `since` in seq order. `next` moves past records of `device` too, which it left out."""
    limit = max(1, min(limit, PULL_MAX_RECORDS))
    con = _db(user)
    try:
        rows = con.execute("SELECT key, stamp, device, deleted, data, seq FROM records "
                           "WHERE seq > ? ORDER BY seq LIMIT ?", (since, limit + 1)).fetchall()
    finally:
        con.close()
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "records": [{"key": k, "stamp": st, "device": d, "deleted": bool(de), "data": da}
                    for k, st, d, de, da, _ in rows if d != device],
        "next": rows[-1][5] if rows else since,
        "more": more,
    }


def put_blob(user: m.User, blob_id: str, data: bytes) -> dict:
    """Photo bytes, stored once per photo id: an upload of the same photo replaces it."""
    path = _blob_path(user, blob_id)
    if not data:
        raise AccountError(422, "照片是空的")
    if len(data) > BLOB_MAX_BYTES:
        raise AccountError(413, "照片太大")
    con = _db(user)
    try:
        con.execute("BEGIN IMMEDIATE")
        used = con.execute("SELECT COALESCE(SUM(size), 0) FROM blobs WHERE id != ?", (blob_id,)).fetchone()[0]
        if used + len(data) > ACCOUNT_BLOBS_MAX_BYTES:
            raise AccountError(507, "雲端照片空間已滿")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        con.execute("INSERT OR REPLACE INTO blobs VALUES (?, ?)", (blob_id, len(data)))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return {"size": len(data)}


def load_blob(user: m.User, blob_id: str) -> bytes:
    path = _blob_path(user, blob_id)
    if not path.exists():
        raise AccountError(404, "雲端沒有這張照片")
    return path.read_bytes()


def remove_user(user: m.User) -> None:
    """Account deleted: its records and photos go with it."""
    (_root(user) / f"{user.id}.sqlite3").unlink(missing_ok=True)
    shutil.rmtree(_blob_dir(user), ignore_errors=True)
