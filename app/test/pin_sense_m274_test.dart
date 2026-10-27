import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

/// M274 (圖 43: open 可通行 instead of 打開的): a picture pin shows the
/// meaning of the label's sense, else of the same word's tag, else the
/// word's first meaning.
Map<String, dynamic> pack(
        {Object? labelSense, Object? tagSense = 2}) =>
    {
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'open',
          'normalized': 'open',
          'pos': 'adj',
          'status': 'full',
          'senses': [
            {'id': 1, 'native': '可通行'},
            {'id': 2, 'native': '打開的'},
            {'id': 3, 'native': '公開的'},
          ],
        },
      ],
      'catalog_images': [
        {
          'id': 43,
          'url': 'http://127.0.0.1/api/image?id=43',
          'tags': [
            {
              'lexeme_id': 1,
              if (tagSense != null) 'sense_id': tagSense,
              'review_status': 'approved',
              'cefr': 'A1',
            },
          ],
          'labels': [
            {
              'word': 'open',
              'point': [0.3, 0.4],
              'lexeme_id': 1,
              if (labelSense != null) 'sense_id': labelSense,
            },
          ],
        },
      ],
    };

String pinMeaning() =>
    databasePins(LexiconPack.instance.catalogImages.first,
            LexiconPack.instance)
        .single
        .zh;

void main() {
  tearDown(LexiconPack.instance.clear);

  test('the label sense wins', () {
    LexiconPack.instance.loadJson(pack(labelSense: 3));
    expect(pinMeaning(), '公開的');
  });

  test('no label sense: the tag sense of the same word', () {
    LexiconPack.instance.loadJson(pack());
    expect(pinMeaning(), '打開的');
  });

  test('no sense anywhere: the first meaning', () {
    LexiconPack.instance.loadJson(pack(tagSense: null));
    expect(pinMeaning(), '可通行');
  });
}
