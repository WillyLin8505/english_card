"""Card #1292 (問題回報 #1717): French usages are not ranked by the English
dictionaries (WordNet / ECDICT read beau as the English boyfriend → noun main)."""

import pytest

from app import app_pack
from app.app_pack import rank_usages
from test_card164_usages import _lx, _senses


def _beau():
    noun = _lx(1, "beau", "noun", _senses(1), 0)
    adj = _lx(2, "beau", "adj", _senses(3), 4)
    return noun, adj


def test_french_word_ignores_english_dictionaries(monkeypatch):
    def boom(word):
        raise AssertionError("English dictionaries must not vote for French")
    monkeypatch.setattr(app_pack, "dictionary_pos", boom)
    noun, adj = _beau()
    rank_usages([noun, adj], {}, language="fr")
    assert adj["usage_rank"] == 0 and noun["rare_usage"]


def test_english_word_still_uses_dictionaries(monkeypatch):
    calls = []

    def votes(word):
        calls.append(word)
        return (2, {"noun": 2}, {"noun": 2})
    monkeypatch.setattr(app_pack, "dictionary_pos", votes)
    noun, adj = _beau()
    rank_usages([noun, adj], {}, language="en")
    assert calls == ["beau"] and noun["usage_rank"] == 0
