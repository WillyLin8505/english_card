import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_query.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  test('adjectives from the database and from photos are one part of speech', () {
    expect(shortPos('adj'), 'adj.');
    expect(shortPos('adverb'), 'adv.');
    final repo = WordDatabaseRepository(clock: () => testNow);
    repo.addWord(word: 'warm', pos: shortPos('adj'), meaning: '溫暖', level: 'A1');
    repo.addWord(word: 'cold', pos: 'adj.', meaning: '冷', level: 'A1');
    // A word saved before the codes were unified.
    repo.addWord(word: 'wet', pos: 'adj', meaning: '濕', level: 'A1');
    expect(repo.partsOfSpeech, ['adj.']);
    expect(repo.query(const WordDatabaseFilter(pos: 'adj.')).map((r) => r.entry.word).toSet(),
        {'warm', 'cold', 'wet'});
    expect(() => repo.addWord(word: 'wet', pos: 'adj.', meaning: '濕', level: 'A1'),
        throwsA(isA<DuplicateWordException>()));
  });
}
