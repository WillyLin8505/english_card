// 問題回報 #1270 (card #943): the apple word page on a small screen — the
// noun's Chinese 蘋果 shows once even when a rarer sense repeats it, the noun
// comes before the verb, and the first picture is inside the first screen.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

Map<String, dynamic> _pack() => {
      'catalog_version': 1,
      'schema_version': 4,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'A1',
          'picture_ids': [1],
          'senses': [
            {'id': 10, 'definition': 'a fruit', 'native': '蘋果'},
            // The same Chinese again on a low-priority sense (Kaikki order).
            {
              'id': 11,
              'definition': 'a fruit or vegetable',
              'native': '蘋果',
              'labels': ['low_priority'],
            },
          ],
        },
        {
          'id': 2,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'verb',
          'status': 'full',
          'cefr': 'C1',
          'senses': [
            {
              'id': 20,
              'definition': 'to make appear like an apple',
              'native': '使看似蘋果',
              'labels': ['transitive'],
            },
          ],
        },
      ],
      'catalog_images': [
        {
          'id': 9,
          'url': 'http://127.0.0.1/api/image?id=9',
          'width': 600,
          'height': 800,
          'tags': [
            {'lexeme_id': 1, 'sense_id': 10, 'review_status': 'approved'},
          ],
          'labels': [],
        },
      ],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson(_pack()));
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('apple: 蘋果 once in the noun area, noun before verb, image on screen',
      (tester) async {
    await pumpApp(tester,
        home: const DatabaseWordScreen(wordId: 1),
        size: const Size(375, 667));
    await tester.pumpAndSettle();

    // The duplicate 蘋果 (sense 11) is not listed again.
    expect(find.byKey(const ValueKey('sense-1-1')), findsOneWidget);
    expect(find.byKey(const ValueKey('sense-1-2')), findsNothing);
    expect(find.text('蘋果'), findsOneWidget);

    // Common noun meaning first; the verb follows it.
    expect(find.byKey(const ValueKey('sense-2-1')), findsOneWidget);
    expect(
        tester.getTopLeft(find.byKey(const ValueKey('sense-1-1'))).dy,
        lessThan(tester.getTopLeft(find.byKey(const ValueKey('sense-2-1'))).dy));

    // The first picture sits inside a 375×667 (iPhone SE) first screen.
    final image = find.byKey(const ValueKey('database-first-image'));
    expect(image, findsOneWidget);
    expect(tester.getBottomLeft(image).dy, lessThan(667));
  });
}
