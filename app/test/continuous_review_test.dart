import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'review_archive_session_test.dart' show smallRepo;

void main() {
  for (final rating in [Rating.good, Rating.again]) {
    // 問題回報 #319: a word shows at most maxRunAppearances times per run, so a
    // one-word database ends the run there instead of looping 60 times.
    test('continuous review stops at the per-word cap: $rating', () {
      final repo = smallRepo(1);
      final s = FlashcardSession(repo, continuous: true);
      addTearDown(s.dispose);
      final id = s.card!.id;
      var n = 0;
      while (!s.finished && n < 60) {
        s.showAnswer();
        s.rate(rating);
        n++;
      }
      expect(s.finished, true);
      expect(n, lessThanOrEqualTo(FlashcardSession.maxRunAppearances));
      expect(s.reviewed, n);
      expect(repo.logsOf(id), hasLength(1));
    });
  }
  test('future cards remain available in a new session', () {
    final repo = smallRepo(1);
    final first = FlashcardSession(repo);
    first.showAnswer();
    first.rate(Rating.easy);
    first.dispose();
    final s = FlashcardSession(repo, continuous: true);
    addTearDown(s.dispose);
    expect(s.finished, false);
    expect(s.isExtraPractice, true);
    s.showAnswer();
    s.rate(Rating.easy);
    expect(repo.logsOf(s.card!.id), hasLength(1));
  });
}
