import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

/// 問題回報 #664: what the learner is looking at when they tap 意見回饋, so the
/// report shows the problem. A PNG at [scale] of the logical size (full size:
/// the server takes 2 MB per report since M132), smaller if over [maxBytes].
/// Null when nothing could be captured (tests, web).
Future<Uint8List?> captureScreen(GlobalKey boundary,
    {double scale = 1.0, int maxBytes = 1300 * 1024}) async {
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

/// The whole app (FeedbackOverlay wraps it in a RepaintBoundary with this
/// key): what every report's screenshot shows (問題回報 #664 #669).
final appScreenKey = GlobalKey(debugLabel: 'app-screen');

/// [captureScreen] of the whole app, given up after [wait] so a stalled
/// capture never holds a report form back.
// 0.8 s was too short on a photo-heavy page (問題回報 #669: the reports
// from 照片詳情 came without one); a big PNG is shrunk and encoded again.
Future<Uint8List?> captureAppScreen(
        {Duration wait = const Duration(milliseconds: 2500)}) =>
    captureScreen(appScreenKey).timeout(wait, onTimeout: () => null);

/// [png] as the `screenshot` field of a report.
String screenshotField(Uint8List png) =>
    'data:image/png;base64,${base64Encode(png)}';
