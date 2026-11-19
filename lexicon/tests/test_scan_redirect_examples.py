"""Card #1229: verify redirect evidence, retain genuine missing-word flags."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import scan_library as scan
from app import quality


def merged_pack(source='lying down', target='lie down', text='Sami was lying down on the bed.'):
    pack = {'lexemes': [
        {'id': 1, 'lemma': target, 'normalized': target, 'pos': 'verb',
         'status': 'full', 'senses': [], 'examples': []},
        {'id': 2, 'lemma': source, 'normalized': source, 'pos': 'verb',
         'status': 'full', 'senses': [],
         'examples': [{'id': 30, 'text': text, 'source': 'tatoeba', 'quality_flags': []}]},
    ]}
    quality.apply_decisions(pack, {'redirect': {'2': 1}})
    return pack


def checks(pack):
    return scan.scan_pack(pack)['groups']['E']['checks']


@pytest.mark.parametrize('source,target,text', [
    ('lying down', 'lie down', 'Sami was lying down on the bed.'),
    ('bent over', 'bend over', 'Sami bent over to pick it up.'),
    ('bronchi', 'bronchus', 'The doctor examined her bronchi.'),
    ('oxen', 'ox', 'The oxen crossed the field.'),
])
def test_accepts_verified_redirect_forms_without_mutating_pack(source, target, text):
    pack = merged_pack(source, target, text)
    before = copy.deepcopy(pack)
    assert 'missing_lemma' in scan.example_flags(text, target, 'verb')
    assert checks(pack)['examples_missing_lemma']['n'] == 0
    assert pack == before


@pytest.mark.parametrize('mutation', ['unrelated', 'no_redirect', 'wrong_target', 'partial_phrase', 'substring', 'missing'])
def test_merged_from_never_disables_real_missing_word_detection(mutation):
    pack = merged_pack()
    target, source = pack['lexemes']
    ex = target['examples'][0]
    if mutation == 'unrelated':
        ex['merged_from'] = 'Sami'
    elif mutation == 'no_redirect':
        source.pop('redirect_to')
        pack['redirects'].clear()
    elif mutation == 'wrong_target':
        source['redirect_to'] = 999
        pack['redirects']['2'] = 999
    else:
        ex['text'] = {'partial_phrase': 'Sami was lying about the weather.',
                      'substring': 'Sami was lying downward on the bed.',
                      'missing': 'Sami was sitting on the bed.'}[mutation]
    rows = checks(pack)['examples_missing_lemma']['rows']
    assert any(row['lexeme_id'] == 1 and row['example_id'] == 30 for row in rows)


def test_names_keep_every_occurrence_and_redirect_origin():
    pack = merged_pack()
    source = pack['lexemes'][1]
    source['examples'] += [dict(id=i, text=f'Sami was lying down near gate {i}.', source='tatoeba')
                           for i in range(31, 71)]
    report = scan.scan_pack(pack)
    row = report['groups']['E']['checks']['examples_odd_tatoeba_names']
    assert row['n'] == len(row['rows']) == 42
    assert len(row['samples']) == 2
    assert len({r['row_id'] for r in row['rows']}) == 42
    merged = next(r for r in row['rows'] if r['lexeme_id'] == 1)
    assert merged['source_lexeme_id'] == 2
    assert merged['source'] == 'tatoeba'
    assert merged['merged_from'] == 'lying down'
    assert merged['matches'] == ['Sami']
    pack['lexemes'].reverse()
    source['examples'].reverse()
    assert checks(pack)['examples_odd_tatoeba_names']['rows'] == row['rows']


def test_row_delta_tracks_add_remove_and_same_id_text_changes():
    pack = merged_pack()
    before = scan.scan_pack(pack)
    pack['lexemes'][0]['examples'] = []
    source = pack['lexemes'][1]
    source['examples'][0]['text'] = 'Sami was lying down outside.'
    source['examples'].append({'id': 40, 'source': 'tatoeba', 'text': 'Ziri was lying down.'})
    after = scan.scan_pack(pack)
    diff = scan.delta_against(after, before)['E.examples_odd_tatoeba_names']['row_diff']
    assert len(diff['added']) == len(diff['removed']) == len(diff['changed']) == 1
    assert diff['added'][0]['example_id'] == 40
    assert diff['removed'][0]['lexeme_id'] == 1
    assert diff['changed'][0]['before']['text'] != diff['changed'][0]['after']['text']


def test_cli_explicit_previous_for_group_only_scan(tmp_path):
    pack = merged_pack()
    previous = tmp_path / 'previous.json'
    previous.write_text(json.dumps(scan.scan_pack(pack)), encoding='utf-8')
    pack['lexemes'][0]['examples'] = []
    fixture = tmp_path / 'fixture.json'
    fixture.write_text(json.dumps(pack), encoding='utf-8')
    out = tmp_path / 'out'
    assert scan.main(['--pack', str(fixture), '--only', 'E', '--previous', str(previous), '--out', str(out)]) == 0
    report = json.loads(next(out.glob('scan-*.json')).read_text(encoding='utf-8'))
    diff = report['delta']['E.examples_odd_tatoeba_names']
    assert diff['diff'] == -1
    assert len(diff['row_diff']['removed']) == 1


def test_old_report_has_no_invented_row_delta_and_fallback_ids_are_stable():
    pack = merged_pack()
    for lx in pack['lexemes']:
        for ex in lx['examples']:
            ex.pop('id')
    before = scan.scan_pack(pack)
    old = copy.deepcopy(before)
    old['groups']['E']['checks']['examples_odd_tatoeba_names'].pop('rows')
    assert scan.delta_against(before, old)['E.examples_odd_tatoeba_names']['row_diff'] is None
    pack['lexemes'].reverse()
    assert checks(pack)['examples_odd_tatoeba_names']['rows'] == before['groups']['E']['checks']['examples_odd_tatoeba_names']['rows']


def test_invalid_previous_fails_before_building_live_pack(tmp_path, monkeypatch):
    def forbidden_build():
        pytest.fail('invalid input must fail before building the live pack')
    monkeypatch.setattr(scan, 'build_pack', forbidden_build)
    with pytest.raises(SystemExit) as caught:
        scan.main(['--previous', str(tmp_path / 'missing.json')])
    assert caught.value.code == 2
