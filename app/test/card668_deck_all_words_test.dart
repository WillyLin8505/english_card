// 問題回報 #668: a 單字集 whose words were mostly in the 單字本 already showed
// "4 個單字" — InstalledDeck kept only the words its install created. It now
// remembers all of its words; 移除集合 still deletes only the created ones.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  const info = DeckInfo(
      slug: 'basic-3000-c2', kind: 'words', title: '基礎 3000 字・C2', count: 2);
  const deck = DeckContent(info, words: [
    (word: 'Apple', pos: 'noun', level: 'A1'),
    (word: 'kite', pos: 'noun', level: 'A2'),
  ]);

  (WordDatabaseRepository, PhotoIntake) env() {
    final repo = WordDatabaseRepository(clock: () => testNow);
    return (
      repo,
      PhotoIntake(repository: () => repo, photoStore: PhotoStore.inMemory())
    );
  }

  test('a deck counts and reviews the words that were in the 單字本 already',
      () async {
    final (repo, intake) = env();
    final apple = repo.addWord(word: 'apple', pos: 'n.', meaning: '蘋果');
    final lib = DeckLibrary(remote: false, persist: false);
    final created = await lib.install(deck, repository: repo, intake: intake);
    expect(created.map((e) => e.word), ['kite']);

    final installed = lib.installedDeck('basic-3000-c2')!;
    expect(installed.wordEntryIds, hasLength(1));
    expect(installed.wordCount, 2);
    final kite = repo.entryByWord('kite')!;
    expect(installed.entryIds(repo).toSet(), {apple.id, kite.id});
    expect(deckCardIds(repo, installed),
        {repo.cardOf(apple.id)!.id, repo.cardOf(kite.id)!.id});

    // Saved and read back with the full list.
    final again = InstalledDeck.fromJson(
        jsonDecode(jsonEncode(installed.toJson())) as Map<String, dynamic>);
    expect(again.words, ['apple', 'kite']);

    await lib.remove('basic-3000-c2', repo);
    expect(repo.entryByWord('apple'), isNotNull);
    expect(repo.entryByWord('kite'), isNull);
  });

  test('an install saved before the word list gets it from the server',
      () async {
    final (repo, _) = env();
    final apple = repo.addWord(word: 'apple', pos: 'n.', meaning: '蘋果');
    final kite = repo.addWord(word: 'kite', pos: 'n.', meaning: '風箏');
    final legacy = jsonEncode([
      {
        'info': info.toJson(),
        'installedAt': testNow.toIso8601String(),
        'photoIds': <String>[],
        'wordEntryIds': [kite.id],
        'albumId': null,
      }
    ]);

    // Offline: it keeps going by the words it created.
    final offline = DeckLibrary(
        client: MockClient((_) async => throw http.ClientException('offline')),
        remote: true,
        persist: false)
      ..restoreForTest('en', legacy);
    await offline.fillDeckWords('en');
    final old = offline.installedDeck('basic-3000-c2')!;
    expect(old.words, isNull);
    expect(old.wordCount, 1);
    expect(old.entryIds(repo), [kite.id]);

    final lib = DeckLibrary(
        client: MockClient((req) async {
          expect(req.url.path, '/api/decks/basic-3000-c2');
          return http.Response.bytes(
              utf8.encode(jsonEncode({
                ...info.toJson(),
                'items': [
                  {'word': 'Apple', 'pos': 'noun', 'cefr': 'A1'},
                  {'word': 'kite', 'pos': 'noun', 'cefr': 'A2'},
                ],
              })),
              200);
        }),
        remote: true,
        persist: false)
      ..restoreForTest('en', legacy);
    await lib.fillDeckWords('en');
    final filled = lib.installedDeck('basic-3000-c2')!;
    expect(filled.words, ['apple', 'kite']);
    expect(filled.wordCount, 2);
    expect(filled.wordEntryIds, [kite.id]);
    expect(deckCardIds(repo, filled),
        {repo.cardOf(apple.id)!.id, repo.cardOf(kite.id)!.id});
  });
}
