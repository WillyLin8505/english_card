import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/tagging_service.dart';

import 'helpers.dart';

void main() {
  test('the tagger\'s inflected words become dictionary forms (spec 08: 詞形正規化)', () {
    Map<String, dynamic> c(String w, String pos) => {'word': w, 'pos': pos, 'point': [500, 500]};
    final got = parseCandidates({
      'candidates': [
        c('eaten', 'verb'), c('children', 'noun'), c('standing', 'verb'),
        c('ironing', 'verb'), c('sitting', 'verb'), c('stopped', 'verb'),
        c('stained_glass', 'noun'), c('swimming', 'noun'), c('decorated', 'adjective'),
        c('slices', 'noun'),
      ]
    }, lexicon: testLexicon());
    expect([for (final x in got) x.word], [
      'eat', 'child', 'stand', 'iron', 'sit', 'stop',
      'stained glass', 'swimming', 'decorated', 'slice',
    ]);
    final stand = got.firstWhere((x) => x.word == 'stand');
    expect(stand.level, isNot('C2'), reason: 'not the noun "standing" (C2)');
  });
}
