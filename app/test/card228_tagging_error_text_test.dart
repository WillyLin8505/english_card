// 設定 → 測試連線 / 照片辨識失敗時給學習者看的文字（卡 #228 第 3 輪）：
// 伺服器回 404、500 或不是 JSON 時，不能把英文原文「health check failed: …」
// 直接顯示出來。
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/services/tagging_service.dart';

void main() {
  const url = 'http://example.test/tag';

  Future<String> healthError(int status, String body) async {
    final service = TaggingService(
      endpoint: Uri.parse(url),
      apiKey: 'k',
      client: MockClient((_) async => http.Response(body, status)),
    );
    try {
      await service.checkHealth();
    } catch (e) {
      return describeTaggingError(e, url);
    }
    fail('checkHealth should have thrown');
  }

  test('a wrong URL (404) says so in Chinese', () async {
    final text = await healthError(404, 'Not Found');
    expect(text, contains('找不到 AI 辨識服務'));
    expect(text, contains(url));
    expect(text, isNot(contains('health check')));
  });

  test('any other server error shows the code, not the English body', () async {
    final text = await healthError(500, 'Internal Server Error');
    expect(text, contains('代碼 500'));
    expect(text, isNot(contains('Internal Server Error')));
  });

  test('known codes keep their own messages', () {
    expect(describeTaggingError(TaggingApiException('x', statusCode: 401), url),
        contains('API Key 不正確'));
    expect(describeTaggingError(TaggingApiException('x', statusCode: 503), url),
        contains('還在啟動'));
    expect(describeTaggingError(TaggingApiException('本機訊息'), url), '本機訊息');
  });
}
