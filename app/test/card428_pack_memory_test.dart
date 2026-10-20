// Card #428: how much memory the real bundled pack costs in each form.
// Skipped unless CARD428_MODE=json or CARD428_MODE=sqlite is set, so the
// two runs are separate processes:
//   CARD428_MODE=json   flutter test test/card428_pack_memory_test.dart
//   CARD428_MODE=sqlite flutter test test/card428_pack_memory_test.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

String mb(int bytes) => (bytes / 1048576).toStringAsFixed(0);

void main() {
  final mode = Platform.environment['CARD428_MODE'];
  test('pack memory ($mode)', () async {
    if (mode != 'json' && mode != 'sqlite') {
      markTestSkipped('set CARD428_MODE=json|sqlite');
      return;
    }
    final out = <String>[];
    void rss(String label) {
      out.add('${label.padRight(44)} rss=${mb(ProcessInfo.currentRss)} MB');
    }
    rss('start');
    final pack = LexiconPack();
    final sw = Stopwatch()..start();
    if (mode == 'json') {
      final raw = File('assets/lexicon/en-zh-TW.json').readAsStringSync();
      rss('readAsString');
      final json = jsonDecode(raw) as Map<String, dynamic>;
      rss('jsonDecode (raw still held)');
      pack.loadJson(json);
      rss('loadJson → ${pack.size} words (${sw.elapsedMilliseconds} ms)');
    } else {
      final dir = Directory.systemTemp.createTempSync('card428_mem_');
      final path = '${dir.path}/en-zh-TW.sqlite';
      File('assets/lexicon/en-zh-TW.sqlite').copySync(path);
      sw.reset();
      pack.loadSqlite(path);
      rss('loadSqlite → ${pack.size} words (${sw.elapsedMilliseconds} ms)');
      sw.reset();
      await pack.warmMeanings();
      rss('warmMeanings (every learnerMeaning, ${sw.elapsedMilliseconds} ms)');
    }
    // What a session touches: the 資料庫單字本 search over every word, then
    // the detail of 500 words (examples, relations, etymology…).
    sw.reset();
    var hits = 0;
    for (final e in pack.catalogWords) {
      if (e.searchRank('ap') != null) hits++;
    }
    rss('search all words → $hits hits (${sw.elapsedMilliseconds} ms)');
    sw.reset();
    var sentences = 0;
    for (final e in pack.catalogWords.where((e) => e.full).take(500)) {
      sentences += pack.detailFor(e).exampleSentences.length;
    }
    rss('detail of 500 words → $sentences sentences '
        '(${sw.elapsedMilliseconds} ms)');
    // ignore: avoid_print
    print(out.join('\n'));
    final report = File('../lexicon/logs/agents/card428/memory_$mode.txt')
      ..parent.createSync(recursive: true);
    report.writeAsStringSync('${out.join('\n')}\n');
    pack.clear();
  }, timeout: const Timeout(Duration(minutes: 5)));
}
