"""Card #1450: pure helpers of lexicon/tools/word_ladder.py (no Qwen, no WordNet needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import word_ladder as wl  # noqa: E402


def test_spelling_variant():
    assert wl.spelling_variant('jewelry', 'jewellery')
    assert wl.spelling_variant('categorise', 'categorize')
    assert not wl.spelling_variant('hug', 'embrace')


def test_inflected():
    assert wl.inflected('kisses', 'kiss', [])
    assert wl.inflected('making', 'make', [])
    assert not wl.inflected('hug', 'kiss', [])


def test_exclusions_cover_months_numbers_units():
    for w in ('april', 'monday', 'seven', 'metre', 'be'):
        assert w in wl.EXCLUDE


def test_compact_candidate_format():
    e = {'word': 'x', 'pos': 'adjective', 'level': 'A1', 'lexemeId': 1, 'shared': [], 'old': [],
         'senses': [{'ssid': 's', 'senseId': 2, 'group': 'g_s', 'gloss': 'g', 'example': '',
                     'candidates': [{'w': 'quickly', 'level': 'A2', 'adverb': True, 'from': 'quick', 'broad': False}]}]}
    assert wl.compact(e)['senses'][0]['cands'] == ['quickly|A2|adv<-quick']
