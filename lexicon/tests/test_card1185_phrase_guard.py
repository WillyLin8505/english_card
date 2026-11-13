"""Card #1185 (issue #1643): a phrase answered with the headword's own term is kept out of writes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from card1049_guard import bad_reason, phrase_head_reason  # noqa: E402

BOX = ["箱子、箱、盒子", "一箱、箱", "證人席、分隔式雅座、包廂"]


def test_phrase_with_headword_term_is_blocked():
    assert phrase_head_reason("box about", "box", "箱子", BOX) == "phrase_head"
    assert phrase_head_reason("box in", "box", "盒子", BOX) == "phrase_head"


def test_term_plus_one_character_is_blocked():
    assert phrase_head_reason("box off", "box", "箱外", BOX) == "phrase_head"


def test_real_phrase_translation_is_kept():
    assert phrase_head_reason("box the compass", "box", "方格", BOX) is None
    assert phrase_head_reason("good afternoon", "afternoon", "下午好", ["下午"]) is None


def test_single_word_and_other_lemma_are_not_phrases():
    assert phrase_head_reason("box", "box", "箱子", BOX) is None
    assert phrase_head_reason("boxer about", "box", "箱子", BOX) is None


def test_bad_reason_passes_word_for_phrase_rule():
    assert bad_reason("箱子", BOX) is None
    assert bad_reason("箱子", BOX, "box about", "box") == "phrase_head"
    assert bad_reason("無此詞", BOX, "box about", "box") == "nonword"
