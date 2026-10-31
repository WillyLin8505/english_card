import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

void main() {
  const tree = LexEntry(
      id: 7, lemma: 'tree', normalized: 'tree', pos: 'noun', status: 'full');
  Map<String, dynamic> img(int n) => {
        'id': n,
        'tags': [
          {'lexeme_id': 7, 'sense_id': 1, 'review_status': 'approved'}
        ]
      };

  test('card 854: at most 5 pictures, first one kept, rest random', () {
    final catalog = [for (var i = 0; i < 40; i++) img(i)];
    final seen = <Object?>{};
    for (var s = 0; s < 20; s++) {
      final out = databaseEntryImages(catalog, tree, random: math.Random(s));
      expect(out.length, 5);
      expect(out.first['id'], 0);
      expect(out.map((i) => i['id']).toSet().length, 5);
      seen.addAll(out.map((i) => i['id']));
    }
    expect(seen.length, greaterThan(5));
  });

  test('card 854: five or fewer pictures are all shown in order', () {
    final catalog = [for (var i = 0; i < 3; i++) img(i)];
    expect(databaseEntryImages(catalog, tree).map((i) => i['id']), [0, 1, 2]);
  });
}
