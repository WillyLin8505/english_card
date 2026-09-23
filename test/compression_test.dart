import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:english_card/services/compression_service.dart';

void main() {
  group('CompressionService', () {
    test('should resize image with width > 1280 to max 1280 width', () async {
      final image = img.Image(width: 2000, height: 1500);
      img.fill(image, color: img.ColorRgb8(100, 150, 200));
      final bytes = Uint8List.fromList(img.encodePng(image));

      final result = await CompressionService.compressImage(bytes);

      expect(result.width, lessThanOrEqualTo(CompressionService.maxEdge));
      expect(result.height, lessThanOrEqualTo(CompressionService.maxEdge));
    });

    test('should resize image with height > 1280 to max 1280 height', () async {
      final image = img.Image(width: 1000, height: 2000);
      img.fill(image, color: img.ColorRgb8(100, 150, 200));
      final bytes = Uint8List.fromList(img.encodePng(image));

      final result = await CompressionService.compressImage(bytes);

      expect(result.width, lessThanOrEqualTo(CompressionService.maxEdge));
      expect(result.height, lessThanOrEqualTo(CompressionService.maxEdge));
      expect(result.height, equals(CompressionService.maxEdge));
    });

    test('should not resize image smaller than 1280', () async {
      final image = img.Image(width: 800, height: 600);
      img.fill(image, color: img.ColorRgb8(100, 150, 200));
      final bytes = Uint8List.fromList(img.encodePng(image));

      final result = await CompressionService.compressImage(bytes);

      expect(result.width, equals(800));
      expect(result.height, equals(600));
    });

    test('should produce JPEG output', () async {
      final image = img.Image(width: 500, height: 500);
      img.fill(image, color: img.ColorRgb8(100, 150, 200));
      final bytes = Uint8List.fromList(img.encodePng(image));

      final result = await CompressionService.compressImage(bytes);

      // JPEG magic bytes: 0xFF 0xD8
      expect(result.bytes[0], equals(0xFF));
      expect(result.bytes[1], equals(0xD8));
    });

    test('should validate constraints correctly', () {
      final validResult = CompressionResult(
        bytes: Uint8List(400 * 1024), // 400KB
        width: 1280,
        height: 960,
        quality: 75,
      );
      expect(CompressionService.validateConstraints(validResult), isTrue);

      final oversizedResult = CompressionResult(
        bytes: Uint8List(600 * 1024), // 600KB - over limit
        width: 1280,
        height: 960,
        quality: 75,
      );
      expect(CompressionService.validateConstraints(oversizedResult), isFalse);

      final tooWideResult = CompressionResult(
        bytes: Uint8List(400 * 1024),
        width: 1500, // over 1280
        height: 960,
        quality: 75,
      );
      expect(CompressionService.validateConstraints(tooWideResult), isFalse);
    });

    test('should maintain aspect ratio when resizing', () async {
      final image = img.Image(width: 2560, height: 1920); // 4:3 ratio
      img.fill(image, color: img.ColorRgb8(100, 150, 200));
      final bytes = Uint8List.fromList(img.encodePng(image));

      final result = await CompressionService.compressImage(bytes);

      final originalRatio = 2560 / 1920;
      final newRatio = result.width / result.height;
      expect((originalRatio - newRatio).abs(), lessThan(0.02));
    });

    test('should throw on invalid image data', () async {
      final invalidBytes = Uint8List.fromList([0, 1, 2, 3, 4, 5]);

      expect(
        () => CompressionService.compressImage(invalidBytes),
        throwsA(isA<CompressionException>()),
      );
    });
  });
}
