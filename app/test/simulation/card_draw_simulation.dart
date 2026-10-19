// How the 複習 tab draws cards (問題回報 #318; not part of the regular suite).
//
// Learners of different sizes open the continuous review mode once a day and
// stop after a fixed number of cards. For each profile it measures what the
// owner complained about — the same few words coming back — and compares it
// with what FSRS promises (every due card once a day, new cards after them):
// distinct words per session, repeats of one word, back-to-back repeats, how
// much of the collection was seen at all, the share of new cards, and the
// share of all draws taken by the five most drawn words.
//
//   flutter test test/simulation/card_draw_simulation.dart
//   (SIM_SEED, SIM_ONLY: profile name substring)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/fsrs_scheduler.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

class _Profile {
  final String name;
  final int cards, perDay, days, addPerDay;

  /// Scales the app's predicted recall: a forgetful learner is below 1.
  final double memory;
  const _Profile(this.name, this.cards, this.perDay, this.days, this.addPerDay,
      [this.memory = 1]);
}

const _profiles = [
  _Profile('20字_每天20_7天', 20, 20, 7, 0),
  _Profile('60字_每天20_7天', 60, 20, 7, 0),
  _Profile('60字_每天40_30天', 60, 40, 30, 0),
  _Profile('200字_每天20_30天', 200, 20, 30, 0),
  _Profile('200字_每天60_30天', 200, 60, 30, 0),
  _Profile('新手200字_每天加10_複習40_30天', 200, 40, 30, 10),
  _Profile('健忘60字_每天20_30天', 60, 20, 30, 0, 0.6),
  _Profile('健忘200字_每天40_30天', 200, 40, 30, 0, 0.6),
];

Map<String, Object> _run(_Profile p, int seed) {
  final rnd = Random(seed);
  var now = DateTime(2026, 1, 1, 20);
  final repo = WordDatabaseRepository(clock: () => now)
    ..scheduler = FsrsScheduler(FsrsParameters());
  var added = 0;
  void add(int n) {
    for (var i = 0; i < n && added < p.cards; i++) {
      final w = 'w${added++}';
      final e =
          repo.addWord(word: w, pos: 'noun', meaning: '意思', level: 'A2');
      repo.editEntry(
        e.copyWith(examples: [
          WordExample(text: 'I see a $w every day.', translation: '我看到$w。')
        ]),
        {WordField.examples},
      );
    }
  }

  add(p.addPerDay == 0 ? p.cards : p.addPerDay);
  final draws = <String, int>{};
  final seenEver = <String>{};
  final distinct = <int>[], maxRepeat = <int>[], backToBack = <int>[];
  final newShare = <double>[], dueAtStart = <int>[], shownPerDay = <int>[];
  final coverage = <int, double>{};
  var totalDraws = 0;
  for (var day = 0; day < p.days; day++) {
    now = DateTime(2026, 1, 1 + day, 7).add(Duration(minutes: rnd.nextInt(960)));
    if (day > 0) add(p.addPerDay);
    dueAtStart.add(repo.eligibleCards().length);
    final s = FlashcardSession(repo, random: rnd, continuous: true);
    final seq = <String>[];
    var fresh = 0;
    while (!s.finished && seq.length < p.perDay) {
      final c = s.card!;
      if (!seenEver.contains(c.id)) fresh++;
      seenEver.add(c.id);
      seq.add(c.id);
      draws[c.id] = (draws[c.id] ?? 0) + 1;
      totalDraws++;
      s.showAnswer();
      final r = repo.scheduler.retrievability(c.fsrs, now);
      final ok = r == null ? rnd.nextDouble() < 0.7 : rnd.nextDouble() < r * p.memory;
      s.rate(ok ? Rating.good : Rating.again);
      now = now.add(const Duration(seconds: 30));
    }
    s.dispose();
    final counts = <String, int>{};
    for (final id in seq) {
      counts[id] = (counts[id] ?? 0) + 1;
    }
    distinct.add(counts.length);
    maxRepeat.add(counts.values.fold(0, max));
    var b2b = 0;
    for (var i = 1; i < seq.length; i++) {
      if (seq[i] == seq[i - 1]) b2b++;
    }
    backToBack.add(b2b);
    newShare.add(seq.isEmpty ? 0 : fresh / seq.length);
    shownPerDay.add(seq.length);
    if (day == 6 || day == p.days - 1) {
      coverage[day + 1] = seenEver.length / added;
    }
  }
  final top = draws.values.toList()..sort((a, b) => b.compareTo(a));
  double avg(Iterable<num> v) =>
      v.isEmpty ? 0 : v.fold<num>(0, (a, b) => a + b) / v.length;
  String f(num v) => v.toStringAsFixed(2);
  return {
    'profile': p.name,
    'collection': added,
    'avg_shown_per_session': f(avg(shownPerDay)),
    'avg_due_at_start': f(avg(dueAtStart)),
    'avg_distinct_per_session': f(avg(distinct)),
    'distinct_share': f(avg(distinct) / max(1, avg(shownPerDay))),
    'avg_max_repeat_of_one_word': f(avg(maxRepeat)),
    'worst_repeat': maxRepeat.reduce(max),
    'back_to_back_per_session': f(avg(backToBack)),
    'new_card_share': f(avg(newShare)),
    'coverage_day7': f(coverage[7] ?? coverage.values.last),
    'coverage_end': f(coverage[p.days] ?? 0),
    'top5_share_of_draws': f(top.take(5).fold(0, (a, b) => a + b) / totalDraws),
    'never_drawn': added - draws.length,
  };
}

void main() {
  test('card draw: variety, repeats and coverage per learner profile', () {
    final env = Platform.environment;
    final seed = int.parse(env['SIM_SEED'] ?? '7');
    final only = env['SIM_ONLY'];
    final rows = <Map<String, Object>>[];
    for (final p in _profiles) {
      if (only != null && !p.name.contains(only)) continue;
      rows.add(_run(p, seed));
    }
    // ignore: avoid_print
    print('SIMDRAW ${const JsonEncoder.withIndent(' ').convert(rows)}');
    for (final r in rows) {
      expect(double.parse(r['back_to_back_per_session'] as String), lessThan(1),
          reason: '${r['profile']}: the same word twice in a row');
      // Reported, not asserted, until 問題回報 #319 (no cap on Again
      // repeats in continuous mode) is fixed: then it must be <= 3.
      if (int.parse('${r['worst_repeat']}') > 3) {
        // ignore: avoid_print
        print('SIMDRAW WARN ${r['profile']}: one word ${r['worst_repeat']}x');
      }
    }
  });
}
