import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/text_scan.dart';

import 'card327_text_scan_test.dart' show line;

// Card #1217 / 問題回報 #1669: English print on a photo for a French learner.
void main() {
  test('printed English becomes French nouns, never English words', () {
    final cs = frenchCandidatesFromText(
      [line('Strawberry flavor', 0.3, height: 0.1), line('the', 0.5)],
      level: 'A2',
      table: {
        'flavor': [
          ['saveur', 'B1', 'f', 3.5]
        ],
        'strawberry': [
          ['fraise', 'A1', 'f', 3.9]
        ],
      },
    );
    expect(cs.map((c) => c.word), containsAll(['saveur', 'fraise']));
    expect(cs.map((c) => c.word), isNot(contains('flavor')));
    for (final c in cs) {
      expect(c.box, isNotNull);
    }
  });
}
