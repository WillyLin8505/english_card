import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

void main() {
  final pack = LexiconPack()
    ..loadJson({
      'schema_version': 4,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 7,
          'lemma': 'banana',
          'normalized': 'banana',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 70, 'definition': 'A fruit.', 'native': '香蕉、香蕉樹'},
          ],
        },
      ],
    });
  final image = {
    'id': 5,
    'url': '/api/image?id=5',
    'width': 600,
    'height': 800,
    'tags': [
      {'lexeme_id': 7, 'sense_id': 70, 'review_status': 'approved'},
    ],
    'labels': [
      {
        'word': 'tile',
        'pos': 'noun',
        'point': [0.8, 0.1],
        'box': null,
        'lexeme_id': null
      },
      {
        'word': 'banana',
        'pos': 'noun',
        'point': [0.5, 0.5],
        'box': [0.2, 0.3, 0.6, 0.9],
        'lexeme_id': 7
      },
      {
        'word': 'ripe',
        'pos': 'adjective',
        'point': [0.4, 0.6],
        'box': null,
        'lexeme_id': null
      },
    ],
  };

  test('database pictures show only approved formal labels', () {
    final pins = databasePins(image, pack);
    expect(pins.first.word, 'banana', reason: 'words in the lexicon first');
    expect(pins.first.zh, '香蕉');
    expect(pins.first.linked, isTrue);
    // "The middle of the picture" becomes the middle of the label's box.
    expect(pins.first.anchor.x, closeTo(0.4, 1e-9));
    expect(pins.first.anchor.y, closeTo(0.6, 1e-9));
    expect(pins.map((p) => p.word), ['banana']);
    expect(databasePins(image, pack, max: 2), hasLength(1));
  });

  test('rejected bindings and unlinked model suggestions stay hidden', () {
    final rejected = Map<String, dynamic>.from(image)
      ..['tags'] = [
        {'lexeme_id': 7, 'sense_id': 70, 'review_status': 'rejected'},
      ];
    expect(databasePins(rejected, pack), isEmpty);
    expect(databasePins(image, pack).map((pin) => pin.word),
        isNot(contains('tile')));
  });

  testWidgets('the album tile draws the labels on the picture', (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: SizedBox(
            width: 180,
            height: 220,
            child: PinnedPhoto(
                photo: databasePhoto(image),
                pins: databasePins(image, pack, max: 4),
                radius: 0))));
    expect(find.text('banana'), findsOneWidget);
    expect(find.text('香蕉'), findsOneWidget);
    expect(find.byType(WordPin), findsOneWidget);
  });
}
