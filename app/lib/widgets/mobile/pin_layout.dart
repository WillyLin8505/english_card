import 'dart:math' as math;
import 'dart:ui';

/// One label to place: where its object is (the focal dot) and how big
/// its badge is.
class PinItem {
  final String id;
  final Offset anchor;
  final Size badge;

  const PinItem(this.id, this.anchor, this.badge);
}

/// Where a label's badge goes, and the leader line from the dot to it.
class PinPlacement {
  final String id;
  final Offset anchor;
  final Rect badge;

  const PinPlacement(this.id, this.anchor, this.badge);

  /// The badge point nearest the dot: where the leader line meets it.
  Offset get joint => Offset(
        anchor.dx.clamp(badge.left, badge.right),
        anchor.dy.clamp(badge.top, badge.bottom),
      );

  /// The leader line runs from the dot to [joint]; none when the dot
  /// already touches the badge.
  double get leaderLength => (joint - anchor).distance;
}

/// Places photo labels so they read as a calm, balanced layer over the
/// photo instead of a pile on the objects:
///
/// - badges never overlap one another and never cover any object's dot;
/// - each badge is joined to its dot by a short leader line, and leader
///   lines avoid crossing each other and other badges;
/// - badges push each other apart and lean outward from the centre of
///   the objects, so labels spread over the photo evenly;
/// - everything stays inside the photo.
///
/// Greedy placement, most crowded objects first, over candidate spots
/// around each dot, in columns beside the cluster, and on a grid over the
/// photo, then passes that re-place each label against all the others.
/// A spot that overlaps another label is never chosen while a free spot
/// exists; among free spots, one that covers a dot loses to one that does
/// not; among those, a leader longer than 60% of the photo's short side
/// loses to a shorter one. Deterministic.
///
/// [reserveTop] / [reserveBottom] keep bands of the photo clear for things
/// drawn over it (a status chip, a notice); badges also keep off the
/// [avoid] rectangles (a control over a corner of the photo).
List<PinPlacement> layoutPins(List<PinItem> items, Size box,
    {double margin = 6,
    double reserveTop = 0,
    double reserveBottom = 0,
    List<Rect> avoid = const []}) {
  if (items.isEmpty) return const [];
  // A badge wider than the photo can't stay inside it: it gets the photo's
  // width and WordPin wraps the text onto another line.
  final widest = box.width - 2 * margin;
  items = [
    for (final it in items)
      it.badge.width > widest
          ? PinItem(it.id, it.anchor, Size(widest, it.badge.height))
          : it,
  ];
  final dots = [for (final i in items) i.anchor];
  final centroid = Offset(
    dots.map((d) => d.dx).reduce((a, b) => a + b) / dots.length,
    dots.map((d) => d.dy).reduce((a, b) => a + b) / dots.length,
  );
  final tallest = items.map((i) => i.badge.height).reduce(math.max);
  final top = margin + reserveTop, bottom = box.height - margin - reserveBottom;
  final area = bottom - top >= tallest * 2
      ? Rect.fromLTRB(margin, top, box.width - margin, bottom)
      : Rect.fromLTWH(
          margin, margin, box.width - 2 * margin, box.height - 2 * margin);

  Rect fit(Rect r) {
    var dx = 0.0, dy = 0.0;
    if (r.left < area.left) dx = area.left - r.left;
    if (r.right > area.right) dx = area.right - r.right;
    if (r.top < area.top) dy = area.top - r.top;
    if (r.bottom > area.bottom) dy = area.bottom - r.bottom;
    return r.shift(Offset(dx, dy));
  }

  // Candidate badge rectangles for one item.
  List<Rect> candidates(PinItem it) {
    final out = <Rect>[];
    final seen = <int>{};
    void add(Rect r) {
      final fitted = fit(r);
      final key = (fitted.left * 2).round() * 100000 + (fitted.top * 2).round();
      if (seen.add(key)) out.add(fitted);
    }

    final w = it.badge.width, h = it.badge.height;
    // 132 sits just under the landscape leader limit (60% of the short side).
    for (final r in const [12.0, 24.0, 40.0, 60.0, 86.0, 104.0, 118.0, 132.0, 150.0]) {
      for (var k = 0; k < 24; k++) {
        final a = k * math.pi / 12;
        final dir = Offset(math.cos(a), math.sin(a));
        // Distance from the badge centre to its edge along dir.
        final extent = (dir.dx.abs() * w / 2 + dir.dy.abs() * h / 2);
        final c = it.anchor + dir * (r + extent);
        add(Rect.fromCenter(center: c, width: w, height: h));
      }
    }
    // Wide photos get more columns: crowded objects need spots beside them.
    final wide = area.width > area.height * 1.3;
    final cols = wide ? 8 : 4, rows = wide ? 5 : 4;
    for (var i = 0; i < cols; i++) {
      for (var j = 0; j < rows; j++) {
        final c = Offset(area.left + area.width * (i + 0.5) / cols,
            area.top + area.height * (j + 0.5) / rows);
        add(Rect.fromCenter(center: c, width: w, height: h));
      }
    }
    // Columns down the photo. Wide badges on a short photo cannot sit
    // side by side, and a ring around the dot gets clamped back on top of
    // it; a vertical scan is what still leaves the dot clear (#61).
    final xs = <double>[
      area.left,
      area.right - w,
      it.anchor.dx - w / 2,
      it.anchor.dx - w - 8,
      it.anchor.dx + 8,
    ];
    for (final rawX in xs) {
      for (var y = area.top; y <= area.bottom - h + 0.1; y += 4) {
        add(Rect.fromLTWH(rawX, y, w, h));
      }
    }
    return out;
  }

  double overlap(Rect a, Rect b) {
    final i = a.intersect(b);
    return i.width > 0 && i.height > 0 ? i.width * i.height : 0;
  }

  bool segmentHitsRect(Offset p, Offset q, Rect r) {
    if (r.contains(p) || r.contains(q)) return true;
    Offset corner(int i) =>
        [r.topLeft, r.topRight, r.bottomRight, r.bottomLeft][i];
    for (var i = 0; i < 4; i++) {
      if (_segmentsCross(p, q, corner(i), corner((i + 1) % 4))) return true;
    }
    return false;
  }

  // Edge-to-edge distance between two badges (negative when they overlap).
  double gap(Rect a, Rect b) => math.max(
        (a.center.dx - b.center.dx).abs() - (a.width + b.width) / 2,
        (a.center.dy - b.center.dy).abs() - (a.height + b.height) / 2,
      );

  double cost(PinItem it, Rect r, Map<String, PinPlacement> placed) {
    final joint = Offset(it.anchor.dx.clamp(r.left, r.right),
        it.anchor.dy.clamp(r.top, r.bottom));
    final leader = (joint - it.anchor).distance;
    // A short leader is as good as none; past that, every pixel counts.
    // Long ones cost more still: a label should stay near its object.
    var c = leader <= 24 ? leader * 0.5 : 12 + (leader - 24) * 1.1;
    if (leader > 60) c += (leader - 60) * 2;
    // The badge must not cover any dot, its own included: worse than any
    // leader line (問題回報 #61: crowded landscape photos hid a dot).
    for (final d in dots) {
      final hit = r.inflate(5).contains(d);
      if (hit) c += 6000;
    }
    for (final a in avoid) {
      if (r.inflate(4).overlaps(a)) c += 400 + overlap(r.inflate(4), a) * 60;
    }
    final centre = r.center;
    var left = centre.dx < area.center.dx ? 1 : 0, right = 1 - left;
    for (final p in placed.values) {
      if (p.id == it.id) continue;
      c += overlap(r.inflate(4), p.badge) * 60;
      // Spread labels out: nearby badges repel, and keep a clear gap.
      final g = gap(r, p.badge);
      c += 3200 / (math.max(g, 0) + 28);
      if (g < 12) c += (12 - g) * 8;
      if (p.badge.center.dx < area.center.dx) {
        left++;
      } else {
        right++;
      }
      // Leader lines neither cross each other nor run under badges.
      if (leader > 1 &&
          p.leaderLength > 1 &&
          _segmentsCross(it.anchor, joint, p.anchor, p.joint)) {
        c += 180;
      }
      if (leader > 1 && segmentHitsRect(it.anchor, joint, p.badge.deflate(1))) {
        c += 220;
      }
      if (p.leaderLength > 1 &&
          segmentHitsRect(p.anchor, p.joint, r.deflate(1))) {
        c += 220;
      }
    }
    // Balance: about as many labels on the left of the photo as on the right.
    c += 18 * (left - right).abs();
    // Lean outward from the middle of the objects, for balance.
    final out = it.anchor - centroid;
    final toward = centre - it.anchor;
    if (out.distance > 1 && toward.distance > 1) {
      final cos = (out.dx * toward.dx + out.dy * toward.dy) /
          (out.distance * toward.distance);
      c -= 14 * cos;
    }
    // A slight preference for labels above their objects, as people read.
    if (centre.dy < it.anchor.dy) c -= 4;
    return c;
  }

  // Most crowded first: they have the fewest good spots.
  int crowd(PinItem it) =>
      dots.where((d) => d != it.anchor && (d - it.anchor).distance < 80).length;
  final order = [...items]..sort((a, b) {
      final c = crowd(b).compareTo(crowd(a));
      return c != 0 ? c : a.anchor.dy.compareTo(b.anchor.dy);
    });
  final cands = {for (final it in items) it.id: candidates(it)};
  final placed = <String, PinPlacement>{};

  bool coversDot(Rect r) {
    final padded = r.inflate(2);
    for (final d in dots) {
      if (padded.contains(d)) return true;
    }
    return false;
  }

  bool overlapsBadge(Rect r, String id) {
    for (final p in placed.values) {
      if (p.id != id && overlap(r, p.badge) > 0) return true;
    }
    return false;
  }

  // 0 free and close, 1 free but the leader is past 60% of the short side,
  // 2 covers a dot, 3 overlaps another label. Lower wins, then [cost].
  int tier(PinItem it, Rect r) {
    if (overlapsBadge(r, it.id)) return 3;
    if (coversDot(r)) return 2;
    final joint = Offset(it.anchor.dx.clamp(r.left, r.right),
        it.anchor.dy.clamp(r.top, r.bottom));
    if ((joint - it.anchor).distance > box.shortestSide * 0.6) return 1;
    return 0;
  }

  PinPlacement best(PinItem it) {
    Rect? bestRect;
    var bestTier = 9;
    var bestCost = double.infinity;
    for (final r in cands[it.id]!) {
      final t = tier(it, r);
      if (t > bestTier) continue;
      final c = cost(it, r, placed);
      if (t < bestTier || c < bestCost) {
        bestTier = t;
        bestCost = c;
        bestRect = r;
      }
    }
    return PinPlacement(it.id, it.anchor, bestRect!);
  }

  for (final it in order) {
    placed[it.id] = best(it);
  }
  for (var pass = 0; pass < 3; pass++) {
    for (final it in order) {
      placed.remove(it.id);
      placed[it.id] = best(it);
    }
  }

  // A label that flees its own dot to stay clear can sit on the only free
  // shelf and force another label to cover a dot. When that happens, stack
  // badges down the photo (closest shelf to each dot) and keep the result
  // only when it leaves fewer spec violations.
  (int, int) violations(Map<String, PinPlacement> map) {
    final limit = box.shortestSide * 0.6;
    var covers = 0, longs = 0;
    for (final p in map.values) {
      if (p.leaderLength > limit) longs++;
      for (final d in dots) {
        if (p.badge.inflate(2).contains(d)) covers++;
      }
    }
    return (covers, longs);
  }

  Map<String, PinPlacement>? columnPack(List<PinItem> seq) {
    final used = <Rect>[];
    final map = <String, PinPlacement>{};
    final limit = box.shortestSide * 0.6;
    for (final it in seq) {
      final w = it.badge.width, h = it.badge.height;
      Rect? picked;
      var pickedKey = (9, 9, double.infinity);
      final xs = <double>[
        area.left,
        area.right - w,
        it.anchor.dx - w / 2,
        it.anchor.dx - w - 8,
        it.anchor.dx + 8,
      ];
      for (final rawX in xs) {
        for (var y = area.top; y <= area.bottom - h + 0.1; y += 4) {
          final r = fit(Rect.fromLTWH(rawX, y, w, h));
          var blocked = false;
          for (final u in used) {
            if (overlap(r, u) > 0) blocked = true;
          }
          if (blocked) continue;
          for (final a in avoid) {
            if (r.inflate(4).overlaps(a)) blocked = true;
          }
          if (blocked) continue;
          final cov = coversDot(r) ? 1 : 0;
          final joint = Offset(it.anchor.dx.clamp(r.left, r.right),
              it.anchor.dy.clamp(r.top, r.bottom));
          final leader = (joint - it.anchor).distance;
          final long = leader > limit ? 1 : 0;
          final key = (cov, long, leader);
          if (key.$1 < pickedKey.$1 ||
              (key.$1 == pickedKey.$1 && key.$2 < pickedKey.$2) ||
              (key.$1 == pickedKey.$1 &&
                  key.$2 == pickedKey.$2 &&
                  key.$3 < pickedKey.$3)) {
            pickedKey = key;
            picked = r;
          }
        }
      }
      if (picked == null) return null;
      map[it.id] = PinPlacement(it.id, it.anchor, picked);
      used.add(picked);
    }
    return map;
  }

  var bestMap = placed;
  var bestViol = violations(placed);
  if (bestViol.$1 > 0 || bestViol.$2 > 0) {
    final sequences = <List<PinItem>>[
      [...items]..sort((a, b) => a.anchor.dy.compareTo(b.anchor.dy)),
      [...items]..sort((a, b) => b.anchor.dy.compareTo(a.anchor.dy)),
      order,
    ];
    for (final seq in sequences) {
      final map = columnPack(seq);
      if (map == null) continue;
      final viol = violations(map);
      final better = viol.$1 + viol.$2 < bestViol.$1 + bestViol.$2 ||
          (viol.$1 + viol.$2 == bestViol.$1 + bestViol.$2 && viol.$1 < bestViol.$1);
      if (better) {
        bestViol = viol;
        bestMap = map;
      }
    }
  }
  return [for (final it in items) bestMap[it.id]!];
}

bool _segmentsCross(Offset a, Offset b, Offset c, Offset d) {
  double cross(Offset o, Offset p, Offset q) =>
      (p.dx - o.dx) * (q.dy - o.dy) - (p.dy - o.dy) * (q.dx - o.dx);
  final d1 = cross(c, d, a),
      d2 = cross(c, d, b),
      d3 = cross(a, b, c),
      d4 = cross(a, b, d);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
      ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}
