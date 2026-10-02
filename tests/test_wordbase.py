"""Tests for the word database app (wordbase/) — no network: sources are stubbed."""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wordbase'))
import model  # noqa: E402
import server  # noqa: E402
import sources  # noqa: E402
from store import DeleteBlocked, Store, duplicate_key, normalize  # noqa: E402

# What each (stubbed) source says about "mug".
STUB = {
    'kaikki': ({
        'pos': ['noun', 'verb'],
        'senses': [{'pos': 'noun', 'gloss': 'A large cup with a handle.'},
                   {'pos': 'verb', 'gloss': 'To rob in the street.'}],
        'meaning_zh': [{'trad': '馬克杯', 'simp': '马克杯', 'pos': 'noun', 'sense': 'cup'}],
        'ipa': [{'ipa': '/mʌɡ/', 'accent': ['UK']}, {'ipa': '/mʌɡ/', 'accent': ['US']}],
        'audio': [{'url': 'https://example.org/uk.mp3', 'accent': ['UK']},
                  {'url': 'https://example.org/us.mp3', 'accent': ['General-American']}],
        'synonyms': ['tankard'],
        'forms': [{'form': 'mugs', 'tags': ['plural'], 'pos': 'noun'}],
        'examples': [{'text': 'A mug of cocoa.'}, {'text': 'I like this mug.'}],
    }, {'status': 'ok', 'counts': {'usage_examples': 2, 'quotations': 5}}),
    'oewn': ({
        'pos': ['noun'],
        'senses': [{'pos': 'noun', 'gloss': 'with handle and usually cylindrical'}],
        'synonyms': ['tankard', 'stein'],
        'examples': [{'text': 'I like this mug.'}],
    }, {'status': 'ok'}),
    'cmudict': ({'ipa': [{'ipa': '/mʌɡ/', 'accent': ['US']}], 'phonemes': ['M AH1 G']},
                {'status': 'ok'}),
    'datamuse': ({'synonyms': ['cup', 'stein'], 'means_like': ['beaker'],
                  'similar_spelling': ['mag']}, {'status': 'ok'}),
    'tatoeba': ({'examples': [
        {'text': 'This mug is mine.', 'translation': '這個馬克杯是我的。', 'script': 'Hant'},
        {'text': 'I like this mug.', 'translation': '我喜欢这个杯子。', 'script': 'Hans',
         'translation_tw': '我喜歡這個杯子。'},
    ]}, {'status': 'ok', 'counts': {'sentences': 40, 'with_mandarin': 12}}),
    'wordlist': ({}, {'status': 'error', 'error': 'boom'}),
}


def fetchers_for(stub):
    """Stub sources that know "mug" and nothing else."""
    nothing = ({}, {'status': 'not_found'})
    return {name: (lambda w, refresh=False, name=name: stub[name] if w in ('mug', 'mugs') else nothing)
            for name in stub}


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / 'wb.sqlite')


def add_mug(store):
    (mug,), _ = store.add_words(['  Mug '], ['廚房'])
    server.Fetcher(store, fetchers_for(STUB)).fetch_one(mug)
    return mug


def test_merge_follows_spec_priority_and_keeps_sources(store):
    mug = add_mug(store)
    e = store.get(mug)
    f = e['view']['fields']
    # 近義字: ① WordNet, then ② Kaikki fills, ③ Datamuse extends; no duplicates.
    syn = [(i['value'], i['source'], i['rank']) for i in f['synonyms']['items']]
    assert syn == [('tankard', 'oewn', 1), ('stein', 'oewn', 1), ('cup', 'datamuse', 3),
                   ('beaker', 'datamuse', 3)]
    assert [(s['source'], s['rank']) for s in f['synonyms']['sources']] == [
        ('oewn', 1), ('kaikki', 2), ('datamuse', 3), ('datamuse', 3)]
    # 英文例句: ① Tatoeba first; the Kaikki and WordNet copies of a sentence merge.
    ex = [(i['value']['text'], i['source']) for i in f['examples']['items']]
    assert ex == [('This mug is mine.', 'tatoeba'), ('I like this mug.', 'tatoeba'),
                  ('A mug of cocoa.', 'kaikki')]
    # Licence and source travel with every field (來源追蹤).
    assert f['ipa']['sources'][0]['license'] == 'CC BY-SA 4.0／GFDL'
    assert f['morphology']['items'] == []
    assert e['fetch_status'] == 'partial' and '本機字表比對' in e['fetch_error']
    assert e['word'] == 'mug' and e['tags'] == ['廚房']


def test_summary_flags_and_duplicates(store):
    mug = add_mug(store)
    s = store.get(mug)['summary']
    assert s['zh'] == '馬克杯' and s['ipa'] == '/mʌɡ/' and s['pos'] == ['noun', 'verb']
    assert s['has']['examples_zh'] and not s['has']['examples5'] and s['has']['audio']
    created, dupes = store.add_words(['MUG', 'mugs'])
    assert dupes == ['mug'] and len(created) == 1
    assert normalize('  Pine   Nuts ') == 'pine nuts'
    assert duplicate_key('pine nuts') == duplicate_key('pine nut')
    assert duplicate_key('well-being') == duplicate_key('wellbeing')


def test_edit_keeps_original_verify_and_revert(store):
    mug = add_mug(store)
    store.set_override(mug, 'meaning_zh', [{'trad': '杯子', 'simp': '杯子', 'pos': 'noun'}])
    f = store.get(mug)['view']['fields']['meaning_zh']
    assert f['trust'] == 'user' and f['items'][0]['value']['trad'] == '杯子'
    assert f['original'][0]['value']['trad'] == '馬克杯'
    # A re-fetch never overwrites the learner's value.
    server.Fetcher(store, fetchers_for(STUB)).fetch_one(mug)
    assert store.get(mug)['view']['fields']['meaning_zh']['items'][0]['value']['trad'] == '杯子'
    store.set_verified(mug, 'ipa', True)
    assert store.get(mug)['view']['fields']['ipa']['verified_at']
    store.clear_override(mug, 'meaning_zh')
    assert store.get(mug)['view']['fields']['meaning_zh']['items'][0]['value']['trad'] == '馬克杯'


def test_primary_sense_and_default_accent(store):
    mug = add_mug(store)
    verb = model.sense_key({'pos': 'verb', 'gloss': 'To rob in the street.'})
    store.update(mug, primary_sense=verb, default_accent='US')
    f = store.get(mug)['view']['fields']
    assert f['senses']['items'][0]['value']['pos'] == 'verb' and f['senses']['items'][0]['primary']
    assert f['audio']['items'][0]['value']['url'].endswith('us.mp3')
    assert store.get(mug)['summary']['gloss'] == 'To rob in the street.'


def test_delete_blocked_when_referenced_and_merge(store):
    mug = add_mug(store)
    store.update(mug, photo_refs=2)
    with pytest.raises(DeleteBlocked) as e:
        store.delete(mug)
    assert (e.value.photos, e.value.cards) == (2, 0)
    (mugs,), _ = store.add_words(['mugs'], ['複數'])
    store.set_override(mugs, 'etymology', ['from mug'])
    store.merge(mug, mugs)
    merged = store.get(mug)
    assert store.get(mugs) is None
    assert merged['tags'] == ['廚房', '複數']
    assert merged['view']['fields']['etymology']['items'][0]['value'] == 'from mug'
    assert merged['photo_refs'] == 2
    store.update(mug, photo_refs=0)
    store.delete(mug)
    assert store.get(mug) is None


def test_tatoeba_prefers_traditional_and_converts(monkeypatch):
    reply_plain = {'data': [{'id': 1, 'text': 'No translation here.'}], 'paging': {'total': 30}}
    reply_zh = {'data': [
        {'id': 2, 'text': 'I use a mouse.', 'translations': [
            {'lang': 'cmn', 'script': 'Hans', 'text': '我用鼠标。'}]},
        {'id': 3, 'text': 'A mug.', 'translations': [
            {'lang': 'cmn', 'script': 'Hant', 'text': '一個馬克杯。'}]},
    ], 'paging': {'total': 2}}
    calls = []

    def fake_fetch(source, word, url, refresh=False, lines=False):
        calls.append(url)
        return (reply_zh if 'trans%3Alang' in url else reply_plain), 200, None

    monkeypatch.setattr(sources, 'fetch', fake_fetch)
    data, meta = sources.tatoeba('mouse')
    assert '%3Dmouse' in calls[0], 'single words are matched exactly'
    texts = [e['text'] for e in data['examples']]
    assert texts == ['A mug.', 'I use a mouse.', 'No translation here.']
    converted = data['examples'][1]
    assert converted['script'] == 'Hans'
    if converted.get('translation_tw'):  # OpenCC installed
        assert converted['translation_tw'] == '我用滑鼠。'
    assert meta['counts']['sentences'] == 30 and meta['counts']['Hant'] == 1
    sources.tatoeba('pine nuts')
    assert '%22pine+nuts%22' in calls[-1], 'phrases are matched as phrases'


def test_local_sources():
    data, meta = sources.cmudict('apple')
    assert data['ipa'][0]['ipa'] == '/ˈæpəl/' and meta['status'] == 'ok'
    assert sources.cmudict('zzqx')[1]['status'] == 'not_found'
    data, _ = sources.wordlist('mug')
    assert 'mud' in data['similar_spelling'] and 'mugs' not in data['similar_spelling']
    assert sources.wordlist('pine nuts')[1]['status'] == 'not_found'
    assert sources.extras('apple')['cefr'] == 'A1'


@pytest.fixture()
def http(store):
    fetcher = server.Fetcher(store, fetchers_for(STUB))
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(store, fetcher))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'

    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call, fetcher
    httpd.shutdown()


def test_api_add_fetch_filter_edit_delete(http):
    call, fetcher = http
    status, res = call('POST', '/api/entries', {'words': 'mug\npine nuts, mug', 'tags': ['測試']})
    assert status == 200 and len(res['created']) == 2 and res['duplicates'] == ['mug']
    for i in res['created']:
        fetcher.fetch_one(i)
    _, listed = call('GET', '/api/entries?q=%E9%A6%AC%E5%85%8B')  # 馬克
    assert [r['word'] for r in listed['entries']] == ['mug']
    _, listed = call('GET', '/api/entries?missing=examples5')
    assert {r['word'] for r in listed['entries']} == {'mug', 'pine nuts'}
    _, listed = call('GET', '/api/entries?source=tatoeba&tag=%E6%B8%AC%E8%A9%A6')
    assert [r['word'] for r in listed['entries']] == ['mug']
    mug = res['created'][0]
    status, entry = call('PUT', f'/api/entries/{mug}/fields/synonyms', {'value': ['beaker']})
    assert status == 200 and entry['view']['fields']['synonyms']['trust'] == 'user'
    assert call('PUT', f'/api/entries/{mug}/fields/nope', {'value': []})[0] == 400
    _, cov = call('GET', '/api/coverage')
    syn = next(f for f in cov['fields'] if f['key'] == 'synonyms')
    assert cov['total'] == 2 and syn['cells'][0] == {'source': 'oewn', 'rank': 1, 'found': 1}
    assert syn['any'] == 1
    call('PATCH', f'/api/entries/{mug}', {'card_refs': 1})
    status, err = call('DELETE', f'/api/entries/{mug}')
    assert status == 409 and err['cards'] == 1
    _, res = call('POST', '/api/batch', {'ids': [mug], 'action': 'archive'})
    _, listed = call('GET', '/api/entries')
    assert [r['word'] for r in listed['entries']] == ['pine nuts']
    _, meta = call('GET', '/api/meta')
    assert '測試' in meta['tags'] and meta['sources']['tatoeba']['name'] == 'Tatoeba'


def test_wordnet_from_several_threads():
    """wn's SQLite handle can't cross threads; each fetch thread gets its own."""
    out = []
    threads = [threading.Thread(target=lambda: out.append(sources.oewn('apple')[1]['status']))
               for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert out == ['ok', 'ok', 'ok']
