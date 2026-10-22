import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

/// Card #510 (問題回報 #524): an approved label with no point draws no pin;
/// the photo-label list marks it 「整張圖」 so it does not look like a missing
/// pin. A label with a point shows no mark.
Map<String, dynamic> image() => {
      'id': 9,
      'url': 'http://127.0.0.1/api/image?id=9',
      'tags': [
        {'lexeme_id': 1, 'cefr': 'A1', 'review_status': 'approved'},
        {'lexeme_id': 2, 'cefr': 'A1', 'review_status': 'approved'},
      ],
      'labels': [
        {'word': 'tree', 'pos': 'noun', 'point': [0.3, 0.4], 'lexeme_id': 1},
        {'word': 'light', 'pos': 'noun', 'point': null, 'lexeme_id': 2},
      ],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson({
        'catalog_version': 1,
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          for (final (id, lemma) in [(1, 'tree'), (2, 'light')])
            {
              'id': id,
              'lemma': lemma,
              'normalized': lemma,
              'pos': 'noun',
              'status': 'full',
              'senses': [
                {'id': id, 'native': '意思$id'}
              ],
            },
        ],
        'catalog_images': [image()],
      }));
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('a label without a point is marked 整張圖, one with a point is not',
      (tester) async {
    await pumpApp(tester,
        size: const Size(402, 1200),
        home: Scaffold(
          body: SingleChildScrollView(
            child: DatabaseTagSections(
                image: image(), pack: LexiconPack.instance),
          ),
        ));
    expect(find.textContaining('tree'), findsOneWidget);
    expect(find.textContaining('light'), findsOneWidget);
    expect(find.byKey(const ValueKey('whole-picture-2')), findsOneWidget);
    expect(find.byKey(const ValueKey('whole-picture-1')), findsNothing);
    expect(find.text('整張圖'), findsOneWidget);
    // No pin for the unplaced label, one for the placed one.
    expect(databasePins(image(), LexiconPack.instance).length, 1);
  });
}
