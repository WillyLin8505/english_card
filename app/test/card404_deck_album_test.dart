import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/screens/deck_browser_screen.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';
import 'review_database_photos_test.dart' show pack;

/// Deck words wait for their meanings (the enricher's job) before they
/// can be reviewed.
void giveMeanings(WordDatabaseRepository repo) {
  for (final w in ['tomato', 'ripe']) {
    final e = repo.entryByWord(w)!;
    repo.editEntry(e.copyWith(meaning: '$w 的意思'), {'meaning'});
  }
}

/// 圖片集 → 相片冊 (問題回報 #403, card #404): a downloaded picture deck is
/// its own album, opens from the album, can be reviewed on its own, and
/// goes with the deck when the deck is removed.
void main() {
  final photosDeck = {
    'slug': 'fruit', 'kind': 'photos', 'title': '水果相片冊', 'cefr': 'B1',
    'author': '編輯部', 'count': 1, 'cover_asset_id': 7,
    'items': [
      {
        'asset_id': 7,
        'labels': [
          {'word': 'tomato', 'pos': 'noun', 'cefr': 'A2', 'point': [0.4, 0.5]},
          {'word': 'ripe', 'pos': 'adjective', 'cefr': 'B1', 'point': [0.6, 0.2]},
        ],
      }
    ],
  };

  http.Response json(Object body) => http.Response.bytes(
      utf8.encode(jsonEncode(body)), 200,
      headers: {'content-type': 'application/json; charset=utf-8'});

  MockClient server() => MockClient((req) async {
        final path = req.url.path;
        if (path == '/api/decks') {
          return json({
            'decks': [
              {...photosDeck}..remove('items'),
            ]
          });
        }
        if (path == '/api/decks/fruit') return json(photosDeck);
        if (path == '/api/image') {
          return http.Response.bytes(Uint8List.fromList([1, 2, 3, 4]), 200);
        }
        return http.Response('', 404);
      });

  (WordDatabaseRepository, PhotoIntake) env() {
    final repo = WordDatabaseRepository(clock: () => testNow);
    return (
      repo,
      PhotoIntake(repository: () => repo, photoStore: PhotoStore.inMemory())
    );
  }

  test('installing a picture deck makes its own album holding its pictures',
      () async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final (repo, intake) = env();
    await lib.install(await lib.fetchDeck('fruit'),
        repository: repo, intake: intake);

    final albumId = lib.installedDeck('fruit')!.albumId!;
    final album = repo.album(albumId)!;
    expect(album.name, '水果相片冊');
    expect(album.deckSlug, 'fruit');
    expect(album.author, '編輯部');
    expect(repo.photosInAlbum(albumId).single.title, '水果相片冊');
    expect(repo.albumWordCount(albumId), 2);
  });

  test('removing the deck removes its album, and the words it added',
      () async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final (repo, intake) = env();
    await lib.install(await lib.fetchDeck('fruit'),
        repository: repo, intake: intake);
    final albumId = lib.installedDeck('fruit')!.albumId!;

    await lib.remove('fruit', repo);
    expect(repo.album(albumId), isNull);
    expect(repo.albums, isEmpty);
    expect(repo.photos, isEmpty);
    expect(repo.entryByWord('tomato'), isNull);
  });

  test('a review run for one album only draws that album\'s words', () async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final (repo, intake) = env();
    await lib.install(await lib.fetchDeck('fruit'),
        repository: repo, intake: intake);
    final albumId = lib.installedDeck('fruit')!.albumId!;
    giveMeanings(repo);
    // Own word, not on any album photo.
    repo.addWord(word: 'apple', pos: 'noun', meaning: '蘋果');

    final lexicon = pack([]);
    final session = FlashcardSession(repo,
        lexicon: lexicon, random: Random(1), continuous: true, albumId: albumId);
    final albumWords = {
      for (final c in repo.cardIdsInAlbum(albumId))
        repo.card(c)!.wordEntryId,
    };
    expect(albumWords, hasLength(2));

    final seen = <String>{};
    for (var i = 0; i < 6 && !session.finished; i++) {
      final id = session.card!.wordEntryId;
      seen.add(repo.entry(id)!.word);
      expect(albumWords, contains(id));
      session.rate(Rating.good);
    }
    expect(seen, isNotEmpty);
    expect(seen.difference({'tomato', 'ripe'}), isEmpty);
    session.dispose();
  });

  testWidgets('download → 相片冊 → open the album → review only this album',
      (tester) async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final app = await pumpApp(tester,
        home: DeckBrowserScreen(library: lib), size: const Size(402, 1200));
    await settle(tester);

    await tester.tap(find.text('加入相片冊'));
    await settle(tester, rounds: 5);
    giveMeanings(app.repository);
    // pumpApp brings the sample albums along; the deck's one is the new one.
    final deckAlbum = app.repository.albums.singleWhere(
        (a) => a.deckSlug == 'fruit');
    expect(deckAlbum.name, '水果相片冊');
    expect(find.text('已在相片冊'), findsOneWidget);

    await tester.tap(find.text('開啟相簿'));
    await settle(tester, rounds: 5);
    expect(find.text('水果相片冊'), findsWidgets);
    expect(find.text('複習這本相簿'), findsOneWidget);
    // A pointer tap on this button did not reach its GestureDetector in the
    // test harness (cause not pinned down), so the button's own handler runs
    // here instead; the handler, which pushes the review, is what is tested.
    final review = find.ancestor(
        of: find.text('複習這本相簿'), matching: find.byType(Tap));
    tester.widget<Tap>(review).onTap!();
    await settle(tester, rounds: 5);
    final session = tester.widget<FlashcardScreen>(find.byType(FlashcardScreen));
    expect(session.albumId, deckAlbum.id);
    expect(find.text('開始複習'), findsOneWidget);
  });
}
