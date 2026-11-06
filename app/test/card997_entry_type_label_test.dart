import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/learning_content.dart';

void main() {
  test('entry type tags follow the UI language (card 997)', () {
    expect(typedMeaning('supermarket', 'phrase', lang: 'en'),
        '[Phrase] supermarket');
    expect(entryTypeLabel('phrasal_verb', lang: 'en'), 'Phrasal verb');
    expect(entryTypeLabel('idiom', lang: 'fr'), 'Idiome');
    expect(entryTypeLabel('collocation', lang: 'en'), 'Collocation');
    expect(entryTypeLabel('fixed_expression', lang: 'en'), 'Fixed expression');
    expect(typedMeaning('x', 'idiom'), '[慣用語] x');
  });
}
