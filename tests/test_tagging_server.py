"""Tests for tagger/tagging_server.py — no Ollama needed (the tagger is stubbed)."""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tagger'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pipeline'))
import tagging_server as ts  # noqa: E402
from ipa import arpabet_to_ipa  # noqa: E402


def _raw(word, **kw):
    c = {'word': word, 'pos': 'noun', 'evidence': 'a cup',
         'point': [538, 467], 'visual_confidence': 0.9, 'inferred': False}
    c.update(kw)
    return c


def test_to_candidates_cleans_clamps_and_dedups():
    raw = [
        _raw('Cup'),
        _raw(' pour  coffee ', pos='phrase', point=[138, 1200]),
        _raw('cup'),                                   # duplicate
        _raw('mug', point=[1]),                        # no point
        _raw('saucer', pos='thing', visual_confidence=85),
        _raw('ceramic', exclude=True),
    ]
    out = ts.to_candidates(raw, exclude=['ceramic'])
    assert [c['word'] for c in out] == ['cup', 'pour coffee', 'saucer']
    assert out[0] == {
        'word': 'cup', 'lemma': 'cup', 'pos': 'noun', 'meaning': '', 'cefr': None,
        'modelLevel': None,
        'evidence': 'a cup', 'point': [0.538, 0.467], 'visualConfidence': 0.7,
        'usefulness': 0.5, 'inferred': False, 'box': None,
    }
    assert out[1]['point'] == [0.138, 1.0]              # clamped
    assert out[2]['pos'] == 'noun' and out[2]['cefr'] is None
    assert out[2]['visualConfidence'] == 0.7 and out[2]['usefulness'] == 0.5


def test_prompt_levels_focus_languages_and_exclude():
    p = ts.build_prompt('B1')
    assert '6 to 8' in p and 'Do not translate' in p
    assert 'CEFR B1' not in p and 'Traditional Chinese' not in p
    assert 'specific, precise labels' in ts.build_prompt('B2', focus='harder')
    assert 'verbs' in ts.build_prompt('A1', focus='actions')
    p = ts.build_prompt('A1', lang='fr', native='en', exclude=['pomme'])
    assert 'useful French labels' in p
    assert 'Do not repeat these words: pomme.' in p
    assert 'translate' in p


def test_arpabet_to_ipa():
    assert arpabet_to_ipa('B AE1 L K AH0 N IY0') == '/ˈbælkəni/'
    assert arpabet_to_ipa('M AH1 G') == '/mʌɡ/'
    assert arpabet_to_ipa('AH0 B AE1 N D AH0 N') == '/əˈbændən/'
    assert arpabet_to_ipa('K AH0 M P Y UW1 T ER0') == '/kəmˈpjutɚ/'
    assert arpabet_to_ipa('X Y1') is None


def test_extract_image_raw_and_multipart():
    assert ts.extract_image('image/jpeg', b'JPEGDATA') == b'JPEGDATA'
    body = (b'--XX\r\nContent-Disposition: form-data; name="image"; filename="p.jpg"\r\n'
            b'Content-Type: image/jpeg\r\n\r\nJPEG\x00\xffDATA\r\n--XX--\r\n')
    assert ts.extract_image('multipart/form-data; boundary=XX', body) == b'JPEG\x00\xffDATA'
    assert ts.extract_image('multipart/form-data; boundary=XX', b'--XX--\r\n') is None


class _StubTagger:
    model = 'stub'
    ollama_url = 'http://stub'

    def __init__(self):
        self.calls = []

    def ollama_ok(self):
        return True

    def candidates(self, image, level, lang, native, focus, exclude):
        self.calls.append((image, level, lang, native, focus, exclude))
        return [{'word': 'mug', 'meaning': '馬克杯', 'cefr': 'A2', 'point': [0.5, 0.4]}]

    def _chat(self, prompt, schema, temperature=0, **_):
        self.calls.append(('chat', prompt))
        return {'items': [{'id': '0', 'text': '義大利麵'}]}

@pytest.fixture()
def server():
    stub = _StubTagger()
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), ts.make_handler(stub, 'secret'))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_address[1]}', stub
    httpd.shutdown()


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read().decode('utf-8')), r.headers


def test_tag_raw_body_with_key(server):
    base, stub = server
    status, body, headers = _post(
        f'{base}/tag?level=b1&lang=fr&native=en&focus=harder&exclude=pomme,tasse', b'JPEG',
        {'X-API-Key': 'secret', 'Content-Type': 'image/jpeg', 'Origin': 'http://localhost:8123'})
    assert status == 200
    assert body['candidates'][0]['meaning'] == '馬克杯'
    assert (body['level'], body['lang'], body['native']) == ('B1', 'fr', 'en')
    assert stub.calls == [(b'JPEG', 'B1', 'fr', 'en', 'harder', ['pomme', 'tasse'])]
    assert headers['Access-Control-Allow-Origin'] == 'http://localhost:8123'


def test_tag_defaults_for_unknown_params(server):
    base, stub = server
    _post(f'{base}/tag?level=Z&lang=de&focus=weird', b'JPEG',
          {'X-API-Key': 'secret', 'Content-Type': 'image/jpeg'})
    assert stub.calls == [(b'JPEG', 'A1', 'en', 'zh-TW', None, [])]


def test_ai_word_enrichment_is_disabled(server):
    base, stub = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(f'{base}/enrich', json.dumps({'word': 'mug'}).encode(),
              {'X-API-Key': 'secret', 'Content-Type': 'application/json'})
    assert e.value.code == 410
    assert stub.calls == []


def test_translate_serves_the_word_database_admin_in_taiwan_usage(server):
    base, stub = server
    status, body, _ = _post(
        f'{base}/translate',
        json.dumps({'lang': 'en', 'native': 'zh-TW', 'kind': 'word',
                    'items': [{'id': '0', 'text': 'pasta'}]}).encode(),
        {'X-API-Key': 'secret', 'Content-Type': 'application/json'})
    assert status == 200
    assert body['items'] == [{'id': '0', 'text': '義大利麵'}]
    assert body['promptVersion'] == ts.TRANSLATE_PROMPT_VERSION
    prompt = stub.calls[0][1]
    assert '台灣' in prompt and '意大利麵' in prompt  # names the Mainland words to avoid


def test_rejects_wrong_key(server):
    base, stub = server
    for path in ('/tag', '/enrich', '/translate'):
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(f'{base}{path}', b'JPEG', {'X-API-Key': 'nope', 'Content-Type': 'image/jpeg'})
        assert e.value.code == 401
    assert stub.calls == []


def test_preflight_and_health(server):
    base, _ = server
    req = urllib.request.Request(f'{base}/tag', method='OPTIONS',
                                 headers={'Origin': 'http://localhost:8123'})
    with urllib.request.urlopen(req) as r:
        assert r.status == 204
        assert 'X-API-Key' in r.headers['Access-Control-Allow-Headers']
    with urllib.request.urlopen(f'{base}/health') as r:
        body = json.loads(r.read())
    assert body['ok'] is True and body['model'] == 'stub'
    assert body['ollama'] is True and body['keyOk'] is None
    for key, ok in (('secret', True), ('nope', False)):
        req = urllib.request.Request(f'{base}/health', headers={'X-API-Key': key})
        with urllib.request.urlopen(req) as r:
            assert json.loads(r.read())['keyOk'] is ok


def test_label_area_is_kept_as_fractions():
    out = ts.to_candidates([_raw('cup', box=[100, 200, 600, 900]), _raw('mug', box=[5, 5, 6, 6])])
    assert out[0]['box'] == [0.1, 0.2, 0.6, 0.9]
    assert out[1]['box'] is None  # too small to be an area


def test_a_reply_cut_off_at_the_token_limit_keeps_its_complete_candidates():
    from tagging_server import loads_salvaging
    cut = '{"candidates":[{"word":"roof","pos":"noun"},{"word":"tree","evidence":"left, \\"tall}"},{"word":"sk'
    assert loads_salvaging(cut) == {"candidates": [{"word": "roof", "pos": "noun"},
                                                   {"word": "tree", "evidence": 'left, "tall}'}]}
    assert loads_salvaging('{"candidates":[]}') == {"candidates": []}
    import json, pytest
    with pytest.raises(json.JSONDecodeError):
        loads_salvaging('{"candidates":[{"wo')


def test_label_scores_come_from_the_shown_answer_logprobs():
    import math
    from tagging_server import boolean_scores, build_score_prompt
    prompt = build_score_prompt([{'word': 'bench', 'pos': 'noun'}, {'word': 'elephant'}])
    assert '1. bench (noun)' in prompt and '2. elephant' in prompt
    lp = [{'token': '{"checks":[{"word":"bench","shown":', 'logprob': 0},
          {'token': ' true', 'logprob': math.log(0.9),
           'top_logprobs': [{'token': ' true', 'logprob': math.log(0.9)},
                            {'token': ' false', 'logprob': math.log(0.1)}]},
          {'token': '},{"word":"elephant","shown":', 'logprob': 0},
          {'token': 'false', 'logprob': math.log(0.98), 'top_logprobs': []},
          {'token': '}]}', 'logprob': 0}]
    scores = boolean_scores(lp)
    assert [round(s, 2) for s in scores] == [0.9, 0.02]


def test_foreign_words_are_dropped_but_loanwords_stay():
    pytest = __import__('pytest')
    from tagging_server import Lexicon, to_candidates
    lex = Lexicon(cmudict_path='does-not-exist')
    if lex._zipf is None:
        pytest.skip('wordfreq not installed')
    raw = [{'word': w, 'pos': 'noun', 'point': [500, 500]} for w in
           ('calendrier', 'fenêtre', 'croissant', 'espresso', 'scrollwork', 'tortilla')]
    assert [c['word'] for c in to_candidates(raw, lex)] == ['croissant', 'espresso', 'scrollwork', 'tortilla']


def test_cefr_prompt_requires_at_least_per_level():
    prompt = ts.build_cefr_prompt("en", per_level=3)
    assert "AT LEAST 3" in prompt
    assert "Every band must meet the minimum" in prompt
    assert "return fewer for that band" not in prompt
    assert ts.CEFR_PROMPT_VERSION == "photo-tags-cefr-bands-v3"


def test_merge_cefr_topup_fills_short_bands_without_inventing():
    def item(word, cefr):
        return {"word": word, "lemma": word, "pos": "noun", "cefr": cefr,
                "modelLevel": cefr, "evidence": word, "point": [0.5, 0.5],
                "box": None, "visualConfidence": 0.7, "usefulness": 0.5,
                "inferred": False, "meaning": ""}

    existing = [
        item("cup", "A1"), item("plate", "A1"),
        item("saucer", "A2"),
    ]
    extra = [
        item("cup", "A1"),
        item("mug", "A1"),
        item("bowl", "A2"), item("fork", "A2"),
        item("teapot", "B1"),
        item("ladle", "A1"),
    ]
    out = ts.merge_cefr_topup(existing, extra, per_level=3)
    counts = ts.cefr_band_counts(out)
    assert counts["A1"] == 3
    assert counts["A2"] == 3
    assert counts["B1"] == 1
    assert "ladle" not in {x["word"] for x in out}


def test_to_candidates_keeps_model_cefr_band():
    out = ts.to_candidates([{
        "word": "chimney", "pos": "noun", "cefr": "B2",
        "evidence": "stone stack on roof", "point": [500, 400],
        "box": [400, 300, 600, 500],
    }])
    assert out[0]["cefr"] == "B2"
    assert out[0]["modelLevel"] == "B2"

