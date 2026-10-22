import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/services/learning_content.dart';

/// 卡 #516: a form's own meaning is joined to its labels as one string —
/// dormant（現在分詞・形容詞：asleep）— which the catalog never held whole.
void main() {
  final cjk = RegExp(r'[一-鿿]');
  const posCodes = [
    'noun', 'verb', 'adj', 'adv', 'pron', 'prep', 'conj', 'intj', 'det',
    'num', 'phrase', 'proper_noun', 'x',
  ];
  const fields = [
    'plural', 'verb_past', 'present participle', 'past participle',
    'third-person singular', 'comparative', 'superlative', 'fr_plural',
    'fr_feminine', 'fr_feminine_plural', 'fr_past_participle',
    'fr_present_participle', 'fr_imperfect_1s', 'fr_future_1s',
    'fr_present_3p', 'other',
  ];

  test('every form label with its own meaning translates', () {
    for (final lang in ['en', 'fr']) {
      for (final f in fields) {
        for (final p in posCodes) {
          final label = '${formLabel(f)}・${posLabel(p)}：asleep；'
              '${posLabel('noun')}：sleeper';
          final out = translateUi('dormant（$label）', lang);
          expect(cjk.hasMatch(out), isFalse, reason: '$lang $f $p → $out');
        }
      }
    }
  });

  test('the case from the report', () {
    expect(translateUi('dormant（現在分詞・形容詞：asleep）', 'en'),
        contains('asleep'));
    expect(translateUi('dormant（現在分詞・形容詞：asleep）', 'zh-TW'),
        'dormant（現在分詞・形容詞：asleep）');
  });
}
