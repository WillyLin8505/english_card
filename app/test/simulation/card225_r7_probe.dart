// Card 225 round 7 probe: does a photo pin's tap open the pinned entry?
// SIM_PACK=build/rounds/<N>/pack.json flutter test test/simulation/card225_r7_probe.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';

void main() {
  test('pin tap target', () {
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(Platform.environment['SIM_PACK']!).readAsStringSync())
          as Map<String, dynamic>);
    var pins = 0, other = 0, otherPos = 0;
    final ex = <String, int>{};
    for (final image in pack.catalogImages) {
      final byWord = {
        for (final l in (image['labels'] as List? ?? []))
          if ((l as Map)['lexeme_id'] is num) '${l['word']}': (l['lexeme_id'] as num).toInt()
      };
      for (final pin in databasePins(image, pack)) {
        pins++;
        final id = byWord[pin.word];
        final opened = pack.byId(pin.lexemeId ?? -1) ?? pack.lookup(pin.word)?.entry;
        if (opened == null || opened.id == id) continue;
        other++;
        final pinned = pack.byId(id!);
        if (pinned != null && pinned.normalized == opened.normalized && pinned.pos != opened.pos) {
          otherPos++;
          final k = '${pin.word} ${pinned.pos}→${opened.pos}';
          ex[k] = (ex[k] ?? 0) + 1;
        }
      }
    }
    final top = ex.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
    // ignore: avoid_print
    print('pins $pins opens other entry $other same word other POS $otherPos ${top.take(15).map((e) => '${e.key}:${e.value}').join(', ')}');
  });
}
