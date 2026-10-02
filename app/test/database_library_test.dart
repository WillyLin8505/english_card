import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'helpers.dart';

Map<String, dynamic> catalog({String meaning = '蘋果', bool removed = false}) => {
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        if (!removed)
          {
            'id': 1,
            'lemma': 'apple',
            'normalized': 'apple',
            'pos': 'noun',
            'status': 'full',
            'senses': [
              {'id': 11, 'native': meaning, 'definition': 'fruit'}
            ]
          },
        {
          'id': 2,
          'lemma': 'pome',
          'normalized': 'pome',
          'pos': 'noun',
          'status': 'stub'
        },
      ],
      'catalog_images': [
        if (!removed)
          {
            'id': 9,
            'url': 'http://127.0.0.1/api/image?id=9',
            'tags': [
              {'lexeme_id': 1, 'sense_id': 11, 'review_status': 'approved'}
            ]
          }
      ],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson(catalog()));
  tearDown(() => LexiconPack.instance.clear());
  testWidgets(
      'database is default, stubs opt in, personal collection is preserved',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.words,
        databaseLibrary: true,
        size: const Size(360, 740));
    final original = app.repository.wordCount;
    expect(find.text('資料庫單字本'), findsOneWidget);
    expect(find.text('apple'), findsOneWidget);
    expect(find.text('pome'), findsNothing);
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    expect(find.text('pome'), findsOneWidget);
    await tester.tap(find.text('我的收藏'));
    await tester.pumpAndSettle();
    expect(find.text('我的單字本'), findsOneWidget);
    expect(app.repository.wordCount, original);
    expect(tester.takeException(), isNull);
  });

  testWidgets('snapshot corrections and deletions update visible database list',
      (tester) async {
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    LexiconPack.instance.loadJson(catalog(meaning: '更新後的蘋果'));
    await tester.pump();
    expect(find.textContaining('更新後的蘋果'), findsOneWidget);
    LexiconPack.instance.loadJson(catalog(removed: true));
    await tester.pump();
    expect(find.text('apple'), findsNothing);
    expect(find.text('沒有符合的單字'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'every database image has a bilingual label and opens its exact word',
      (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.album,
        databaseLibrary: true,
        size: const Size(360, 740));
    await tester.pumpAndSettle();
    expect(find.text('apple · 蘋果'), findsOneWidget);
    await tester.tap(find.byType(DatabaseImageTile));
    await tester.pumpAndSettle();
    expect(find.text('已確認'), findsOneWidget);
    await tester.tap(find.text('apple · 蘋果'));
    await tester.pumpAndSettle();
    expect(find.text('資料庫圖片（1）'), findsOneWidget);
    expect(find.text('蘋果'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
