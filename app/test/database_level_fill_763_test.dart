import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_selector.dart';

import 'helpers.dart';

/// 問題回報 #763 (owner chose A): the database picture pages follow 照片詳情's
/// rule — each level lists five words, filled from the nearest levels.

/// One word per entry of [levels] (null = unleveled), ids 1…n, each with a
/// pin except the ones in [noPoint].
Map<String, dynamic> catalog(List<String?> levels,
        {Set<int> noPoint = const {}}) =>
    {
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        for (var i = 1; i <= levels.length; i++)
          {
            'id': i,
            'lemma': 'w$i',
            'normalized': 'w$i',
            'pos': 'noun',
            'status': 'full',
            'senses': [
              {'id': i * 10, 'native': '字$i'}
            ],
          },
      ],
      'catalog_images': [
        {
          'id': 7,
          'url': 'http://127.0.0.1/api/image?id=7',
          'tags': [
            for (var i = 1; i <= levels.length; i++)
              {
                'lexeme_id': i,
                'sense_id': i * 10,
                'review_status': 'approved',
                if (levels[i - 1] != null) 'cefr': levels[i - 1],
              },
          ],
          'labels': [
            for (var i = 1; i <= levels.length; i++)
              {
                'word': 'w$i',
                'point': noPoint.contains(i) ? null : [0.1 * i, 0.5],
                'lexeme_id': i,
              },
          ],
        },
      ],
    };

Map<String, dynamic> firstImage() => LexiconPack.instance.catalogImages.first;

List<int> ids(List<Map<String, dynamic>> tags) =>
    [for (final t in tags) (t['lexeme_id'] as num).toInt()];

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('nearest-level order matches the photo detail: easier first', () {
    // B1 (2): B1, A2, B2, A1, C1, C2.
    final order = [for (var l = 0; l < 6; l++) l]..sort((a, b) =>
        WordSelector.nearestLevelOrder(a, 2)
            .compareTo(WordSelector.nearestLevelOrder(b, 2)));
    expect(order, [2, 1, 3, 0, 4, 5]);
  });

  test('a short level fills to five from the nearest levels', () {
    // ids: 1 B1, 2 C2, 3 A1, 4 B2, 5 A2, 6 C1, 7 unleveled
    LexiconPack.instance
        .loadJson(catalog(['B1', 'C2', 'A1', 'B2', 'A2', 'C1', null]));
    final pack = LexiconPack.instance;
    // B1 + A2, B2, A1, C1 — C2 and the unleveled word are left out.
    expect(ids(databaseLevelTags(firstImage(), pack, 'B1')), [1, 5, 4, 3, 6]);
    // A1 + A2, B1, B2, C1.
    expect(ids(databaseLevelTags(firstImage(), pack, 'A1')), [3, 5, 1, 4, 6]);
    // Pins match the list; without borrowing only the level's own.
    expect(databasePins(firstImage(), pack, level: 'B1').map((p) => p.word),
        unorderedEquals(['w1', 'w3', 'w4', 'w5', 'w6']));
    expect(
        databasePins(firstImage(), pack, level: 'B1', borrow: false)
            .map((p) => p.word),
        ['w1']);
  });

  test('a level with five or more words keeps its own, all of them', () {
    LexiconPack.instance
        .loadJson(catalog(['A1', 'A1', 'A1', 'A1', 'A1', 'A1', 'A2']));
    expect(ids(databaseLevelTags(firstImage(), LexiconPack.instance, 'A1')),
        [1, 2, 3, 4, 5, 6]);
  });

  test('fewer than five words on the picture: all of them, no padding', () {
    LexiconPack.instance.loadJson(catalog(['A1', 'C2']));
    expect(ids(databaseLevelTags(firstImage(), LexiconPack.instance, 'B2')),
        [2, 1]);
  });

  test('a search hit filled in from a nearby level needs no hint', () {
    LexiconPack.instance.loadJson(catalog(['A1', 'B1']));
    final pack = LexiconPack.instance;
    expect(databaseSearchElsewhere(firstImage(), pack, 'w2', 'A1'), isNull);
    LexiconPack.instance
        .loadJson(catalog(['A1', 'A1', 'A1', 'A1', 'A1', 'B1']));
    expect(databaseSearchElsewhere(firstImage(), pack, 'w6', 'A1'),
        (word: 'w6', level: 'B1'));
  });

  test('new copy is translated', () {
    for (final lang in ['en', 'fr']) {
      for (final source in [
        '入門（A1）：3 張圖片有這個程度的標籤 · 不到 5 個字的從相近程度補',
        '入門（A1）：3 張圖片有這個程度的標籤 · 不到 5 個字的從相近程度補 · 2 張的搜尋字在其他程度',
        '這個程度不到 5 個字，已從相近程度補上',
      ]) {
        final out = translateUi(source, lang);
        expect(out, isNot(source));
        expect(out, isNot(contains('相近')));
        expect(out, contains('5'));
      }
    }
    expect(translateUi('這個程度不到 5 個字，已從相近程度補上', 'en'),
        'Fewer than 5 words at this level; filled from nearby levels');
  });

  testWidgets('tile marks borrowed words with their level', (tester) async {
    LexiconPack.instance.loadJson(catalog(['B1', 'A2']));
    await pumpApp(tester,
        home: Scaffold(
            body: SizedBox(
                width: 175,
                height: 280,
                child: DatabaseImageTile(image: firstImage(), level: 'B1'))));
    await tester.pumpAndSettle();
    expect(find.text('中階（B1）：w1 · 字1、w2 · 字2（A2）'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('picture page at 375pt: borrowed badge and 整張圖, no overflow',
      (tester) async {
    // w2 (A2) has no point: listed as 整張圖 with no pin, and borrowed.
    LexiconPack.instance
        .loadJson(catalog(['B1', 'A2', 'B2', 'A1', 'C1'], noPoint: {2}));
    await pumpApp(tester,
        size: const Size(375, 2000),
        home: const DatabaseImageScreen(imageId: 7, initialLevel: 'B1'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('borrowed-hint')), findsOneWidget);
    expect(find.byKey(const ValueKey('borrowed-1')), findsNothing);
    expect(find.byKey(const ValueKey('borrowed-2')), findsOneWidget);
    expect(find.byKey(const ValueKey('whole-picture-2')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('toggle-B1')));
    await tester.pumpAndSettle();
    for (final id in [3, 4, 5]) {
      expect(find.byKey(ValueKey('borrowed-$id')), findsOneWidget);
    }
    expect(tester.takeException(), isNull);
  });
}
