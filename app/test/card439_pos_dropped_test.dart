// 問題回報 #436 (card #439): when a pack update drops a word's part of
// speech, the saved card moves to the pos the pack kept and keeps updating.

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

Map<String, dynamic> pack(String version, List<String> poses) => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': version,
      'lexemes': [
        for (var i = 0; i < poses.length; i++)
          {
            'id': 10 + i,
            'lemma': 'cozy',
            'normalized': 'cozy',
            'pos': poses[i],
            'status': 'full',
            'cefr': 'B1',
            'senses': [
              {'id': 10 + i, 'definition': 'cozy', 'native': '${poses[i]}意思'}
            ],
          }
      ],
    };

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('card follows the word to the remaining pos', () {
    final repo = WordDatabaseRepository();
    repo.addWord(word: 'cozy', pos: 'noun', meaning: '');
    repo.linkLexicon(LexiconPack.instance..loadJson(pack('v1', ['noun', 'adj'])));
    expect(repo.entryByWord('cozy')!.pos, 'noun');
    repo.linkLexicon(LexiconPack.instance..loadJson(pack('v2', ['adj'])));
    final e = repo.entryByWord('cozy')!;
    expect(e.pos, 'adj.');
    expect(e.meaning, 'adj意思');
  });
}
