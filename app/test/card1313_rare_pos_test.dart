// Card #1313: a recognizer's guessed part of speech must not pick the rare
// entry of a word (dog verb 「追捕」, beautiful noun 「美人」).
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart' show LabelPoint;
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

Map<String, dynamic> _lex(int id, String lemma, String pos, int rank,
        String meaning) =>
    {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': pos,
      'zipf': 5,
      'usage_rank': rank,
      'rare_usage': rank > 0,
      'senses': [
        {'id': id * 10, 'definition': 'x', 'native': meaning},
      ],
    };

void main() {
  _savedWordHeals();
  test('link keeps the common entry, not the guessed rare pos', () {
    final pack = LexiconPack.instance;
    pack.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        _lex(1, 'dog', 'noun', 0, '狗'),
        _lex(2, 'dog', 'verb', 1, '追捕'),
        _lex(3, 'beautiful', 'adj', 0, '漂亮'),
        _lex(4, 'beautiful', 'noun', 1, '美人'),
      ],
    });
    WordCandidate c(String w, String pos) => WordCandidate(
        word: w, pos: pos, meaning: '', level: 'A1', levelSource: 'cefr-j', point: const LabelPoint(.5, .5));
    final dog = pack.link(c('dog', 'verb'));
    expect(dog.meaning, '狗');
    expect(dog.pos, 'noun');
    final beautiful = pack.link(c('beautiful', 'noun'));
    expect(beautiful.meaning, '漂亮');
    expect(beautiful.pos, 'adj.');
    expect(pack.link(c('dog', 'noun')).meaning, '狗');
  });
}

// Card #1385: a word already saved on the guessed rare pos moves to the
// common entry when the pack is linked, also for the bundled pack.
void _savedWordHeals() {
  test('saved dog verb / beautiful noun move to the common entry', () {
    final repo = WordDatabaseRepository();
    repo.addWord(word: 'dog', pos: 'verb', meaning: '追捕');
    repo.addWord(word: 'beautiful', pos: 'noun', meaning: '美人');
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        _lex(1, 'dog', 'noun', 0, '狗'),
        _lex(2, 'dog', 'verb', 1, '追捕'),
        _lex(3, 'beautiful', 'adj', 0, '漂亮'),
        _lex(4, 'beautiful', 'noun', 1, '美人'),
      ],
    });
    repo.linkLexicon(LexiconPack.instance);
    expect(repo.entryByWord('dog')!.meaning, '狗');
    expect(repo.entryByWord('beautiful')!.meaning, '漂亮');
  });
}
