import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/widgets/mobile/tab_bar.dart';

import 'helpers.dart';

/// 問題回報 #307: 學習洞察's weak words open their details, and
/// 「複習這些字」 starts a run with them first.
void main() {
  test('a focus run shows the asked cards first, in order', () {
    final repo = testRepository();
    final ids = [
      for (final c in repo.eligibleCards(includeFuture: true)) c.id
    ].reversed.take(3).toList();
    final s = FlashcardSession(repo, continuous: true, focus: ids);
    addTearDown(s.dispose);
    final shown = <String>[];
    for (var i = 0; i < 3; i++) {
      shown.add(s.card!.id);
      s.showAnswer();
      s.rate(Rating.good);
    }
    expect(shown, ids);
  });

  testWidgets('weak words open details and 複習這些字 starts a run',
      (tester) async {
    final repo = testRepository();
    final card = repo.eligibleCards().first;
    repo.review(card.id, Rating.again);
    repo.review(card.id, Rating.again);
    final app = await pumpApp(tester,
        initialTab: AppTab.settings, repository: repo);
    await tester.pumpAndSettle();

    final note = find.text('複習 2 次，忘了 2 次');
    await tester.scrollUntilVisible(note, 300,
        scrollable: find.byType(Scrollable).first);
    // Clear of the tab bar.
    await Scrollable.ensureVisible(tester.element(note), alignment: 0.5);
    await tester.pumpAndSettle();
    expect(find.text('還沒有常按「忘記」或「吃力」的字。'), findsNothing);

    await tester.tap(note);
    await tester.pumpAndSettle();
    expect(find.byType(WordDetailScreen), findsOneWidget);
    expect(
        tester
            .widget<WordDetailScreen>(find.byType(WordDetailScreen))
            .wordEntryId,
        card.wordEntryId);
    Navigator.of(tester.element(find.byType(WordDetailScreen))).pop();
    await tester.pumpAndSettle();

    await tester.tap(find.text('複習這些字'));
    await tester.pumpAndSettle();
    // A run is going on in the 複習 tab: the tab bar hides (問題回報 #101).
    expect(find.byType(MobileTabBar), findsNothing);
    expect(app.navigator.target, isNotNull);
  });
}
