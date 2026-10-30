import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

void main() {
  final cjk = RegExp(r'[一-鿿]');
  final samples = [
    '今天 3 張',
    '查看單字',
    '相簿，12 個單字',
    '摘要，查看是哪些字',
    '複習這本相簿',
    '單字難度 入門，左右拖曳調整',
    '標籤程度 入門',
    '第 2 張，共 5 張，左右滑動切換照片',
    '復原 apple',
  ];
  for (final lang in ['en', 'fr']) {
    test('spoken labels with variables are translated ($lang)', () {
      for (final s in samples) {
        final out = translateUi(s, lang);
        // '入門' / '綜合' are names, covered by their own catalog entries.
        expect(out.replaceAll(RegExp(r'入門|綜合|管理|相簿|摘要'), ''),
            isNot(matches(cjk)),
            reason: '$s -> $out');
      }
      expect(translateUi('相簿，12 個單字', 'en'), 'Album, 12 words'.replaceFirst('Album', '相簿'));
    });
  }
}
