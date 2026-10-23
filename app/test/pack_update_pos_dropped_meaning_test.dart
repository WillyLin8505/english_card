// pack_update_simulation seed 1023: a pack update drops the part of speech
// that had a Chinese meaning (somewhere adv「到某處」, sue verb「起訴」) and
// keeps only one without. The card moves to the kept pos (問題回報 #436) but
// must keep the meaning the learner already saw, not turn into
// 「詞庫尚未提供中文意思」.

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

Map<String, dynamic> lexeme(int id, String word, String pos, String? native) =>
    {
      'id': id,
      'lemma': word,
      'normalized': word,
      'pos': pos,
      'status': 'full',
      'cefr': 'B1',
      'senses': [
        {'id': id, 'definition': word, if (native != null) 'native': native}
      ],
    };

Map<String, dynamic> pack(String version, List<Map<String, dynamic>> lex) => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': version,
      'lexemes': lex,
    };

final v1 = pack('v1', [
  lexeme(1, 'somewhere', 'adv', '到某處'),
  lexeme(2, 'somewhere', 'noun', null),
  lexeme(3, 'sue', 'verb', '起訴'),
  lexeme(4, 'sue', 'noun', null),
]);
final v2 = pack('v2', [
  lexeme(2, 'somewhere', 'noun', null),
  lexeme(4, 'sue', 'noun', null),
]);

void main() {
  tearDown(() => LexiconPack.instance.clear());

  for (final batches in [false, true]) {
    test('moved card keeps its meaning (batches: $batches)', () async {
      final repo = WordDatabaseRepository();
      repo.addWord(word: 'somewhere', pos: 'adv.', meaning: '');
      repo.addWord(word: 'sue', pos: 'verb', meaning: '');
      repo.linkLexicon(LexiconPack.instance..loadJson(v1));
      expect(repo.entryByWord('somewhere')!.meaning, '到某處');
      expect(repo.entryByWord('sue')!.meaning, '起訴');

      LexiconPack.instance.loadJson(v2);
      if (batches) {
        await repo.linkLexiconInBatches(LexiconPack.instance,
            budget: Duration.zero);
      } else {
        repo.linkLexicon(LexiconPack.instance);
      }
      for (final (word, meaning) in [('somewhere', '到某處'), ('sue', '起訴')]) {
        final e = repo.entryByWord(word)!;
        expect(e.pos, 'noun');
        expect(e.lexemeId, word == 'sue' ? 4 : 2);
        expect(e.meaning, meaning);
        expect(e.dataStatus, isNot(WordDataStatus.failed));
        expect(e.dataError, isNull);
      }
    });
  }

  test('a learner-edited meaning stays as before', () {
    final repo = WordDatabaseRepository();
    repo.addWord(word: 'sue', pos: 'verb', meaning: '');
    repo.linkLexicon(LexiconPack.instance..loadJson(v1));
    final e = repo.entryByWord('sue')!;
    repo.editEntry(e.copyWith(meaning: '告人'), {WordField.meaning});
    repo.linkLexicon(LexiconPack.instance..loadJson(v2));
    final after = repo.entryByWord('sue')!;
    expect(after.pos, 'noun');
    expect(after.meaning, '告人');
  });
}
