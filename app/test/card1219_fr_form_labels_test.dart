import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/learning_content.dart';

void main() {
  test('card #1219: French conjugation field names get Chinese labels', () {
    expect(formLabel('fr_conditional_1s'), '條件式 je');
    expect(formLabel('fr conditional 1s'), '條件式 je');
    expect(formLabel('fr_passe_simple_3p'), '簡單過去式 ils／elles');
    expect(formLabel('fr_subjunctive_2s'), '虛擬式現在 tu');
    expect(formLabel('fr_imperative_1p'), '命令式 nous');
    expect(formLabel('fr_imperfect_3s'), '未完成過去式 il／elle');
    expect(formLabel('fr_future_2p'), '簡單將來式 vous');
    expect(formLabel('fr_past_participle_fpl'), '過去分詞 陰性複數');
    expect(formLabel('fr_conj_model'), '變位範本');
    expect(formLabel('fr_h_aspire'), '有聲 h（h aspiré）');
    expect(formLabel('unknown_field'), '變化形');
  });
}
