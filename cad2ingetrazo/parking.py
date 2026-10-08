# SPDX-License-Identifier: GPL-3.0-or-later
"""Car parking, car ramps and floor-level marks, read from the CAD plan.

* Parking: the bay lines of the parking layers and the car blocks of the
  car layers, as drawn — in the plan (the CAD's own symbols) and in 3D
  (white paint on the floor, a simple car mass in each car block).
* Ramps: the lines of the ramp layers. A ramp drawn with cross stripes
  (the usual hatch across the slope) follows its stripes — straight or
  curved; a ramp drawn as two side lines runs between them. The climb is
  read from the note beside it (CLIMB HEIGHT, or GRADIENT 1:n × length),
  up or down from «RAMP UP / DN» and the arrow on it. Built in 3D as a
  sloped RC slab; in plan as its outline, stripes and an UP / DN arrow.
* Level marks: the CAD's «LEV. +4'-0"» / «FFL» notes, drawn as level
  symbols; a level with none gets its own (its floor level) on the plan.

Pure: no Qt, no IngeTrazo. Lengths in metres.
"""
from __future__ import annotations

import math
import re

FT = 0.3048
PAINT = (0.95, 0.95, 0.90, 1.0)
RAMP_C = (0.64, 0.64, 0.62, 1.0)
RAMP_TOP = (0.55, 0.55, 0.54, 1.0)
GLASS = (0.22, 0.27, 0.33, 1.0)
TYRE = (0.12, 0.12, 0.13, 1.0)
CAR_COLORS = [(0.78, 0.80, 0.82, 1.0), (0.20, 0.22, 0.26, 1.0),
              (0.62, 0.12, 0.12, 1.0), (0.90, 0.90, 0.88, 1.0),
              (0.18, 0.30, 0.52, 1.0), (0.50, 0.52, 0.54, 1.0)]

_FI = re.compile(r"(\d+(?:\.\d+)?)\s*'\s*-?\s*(?:(\d+(?:\.\d+)?)\s*\")?")
_GRAD = re.compile(r"1\s*:\s*(\d+(?:\.\d+)?)")
_LEV = re.compile(r"^\s*(?:LEV(?:EL)?|LVL|F\.?F\.?L|S\.?S\.?L|T\.?O\.?S|EL)"
                  r"\.?\s*[:=]?\s*([+\-±]?)\s*(.+?)\s*$", re.I)


# ---- reading notes -----------------------------------------------------------------
def feet(txt):
    """Metres from «11'-0"», «0'-9"», «22'»; None when there is none."""
    m = _FI.search(txt or "")
    if not m:
        return None
    return (float(m.group(1)) + float(m.group(2) or 0) / 12.0) * FT


def _field(text, key):
    for line in str(text).replace("\t", " ").split("\n"):
        if key in line.upper():
            return line.split("=", 1)[-1] if "=" in line else line
    return None


def ramp_notes(texts) -> list:
    """[{x, y, rise, grad, length, width, dir}] from the ramp notes."""
    out = []
    for t in texts:
        s = str(t.get("text", ""))
        u = s.upper()
        if "RAMP" not in u and "CLIMB" not in u and "GRADIENT" not in u:
            continue
        rec = {"x": t["x"], "y": t["y"], "rise": None, "grad": None,
               "length": None, "width": None, "dir": None}
        if re.search(r"\bUP\b", u):
            rec["dir"] = "up"
        elif re.search(r"\b(DN|DOWN)\b", u):
            rec["dir"] = "dn"
        f = _field(s, "CLIMB")
        if f:
            rec["rise"] = feet(f)
        f = _field(s, "GRADIENT")
        if f:
            m = _GRAD.search(f)
            rec["grad"] = float(m.group(1)) if m else None
        f = _field(s, "LENGTH")
        if f:
            rec["length"] = feet(f)
        f = _field(s, "WIDTH")
        if f:
            rec["width"] = feet(f)
        out.append(rec)
    return out


def level_note(text):
    """(«LEV. +4'-0"» as drawn, metres or None) — a level note — or None."""
    s = str(text or "").strip().split("\n")[0]
    m = _LEV.match(s)
    if not m or len(s) > 30:
        return None
    sign, val = m.group(1), m.group(2)
    v = feet(val)
    if v is None:
        try:
            v = float(val.replace(",", ""))
            sign = ""
        except ValueError:
            return None
        return s, None                    # an absolute level (75.50)
    return s, -v if sign == "-" else v


def abs_level(text):
    """An absolute level note («LEV. 75.50», «RL 102.00») → its number (in
    the drawing's level unit: feet on an imperial plan, metres on a metric
    one), else None."""
    s_ = str(text or "").strip().split("\n")[0]
    m = _LEV.match(s_) or re.match(r"^\s*R\.?L\.?\s*[:=]?\s*()(.+?)\s*$",
                                   s_, re.I)
    if not m or m.group(1) in ("+", "-", "±") or "'" in m.group(2):
        return None
    try:
        return float(m.group(2).replace(",", ""))
    except ValueError:
        return None


# ---- parking ----------------------------------------------------------------------
def car_of(ins) -> dict | None:
    """A car block → {c, ang (°, its length), L, W}."""
    cs = ins.get("corners")
    if not cs or len(cs) < 4:
        return None
    xs, ys = [p[0] for p in cs], [p[1] for p in cs]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    r = math.radians(float(ins.get("rot", 0.0)))
    c, s = abs(math.cos(r)), abs(math.sin(r))
    det = c * c - s * s
    if abs(det) > 0.2:                    # the box of the turned car
        a = (bw * c - bh * s) / det
        b = (bh * c - bw * s) / det
    else:                                 # 45°: a square guess
        a = b = max(bw, bh) / math.sqrt(2)
    ang = math.degrees(r)
    if b > a:
        a, b, ang = b, a, ang + 90.0
    if not (2.5 <= a <= 7.5 and 1.2 <= b <= 3.0):
        return None
    return {"c": [round((min(xs) + max(xs)) / 2, 4),
                  round((min(ys) + max(ys)) / 2, 4)],
            "ang": round(ang, 3), "L": round(a, 3), "W": round(b, 3)}


def _bx(c, u, n, a0, a1, b0, b1, z0, z1, col):
    def P(a, b, z):
        return (c[0] + u[0] * a + n[0] * b, c[1] + u[1] * a + n[1] * b, z)
    p = [P(a0, b0, z0), P(a1, b0, z0), P(a1, b1, z0), P(a0, b1, z0),
         P(a0, b0, z1), P(a1, b0, z1), P(a1, b1, z1), P(a0, b1, z1)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    return [{"loop": [p[i] for i in q], "holes": [], "color": col}
            for q in quads]


def car_faces(car, z0, k=0) -> list:
    """A simple car: body, glass cabin, four wheels."""
    r = math.radians(car["ang"])
    u, n = (math.cos(r), math.sin(r)), (-math.sin(r), math.cos(r))
    L, W, c = car["L"], car["W"], car["c"]
    col = CAR_COLORS[k % len(CAR_COLORS)]
    h, w = L / 2, W / 2
    f = []
    f += _bx(c, u, n, -h, h, -w * 0.96, w * 0.96, z0 + 0.20, z0 + 0.78, col)
    f += _bx(c, u, n, -h * 0.45, h * 0.40, -w * 0.84, w * 0.84, z0 + 0.78,
             z0 + 1.35, GLASS)
    rr = 0.32
    for a in (-h * 0.68, h * 0.66):
        for b in (-w * 0.90, w * 0.90):
            f += _bx(c, u, n, a - rr, a + rr, b - 0.11, b + 0.11, z0,
                     z0 + 2 * rr, TYRE)
    return f


def car_outline(car) -> list:
    """The car's rectangle, for a plan with no CAD lines of it."""
    r = math.radians(car["ang"])
    u, n = (math.cos(r), math.sin(r)), (-math.sin(r), math.cos(r))
    h, w, c = car["L"] / 2, car["W"] / 2, car["c"]
    pts = [(c[0] + u[0] * a + n[0] * b, c[1] + u[1] * a + n[1] * b)
           for a, b in ((-h, -w), (h, -w), (h, w), (-h, w))]
    return [(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def paint_faces(a, b, z, w=0.10) -> list:
    """A painted bay line on the floor."""
    L = math.dist(a, b)
    if L < 0.2:
        return []
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])
    pts = [(a[0] + n[0] * s * w / 2 + u[0] * t, a[1] + n[1] * s * w / 2
            + u[1] * t, z) for s, t in ((-1, 0), (-1, L), (1, L), (1, 0))]
    return [{"loop": pts, "holes": [], "color": PAINT}]


def paint_union(lines, z, w=0.10) -> list:
    """The bay markings painted as ONE clean shape: every line a band
    ``w`` wide with square ends (so the corners meet and close), all of
    them merged — joined corners, no overlaps, no slivers."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    bands = []
    for a, b in lines:
        a, b = tuple(a), tuple(b)
        if math.dist(a, b) >= 0.2:
            bands.append(LineString([a, b]).buffer(w / 2, cap_style=3,
                                                   join_style=2))
    if not bands:
        return []
    u = unary_union(bands).simplify(0.003)
    faces = []
    for g in getattr(u, "geoms", [u]):
        if g.geom_type != "Polygon" or g.area < 1e-4:
            continue
        ext = list(g.exterior.coords)[:-1]
        if sum(p[0] * q[1] - q[0] * p[1]
               for p, q in zip(ext, ext[1:] + ext[:1])) < 0:
            ext = ext[::-1]
        holes = []
        for r in g.interiors:
            h = list(r.coords)[:-1]
            if sum(p[0] * q[1] - q[0] * p[1]
                   for p, q in zip(h, h[1:] + h[:1])) > 0:
                h = h[::-1]
            holes.append([(p[0], p[1], z) for p in h])
        faces.append({"loop": [(p[0], p[1], z) for p in ext], "holes": holes,
                      "color": PAINT})
    return faces


# ---- ramps ------------------------------------------------------------------------
def _ang(s):
    return math.degrees(math.atan2(s[1][1] - s[0][1], s[1][0] - s[0][0])) % 180


def _chain(pts):
    """The points in order along their line (curves too): from one end,
    nearest next."""
    if len(pts) < 3:
        return list(range(len(pts)))
    i0 = 0
    far = max(range(len(pts)), key=lambda j: math.dist(pts[j], pts[i0]))
    start = max(range(len(pts)), key=lambda j: math.dist(pts[j], pts[far]))
    order, left = [start], set(range(len(pts))) - {start}
    while left:
        j = min(left, key=lambda q: math.dist(pts[q], pts[order[-1]]))
        order.append(j)
        left.discard(j)
    return order


def _sections_from_stripes(lines, allpts):
    """Cross sections (a, b) in order along the ramp, a on its left."""
    mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in lines]
    order = _chain(mids)
    secs = [lines[i] for i in order]
    mids = [mids[i] for i in order]
    # stripes drawn twice (or very close): one
    keep_s, keep_m = [secs[0]], [mids[0]]
    for s, m in zip(secs[1:], mids[1:]):
        if math.dist(m, keep_m[-1]) > 0.08:
            keep_s.append(s)
            keep_m.append(m)
    secs, mids = keep_s, keep_m
    if len(secs) < 2:
        return []
    # a jump or a sharp turn in the chain: another ramp (or the landing
    # between two) — the chain cut there, the longest piece kept here
    gaps = [math.dist(mids[i], mids[i + 1]) for i in range(len(mids) - 1)]
    med = sorted(gaps)[len(gaps) // 2]
    cuts = [0]
    for i in range(1, len(mids) - 1):
        d0 = (mids[i][0] - mids[i - 1][0], mids[i][1] - mids[i - 1][1])
        d1 = (mids[i + 1][0] - mids[i][0], mids[i + 1][1] - mids[i][1])
        n0, n1 = math.hypot(*d0) or 1, math.hypot(*d1) or 1
        turn = math.degrees(math.acos(max(-1, min(1, (d0[0] * d1[0] + d0[1]
                                                      * d1[1]) / n0 / n1))))
        if gaps[i] > 4 * med + 0.3 or turn > 40:
            cuts.append(i + 1)
    cuts.append(len(mids))
    pieces = [(cuts[j], cuts[j + 1]) for j in range(len(cuts) - 1)]
    i0, i1 = max(pieces, key=lambda p: p[1] - p[0])
    secs, mids = secs[i0:i1], mids[i0:i1]
    if len(secs) < 3:
        return []
    out = []
    for i, (a, b) in enumerate(secs):
        j = min(i, len(mids) - 2)
        t = (mids[j + 1][0] - mids[j][0], mids[j + 1][1] - mids[j][1])
        cross = t[0] * (b[1] - a[1]) - t[1] * (b[0] - a[0])
        out.append((a, b) if cross > 0 else (b, a))
    # carried on to the ramp's ends (its side lines run past the stripes)
    for end in (0, -1):
        m0, m1 = (mids[0], mids[1]) if end == 0 else (mids[-1], mids[-2])
        d = math.dist(m0, m1)
        if d < 1e-6:
            continue
        t = ((m0[0] - m1[0]) / d, (m0[1] - m1[1]) / d)
        a, b = out[end]
        w = math.dist(a, b)
        reach = max(((p[0] - m0[0]) * t[0] + (p[1] - m0[1]) * t[1]
                     for p in allpts
                     if abs(-(p[0] - m0[0]) * t[1] + (p[1] - m0[1]) * t[0])
                     <= w / 2 + 0.3), default=0.0)
        if 0.15 < reach < 6.0:
            na = (a[0] + t[0] * reach, a[1] + t[1] * reach)
            nb = (b[0] + t[0] * reach, b[1] + t[1] * reach)
            if end == 0:
                out.insert(0, (na, nb))
            else:
                out.append((na, nb))
    return out


def _sections_from_sides(lines):
    """Two side lines (roughly parallel) → the two end sections."""
    best = None
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            p, q = lines[i], lines[j]
            da = abs(_ang(p) - _ang(q))
            if min(da, 180 - da) > 8:
                continue
            L = math.dist(*p)
            u = ((p[1][0] - p[0][0]) / L, (p[1][1] - p[0][1]) / L)
            gap = abs(-(q[0][0] - p[0][0]) * u[1] + (q[0][1] - p[0][1]) * u[0])
            if not 0.9 <= gap <= 8.0:
                continue
            t0 = [(r[0] - p[0][0]) * u[0] + (r[1] - p[0][1]) * u[1] for r in q]
            lo, hi = max(0.0, min(t0)), min(L, max(t0))
            if hi - lo < 1.5:
                continue
            score = hi - lo
            if best is None or score > best[0]:
                best = (score, p, u, lo, hi, gap, q)
    if best is None:
        return []
    _s, p, u, lo, hi, gap, q = best
    n = (-u[1], u[0])
    side = 1.0 if (q[0][0] - p[0][0]) * n[0] + (q[0][1] - p[0][1]) * n[1] > 0 \
        else -1.0

    def P(t, c):
        return (p[0][0] + u[0] * t + n[0] * c, p[0][1] + u[1] * t + n[1] * c)
    secs = [(P(t, 0.0), P(t, side * gap)) for t in (lo, (lo + hi) / 2, hi)]
    return [(b, a) if side > 0 else (a, b) for a, b in secs]


def _length(secs):
    mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in secs]
    return [0.0] + [sum(math.dist(mids[i], mids[i + 1]) for i in range(k))
                    for k in range(1, len(mids))]


def ramps_from(segs, texts, arrows) -> list:
    """Ramps from the ramp layers' lines (metres): [{sections, rise, w}].
    ``arrows``: [(x, y, rot°)] of the arrow blocks."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    S = [((s[0], s[1]), (s[2], s[3])) for s in segs
         if math.dist((s[0], s[1]), (s[2], s[3])) > 0.05]
    if not S:
        return []
    blob = unary_union([LineString(s).buffer(0.3) for s in S])
    comps = [g for g in getattr(blob, "geoms", [blob]) if g.area > 0.5]
    notes = ramp_notes(texts)
    used = set()
    out = []
    cands, loose = [], []
    for g in comps:
        mine = [s for s in S if g.contains(LineString(s).centroid)]
        if not mine:
            continue
        lens = [round(math.dist(*s) / 0.05) * 0.05 for s in mine]
        count: dict = {}
        for v in lens:
            if v >= 1.0:
                count[v] = count.get(v, 0) + 1
        secs = []
        if count:
            # the stripes: the length most lines share AND lie parallel
            # at (the chevrons of an arrow pattern come as many, but in
            # two directions — never the ramp's width)
            def par(v):
                angs = [math.degrees(math.atan2(s[1][1] - s[0][1],
                                                s[1][0] - s[0][0])) % 180
                        for s, L_ in zip(mine, lens) if L_ == v]
                best = 0
                for a0 in angs:
                    best = max(best, sum(
                        1 for a1 in angs
                        if min(abs(a1 - a0), 180 - abs(a1 - a0)) < 3.0))
                return best
            mode = max(count, key=lambda v: (par(v), count[v], v))
            stripes = [s for s in mine
                       if abs(math.dist(*s) - mode) <= 0.06 * mode]
            # the stripes run square to the ramp: one main direction
            if len(stripes) >= 3 and 1.5 <= mode <= 12.0:
                allpts = [p for s in mine for p in s]
                secs = _sections_from_stripes(stripes, allpts)
        if not secs:
            secs = _sections_from_sides(sorted(mine, key=lambda s:
                                               -math.dist(*s))[:6])
        if len(secs) < 2:
            loose += [x for x in mine if math.dist(*x) >= 3.0]
            continue
        cands.append(secs)
    # side lines in groups of their own: paired across (a wide ramp)
    while len(loose) >= 2:
        secs = _sections_from_sides(loose)
        if len(secs) < 2 or _length([(tuple(a), tuple(b)) for a, b in secs])[-1] < 4.0:
            break
        cands.append(secs)
        sp = footprint({"sections": secs}).buffer(0.3)
        loose = [x for x in loose if not sp.contains(LineString(x).centroid)
                 and not sp.intersects(LineString(x))]
    for secs in cands:
        run = _length(secs)[-1]
        if run < 1.5:
            continue
        foot = unary_union([Polygon([a, b, d, c]).buffer(0)
                            for (a, b), (c, d) in zip(secs, secs[1:])])
        cen = foot.centroid
        # its note: the nearest within 20 m
        best, bd = None, 20.0
        for i, nt in enumerate(notes):
            if i in used or (nt["rise"] is None and nt["grad"] is None):
                continue
            d = foot.distance(Point(nt["x"], nt["y"]))
            if d < bd:
                best, bd = i, d
        rise = None
        if best is not None:
            nt = notes[best]
            used.add(best)
            if nt["rise"]:
                rise = nt["rise"]
            elif nt["grad"]:
                rise = run / nt["grad"]
        if rise is None:
            rise = run / 8.0
        rise = min(rise, 6.0)
        # up or down: the nearest «RAMP UP / DN» within 15 m
        dirs = [(foot.distance(Point(nt["x"], nt["y"])), nt["dir"], nt)
                for nt in notes if nt["dir"]]
        dirs.sort(key=lambda x: x[0])
        sign, label = 1.0, None
        if dirs and dirs[0][0] < 15.0:
            sign = -1.0 if dirs[0][1] == "dn" else 1.0
            label = dirs[0][2]
        # which end it starts from: the arrow on it, else the end nearer
        # its «UP / DN» note
        start, end = secs[0], secs[-1]
        m0 = ((start[0][0] + start[1][0]) / 2, (start[0][1] + start[1][1]) / 2)
        m1 = ((end[0][0] + end[1][0]) / 2, (end[0][1] + end[1][1]) / 2)
        flip = None
        for ax, ay, rot in arrows:
            if foot.buffer(1.5).contains(Point(ax, ay)):
                r = math.radians(rot)
                flip = (math.cos(r) * (m1[0] - m0[0])
                        + math.sin(r) * (m1[1] - m0[1])) < 0
                break
        if flip is None and label is not None:
            flip = math.dist((label["x"], label["y"]), m1) < \
                math.dist((label["x"], label["y"]), m0)
        if flip:
            secs = [(b, a) for a, b in reversed(secs)]
        w = sum(math.dist(a, b) for a, b in secs) / len(secs)
        out.append({"sections": [[[round(a[0], 4), round(a[1], 4)],
                                  [round(b[0], 4), round(b[1], 4)]]
                                 for a, b in secs],
                    "rise": round(sign * rise, 4), "w": round(w, 3),
                    "run": round(run, 3)})
    return out


def add_turns(ramps, segs, reach=5.5) -> int:
    """The turns at the ramps' ends (a curved edge, the entry's corner):
    the ramp lines no ramp took, within ``reach`` of a ramp's end, become
    a flat pad joined to that end, at that end's height. Returns how many
    pads."""
    from shapely.geometry import LineString, MultiPoint, Point
    from shapely.ops import unary_union
    if not ramps:
        return 0
    taken = unary_union([footprint(r).buffer(0.3) for r in ramps])
    free = [((s[0], s[1]), (s[2], s[3])) for s in segs
            if math.dist((s[0], s[1]), (s[2], s[3])) > 0.05
            and not taken.contains(LineString([(s[0], s[1]),
                                               (s[2], s[3])]))]
    if not free:
        return 0
    blob = unary_union([LineString(x).buffer(1.0) for x in free])
    n = 0
    for g in getattr(blob, "geoms", [blob]):
        mine = [x for x in free if g.intersects(LineString(x))]
        # the ramp end nearest it
        best = None
        for r in ramps:
            secs = r["sections"]
            for end, (a, b) in ((0, secs[0]), (1, secs[-1])):
                d = LineString([a, b]).distance(g)
                if d < 3.0 and (best is None or d < best[0]):
                    best = (d, r, end, (tuple(a), tuple(b)))
        if best is None:
            continue
        _d, r, end, (a, b) = best
        mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        pts = [p for x in mine for p in x
               if Point(p).distance(mid) <= reach]
        if len(pts) < 2:
            continue
        hull = MultiPoint(pts + [a, b]).convex_hull
        pad = hull.difference(footprint(r))
        pad = max(getattr(pad, "geoms", [pad]), key=lambda q: q.area) \
            if not pad.is_empty else pad
        if pad.is_empty or pad.geom_type != "Polygon" or pad.area < 1.0:
            continue
        r.setdefault("pads", []).append(
            {"end": end, "pts": [[round(x, 4), round(y, 4)] for x, y in
                                 list(pad.simplify(0.02).exterior.coords)[:-1]]})
        n += 1
    return n


def pad_faces(r, z0, t=0.20) -> list:
    """The turns at a ramp's ends: flat slabs at the end's height."""
    zs = ramp_z(r)
    f = []
    for pd in r.get("pads") or []:
        z = z0 + (zs[-1] if pd["end"] else zs[0])
        pts = [tuple(p) for p in pd["pts"]]
        a2 = sum(p[0] * q[1] - q[0] * p[1]
                 for p, q in zip(pts, pts[1:] + pts[:1]))
        if a2 < 0:
            pts = pts[::-1]
        f.append({"loop": [(*p, z) for p in pts], "holes": [],
                  "color": RAMP_TOP})
        f.append({"loop": [(*p, z - t) for p in reversed(pts)], "holes": [],
                  "color": RAMP_C})
        for p, q in zip(pts, pts[1:] + pts[:1]):
            f.append({"loop": [(*p, z - t), (*q, z - t), (*q, z), (*p, z)],
                      "holes": [], "color": RAMP_C})
    return f


def pad_lines(r) -> list:
    out = []
    for pd in r.get("pads") or []:
        pts = [tuple(p) for p in pd["pts"]]
        out += list(zip(pts, pts[1:] + pts[:1]))
    return out


def stalls_of(bays, cars) -> list:
    """The parking spaces: the bay rectangles the parking lines close
    (8–25 m²), and every car symbol standing outside them — in reading
    order (rows top to bottom, then left to right).
    [{"c": [x, y], "ang": ° of the bay's length, "L", "W"}]."""
    from shapely.geometry import LineString, Point
    from shapely.ops import polygonize, unary_union
    out = []
    lines = [LineString(b) for b in bays
             if math.dist(tuple(b[0]), tuple(b[1])) > 0.05]
    if lines:
        for f in polygonize(unary_union(lines)):
            mr = f.minimum_rotated_rectangle
            if 8.0 <= f.area <= 25.0 and mr.area > 0 and \
                    f.area / mr.area > 0.85:
                c = f.centroid
                q = list(mr.exterior.coords)
                e1 = (q[1][0] - q[0][0], q[1][1] - q[0][1])
                e2 = (q[2][0] - q[1][0], q[2][1] - q[1][1])
                l1, l2 = math.hypot(*e1), math.hypot(*e2)
                e = e1 if l1 >= l2 else e2
                out.append((f, (c.x, c.y), math.degrees(math.atan2(e[1], e[0])),
                            max(l1, l2), min(l1, l2)))
    for c in cars:
        p = Point(c["c"])
        if not any(f.contains(p) for f, *_r in out):
            out.append((p.buffer(0.01), (p.x, p.y), float(c.get("ang", 90.0)),
                        float(c.get("L", 4.8)), float(c.get("W", 2.4))))
    if not out:
        return []
    # rows: by y (within 3 m), top first; in a row left to right
    recs = sorted((r[1:] for r in out), key=lambda r: -r[0][1])
    rows, cur = [], [recs[0]]
    for r in recs[1:]:
        if abs(r[0][1] - cur[0][0][1]) <= 3.0:
            cur.append(r)
        else:
            rows.append(cur)
            cur = [r]
    rows.append(cur)
    return [{"c": [round(c[0], 4), round(c[1], 4)], "ang": round(a % 360.0, 2),
             "L": round(L, 3), "W": round(W, 3)}
            for row in rows for c, a, L, W in sorted(row)]


def ramp_z(r) -> list:
    s = _length([(tuple(a), tuple(b)) for a, b in r["sections"]])
    run = s[-1] or 1.0
    return [float(r["rise"]) * v / run for v in s]


def ramp_faces(r, z0, t=0.20) -> list:
    """A sloped RC ramp: its top, soffit, sides and ends."""
    secs = [(tuple(a), tuple(b)) for a, b in r["sections"]]
    zs = [z0 + v for v in ramp_z(r)]
    f = []

    def F(pts, col):
        f.append({"loop": pts, "holes": [], "color": col})
    for i in range(len(secs) - 1):
        (a0, b0), (a1, b1) = secs[i], secs[i + 1]
        za, zb = zs[i], zs[i + 1]
        A0, B0 = (*a0, za), (*b0, za)
        A1, B1 = (*a1, zb), (*b1, zb)
        a0l, b0l = (*a0, za - t), (*b0, za - t)
        a1l, b1l = (*a1, zb - t), (*b1, zb - t)
        F([A0, B0, B1, A1], RAMP_TOP)                 # the driving surface
        F([a0l, a1l, b1l, b0l], RAMP_C)               # the soffit
        F([A0, A1, a1l, a0l], RAMP_C)                 # left side
        F([B0, b0l, b1l, B1], RAMP_C)                 # right side
    for i, rev in ((0, True), (len(secs) - 1, False)):
        a, b = secs[i]
        z = zs[i]
        q = [(*a, z), (*a, z - t), (*b, z - t), (*b, z)]
        F(q if rev else q[::-1], RAMP_C)
    return f


def ramp_plan(r) -> tuple:
    """(lines, (arrow tip x, y, «UP»|«DN»)): outline, stripes, arrow."""
    secs = [(tuple(a), tuple(b)) for a, b in r["sections"]]
    lines = []
    for (a0, b0), (a1, b1) in zip(secs, secs[1:]):
        lines += [(a0, a1), (b0, b1)]
    lines += [secs[0], secs[-1]]
    mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in secs]
    # the stripes, every ~0.6 m along
    s = _length(secs)
    step, nxt = 0.6, 0.6
    for i in range(len(secs) - 1):
        while nxt < s[i + 1]:
            f = (nxt - s[i]) / max(s[i + 1] - s[i], 1e-9)
            (a0, b0), (a1, b1) = secs[i], secs[i + 1]
            lines.append(((a0[0] + (a1[0] - a0[0]) * f,
                           a0[1] + (a1[1] - a0[1]) * f),
                          (b0[0] + (b1[0] - b0[0]) * f,
                           b0[1] + (b1[1] - b0[1]) * f)))
            nxt += step
    # the arrow along the middle (from the start, the way up or down)
    lines += list(zip(mids, mids[1:]))
    tip, prev = mids[-1], mids[-2]
    d = math.dist(tip, prev) or 1.0
    t = ((tip[0] - prev[0]) / d, (tip[1] - prev[1]) / d)
    n = (-t[1], t[0])
    for sgn in (1, -1):
        lines.append((tip, (tip[0] - t[0] * 0.6 + n[0] * 0.3 * sgn,
                            tip[1] - t[1] * 0.6 + n[1] * 0.3 * sgn)))
    word = "UP" if float(r["rise"]) >= 0 else "DN"
    mid = mids[len(mids) // 2]
    return lines, (mid[0], mid[1], word)


def footprint(r, pads=False):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    secs = [(tuple(a), tuple(b)) for a, b in r["sections"]]
    parts = [Polygon([a, b, d, c]).buffer(0)
             for (a, b), (c, d) in zip(secs, secs[1:])]
    if pads:
        parts += [Polygon(pd["pts"]).buffer(0) for pd in r.get("pads") or []
                  if len(pd["pts"]) >= 3]
    return unary_union(parts)


# ---- level marks ------------------------------------------------------------------
def mark_lines(x, y, r=0.22) -> tuple:
    """A level symbol: a quartered circle, its leader and the shelf the
    text sits on; returns (lines, text point)."""
    lines = []
    k = 20
    pts = [(x + r * math.cos(2 * math.pi * i / k),
            y + r * math.sin(2 * math.pi * i / k)) for i in range(k)]
    lines += [(pts[i], pts[(i + 1) % k]) for i in range(k)]
    lines += [((x - r, y), (x + r, y)), ((x, y - r), (x, y + r))]
    # two quarters filled (hatched)
    for q in (0, 2):
        for j in range(1, 5):
            a = (q * 90 + j * 18) * math.pi / 180
            lines.append(((x, y), (x + r * math.cos(a), y + r * math.sin(a))))
    ex, ey = x + 0.55, y + 0.45
    lines += [((x + r * 0.7, y + r * 0.7), (ex, ey)), ((ex, ey), (ex + 1.6, ey))]
    return lines, (ex + 0.8, ey + 0.18)


# ---- ramp routes: the pieces, their turns and lanes, as ONE ramp -----------
def _unit2(v):
    L = math.hypot(*v) or 1.0
    return (v[0] / L, v[1] / L)


def _mid2(sec):
    (a, b) = sec
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _meet(p, d, q, e):
    """Where the line p + s·d meets the line q + r·e (None: parallel)."""
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 0.3:
        return None
    s = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return (p[0] + d[0] * s, p[1] + d[1] * s)


def _fillet(path, R) -> list:
    """The path's corners rounded (radius R, less where a leg is short)."""
    if len(path) < 3:
        return list(path)
    out = [path[0]]
    for i in range(1, len(path) - 1):
        p0, p1, p2 = out[-1], path[i], path[i + 1]
        d1 = _unit2((p1[0] - p0[0], p1[1] - p0[1]))
        d2 = _unit2((p2[0] - p1[0], p2[1] - p1[1]))
        cosang = max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1]))
        turn = math.acos(cosang)
        if turn < math.radians(8):
            out.append(p1)
            continue
        L1, L2 = math.dist(p0, p1), math.dist(p1, p2)
        tl = min(R * math.tan(turn / 2), L1 * 0.95, L2 * 0.5)
        r = tl / math.tan(turn / 2)
        a = (p1[0] - d1[0] * tl, p1[1] - d1[1] * tl)
        b = (p1[0] + d2[0] * tl, p1[1] + d2[1] * tl)
        side = 1.0 if d1[0] * d2[1] - d1[1] * d2[0] > 0 else -1.0
        n1 = (-d1[1] * side, d1[0] * side)
        c = (a[0] + n1[0] * r, a[1] + n1[1] * r)
        a0 = math.atan2(a[1] - c[1], a[0] - c[0])
        a1 = math.atan2(b[1] - c[1], b[0] - c[0])
        da = a1 - a0
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        k = max(3, int(abs(da) / math.radians(10)))
        for j in range(k + 1):
            t = a0 + da * j / k
            out.append((c[0] + r * math.cos(t), c[1] + r * math.sin(t)))
    out.append(path[-1])
    return out


def _sections_along(path, w, step=0.6) -> list:
    """Sections (left, right) square to a smooth path, every ``step``."""
    pts = [path[0]]
    for p in path[1:]:
        if math.dist(p, pts[-1]) > 1e-3:
            pts.append(p)
    if len(pts) < 2:
        return []
    dense = [pts[0]]
    for p, q in zip(pts, pts[1:]):
        L = math.dist(p, q)
        k = max(1, int(L / step))
        for j in range(1, k + 1):
            dense.append((p[0] + (q[0] - p[0]) * j / k,
                          p[1] + (q[1] - p[1]) * j / k))
    secs = []
    h = w / 2
    for i, p in enumerate(dense):
        a = dense[max(i - 1, 0)]
        b = dense[min(i + 1, len(dense) - 1)]
        t = _unit2((b[0] - a[0], b[1] - a[1]))
        n = (-t[1], t[0])
        secs.append([[round(p[0] + n[0] * h, 4), round(p[1] + n[1] * h, 4)],
                     [round(p[0] - n[0] * h, 4), round(p[1] - n[1] * h, 4)]])
    return secs


def routes(pieces, segs, texts, reach=6.0) -> list:
    """The ramp pieces joined into routes, each ONE continuous ramp from
    floor to floor: a piece's end runs on into the next piece (round the
    corner the plan draws), or into the lane the plan draws at its foot or
    head (a line as wide as the ramp, and the side lines beyond it). The
    route climbs evenly from end to end, by the climbs its notes give (all
    the ramp notes on it), else by its pieces' rises. Returns the routes
    as ramps ({sections, rise, w, run})."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    if not pieces:
        return []
    P = []
    for r in pieces:
        secs = [(tuple(a), tuple(b)) for a, b in r["sections"]]
        rise = float(r["rise"])
        dn = rise < 0
        if dn:                                   # uphill order
            secs = [(b, a) for a, b in reversed(secs)]
            rise = -rise
        mids = [_mid2(s) for s in secs]
        P.append({"fp": footprint({"sections": [[list(a_), list(b_)]
                                                for a_, b_ in secs]}
                                  ).buffer(0.3),
                  "secs": secs, "mids": mids, "rise": rise, "dn": dn,
                  "w": float(r["w"]), "run": float(r["run"]),
                  "next": None, "prev": None, "foot": None, "head": None})
    taken = unary_union([footprint(r).buffer(0.3) for r in pieces])
    free = [((s[0], s[1]), (s[2], s[3])) for s in segs
            if math.dist((s[0], s[1]), (s[2], s[3])) > 0.05
            and not taken.contains(LineString([(s[0], s[1]), (s[2], s[3])]))]

    def end_axis(p, top):
        m = p["mids"]
        if top:
            return m[-1], _unit2((m[-1][0] - m[-2][0], m[-1][1] - m[-2][1]))
        return m[0], _unit2((m[0][0] - m[1][0], m[0][1] - m[1][1]))

    # a piece's head into the next piece's foot (uphill, both ways)
    pairs = []
    for i, a in enumerate(P):
        ma, _da = end_axis(a, True)
        for j, b in enumerate(P):
            if i == j:
                continue
            mb, _db = end_axis(b, False)
            dd = math.dist(ma, mb)
            if dd <= reach + max(a["w"], b["w"]) * 0.5:
                pairs.append((dd, i, j))
    for dd, i, j in sorted(pairs):
        if P[i]["next"] is None and P[j]["prev"] is None:
            # no loop
            k, seen = j, set()
            while k is not None and k not in seen:
                seen.add(k)
                k = P[k]["next"]
            if i in seen:
                continue
            P[i]["next"], P[j]["prev"] = j, i

    def lane(p, top):
        """A lane the plan draws at a free end: (far point, axis out)."""
        m, d = end_axis(p, top)
        w = p["w"]
        best = None
        for ln in free:
            L = math.dist(*ln)
            if not 0.75 * w <= L <= 1.3 * w:
                continue
            if built and built_fp.intersects(LineString(ln).centroid.buffer(0.2)):
                continue                       # another route's lane
            if p["fp"].intersects(LineString(ln)):
                continue                       # its own side line
            q = _mid2(ln)
            dd = math.dist(m, q)
            if dd > reach or dd < 0.5:
                continue
            if best is None or dd > best[0]:
                best = (dd, ln)
        if best is None:
            return None
        ln = best[1]
        q = _mid2(ln)
        e = _unit2((ln[1][0] - ln[0][0], ln[1][1] - ln[0][1]))
        e = (-e[1], e[0])                         # the lane's axis
        if (q[0] - m[0]) * e[0] + (q[1] - m[1]) * e[1] < 0:
            e = (-e[0], -e[1])                    # pointing away from it
        # side lines running on from the line's ends: the lane goes on
        far = q
        for end in ln:
            for s in free:
                for u, v in ((s[0], s[1]), (s[1], s[0])):
                    if math.dist(u, end) < 0.15:
                        g = _unit2((v[0] - u[0], v[1] - u[1]))
                        if abs(g[0] * e[0] + g[1] * e[1]) > 0.95 and \
                                (v[0] - u[0]) * e[0] + (v[1] - u[1]) * e[1] > 0:
                            ext = (v[0] - u[0]) * e[0] + (v[1] - u[1]) * e[1]
                            cand = (q[0] + e[0] * ext, q[1] + e[1] * ext)
                            if math.dist(cand, q) > math.dist(far, q):
                                far = cand
        return q, far, e

    notes = [nt for nt in ramp_notes(texts) if nt["rise"] is not None
             or nt["grad"] is not None]
    out = []
    built, built_fp = [], None
    chains = []
    for i0 in [i for i, p in enumerate(P) if p["prev"] is None]:
        chain = []
        k = i0
        while k is not None and k not in chain:
            chain.append(k)
            k = P[k]["next"]
        chains.append(chain)
    # the longest routes first: a short one never takes their lanes
    chains.sort(key=lambda c: -sum(P[k]["run"] for k in c))
    for chain in chains:
        w = max(P[k]["w"] for k in chain)
        path = []
        # the foot: its lane, the corner into the first piece
        first = P[chain[0]]
        foot = lane(first, False)
        mids0 = list(first["mids"])
        if foot is not None:
            q, far, e = foot
            m, d = end_axis(first, False)
            c = _meet(m, d, q, (-e[0], -e[1]))
            path += [far, q] if math.dist(far, q) > 0.05 else [q]
            if c is not None:
                din = (-d[0], -d[1])
                tc = (c[0] - m[0]) * din[0] + (c[1] - m[1]) * din[1]
                mids0 = [p_ for p_ in mids0
                         if (p_[0] - m[0]) * din[0] + (p_[1] - m[1]) * din[1]
                         > tc + 0.05]
                path.append(c)
        cur = mids0
        for n_, k in enumerate(chain):
            p = P[k]
            if n_ > 0:
                prev = P[chain[n_ - 1]]
                ma, da = end_axis(prev, True)
                mb, db = end_axis(p, False)
                c = _meet(ma, da, mb, db)
                mids_b = list(p["mids"])
                if c is not None:
                    # each piece cut back to the corner
                    ta = (c[0] - ma[0]) * da[0] + (c[1] - ma[1]) * da[1]
                    cur = [p_ for p_ in cur
                           if (p_[0] - ma[0]) * da[0] + (p_[1] - ma[1]) * da[1]
                           < ta - 0.05] if ta < 0 else cur
                    din = (-db[0], -db[1])
                    tb = (c[0] - mb[0]) * din[0] + (c[1] - mb[1]) * din[1]
                    mids_b = [p_ for p_ in mids_b
                              if (p_[0] - mb[0]) * din[0]
                              + (p_[1] - mb[1]) * din[1] > tb + 0.05]
                    path += cur + [c]
                else:
                    path += cur
                cur = mids_b
        last = P[chain[-1]]
        head = lane(last, True)
        if head is not None:
            q, far, e = head
            m, d = end_axis(last, True)
            c = _meet(m, d, q, (-e[0], -e[1]))
            if c is not None:
                tc = (c[0] - m[0]) * d[0] + (c[1] - m[1]) * d[1]
                if tc < 0:
                    cur = [p_ for p_ in cur
                           if (p_[0] - m[0]) * d[0] + (p_[1] - m[1]) * d[1]
                           < tc - 0.05]
                path += cur + [c, q]
            else:
                path += cur + [q]
            if math.dist(far, q) > 0.05:
                path.append(far)
        else:
            path += cur
        # clean: no doubled points, no back-steps
        clean = []
        for p_ in path:
            if not clean or math.dist(p_, clean[-1]) > 0.05:
                clean.append(p_)
        if len(clean) < 2:
            continue
        smooth = _fillet(clean, max(w / 2 + 0.6, 2.0))
        secs = _sections_along(smooth, w)
        if len(secs) < 2:
            continue
        run = _length([(tuple(a), tuple(b)) for a, b in secs])[-1]
        fp_ = footprint({"sections": secs})
        built.append(fp_)
        built_fp = unary_union(built)
        out.append({"sections": secs, "w": w, "run": run, "chain": chain,
                    "fp": fp_})
    # each climb note to the route nearest it (within 2 m)
    for nt in notes:
        pt = Point(nt["x"], nt["y"])
        near = [(r_["fp"].distance(pt), r_) for r_ in out]
        near = [x for x in near if x[0] <= 2.0]
        if near:
            min(near, key=lambda x: x[0])[1].setdefault("notes", []).append(nt)
    res = []
    for r_ in out:
        chain, secs, w, run = r_["chain"], r_["sections"], r_["w"], r_["run"]
        climb = 0.0
        seen_ = set()
        for nt in r_.get("notes", []):
            key_ = (nt["rise"], nt["grad"], nt.get("length"))
            if key_ in seen_:                    # one note drawn twice
                continue
            seen_.add(key_)
            if nt["rise"]:
                climb += nt["rise"]
            elif nt["grad"] and nt.get("length"):
                climb += nt["length"] / nt["grad"]
        if climb < 0.05:
            climb = sum(P[k]["rise"] for k in chain)
        climb = min(climb, 8.0)
        # up from this floor — unless every piece of it is noted down
        down = all(P[k]["dn"] for k in chain)
        if down:                                 # from the floor, down
            secs = [[b, a] for a, b in reversed(secs)]
            rise = -climb
        else:
            rise = climb
        res.append({"sections": secs, "rise": round(rise, 4),
                    "w": round(w, 3), "run": round(run, 3),
                    "pieces": len(chain)})
    return res


def fit_ends(r, segs, reach=3.0) -> int:
    """The ramp's ends cut along the line the plan draws there (a ramp
    ending on a slanted edge, the plot's line, a skewed slab edge): each
    end section moved to where its two side lines meet that line. Returns
    how many ends moved."""
    secs = [[tuple(a), tuple(b)] for a, b in r["sections"]]
    if len(secs) < 3:
        return 0
    moved = 0
    for end, nb in ((0, 1), (len(secs) - 1, len(secs) - 2)):
        (a, b), (a1, b1) = secs[end], secs[nb]
        w = math.dist(a, b)
        if w < 0.5:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        da = (a[0] - a1[0], a[1] - a1[1])
        db = (b[0] - b1[0], b[1] - b1[1])
        if math.hypot(*da) < 1e-6 or math.hypot(*db) < 1e-6:
            continue
        da = (da[0] / math.hypot(*da), da[1] / math.hypot(*da))
        db = (db[0] / math.hypot(*db), db[1] / math.hypot(*db))
        sec_ang = math.atan2(b[1] - a[1], b[0] - a[0])
        best = None
        for s in segs:
            p, q = (s[0], s[1]), (s[2], s[3])
            L = math.dist(p, q)
            if L < 0.6 * w:
                continue
            e = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
            dang = abs((math.atan2(e[1], e[0]) - sec_ang + math.pi / 2)
                       % math.pi - math.pi / 2)
            if dang < math.radians(3) or dang > math.radians(60):
                continue                 # square already, or along the ramp
            # the line's distance from the end's middle
            dm = abs((m[0] - p[0]) * e[1] - (m[1] - p[1]) * e[0])
            if dm > reach:
                continue
            pa = _meet(a, da, p, e)
            pb = _meet(b, db, p, e)
            if pa is None or pb is None:
                continue

            def on(x):
                t = (x[0] - p[0]) * e[0] + (x[1] - p[1]) * e[1]
                return -0.5 <= t <= L + 0.5
            if not (on(pa) and on(pb)) or math.dist(pa, a) > reach or \
                    math.dist(pb, b) > reach:
                continue
            if best is None or dm < best[0]:
                best = (dm, pa, pb)
        if best is None:
            continue
        _d, pa, pb = best
        secs[end] = [pa, pb]
        moved += 1
    if moved:
        r["sections"] = [[[round(a[0], 4), round(a[1], 4)],
                          [round(b[0], 4), round(b[1], 4)]] for a, b in secs]
    return moved


def to_walls(r, walls, reach=1.2, corner=3.5) -> int:
    """The ramp widened to the walls round it: each section's ends pushed
    out to the nearest wall face — up to ``reach`` along the straight, up
    to ``corner`` where it turns (the outside of a bend fills its corner)
    — so no strip of floor is left between a ramp and its walls.
    ``walls``: the walls' plan (shapely). Returns how many ends moved."""
    from shapely.geometry import LineString, Point
    secs = [[tuple(a), tuple(b)] for a, b in r["sections"]]
    if len(secs) < 2 or walls is None or walls.is_empty:
        return 0

    def ang(i):
        (a, b) = secs[i]
        return math.atan2(b[1] - a[1], b[0] - a[0])
    n = len(secs)
    moved = 0
    out = []
    for i, (a, b) in enumerate(secs):
        # turning here? the section's direction against its neighbours'
        da = 0.0
        for j in (i - 1, i + 1):
            if 0 <= j < n:
                d = abs((ang(i) - ang(j) + math.pi) % (2 * math.pi) - math.pi)
                da = max(da, d)
        lim = corner if da > math.radians(2.5) else reach
        L = math.dist(a, b) or 1.0
        v = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        new = []
        for p, sg in ((a, -1.0), (b, 1.0)):
            if walls.contains(Point(p)):
                new.append(p)
                continue
            q = (p[0] + v[0] * sg * lim, p[1] + v[1] * sg * lim)
            hit = LineString([p, q]).intersection(walls)
            if hit.is_empty:
                new.append(p)
                continue
            d = Point(p).distance(hit)
            if d < 0.02:
                new.append(p)
                continue
            new.append((p[0] + v[0] * sg * d, p[1] + v[1] * sg * d))
            moved += 1
        out.append([[round(new[0][0], 4), round(new[0][1], 4)],
                    [round(new[1][0], 4), round(new[1][1], 4)]])
    # a corner filled by ONE section alone is a spike, not a corner: an
    # end pushed further than the straight's reach keeps its push only
    # when a neighbour's same end was pushed that far too
    far = [[math.dist(out[i][k], secs[i][k]) > reach + 0.05 for k in (0, 1)]
           for i in range(n)]
    for i in range(n):
        for k in (0, 1):
            if far[i][k] and not any(far[j][k] for j in (i - 1, i + 1)
                                     if 0 <= j < n):
                out[i][k] = [round(secs[i][k][0], 4), round(secs[i][k][1], 4)]
                moved -= 1
    r["sections"] = out
    return moved
