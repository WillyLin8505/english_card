import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/flashcard_session.dart';

import 'helpers.dart';

/// 問題回報 #398: 每日上限 defers the rest of the day's cards.
void main() {
  test('daily limits cap the cards offered and count what was done today', () {
    final repo = testRepository();
    final all = repo.eligibleCards();
    expect(all.length, greaterThan(2));
    final capped = repo.eligibleCards(newLimit: 1, reviewLimit: 1);
    final news =
        capped.where((c) => c.fsrs.state == FsrsCardState.newCard).length;
    expect(news, lessThanOrEqualTo(1));
    expect(capped.length, lessThanOrEqualTo(2));
    expect(capped.length, lessThan(all.length));

    final session = FlashcardSession(repo,
        random: math.Random(1), newLimit: 1, reviewLimit: 1);
    var shown = 0;
    while (!session.finished && shown < 20) {
      session.showAnswer();
      session.rate(Rating.good);
      shown++;
    }
    final done = repo.doneToday();
    expect(done.newCards + done.reviews, lessThanOrEqualTo(2));
    expect(repo.eligibleCards(newLimit: 1, reviewLimit: 1)
        .where((c) => c.fsrs.state == FsrsCardState.newCard), isEmpty);
  });
}
