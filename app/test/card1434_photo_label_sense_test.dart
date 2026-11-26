// Card #1434 / 問題回報 #1866: a photo label shows the sense the photo shows
// (counter 「流理台」, not the first sense 「計算者」), chosen by the
// recognizer's English evidence.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart' show LabelPoint;
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

Map<String, dynamic> _lex(int id, String lemma, String pos,
        List<Map<String, dynamic>> senses) =>
    {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': pos,
      'zipf': 5,
      'usage_rank': 0,
      'rare_usage': false,
      'senses': senses,
    };

WordCandidate _c(String w, String pos, String evidence) => WordCandidate(
    word: w,
    pos: pos,
    meaning: '',
    level: 'A2',
    levelSource: 'cefr-j',
    evidence: evidence,
    point: const LabelPoint(.5, .5));

void main() {
  setUp(() {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        _lex(1, 'counter', 'noun', [
          {'id': 11, 'definition': 'one who counts', 'native': '計算者'},
          {
            'id': 12,
            'definition': 'a flat surface in a kitchen, a countertop',
            'native': '流理台'
          },
        ]),
        _lex(2, 'dirt', 'noun', [
          {'id': 21, 'definition': 'filth, grime', 'native': '污垢'},
          {'id': 22, 'definition': 'loose soil or earth', 'native': '泥土'},
        ]),
        _lex(3, 'grain', 'noun', [
          {'id': 31, 'definition': 'a small hard seed', 'native': '穀粒'},
          {
            'id': 32,
            'definition': 'the pattern of fibres in wood',
            'native': '木紋'
          },
        ]),
        _lex(4, 'phone', 'noun', [
          {'id': 41, 'definition': 'a telephone device', 'native': '電話'},
        ]),
      ],
    });
  });

  test('counter takes the sense of the photo, not the first one', () {
    final c = LexiconPack.instance
        .link(_c('counter', 'noun', 'kitchen countertop'));
    expect(c.meaning, '流理台');
  });

  test('without evidence the usual first sense is kept', () {
    final c = LexiconPack.instance.link(_c('counter', 'noun', ''));
    expect(c.meaning, '計算者；流理台');
  });

  test('a plural in the evidence still matches the singular definition', () {
    final c = LexiconPack.instance
        .link(_c('grain', 'noun', 'wood grain pattern'));
    expect(c.meaning, '木紋');
  });

  test('dirt on a road is the soil sense', () {
    final c =
        LexiconPack.instance.link(_c('dirt', 'noun', 'dirt road soil'));
    expect(c.meaning, '泥土');
  });

  test('evidence sharing no word keeps the usual meaning', () {
    final c =
        LexiconPack.instance.link(_c('phone', 'noun', 'black smartphone'));
    expect(c.meaning, '電話');
  });
}
