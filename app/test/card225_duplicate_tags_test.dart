import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';

/// 卡 #225 第 97 輪: a sense remap (sense_fallback) left 44 tags in the pack
/// with the same lexeme + sense twice on one picture, so the picture's tag
/// list showed e.g. 「pile · 堆起」 twice. One tag per word sense.
void main() {
  test('a picture lists each word sense once', () {
    final image = {
      'id': 1,
      'tags': [
        {'lexeme_id': 5, 'sense_id': 50, 'review_status': 'approved'},
        {
          'lexeme_id': 5,
          'sense_id': 50,
          'review_status': 'approved',
          'sense_id_before': 51,
          'sense_fallback': true
        },
        {'lexeme_id': 5, 'sense_id': 52, 'review_status': 'approved'},
        {'lexeme_id': 6, 'sense_id': 60, 'review_status': 'pending'},
      ],
    };
    final tags = databaseImageTags(image);
    expect([for (final t in tags) (t['lexeme_id'], t['sense_id'])],
        [(5, 50), (5, 52)]);
  });
}
