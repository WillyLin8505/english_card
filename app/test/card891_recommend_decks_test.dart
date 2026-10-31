import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/screens/recommended_decks_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/interest_topics.dart';

import 'helpers.dart';

DeckInfo _deck(String slug, String title, String topic,
        {String cefr = 'A1', int count = 100}) =>
    DeckInfo(
        slug: slug,
        kind: 'words',
        title: title,
        topic: topic,
        cefr: cefr,
        count: count);

void main() {
  final basics = [
    _deck('b-a1', '基礎 3000 字・A1', '基礎單字', count: 805),
    _deck('b-b2', '基礎 3000 字・B2', '基礎單字', cefr: 'B2', count: 358),
    _deck('adv', '進階單字・C1', '進階單字', cefr: 'C1', count: 400),
  ];
  final sports = _deck('sp', '運動單字', '運動', count: 50);

  test('availableInterests only lists topics that have a deck', () {
    final keys = availableInterests(basics).map((o) => o.$1).toList();
    expect(keys, ['daily', 'advanced']);
    expect(availableInterests([...basics, sports]).map((o) => o.$1),
        contains('sports'));
    expect(availableInterests([...basics, sports]).map((o) => o.$1),
        isNot(contains('hiking')));
  });

  test('recommendDecks: interest first, never empty', () {
    final r = recommendDecks([...basics, sports], interests: ['sports']);
    expect(r.first.slug, 'sp');
    // Nothing matches the interest: basics at the learner's level lead.
    final none = recommendDecks(basics, interests: ['hiking'], level: 'B2');
    expect(none, isNotEmpty);
    expect(none.first.slug, 'b-b2');
    expect(recommendDecks(const []), isEmpty);
  });

  test('goals rank decks when no interest decides', () {
    final r = recommendDecks(basics, goals: ['exam'], level: 'A1');
    expect(r.first.topic, isNotNull);
    expect(r.length, 3);
  });

  testWidgets('onboarding offers only interests with a deck', (tester) async {
    tester.view.physicalSize = const Size(375, 667);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
        home: OnboardingScreen(
            lexicon: testLexicon(),
            onDone: (_) {},
            loadDecks: ({target, native}) async => [...basics, sports])));
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('熟練'));
    await tester.pump();
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    expect(find.text('運動'), findsOneWidget);
    expect(find.text('爬山／戶外活動'), findsNothing);
    expect(find.text('廚房'), findsNothing);
  });

  testWidgets('recommended screen lists decks and adds one in a tap',
      (tester) async {
    final client = MockClient((req) async {
      if (req.url.path == '/api/decks') {
        return http.Response(
            jsonEncode({
              'decks': [for (final d in [...basics, sports]) d.toJson()]
            }),
            200,
            headers: {'content-type': 'application/json'});
      }
      if (req.url.path.startsWith('/api/decks/')) {
        return http.Response(
            jsonEncode({
              ...sports.toJson(),
              'items': [
                {'word': 'run', 'pos': 'verb', 'level': 'A1'}
              ]
            }),
            200,
            headers: {'content-type': 'application/json'});
      }
      return http.Response('', 404);
    });
    final library = DeckLibrary(client: client, remote: true, persist: false);
    await pumpApp(tester,
        size: const Size(375, 667),
        home: RecommendedDecksScreen(
            interests: const ['sports'], library: library));
    await tester.pumpAndSettle();
    expect(find.text('運動單字'), findsOneWidget);
    expect(find.textContaining('50'), findsWidgets);
    expect(find.text('略過'), findsOneWidget);
    await tester.tap(find.text('加入').first);
    await tester.pumpAndSettle();
    expect(find.text('已加入'), findsOneWidget);
    expect(find.text('開始使用'), findsOneWidget);
  });

  testWidgets('offline shows a note and 略過, not a blank page', (tester) async {
    final library = DeckLibrary(remote: false, persist: false);
    await pumpApp(tester,
        home: RecommendedDecksScreen(library: library));
    await tester.pumpAndSettle();
    expect(find.text('重試'), findsOneWidget);
    expect(find.text('略過'), findsOneWidget);
  });
}
