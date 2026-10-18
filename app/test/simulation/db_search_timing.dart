// Timing (not part of the suite): the 資料庫單字本 filter on the live pack.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

void main() {
  test('database search filter time', () {
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(Platform.environment['SIM_PACK']!).readAsStringSync()) as Map<String, dynamic>);
    for (final q in ['', 'a', 'ap', 'app', '蘋']) {
      final sw = Stopwatch()..start();
      final words = pack.catalogWords
          .where((w) => w.searchText.contains(q.toLowerCase()))
          .toList()
        ..sort((a, b) => a.rareUsage != b.rareUsage ? (a.rareUsage ? 1 : -1) : a.lemma.compareTo(b.lemma));
      // ignore: avoid_print
      print('query "$q": ${words.length} words in ${sw.elapsedMilliseconds} ms');
    }
  });
}
