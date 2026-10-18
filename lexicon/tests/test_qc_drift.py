"""問題回報 #281: a part of speech removed from `lexemes` but still in the
adopted values comes back on the next re-run (marine verb). qc_drift
reports it so `qc.py check --live` catches the drift."""

from __future__ import annotations

import json

from sqlalchemy import delete, select

from app import models as m, pos_exclusions, qc_drift
from app.materialize import materialize


def _seed(s, word: str, poses: list[str]) -> None:
    s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field="pos",
                       status="complete", items=[{"key": p, "pos": p} for p in poses]))
    s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field="definition",
                       status="complete", items=[{"key": f"{word}-{p}", "sense_key": f"{word}-{p}",
                                                  "pos": p, "gloss": f"{word} as {p}"} for p in poses]))
    s.flush()


def _poses(s, word: str) -> list[str]:
    return sorted(s.execute(select(m.Lexeme.pos).where(
        m.Lexeme.language == "en", m.Lexeme.normalized == word,
        m.Lexeme.status == "full")).scalars())


def test_one_lexeme_per_pos_is_not_drift(session):
    _seed(session, "marine", ["adj", "noun", "verb"])
    materialize(session, "en", "marine")
    assert _poses(session, "marine") == ["adj", "noun", "verb"]
    assert qc_drift.pos_without_lexeme(session) == {}


def test_lexeme_deleted_but_value_kept_is_drift_and_comes_back(session):
    _seed(session, "marine", ["adj", "noun", "verb"])
    materialize(session, "en", "marine")
    session.execute(delete(m.Lexeme).where(m.Lexeme.normalized == "marine", m.Lexeme.pos == "verb"))
    session.flush()
    assert qc_drift.pos_without_lexeme(session) == {"marine": ["verb"]}
    assert qc_drift.metrics(session)[0] == {"v.entry.pos_not_materialized": 1,
                                            "v.entry.excluded_pos_present": 0}
    materialize(session, "en", "marine")  # what any re-run does
    assert _poses(session, "marine") == ["adj", "noun", "verb"]


def test_word_never_materialized_is_not_drift(session):
    _seed(session, "drape", ["noun"])
    assert qc_drift.pos_without_lexeme(session) == {}


def _exclude(word: str, pos: str) -> None:
    pos_exclusions.PATH.write_text(json.dumps({"en": {word: {pos: "test"}}}), encoding="utf-8")
    pos_exclusions._cache = None


def test_excluded_pos_is_not_rebuilt_and_existing_one_is_redirected(session):
    """問題回報 #284: the exclusion, not a deleted row, keeps the verb away."""
    _seed(session, "marine", ["adj", "noun", "verb"])
    materialize(session, "en", "marine")
    _exclude("marine", "verb")
    assert qc_drift.metrics(session)[0]["v.entry.excluded_pos_present"] == 1
    materialize(session, "en", "marine")  # re-run with the values still naming verb
    assert _poses(session, "marine") == ["adj", "noun"]
    assert qc_drift.pos_without_lexeme(session) == {}
    assert qc_drift.metrics(session)[0] == {"v.entry.pos_not_materialized": 0,
                                            "v.entry.excluded_pos_present": 0}
