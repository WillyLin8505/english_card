// Card #949 (問題回報 #1285): the 「尚缺」 hint must not show Chinese labels to a French native.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

void main() {
  final cjk = RegExp(r'[一-鿿]');
  const labels = ['{N}意思', '音標', '真人發音', '例句', '例句翻譯', '詞源'];

  test('every missing-field label has a French translation', () {
    for (final label in labels) {
      final fr = translateUi(label, 'fr', learning: 'en');
      expect(cjk.hasMatch(fr), isFalse, reason: '$label -> $fr');
    }
  });

  test('the hint template keeps translated labels verbatim', () {
    final labelsFr = [for (final l in labels) translateUi(l, 'fr', learning: 'en')];
    final hint = translateUi(
        '尚缺：${labelsFr.join('、')}。詞庫更新後會自動補上。', 'fr',
        learning: 'en');
    expect(hint.startsWith('Manquant : Sens en français'), isTrue, reason: hint);
    expect(cjk.hasMatch(hint), isFalse, reason: hint);
  });
}
