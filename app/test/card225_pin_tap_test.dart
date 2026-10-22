// Card 225 round 7: a photo pin opens the entry it is pinned to. Tapping the
// soil noun pin opened soil verb 弄髒 (the spelling's first entry): 5,654 of
// 55,906 database pins opened another entry, 4,204 the same word in another
// part of speech (hold verb→noun, outline noun→verb, stem noun→verb).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

Map<String, dynamic> soil(int id, String pos, String native) => {
      'id': id,
      'lemma': 'soil',
      'normalized': 'soil',
      'pos': pos,
      'status': 'full',
      'cefr': 'B1',
      'senses': [
        {'id': id * 10, 'definition': 'soil $pos', 'native': native},
      ],
    };

void loadPack() => LexiconPack.instance.loadJson({
      'schema_version': 4,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [soil(1, 'verb', '弄髒'), soil(2, 'noun', '土壤')],
      'catalog_images': [
        {
          'id': 9,
          'url': 'http://127.0.0.1/api/image?id=9',
          'width': 600,
          'height': 800,
          'tags': [
            {'lexeme_id': 2, 'sense_id': 20, 'review_status': 'approved'},
          ],
          'labels': [
            {
              'word': 'soil',
              'pos': 'noun',
              'point': [0.4, 0.7],
              'box': null,
              'lexeme_id': 2
            },
          ],
        },
      ],
    });

void main() {
  setUp(loadPack);
  tearDown(() => LexiconPack.instance.clear());

  test('the pin carries its lexeme, not the spelling\'s first entry', () {
    final pack = LexiconPack.instance;
    expect(pack.lookup('soil')!.entry.id, 1);
    final pins = databasePins(pack.catalogImages.single, pack);
    expect(pins.single.lexemeId, 2);
    expect(pins.single.zh, '土壤');
  });

  testWidgets('tapping the soil noun pin opens soil noun', (tester) async {
    await pumpApp(tester,
        size: const Size(402, 1400),
        home: const DatabaseImageScreen(imageId: 9));
    final pin = find.descendant(
        of: find.byType(PinnedPhoto), matching: find.textContaining('soil'));
    expect(pin, findsWidgets);
    await tester.tap(pin.first);
    await tester.pumpAndSettle();
    final screen =
        tester.widget<DatabaseWordScreen>(find.byType(DatabaseWordScreen));
    expect(screen.wordId, 2);
  });
}
