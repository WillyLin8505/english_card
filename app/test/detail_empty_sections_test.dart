import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// 單字本、複習模擬: 單字詳情不可出現空白標題 — a 詞性與意思 title with nothing
// under it, a part of speech with no Chinese, a stub's empty sections, and an
// add button that only says 「已在單字本」 after a tap.
void main() {
  setUp(() => LexiconPack.instance.loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          {'id': 1, 'lemma': 'cigarette', 'normalized': 'cigarette',
           'pos': 'noun', 'status': 'full', 'cefr': 'A2',
           'senses': [{'id': 10, 'definition': 'A small cigar.', 'native': '香煙'}]},
          {'id': 2, 'lemma': 'cigarette', 'normalized': 'cigarette',
           'pos': 'verb', 'status': 'full', 'cefr': 'C2', 'rare_usage': true,
           'senses': [{'id': 20, 'definition': 'To give a cigarette.',
                       'native': null, 'labels': ['rare', 'slang']}]},
          {'id': 3, 'lemma': 'zorbing', 'normalized': 'zorbing',
           'pos': 'unknown', 'status': 'stub', 'senses': []},
          {'id': 4, 'lemma': 'bulletin', 'normalized': 'bulletin',
           'pos': 'noun', 'status': 'full',
           'senses': [{'id': 40, 'definition': 'A short report.', 'native': '公告'}]},
        ],
      }));
  tearDown(LexiconPack.instance.clear);

  Future<void> open(WidgetTester tester, int id) async {
    tester.state<NavigatorState>(find.byType(Navigator).last)
        .push(MaterialPageRoute(builder: (_) => DatabaseWordScreen(wordId: id)));
    await tester.pumpAndSettle();
  }

  FilledButton addButton(WidgetTester tester) =>
      tester.widget<FilledButton>(find.byKey(const ValueKey('database-add')));

  testWidgets('a part of speech without Chinese is left out whole (cigarette 動詞)',
      (tester) async {
    await pumpApp(tester);
    await open(tester, 2);
    expect(find.text('詞性與意思'), findsOneWidget);
    expect(find.text('名詞'), findsOneWidget);
    expect(find.text('香煙'), findsOneWidget);
    // Only the header names 動詞; no bare 動詞 chip in the section.
    expect(find.text('動詞'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a stub has no empty title, no empty photo section and says it is pending',
      (tester) async {
    await pumpApp(tester);
    await open(tester, 3);
    expect(find.text('zorbing'), findsOneWidget);
    expect(find.text('詞性與意思'), findsNothing);
    expect(find.textContaining('其他詞性'), findsNothing);
    expect(find.textContaining('資料庫圖片'), findsNothing);
    expect(find.text('資料庫尚未加入這個單字的圖片'), findsNothing);
    expect(find.text('這個字還在補齊資料'), findsOneWidget);
    expect(find.text('加入單字本（中文補齊後排進複習）'), findsOneWidget);
    expect(find.text('加入我的單字本與複習'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a full word without photos shows one muted line, not 資料庫圖片（0）',
      (tester) async {
    await pumpApp(tester);
    await open(tester, 4);
    expect(find.textContaining('資料庫圖片'), findsNothing);
    expect(find.text('資料庫尚未加入這個單字的圖片'), findsOneWidget);
    expect(find.text('這個字還在補齊資料'), findsNothing);
    expect(find.text('加入我的單字本與複習'), findsOneWidget);
  });

  testWidgets('a word already in 我的單字本 says so before any tap', (tester) async {
    final app = await pumpApp(tester);
    app.repository.addWord(word: 'cigarette', pos: 'noun', meaning: '香煙');
    await open(tester, 1);
    expect(find.text('已在我的單字本 ✓'), findsOneWidget);
    expect(addButton(tester).onPressed, isNull);
    expect(find.text('加入我的單字本與複習'), findsNothing);
  });

  testWidgets('the add button turns into 已在我的單字本 ✓ once added', (tester) async {
    await pumpApp(tester);
    await open(tester, 4);
    expect(addButton(tester).onPressed, isNotNull);
    await tester.ensureVisible(find.text('加入我的單字本與複習'));
    await tester.tap(find.text('加入我的單字本與複習'));
    await tester.pump();
    expect(find.text('已在我的單字本 ✓'), findsOneWidget);
    expect(addButton(tester).onPressed, isNull);
  });

  testWidgets('my word detail: no 詞性與意思 title when no part of speech has a meaning',
      (tester) async {
    final entry = WordEntry(
        id: 'unable',
        word: 'unable',
        pos: 'adj',
        meaning: '',
        createdAt: testNow,
        updatedAt: testNow,
        usages: const [
          LexemeUsage(id: 'a', pos: 'adj', senses: [WordSense(id: 'a1', meaning: '')]),
          LexemeUsage(id: 'i', pos: 'intj', senses: [WordSense(id: 'i1', meaning: ' ')]),
        ]);
    final repo = WordDatabaseRepository(entries: [entry], clock: () => testNow);
    await pumpApp(tester,
        repository: repo, home: const WordDetailScreen(wordEntryId: 'unable'));
    expect(find.text('詞性與意思'), findsNothing);
    expect(find.text('感嘆詞'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('my word detail: a part of speech without meaning is hidden (shop 感嘆詞)',
      (tester) async {
    final entry = WordEntry(
        id: 'shop',
        word: 'shop',
        pos: 'noun',
        meaning: '商店',
        createdAt: testNow,
        updatedAt: testNow,
        usages: const [
          LexemeUsage(id: 'n', pos: 'noun', senses: [WordSense(id: 'n1', meaning: '商店')]),
          LexemeUsage(id: 'v', pos: 'verb', senses: [WordSense(id: 'v1', meaning: '購物')]),
          LexemeUsage(id: 'i', pos: 'intj', senses: [WordSense(id: 'i1', meaning: '')]),
        ]);
    final repo = WordDatabaseRepository(entries: [entry], clock: () => testNow);
    await pumpApp(tester,
        repository: repo, home: const WordDetailScreen(wordEntryId: 'shop'));
    expect(find.text('詞性與意思'), findsOneWidget);
    expect(find.text('名詞'), findsOneWidget);
    expect(find.text('動詞'), findsOneWidget);
    expect(find.text('感嘆詞'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
