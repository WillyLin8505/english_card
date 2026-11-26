import 'dart:ui' as ui;

import 'package:flutter_test/flutter_test.dart';

import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/spot_crop.dart';

void main() {
  testWidgets('cropAround decodes a large shot scaled and still crops',
      (tester) async {
    await tester.runAsync(() async {
      final rec = ui.PictureRecorder();
      ui.Canvas(rec).drawRect(const ui.Rect.fromLTWH(0, 0, 3000, 2000),
          ui.Paint()..color = const ui.Color(0xFF336699));
      final img = await rec.endRecording().toImage(3000, 2000);
      final png = (await img.toByteData(format: ui.ImageByteFormat.png))!
          .buffer
          .asUint8List();
    await ui.instantiateImageCodec(png);
    final out = await cropAround(png, const LabelPoint(0.5, 0.5));
      final codec = await ui.instantiateImageCodec(out);
      final crop = (await codec.getNextFrame()).image;
      expect(crop.width, 640);
      expect(crop.height, 640);
    });
  });
}
