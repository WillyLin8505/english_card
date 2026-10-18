import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/flashcard_session.dart';

import 'helpers.dart';

/// Card #216: the practice pool must keep rotating through the whole
/// personal database, not narrow to whichever handful of words always
/// had a safe interactive exercise (問題回報 #207).
void main() {
  test(
      'continuous practice rotates through most of the database, not a '
      'handful of words, and clears due cards first', () {
    final repo = testRepository();
    final totalWords = repo.entries.length;
    final dueNow = repo.eligibleCards().map((c) => c.wordEntryId).toSet();
    expect(totalWords, greaterThan(10),
        reason: 'the sample database must be large enough for this to be '
            'a meaningful check');

    final session =
        FlashcardSession(repo, continuous: true, random: math.Random(7));
    addTearDown(session.dispose);

    const draws = 60;
    final seenWords = <String>[];
    final dueSeenByStep = <int>[];
    for (var step = 0; step < draws; step++) {
      final card = session.card;
      expect(card, isNotNull,
          reason: 'continuous practice never runs out of cards to show');
      seenWords.add(card!.wordEntryId);
      if (dueNow.length == seenWords.toSet().intersection(dueNow).length) {
        dueSeenByStep.add(step);
      }
      session.showAnswer();
      session.rate(Rating.good);
    }

    // The root-cause bug (#207: unsafe-exercise cards permanently
    // blacklisted) narrowed every run down to ~5-10 words that always had
    // a buildable exercise. A healthy pool visits well over 10 distinct
    // words in 60 draws.
    expect(seenWords.toSet().length, greaterThan(10),
        reason: 'pool of $totalWords words collapsed to '
            '${seenWords.toSet().length} distinct cards in $draws draws');

    // Every card that was due when the run started must appear before the
    // run falls back to recycling not-yet-due cards for extra practice.
    final allDueSeenAt = dueSeenByStep.isEmpty ? -1 : dueSeenByStep.first;
    expect(allDueSeenAt, greaterThanOrEqualTo(0),
        reason: 'all ${dueNow.length} due cards should appear early');
    expect(allDueSeenAt, lessThan(dueNow.length + FlashcardSession.againGap),
        reason: 'due cards must be cleared before practice recycling kicks '
            'in, not buried among future cards');
  });
}
