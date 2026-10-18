import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/web_fonts.dart';

/// 問題回報 #25: the web build loads its bundled Chinese font before the
/// first frame, and a missing or slow font never blocks the app.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final base = Uri.parse('http://127.0.0.1:8123/');

  test('both weights come from the web build next to the app', () async {
    final asked = <Uri>[];
    await loadWebCjkFont(base: base, fetch: (uri) async {
      asked.add(uri);
      return null; // not served: nothing to register
    });
    expect(asked.map((u) => u.toString()), [
      'http://127.0.0.1:8123/fonts/NotoSansTC-Regular.ttf',
      'http://127.0.0.1:8123/fonts/NotoSansTC-Bold.ttf',
    ]);
  });

  test('a failed or hanging download never stops the app from starting',
      () async {
    await loadWebCjkFont(
        base: base, fetch: (_) async => throw Exception('offline'));
    await loadWebCjkFont(
        base: base,
        timeout: const Duration(milliseconds: 50),
        fetch: (_) => Future<Uint8List?>.delayed(const Duration(seconds: 5)));
  });
}
