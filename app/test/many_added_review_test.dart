import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  test('every word added from the database comes up once in the first run (問題回報 #100)', () {
    var now = testNow;
    final repo = WordDatabaseRepository(
        clock: () => now, profile: UserVocabularyProfile.start('A2', now: testNow));
    final words = ['apple', 'banana', 'bus', 'cat', 'dog', 'egg', 'fish', 'goat', 'hat', 'ink',
                   'jam', 'kite', 'lamp', 'milk', 'nest', 'owl', 'pen', 'rice'];
    for (final w in words) {
      repo.addWord(word: w, pos: 'n.', meaning: '意思$w', level: 'A1');
      now = now.add(const Duration(seconds: 3));
    }
    final s = FlashcardSession(repo);
    final seen = <String>{};
    var n = 0;
    while (!s.finished && n < 100) {
      seen.add(repo.entry(s.card!.wordEntryId)!.word);
      s.showAnswer();
      s.rate(Rating.good);
      now = now.add(const Duration(seconds: 8));
      n++;
    }
    expect(seen.length, words.length);
  });
}
