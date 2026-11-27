"""Sense alignment must abstain rather than cross meanings (card #1467)."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import word_ladder as wl


class Synset:
    def __init__(self, id, definition):
        self.id, self.gloss = id, definition

    def definition(self):
        return self.gloss

    def examples(self):
        return []

    def lemmas(self):
        return ['house']


@pytest.fixture
def resources(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.executescript('''
        create table lexemes(id integer, normalized text, pos text);
        create table senses(id integer, lexeme_id integer, labels text, definition text, ordinal integer);
        create table examples(sense_id integer, text text, ordinal integer);
        insert into lexemes values(1, 'house', 'noun'), (2, 'house', 'verb');
    ''')
    synsets = []

    class Wordnet:
        def synsets(self, word, pos):
            return synsets if word == 'house' and pos == 'n' else []

    monkeypatch.setattr(wl, '_lexdb', db)
    monkeypatch.setattr(wl, '_W', Wordnet())
    monkeypatch.setattr(wl, 'level', lambda *args: 'A1')

    def add(sid, gloss, lid=1, labels=''):
        db.execute('insert into senses values(?,?,?,?,?)', (sid, lid, labels, gloss, sid))

    yield synsets, add
    db.close()


def test_prefix_overlap_never_establishes_identity(resources):
    synsets, add = resources
    synsets.append(Synset('building-n', 'a building for human habitation'))
    add(10, 'a family governing a human habitation')
    assert wl.closest_sense_id('house', 'noun', synsets[0]) is None
    assert wl.best_synset('house', 'noun', 'a family governing a human habitation') is None
    senses = wl.all_senses('house', 'noun')
    assert len(senses) == 2
    assert senses[0]['sense_id'] is None
    assert senses[1]['sense_id'] == 10 and senses[1]['ss'] is None


def test_exact_definition_links_and_preserves_provenance(resources):
    synsets, add = resources
    synsets.append(Synset('building-n', 'A building for human habitation.'))
    add(10, 'a building for human habitation')
    senses = wl.all_senses('house', 'noun')
    assert len(senses) == 1 and senses[0]['sense_id'] == 10
    assert senses[0]['source']['id'] == 'building-n'


@pytest.mark.parametrize('definition', [
    'not a building for human habitation',
    'a building for human habitation or business',
    '(transitive) a building for human habitation',
])
def test_qualifiers_and_negation_are_not_discarded(resources, definition):
    synsets, add = resources
    synsets.append(Synset('building-n', 'a building for human habitation'))
    add(10, definition)
    assert wl.closest_sense_id('house', 'noun', synsets[0]) is None


def test_duplicate_definitions_abstain_in_both_directions(resources):
    synsets, add = resources
    synsets.append(Synset('building-n', 'a dwelling'))
    add(10, 'a dwelling')
    add(11, 'a dwelling')
    assert wl.closest_sense_id('house', 'noun', synsets[0]) is None
    wl.lexdb().execute('delete from senses where id=11')
    synsets.append(Synset('another-n', 'a dwelling'))
    assert wl.closest_sense_id('house', 'noun', synsets[0]) is None
    assert wl.best_synset('house', 'noun', 'a dwelling') is None


def test_wrong_pos_and_excluded_senses_cannot_supply_id(resources):
    synsets, add = resources
    synsets.append(Synset('building-n', 'a dwelling'))
    add(10, 'a dwelling', lid=2)
    add(11, 'a dwelling', labels='vulgar')
    assert wl.closest_sense_id('house', 'noun', synsets[0]) is None


def test_shared_candidates_do_not_merge_meanings():
    senses = [{'ssid': id, 'senseId': sid, 'gloss': id, 'candidates': [{'w': 'home'}]}
              for id, sid in [('building-n', 10), ('family-n', 11)]]
    stats = {'merged': 0}
    assert len(wl.merge_senses(senses, stats)) == 2 and stats['merged'] == 0


def document(*senses):
    return {'words': [{'word': 'house', 'pos': 'noun', 'senses': list(senses)}]}


def sense(ssid='building-n', sid=99, group='g_building', **extra):
    return dict(ssid=ssid, senseId=sid, group=group,
                members=[{'w': 'home', 'pos': 'noun'}], **extra)


def test_build_revalidates_legacy_id_against_definition(resources):
    synsets, add = resources
    synsets.append(Synset('building-n', 'a dwelling'))
    add(10, 'a dwelling')
    add(99, 'a dynasty')
    output, audit = wl.build_app_documents([document(sense())])
    assert output['senses'] == {'1:10': 'g_building'}
    assert audit['rows'][0]['oldSenseId'] == 99
    assert audit['rows'][0]['senseId'] == 10


def test_build_removes_all_competing_groups_order_independently(resources):
    synsets, add = resources
    synsets.append(Synset('building-n', 'a dwelling'))
    add(10, 'a dwelling')
    a, b = sense(group='g_one'), sense(group='g_two')
    first, audit = wl.build_app_documents([document(a, b)])
    second, _ = wl.build_app_documents([document(b, a)])
    assert first['senses'] == second['senses'] == {}
    assert audit['conflictingKeys'] == ['1:10']


def test_build_rejects_group_shared_by_different_meanings(resources):
    synsets, add = resources
    synsets.extend([Synset('building-n', 'a dwelling'), Synset('family-n', 'a dynasty')])
    add(10, 'a dwelling')
    add(11, 'a dynasty')
    output, audit = wl.build_app_documents([document(sense(), sense(ssid='family-n'))])
    assert output['senses'] == {} and output['groups'] == {}
    assert audit['conflictingGroups'] == ['g_building']


def test_unverified_rows_never_reach_asset(resources):
    synsets, add = resources
    add(99, 'a dynasty')
    output, audit = wl.build_app_documents([document(sense(ssid='foreign-v'), sense(ssid=None))])
    assert output['senses'] == {} and output['groups'] == {}
    assert all(row['senseId'] is None for row in audit['rows'])


def test_forged_or_stale_dictionary_provenance_is_rejected(resources):
    synsets, add = resources
    add(10, 'a dwelling')
    src = {'kind': 'dictionary', 'id': 10, 'lexemeId': 1, 'definition': 'a dynasty'}
    output, _ = wl.build_app_documents([document(sense(ssid=None, sid=10, source=src))])
    assert output['senses'] == {}


def test_old_group_cache_is_not_reused(tmp_path, monkeypatch):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'ssid_group': {'old': 'g_old'}, 'done_words': ['house']}), encoding='utf-8')
    monkeypatch.setattr(wl, 'STATE', str(state))
    assert wl.load_state()['ssid_group'] == {}
