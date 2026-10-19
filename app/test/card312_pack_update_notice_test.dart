// 問題回報 #300 (card #312): after a dictionary update fills in a word's
// examples or meaning, the 單字本 shows a one-time notice listing those
// words; no change → no notice.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
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
    repo.linkLexicon(LexiconPack.instance..loadJson(pack('v2', examples: true)));
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
    await pumpApp(tester,
        repository: repo, home: const WordDatabaseScreen());
    expect(find.textContaining('詞庫已更新'), findsNothing);

    repo.linkLexicon(LexiconPack.instance..loadJson(pack('v2', examples: true)));
    await tester.pump();
    expect(find.text('詞庫已更新：1 個字補上例句'), findsOneWidget);

    await tester.tap(find.text('詞庫已更新：1 個字補上例句'));
    await tester.pumpAndSettle();
    expect(find.text('補上：例句'), findsOneWidget);
    expect(find.descendant(of: find.byType(AlertDialog), matching: find.text('apple')),
        findsOneWidget);
    await tester.tap(find.text('知道了'));
    await tester.pumpAndSettle();
    expect(find.textContaining('詞庫已更新'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
