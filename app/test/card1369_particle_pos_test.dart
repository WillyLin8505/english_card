import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/services/learning_content.dart';

// 問題回報 #1803: the English-UI card back for French `ne` showed 「助詞」.
void main() {
  test('particle POS is translated for English and French UI', () {
    final zh = posLabel('particle');
    expect(zh, '助詞');
    expect(translateUi(zh, 'en'), 'Particle');
    expect(translateUi(zh, 'fr'), 'Particule');
  });
}
