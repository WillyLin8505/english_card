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
  testWidgets('database search survives visiting the personal collection',
      (tester) async {
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'apple');
    await tester.pumpAndSettle();
    expect(find.text('pome'), findsNothing);
    await tester.tap(find.text('我的單字本'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('資料庫'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        'apple');
    expect(find.text('pome'), findsNothing);
    await tester.enterText(find.byType(TextField), '');
    await tester.pumpAndSettle();
    expect(find.text('pome'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('database detail skips glossary columns and preserves source',
      (tester) async {
    final data = catalog();
    final entry = (data['lexemes'] as List).first as Map<String, dynamic>;
    entry['examples'] = [
      {'text': 'custard apple\trose apple\tthorn apple', 'translation': '詞彙清單'},
      {'text': 'She eats an apple.', 'translation': '她吃一顆蘋果。'},
      {'text': 'The apple is red.', 'translation': '這顆蘋果是紅色的。'},
    ];
    entry['forms'] = [
      {'field': 'plural', 'form': 'apples', 'normalized': 'apples'}
    ];
    entry['relations'] = [
      {
        'relation': 'synonyms',
        'word': 'pome',
        'native': '梨果',
      },
      {
        'relation': 'homophones',
        'word': 'appel',
        'native': '點名',
      },
    ];
    entry['morphemes'] = [
      {'part': 'app', 'kind': 'root', 'native': '果實'},
      {'part': '-le', 'kind': 'suffix', 'native': '名詞後綴'},
    ];
    entry['etymology'] = {
      'text': 'Old English æppel',
      'native': '源自古英语 æppel。'
    };
    (data['lexemes'] as List).add({
      'id': 3,
      'lemma': 'apple',
      'normalized': 'apple',
      'pos': 'verb',
      'status': 'full',
      'senses': [
        {'id': 31, 'native': '長成蘋果狀', 'definition': 'form like an apple'}
      ],
    });
    LexiconPack.instance.loadJson(data);
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    await tester.tap(find.text('apple').first);
    await tester.pumpAndSettle();
    final detailScroll = find
        .descendant(
            of: find.byType(DatabaseWordScreen),
            matching: find.byType(Scrollable))
        .at(0);
    expect(find.text('custard apple\trose apple\tthorn apple'), findsNothing);
    expect(find.text('She eats an apple.'), findsOneWidget);
    expect(find.text('The apple is red.'), findsOneWidget);
    expect(find.text('動詞'), findsOneWidget);
    expect(find.text('長成蘋果狀'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('近義詞'), 300,
        scrollable: detailScroll);
    expect(find.text('近義詞'), findsOneWidget);
    expect(find.textContaining('pome'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('同音詞'), 300,
        scrollable: detailScroll);
    expect(find.text('同音詞'), findsOneWidget);
    expect(find.textContaining('appel'), findsOneWidget);
    await tester.drag(detailScroll, const Offset(0, -300));
    await tester.pumpAndSettle();
    expect(find.text('apples（複數）'), findsWidgets);
    await tester.scrollUntilVisible(find.text('構詞'), 300,
        scrollable: detailScroll);
    expect(find.text('構詞'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('詞源'), 300,
        scrollable: detailScroll);
    expect(find.text('詞源'), findsOneWidget);
    expect(find.text('更多意思'), findsNothing);
    expect(LexiconPack.instance.byId(1)!.examples.length, 3);
    expect(tester.takeException(), isNull);
  });
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
    await tester.tap(find.text('我的單字本').first);
    await tester.pumpAndSettle();
    expect(find.text('我的單字本'), findsWidgets);
    expect(app.repository.wordCount, original);
    expect(tester.takeException(), isNull);
  });

  testWidgets('no 包含待補齊單字（0） box when the pack has no listable stub',
      (tester) async {
    // The live pack's stubs are all form pointers (redirect_to), which never
    // become list rows (card #227 round 68).
    final data = catalog();
    ((data['lexemes'] as List)[1] as Map)['redirect_to'] = 1;
    LexiconPack.instance.loadJson(data);
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    expect(find.text('apple'), findsOneWidget);
    expect(find.byType(CheckboxListTile), findsNothing);
    expect(find.textContaining('包含待補齊單字'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      '我的單字本 返回 steps back to 資料庫 instead of leaving the tab (問題回報 #258)',
      (tester) async {
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    expect(find.text('資料庫單字本'), findsOneWidget);
    await tester.tap(find.text('我的單字本'));
    await tester.pumpAndSettle();
    expect(find.text('資料庫單字本'), findsNothing);
    await tester.tap(find.bySemanticsLabel('返回'));
    await tester.pumpAndSettle();
    expect(find.text('資料庫單字本'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      '我的相片冊 返回 steps back to 資料庫 instead of leaving the tab (問題回報 #258)',
      (tester) async {
    await pumpApp(tester, initialTab: AppTab.album, databaseLibrary: true);
    expect(find.text('資料庫相片冊'), findsOneWidget);
    await tester.tap(find.text('我的相片冊'));
    await tester.pumpAndSettle();
    expect(find.text('資料庫相片冊'), findsNothing);
    await tester.tap(find.bySemanticsLabel('返回'));
    await tester.pumpAndSettle();
    expect(find.text('資料庫相片冊'), findsOneWidget);
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
    expect(find.text('未分級：apple · 蘋果'), findsOneWidget);
    await tester.tap(find.byType(DatabaseImageTile));
    await tester.pumpAndSettle();
    expect(find.text('已確認'), findsNothing);
    expect(find.text('apple · 蘋果'), findsOneWidget);
    await tester.tap(find.text('apple · 蘋果'));
    await tester.pumpAndSettle();
    expect(find.text('資料庫圖片（1）'), findsOneWidget);
    expect(find.text('蘋果'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
