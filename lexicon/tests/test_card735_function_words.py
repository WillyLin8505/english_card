"""Card 735 / 問題回報 #880 + #887 (owner option B): function-word synonyms, near_homophones and homophones are
hidden from every source; other relation kinds and content words keep their current rule."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.function_words import ALL_SOURCE_HIDDEN_RELATIONS, is_noisy_function_word_relation  # noqa: E402


def test_function_word_synonyms_and_homophones_hidden_for_all_sources():
    for source in ("datamuse", "oewn", "kaikki", "cmudict"):
        for kind in ALL_SOURCE_HIDDEN_RELATIONS:
            assert is_noisy_function_word_relation("be", source, kind), (source, kind)
    assert is_noisy_function_word_relation("the", "oewn", "synonyms")  # the→le (kaikki) style rows
    assert is_noisy_function_word_relation("be", "oewn", "synonyms")  # be→beryllium


def test_other_kinds_and_content_words_are_not_hidden_by_this_rule():
    assert not is_noisy_function_word_relation("be", "oewn", "derived_terms")
    assert not is_noisy_function_word_relation("be", "kaikki", "derived_terms")
    assert not is_noisy_function_word_relation("apple", "oewn", "synonyms")
    assert not is_noisy_function_word_relation("apple", "cmudict", "homophones")
    assert not is_noisy_function_word_relation("can", "oewn", "synonyms")  # can is also a noun
