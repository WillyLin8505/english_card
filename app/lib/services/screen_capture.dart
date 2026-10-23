import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

/// 問題回報 #664: what the learner is looking at when they tap 意見回饋, so the
/// report shows the problem. A small PNG (the server takes up to 256 KB per
/// report): [scale] of the logical size, smaller again if still too big.
/// Null when nothing could be captured (tests, web).
Future<Uint8List?> captureScreen(GlobalKey boundary,
    {double scale = 0.6, int maxBytes = 170 * 1024}) async {
  try {
    final box = boundary.currentContext?.findRenderObject();
    if (box is! RenderRepaintBoundary || !box.hasSize) return null;
    for (var s = scale; s >= 0.3; s -= 0.15) {
      final image = await box.toImage(pixelRatio: s);
      final data = await image.toByteData(format: ui.ImageByteFormat.png);
      image.dispose();
      if (data == null) return null;
      final bytes = data.buffer.asUint8List();
      if (bytes.length <= maxBytes) return bytes;
    }
  } catch (e) {
    debugPrint('captureScreen failed: $e');
  }
  return null;
}

/// [png] as the `screenshot` field of a report.
String screenshotField(Uint8List png) =>
    'data:image/png;base64,${base64Encode(png)}';
