import gzip
import json
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from lexicon_transport import SnapshotStore, accepts_gzip, delta, encode, matches_etag


def pack(version='one'):
    return {'target_language': 'en', 'native_language': 'zh-TW',
            'created_at': version, 'catalog_images': [],
            'lexemes': [{'id': i, 'text': str(i) * 100} for i in range(100)]}


def test_delta_losslessly_reconstructs_add_edit_delete_reorder_and_metadata():
    before = pack()
    after = pack('two')
    after['lexemes'] = after['lexemes'][1:][::-1] + [{'id': 999, 'text': 'new'}]
    after['lexemes'][0]['text'] = 'edit'
    after['catalog_images'] = [{'id': 2}]
    patch = delta(before, after)
    rows = {r['id']: r for r in before['lexemes']}
    rows.update({r['id']: r for r in patch['upserts']})
    assert {**patch['metadata'], 'lexemes': [rows[i] for i in patch['order']]} == after
    assert len(patch['upserts']) == 2


def test_durable_snapshot_does_not_block_on_refresh_and_failure_retries(tmp_path):
    before = pack()
    store = SnapshotStore(lambda *a: (encode(before), 'one'), tmp_path)
    first = store.get('en', 'zh-TW')
    entered, release = threading.Event(), threading.Event()
    calls = []

    def slow(*a):
        calls.append(a)
        entered.set()
        assert release.wait(3)
        return encode(pack('two')), 'two'

    restarted = SnapshotStore(slow, tmp_path)
    try:
        assert restarted.get('en', 'zh-TW').body == first.body
        assert entered.wait(1)
        for _ in range(5):
            assert restarted.get('en', 'zh-TW').body == first.body
        assert len(calls) == 1
    finally:
        release.set()
    for _ in range(100):
        if not restarted.refreshing:
            break
        time.sleep(.01)
    latest = restarted.get('en', 'zh-TW')
    assert latest.version == 'two'
    assert json.loads(latest.representation('one', False))['delta_version'] == 1
    assert latest.representation('unknown', False) == latest.body
    assert gzip.decompress(latest.representation('one', True)) == latest.delta_body

    def broken(*a):
        raise RuntimeError('test failure')
    restarted.builder = broken
    restarted.checked[('en', 'zh-TW')] = 0
    restarted.get('en', 'zh-TW')
    for _ in range(100):
        if not restarted.refreshing:
            break
        time.sleep(.01)
    assert restarted.get('en', 'zh-TW') is latest
    assert not restarted.refreshing


def test_http_gzip_validators_cors_and_incremental_fallback(monkeypatch, tmp_path):
    import serve_app
    store = SnapshotStore(lambda *a: (encode(pack()), 'one'), tmp_path)
    monkeypatch.setattr(serve_app, '_http_snapshots', store)
    server = ThreadingHTTPServer(('127.0.0.1', 0), serve_app.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def request(headers, path='/api/lexicon'):
        conn = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        conn.request('GET', path, headers=headers)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result
    try:
        status, headers, compressed = request({'Accept-Encoding': 'gzip',
                                               'Origin': 'http://localhost:9999'})
        assert status == 200
        assert headers['Content-Encoding'] == 'gzip'
        assert headers['Access-Control-Expose-Headers'] == 'ETag'
        assert json.loads(gzip.decompress(compressed)) == pack()
        assert headers['ETag'] == 'W/"one"'
        assert request({'If-None-Match': '"other", "one"'})[::2] == (304, b'')
        assert request({'If-None-Match': '*'})[0] == 304
        status, headers, raw = request({'Accept-Encoding': 'gzip;q=0'})
        assert 'Content-Encoding' not in headers
        assert json.loads(raw) == pack()
        assert request({}, '/api/lexicon?target=../bad')[0] == 400
        store.builder = lambda *a: (encode(pack('two')), 'two')
        store._refresh(('en', 'zh-TW'), store.entries[('en', 'zh-TW')])
        assert json.loads(request({}, '/api/lexicon?since=one')[2])['delta_version'] == 1
        assert json.loads(request({}, '/api/lexicon?since=expired')[2]) == pack('two')
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_encoding_and_validator_negotiation():
    assert accepts_gzip('br, gzip;q=0.5')
    assert not accepts_gzip('gzip;q=0, *;q=1')
    assert not accepts_gzip('xgzip')
    assert matches_etag('"old", W/"new"', '"new"')
    assert not matches_etag('"old"', 'W/"new"')


def test_corrupt_persisted_snapshot_is_rebuilt(tmp_path):
    store = SnapshotStore(lambda *a: (encode(pack()), 'one'), tmp_path)
    store._path(('en', 'zh-TW')).write_bytes(b'incomplete gzip')
    assert store.get('en', 'zh-TW').version == 'one'


def test_exporter_language_mismatch_is_never_persisted(tmp_path):
    import pytest
    wrong = {**pack(), 'native_language': 'a translated sense'}
    store = SnapshotStore(lambda *a: (encode(wrong), 'one'), tmp_path)
    with pytest.raises(ValueError, match='language pair'):
        store.get('en', 'zh-TW')
    assert not list(tmp_path.iterdir())
