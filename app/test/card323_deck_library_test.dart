import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/screens/deck_browser_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// 卡片集／圖片集 (card #323, 問題回報 #320): browse, add, use offline, remove.
void main() {
  final wordsDeck = {
    'slug': 'basic', 'kind': 'words', 'title': '基礎單字', 'cefr': 'A1',
    'topic': '日常', 'author': '編輯部', 'count': 2, 'description': '日常用字',
    'items': [
      {'word': 'Apple', 'pos': 'noun', 'cefr': 'A1'},
      {'word': 'happy', 'pos': 'adjective', 'cefr': 'A1'},
    ],
  };
  final photosDeck = {
    'slug': 'fruit', 'kind': 'photos', 'title': '水果相片冊', 'cefr': 'B1',
    'count': 1, 'cover_asset_id': 7,
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

  MockClient server({bool imagesOk = true}) => MockClient((req) async {
        final path = req.url.path;
        if (path == '/api/decks') {
          return json({
            'decks': [
              {...wordsDeck}..remove('items'),
              {...photosDeck}..remove('items'),
            ]
          });
        }
        if (path == '/api/decks/basic') {
          return json(wordsDeck);
        }
        if (path == '/api/decks/fruit') {
          return json(photosDeck);
        }
        if (path == '/api/image') {
          return imagesOk
              ? http.Response.bytes(Uint8List.fromList([1, 2, 3, 4]), 200)
              : http.Response('', 404);
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

  test('a word deck adds words with cards, and removing it takes them out',
      () async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final (repo, intake) = env();
    final list = await lib.fetchList();
    expect(list.map((d) => d.slug), ['basic', 'fruit']);

    final created = await lib.install(await lib.fetchDeck('basic'),
        repository: repo, intake: intake);
    expect(created.map((e) => e.word), ['apple', 'happy']);
    expect(repo.entryByWord('happy')!.pos, 'adj.');
    expect(repo.cardOf(repo.entryByWord('apple')!.id), isNotNull);
    expect(lib.installedDeck('basic'), isNotNull);

    await lib.remove('basic', repo);
    expect(repo.entryByWord('apple'), isNull);
    expect(lib.installedDeck('basic'), isNull);
  });

  test('words already in the database are kept when the deck is removed',
      () async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final (repo, intake) = env();
    repo.addWord(word: 'apple', pos: 'noun', meaning: '蘋果');
    final created = await lib.install(await lib.fetchDeck('basic'),
        repository: repo, intake: intake);
    expect(created.map((e) => e.word), ['happy']);
    await lib.remove('basic', repo);
    expect(repo.entryByWord('apple'), isNotNull);
    expect(repo.entryByWord('happy'), isNull);
  });

  test('a picture deck downloads the picture and saves its labels', () async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final (repo, intake) = env();
    final created = await lib.install(await lib.fetchDeck('fruit'),
        repository: repo, intake: intake);
    expect(created.map((e) => e.word).toSet(), {'tomato', 'ripe'});
    final photo = repo.photos.single;
    expect(photo.title, '水果相片冊');
    expect(repo.activeLabels(photo.id).length, 2);
    expect(await intake.bytesOf(photo), isNotNull);

    await lib.remove('fruit', repo);
    expect(repo.photos, isEmpty);
    expect(repo.entryByWord('tomato'), isNull);
  });

  test('a picture that cannot be fetched leaves nothing behind', () async {
    final lib = DeckLibrary(client: server(imagesOk: false), remote: true, persist: false);
    final (repo, intake) = env();
    await expectLater(
        lib.install(await lib.fetchDeck('fruit'),
            repository: repo, intake: intake),
        throwsA(isA<DeckException>()));
    expect(repo.photos, isEmpty);
    expect(lib.installedDeck('fruit'), isNull);
  });

  test('offline: the list fails clearly, installed decks keep working',
      () async {
    final online = DeckLibrary(client: server(), remote: true, persist: false);
    final (repo, intake) = env();
    await online.install(await online.fetchDeck('basic'),
        repository: repo, intake: intake);
    final offline = DeckLibrary(
        client: MockClient((_) async => throw http.ClientException('offline')),
        remote: true, persist: false);
    await expectLater(offline.fetchList(), throwsA(isA<DeckException>()));
    expect(repo.entryByWord('apple'), isNotNull);
    expect(online.installed.single.info.title, '基礎單字');
  });

  testWidgets('the 相片冊 screen lists decks and adds one', (tester) async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    final app = await pumpApp(tester,
        home: DeckBrowserScreen(library: lib), size: const Size(402, 1200));
    await settle(tester);
    expect(find.text('基礎單字'), findsOneWidget);
    expect(find.text('水果相片冊'), findsOneWidget);
    expect(find.textContaining('B1'), findsOneWidget);

    await tester.tap(find.text('加入').first);
    await settle(tester, rounds: 5);
    expect(app.repository.entryByWord('apple'), isNotNull);
    expect(find.text('移除'), findsOneWidget);
  });

  testWidgets('offline, the screen shows the error but keeps installed decks',
      (tester) async {
    final lib = DeckLibrary(
        client: MockClient((_) async => throw http.ClientException('offline')),
        remote: true, persist: false);
    await pumpApp(tester, home: DeckBrowserScreen(library: lib));
    await settle(tester);
    expect(find.textContaining('無法連線'), findsOneWidget);
    expect(find.text('重試'), findsOneWidget);
  });
}
