// 問題回報：Mac 實機量測同步新詞庫時主執行緒卡 1,151ms（M-PERF2）: applying a
// new server pack (delta, re-index, linkLexicon) ran in one synchronous
// block on the UI isolate. Now copy, patch and index run on a background
// isolate and the words are linked in slices, with the same result.
import 'dart:async';
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

/// The longest the event loop went without a turn while [work] ran.
Future<Duration> longestStall(Future<void> Function() work) async {
  var longest = Duration.zero;
  final watch = Stopwatch()..start();
  var last = watch.elapsed;
  final timer = Timer.periodic(const Duration(milliseconds: 1), (_) {
    final now = watch.elapsed;
    if (now - last > longest) longest = now - last;
    last = now;
  });
  await work();
  final now = watch.elapsed;
  if (now - last > longest) longest = now - last;
  timer.cancel();
  return longest;
}

Map<String, Object?> comparable(WordDatabaseRepository repo) => {
      for (final e in repo.entries)
        e.word: {
          ...e.toJson()
            ..remove('id')
            ..remove('createdAt')
            ..remove('updatedAt'),
        },
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  final services = <DictionarySync>[];

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('sync-main-thread-');
    Hive.init('${directory.path}/hive');
    LexiconPack.storageDirectory =
        () async => Directory('${directory.path}/lexicon');
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

  for (final full in [false, true]) {
    final kind = full ? '整個 SQLite 檔' : 'delta';
    test('同步新詞庫（$kind）時主執行緒不再整段卡住，結果與原本一樣', () async {
      // The real bundled pack, as the app has it before the first sync.
      await LexiconPack.instance.load(target: 'en', native: 'zh-TW');
      expect(LexiconPack.instance.fromSqlite, isTrue);
      final bundledPath = LexiconPack.instance.sqlitePath!;
      final base = LexiconSqlite.open(bundledPath, readOnly: true);
      final meta = base.meta();
      final ids = <int>[];
      final upserts = <Map<String, dynamic>>[];
      for (final head in base.heads()) {
        final id = (head['id'] as num).toInt();
        ids.add(id);
        final senses = base.senses(id);
        if (upserts.length >= 2000 || senses == null || senses.isEmpty) {
          continue;
        }
        upserts.add({
          ...head,
          ...?base.body(id),
          'senses': [
            for (final (i, s) in senses.cast<Map<String, dynamic>>().indexed)
              i == 0 && s['native'] != null
                  ? {...s, 'native': '${s['native']}（新）'}
                  : s
          ],
        });
      }
      base.close();
      final delta = {
        'delta_version': 1,
        'base_version': meta['created_at'],
        'metadata': {...meta, 'created_at': 'm-perf2-next'},
        'order': ids,
        'upserts': upserts,
      };
      final words = [
        for (final e in LexiconPack.instance.catalogWords
            .where((e) => e.full && e.learnerMeaning != null)
            .take(300))
          (e.lemma, e.pos),
      ];
      WordDatabaseRepository newRepo() {
        final repo = WordDatabaseRepository();
        for (final (word, pos) in words) {
          try {
            repo.addWord(word: word, pos: pos, meaning: '');
          } on DuplicateWordException {
            // Two parts of speech of one spelling: one card.
          }
        }
        return repo;
      }

      // Before: the same work, all of it in one block on the UI isolate.
      final before = newRepo()..linkLexicon(LexiconPack.instance);
      final copy = '${directory.path}/before.sqlite';
      File(bundledPath).copySync(copy);
      final LexiconPack oldPack;
      final Stopwatch old;
      if (full) {
        // A whole new pack file, as the server sends it.
        LexiconSqlite.open(copy)
          ..applyDelta(delta)
          ..close();
        old = Stopwatch()..start();
        LexiconSqlite.inspect(copy);
        oldPack = LexiconPack()..loadSqlite(copy);
      } else {
        old = Stopwatch()..start();
        oldPack = LexiconPack()
          ..loadSqlite(copy)
          ..applySqliteDelta(delta);
      }
      before.linkLexicon(oldPack);
      old.stop();

      // Now: DictionarySync takes the new pack from the server.
      final body =
          full ? File(copy).readAsBytesSync() : utf8.encode(jsonEncode(delta));
      final type =
          full ? 'application/vnd.sqlite3' : 'application/json; charset=utf-8';
      final repo = newRepo();
      final s = DictionarySync(
          client: MockClient((request) async =>
              http.Response.bytes(body, 200, headers: {'content-type': type})),
          remote: true);
      services.add(s);
      final stall = await longestStall(() async {
        await s.start(AppSettings.inMemory(), () => repo);
        await LexiconPack.instance.warmMeanings();
      });
      // ignore: avoid_print
      print('M-PERF2 ($kind): one block before ${old.elapsedMilliseconds} ms, '
          'longest stall now ${stall.inMilliseconds} ms');

      expect(s.hasError, isFalse);
      expect(LexiconPack.instance.version, 'm-perf2-next');
      expect(LexiconPack.instance.sqlitePath, isNot(bundledPath));
      expect(LexiconPack.instance.catalogWords.map((e) => e.id),
          oldPack.catalogWords.map((e) => e.id));
      for (final (a, b) in [
        for (final (i, e) in oldPack.catalogWords.indexed)
          if (i % 50 == 0) (e, LexiconPack.instance.catalogWords[i])
      ]) {
        expect(b.learnerMeaning, a.learnerMeaning);
        expect(b.examples.map((x) => x.text), a.examples.map((x) => x.text));
      }
      expect(comparable(repo), comparable(before));
      expect(
          repo.filledByUpdate.keys.toSet(), before.filledByUpdate.keys.toSet());
      expect(stall * 3, lessThan(old.elapsed),
          reason: 'the longest stall is a small part of the old block');
      oldPack.clear();
    }, timeout: const Timeout(Duration(minutes: 3)));
  }

  test('linkLexiconInBatches 中途有新的 linkLexicon 會先做完，結果一樣', () async {
    await LexiconPack.instance.load(target: 'en', native: 'zh-TW');
    final pack = LexiconPack.instance;
    final words = [
      for (final e in pack.catalogWords.where((e) => e.full).take(200))
        (e.lemma, e.pos),
    ];
    WordDatabaseRepository newRepo() {
      final repo = WordDatabaseRepository();
      for (final (word, pos) in words) {
        try {
          repo.addWord(word: word, pos: pos, meaning: '');
        } on DuplicateWordException {
          // One card per spelling.
        }
      }
      return repo;
    }

    final expected = newRepo()..linkLexicon(pack);
    final repo = newRepo();
    final batches = repo.linkLexiconInBatches(pack, budget: Duration.zero);
    await Future<void>.delayed(Duration.zero);
    // A word added while the batches pause, then a synchronous link.
    final added = repo.addWord(word: 'zzz-m-perf2', pos: 'noun', meaning: '自訂');
    repo.linkLexicon(pack);
    await batches;
    expect(repo.entry(added.id)!.meaning, '自訂');
    final got = comparable(repo)..remove('zzz-m-perf2');
    expect(got, comparable(expected));
  });
}
