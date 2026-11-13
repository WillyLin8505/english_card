"""Card #1187 (issue #1645): phrases with the headword are asked as phrases, not with the headword's sense."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from app.adapters.ai import phrase_context  # noqa: E402


def test_phrase_gets_phrase_context():
    ctx = phrase_context("box about", "box")
    assert ctx.startswith("vocabulary connected to box;")
    assert "whole phrase 'box about'" in ctx and "not of 'box' alone" in ctx


def test_hyphenated_phrase_counts():
    assert phrase_context("box-in", "box") is not None


def test_single_word_or_phrase_without_headword_keeps_sense_context():
    assert phrase_context("crate", "box") is None
    assert phrase_context("love tunnel", "box") is None


def test_lemma_still_parsed_from_new_context():
    from card831_qwen_apply import lemma_of
    assert lemma_of(phrase_context("box about", "box")) == "box"
