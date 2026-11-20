import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

// 問題回報 #1686 (Mac iPad check of card #1218): the 精簡字典 badge and the
// 已在單字本 button showed Chinese in the English and French UI.
void main() {
  const badge = '基本資料（精簡字典）：連網後會補上例句、關聯詞與圖片。';

  test('basic-entry badge is fully translated for en and fr', () {
    for (final lang in ['en', 'fr']) {
      final out = translateUi(badge, lang);
      expect(RegExp(r'[一-鿿]').hasMatch(out), isFalse, reason: out);
    }
    expect(translateUi(badge, 'en'), startsWith('Basic entry'));
  });

  test('已在單字本 is translated for en and fr', () {
    expect(translateUi('已在單字本', 'en'), 'Already in My words');
    expect(translateUi('已在單字本', 'fr'), 'Déjà dans Mes mots');
  });
}
