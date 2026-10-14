import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

// 問題回報 #191: an inflected form is a pointer to its lemma, not a card.
Map<String, dynamic> _pack() => {
      'schema_version': 5,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'redirects': {'3': 2},
      'lexemes': [
        {
          'id': 2,
          'lemma': 'tear',
          'normalized': 'tear',
          'pos': 'verb',
          'status': 'full',
          'cefr': 'B1',
          'senses': [
            {'id': 20, 'definition': 'To pull apart.', 'native': '撕', 'native_ai': false}
          ],
          'forms': [],
          'pronunciations': [],
          'examples': [],
        },
        // A full inflected entry and a stub one, both redirected.
        {
          'id': 3,
          'lemma': 'tore',
          'normalized': 'tore',
          'pos': 'verb',
          'status': 'full',
          'cefr': null,
          'redirect_to': 2,
          'card': 'tear',
          'senses': [
            {'id': 30, 'definition': 'past of tear', 'native': '撕（過去式）'}
          ],
        },
        {
          'id': 4,
          'lemma': 'torn up',
          'normalized': 'torn up',
          'pos': 'unknown',
          'status': 'stub',
          'redirect_to': 2,
        },
        // Pointer to a lemma that is missing: must not crash.
        {
          'id': 5,
          'lemma': 'zorbed',
          'normalized': 'zorbed',
          'pos': 'unknown',
          'status': 'stub',
          'redirect_to': 999,
        },
      ],
    };

void main() {
  late LexiconPack pack;
  setUp(() => pack = LexiconPack()..loadJson(_pack()));

  test('a redirected id opens the lemma', () {
    expect(pack.byId(3)!.lemma, 'tear');
    expect(pack.byId(4)!.lemma, 'tear');
    expect(pack.byId(5), isNull);
  });

  test('looking up the form finds the lemma', () {
    expect(pack.lookup('tore')!.entry.lemma, 'tear');
    expect(pack.lookup('zorbed'), isNull);
  });

  test('pointers are not learnable cards in the database list', () {
    expect(pack.catalogWords.map((w) => w.lemma), ['tear']);
    expect(pack.size, 1);
    expect(pack.detailFor(pack.byId(3)!).word, 'tear');
  });
}