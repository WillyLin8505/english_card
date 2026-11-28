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


def test_lean_review_tsv_drops_both_ways_and_overrides_zh():
    """owner 11/27 lean format: '-2' and '2<TAB>-2' both drop a sense; adore=非常喜歡 overrides ECDICT."""
    doc = {'batch': 91, 'entries': [{'word': 'like', 'pos': 'verb', 'shared': [{'group': 'g_x', 'senseId': 5}],
                                     'senses': [{'ssid': 'a', 'senseId': 1, 'group': 'g_a'},
                                                {'ssid': 'b', 'senseId': 2, 'group': 'g_b'},
                                                {'ssid': 'c', 'senseId': 3, 'group': 'g_c'}]}]}
    tsv = 'like/verb\t1\t喜歡\tenjoy adore=非常喜歡 like\nlike/verb\t2\t-2\nlike/verb\t-3\nlike/verb\t+\t按讚\t\n'
    out, missing = wl.apply_review(doc, tsv, 'test')
    senses = out['words'][0]['senses']
    assert missing == []
    assert [s.get('group') for s in senses] == ['g_x', 'g_a', 'g_b91_like_verb_2']
    ms = {m['w']: m for m in senses[1]['members']}
    assert set(ms) == {'enjoy', 'adore'}  # the headword itself is not a member
    assert ms['adore']['zh'] == '非常喜歡' and ms['adore']['zh_source'] == 'AI'
    assert ms['enjoy']['zh_source'] == 'ECDICT'


def test_parse_rels_aliases_and_junk():
    assert wl.parse_rels('Cherish:S period:broad fine:k nope bad:x') == {
        'cherish': 'synonym', 'period': 'broad', 'fine': 'kind'}


def test_review_column_five_sets_relation_and_short_rows_still_apply():
    """card #1484: column 5 is member:s|k|b. A row without it must still apply (the column used to be sliced off,
    and the 4-tuple unpack then crashed every review)."""
    doc = {'batch': 1, 'entries': [{'word': 'good', 'pos': 'adjective', 'shared': [],
                                    'senses': [{'ssid': 'a', 'senseId': 1, 'group': 'g_a'},
                                               {'ssid': 'b', 'senseId': 2, 'group': 'g_b'}]}]}
    tsv = 'good/adjective\t1\t好的\tfine great\tfine:s great:k\ngood/adjective\t2\t善良的\tkind\n'
    out, missing = wl.apply_review(doc, tsv, 'test')
    assert missing == []
    senses = out['words'][0]['senses']
    m1 = {m['w']: m for m in senses[0]['members']}
    assert m1['fine']['rel'] == 'synonym' and m1['great']['rel'] == 'kind'
    assert senses[1]['members'][0]['w'] == 'kind' and 'rel' not in senses[1]['members'][0]


def test_rel_labels_stay_inside_the_sense_and_repeat_is_a_no_op():
    doc = {'words': [{'word': 'good', 'pos': 'adjective', 'senses': [
        {'zh': '好的', 'members': [{'w': 'fine'}, {'w': 'great'}]},
        {'zh': '善良', 'members': [{'w': 'fine'}]}]}]}
    tsv = 'good/adjective\t好的\tfine:s great:b\n# skip\n\ngood/adjective\t善良\tfine:k\n'
    assert wl.apply_rel_labels(doc, tsv) == 3
    assert wl.apply_rel_labels(doc, tsv) == 0
    senses = doc['words'][0]['senses']
    assert senses[0]['members'][0]['rel'] == 'synonym'
    assert senses[0]['members'][1]['rel'] == 'broad'
    assert senses[1]['members'][0]['rel'] == 'kind'


def test_checker_relation_beats_a_missing_wordnet_link():
    assert wl.member_how(None, 'cherish', 'verb', {}, 'synonym') == 'synonym'
    assert wl.member_how(None, 'cherish', 'verb', {}) == 'unknown'
