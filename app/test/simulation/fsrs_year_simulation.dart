// A year with FSRS (not part of the regular suite). The learner remembers a
// review card exactly with FSRS's own predicted probability, so the share of
// remembered reviews should match the desired retention (90%), intervals
// should grow, and no card should be lost or scheduled in the past.
//
//   flutter test test/simulation/fsrs_year_simulation.dart  (SIM_RETENTION)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/fsrs_scheduler.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'learner_simulation.dart' show allCards;

void main() {
  test('a year of reviews keeps the desired retention', () {
    final retention = double.parse(Platform.environment['SIM_RETENTION'] ?? '0.9');
    final rnd = Random(3);
    var now = DateTime(2026, 1, 1, 20);
    final repo = WordDatabaseRepository(clock: () => now)
      ..scheduler = FsrsScheduler(FsrsParameters(desiredRetention: retention));
    var reviews = 0, remembered = 0, newCards = 0, words = 0;
    final perDay = <int>[];
    final intervals = <int>[];
    for (var day = 0; day < 365; day++) {
      for (var i = 0; i < 10 && day < 200; i++) {
        repo.addWord(word: 'w${words++}', pos: 'noun', meaning: '意思', level: 'A2');
      }
      final s = FlashcardSession(repo, random: rnd);
      var shown = 0;
      while (!s.finished && shown < 2000) {
        final c = s.card!;
        s.showAnswer();
        Rating r;
        final p = repo.scheduler.retrievability(c.fsrs, now);
        if (c.fsrs.state == FsrsCardState.newCard) {
          newCards++;
          r = rnd.nextDouble() < 0.7 ? Rating.good : Rating.again;
        } else if (c.fsrs.lastReview != null && now.difference(c.fsrs.lastReview!).inHours < 20) {
          r = Rating.good; // the same-day Again repeat
        } else {
          reviews++;
          final ok = rnd.nextDouble() < (p ?? 0.9);
          if (ok) remembered++;
          r = ok ? Rating.good : Rating.again;
        }
        s.rate(r);
        final after = repo.card(c.id)!;
        if (r == Rating.good && after.fsrs.scheduledDays > 0) intervals.add(after.fsrs.scheduledDays);
        shown++;
        now = now.add(const Duration(seconds: 10));
      }
      perDay.add(shown);
      now = DateTime(now.year, now.month, now.day + 1, 20);
    }
    final rate = remembered / reviews;
    intervals.sort();
    final report = {
      'desired_retention': retention, 'observed_retention': rate, 'reviews': reviews,
      'new_cards': newCards, 'cards': allCards(repo).length,
      'median_interval': intervals[intervals.length ~/ 2], 'max_interval': intervals.last,
      'busiest_day': perDay.reduce(max), 'last_month_avg': perDay.skip(335).reduce((a, b) => a + b) / 30,
    };
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert(report));
    expect((rate - retention).abs(), lessThan(0.04), reason: 'FSRS should hit its target retention');
  });
}
