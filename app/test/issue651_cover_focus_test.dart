import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';

/// 問題回報 #651: on a review photo shown with BoxFit.cover, a spot in the
/// cropped-away part of the photo put the blue dot outside the frame. The
/// photo now moves so the spot is in view, and the dot stays on its object.
Photo photo(int w, int h) => Photo(
    id: 'p',
    title: '',
    takenAt: testNow,
    createdAt: testNow,
    networkUrl: 'http://127.0.0.1:1/x.jpg',
    width: w,
    height: h);

void main() {
  // A landscape photo in a portrait frame: most of its sides are cropped.
  final wide = photo(400, 300);
  const box = Size(150, 300);
  const edge = LabelPoint(0.95, 0.5);

  group('CoverGeometry.focusing', () {
    test('centred, a spot at x = 0.95 lands outside the frame', () {
      final at = CoverGeometry(box, wide).toBox(edge);
      expect(at.dx, greaterThan(box.width));
    });

    test('moves the photo so the spot is inside, on the same object', () {
      final a = CoverGeometry.focusing(box, wide, edge);
      final geo = CoverGeometry(box, wide, alignment: a);
      final at = geo.toBox(edge);
      // Too near the edge for a full margin: the photo's right edge is
      // shown, and the spot is 5% of 400 px = 20 px inside the frame.
      expect(at.dx, closeTo(130, 0.01));
      expect(at.dy, closeTo(150, 0.01));
      expect(a.x, 1);
      // Not clamped to the edge: the box point maps back to the same spot
      // of the image.
      final back = geo.fromBox(at);
      expect(back.x, closeTo(edge.x, 1e-9));
      expect(back.y, closeTo(edge.y, 1e-9));
      // The photo still covers the frame (no empty edge).
      expect(geo.offset.dx, lessThanOrEqualTo(0));
      expect(geo.offset.dx + 400 * geo.scale, greaterThanOrEqualTo(box.width));
    });

    test('a cropped spot with room moves the photo just enough', () {
      const spot = LabelPoint(0.75, 0.5); // centred: 300 − 125 = 175 > 150
      expect(CoverGeometry(box, wide).toBox(spot).dx, greaterThan(box.width));
      final a = CoverGeometry.focusing(box, wide, spot);
      final at = CoverGeometry(box, wide, alignment: a).toBox(spot);
      expect(at.dx, closeTo(box.width - 40, 0.01)); // the 40 px margin
    });

    test('a spot already in view keeps the photo centred', () {
      expect(CoverGeometry.focusing(box, wide, const LabelPoint(0.5, 0.2)),
          Alignment.center);
      expect(CoverGeometry.focusing(box, wide, const LabelPoint(0.45, 0.9)),
          Alignment.center);
    });

    test('spot at the very edge shows that edge of the photo', () {
      expect(CoverGeometry.focusing(box, wide, const LabelPoint(1, 0.5)).x, 1);
      expect(CoverGeometry.focusing(box, wide, const LabelPoint(0, 0.5)).x, -1);
    });

    test('portrait photo in a wide frame moves vertically', () {
      const wideBox = Size(300, 120);
      final tall = photo(300, 400);
      const low = LabelPoint(0.5, 0.97);
      expect(CoverGeometry(wideBox, tall).toBox(low).dy,
          greaterThan(wideBox.height));
      final a = CoverGeometry.focusing(wideBox, tall, low);
      final at = CoverGeometry(wideBox, tall, alignment: a).toBox(low);
      expect(at.dy, inInclusiveRange(0, wideBox.height));
      expect(a.x, 0);
    });
  });

  group('PinnedPhoto keeps its focus in the frame', () {
    Future<Offset> pump(WidgetTester tester, Widget Function() child) async {
      await pumpApp(tester,
          home: Center(
              child: SizedBox(
                  key: const ValueKey('box'),
                  width: box.width,
                  height: box.height,
                  child: child())));
      await tester.pump();
      return tester.getTopLeft(find.byKey(const ValueKey('box')));
    }

    testWidgets('review front: the target ring and the photo move together',
        (tester) async {
      final origin = await pump(
          tester,
          () => PinnedPhoto(
              photo: wide,
              pins: const [],
              focus: edge,
              overlay: TargetRing(photo: wide, anchor: edge)));
      final ring =
          tester.getCenter(find.byKey(const ValueKey('target-ring'))) - origin;
      expect(ring.dx, inInclusiveRange(0, box.width));
      expect(ring.dy, closeTo(150, 0.01));
      // The image is drawn with the alignment that puts the spot there.
      final image = tester.widget<Image>(find.byType(Image));
      final a = CoverGeometry.focusing(box, wide, edge);
      expect(image.alignment, a);
      final at = CoverGeometry(box, wide, alignment: a).toBox(edge);
      expect(ring.dx, closeTo(at.dx, 0.01));
    });

    testWidgets('one label: the photo follows the label without a focus',
        (tester) async {
      await pump(
          tester,
          () => PinnedPhoto(photo: wide, pins: const [
                PinData(id: 'a', anchor: edge, word: 'apple', zh: '蘋果'),
              ]));
      final image = tester.widget<Image>(find.byType(Image));
      expect(image.alignment, CoverGeometry.focusing(box, wide, edge));
      expect((image.alignment as Alignment).x, greaterThan(0));
    });

    testWidgets('no focus: centred as before', (tester) async {
      await pump(
          tester,
          () => PinnedPhoto(
              photo: wide,
              pins: const [],
              overlay: TargetRing(photo: wide, anchor: edge)));
      expect(tester.widget<Image>(find.byType(Image)).alignment,
          Alignment.center);
    });
  });
}
