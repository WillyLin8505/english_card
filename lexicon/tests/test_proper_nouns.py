"""Relation words that the dictionary lists only as names are rejected
(問題回報 #22: brett-like people, Antarctica, brands), while capitalised common
nouns and words that are also common stay."""

from __future__ import annotations

from app import kaikki_index
from app.adapters import Candidate, Context
from app.adapters.base import is_proper_noun, validate

DICTIONARY = {
    "terrance": [{"word": "Terrance", "pos": "name"}],
    "antarctica": [{"word": "Antarctica", "pos": "name"}],
    "stein": [{"word": "Stein", "pos": "name"}, {"word": "stein", "pos": "noun"}],
    "bengal tiger": [{"word": "Bengal tiger", "pos": "noun"}],
}


def _dictionary(monkeypatch):
    is_proper_noun.cache_clear()
    monkeypatch.setattr(kaikki_index, "lookup",
                        lambda language, word, path=None: DICTIONARY.get(word.lower(), []))


def test_only_name_entries_make_a_proper_noun(monkeypatch):
    _dictionary(monkeypatch)
    assert is_proper_noun("terrance", "en") and is_proper_noun("Antarctica", "en")
    assert not is_proper_noun("stein", "en")          # also a beer mug
    assert not is_proper_noun("Bengal tiger", "en")   # a capitalised common noun
    assert not is_proper_noun("zyzzyva", "en")        # unknown: kept, other rules apply
    is_proper_noun.cache_clear()


def test_relation_validation_rejects_names(monkeypatch):
    _dictionary(monkeypatch)
    ctx = Context("en", "zh-TW", "terrace", "terrace")
    name = Candidate("similar_spelling", "en", {"word": "terrance"}, "terrance")
    word = Candidate("hyponyms", "en", {"word": "Bengal tiger"}, "bengal tiger")
    assert "專有名詞" in validate(name, ctx)
    assert validate(word, ctx) is None
    is_proper_noun.cache_clear()
