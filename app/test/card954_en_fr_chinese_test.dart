import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

void main() {
  test('card 954: pill and update notice have no Chinese in en/fr', () {
    final han = RegExp(r'[一-鿿]');
    for (final lang in ['en', 'fr']) {
      expect(han.hasMatch(translateUi('下載的相片冊', lang)), isFalse);
      final t = translateUi('詞庫已更新：2999 個字補上{N}意思、音標、真人發音、例句', lang,
          learning: 'fr');
      expect(han.hasMatch(t), isFalse, reason: t);
    }
  });
}
