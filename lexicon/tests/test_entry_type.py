"""問題回報 #5: phrase-type labels reach the app pack."""

import sqlite3
import tempfile
from pathlib import Path

from app import app_pack, exporter
from app.text import entry_type_of


def test_entry_type_of_is_a_pure_token_count_rule():
    assert entry_type_of("apple") == "word"
    assert entry_type_of("turn off") == "phrase"
    assert entry_type_of("give up") == "phrase"
    assert entry_type_of("well-known") == "word"  # hyphenated, single token
    assert entry_type_of("") == "word"


def test_app_pack_tags_multi_word_lexemes_full_and_stub():
    tmp = Path(tempfile.mktemp(suffix=".sqlite"))
    con = sqlite3.connect(tmp)
    con.executescript(exporter.DDL)
    for key, value in (("schema_version", "5"), ("target_language", "en"),
                       ("native_language", "zh-TW"), ("created_at", "2026-10-16"),
                       ("card_template", "null")):
        con.execute("INSERT INTO meta VALUES (?,?)", (key, value))
    con.execute("INSERT INTO lexemes VALUES (?,?,?,?,?,?,?,?)",
                (1, "en", "apple", "apple", "noun", "full", None, None))
    con.execute("INSERT INTO lexemes VALUES (?,?,?,?,?,?,?,?)",
                (2, "en", "turn off", "turn off", "verb", "full", None, None))
    con.execute("INSERT INTO lexemes VALUES (?,?,?,?,?,?,?,?)",
                (3, "en", "on the table", "on the table", "phrase", "stub", None, None))
    con.commit()
    con.close()
    try:
        pack = app_pack.build(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    by_norm = {lx["normalized"]: lx for lx in pack["lexemes"]}
    assert by_norm["apple"]["entry_type"] == "word"
    assert by_norm["turn off"]["entry_type"] == "phrase"
    assert by_norm["on the table"]["entry_type"] == "phrase"  # stub too
