// 問題回報 #923 (card #782): an older pack lists boring as a form of bore.
// The start-up link (fold: false) must keep boring; only the folding link
// may merge it.

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

Map<String, dynamic> oldPack() => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': 'old',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'bore',
          'normalized': 'bore',
          'pos': 'verb',
          'status': 'full',
          'cefr': 'B1',
          'senses': [
            {'id': 1, 'definition': 'bore', 'native': '使厭煩'}
          ],
          'forms': [
            {'field': 'present_participle', 'form': 'boring', 'normalized': 'boring'}
          ],
        }
      ],
    };

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('start-up link with an older pack keeps boring', () {
    final repo = WordDatabaseRepository();
    repo.addWord(word: 'boring', pos: 'adjective', meaning: '');
    repo.linkLexicon(LexiconPack.instance..loadJson(oldPack()),
        fold: false, refreshWords: false);
    expect(repo.entryByWord('boring'), isNotNull);
  });
}
