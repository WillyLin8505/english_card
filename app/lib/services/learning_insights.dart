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

  const LearningInsights({
    required this.daily,
    required this.weekly,
    required this.total,
    required this.levelChanges,
    required this.weakWords,
  });

  static const days = 7;
  static const weeks = 4;
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
    final perCard = <String, List<int>>{}; // [reviews, again, hard]
    for (final l in logs) {
      final t = l.reviewedAt.toLocal();
      final age = today.difference(DateTime(t.year, t.month, t.day)).inDays;
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
    return LearningInsights(
      daily: daily,
      weekly: weekly,
      total: logs.length,
      levelChanges: profile.levelHistory,
      weakWords: weak.take(maxWeak).toList(),
    );
  }
}
