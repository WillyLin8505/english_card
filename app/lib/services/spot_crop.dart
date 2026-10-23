import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import '../models/learning_card.dart';

/// 長按辨識 (問題回報 #616): the part of [image] around [at] (fractions of
/// the picture as shown) as a PNG for the recognizer — a square [fraction]
/// of the picture's shorter side, at most [maxEdge] px.
Future<Uint8List> cropAround(Uint8List image, LabelPoint at,
    {double fraction = 0.35, double maxEdge = 640}) async {
  final codec = await ui.instantiateImageCodec(image);
  final source = (await codec.getNextFrame()).image;
  codec.dispose();
  try {
    final w = source.width.toDouble(), h = source.height.toDouble();
    final side = math.min(w, h) * fraction;
    final region = cropRegion(Size2(w, h), at, side);
    final out = math.min(side, maxEdge).roundToDouble().clamp(1.0, maxEdge);
    final recorder = ui.PictureRecorder();
    ui.Canvas(recorder).drawImageRect(
        source,
        region,
        ui.Rect.fromLTWH(0, 0, out, out),
        ui.Paint()..filterQuality = ui.FilterQuality.medium);
    final picture = recorder.endRecording();
    final cropped = await picture.toImage(out.toInt(), out.toInt());
    picture.dispose();
    final data = await cropped.toByteData(format: ui.ImageByteFormat.png);
    cropped.dispose();
    return data!.buffer.asUint8List();
  } finally {
    source.dispose();
  }
}

/// A picture's width and height (kept free of Flutter's widgets layer).
class Size2 {
  final double width;
  final double height;
  const Size2(this.width, this.height);
}

/// The [side]×[side] square centred on [at], moved inside the picture.
ui.Rect cropRegion(Size2 picture, LabelPoint at, double side) {
  final s = math.min(side, math.min(picture.width, picture.height));
  final left = (at.x * picture.width - s / 2).clamp(0.0, picture.width - s);
  final top = (at.y * picture.height - s / 2).clamp(0.0, picture.height - s);
  return ui.Rect.fromLTWH(left, top, s, s);
}
