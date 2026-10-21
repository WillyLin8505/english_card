import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/services/learning_content.dart';

void main() {
  test('French grammar labels translate for native en', () {
    expect(translateUi(formLabel('fr present 3p'), 'en'), 'present ils／elles');
    expect(translateUi(frenchGenderLabel('m'), 'en'), 'masculine noun');
    expect(translateUi('un exemple（陽性名詞）', 'en'), 'un exemple（masculine noun）');
    expect(translateUi('動詞・名詞', 'en'), 'Verb・Noun');
    expect(translateUi('顯示更多（3）', 'en'), 'Show more (3)');
    expect(translateUi('第 21 / 26 張　·　左右滑動換照片', 'en'),
        'Photo 21 of 26 · swipe to change photo');
    expect(translateUi('最近 7 天（每日）：0 · 20', 'en'),
        'Last 7 days (daily): 0 · 20');
    expect(translateUi('動詞・名詞', 'zh-TW'), '動詞・名詞');
  });
}
