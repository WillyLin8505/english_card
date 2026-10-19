import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

void main() {
  test('photoErrorMessage never leaks the raw exception', () {
    final cases = {
      Exception('PlatformException(photo_access_denied, permission denied)'):
          '沒有相機或相簿權限，請到手機設定開啟後再試。',
      Exception('FileSystemException: No space left (errno = 28) ENOSPC'):
          '手機儲存空間不足，請清出空間後再試。',
      const FormatException('bad bytes'): '這張照片的格式無法使用，請換一張。',
      Exception('boom'): '發生問題，請再試一次。',
    };
    cases.forEach((error, expected) {
      final msg = photoErrorMessage(error);
      expect(msg, expected);
      expect(msg, isNot(contains('Exception')));
    });
  });
}
