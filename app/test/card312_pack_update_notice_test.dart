// 問題回報 #300 (card #312): after a dictionary update fills in a word's
// examples or meaning, the 單字本 shows a one-time notice listing those
// words; no change → no notice.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/word_database_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_query.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> pack(String version, {bool examples = false}) => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': version,
      'lexemes': [
        for (final w in ['apple', 'river'])
          {
            'id': w.length,
            'lemma': w,
            'normalized': w,
            'pos': 'noun',
            'status': 'full',
            'cefr': 'A1',
            'senses': [
              {'id': w.length, 'definition': w, 'native': '$w的意思'}
            ],
            if (examples && w == 'apple')
              'examples': [
                {'text': 'I eat an apple.', 'translation': '我吃一顆蘋果。'}
              ],
          }
      ],
    };

/// Records which words were opened (問題回報 #712).
class _Nav implements AppNavigator {
  final opened = <String>[];
  @override
  void openWord(String wordEntryId, {String? occurrenceId}) =>
      opened.add(wordEntryId);
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

WordDatabaseRepository linked() {
  final repo = WordDatabaseRepository();
  repo.addWord(word: 'apple', pos: 'noun', meaning: '');
  repo.addWord(word: 'river', pos: 'noun', meaning: '');
  repo.linkLexicon(LexiconPack.instance..loadJson(pack('v1')));
  return repo;
}

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('a new version that fills examples is recorded; first link is not', () {
    final repo = linked();
    expect(repo.filledByUpdate, isEmpty, reason: 'first link is not an update');
    repo.linkLexicon(
        LexiconPack.instance..loadJson(pack('v2', examples: true)));
    final filled = repo.filledByUpdate;
    expect(filled.length, 1);
    expect(filled.values.single, contains('例句'));
    expect(packUpdateSummary(filled), '詞庫已更新：1 個字補上例句');
    repo.dismissPackUpdateNotice();
    expect(repo.filledByUpdate, isEmpty);
  });

  test('relinking the same version or an update with no gain → no notice', () {
    final repo = linked();
    repo.linkLexicon(LexiconPack.instance);
    repo.linkLexicon(LexiconPack.instance..loadJson(pack('v2')));
    expect(repo.filledByUpdate, isEmpty);
    expect(packUpdateSummary(repo.filledByUpdate), isNull);
  });

  testWidgets('單字本 shows the notice, lists the words, then hides it',
      (tester) async {
    final repo = linked();
    await pumpApp(tester, repository: repo, home: const WordDatabaseScreen());
    expect(find.textContaining('詞庫已更新'), findsNothing);

    repo.linkLexicon(
        LexiconPack.instance..loadJson(pack('v2', examples: true)));
    await tester.pump();
    expect(find.text('詞庫已更新：1 個字補上例句'), findsOneWidget);

    await tester.tap(find.text('詞庫已更新：1 個字補上例句'));
    await tester.pumpAndSettle();
    expect(find.text('補上：例句'), findsOneWidget);
    expect(
        find.descendant(
            of: find.byType(AlertDialog), matching: find.text('apple')),
        findsOneWidget);
    await tester.tap(find.text('知道了'));
    await tester.pumpAndSettle();
    expect(find.textContaining('詞庫已更新'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  // 問題回報 #712: opening one updated word used to end the notice, so the
  // other updated words could not be found again.
  testWidgets('the list stays after opening a word until 知道了', (tester) async {
    final repo = WordDatabaseRepository();
    for (final w in ['apple', 'river']) {
      repo.addWord(word: w, pos: 'noun', meaning: '');
    }
    repo.linkLexicon(LexiconPack.instance..loadJson(pack('v1')));
    final app = await pumpApp(tester,
        repository: repo,
        home: const WordDatabaseScreen(),
        size: const Size(375, 812));
    final nav = _Nav();
    app.navigator.target = nav;
    final v2 = pack('v2', examples: true);
    for (final l in v2['lexemes'] as List) {
      l['examples'] = [
        {'text': 'A ${l['lemma']} here.', 'translation': '這裡。'}
      ];
    }
    repo.linkLexicon(LexiconPack.instance..loadJson(v2));
    await tester.pump();
    const summary = '詞庫已更新：2 個字補上例句';
    expect(find.text(summary), findsOneWidget);

    Finder inList(String w) =>
        find.descendant(of: find.byType(AlertDialog), matching: find.text(w));
    await tester.tap(find.text(summary));
    await tester.pumpAndSettle();
    await tester.tap(inList('apple'));
    await tester.pumpAndSettle();
    expect(nav.opened, [repo.entries.firstWhere((e) => e.word == 'apple').id]);
    // Still there, with both words.
    expect(find.text(summary), findsOneWidget);
    expect(repo.filledByUpdate.length, 2);

    await tester.tap(find.text(summary));
    await tester.pumpAndSettle();
    await tester.tap(inList('river'));
    await tester.pumpAndSettle();
    expect(nav.opened.length, 2);
    expect(find.text(summary), findsOneWidget);

    // Tapping outside the list is not 知道了 either.
    await tester.tap(find.text(summary));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text(summary), findsOneWidget);

    // Leaving the 單字本 keeps it too.
    await tester.pumpWidget(const SizedBox());
    expect(repo.filledByUpdate.length, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('closing the notice ends it', (tester) async {
    final repo = linked();
    await pumpApp(tester, repository: repo, home: const WordDatabaseScreen());
    repo.linkLexicon(
        LexiconPack.instance..loadJson(pack('v2', examples: true)));
    await tester.pump();
    await tester.tap(find.bySemanticsLabel('關閉提示'));
    await tester.pump();
    expect(find.textContaining('詞庫已更新'), findsNothing);
    expect(repo.filledByUpdate, isEmpty);
  });
}
