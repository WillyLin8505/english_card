import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/interest_topics.dart';
import 'helpers.dart';

DeckInfo _deck(String slug, String title, String? topic) =>
    DeckInfo(slug: slug, kind: 'words', title: title, topic: topic, count: 1);

void main() {
  testWidgets('goals and interests are chosen on small screen without overflow',
      (tester) async {
    tester.view.physicalSize = const Size(375, 667);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OnboardingResult? result;
    await tester.pumpWidget(MaterialApp(
        home: OnboardingScreen(
            lexicon: testLexicon(), onDone: (r) => result = r)));
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('熟練'));
    await tester.pump();
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('旅行'));
    await tester.tap(find.text('工作'));
    await tester.pump();
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('食物'));
    await tester.tap(find.text('動物'));
    await tester.pump();
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('開始使用'));
    expect(result!.goals, ['travel', 'work']);
    expect(result!.interests, ['food', 'animal']);
    expect(result!.level, 'B2');
  });

  test('decks matching the interests come first, others keep their order', () {
    final decks = [
      _deck('a', '基礎 3000 字', '基礎單字'),
      _deck('b', '水果與蔬菜相片冊', '食物'),
      _deck('c', '進階單字・C1', '進階單字'),
    ];
    expect(sortByInterests(decks, const ['food']).map((d) => d.slug),
        ['b', 'a', 'c']);
    expect(sortByInterests(decks, const ['advanced']).map((d) => d.slug),
        ['c', 'a', 'b']);
    expect(sortByInterests(decks, const []).map((d) => d.slug), ['a', 'b', 'c']);
  });
}
