import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

void main() {
  test('h aspiré note translates with straight and curly apostrophes', () {
    for (final a in ["'", '’']) {
      final src = 'h aspiré：不連音、不省略（le héros，不是 l${a}héros）';
      expect(translateUi(src, 'en'), contains('no liaison'));
      expect(translateUi(src, 'fr'), contains('pas de liaison'));
    }
  });
}
