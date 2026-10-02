import json
import sqlite3

from app import kaikki_index


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
