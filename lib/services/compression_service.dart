import 'dart:typed_data';
import 'package:image/image.dart' as img;

class CompressionResult {
  final Uint8List bytes;
  final int width;
  final int height;
  final int quality;

  CompressionResult({
    required this.bytes,
    required this.width,
    required this.height,
    required this.quality,
  });
}

class CompressionService {
  static const int maxEdge = 1280;
  static const int maxBytes = 500 * 1024; // 500KB
  static const int initialQuality = 75;
  static const int minQuality = 30;

  static Future<CompressionResult> compressImage(Uint8List imageBytes) async {
    final decoded = img.decodeImage(imageBytes);
    if (decoded == null) {
      throw CompressionException('無法解碼圖片');
    }

    final resized = _resizeToMaxEdge(decoded);
    return _compressToTargetSize(resized);
  }

  static img.Image _resizeToMaxEdge(img.Image image) {
    final width = image.width;
    final height = image.height;

    if (width <= maxEdge && height <= maxEdge) {
      return image;
    }

    final aspectRatio = width / height;
    int newWidth;
    int newHeight;

    if (width > height) {
      newWidth = maxEdge;
      newHeight = (maxEdge / aspectRatio).round();
    } else {
      newHeight = maxEdge;
      newWidth = (maxEdge * aspectRatio).round();
    }

    return img.copyResize(image, width: newWidth, height: newHeight);
  }

  static CompressionResult _compressToTargetSize(img.Image image) {
    int quality = initialQuality;

    while (quality >= minQuality) {
      final bytes = Uint8List.fromList(img.encodeJpg(image, quality: quality));

      if (bytes.length <= maxBytes) {
        return CompressionResult(
          bytes: bytes,
          width: image.width,
          height: image.height,
          quality: quality,
        );
      }

      quality -= 5;
    }

    final bytes = Uint8List.fromList(img.encodeJpg(image, quality: minQuality));
    return CompressionResult(
      bytes: bytes,
      width: image.width,
      height: image.height,
      quality: minQuality,
    );
  }

  static bool validateConstraints(CompressionResult result) {
    return result.width <= maxEdge &&
        result.height <= maxEdge &&
        result.bytes.length <= maxBytes;
  }
}

class CompressionException implements Exception {
  final String message;
  CompressionException(this.message);

  @override
  String toString() => 'CompressionException: $message';
}
