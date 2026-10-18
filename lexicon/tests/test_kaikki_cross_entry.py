"""Cross-entry form fallbacks must not pollute independent meanings (#251)."""
import pytest

from app.adapters.kaikki import Kaikki


@pytest.mark.parametrize('marker', ['form_of', 'alt_of', 'tags'])
@pytest.mark.parametrize('reverse', [False, True])
def test_fallback_considers_all_entries_of_same_pos(marker, reverse):
    fallback = {'glosses': ['form of another word']}
    fallback[marker] = ['form-of'] if marker == 'tags' else [{'word': 'other'}]
    entries = [{'pos': 'verb', 'senses': [fallback]},
               {'pos': 'verb', 'senses': [{'glosses': ['An independent meaning.']}]}]
    if reverse:
        entries.reverse()
    result = Kaikki().senses(entries, None)
    assert [s['gloss'] for s in result] == ['An independent meaning.']
    assert not result[0]['form_of']


def test_all_form_entries_keep_fallback_and_ignore_empty_gloss():
    entries = [{'pos': 'noun', 'senses': [
        {'glosses': [''], 'form_of': [{'word': 'other'}]},
        {'glosses': ['plural of other'], 'form_of': [{'word': 'other'}]}]}]
    assert [s['gloss'] for s in Kaikki().senses(entries, None)] == ['plural of other']


def test_other_pos_and_same_entry_behavior_preserved():
    entries = [{'pos': 'verb', 'senses': [
        {'glosses': ['form of other'], 'form_of': [{'word': 'other'}]}]},
        {'pos': 'noun', 'senses': [
            {'glosses': ['alternative form of other'], 'alt_of': [{'word': 'other'}]},
            {'glosses': ['Independent noun.']}]}]
    result = Kaikki().senses(entries, None)
    assert [(s['pos'], s['gloss']) for s in result] == [('noun', 'Independent noun.')]
