import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

/// Card #780: the review card's picture lookup is a table, not a scan of the
/// whole catalog per card.
void main() {
  test('catalog lookups by picture id and by approved lexeme', () {
    final pack = LexiconPack();
    pack.catalogImages = [
      for (var i = 0; i < 30000; i++)
        {
          'id': i,
          'url': 'u$i',
          'status': 'ready',
          'tags': [
            {'lexeme_id': i % 3000, 'review_status': 'approved'},
            {'lexeme_id': 99999, 'review_status': 'pending'},
          ],
        },
    ];
    final sw = Stopwatch()..start();
    for (var l = 0; l < 3000; l++) {
      expect(pack.approvedImagesOf(l).length, 10);
    }
    expect(pack.approvedImagesOf(99999), isEmpty);
    expect(pack.catalogImageByDbId('db-7')!['id'], 7);
    expect(pack.catalogImageByDbId('db-x'), isNull);
    expect(sw.elapsedMilliseconds, lessThan(1500));
    // A reloaded catalog is re-indexed.
    pack.catalogImages = [
      {'id': 1, 'url': 'a', 'status': 'ready', 'tags': [{'lexeme_id': 5, 'review_status': 'approved'}]},
    ];
    expect(pack.approvedImagesOf(5).length, 1);
    expect(pack.approvedImagesOf(1), isEmpty);
  });
}
