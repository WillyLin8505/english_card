import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'helpers.dart';
import 'review_missing_exercise_test.dart' show singleWordRepo;

void main() {
  // 問題回報 #1590: turning off one kind of question keeps the card.
  test('replaceExerciseType hides only that type and keeps the card', () {
    final entry = WordEntry.fromUserInput(
            id: 'apple',
            word: 'apple',
            pos: 'noun',
            meaning: '蘋果',
            level: 'A1',
            now: testNow)
        .copyWith(examples: const [
      WordExample(text: 'I eat an apple.', translation: '我吃蘋果。')
    ]);
    final hidden = <String>{};
    final s = FlashcardSession(singleWordRepo(entry),
        continuous: true, hiddenTypes: () => hidden);
    final cardId = s.card?.id;
    expect(s.exercise?.type, ReviewExerciseType.sentenceCloze);
    s.replaceExerciseType(hidden.add);
    expect(hidden, {'sentenceCloze'});
    expect(s.exercise?.type, isNot(ReviewExerciseType.sentenceCloze));
    expect(s.card?.id, cardId);
  });
}
