"""問題回報 #303 (card #297): a part of speech the `pos` value names but no
definition uses (shack adj, hollow intj) must not become a full lexeme
with zero senses — a blank row in the app's 資料庫單字本."""

from __future__ import annotations

import sqlite3

from sqlalchemy import select

from app import exporter, qc_drift
from app import models as m
from app.materialize import materialize, poses_with_senses


def _seed(s, word: str, poses: list[str], defined: list[str] | None = None, **extra) -> None:
    defined = poses if defined is None else defined
    s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field="pos",
                       status="complete", items=[{"key": p, "pos": p} for p in poses]))
    s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field="definition",
                       status="complete", items=[{"key": f"{word}-{p}", "sense_key": f"{word}-{p}",
                                                  "pos": p, "gloss": f"{word} as {p}"} for p in defined]))
    for field, items in extra.items():
        s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field=field,
                           status="complete", items=items))
    s.flush()


def _full(s, word: str) -> dict[str, int]:
    return {lx.pos: lx.id for lx in s.execute(select(m.Lexeme).where(
        m.Lexeme.language == "en", m.Lexeme.normalized == word,
        m.Lexeme.status == "full")).scalars()}


def test_poses_with_senses_keeps_order_and_drops_blank_pos():
    pos = [{"pos": "noun"}, {"pos": "verb"}, {"pos": "adj"}]
    defs = [{"pos": "verb"}, {"pos": "noun"}]
    assert poses_with_senses(pos, defs) == ["noun", "verb"]
    # senses without a part of speech go to the first listed one
    assert poses_with_senses(pos, [{"pos": "verb"}, {"gloss": "x"}]) == ["noun", "verb"]
    # a definition's part of speech the pos value forgot is still built
    assert poses_with_senses([{"pos": "noun"}], [{"pos": "noun"}, {"pos": "intj"}]) == ["noun", "intj"]
    assert poses_with_senses([], [{"gloss": "x"}]) == []
    # no definitions yet (partial run): placeholders for every listed part of speech
    assert poses_with_senses(pos, []) == ["noun", "verb", "adj"]


def test_pos_without_definitions_gets_no_lexeme(session):
    _seed(session, "shack", ["noun", "verb", "adj"], defined=["noun", "verb"])
    materialize(session, "en", "shack")
    assert sorted(_full(session, "shack")) == ["noun", "verb"]
    assert qc_drift.pos_without_lexeme(session) == {}
    assert session.execute(select(m.Lexeme).where(m.Lexeme.normalized == "shack",
                                                   m.Lexeme.pos == "adj")).first() is None


def test_existing_blank_lexeme_is_redirected_on_rerun(session):
    _seed(session, "hollow", ["adj", "noun", "intj"])
    materialize(session, "en", "hollow")
    before = _full(session, "hollow")
    assert sorted(before) == ["adj", "intj", "noun"]
    # a later run adopts no intj sense (Kaikki's only one was filtered)
    fv = session.execute(select(m.FieldValue).where(m.FieldValue.lemma == "hollow",
                                                    m.FieldValue.field == "definition")).scalar_one()
    fv.items = [i for i in fv.items if i["pos"] != "intj"]
    session.flush()
    _seed(session, "empty", ["adj"], synonyms=[{"word": "hollow", "pos": "intj"}])
    materialize(session, "en", "empty")  # links to the blank intj lexeme
    materialize(session, "en", "hollow")
    after = _full(session, "hollow")
    assert sorted(after) == ["adj", "noun"]
    assert after["adj"] == before["adj"] and after["noun"] == before["noun"]
    redirect = session.get(m.LexemeRedirect, before["intj"])
    assert redirect is not None and redirect.new_id == before["adj"]
    rel = session.execute(select(m.LexemeRelation).where(
        m.LexemeRelation.relation == "synonyms")).scalar_one()
    assert rel.target_lexeme_id == before["adj"]


def test_exporter_leaves_blank_lexeme_out_but_keeps_it_as_link_target(session, tmp_path):
    _seed(session, "shack", ["noun"])
    materialize(session, "en", "shack")
    blank = m.Lexeme(language="en", lemma="shack", normalized="shack", pos="adj", status="full",
                     cefr="C1")
    session.add(blank)
    session.flush()
    _seed(session, "hut", ["noun"], synonyms=[{"word": "shack", "pos": "adj"}])
    materialize(session, "en", "hut")
    rel = session.execute(select(m.LexemeRelation).where(
        m.LexemeRelation.relation == "synonyms")).scalar_one()
    assert rel.target_lexeme_id == blank.id
    counts, *_ = exporter._build(session, tmp_path / "pack.sqlite", "en", "zh-TW", None, False,
                                 tmp_path)
    assert counts["lexemes"] == 2 and counts["lexemes_without_senses"] == 1
    con = sqlite3.connect(tmp_path / "pack.sqlite")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    rows = dict(con.execute("SELECT pos, status FROM lexemes WHERE normalized = 'shack'"))
    assert rows == {"noun": "full", "adj": "stub"}
    assert con.execute("SELECT count(*) FROM lexemes l WHERE status = 'full' AND NOT EXISTS "
                       "(SELECT 1 FROM senses s WHERE s.lexeme_id = l.id)").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM relations WHERE target_lexeme_id = ?",
                       (blank.id,)).fetchone()[0] == 1
