import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

/// 問題回報 #113: the albums' 標籤程度 picker shows another level's labels on
/// the same pictures, without touching saved words or tags.
Finder chip(String label) => find.widgetWithText(FilterPill, label);
Finder level(String label) =>
    find.descendant(of: find.byType(LabelLevelBar), matching: find.text(label));

Map<String, dynamic> leveledCatalog() => {
      'catalog_version': 1,
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
          'senses': [
            {'id': 11, 'native': '蘋果', 'definition': 'fruit'}
          ]
        },
        {
          'id': 3,
          'lemma': 'cluster',
          'normalized': 'cluster',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'B1',
          'senses': [
            {'id': 31, 'native': '串', 'definition': 'a group'}
          ]
        },
      ],
      'catalog_images': [
        {
          'id': 9,
          'url': 'http://127.0.0.1/api/image?id=9',
          'tags': [
            {'lexeme_id': 1, 'sense_id': 11, 'review_status': 'approved'},
            {'lexeme_id': 3, 'sense_id': 31, 'review_status': 'approved'},
          ],
          'labels': [
            {
              'word': 'apple',
              'point': [0.3, 0.4],
              'lexeme_id': 1
            },
            {
              'word': 'cluster',
              'point': [0.6, 0.5],
              'lexeme_id': 3
            },
          ],
        },
        {
          'id': 10,
          'url': 'http://127.0.0.1/api/image?id=10',
          'tags': [
            {
              'lexeme_id': 3,
              'sense_id': 31,
              'review_status': 'approved',
              'cefr': 'C1'
            },
          ],
          // A level association without coordinates cannot draw a label.
          'labels': [
            {'word': 'cluster', 'point': null, 'lexeme_id': 3},
          ],
        }
      ],
    };

void main() {
  testWidgets('我的相片冊：切換程度只換顯示的標籤，不改照片的單字與轉盤', (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.album);
    final repo = app.repository;
    final before = repo.photo('photo-breakfast')!;
    final saved = [for (final l in repo.visibleLabels(before.id)) l.entry.word];
    await tester.tap(find.text('早餐時光'));
    await tester.pumpAndSettle();
    expect(level('學習中'), findsOneWidget);
    expect(chip('coffee'), findsOneWidget);

    // B2 shows the photo's B2 candidates instead of the saved words.
    await tester.tap(level('B2'));
    await tester.pumpAndSettle();
    expect(chip('slice'), findsOneWidget);
    expect(chip('rustic'), findsOneWidget);
    expect(chip('coffee'), findsNothing);

    await tester.tap(level('C2'));
    await tester.pumpAndSettle();
    expect(find.text('沒有 C2 標籤'), findsOneWidget);

    await tester.tap(level('學習中'));
    await tester.pumpAndSettle();
    expect(chip('coffee'), findsOneWidget);

    // Nothing was written: same words, same dial setting.
    final after = repo.photo('photo-breakfast')!;
    expect(after.difficultyOffset, before.difficultyOffset);
    expect(after.wordsSavedAt, before.wordsSavedAt);
    expect(after.candidates.length, before.candidates.length);
    expect([for (final l in repo.visibleLabels(after.id)) l.entry.word], saved);

    // Learned words stay hidden at every level.
    repo.archiveWord(repo.entryByWord('apple')!.id);
    await tester.tap(level('A1'));
    await tester.pumpAndSettle();
    expect(chip('apple'), findsNothing);
    expect(chip('bread'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  group('資料庫相片冊', () {
    setUp(() => LexiconPack.instance.loadJson(leveledCatalog()));
    tearDown(() => LexiconPack.instance.clear());

    test('pins keep only the chosen level', () {
      final image = (leveledCatalog()['catalog_images'] as List).first
          as Map<String, dynamic>;
      final pack = LexiconPack.instance;
      expect(
          databasePins(image, pack).map((p) => p.word), ['apple', 'cluster']);
      expect(databasePins(image, pack, level: 'B1').map((p) => p.word),
          ['cluster']);
      expect(databasePins(image, pack, level: 'C1'), isEmpty);
    });

    testWidgets('the picker filters tiles and the opened picture',
        (tester) async {
      await pumpApp(tester,
          initialTab: AppTab.album,
          databaseLibrary: true,
          size: const Size(360, 740));
      await tester.pumpAndSettle();
      // One line per level (#179).
      expect(find.text('入門（A1）：apple · 蘋果'), findsOneWidget);
      expect(find.text('中階（B1）：cluster · 串'), findsOneWidget);

      await tester.tap(level('B1'));
      await tester.pumpAndSettle();
      expect(find.text('中階（B1）：cluster · 串'), findsOneWidget);

      expect(find.text('中階（B1）：1 張圖片有這個程度的標籤'), findsOneWidget);

      // A level no picture has: the album lists nothing.
      await tester.tap(level('C1'));
      await tester.pumpAndSettle();
      expect(find.byType(DatabaseImageTile), findsNothing);
      expect(find.text('沒有符合的圖片'), findsOneWidget);

      // The picture opens at the album's level and has its own picker.
      await tester.tap(level('B1'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(DatabaseImageTile));
      await tester.pumpAndSettle();
      expect(find.text('cluster · 串'), findsOneWidget);
      expect(find.text('apple · 蘋果'), findsNothing);
      await tester.tap(level('C1'));
      await tester.pumpAndSettle();
      expect(find.text('這張圖片沒有 進階（C1） 的標籤，換個程度看看。'), findsOneWidget);
      await tester.tap(level('A1'));
      await tester.pumpAndSettle();
      // The tag list sits below a tall picture: scroll to its end.
      Future<void> toEnd() async {
        await tester.drag(find.byType(ListView).last, const Offset(0, -2000));
        await tester.pumpAndSettle();
      }

      await toEnd();
      expect(find.text('apple · 蘋果'), findsOneWidget);
      expect(find.text('cluster · 串'), findsNothing);
      await tester.drag(find.byType(ListView).last, const Offset(0, 2000));
      await tester.pumpAndSettle();
      await tester.tap(level('全部'));
      await tester.pumpAndSettle();
      await toEnd();
      expect(find.text('apple · 蘋果'), findsOneWidget);
      expect(find.text('cluster · 串'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
