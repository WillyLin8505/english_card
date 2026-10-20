import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

/// 問題回報 #417: the 資料庫單字本 search listed every word with the letters
/// anywhere, alphabetically (rat → accurate, celebrate … rat at #69). Now the
/// word itself comes first, then words that start with the search, then
/// letters inside a word.
Map<String, dynamic> lexeme(int id, String lemma, String native) => {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': 'noun',
      'status': 'full',
      'cefr': 'A1',
      'senses': [
        {'id': id * 10, 'native': native, 'definition': lemma}
      ]
    };

Map<String, dynamic> catalog() => {
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        lexeme(1, 'accurate', '準確的'),
        lexeme(2, 'celebrate', '慶祝'),
        lexeme(3, 'rate', '比率'),
        lexeme(4, 'rat race', '激烈競爭'),
        lexeme(5, 'rat', '老鼠'),
        lexeme(6, 'pen', '筆'),
        lexeme(7, 'pencil', '鉛筆'),
        lexeme(8, 'brush', '筆、刷子'),
      ],
      'catalog_images': [],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson(catalog()));
  tearDown(() => LexiconPack.instance.clear());

  int? rank(int id, String q) => LexiconPack.instance.byId(id)!.searchRank(q);

  test('word itself, a word of it, a word start, letters inside', () {
    expect(rank(5, 'rat'), 0);
    expect(rank(4, 'rat'), 1);
    expect(rank(3, 'rat'), 2);
    expect(rank(1, 'rat'), 3);
    expect(rank(2, 'rat'), 3);
    expect(rank(6, 'rat'), isNull);
    expect(rank(1, ''), 0);
    // Chinese: the meaning, one of its meanings, then a character inside.
    expect(rank(5, '老鼠'), 0);
    expect(rank(6, '筆'), 0);
    expect(rank(8, '筆'), 1);
    expect(rank(7, '筆'), 3);
  });

  testWidgets('the word book lists rat before accurate', (tester) async {
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'rat');
    await tester.pumpAndSettle();
    double y(String text) => tester.getTopLeft(find.text(text).first).dy;
    expect(y('rat'), lessThan(y('rat race')));
    expect(y('rat race'), lessThan(y('rate')));
    expect(y('rate'), lessThan(y('accurate')));
    expect(find.text('pen'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
