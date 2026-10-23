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
///
/// [keep] (問題回報 #665) are badges already on the photo, in order of
/// priority: a label whose dot and badge size are unchanged stays exactly
/// there (when it is still inside the photo and clear of the labels kept
/// before it), and only the other labels are placed, around them.
List<PinPlacement> layoutPins(List<PinItem> items, Size box,
    {double margin = 6,
    double reserveTop = 0,
    double reserveBottom = 0,
    List<Rect> avoid = const [],
    List<PinPlacement> keep = const []}) {
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
    for (final r in const [
      12.0,
      24.0,
      40.0,
      60.0,
      86.0,
      104.0,
      118.0,
      132.0,
      150.0
    ]) {
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

  // Most crowded first: they have the fewest good spots.
  int crowd(PinItem it) =>
      dots.where((d) => d != it.anchor && (d - it.anchor).distance < 80).length;
  final order = [...items]..sort((a, b) {
      final c = crowd(b).compareTo(crowd(a));
      return c != 0 ? c : a.anchor.dy.compareTo(b.anchor.dy);
    });
  final placed = <String, PinPlacement>{};
  // 問題回報 #665: labels already on the photo stay where they are.
  final byId = {for (final it in items) it.id: it};
  for (final k in keep) {
    final it = byId[k.id];
    if (it == null || placed.containsKey(k.id)) continue;
    if ((it.anchor - k.anchor).distance > 0.5 ||
        (it.badge.width - k.badge.width).abs() > 0.5 ||
        (it.badge.height - k.badge.height).abs() > 0.5) {
      continue;
    }
    final r = k.badge;
    if (r.left < -0.5 ||
        r.top < -0.5 ||
        r.right > box.width + 0.5 ||
        r.bottom > box.height + 0.5) {
      continue;
    }
    if (placed.values.any((p) => overlap(p.badge, r) > 0)) continue;
    placed[k.id] = PinPlacement(it.id, it.anchor, r);
  }
  final fixed = Set<String>.of(placed.keys);
  if (fixed.length == items.length) {
    return [for (final it in items) placed[it.id]!];
  }
  final free = [
    for (final it in order)
      if (!fixed.contains(it.id)) it
  ];
  final cands = {for (final it in free) it.id: candidates(it)};

  bool coversDot(Rect r) {
    final padded = r.inflate(2);
    for (final d in dots) {
      if (padded.contains(d)) return true;
    }
    return false;
  }

  // 問題回報：Mac 實機量測第二輪 照片詳情 64ms／翻卡 87ms（M-PERF2）: the same
  // tiers and cost as before, worked out on plain numbers (no rectangles
  // made per spot), and a spot that can no longer beat the best one so far
  // stops being scored. The result is the same, bit for bit.
  final dotX = [for (final d in dots) d.dx];
  final dotY = [for (final d in dots) d.dy];
  final areaCx = area.center.dx;
  final longLeader = box.shortestSide * 0.6;

  PinPlacement best(PinItem it) {
    final others = [
      for (final p in placed.values)
        if (p.id != it.id) _Placed(p),
    ];
    final ax = it.anchor.dx, ay = it.anchor.dy;
    final out = it.anchor - centroid;
    final outDistance = out.distance;
    Rect? bestRect;
    var bestTier = 9;
    var bestCost = double.infinity;
    for (final r in cands[it.id]!) {
      final l = r.left, t = r.top, rr = r.right, b = r.bottom;
      // 0 free and close, 1 free but the leader is past 60% of the short
      // side, 2 covers a dot, 3 overlaps another label. Lower wins, then
      // the cost.
      var tier = 0;
      for (final p in others) {
        final iw = math.min(rr, p.right) - math.max(l, p.left);
        final ih = math.min(b, p.bottom) - math.max(t, p.top);
        if (iw > 0 && ih > 0 && iw * ih > 0) {
          tier = 3;
          break;
        }
      }
      final jx = ax.clamp(l, rr), jy = ay.clamp(t, b);
      final ldx = jx - ax, ldy = jy - ay;
      final leader = math.sqrt(ldx * ldx + ldy * ldy);
      if (tier == 0) {
        final pl = l - 2, pt = t - 2, pr = rr + 2, pb = b + 2;
        for (var i = 0; i < dotX.length; i++) {
          final x = dotX[i], y = dotY[i];
          if (x >= pl && x < pr && y >= pt && y < pb) {
            tier = 2;
            break;
          }
        }
        if (tier == 0 && leader > longLeader) tier = 1;
      }
      if (tier > bestTier) continue;
      // Only a lower tier wins whatever it costs; in the same tier the
      // terms still to come take off at most 18.
      final prune = tier == bestTier && bestCost.isFinite;
      final cut = bestCost + 19;

      // A short leader is as good as none; past that, every pixel counts.
      // Long ones cost more still: a label should stay near its object.
      var c = leader <= 24 ? leader * 0.5 : 12 + (leader - 24) * 1.1;
      if (leader > 60) c += (leader - 60) * 2;
      // The badge must not cover any dot, its own included: worse than any
      // leader line (問題回報 #61: crowded landscape photos hid a dot).
      final hl = l - 5, ht = t - 5, hr = rr + 5, hb = b + 5;
      for (var i = 0; i < dotX.length; i++) {
        final x = dotX[i], y = dotY[i];
        if (x >= hl && x < hr && y >= ht && y < hb) c += 6000;
      }
      for (final a in avoid) {
        if (r.inflate(4).overlaps(a)) c += 400 + overlap(r.inflate(4), a) * 60;
      }
      if (prune && c > cut) continue;
      final rw = rr - l, rh = b - t;
      final cx = l + rw / 2.0, cy = t + rh / 2.0;
      var left = cx < areaCx ? 1 : 0, right = 1 - left;
      final il = l - 4, it4 = t - 4, ir = rr + 4, ib = b + 4;
      final dl = l + 1, dt = t + 1, dr = rr - 1, db = b - 1;
      var dropped = false;
      for (final p in others) {
        final iw = math.min(ir, p.right) - math.max(il, p.left);
        final ih = math.min(ib, p.bottom) - math.max(it4, p.top);
        c += (iw > 0 && ih > 0 ? iw * ih : 0) * 60;
        // Spread labels out: nearby badges repel, and keep a clear gap.
        final g = math.max((cx - p.cx).abs() - (rw + p.width) / 2,
            (cy - p.cy).abs() - (rh + p.height) / 2);
        c += 3200 / (math.max(g, 0) + 28);
        if (g < 12) c += (12 - g) * 8;
        if (p.cx < areaCx) {
          left++;
        } else {
          right++;
        }
        // Leader lines neither cross each other nor run under badges.
        if (leader > 1 &&
            p.leaderLength > 1 &&
            _crosses(ax, ay, jx, jy, p.ax, p.ay, p.jx, p.jy)) {
          c += 180;
        }
        if (leader > 1 &&
            _segmentHits(ax, ay, jx, jy, p.dl, p.dt, p.dr, p.db)) {
          c += 220;
        }
        if (p.leaderLength > 1 &&
            _segmentHits(p.ax, p.ay, p.jx, p.jy, dl, dt, dr, db)) {
          c += 220;
        }
        if (prune && c > cut) {
          dropped = true;
          break;
        }
      }
      if (dropped) continue;
      // Balance: about as many labels on the left of the photo as on the right.
      c += 18 * (left - right).abs();
      // Lean outward from the middle of the objects, for balance.
      final tx = cx - ax, ty = cy - ay;
      final towardDistance = math.sqrt(tx * tx + ty * ty);
      if (outDistance > 1 && towardDistance > 1) {
        final cos =
            (out.dx * tx + out.dy * ty) / (outDistance * towardDistance);
        c -= 14 * cos;
      }
      // A slight preference for labels above their objects, as people read.
      if (cy < ay) c -= 4;
      if (tier < bestTier || c < bestCost) {
        bestTier = tier;
        bestCost = c;
        bestRect = r;
      }
    }
    return PinPlacement(it.id, it.anchor, bestRect!);
  }

  for (final it in free) {
    placed[it.id] = best(it);
  }
  for (var pass = 0; pass < 3; pass++) {
    for (final it in free) {
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
    final used = <Rect>[for (final id in fixed) placed[id]!.badge];
    final map = <String, PinPlacement>{for (final id in fixed) id: placed[id]!};
    final limit = box.shortestSide * 0.6;
    for (final it in seq) {
      if (fixed.contains(it.id)) continue;
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
          (viol.$1 + viol.$2 == bestViol.$1 + bestViol.$2 &&
              viol.$1 < bestViol.$1);
      if (better) {
        bestViol = viol;
        bestMap = map;
      }
    }
  }
  return [for (final it in items) bestMap[it.id]!];
}

/// A placed badge as plain numbers, for [layoutPins]' inner loop (M-PERF2).
class _Placed {
  final double left, top, right, bottom, width, height, cx, cy;
  final double ax, ay, jx, jy, leaderLength;

  /// The badge less 1 on each side, which leader lines must not cross.
  final double dl, dt, dr, db;

  factory _Placed(PinPlacement p) {
    final b = p.badge;
    final joint = p.joint;
    return _Placed._(
      b.left,
      b.top,
      b.right,
      b.bottom,
      b.width,
      b.height,
      b.left + b.width / 2.0,
      b.top + b.height / 2.0,
      p.anchor.dx,
      p.anchor.dy,
      joint.dx,
      joint.dy,
      p.leaderLength,
      b.left + 1,
      b.top + 1,
      b.right - 1,
      b.bottom - 1,
    );
  }

  const _Placed._(
      this.left,
      this.top,
      this.right,
      this.bottom,
      this.width,
      this.height,
      this.cx,
      this.cy,
      this.ax,
      this.ay,
      this.jx,
      this.jy,
      this.leaderLength,
      this.dl,
      this.dt,
      this.dr,
      this.db);
}

/// Whether the segments a→b and c→d cross (touching does not count).
bool _crosses(double ax, double ay, double bx, double by, double cx, double cy,
    double dx, double dy) {
  final d1 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx),
      d2 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx),
      d3 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax),
      d4 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
      ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

/// Whether the segment p→q touches the rectangle [l, t, r, b]: an end
/// inside it, or crossing one of its sides.
bool _segmentHits(double px, double py, double qx, double qy, double l,
    double t, double r, double b) {
  if (px >= l && px < r && py >= t && py < b) return true;
  if (qx >= l && qx < r && qy >= t && qy < b) return true;
  return _crosses(px, py, qx, qy, l, t, r, t) ||
      _crosses(px, py, qx, qy, r, t, r, b) ||
      _crosses(px, py, qx, qy, r, b, l, b) ||
      _crosses(px, py, qx, qy, l, b, l, t);
}
