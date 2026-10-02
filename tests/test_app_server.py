import importlib.util
import json
import threading
import io
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location('local_app_server', Path(__file__).resolve().parents[1] / 'serve_app.py')
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


def test_http_versioning_and_local_access_guards(monkeypatch):
    calls = []
    def pack(target, native):
        calls.append((target, native))
        return json.dumps({'target_language': target}).encode(), '"version1"'
    monkeypatch.setattr(server_module, 'live_pack', pack)
    server = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def request(path='/api/lexicon?target=en&native=zh-TW', headers=None):
            conn = HTTPConnection('127.0.0.1', server.server_port)
            conn.request('GET', path, headers=headers or {})
            result = conn.getresponse()
            status, data = result.status, result.read()
            conn.close()
            return status, data
        assert request()[0] == 200
        assert calls[-1] == ('en', 'zh-TW')
        assert request(headers={'If-None-Match': '"version1"'}) == (304, b'')
        count = len(calls)
        assert request(headers={'Origin': 'https://unrelated.example'})[0] == 403
        assert request(headers={'Host': 'unrelated.example'})[0] == 403
        assert len(calls) == count
        assert request('/api/audio?path=../../.env')[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_tagger_proxy_keeps_key_on_server_and_rejects_foreign_requests(monkeypatch):
    calls = []
    monkeypatch.setenv('TAGGER_API_KEY', 'server-only-test-key')
    class Reply(io.BytesIO):
        code = 200
    def upstream(request, timeout):
        calls.append(request)
        return Reply(b'{"ok":true,"keyOk":true}')
    monkeypatch.setattr(server_module, 'urlopen', upstream)
    server = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def request(method, path, body=None, headers=None):
            conn = HTTPConnection('127.0.0.1', server.server_port)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            result = response.status, response.read()
            conn.close()
            return result
        status, data = request('GET', '/health')
        assert status == 200 and b'server-only-test-key' not in data
        assert request('POST', '/tag?level=A1', b'photo', {'Content-Type': 'image/jpeg'})[0] == 200
        assert calls[-1].data == b'photo'
        assert calls[-1].get_header('X-api-key') == 'server-only-test-key'
        count = len(calls)
        assert request('POST', '/tag', b'photo', {'Origin': 'https://other.example'})[0] == 403
        assert request('POST', '/translate', b'photo')[0] == 404
        assert request('POST', '/tag', headers={'Content-Length': '20971521'})[0] == 413
        assert len(calls) == count
        def offline(*args, **kwargs):
            raise OSError('offline')
        monkeypatch.setattr(server_module, 'urlopen', offline)
        assert request('GET', '/health')[0] == 502
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_missing_words_are_saved_for_the_admin(monkeypatch):
    """Spec section 7: words the pack lacks become 缺詞條 the admin can fill.
    Runs against the lexicon_test database."""
    import pytest
    from sqlalchemy import text
    from app import config, db
    try:
        db.use_engine(config.database_url(test=True))
        with db.engine.connect() as c:
            c.execute(text('SELECT 1 FROM missing_lexeme_requests LIMIT 1'))
    except Exception:  # noqa: BLE001
        pytest.skip('lexicon_test is not reachable or not migrated')
    with db.engine.begin() as c:
        c.execute(text("DELETE FROM missing_lexeme_requests WHERE lemma LIKE 'zzsim%'"))
    server = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def post(body, headers=None):
            conn = HTTPConnection('127.0.0.1', server.server_port)
            conn.request('POST', '/api/missing', body=json.dumps(body).encode(),
                         headers={'Content-Type': 'application/json', **(headers or {})})
            r = conn.getresponse()
            out = r.status, r.read()
            conn.close()
            return out
        reqs = {'requests': [{'kind': 'missing_lexeme', 'lemma': 'ZzSimWord', 'pos': 'noun', 'target': 'en'},
                             {'kind': 'missing_lexeme', 'lemma': 'zzsimword', 'pos': 'noun', 'target': 'en'},
                             {'kind': 'missing_lexeme', 'lemma': '', 'target': 'en'},
                             {'kind': 'other'}]}
        status, data = post(reqs)
        assert status == 200 and json.loads(data)['saved'] == 2
        assert post(reqs, {'Origin': 'https://unrelated.example'})[0] == 403
        assert post({'requests': 'nope'})[0] == 400
        with db.engine.connect() as c:
            rows = c.execute(text("SELECT lemma, pos FROM missing_lexeme_requests WHERE lemma LIKE 'zzsim%'")).all()
        assert [tuple(r) for r in rows] == [('zzsimword', 'noun')]
    finally:
        server.shutdown()
        with db.engine.begin() as c:
            c.execute(text("DELETE FROM missing_lexeme_requests WHERE lemma LIKE 'zzsim%'"))


def test_a_word_without_data_in_this_direction_is_a_stub():
    exported = {1: {'id': 1, 'status': 'full', 'senses': [{'native': '蘋果'}]}}
    meta = [{'id': 1, 'lemma': 'apple', 'status': 'full'}, {'id': 2, 'lemma': 'tea', 'status': 'full'}]
    out = {w['id']: w for w in server_module.merge_catalog(exported, meta)}
    assert out[1]['status'] == 'full' and out[1]['senses']
    assert out[2]['status'] == 'stub' and 'senses' not in out[2]
