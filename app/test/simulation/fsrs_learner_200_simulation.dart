// A learner with 200 cards for half a year (not part of the regular suite).
//
// Unlike fsrs_year_simulation.dart, the learner's memory is its own: each
// card's true stability and difficulty follow FSRS-5 in real elapsed time
// (fractional days), and recall is drawn from that — not from the app's
// estimate. The learner reviews at a random time between 07:00 and 23:00,
// skips about one day in ten, and uses the app's continuous mode (extra
// practice never changes the schedule). It then checks what the forgetting
// algorithm promises: about the desired share of due reviews is
// remembered, and the app's predicted recall matches what happens.
//
//   flutter test test/simulation/fsrs_learner_200_simulation.dart
//   (SIM_CARDS, SIM_DAYS, SIM_SEED, SIM_RETENTION, SIM_SKIP: share of days
//   without reviews, 0.1)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/fsrs_scheduler.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

/// The learner's real memory of one card: FSRS-5 with the default weights,
/// in continuous time.
class _Memory {
  static const w = FsrsParameters.defaultWeights;
  static final factor = pow(0.9, 1 / -0.5) - 1;
  double stability = 0, difficulty = 0;
  DateTime? last;

  double recall(DateTime now) {
    if (last == null) return 0;
    final t = now.difference(last!).inSeconds / 86400;
    return pow(1 + factor * t / stability, -0.5).toDouble();
  }

  void see(int grade, DateTime now) {
    double initD(int g) => w[4] - exp(w[5] * (g - 1)) + 1;
    if (last == null) {
      stability = w[grade - 1];
      difficulty = initD(grade).clamp(1.0, 10.0);
    } else {
      final r = recall(now);
      if (grade == 1) {
        stability = min(
            w[11] *
                pow(difficulty, -w[12]) *
                (pow(stability + 1, w[13]) - 1) *
                exp((1 - r) * w[14]),
            stability / exp(w[17] * w[18]));
      } else {
        stability *= 1 +
            exp(w[8]) *
                (11 - difficulty) *
                pow(stability, -w[9]) *
                (exp((1 - r) * w[10]) - 1);
      }
      final damped = difficulty + -w[6] * (grade - 3) * (10 - difficulty) / 9;
      difficulty = (w[7] * initD(4) + (1 - w[7]) * damped).clamp(1.0, 10.0);
      stability = max(stability, 0.01);
    }
    last = now;
  }
}

void main() {
  test('200 cards: the forgetting algorithm keeps its promise', () {
    final env = Platform.environment;
    final cards = int.parse(env['SIM_CARDS'] ?? '200');
    final days = int.parse(env['SIM_DAYS'] ?? '180');
    final retention = double.parse(env['SIM_RETENTION'] ?? '0.9');
    final skip = double.parse(env['SIM_SKIP'] ?? '0.1');
    final rnd = Random(int.parse(env['SIM_SEED'] ?? '7'));
    var now = DateTime(2026, 1, 1, 20);
    final repo = WordDatabaseRepository(clock: () => now)
      ..scheduler = FsrsScheduler(FsrsParameters(desiredRetention: retention));
    final memory = <String, _Memory>{};
    var words = 0, due = 0, remembered = 0, practice = 0, skipped = 0;
    var predicted = 0.0, logLoss = 0.0, nextMorning = 0;
    final perDay = <int>[];
    for (var day = 0; day < days; day++) {
      // A random time of day; about one day in ten without reviews.
      now = DateTime(2026, 1, 1 + day, 7)
          .add(Duration(minutes: rnd.nextInt(16 * 60)));
      if (day > 0 && rnd.nextDouble() < skip) {
        skipped++;
        perDay.add(0);
        continue;
      }
      for (var i = 0; i < 10 && words < cards; i++) {
        final w = 'w${words++}';
        final e =
            repo.addWord(word: w, pos: 'noun', meaning: '意思', level: 'A2');
        repo.editEntry(
          e.copyWith(examples: [
            WordExample(
                text: 'I see a $w every day.', translation: '我每天看到一個$w。')
          ]),
          {WordField.examples},
        );
      }
      final s = FlashcardSession(repo, random: rnd, continuous: true);
      var shown = 0;
      while (!s.finished && shown < 2000) {
        // Extra practice once nothing is due any more: done for the day.
        if (s.isExtraPractice && repo.eligibleCards().isEmpty) break;
        final c = s.card!;
        final m = memory.putIfAbsent(c.id, _Memory.new);
        s.showAnswer();
        final int grade;
        if (m.last == null) {
          grade = rnd.nextDouble() < 0.7 ? 3 : 1; // first meeting
        } else {
          final ok = rnd.nextDouble() < m.recall(now);
          grade = ok ? 3 : 1;
          if (s.isExtraPractice) {
            practice++;
          } else {
            // A scheduled review: what the app predicted vs what happened.
            due++;
            if (ok) remembered++;
            final p = repo.scheduler
                .retrievability(c.fsrs, now)!
                .clamp(1e-6, 1 - 1e-6);
            predicted += p;
            logLoss -= ok ? log(p) : log(1 - p);
            final last = c.fsrs.lastReview!;
            if (now.difference(last).inDays == 0 &&
                calendarDaysBetween(last, now) >= 1) {
              nextMorning++;
            }
          }
        }
        m.see(grade, now);
        s.rate(grade == 3 ? Rating.good : Rating.again);
        shown++;
        now = now.add(const Duration(seconds: 30));
      }
      s.dispose();
      perDay.add(shown);
    }
    final all = [for (final e in repo.entries) repo.cardOf(e.id)!];
    final intervals = [for (final c in all) c.fsrs.scheduledDays]..sort();
    final observed = remembered / due;
    final report = {
      'cards': all.length,
      'days': days,
      'days_skipped': skipped,
      'desired_retention': retention,
      'observed_retention': double.parse(observed.toStringAsFixed(4)),
      'app_predicted_recall':
          double.parse((predicted / due).toStringAsFixed(4)),
      'log_loss': double.parse((logLoss / due).toStringAsFixed(4)),
      'due_reviews': due,
      'reviews_per_card': double.parse((due / all.length).toStringAsFixed(2)),
      'next_morning_reviews': nextMorning,
      'extra_practice': practice,
      'lapses': all.fold<int>(0, (n, c) => n + c.fsrs.lapses),
      'median_interval_end': intervals[intervals.length ~/ 2],
      'max_interval_end': intervals.last,
      'busiest_day': perDay.reduce(max),
      'last_month_avg_per_day': double.parse(
          (perDay.skip(days - 30).reduce((a, b) => a + b) / 30)
              .toStringAsFixed(1)),
    };
    // ignore: avoid_print
    print('SIM200 ${const JsonEncoder.withIndent(' ').convert(report)}');
    expect(all, hasLength(cards));
    expect((observed - retention).abs(), lessThan(0.04),
        reason: 'about the desired share of due reviews is remembered');
    expect((predicted / due - observed).abs(), lessThan(0.03),
        reason: "the app's predicted recall matches what happens");
  });
}
