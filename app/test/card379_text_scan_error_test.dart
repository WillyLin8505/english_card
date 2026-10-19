import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/text_scan.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(TextScan.channel, null);
    TextScan.recognizer = null;
  });

  test('a platform text-reader failure shows a plain sentence (問題回報 #377)',
      () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(TextScan.channel, (call) async {
      throw PlatformException(
          code: 'vision', message: 'Failed to create espresso context.');
    });
    await expectLater(
      TextScan.recognize(Uint8List.fromList([1, 2, 3])),
      throwsA(isA<TaggingApiException>().having(
          (e) => e.message, 'message', TextScan.readFailedMessage)),
    );
  });

  test('the text-reader failure message has no English platform text', () {
    expect(TextScan.readFailedMessage, isNot(contains('espresso')));
    expect(TextScan.readFailedMessage,
        isNot(matches(RegExp(r'[A-Za-z]{3,}'))));
    expect(TextScan.readFailedMessage, contains('請換一張照片'));
  });
}
