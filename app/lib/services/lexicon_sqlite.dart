import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:sqlite3/sqlite3.dart';

/// The language pack as a SQLite file (card #428, 問題回報 #423, owner
/// decision B). Mirrors `pack_sqlite.py` in the project root:
///
/// * `meta(key, value)` — zlib(JSON) of every top-level pack key except
///   `lexemes`, plus `format_version`.
/// * `lexemes(id, ord, head, senses, body)` — `head` is the JSON of the row
///   without `senses` and [bodyKeys] (what the app indexes at launch, ~4 MB
///   for 10k words); `senses` and `body` are zlib(JSON) read per word.
///
/// Parsing the whole pack JSON into Dart objects cost 636 MB on Windows and
/// killed the app on an iPhone (#419); this keeps the heads only.
class LexiconSqlite {
  LexiconSqlite._(this._db, this.path)
      : _senses = _db.prepare('SELECT senses FROM lexemes WHERE id = ?'),
        _body = _db.prepare('SELECT body FROM lexemes WHERE id = ?');

  static const formatVersion = 1;

  /// False on the web (see lexicon_sqlite_stub.dart).
  static const supported = true;

  /// Row fields fetched per word, never kept in the index.
  static const bodyKeys = {
    'examples',
    'relations',
    'morphemes',
    'etymology',
    'pronunciations',
    'missing',
  };

  final Database _db;
  final String path;
  final PreparedStatement _senses;
  final PreparedStatement _body;
  bool _closed = false;

  bool get closed => _closed;

  /// Opens a pack file; throws [FormatException] when it is not one.
  static LexiconSqlite open(String path, {bool readOnly = false}) {
    final db = sqlite3.open(path,
        mode: readOnly ? OpenMode.readOnly : OpenMode.readWrite);
    try {
      final version =
          db.select("SELECT value FROM meta WHERE key = 'format_version'");
      if (version.isEmpty ||
          _decode(version.first['value'] as Uint8List) != formatVersion) {
        throw const FormatException('Not a lexicon pack (format_version)');
      }
    } on SqliteException catch (e) {
      db.close();
      throw FormatException('Not a lexicon pack: ${e.message}');
    } catch (_) {
      db.close();
      rethrow;
    }
    return LexiconSqlite._(db, path);
  }

  /// `target_language`, `native_language`, `created_at` of a pack file, or
  /// null when the file is missing or not a pack. Cheap: three meta rows.
  static ({String? target, String? native, String? version})? inspect(
      String path) {
    if (!File(path).existsSync()) return null;
    try {
      final pack = open(path, readOnly: true);
      try {
        final m = pack.meta(keys: const {
          'target_language',
          'native_language',
          'created_at',
        });
        return (
          target: m['target_language'] as String?,
          native: m['native_language'] as String?,
          version: m['created_at'] as String?,
        );
      } finally {
        pack.close();
      }
    } catch (_) {
      return null;
    }
  }

  /// Every top-level pack key (no `lexemes`, no `format_version`).
  Map<String, dynamic> meta({Set<String>? keys}) {
    final out = <String, dynamic>{};
    for (final row in _db.select('SELECT key, value FROM meta')) {
      final key = row['key'] as String;
      if (key == 'format_version') continue;
      if (keys != null && !keys.contains(key)) continue;
      out[key] = _decode(row['value'] as Uint8List);
    }
    return out;
  }

  /// The heads of every row in pack order (the launch-time index).
  Iterable<Map<String, dynamic>> heads() sync* {
    final statement = _db.prepare('SELECT head FROM lexemes ORDER BY ord');
    try {
      final cursor = statement.selectCursor();
      while (cursor.moveNext()) {
        yield jsonDecode(cursor.current['head'] as String)
            as Map<String, dynamic>;
      }
    } finally {
      statement.close();
    }
  }

  int get rowCount =>
      _db.select('SELECT count(*) AS n FROM lexemes').first['n'] as int;

  /// The word's senses (JSON list) or null for a word without them.
  List<dynamic>? senses(int id) {
    if (_closed) return null;
    final rows = _senses.select([id]);
    if (rows.isEmpty) return null;
    final blob = rows.first['senses'] as Uint8List?;
    return blob == null ? null : _decode(blob) as List<dynamic>;
  }

  /// The word's examples, relations, morphemes, etymology, pronunciations,
  /// missing (whichever the row has) or null.
  Map<String, dynamic>? body(int id) {
    if (_closed) return null;
    final rows = _body.select([id]);
    if (rows.isEmpty) return null;
    final blob = rows.first['body'] as Uint8List?;
    return blob == null ? null : _decode(blob) as Map<String, dynamic>;
  }

  /// Applies a dictionary delta (lexicon_transport.delta): upserted rows,
  /// the new order (which also deletes), new metadata. Throws
  /// [FormatException] on a patch for another version; the file is then
  /// unchanged (one transaction).
  void applyDelta(Map<String, dynamic> patch) {
    final base = meta(keys: const {'created_at'})['created_at'];
    if (patch['delta_version'] != 1 ||
        patch['base_version'] != base ||
        patch['metadata'] is! Map ||
        patch['order'] is! List ||
        patch['upserts'] is! List) {
      throw const FormatException('Invalid dictionary delta');
    }
    final order = (patch['order'] as List).cast<int>();
    if (order.toSet().length != order.length) {
      throw const FormatException('Incomplete dictionary delta');
    }
    _db.execute('BEGIN');
    try {
      final upsert = _db.prepare(
          'INSERT OR REPLACE INTO lexemes (id, ord, head, senses, body) '
          'VALUES (?, -1, ?, ?, ?)');
      try {
        for (final row
            in (patch['upserts'] as List).cast<Map<String, dynamic>>()) {
          final (head, senses, body) = splitRow(row);
          upsert.execute([(row['id'] as num).toInt(), head, senses, body]);
        }
      } finally {
        upsert.close();
      }
      _db.execute(
          'CREATE TEMP TABLE keep (id INTEGER PRIMARY KEY, ord INTEGER)');
      final keep = _db.prepare('INSERT INTO keep VALUES (?, ?)');
      try {
        for (var i = 0; i < order.length; i++) {
          keep.execute([order[i], i]);
        }
      } finally {
        keep.close();
      }
      final missing = _db.select(
          'SELECT count(*) AS n FROM keep WHERE id NOT IN (SELECT id FROM lexemes)');
      if ((missing.first['n'] as int) != 0) {
        throw const FormatException('Incomplete dictionary delta');
      }
      _db.execute('DELETE FROM lexemes WHERE id NOT IN (SELECT id FROM keep)');
      _db.execute('UPDATE lexemes SET ord = '
          '(SELECT ord FROM keep WHERE keep.id = lexemes.id)');
      _db.execute('DROP TABLE keep');
      _db.execute('DELETE FROM meta');
      final put = _db.prepare('INSERT INTO meta VALUES (?, ?)');
      try {
        final metadata = Map<String, dynamic>.from(patch['metadata'] as Map);
        metadata['format_version'] = formatVersion;
        for (final e in metadata.entries) {
          put.execute([e.key, _encode(e.value)]);
        }
      } finally {
        put.close();
      }
      _db.execute('COMMIT');
    } catch (_) {
      _db.execute('ROLLBACK');
      rethrow;
    }
  }

  void close() {
    if (_closed) return;
    _closed = true;
    _senses.close();
    _body.close();
    _db.close();
  }

  /// Writes [pack] (the JSON form) as a pack file — tests and tooling; the
  /// server and the bundle use `pack_sqlite.py`.
  static void build(Map<String, dynamic> pack, String path) {
    final file = File(path);
    if (file.existsSync()) file.deleteSync();
    file.parent.createSync(recursive: true);
    final db = sqlite3.open(path);
    try {
      db.execute('PRAGMA journal_mode=OFF');
      db.execute(
          'CREATE TABLE meta(key TEXT PRIMARY KEY, value BLOB NOT NULL)');
      db.execute('CREATE TABLE lexemes(id INTEGER PRIMARY KEY, '
          'ord INTEGER NOT NULL, head TEXT NOT NULL, senses BLOB, body BLOB)');
      db.execute('BEGIN');
      final put = db.prepare('INSERT INTO meta VALUES (?, ?)');
      for (final e in pack.entries) {
        if (e.key == 'lexemes') continue;
        put.execute([e.key, _encode(e.value)]);
      }
      put.execute(['format_version', _encode(formatVersion)]);
      put.close();
      final insert = db.prepare(
          'INSERT OR REPLACE INTO lexemes (id, ord, head, senses, body) '
          'VALUES (?, ?, ?, ?, ?)');
      var ord = 0;
      for (final row in (pack['lexemes'] as List? ?? const [])
          .cast<Map<String, dynamic>>()) {
        final (head, senses, body) = splitRow(row);
        insert.execute([(row['id'] as num).toInt(), ord++, head, senses, body]);
      }
      insert.close();
      db.execute('CREATE INDEX lexemes_ord ON lexemes(ord)');
      db.execute('COMMIT');
    } finally {
      db.close();
    }
  }

  /// A pack row as the three stored columns: head JSON, senses and body
  /// blobs (null when the row has none).
  static (String, Uint8List?, Uint8List?) splitRow(Map<String, dynamic> row) {
    final head = <String, dynamic>{
      for (final e in row.entries)
        if (e.key != 'senses' && !bodyKeys.contains(e.key)) e.key: e.value
    };
    final body = <String, dynamic>{
      for (final k in bodyKeys)
        if (row.containsKey(k)) k: row[k]
    };
    return (
      jsonEncode(head),
      row['senses'] == null ? null : _encode(row['senses']),
      body.isEmpty ? null : _encode(body),
    );
  }

  static Uint8List _encode(Object? value) =>
      Uint8List.fromList(zlib.encode(utf8.encode(jsonEncode(value))));

  static dynamic _decode(Uint8List blob) =>
      jsonDecode(utf8.decode(zlib.decode(blob)));
}
