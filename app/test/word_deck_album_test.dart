// 問題回報 #663: a downloaded 單字集 is on the 相片冊 grid and opens the
// lexicon pictures of its words.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/word_deck_photos_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

void main() {
  late DeckLibrary previous;
  setUp(() {
    previous = DeckLibrary.instance;
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'catalog_version': 1,
      'lexemes': [
        {'id': 10, 'lemma': 'zebra', 'normalized': 'zebra', 'pos': 'noun'},
        {'id': 11, 'lemma': 'kite', 'normalized': 'kite', 'pos': 'noun'},
      ],
      'catalog_images': [
        for (final (id, lex) in [(1, 10), (2, 11), (3, 99)])
          {
            'id': id,
            'url': 'assets/sample/photo_kitchen.jpg',
            'width': 100,
            'height': 100,
            'tags': [
              {'lexeme_id': lex, 'sense_id': 1, 'review_status': 'approved'}
            ],
            'labels': const [],
          },
      ],
    });
  });
  tearDown(() {
    DeckLibrary.instance = previous;
    LexiconPack.instance.clear();
  });

  testWidgets('a word set is an album that shows its words\' pictures',
      (tester) async {
    final lib = DeckLibrary(remote: false, persist: false);
    DeckLibrary.instance = lib;
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    await lib.install(
        const DeckContent(
            DeckInfo(
                slug: 'c2', kind: 'words', title: '基礎 3000 字・C2', count: 2),
            words: [
              (word: 'zebra', pos: 'noun', level: 'C2'),
              (word: 'kite', pos: 'noun', level: 'C2'),
            ]),
        repository: app.repository,
        intake:
            AppScope.of(tester.element(find.byType(Scaffold).first)).intake);
    app.repository.linkLexicon(LexiconPack.instance);
    await tester.pumpAndSettle();

    expect(find.text('基礎 3000 字・C2'), findsOneWidget);
    final images = wordDeckImages(
        app.repository, lib.installedDeck('c2')!, LexiconPack.instance);
    expect([for (final i in images) i['id']], [1, 2],
        reason: 'only pictures of the set\'s words');

    await tester.tap(find.text('基礎 3000 字・C2'));
    await tester.pumpAndSettle();
    expect(find.byType(WordDeckPhotosScreen), findsOneWidget);
    expect(find.text('單字集 · 2 個單字 · 2 張詞庫圖片'), findsOneWidget);
  });

  testWidgets('a word set without pictures lists its words (#673)',
      (tester) async {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'catalog_version': 1,
      'lexemes': [
        {'id': 20, 'lemma': 'counsel', 'normalized': 'counsel', 'pos': 'noun'},
        {'id': 21, 'lemma': 'situate', 'normalized': 'situate', 'pos': 'verb'},
      ],
      'catalog_images': const [],
    });
    final lib = DeckLibrary(remote: false, persist: false);
    DeckLibrary.instance = lib;
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    await lib.install(
        const DeckContent(
            DeckInfo(
                slug: 'c2', kind: 'words', title: '基礎 3000 字・C2', count: 2),
            words: [
              (word: 'counsel', pos: 'noun', level: 'C2'),
              (word: 'situate', pos: 'verb', level: 'C2'),
            ]),
        repository: app.repository,
        intake:
            AppScope.of(tester.element(find.byType(Scaffold).first)).intake);
    await tester.pumpAndSettle();
    await tester.tap(find.text('基礎 3000 字・C2'));
    await tester.pumpAndSettle();
    expect(find.text('這 2 個字在詞庫裡還沒有圖片，可以先看單字'), findsOneWidget);
    expect(find.byKey(const ValueKey('deck-word-counsel')), findsOneWidget);
    expect(find.byKey(const ValueKey('deck-word-situate')), findsOneWidget);
  });
}
