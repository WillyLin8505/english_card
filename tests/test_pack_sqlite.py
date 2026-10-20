"""Card #428: the SQLite form of a language pack (pack_sqlite.py)."""
import gzip
import json
import sqlite3
import threading
import zlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pack_sqlite
from lexicon_transport import SQLITE_TYPE, SnapshotStore, encode


def pack(version='one', meaning='蘋果'):
    return {
        'target_language': 'en', 'native_language': 'zh-TW', 'created_at': version,
        'labels': {'pos:noun': '名詞'}, 'catalog_images': [{'id': 7}],
        'lexemes': [
            {'id': 1, 'lemma': 'apple', 'normalized': 'apple', 'pos': 'noun', 'status': 'full',
             'senses': [{'id': 10, 'definition': 'fruit', 'native': meaning,
                         'images': [{'id': 7}]}],
             'forms': [{'field': 'noun_plural', 'form': 'apples', 'normalized': 'apples'}],
             'examples': [{'text': f'Sentence {i}.'} for i in range(10)],
             'relations': [{'relation': 'synonyms', 'word': f's{i}', 'detail': 'x'}
                           for i in range(12)] + [{'relation': 'hyponyms', 'word': 'h'}],
             'pronunciations': [{'kind': 'ipa', 'value': '/a/', 'default': True},
                                {'kind': 'phoneme', 'value': 'AE'},
                                {'kind': 'audio', 'audio': 'audio/en/a.mp3', 'default': True}],
             'etymology': {'text': 'Old English', 'native': '古英語'},
             'missing': {}},
            {'id': 2, 'lemma': 'tore', 'normalized': 'tore', 'pos': 'verb', 'status': 'full',
             'redirect_to': 3},
            {'id': 3, 'lemma': 'tear', 'normalized': 'tear', 'pos': 'verb', 'status': 'full',
             'senses': []},
        ],
    }


def test_build_is_lossless_and_splits_heads_from_bodies(tmp_path):
    path = pack_sqlite.build(pack(), tmp_path / 'p.sqlite')
    assert pack_sqlite.read_pack(path) == pack()
    assert pack_sqlite.read_meta(path)['created_at'] == 'one'
    con = sqlite3.connect(path)
    rows = {r[0]: r for r in con.execute('SELECT id, ord, head, senses, body FROM lexemes')}
    con.close()
    assert [rows[i][1] for i in (1, 2, 3)] == [0, 1, 2]
    head = json.loads(rows[1][2])
    assert set(head) == {'id', 'lemma', 'normalized', 'pos', 'status', 'forms'}
    assert json.loads(zlib.decompress(rows[1][3]))[0]['native'] == '蘋果'
    assert set(json.loads(zlib.decompress(rows[1][4]))) == {
        'examples', 'relations', 'pronunciations', 'etymology', 'missing'}
    assert rows[2][3] is None and rows[2][4] is None, 'a pointer row has no senses or body'
    assert json.loads(zlib.decompress(rows[3][3])) == [] and rows[3][4] is None


def test_read_meta_of_a_non_pack_is_empty(tmp_path):
    assert pack_sqlite.read_meta(tmp_path / 'missing.sqlite') == {}
    (tmp_path / 'junk.sqlite').write_text('not a database')
    assert pack_sqlite.read_meta(tmp_path / 'junk.sqlite') == {}


def test_slim_pack_keeps_what_the_app_reads():
    slim = pack_sqlite.slim_pack(pack())
    apple = slim['lexemes'][0]
    assert 'images' not in apple['senses'][0]
    assert len(apple['examples']) == pack_sqlite.SLIM_EXAMPLES
    assert len(apple['relations']) == pack_sqlite.SLIM_RELATIONS
    assert all('detail' not in r and r['relation'] == 'synonyms' for r in apple['relations'])
    assert [p['kind'] for p in apple['pronunciations']] == ['ipa', 'audio']
    assert slim['lexemes'][1] == pack()['lexemes'][1], 'pointer rows are untouched'
    assert slim['labels'] == pack()['labels']
    # The bundle keeps only clips it ships; the server keeps every clip.
    none = pack_sqlite.slim_pack(pack(), bundled_audio=set())
    assert [p['kind'] for p in none['lexemes'][0]['pronunciations']] == ['ipa']


def test_snapshot_serves_sqlite_and_slim_delta(tmp_path):
    store = SnapshotStore(lambda *a: (encode(pack()), 'one'), tmp_path)
    first = store.get('en', 'zh-TW')
    body, ctype, gz = first.respond(None, True, 'sqlite')
    assert ctype == SQLITE_TYPE and not gz
    assert body[:15] == b'SQLite format 3'
    sqlite_file = tmp_path / (first.sqlite_path.name)
    assert sqlite_file.is_file() and sqlite_file.read_bytes() == body
    assert pack_sqlite.read_pack(sqlite_file) == pack_sqlite.slim_pack(pack())

    # A restart reuses the file instead of rebuilding it.
    restarted = SnapshotStore(lambda *a: (encode(pack()), 'one'), tmp_path)
    again = restarted.get('en', 'zh-TW')
    assert again.respond(None, False, 'sqlite')[0] == body

    # The next version: a phone on 'one' gets a slim delta, others the file.
    store.builder = lambda *a: (encode(pack('two', '蘋果二')), 'two')
    store._refresh(('en', 'zh-TW'), first)
    latest = store.entries[('en', 'zh-TW')]
    patch, ctype, gz = latest.respond('one', True, 'sqlite')
    assert ctype.startswith('application/json') and gz
    patch = json.loads(gzip.decompress(patch))
    assert patch['base_version'] == 'one' and patch['order'] == [1, 2, 3]
    assert [r['id'] for r in patch['upserts']] == [1]
    assert len(patch['upserts'][0]['examples']) == pack_sqlite.SLIM_EXAMPLES, 'slim rows'
    full, ctype, _ = latest.respond('stale', True, 'sqlite')
    assert ctype == SQLITE_TYPE and pack_sqlite.read_meta(latest.sqlite_path)['created_at'] == 'two'
    # JSON callers are unchanged.
    assert json.loads(latest.respond(None, False)[0]) == pack('two', '蘋果二')


def test_http_format_sqlite(monkeypatch, tmp_path):
    import serve_app
    store = SnapshotStore(lambda *a: (encode(pack()), 'one'), tmp_path)
    monkeypatch.setattr(serve_app, '_http_snapshots', store)
    server = ThreadingHTTPServer(('127.0.0.1', 0), serve_app.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(path, headers=None):
        conn = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        conn.request('GET', path, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result
    try:
        status, headers, body = request('/api/lexicon?format=sqlite', {'Accept-Encoding': 'gzip'})
        assert status == 200
        assert headers['Content-Type'] == SQLITE_TYPE
        assert 'Content-Encoding' not in headers
        assert headers['ETag'] == 'W/"one"'
        assert body[:15] == b'SQLite format 3' and int(headers['Content-Length']) == len(body)
        assert request('/api/lexicon?format=sqlite', {'If-None-Match': 'W/"one"'})[0] == 304
        status, headers, raw = request('/api/lexicon')
        assert headers['Content-Type'].startswith('application/json') and json.loads(raw) == pack()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
