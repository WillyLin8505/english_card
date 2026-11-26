// Owner 11/26: window "panes" became "pan" 平底鍋 on a photo.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/cefr_lexicon.dart';

void main() {
  test('-es comes off only after s, x, z, ch, sh', () {
    final lex = CefrLexicon.fromJson({
      'words': {
        'pan': [4.0, {'noun': 'A2'}],
        'pane': [3.0, {'noun': 'C1'}],
        'box': [5.0, {'noun': 'A1'}],
        'dish': [4.5, {'noun': 'A2'}],
        'tomato': [4.4, {'noun': 'A1'}],
      }
    });
    expect(lex.lemmaOf('panes')!.lemma, 'pane');
    expect(lex.lemmaOf('boxes')!.lemma, 'box');
    expect(lex.lemmaOf('dishes')!.lemma, 'dish');
    expect(lex.lemmaOf('tomatoes')!.lemma, 'tomato');
    expect(lex.resolve('panes', 'noun').level, 'C1');
  });
}
