import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

// 問題回報 #1152: 設定 copy that used to stay Chinese in English / French.
void main() {
  final cjk = RegExp(r'[一-鿿]');
  const samples = [
    '播放發音失敗，請檢查音量或稍後再試',
    '字卡和複習紀錄保存在此瀏覽器。',
    '字卡和複習紀錄保存在此裝置。',
    '網頁版會自動連接這台電腦的照片辨識服務，不用填網址或金鑰。只有使用其他服務時才需要修改。連不上時照片會先排隊，恢復連線後自動處理。',
    '留空時用手機本機辨識照片；填入服務網址與金鑰則改用該服務。連不上時照片會先排隊，恢復連線後自動處理。',
    '✕ API Key 不正確',
    '✕ AI 模型沒有回應，稍後會自動重試',
    '✕ AI 辨識服務還在啟動，稍後會自動重試',
    '✕ AI 辨識服務太久沒有回應，稍後會自動重試',
    '✕ 這個網址找不到 AI 辨識服務（http://10.0.0.2:8790），請確認網址',
    '✕ AI 辨識服務回應錯誤（代碼 500），請確認網址或稍後再試',
    '✕ 連不到 AI 辨識服務（http://10.0.0.2:8790），請確認服務已啟動',
    '✓ 已連線 · qwen2.5',
    '12 個單字',
    '3 張照片',
    '已學會 5 個',
  ];

  test('settings copy has no Chinese left in English or French', () {
    for (final source in samples) {
      for (final language in const ['en', 'fr']) {
        final out = translateUi(source, language);
        expect(cjk.hasMatch(out), isFalse, reason: '$language: $source → $out');
      }
    }
  });

  test('settings copy keeps Traditional Chinese for zh-TW', () {
    for (final source in samples) {
      expect(translateUi(source, 'zh-TW'), source);
    }
  });

  test('catalog keys added for 問題回報 #1152 exist', () {
    expect(uiCatalog.containsKey('播放發音失敗，請檢查音量或稍後再試'), isTrue);
    expect(uiCatalog.containsKey('字卡和複習紀錄保存在此裝置。'), isTrue);
  });
}
