import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/flashcard_session.dart';

import 'helpers.dart';

/// Card #303 / 問題回報 #315: a few words the learner keeps grading Again
/// must not take over the run. Before the fix every due Again card was
/// served before any fresh card, so three forgotten words refilled the
/// queue every [FlashcardSession.againGap] steps and 40 continuous draws
/// showed only those 3 words (pot、fresh、brick、ocean 一直輪).
void main() {
  /// 50 saved words, continuous review, [hardCount] of the first words
  /// shown are graded Again every time, the rest Good.
  List<String> run(int hardCount, {int draws = 40, int seed = 3}) {
    final repo = testRepository();
    for (var i = repo.entries.length; i < 50; i++) {
      repo.addWord(word: 'word$i', pos: 'noun', meaning: '字$i');
    }
    expect(repo.eligibleCards(includeFuture: true), hasLength(50));
    final session =
        FlashcardSession(repo, continuous: true, random: math.Random(seed));
    addTearDown(session.dispose);
    final hard = <String>{};
    final seen = <String>[];
    for (var step = 0; step < draws; step++) {
      final card = session.card;
      expect(card, isNotNull, reason: 'continuous practice never stops');
      if (hard.length < hardCount) hard.add(card!.id);
      seen.add(card!.id);
      session.showAnswer();
      session.rate(hard.contains(card.id) ? Rating.again : Rating.good);
    }
    return seen;
  }

  for (final hardCount in [2, 3, 4, 6]) {
    test('$hardCount words always graded Again: 40 draws still show at '
        'least 25 distinct words and never the same word twice in a row', () {
      final seen = run(hardCount);
      expect(seen.toSet().length, greaterThanOrEqualTo(25),
          reason: 'only ${seen.toSet().length} distinct cards in 40 draws');
      for (var i = 1; i < seen.length; i++) {
        expect(seen[i], isNot(seen[i - 1]),
            reason: 'same card twice in a row at step $i');
      }
      // Again cards still come back, spaced at least againGap apart, and
      // at most one Again return per againGap steps.
      final hard = seen.take(hardCount).toSet();
      var lastReturn = -FlashcardSession.againGap;
      for (var i = hardCount; i < seen.length; i++) {
        if (!hard.contains(seen[i])) continue;
        expect(i - lastReturn, greaterThanOrEqualTo(FlashcardSession.againGap),
            reason: 'Again returns at $lastReturn and $i are too close');
        lastReturn = i;
      }
      expect(lastReturn, greaterThan(0),
          reason: 'an Again card must still come back later in the run');
    });
  }

  test(
      'a single Again card still returns exactly againGap cards later, up to '
      'maxAgainRepeats times (問題回報 #319)', () {
    final seen = run(1, draws: 12);
    final first = seen.first;
    final returns = [
      for (var i = 1; i < seen.length; i++)
        if (seen[i] == first) i,
    ];
    expect(returns, [
      for (var n = 1; n <= FlashcardSession.maxAgainRepeats; n++)
        n * FlashcardSession.againGap,
    ]);
  });
}
