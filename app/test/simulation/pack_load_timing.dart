// How long loading the live pack takes (not part of the regular suite).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

void main() {
  test('pack load time', () {
    final text = File(Platform.environment['SIM_PACK'] ?? 'build/live_pack.json').readAsStringSync();
    for (var i = 0; i < 3; i++) {
      final sw = Stopwatch()..start();
      final j = jsonDecode(text) as Map<String, dynamic>;
      final decode = sw.elapsedMilliseconds;
      LexiconPack.instance.loadJson(j);
      final load = sw.elapsedMilliseconds - decode;
      final lookups = Stopwatch()..start();
      for (final w in LexiconPack.instance.catalogWords.take(2000)) {
        LexiconPack.instance.lookup(w.lemma);
      }
      // ignore: avoid_print
      print('bytes ${text.length} decode ${decode}ms load ${load}ms 2000 lookups ${lookups.elapsedMilliseconds}ms');
    }
  });
}
