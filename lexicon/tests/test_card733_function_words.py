"""Card 733 / 問題回報 #875: Datamuse rows of function words are hidden for every relation kind Datamuse fills;
other sources (oewn, kaikki, cmudict) and content words are untouched."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.function_words import FUNCTION_WORD_RELATIONS, is_noisy_function_word_relation  # noqa: E402


def test_datamuse_function_word_rows_are_noisy_for_all_datamuse_kinds():
    for kind in ("related", "hyponyms", "hypernyms", "synonyms", "antonyms", "homophones", "near_homophones"):
        assert kind in FUNCTION_WORD_RELATIONS
        assert is_noisy_function_word_relation("be", "datamuse", kind)


def test_other_sources_and_content_words_are_kept():
    # card #735 / #887: oewn / kaikki / cmudict synonyms, near_homophones and homophones are hidden now
    # (see test_card735_function_words.py); their other kinds stay visible.
    assert not is_noisy_function_word_relation("be", "kaikki", "antonyms")
    assert not is_noisy_function_word_relation("be", "oewn", "related")
    assert not is_noisy_function_word_relation("apple", "datamuse", "near_homophones")
    assert not is_noisy_function_word_relation("can", "datamuse", "synonyms")  # can is also a noun
    assert not is_noisy_function_word_relation("be", "datamuse", "derived_terms")
