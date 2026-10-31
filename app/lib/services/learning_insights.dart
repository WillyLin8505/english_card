import '../models/learning_card.dart';
import '../models/vocabulary_profile.dart';

/// A word the learner keeps pressing 忘記/吃力 on.
class WeakWord {
  final String cardId;
  final String word;
  final int reviews;
  final int again;
  final int hard;

  const WeakWord(this.cardId, this.word, this.reviews, this.again, this.hard);

  /// 忘記 counts double: it is the stronger "I don't know this" signal.
  double get score => (again * 2 + hard) / reviews;
}

/// 學習洞察 — read-only figures derived from the local ReviewLog and
/// UserVocabularyProfile; nothing here is stored.
class LearningInsights {
  /// Reviews per day, oldest first, ending today (local calendar days).
  final List<int> daily;

  /// Reviews per week (7-day blocks ending today), oldest first.
  final List<int> weekly;
  final int total;
  final List<LevelChange> levelChanges;
  final List<WeakWord> weakWords;

  /// Reviews per day for the last [progressDays] days, oldest first.
  final List<int> monthly;

  /// 連續天數 (問題回報 #1172): consecutive local days with a review, ending
  /// today — or yesterday while today has none yet, so the streak is not
  /// shown as lost before the day is over.
  final int currentStreak;
  final int longestStreak;
  final int activeDays;

  const LearningInsights({
    required this.daily,
    required this.weekly,
    required this.total,
    required this.levelChanges,
    required this.weakWords,
    this.monthly = const [],
    this.currentStreak = 0,
    this.longestStreak = 0,
    this.activeDays = 0,
  });

  static const days = 7;
  static const weeks = 4;
  static const progressDays = 30;
  static const minWeakPresses = 2;

  /// [wordOf] maps a card id to its word (null for a deleted word).
  static LearningInsights compute({
    required List<ReviewLog> logs,
    required UserVocabularyProfile profile,
    required String? Function(String cardId) wordOf,
    required DateTime now,
    int maxWeak = 10,
  }) {
    final today = DateTime(now.year, now.month, now.day);
    final daily = List.filled(days, 0);
    final weekly = List.filled(weeks, 0);
    final monthly = List.filled(progressDays, 0);
    final dayNumbers = <int>{}; // local calendar days since the epoch
    final perCard = <String, List<int>>{}; // [reviews, again, hard]
    for (final l in logs) {
      final t = l.reviewedAt.toLocal();
      final age = today.difference(DateTime(t.year, t.month, t.day)).inDays;
      if (age >= 0 && age < progressDays) monthly[progressDays - 1 - age]++;
      if (age >= 0) dayNumbers.add(_dayNumber(t));
      if (age >= 0 && age < days) daily[days - 1 - age]++;
      if (age >= 0 && age < weeks * 7) weekly[weeks - 1 - age ~/ 7]++;
      // What the learner pressed; legacy logs only have the effective rating.
      final pressed = l.requestedRating ?? l.rating;
      final c = perCard.putIfAbsent(l.cardId, () => [0, 0, 0]);
      c[0]++;
      if (pressed == Rating.again) c[1]++;
      if (pressed == Rating.hard) c[2]++;
    }
    final weak = <WeakWord>[];
    for (final e in perCard.entries) {
      final c = e.value;
      if (c[1] + c[2] < minWeakPresses) continue;
      final word = wordOf(e.key);
      if (word == null) continue;
      weak.add(WeakWord(e.key, word, c[0], c[1], c[2]));
    }
    weak.sort((a, b) {
      final s = b.score.compareTo(a.score);
      return s != 0 ? s : b.reviews.compareTo(a.reviews);
    });
    final todayNo = _dayNumber(today);
    var current = 0;
    for (var d = dayNumbers.contains(todayNo) ? todayNo : todayNo - 1;
        dayNumbers.contains(d);
        d--) {
      current++;
    }
    var longest = 0, run = 0;
    final sorted = dayNumbers.toList()..sort();
    for (var i = 0; i < sorted.length; i++) {
      run = i > 0 && sorted[i] == sorted[i - 1] + 1 ? run + 1 : 1;
      if (run > longest) longest = run;
    }
    return LearningInsights(
      monthly: monthly,
      currentStreak: current,
      longestStreak: longest,
      activeDays: dayNumbers.length,
      daily: daily,
      weekly: weekly,
      total: logs.length,
      levelChanges: profile.levelHistory,
      weakWords: weak.take(maxWeak).toList(),
    );
  }

  /// Calendar day count that ignores DST (UTC midnight of the local date).
  static int _dayNumber(DateTime t) =>
      DateTime.utc(t.year, t.month, t.day).millisecondsSinceEpoch ~/ 86400000;
}
