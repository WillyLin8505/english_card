"""問題回報 #284: an excluded part of speech (quality/excluded_pos.json) is
never adopted again, even when a source still offers it on force_refresh /
reresolve, and materialize never builds its lexeme."""

import json

from sqlalchemy import select

from app import models as m
from app import pipeline, pos_exclusions
from conftest import apple_data


def _with_verb(fakes):
    apple_data(fakes)
    k = fakes["kaikki"]
    k.data["pos"].append(({"pos": "verb"}, "verb", "verb"))
    k.data["definition"].append(({"pos": "verb", "gloss": "To pick apples.", "sense_key": "v1",
                                  "gloss_language": "en"}, "v1", "verb"))


def _exclude(rules: dict) -> None:
    pos_exclusions.PATH.write_text(json.dumps({"_note": "test", "en": rules}), encoding="utf-8")


def _poses(s) -> list[str]:
    return sorted(s.execute(select(m.Lexeme.pos).where(
        m.Lexeme.normalized == "apple", m.Lexeme.status == "full")).scalars())


def test_no_file_means_nothing_excluded():
    assert pos_exclusions.excluded("en", "apple") == set()


def test_excluded_pos_is_not_adopted_on_refresh(session, fakes):
    _with_verb(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", ["pos", "definition"], "force_refresh")
    assert _poses(session) == ["noun", "verb"]

    _exclude({"apple": {"verb": "main sense has no Chinese"}})
    for mode in ("force_refresh", "reresolve"):
        reps = pipeline.process_word(session, "en", "zh-TW", "apple", ["pos", "definition"], mode)
        for r in reps:
            if r.field in ("pos", "definition"):
                assert all(i.get("pos") != "verb" for i in r.items), (mode, r.field)
        assert _poses(session) == ["noun"], mode
    # The source's evidence is kept: only adoption is blocked.
    kept = session.execute(select(m.FieldCandidate.value).where(
        m.FieldCandidate.lemma == "apple", m.FieldCandidate.field == "pos")).scalars().all()
    assert {"pos": "verb"} in kept


def test_excluding_every_pos_leaves_a_stub(session, fakes):
    """Card #166 (alfred): a word whose every part of speech is excluded stops
    being a full entry; its lexeme stays as a stub link target."""
    _with_verb(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", ["pos", "definition"], "force_refresh")
    _exclude({"apple": {"noun": "x", "verb": "x"}})
    pipeline.process_word(session, "en", "zh-TW", "apple", ["pos", "definition"], "reresolve")
    assert _poses(session) == []
    assert session.execute(select(m.Lexeme.status).where(
        m.Lexeme.normalized == "apple")).scalars().all() == ["stub", "stub"]


def test_removing_the_entry_brings_the_pos_back(session, fakes):
    _with_verb(fakes)
    _exclude({"apple": {"verb": "x"}})
    pipeline.process_word(session, "en", "zh-TW", "apple", ["pos", "definition"], "force_refresh")
    assert _poses(session) == ["noun"]
    _exclude({})
    pipeline.process_word(session, "en", "zh-TW", "apple", ["pos", "definition"], "reresolve")
    assert _poses(session) == ["noun", "verb"]
