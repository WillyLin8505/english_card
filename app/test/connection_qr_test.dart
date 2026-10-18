import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/connection_qr.dart';

void main() {
  test('parses a connection code and trims the fields', () {
    final qr = ConnectionQr.parse(
        '{"v":1,"taggingUrl":" https://api.willylinai.com/tag ","apiKey":" k123 "}');
    expect(qr, isNotNull);
    expect(qr!.taggingUrl, 'https://api.willylinai.com/tag');
    expect(qr.apiKey, 'k123');
  });

  test('ignores QR codes that are not connection codes', () {
    expect(ConnectionQr.parse('https://example.com'), isNull);
    expect(ConnectionQr.parse('not json'), isNull);
    expect(ConnectionQr.parse('[1,2]'), isNull);
    expect(ConnectionQr.parse('{"taggingUrl":"https://a.b","apiKey":"k"}'),
        isNull, reason: 'missing version');
    expect(ConnectionQr.parse('{"v":2,"taggingUrl":"https://a.b","apiKey":"k"}'),
        isNull, reason: 'unknown version');
    expect(ConnectionQr.parse('{"v":1,"taggingUrl":"api.x","apiKey":"k"}'),
        isNull, reason: 'url without scheme');
    expect(ConnectionQr.parse('{"v":1,"taggingUrl":"https://a.b","apiKey":" "}'),
        isNull, reason: 'empty key');
  });
}
