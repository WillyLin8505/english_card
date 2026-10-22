import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';

/// 卡 #227 第 142 輪: load's 詞形變化 showed
/// loaded（形容詞：有負載的；過去式・形容詞：有負載的；過去分詞・形容詞：有負載的）.
void main() {
  test('a form with its own meaning lists the meaning once', () {
    expect(
        mergeFormLabels(
            ['形容詞：有負載的', '過去式・形容詞：有負載的', '過去分詞・形容詞：有負載的']),
        '過去式；過去分詞・形容詞：有負載的');
  });

  test('grammar-only labels are joined as before', () {
    expect(mergeFormLabels(['複數', '第三人稱單數', '']), '複數；第三人稱單數');
    expect(mergeFormLabels(['過去分詞・形容詞：被拴住的']), '過去分詞・形容詞：被拴住的');
  });

  test('different meanings are all kept', () {
    expect(mergeFormLabels(['複數', '名詞：藍調；形容詞：憂鬱的']),
        '複數・名詞：藍調；形容詞：憂鬱的');
  });
}
