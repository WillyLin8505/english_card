"""SQLite form of a language pack (card #428, 問題回報 #423, owner decision B).

The app used to parse the whole pack JSON (61 MB bundled, 260 MB live) into
Dart objects at every launch: 636 MB on Windows, more on an iPhone (#419).
The SQLite pack keeps one row per lexeme and the app reads only the small
`head` of every row at launch (4 MB of JSON: id, lemma, pos, forms, CEFR…);
senses and the rest (examples, relations, etymology, pronunciations…) are
zlib-compressed JSON blobs fetched per word when a screen needs them.

Schema (format_version 1, mirrored by app/lib/services/lexicon_sqlite.dart):

    meta(key TEXT PRIMARY KEY, value BLOB)   -- zlib(JSON) of every top-level
                                             -- pack key except `lexemes`,
                                             -- plus format_version
    lexemes(id INTEGER PRIMARY KEY, ord INTEGER, head TEXT, senses BLOB, body BLOB)
        head   JSON of the row without `senses` and the BODY_KEYS
        senses zlib(JSON list) or NULL
        body   zlib(JSON object of the BODY_KEYS present) or NULL
        ord    position in the pack's lexeme order (usage ranking, deltas)

Usage:
    python pack_sqlite.py app/assets/lexicon/en-zh-TW.json [out.sqlite] [--slim]
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import zlib
from collections import defaultdict
from pathlib import Path

FORMAT_VERSION = 1
BODY_KEYS = frozenset({"examples", "relations", "morphemes", "etymology", "pronunciations", "missing"})

# What LexRelation.fromJson reads (lexicon_pack.dart); the detail screen shows
# synonyms / antonyms / homophones / derived_terms / related / near_homophones /
# similar_spelling, so hyponyms and hypernyms stay out of a slim pack.
RELATION_FIELDS = ("relation", "word", "lexeme_id", "native", "cefr", "zipf", "rarity",
                   "hide_by_default")
RELATION_KINDS = {"synonyms", "antonyms", "homophones", "derived_terms", "related",
                  "near_homophones", "similar_spelling"}
SLIM_EXAMPLES = 6
SLIM_RELATIONS = 8


def encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _blob(value) -> bytes | None:
    if value is None:
        return None
    return zlib.compress(encode(value), 6)


def _unblob(blob):
    return None if blob is None else json.loads(zlib.decompress(blob))


def split_row(row: dict) -> tuple[dict, list | None, dict]:
    """head (kept in memory by the app), senses, body (fetched per word)."""
    head = {k: v for k, v in row.items() if k != "senses" and k not in BODY_KEYS}
    body = {k: row[k] for k in BODY_KEYS if k in row}
    return head, row.get("senses"), body


def build(pack: dict, path: Path) -> Path:
    """Write `pack` as a SQLite file at `path` (atomically)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.executescript(
            # Card #852 (問題回報 #1111): a row is ~2 KB, so 4 KB pages left about
            # a quarter of the file empty (91 MB → 72 MB with 16 KB pages).
            "PRAGMA page_size=16384; PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
            "CREATE TABLE meta(key TEXT PRIMARY KEY, value BLOB NOT NULL);"
            "CREATE TABLE lexemes(id INTEGER PRIMARY KEY, ord INTEGER NOT NULL,"
            " head TEXT NOT NULL, senses BLOB, body BLOB);")
        meta = {k: v for k, v in pack.items() if k != "lexemes"}
        meta["format_version"] = FORMAT_VERSION
        con.executemany("INSERT INTO meta VALUES (?, ?)",
                        [(k, zlib.compress(encode(v), 6)) for k, v in meta.items()])

        def rows():
            for ord_, row in enumerate(pack.get("lexemes", [])):
                head, senses, body = split_row(row)
                yield (int(row["id"]), ord_, encode(head).decode(), _blob(senses),
                       _blob(body) if body else None)

        con.executemany("INSERT OR REPLACE INTO lexemes VALUES (?, ?, ?, ?, ?)", rows())
        con.execute("CREATE INDEX lexemes_ord ON lexemes(ord)")
        con.commit()
    finally:
        con.close()
    os.replace(tmp, path)
    return path


def read_meta(path: Path) -> dict:
    """The pack's top-level keys (no lexemes); {} when the file is not a pack."""
    try:
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        return {k: _unblob(v) for k, v in con.execute("SELECT key, value FROM meta")}
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def read_pack(path: Path) -> dict:
    """The whole pack back as JSON (tests, tooling); lexemes in `ord` order."""
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        pack = {k: _unblob(v) for k, v in con.execute("SELECT key, value FROM meta")}
        pack.pop("format_version", None)
        lexemes = []
        for head, senses, body in con.execute(
                "SELECT head, senses, body FROM lexemes ORDER BY ord"):
            row = json.loads(head)
            if senses is not None:
                row["senses"] = _unblob(senses)
            row.update(_unblob(body) or {})
            lexemes.append(row)
        pack["lexemes"] = lexemes
        return pack
    finally:
        con.close()


def slim_lexeme(lx: dict, *, examples: int = SLIM_EXAMPLES, relations: int = SLIM_RELATIONS,
                bundled_audio: set[str] | None = None) -> dict:
    """The row the app actually reads (card #268): no sense pictures or
    relation detail, at most `examples` sentences and `relations` per kind,
    two IPA rows and the audio clips (`bundled_audio`: only those; None: all)."""
    if lx.get("status") != "full" or "redirect_to" in lx:
        return lx
    out = dict(lx)
    out["senses"] = [{k: v for k, v in sn.items() if k != "images"} for sn in lx.get("senses", [])]
    by_kind: dict[str, list] = defaultdict(list)
    for r in lx.get("relations", []):
        if r.get("relation") not in RELATION_KINDS:
            continue
        by_kind[r["relation"]].append(
            {k: r[k] for k in RELATION_FIELDS if k in r and r[k] not in (None, False)})
    rels = []
    for kind, items in by_kind.items():
        items.sort(key=lambda r: bool(r.get("hide_by_default")))  # stable: keep rank, hidden last
        rels.extend(items[:relations])
    out["relations"] = rels
    out["examples"] = lx.get("examples", [])[:examples]
    # LexEntry.fromJson reads the first `ipa` and the `audio` clips; phoneme /
    # stress / syllable rows and null fields only cost bytes.
    ipa = [pr for pr in lx.get("pronunciations", []) if pr.get("kind") == "ipa"]
    ipa.sort(key=lambda pr: not pr.get("default"))
    audio = [pr for pr in lx.get("pronunciations", [])
             if pr.get("kind") == "audio" and (pr.get("audio") or "")
             and (bundled_audio is None or pr.get("audio") in bundled_audio)]
    out["pronunciations"] = [
        {k: v for k, v in pr.items() if v not in (None, "", False)} for pr in ipa[:2] + audio
    ]
    return out


def slim_pack(pack: dict, **kw) -> dict:
    """The pack with every lexeme slimmed; metadata untouched."""
    return {**pack, "lexemes": [slim_lexeme(lx, **kw) for lx in pack.get("lexemes", [])]}


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    source = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else source.with_suffix(".sqlite")
    pack = json.loads(source.read_text(encoding="utf-8"))
    if "--slim" in argv:
        pack = slim_pack(pack)
    build(pack, out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(pack.get('lexemes', []))} lexemes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
