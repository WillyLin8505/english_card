// 問題回報 #1843: labels on the photo show one short meaning.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/learning_content.dart';

void main() {
  test('short meanings stay, long glosses give one short piece', () {
    expect(shortLabelMeaning('鍵盤'), '鍵盤');
    expect(shortLabelMeaning('監督器；顯示器'), '監督器；顯示器'); // 7 ≤ 8: kept
    expect(shortLabelMeaning('一家人；戶'), '一家人；戶');
    expect(shortLabelMeaning('衣服；衣著、衣著打扮的總稱'), '衣服');
    expect(shortLabelMeaning('（文）新鮮的、青翠的、草木茂盛的樣子'), '新鮮的');
    final fuzzy = shortLabelMeaning('覆蓋著絨毛或大量類似地毯或許多玩偶的細小起數纖維；模糊不清或不精確的');
    expect(fuzzy.runes.length, lessThanOrEqualTo(9));
  });
}
