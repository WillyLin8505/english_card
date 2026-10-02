// Photo label layout, the same rules as the app (app/lib/widgets/mobile/
// pin_layout.dart): labels never overlap one another or cover any object's
// dot, join their dot with a short leader line, spread out and balance left
// and right, and stay inside the picture. Deterministic.

export type Pt = { x: number; y: number };
export type Box = { l: number; t: number; r: number; b: number };
export type PinItem = { id: string; anchor: Pt; w: number; h: number };
export type Placement = { id: string; anchor: Pt; badge: Box; joint: Pt; leader: number };

const center = (b: Box): Pt => ({ x: (b.l + b.r) / 2, y: (b.t + b.b) / 2 });
const inflate = (b: Box, d: number): Box => ({ l: b.l - d, t: b.t - d, r: b.r + d, b: b.b + d });
const contains = (b: Box, p: Pt) => p.x >= b.l && p.x <= b.r && p.y >= b.t && p.y <= b.b;
const dist = (a: Pt, b: Pt) => Math.hypot(a.x - b.x, a.y - b.y);
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

function overlap(a: Box, b: Box) {
  const w = Math.min(a.r, b.r) - Math.max(a.l, b.l), h = Math.min(a.b, b.b) - Math.max(a.t, b.t);
  return w > 0 && h > 0 ? w * h : 0;
}

function segmentsCross(a: Pt, b: Pt, c: Pt, d: Pt) {
  const cross = (o: Pt, p: Pt, q: Pt) => (p.x - o.x) * (q.y - o.y) - (p.y - o.y) * (q.x - o.x);
  const d1 = cross(c, d, a), d2 = cross(c, d, b), d3 = cross(a, b, c), d4 = cross(a, b, d);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

function segmentHitsBox(p: Pt, q: Pt, r: Box) {
  if (contains(r, p) || contains(r, q)) return true;
  const c = [{ x: r.l, y: r.t }, { x: r.r, y: r.t }, { x: r.r, y: r.b }, { x: r.l, y: r.b }];
  return c.some((a, i) => segmentsCross(p, q, a, c[(i + 1) % 4]));
}

const jointOf = (anchor: Pt, b: Box): Pt => ({ x: clamp(anchor.x, b.l, b.r), y: clamp(anchor.y, b.t, b.b) });

export function layoutPins(items: PinItem[], width: number, height: number, margin = 6): Placement[] {
  if (!items.length) return [];
  const dots = items.map((i) => i.anchor);
  const centroid = { x: dots.reduce((s, d) => s + d.x, 0) / dots.length, y: dots.reduce((s, d) => s + d.y, 0) / dots.length };
  const area: Box = { l: margin, t: margin, r: width - margin, b: height - margin };
  const areaMid = (area.l + area.r) / 2;
  const fit = (b: Box): Box => {
    let dx = 0, dy = 0;
    if (b.l < area.l) dx = area.l - b.l;
    if (b.r > area.r) dx = area.r - b.r;
    if (b.t < area.t) dy = area.t - b.t;
    if (b.b > area.b) dy = area.b - b.b;
    return { l: b.l + dx, t: b.t + dy, r: b.r + dx, b: b.b + dy };
  };
  const around = (c: Pt, w: number, h: number): Box => fit({ l: c.x - w / 2, t: c.y - h / 2, r: c.x + w / 2, b: c.y + h / 2 });

  const candidates = (it: PinItem): Box[] => {
    const out: Box[] = [];
    for (const r of [12, 24, 40, 60, 86, 118]) {
      for (let k = 0; k < 16; k++) {
        const a = (k * Math.PI) / 8, dx = Math.cos(a), dy = Math.sin(a);
        const extent = Math.abs(dx) * it.w / 2 + Math.abs(dy) * it.h / 2;
        out.push(around({ x: it.anchor.x + dx * (r + extent), y: it.anchor.y + dy * (r + extent) }, it.w, it.h));
      }
    }
    for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
      out.push(around({ x: area.l + (area.r - area.l) * (i + 0.5) / 4, y: area.t + (area.b - area.t) * (j + 0.5) / 4 }, it.w, it.h));
    }
    return out;
  };

  const gap = (a: Box, b: Box) => {
    const ca = center(a), cb = center(b);
    return Math.max(Math.abs(ca.x - cb.x) - ((a.r - a.l) + (b.r - b.l)) / 2,
                    Math.abs(ca.y - cb.y) - ((a.b - a.t) + (b.b - b.t)) / 2);
  };

  const cost = (it: PinItem, r: Box, placed: Map<string, Placement>) => {
    const joint = jointOf(it.anchor, r);
    const leader = dist(joint, it.anchor);
    let c = leader <= 24 ? leader * 0.5 : 12 + (leader - 24) * 1.1;
    if (leader > 60) c += (leader - 60) * 2;
    for (const d of dots) if (contains(inflate(r, 5), d)) c += d === it.anchor ? 4000 : 2500;
    const cr = center(r);
    let left = cr.x < areaMid ? 1 : 0, right = 1 - left;
    for (const p of placed.values()) {
      if (p.id === it.id) continue;
      c += overlap(inflate(r, 4), p.badge) * 60;
      const g = gap(r, p.badge);
      c += 3200 / (Math.max(g, 0) + 28);
      if (g < 12) c += (12 - g) * 8;
      if (center(p.badge).x < areaMid) left++; else right++;
      if (leader > 1 && p.leader > 1 && segmentsCross(it.anchor, joint, p.anchor, p.joint)) c += 180;
      if (leader > 1 && segmentHitsBox(it.anchor, joint, inflate(p.badge, -1))) c += 220;
      if (p.leader > 1 && segmentHitsBox(p.anchor, p.joint, inflate(r, -1))) c += 220;
    }
    c += 18 * Math.abs(left - right);
    const out = { x: it.anchor.x - centroid.x, y: it.anchor.y - centroid.y };
    const toward = { x: cr.x - it.anchor.x, y: cr.y - it.anchor.y };
    const lo = Math.hypot(out.x, out.y), lt = Math.hypot(toward.x, toward.y);
    if (lo > 1 && lt > 1) c -= 14 * (out.x * toward.x + out.y * toward.y) / (lo * lt);
    if (cr.y < it.anchor.y) c -= 4;
    return c;
  };

  const crowd = (it: PinItem) => dots.filter((d) => d !== it.anchor && dist(d, it.anchor) < 80).length;
  const order = [...items].sort((a, b) => crowd(b) - crowd(a) || a.anchor.y - b.anchor.y);
  const cands = new Map(items.map((it) => [it.id, candidates(it)]));
  const placed = new Map<string, Placement>();
  const best = (it: PinItem): Placement => {
    let bestBox = cands.get(it.id)![0], bestCost = Infinity;
    for (const r of cands.get(it.id)!) {
      const c = cost(it, r, placed);
      if (c < bestCost) { bestCost = c; bestBox = r; }
    }
    const joint = jointOf(it.anchor, bestBox);
    return { id: it.id, anchor: it.anchor, badge: bestBox, joint, leader: dist(joint, it.anchor) };
  };
  for (const it of order) placed.set(it.id, best(it));
  for (let pass = 0; pass < 2; pass++) {
    for (const it of order) { placed.delete(it.id); placed.set(it.id, best(it)); }
  }
  return items.map((it) => placed.get(it.id)!);
}
