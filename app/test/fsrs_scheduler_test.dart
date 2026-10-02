import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/fsrs_scheduler.dart';

void main() {
  const scheduler = FsrsScheduler();

  // Stability / difficulty after each review, generated with the
  // reference implementation py-fsrs 5.1.3 (default parameters,
  // learning_steps=(), relearning_steps=(), enable_fuzzing=False).
  // Each step is (rating, days after the previous review, S, D).
  const reference = <String, List<(Rating, int, double, double)>>{
    'A': [
      (Rating.good, 0, 3.173000, 5.282434),
      (Rating.good, 3, 10.738926, 5.272968),
      (Rating.again, 10, 2.146381, 6.790568),
      (Rating.hard, 2, 3.048311, 7.292552),
      (Rating.easy, 5, 26.010889, 6.836531),
      (Rating.good, 0, 36.617381, 6.819916), // same day: short-term
    ],
    'B': [
      (Rating.again, 0, 0.402550, 7.194900),
      (Rating.good, 1, 2.265009, 7.176636),
      (Rating.good, 4, 8.754060, 7.158456),
    ],
    'C': [
      (Rating.easy, 0, 15.691050, 3.224502),
      (Rating.hard, 20, 28.393979, 4.318882),
    ],
    'D': [
      (Rating.hard, 0, 1.183850, 6.488305),
      (Rating.good, 0, 1.666590, 6.473292),
    ],
  };

  for (final MapEntry(key: name, value: steps) in reference.entries) {
    test('matches py-fsrs 5 reference sequence $name', () {
      var state = FsrsState.initial;
      var t = DateTime.utc(2026, 1, 1, 9);
      for (final (rating, days, s, d) in steps) {
        t = t.add(Duration(days: days));
        state = scheduler.next(state, rating, t).state;
        expect(state.stability, closeTo(s, 1e-4), reason: '$name $rating +${days}d S');
        expect(state.difficulty, closeTo(d, 1e-4), reason: '$name $rating +${days}d D');
      }
    });
  }

  test('new card: interval = stability at 90% retention, buttons in order', () {
    final now = DateTime(2026, 9, 24, 10);
    final p = scheduler.preview(FsrsState.initial, now);
    expect([for (final r in Rating.values) p[r]!.scheduledDays], [1, 2, 3, 16]);
    expect(p[Rating.good]!.state.due, now.add(const Duration(days: 3)));
    expect(p[Rating.again]!.state.state, FsrsCardState.learning);
    expect(p[Rating.good]!.state.state, FsrsCardState.review);
    expect(p[Rating.good]!.state.reps, 1);
    expect(p[Rating.good]!.state.algorithmVersion, 'fsrs-5');
  });

  test('forgetting a review card counts a lapse and relearns', () {
    final now = DateTime(2026, 9, 24);
    final reviewed = scheduler.next(FsrsState.initial, Rating.good, now).state;
    final later = now.add(const Duration(days: 3));
    final again = scheduler.next(reviewed, Rating.again, later);
    expect(again.state.state, FsrsCardState.relearning);
    expect(again.state.lapses, 1);
    expect(again.state.stability, lessThan(reviewed.stability));
    expect(again.elapsedDays, 3);
  });

  test('retrievability is 90% after exactly S days', () {
    final start = DateTime(2026, 9, 1);
    final s = scheduler.next(FsrsState.initial, Rating.good, start).state; // S = 3.173
    expect(scheduler.retrievability(FsrsState.initial, start), isNull);
    expect(scheduler.retrievability(s, start), 1.0);
    final r3 = scheduler.retrievability(s, start.add(const Duration(days: 3)))!;
    expect(r3, closeTo(0.9, 0.01)); // 3 days ≈ S
  });
}
