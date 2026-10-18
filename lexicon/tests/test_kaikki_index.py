import json
import sqlite3

from app import kaikki_index


def test_spelling_candidates_cover_every_edit_and_unicode(tmp_path):
    path = tmp_path / 'words.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);'
                          'CREATE TABLE entries(language TEXT,normalized TEXT,payload TEXT);'
                          'CREATE INDEX lookup ON entries(language,normalized);')
        conn.execute("INSERT INTO metadata VALUES ('complete:en','1')")
        words = ['apple', 'aple', 'appple', 'apqle', 'appel', 'ápple',
                 'apple', 'apple pie', 'axxxe', 'banana']
        conn.executemany("INSERT INTO entries VALUES ('en',?,'{}')", [(w,) for w in words])
        conn.execute("INSERT INTO entries VALUES ('fr','apzle','{}')")
    assert set(kaikki_index.spelling_candidates('en', 'APPLE', path)) == {
        'aple', 'appple', 'apqle', 'appel', 'ápple'}
    assert kaikki_index.spelling_candidates('en', 'zzzzzz', path) == []
    assert kaikki_index.spelling_candidates('fr', 'apple', path) is None
    assert kaikki_index.spelling_candidates('en', 'apple pie', path) == []
    info = kaikki_index.wordlist_snapshot('en', path)
    assert info['details'] == {'wordlist': 'kaikki_index', 'complete': True}
    assert info['row_count'] == 9  # distinct headwords, not duplicate POS entries
    assert kaikki_index.wordlist_snapshot('fr', path) is None


def test_adapter_prefers_index_and_does_not_fallback_on_empty_result(monkeypatch):
    from app.adapters import Context
    from app.adapters import local
    def no_fallback(language):
        raise AssertionError('complete index must not use reduced word list')
    monkeypatch.setattr(local, '_wordlist', no_fallback)
    monkeypatch.setattr(kaikki_index, 'spelling_candidates', lambda *args: ['apply'])
    result = local.KaikkiWordlist().normalize('similar_spelling', None,
                                            Context('en', 'zh-TW', 'apple'))
    assert result and result[0].value['wordlist'] == 'kaikki_index'
    monkeypatch.setattr(kaikki_index, 'spelling_candidates', lambda *args: [])
    assert local.KaikkiWordlist().normalize('similar_spelling', None,
                                          Context('en', 'zh-TW', 'apple')) == []


def test_missing_index_keeps_explicit_fallback(monkeypatch):
    from app.adapters import Context, local
    monkeypatch.setattr(kaikki_index, 'spelling_candidates', lambda *args: None)
    monkeypatch.setattr(kaikki_index, 'wordlist_snapshot', lambda *args: None)
    monkeypatch.setattr(local, '_wordlist', lambda lang: ('apple', 'apply'))
    result = local.KaikkiWordlist().normalize('similar_spelling', None,
                                            Context('en', 'zh-TW', 'apple'))
    assert result[0].value['wordlist'] == 'wordfreq_cefr_fallback'
    assert local.KaikkiWordlist().download_snapshot('en', '')['row_count'] == 2


def test_local_kaikki_index_requires_complete_marker(tmp_path):
    path = tmp_path / "kaikki.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript("""
      CREATE TABLE entries (id INTEGER PRIMARY KEY, language TEXT, normalized TEXT, payload TEXT);
      CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    entry = {"word": "Bench", "lang_code": "en", "pos": "noun", "senses": []}
    conn.execute("INSERT INTO entries(language, normalized, payload) VALUES ('en', 'bench', ?)",
                 (json.dumps(entry),))
    conn.commit()
    conn.close()
    assert kaikki_index.lookup("en", "bench", path) is None
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO metadata VALUES ('complete:en', '1')")
    conn.commit()
    conn.close()
    # Clear the thread-local connection opened before the completion marker.
    kaikki_index._local.kaikki[1].close()
    del kaikki_index._local.kaikki
    assert kaikki_index.lookup("en", "BENCH", path) == [entry]
    assert kaikki_index.lookup("en", "missing", path) == []
