import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'review_archive_session_test.dart' show smallRepo;

void main() {
  for (final rating in [Rating.good, Rating.again]) {
    test('continuous review survives 60 responses: $rating', () {
      final repo = smallRepo(1);
      final s = FlashcardSession(repo, continuous: true);
      addTearDown(s.dispose);
      final id = s.card!.id;
      for (var i = 0; i < 60; i++) {
        expect(s.finished, false);
        s.showAnswer();
        s.rate(rating);
      }
      expect(s.reviewed, 60);
      expect(repo.logsOf(id), hasLength(1));
      expect(s.isExtraPractice, true);
      repo.archiveWord(s.card!.wordEntryId);
      expect(s.finished, true);
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
