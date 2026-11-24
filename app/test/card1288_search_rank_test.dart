import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_query.dart';

/// 問題回報 #1719: typing "dog" listed it 12th of 34, alphabetically.
void main() {
  test('exact, prefix, contains, elsewhere', () {
    WordEntry w(String s) => WordEntry(id: s, word: s, pos: 'noun', meaning: 'x', createdAt: DateTime(2026), updatedAt: DateTime(2026));
    expect(searchRank('dog', w('dog')), 0);
    expect(searchRank('dog', w('dogma')), 1);
    expect(searchRank('dog', w('hotdog')), 2);
    expect(searchRank('dog', w('puppy')), 3);
    expect(searchRank('', w('puppy')), 0);
  });

  // 問題回報 #1740: French list, maison 32/58 and parler 23/45.
  test('French headwords rank like English ones (#1740)', () {
    WordEntry w(String s) => WordEntry(id: s, word: s, pos: 'noun', meaning: 'x', createdAt: DateTime(2026), updatedAt: DateTime(2026));
    final words = ['abri', 'maisonnette', 'ma maison', 'maison', 'chat'];
    words.sort((a, b) => searchRank('maison', w(a)).compareTo(searchRank('maison', w(b))));
    expect(words.first, 'maison');
    expect(searchRank('maison', w('maisonnette')), 1);
    expect(searchRank('maison', w('ma maison')), 2);
  });
}
