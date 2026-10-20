// Card #428: DictionarySync on a phone — the pack arrives as a SQLite file
// (format=sqlite), is opened from disk, and later versions come as deltas
// applied to that file. Nothing of the pack is parsed into memory as JSON.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

Map<String, dynamic> pack(String version, String meaning) => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': version,
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'A1',
          'senses': [
            {'id': 1, 'definition': 'fruit', 'native': meaning}
          ],
          'examples': [
            {'text': 'An apple.', 'translation': '$meaning。', 'level': 'A1'}
          ],
        }
      ],
    };

Map<String, dynamic> delta(Map<String, dynamic> from, Map<String, dynamic> to) =>
    {
      'delta_version': 1,
      'base_version': from['created_at'],
      'metadata': {
        for (final e in to.entries)
          if (e.key != 'lexemes') e.key: e.value
      },
      'order': [for (final r in to['lexemes'] as List) r['id']],
      'upserts': [
        for (final r in to['lexemes'] as List)
          if (!(from['lexemes'] as List).any((o) => jsonEncode(o) == jsonEncode(r))) r
      ],
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late WordDatabaseRepository repo;
  late String id;
  final services = <DictionarySync>[];

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('card428-sync-');
    Hive.init('${directory.path}/hive');
    LexiconPack.storageDirectory =
        () async => Directory('${directory.path}/lexicon');
    repo = WordDatabaseRepository();
    id = repo.addWord(word: 'apple', pos: 'noun', meaning: '舊意思').id;
  });
  tearDown(() async {
    for (final s in services) {
      s.dispose();
    }
    services.clear();
    await Hive.close();
    LexiconPack.instance.clear();
    try {
      await directory.delete(recursive: true);
    } on FileSystemException {
      // Windows may still hold the replaced pack for a moment.
    }
  });
  DictionarySync service(http.Client client) {
    final s = DictionarySync(client: client, remote: true);
    services.add(s);
    return s;
  }

  http.Response sqliteResponse(Map<String, dynamic> p) {
    final file = '${directory.path}/${p['created_at']}.sqlite';
    LexiconSqlite.build(p, file);
    return http.Response.bytes(File(file).readAsBytesSync(), 200, headers: {
      'content-type': 'application/vnd.sqlite3',
      'etag': 'W/"${p['created_at']}"',
    });
  }

  http.Response jsonResponse(Object body) =>
      http.Response.bytes(utf8.encode(jsonEncode(body)), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});

  List<File> downloads() => [
        for (final f in Directory('${directory.path}/lexicon').listSync())
          if (f is File && f.path.contains('.server.')) f
      ];

  test('a phone downloads the pack as SQLite, then takes deltas', () async {
    expect(DictionarySync.useSqlite, isTrue);
    final requests = <Uri>[];
    var current = pack('v1', '蘋果一');
    var previous = <String, dynamic>{};
    final s = service(MockClient((request) async {
      requests.add(request.url);
      final since = request.url.queryParameters['since'];
      if (request.headers['If-None-Match'] == '"${current['created_at']}"') {
        return http.Response('', 304);
      }
      if (since != null && since == previous['created_at']) {
        return jsonResponse(delta(previous, current));
      }
      return sqliteResponse(current);
    }));
    await s.start(AppSettings.inMemory(), () => repo);
    expect(requests.single.queryParameters['format'], 'sqlite');
    // Before the first download the bundled SQLite pack (the real asset,
    // copied into the test's storage directory) is the base offered.
    final bundled = LexiconSqlite.inspect(LexiconPack.bundledSqlitePath(
        Directory('${directory.path}/lexicon'), 'en', 'zh-TW'));
    expect(bundled?.version, isNotNull);
    expect(requests.single.queryParameters['since'], bundled!.version);
    expect(LexiconPack.instance.fromSqlite, isTrue);
    expect(LexiconPack.instance.version, 'v1');
    expect(repo.entry(id)!.meaning, '蘋果一');
    expect(downloads(), hasLength(1));
    expect(s.hasError, isFalse);

    // Unchanged: a 304 on the ETag, nothing read.
    await s.refresh();
    expect(requests.last.queryParameters['since'], 'v1');
    expect(LexiconPack.instance.version, 'v1');

    // A new version: a delta patches the downloaded file in place.
    previous = current;
    current = pack('v2', '蘋果二');
    await s.refresh();
    expect(requests.last.queryParameters['since'], 'v1');
    expect(LexiconPack.instance.version, 'v2');
    expect(LexiconPack.instance.fromSqlite, isTrue);
    expect(repo.entry(id)!.meaning, '蘋果二');
    expect(repo.entry(id)!.examples.single.translation, '蘋果二。');
    expect(downloads(), hasLength(1), reason: 'patched, not re-downloaded');
    final path = downloads().single.path;
    expect(LexiconSqlite.inspect(path)!.version, 'v2');

    // Two versions behind: the server has no delta, the file is replaced.
    previous = pack('v2.5', 'x');
    current = pack('v3', '蘋果三');
    await s.refresh();
    expect(LexiconPack.instance.version, 'v3');
    expect(repo.entry(id)!.meaning, '蘋果三');
    final kept =
        downloads().map((f) => f.path.replaceAll('\\', '/')).toList();
    expect(kept, isNot(contains(path.replaceAll('\\', '/'))),
        reason: 'the old download is gone');
    expect(kept, hasLength(1));
    expect(LexiconPack.instance.sqlitePath!.replaceAll('\\', '/'), kept.single);
  });

  test('a restart opens the downloaded pack from disk before asking', () async {
    final v1 = pack('v1', '蘋果一');
    final first = service(MockClient((_) async => sqliteResponse(v1)));
    await first.start(AppSettings.inMemory(), () => repo);
    expect(LexiconPack.instance.version, 'v1');
    first.dispose();
    services.clear();
    LexiconPack.instance.clear();

    final restartedRepo = WordDatabaseRepository();
    final rid = restartedRepo.addWord(word: 'apple', pos: 'noun', meaning: '').id;
    var asked = 0;
    final restarted = service(MockClient((request) async {
      asked++;
      expect(request.headers['If-None-Match'], '"v1"');
      return http.Response('', 304);
    }));
    await restarted.start(AppSettings.inMemory(), () => restartedRepo);
    expect(asked, 1);
    expect(LexiconPack.instance.fromSqlite, isTrue);
    expect(LexiconPack.instance.version, 'v1');
    expect(restartedRepo.entry(rid)!.meaning, '蘋果一');
    expect(restarted.hasError, isFalse);
  });

  test('a broken download is discarded and the current pack stays', () async {
    final v1 = pack('v1', '蘋果一');
    var broken = false;
    final s = service(MockClient((_) async {
      if (broken) {
        return http.Response.bytes(utf8.encode('not a database'), 200,
            headers: {'content-type': 'application/vnd.sqlite3'});
      }
      return sqliteResponse(v1);
    }));
    await s.start(AppSettings.inMemory(), () => repo);
    expect(LexiconPack.instance.version, 'v1');
    broken = true;
    await s.refresh();
    expect(s.hasError, isTrue);
    expect(LexiconPack.instance.version, 'v1');
    expect(repo.entry(id)!.meaning, '蘋果一');
    expect(downloads(), hasLength(1));
    expect(Directory('${directory.path}/lexicon')
            .listSync()
            .where((f) => f.path.endsWith('.part')),
        isEmpty);
  });

  test('a server that still answers JSON is handled as before', () async {
    final s = service(
        MockClient((_) async => jsonResponse(pack('j1', '蘋果 JSON'))));
    await s.start(AppSettings.inMemory(), () => repo);
    expect(LexiconPack.instance.fromSqlite, isFalse);
    expect(LexiconPack.instance.version, 'j1');
    expect(repo.entry(id)!.meaning, '蘋果 JSON');
    expect(s.hasError, isFalse);
  });
}
