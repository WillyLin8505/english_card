import 'package:flutter_test/flutter_test.dart';
import 'package:english_card/services/label_service.dart';

void main() {
  group('LabelService', () {
    group('Request encoding', () {
      test('requestEncoding returns valid enum value', () {
        final encoding = LabelService.requestEncoding;
        expect(
          encoding,
          anyOf(
            LabelRequestEncoding.rawJpeg,
            LabelRequestEncoding.multipart,
          ),
        );
      });

      test('LabelRequestEncoding enum has correct values', () {
        expect(LabelRequestEncoding.values.length, equals(2));
        expect(LabelRequestEncoding.values, contains(LabelRequestEncoding.rawJpeg));
        expect(LabelRequestEncoding.values, contains(LabelRequestEncoding.multipart));
      });
    });
  });
}
