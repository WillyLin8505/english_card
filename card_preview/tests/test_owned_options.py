import copy
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import pytest

from domain import live_exercise, prepare_exercise
from server import PreviewService, make_handler
from test_preview import packet, word
from test_confusable_options import relation


def ownership_word():
    w = word(1, 'coat')
    w['senses'][0]['translation'] = '外套'
    w['examples'][0]['text'] = 'Put on your coat.'
    w['images'] = [dict(sense_id=1, sense_image_id=1)]
    w['relations'] = [relation(2, 'circuit card', '電路板', 'similar_spelling'),
                      relation(3, 'carte du jour', '今日菜單', 'similar_spelling'),
                      relation(4, 'boat', '小船'), relation(5, 'goat', '山羊')]
    return w


@pytest.mark.parametrize('kind', ['similar', 'photo_choice'])
def test_only_owned_candidates_and_do_not_mutate_dictionary(kind):
    w = ownership_word()
    original = copy.deepcopy(w)
    result = live_exercise(w, kind, 1, owned_lexeme_ids={1, 4, 5})
    assert result['available']
    assert {o['label'] for o in result['options']} == {'coat', 'boat', 'goat'}
    assert w == original


@pytest.mark.parametrize('kind', ['similar', 'photo_choice'])
@pytest.mark.parametrize('owned', [None, set(), {4, 5}, {1}, {1, 4}])
def test_missing_scope_unowned_target_or_insufficient_owned_candidates(kind, owned):
    result = live_exercise(ownership_word(), kind, 1, owned_lexeme_ids=owned)
    assert not result['available']
    assert not result.get('options')


def test_duplicate_owned_id_is_not_two_candidates():
    w = ownership_word()
    w['relations'] = [relation(4, 'boat', '小船'), relation(4, 'boats', '船隻')]
    result = live_exercise(w, 'photo_choice', 1, owned_lexeme_ids={1, 4})
    assert not result['available']


@pytest.mark.parametrize('owned', [None, {1}, {1, 2}, {1, 2, 3}])
def test_live_drag_requires_owned_labels(owned, tmp_path):
    class Repo:
        def drag_exercise(self, word, sense):
            return {'available': True, 'options': [
                {'id': i, 'label': label} for i, label in
                [(1, 'coat'), (2, 'boat'), (3, 'goat')]]}
    service = PreviewService(repo=Repo(), state=object())
    with patch('server.BASE', tmp_path):
        result = service.exercise(ownership_word(), 'drag', 1, owned_lexeme_ids=owned)
    assert result['available'] == (owned == {1, 2, 3})
    if not result['available']:
        assert not result.get('options')


def test_reviewed_drag_requires_owned_labels():
    cards, bundle = packet('drag')
    cards[1]['images'] = [dict(sense_id=1, sense_image_id=1)]
    bundle['sense_image_id'] = 1
    for option in bundle['options']:
        option['box'] = [0, 0, .25, .25]
    assert prepare_exercise(cards[1], 'drag', 1, bundle, cards,
                            owned_lexeme_ids={1, 2, 3})['available']
    result = prepare_exercise(cards[1], 'drag', 1, bundle, cards, owned_lexeme_ids={1})
    assert not result['available']
    assert all(o['id'] == 1 for o in result['options'])


@pytest.mark.parametrize('kind', ['similar', 'photo_choice', 'cloze'])
def test_approved_packet_cannot_bypass_ownership(kind):
    cards, bundle = packet(kind)
    cards[1]['senses'][0]['translation'] = '蘋果'
    cards[2]['senses'][0]['translation'] = '書本'
    cards[3]['senses'][0]['translation'] = '鞋子'
    cards[1]['relations'] = [relation(2, 'book', '書本'), relation(3, 'shoe', '鞋子')]
    cards[1]['images'] = [dict(sense_id=1, sense_image_id=1)]
    bundle['sense_image_id'] = 1
    assert prepare_exercise(cards[1], kind, 1, bundle, cards, owned_lexeme_ids={1, 2, 3})['available']
    for owned in (None, {1, 2}):
        result = prepare_exercise(cards[1], kind, 1, bundle, cards, owned_lexeme_ids=owned)
        assert not result['available']
        assert all(o['id'] in (owned or set()) for o in result['options'])


@pytest.mark.parametrize('kind', ['similar', 'photo_choice'])
def test_service_passes_scope_to_live_and_reviewed_paths(kind, tmp_path):
    service = PreviewService(repo=object(), state=object())
    w = ownership_word()
    with patch('server.BASE', tmp_path):
        assert not service.exercise(w, kind, 1)['available']
        result = service.exercise(w, kind, 1, owned_lexeme_ids={1, 4, 5})
        assert result['available']
        assert {o['id'] for o in result['options']} == {1, 4, 5}
        folder = tmp_path / 'exercise-input'
        folder.mkdir()
        (folder / f'1-1-{kind}-zh-TW.json').write_text(json.dumps({'options': []}), encoding='utf-8')
        with patch('server.prepare_exercise', return_value={}) as prepare:
            service.exercise(w, kind, 1, owned_lexeme_ids={1, 4, 5})
            assert prepare.call_args.kwargs['owned_lexeme_ids'] == {1, 4, 5}


def test_http_scope_is_per_request_and_missing_scope_never_reuses_previous_library(tmp_path):
    class Repo:
        def entry(self, *args):
            return ownership_word()

    service = PreviewService(repo=Repo(), state=object())
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/api/exercise/1?target=en&native=zh-TW&kind=similar&sense=1'

    def post(body, token=True):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Preview-Token'] = service.token
        return urlopen(Request(url, data=json.dumps(body).encode('utf-8'), headers=headers))

    try:
        with patch('server.BASE', tmp_path):
            with post({'owned_lexeme_ids': [1, 4, 5]}) as response:
                result = json.load(response)
            assert result['available']
            assert {o['id'] for o in result['options']} == {1, 4, 5}
            with urlopen(url) as response:
                assert not json.load(response)['available']
            with post({'owned_lexeme_ids': [1, 4]}) as response:
                assert not json.load(response)['available']
            for body in ({}, [], {'owned_lexeme_ids': ['1']}, {'owned_lexeme_ids': [True]}):
                with pytest.raises(HTTPError) as error:
                    post(body)
                assert error.value.code == 400
                error.value.close()
            with pytest.raises(HTTPError) as error:
                post({'owned_lexeme_ids': [1, 4, 5]}, token=False)
            assert error.value.code == 403
            error.value.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
