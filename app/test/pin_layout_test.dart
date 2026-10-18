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

  test('a label wider than the photo is narrowed to fit inside it (#61)', () {
    const landscape = Size(343, 230);
    final out = layoutPins([
      const PinItem('long', Offset(170, 120), Size(420, 22)), // "semantic interpretations"
      const PinItem('cup', Offset(60, 60), badge),
    ], landscape);
    final long = out.firstWhere((p) => p.id == 'long');
    expect(long.badge.width, lessThanOrEqualTo(landscape.width - 12));
    expect(long.badge.left, greaterThanOrEqualTo(0));
    expect(long.badge.right, lessThanOrEqualTo(landscape.width));
  });

  test('wide labels on a short photo stay clear of every dot (#61)', () {
    const landscape = Size(343, 230);
    // Cache photos whose first five labels are wider than half the photo
    // and whose dots share one column or sit on the bottom edge.
    final cases = <List<PinItem>>[
      // 45a5c580b2 橫式 — sunlit area used to sit on its own dot.
      [
        const PinItem('dirt', Offset(157, 44), Size(177, 22)),
        const PinItem('rock', Offset(167, 97), Size(165, 22)),
        const PinItem('post', Offset(305, 150), Size(189, 22)),
        const PinItem('sunlit', Offset(171, 202), Size(189, 22)),
        const PinItem('shadow', Offset(143, 115), Size(261, 22)),
      ],
      // 351a6f522a 橫式 — vestment covered itself, cross leader was 177px.
      [
        const PinItem('font', Offset(154, 143), Size(225, 22)),
        const PinItem('robe', Offset(130, 71), Size(237, 22)),
        const PinItem('incense', Offset(178, 104), Size(225, 22)),
        const PinItem('cross', Offset(185, 14), Size(273, 22)),
        const PinItem('vestment', Offset(247, 87), Size(285, 22)),
      ],
      // 02855cfd32 橫式 — five dots in the top-left corner, brown leader 146px.
      [
        const PinItem('wooden', Offset(86, 7), Size(149, 22)),
        const PinItem('rustic', Offset(89, 9), Size(139, 22)),
        const PinItem('weathered', Offset(93, 12), Size(165, 22)),
        const PinItem('dark', Offset(96, 14), Size(145, 22)),
        const PinItem('brown', Offset(100, 16), Size(117, 22)),
      ],
      // 2a9505d5d0 橫式 — one column of dots; badges cannot dodge them sideways.
      [
        const PinItem('undulating', Offset(172, 69), Size(177, 22)),
        const PinItem('radiating', Offset(172, 92), Size(165, 22)),
        const PinItem('concentric', Offset(172, 46), Size(177, 22)),
        const PinItem('glistening', Offset(172, 138), Size(177, 22)),
        const PinItem('textured', Offset(172, 23), Size(163, 22)),
      ],
      // 78f90762d1 橫式 — same column, wider badges. One cover is forced.
      [
        const PinItem('oxidation', Offset(172, 138), Size(165, 22)),
        const PinItem('thermoluminescence', Offset(172, 92), Size(273, 22)),
        const PinItem('chemiluminescence', Offset(172, 69), Size(261, 22)),
        const PinItem('pyrolysis', Offset(172, 46), Size(165, 22)),
        const PinItem('thermochromic', Offset(172, 23), Size(213, 22)),
      ],
    ];
    final limit = landscape.shortestSide * 0.6;
    for (final (caseIndex, items) in cases.indexed) {
      final out = layoutPins(items, landscape);
      expect(out, hasLength(items.length));
      // The last case's badges are all too wide to sit beside the centre
      // dots, and five of them do not fit in the four clear shelves.
      final coverBudget = caseIndex == cases.length - 1 ? 1 : 0;
      var covers = 0;
      for (final p in out) {
        expect(p.badge.left, greaterThanOrEqualTo(-0.5), reason: p.id);
        expect(p.badge.top, greaterThanOrEqualTo(-0.5), reason: p.id);
        expect(p.badge.right, lessThanOrEqualTo(landscape.width + 0.5), reason: p.id);
        expect(p.badge.bottom, lessThanOrEqualTo(landscape.height + 0.5), reason: p.id);
        expect(p.leaderLength, lessThanOrEqualTo(limit), reason: '${p.id} leader ${p.leaderLength}');
        for (final it in items) {
          if (p.badge.inflate(2).contains(it.anchor)) covers++;
        }
        for (final q in out) {
          if (identical(p, q)) continue;
          expect(p.badge.overlaps(q.badge), isFalse, reason: '${p.id} overlaps ${q.id}');
        }
      }
      expect(covers, lessThanOrEqualTo(coverBudget), reason: 'case $caseIndex');
    }
  });

  test('five crowded objects on a landscape photo keep every dot visible (#61)', () {
    const landscape = Size(343, 230);
    final anchors = [
      const Offset(150, 110), const Offset(175, 118), const Offset(160, 140),
      const Offset(190, 100), const Offset(140, 128),
    ];
    final out = layoutPins(
        [for (final (i, a) in anchors.indexed) PinItem('p$i', a, const Size(104, 24))], landscape);
    for (final p in out) {
      for (final d in anchors) {
        expect(p.badge.inflate(2).contains(d), isFalse, reason: '${p.id} covers a dot at $d');
      }
    }
  });
}
