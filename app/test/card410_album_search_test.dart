import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

/// 問題回報 #396: the 資料庫相片冊 search matched letters anywhere in a label
/// (cat → category, scatter). Decision: whole words first, then words that
/// start with the search (cats, catch); letters inside a word don't match.
Map<String, dynamic> lexeme(int id, String lemma, String native,
        {String cefr = 'A1'}) =>
    {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': 'noun',
      'status': 'full',
      'cefr': cefr,
      'senses': [
        {'id': id * 10, 'native': native, 'definition': lemma}
      ]
    };

Map<String, dynamic> image(int id, List<int> lexemes) => {
      'id': id,
      'url': 'http://127.0.0.1/api/image?id=$id',
      'tags': [
        for (final l in lexemes)
          {'lexeme_id': l, 'sense_id': l * 10, 'review_status': 'approved'}
      ],
      'labels': [
        for (final l in lexemes)
          {'word': 'w$l', 'point': [0.5, 0.4], 'lexeme_id': l}
      ],
    };

Map<String, dynamic> catalog() => {
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        lexeme(1, 'bobcat', '山貓'),
        lexeme(2, 'scatter', '散布'),
        lexeme(3, 'catch', '接住'),
        lexeme(4, 'cat', '貓'),
        lexeme(5, 'panda', '熊貓'),
        lexeme(6, 'cat food', '貓食'),
        lexeme(7, 'card', '卡片', cefr: 'B1'),
      ],
      'catalog_images': [
        image(1, [1]), // bobcat: cat is inside the word
        image(2, [2]), // scatter: no match
        image(3, [3]), // catch: starts with cat
        image(4, [4]), // cat: whole word
        image(5, [5]),
        image(6, [6, 3]),
        image(7, [7]),
      ],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson(catalog()));
  tearDown(() => LexiconPack.instance.clear());

  Map<String, dynamic> img(int i) =>
      (catalog()['catalog_images'] as List)[i - 1] as Map<String, dynamic>;

  test('whole word, then word start, never letters inside a word', () {
    final pack = LexiconPack.instance;
    int? m(int i, String q) => databaseImageMatch(img(i), pack, q);
    expect(m(1, 'cat'), isNull);
    expect(m(2, 'cat'), isNull);
    expect(m(3, 'cat'), 1);
    expect(m(4, 'cat'), 0);
    expect(m(4, ' CAT '), 0);
    // A word of a phrase counts as a whole word.
    expect(m(6, 'cat'), 0);
    expect(m(6, 'cat food'), 0);
    expect(m(6, 'cat f'), 1);
    expect(m(6, 'food'), 0);
    // Chinese: the meaning or its start, not a character in the middle.
    expect(m(4, '貓'), 0);
    expect(m(6, '貓'), 1);
    expect(m(5, '貓'), isNull);
    expect(m(1, '貓'), isNull);
    expect(m(1, ''), 0);
  });

  test('the level hint names the whole-word hit first', () {
    final pack = LexiconPack.instance;
    expect(databaseSearchHits(img(6), pack, 'cat').map((h) => h.$1),
        ['cat food', 'catch']);
    expect(databaseSearchHits(img(1), pack, 'cat'), isEmpty);
    // card starts with "car" (listed after whole words); "ar" is inside it.
    expect(databaseSearchHits(img(7), pack, 'car').map((h) => h.$1), ['card']);
    expect(databaseSearchHits(img(7), pack, 'ar'), isEmpty);
  });

  testWidgets('the album lists whole-word pictures before word starts',
      (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.album,
        databaseLibrary: true,
        size: const Size(360, 740));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'cat');
    await tester.pumpAndSettle();
    final tiles = tester
        .widgetList<DatabaseImageTile>(find.byType(DatabaseImageTile))
        .map((t) => t.image['id'])
        .toList();
    // Visible tiles (the grid may lazily build only the first ones).
    expect(tiles, isNotEmpty);
    expect(tiles.contains(1) || tiles.contains(2), isFalse);
    expect(tiles.take(2), [4, 6]);
    expect(tester.takeException(), isNull);
  });
}
