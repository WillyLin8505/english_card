import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/deck_browser_screen.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// 問題回報 #440: the 卡片集 download entry lives on the 相片冊 tab, a
/// downloaded deck is one tile in its grid, and 複習 opens on a grid of
/// books (綜合 first) instead of a dropdown or picker.
void main() {
  final deck = {
    'slug': 'fruit', 'kind': 'photos', 'title': '水果相片冊', 'cefr': 'B1',
    'author': '編輯部', 'count': 1, 'cover_asset_id': 7,
    'items': [
      {
        'asset_id': 7,
        'labels': [
          {'word': 'tomato', 'pos': 'noun', 'cefr': 'A2', 'point': [0.4, 0.5]},
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
              {...deck}..remove('items')
            ]
          });
        }
        if (path == '/api/decks/fruit') return json(deck);
        if (path == '/api/image') {
          return http.Response.bytes(Uint8List.fromList([1, 2, 3, 4]), 200);
        }
        return http.Response('', 404);
      });

  testWidgets('相片冊 has a 下載相片冊 tile, and the downloaded deck appears',
      (tester) async {
    final lib = DeckLibrary(client: server(), remote: true, persist: false);
    DeckLibrary.instance = lib;
    await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1200));
    await tester.pumpAndSettle();
    expect(find.text('＋ 下載相片冊'), findsOneWidget);

    await tester.tap(find.text('＋ 下載相片冊'));
    await tester.pumpAndSettle();
    expect(find.byType(DeckBrowserScreen), findsOneWidget);
    await tester.tap(find.text('加入相片冊'));
    await tester.pumpAndSettle();
    Navigator.of(tester.element(find.byType(DeckBrowserScreen))).pop();
    await tester.pumpAndSettle();
    expect(find.text('水果相片冊'), findsOneWidget);
    expect(find.textContaining('相片冊 · 編輯部'), findsOneWidget);
  });

  testWidgets('單字本 no longer links to 相片冊', (tester) async {
    await pumpApp(tester, initialTab: AppTab.words);
    await tester.pumpAndSettle();
    expect(find.textContaining('相片冊：下載'), findsNothing);
  });

  testWidgets('複習 opens on a grid: 綜合 first, no dropdown; a tile starts',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.review,
        repository: WordDatabaseRepository(clock: () => testNow));
    final w = app.repository.addWord(
        word: 'banana', pos: 'n.', meaning: '香蕉', level: 'A1');
    app.repository.applyWordData(w.id, status: WordDataStatus.complete);
    await tester.pumpAndSettle();

    expect(find.byType(DropdownButton), findsNothing);
    expect(find.byType(DropdownButtonFormField), findsNothing);
    expect(find.text('綜合'), findsOneWidget);
    expect(find.textContaining('今天'), findsWidgets);

    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    final screen = tester.widget<FlashcardScreen>(find.byType(FlashcardScreen));
    expect(screen.albumId, isNull);
    expect(app.settings.reviewScope, 'all');
    expect(find.text('綜合'), findsNothing); // the run began; grid is gone
  });
}
