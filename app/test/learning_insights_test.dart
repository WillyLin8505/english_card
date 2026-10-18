import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/services/learning_insights.dart';
import 'package:flutter_test/flutter_test.dart';

ReviewLog _log(String card, DateTime at, Rating r) => ReviewLog(
      cardId: card,
      reviewedAt: at,
      rating: r,
      before: FsrsState.initial,
      after: FsrsState.initial,
      elapsedDays: 0,
      scheduledDays: 1,
    );

void main() {
  final now = DateTime(2026, 10, 18, 12);

  test('counts per day and week, ranks weak words', () {
    final logs = [
      _log('a', now, Rating.again),
      _log('a', now.subtract(const Duration(days: 1)), Rating.hard),
      _log('a', now.subtract(const Duration(days: 10)), Rating.good),
      _log('b', now.subtract(const Duration(days: 2)), Rating.again),
      _log('c', now, Rating.good),
    ];
    final ins = LearningInsights.compute(
      logs: logs,
      profile: UserVocabularyProfile.start('A2', now: now),
      wordOf: (id) => {'a': 'apple', 'b': 'bear'}[id],
      now: now,
    );
    expect(ins.daily.last, 2);
    expect(ins.daily[5], 1);
    expect(ins.weekly.last, 4);
    expect(ins.weekly[2], 1);
    expect(ins.total, 5);
    expect(ins.weakWords.map((w) => w.word), ['apple']);
  });

  test('level changes are recorded and survive json', () {
    var p = UserVocabularyProfile.start('A1', now: now);
    p = p.withLevel('B1', 'user', now);
    p = p.withLevel('B1', 'user', now);
    expect(p.levelHistory.length, 1);
    final back = UserVocabularyProfile.fromJson(p.toJson());
    expect(back.levelHistory.single.to, p.level);
    expect(back.levelHistory.single.source, 'user');
  });
}
