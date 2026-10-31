// 卡 #862 (問題回報 #1117, Mac M461): the onboarding row for French under an
// English interface said 「法文目前只提供英文母語」 in Chinese. Every row label
// and Semantics label built from catalog copy must come out in the interface
// language, and Traditional Chinese must stay as it is.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

bool _hasCjk(String s) => RegExp(r'[一-鿿]').hasMatch(s);

void main() {
  test('the French reason is translated in English and French', () {
    expect(translateUi('法文目前只提供英文母語', 'en'),
        'French is currently only available with English as the native language');
    expect(translateUi('法文目前只提供英文母語', 'fr'), contains('Le français'));
    expect(translateUi('法文目前只提供英文母語', 'zh-TW'), '法文目前只提供英文母語');
  });

  test('a row label joined with its note is translated part by part', () {
    expect(translateUi('法文（Français），法文目前只提供英文母語', 'en'),
        'French (Français), French is currently only available with English as the native language');
    expect(translateUi('英文（English），第一階段尚未提供詞庫', 'en'),
        isNot(contains('第一階段')));
  });

  test('selected and known suffixes are translated', () {
    expect(translateUi('入門（A1）（已選）', 'en'), 'Beginner (A1) (selected)');
    expect(translateUi('入門（A1）（已選）', 'fr'),
        'Débutant (A1) (sélectionné)');
    expect(translateUi('apple（認得）', 'en'), 'apple (known)');
  });

  test('onboarding French row copy has no Chinese in English or French', () {
    for (final lang in ['en', 'fr']) {
      for (final source in [
        '法文目前只提供英文母語',
        '法文目前只提供英文母語，已切回英文',
        '你對英文熟悉嗎？',
        '你對法文熟悉嗎？',
      ]) {
        expect(_hasCjk(translateUi(source, lang)), isFalse,
            reason: '$source ($lang)');
      }
    }
  });
}
