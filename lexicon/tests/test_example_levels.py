"""Per-level example targets (問題回報 #21 decision, 2026-10-14): an A1/A2
headword needs sentences A1–B2 only; B1 and harder words need all six."""

from __future__ import annotations

from app.adapters import Context
from app.pipeline import expected_slots


def _ctx(word: str, level: str | None) -> Context:
    ctx = Context("en", "zh-TW", word, word)
    if level:
        ctx.resolved["cefr"] = [{"level": level}]
    return ctx


def test_easy_words_need_no_c1_c2_sentences():
    assert expected_slots("example_sentences", _ctx("apple", "A1")) == {"A1", "A2", "B1", "B2"}
    assert expected_slots("example_sentences", _ctx("basket", "A2")) == {"A1", "A2", "B1", "B2"}
    assert expected_slots("example_sentences", _ctx("survey", "B1")) \
        == {"A1", "A2", "B1", "B2", "C1", "C2"}


def test_without_a_stored_level_the_word_list_decides():
    assert "C2" not in expected_slots("example_sentences", _ctx("apple", None))  # CEFR-J A1


def test_relation_targets_are_unchanged():
    assert expected_slots("synonyms", _ctx("apple", "A1")) == {"A1", "A2", "B1", "B2", "C1", "C2"}
