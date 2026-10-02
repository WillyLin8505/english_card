import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/widgets/mobile/pin_layout.dart';

void main() {
  const box = Size(343, 320);
  const badge = Size(92, 24);

  List<PinPlacement> place(List<Offset> anchors) => layoutPins(
      [for (final (i, a) in anchors.indexed) PinItem('p$i', a, badge)], box);

  void expectClean(List<PinPlacement> out, List<Offset> anchors) {
    final area = Offset.zero & box;
    for (final p in out) {
      expect(area.contains(p.badge.topLeft) && area.contains(p.badge.bottomRight - const Offset(1, 1)),
          isTrue,
          reason: '${p.id} stays inside the photo');
      for (final d in anchors) {
        expect(p.badge.inflate(4).contains(d), isFalse, reason: '${p.id} covers a dot at $d');
      }
      for (final q in out) {
        if (identical(p, q)) continue;
        expect(p.badge.overlaps(q.badge), isFalse, reason: '${p.id} overlaps ${q.id}');
      }
    }
  }

  test('labels on objects crowded in the middle spread out without overlapping', () {
    final anchors = [
      const Offset(160, 150), const Offset(180, 158), const Offset(170, 172),
      const Offset(150, 166), const Offset(190, 140), const Offset(165, 135),
    ];
    final out = place(anchors);
    expectClean(out, anchors);
    // Spread: the badges cover much more of the photo than the objects do.
    final spread = out.map((p) => p.badge).reduce((a, b) => a.expandToInclude(b));
    expect(spread.width, greaterThan(200));
    expect(spread.height, greaterThan(130));
    // Balanced: badges on both sides and both halves of the cluster.
    final left = out.where((p) => p.badge.center.dx < 170).length;
    final top = out.where((p) => p.badge.center.dy < 155).length;
    expect(left, inInclusiveRange(2, 4));
    expect(top, inInclusiveRange(2, 4));
    // Short leader lines: each label stays near its object.
    for (final p in out) {
      expect(p.leaderLength, lessThan(90));
    }
    // Not packed edge to edge: a clear gap between any two labels.
    for (final p in out) {
      for (final q in out) {
        if (identical(p, q)) continue;
        expect(p.badge.inflate(4).overlaps(q.badge), isFalse,
            reason: '${p.id} and ${q.id} are less than 4px apart');
      }
    }
  });

  test('objects near the edges keep their labels inside', () {
    final anchors = [
      const Offset(8, 8), const Offset(335, 10), const Offset(5, 312), const Offset(338, 315),
      const Offset(170, 4),
    ];
    expectClean(place(anchors), anchors);
  });

  test('labels keep off controls drawn over the photo', () {
    const dial = Rect.fromLTWH(-3, 258, 52, 58);
    final anchors = [const Offset(40, 300), const Offset(60, 280), const Offset(30, 250)];
    final out = layoutPins(
        [for (final (i, a) in anchors.indexed) PinItem('p$i', a, badge)], box,
        avoid: const [dial]);
    expectClean(out, anchors);
    for (final p in out) {
      expect(p.badge.overlaps(dial), isFalse, reason: '${p.id} is under the dial');
    }
  });

  test('a single label sits right by its object, and layout is deterministic', () {
    final one = place([const Offset(120, 200)]);
    expect(one.single.leaderLength, lessThan(30));
    final anchors = [const Offset(100, 100), const Offset(110, 104), const Offset(250, 220)];
    expect([for (final p in place(anchors)) p.badge], [for (final p in place(anchors)) p.badge]);
  });
}
