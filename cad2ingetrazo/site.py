# SPDX-License-Identifier: GPL-3.0-or-later
"""The ground around the building: a boundary wall on the plot's edge
(its outer face on the property line), pillars at its corners and gates,
and the gates themselves (swing — single or double — or sliding). And
the column grid of the plans: axes 1, 2, 3… and A, B, C… with bubbles.

``doc["site"]`` = {"wall": bool, "h", "t", "pillars": bool, "pillar",
                   "gates": [{"side", "pos" (m from the side's start to
                   the gate's centre), "w", "kind": "single" | "double" |
                   "sliding"}]}
``doc["grid"]`` = {"on": bool, "source": "columns" | "corners" |
                   "spacing", "xs": [m…], "ys": [m…] (spacing: the bays),
                   "ox", "oy" (spacing: the first axis), "ext": m}
"""
from __future__ import annotations

import math

SITE_DEFAULT = {"wall": False, "h": 2.10, "t": 0.23, "pillars": True,
                "pillar": 0.35, "gates": []}
GRID_DEFAULT = {"on": False, "source": "columns", "xs": [], "ys": [],
                "lines": [],
                "ox": 0.0, "oy": 0.0, "ext": 2.2}
GATE_KINDS = [("double", "Double swing"), ("single", "Single swing"),
              ("sliding", "Sliding")]
WALL_COLOR = (0.80, 0.78, 0.74)
PILLAR_COLOR = (0.72, 0.70, 0.66)
GATE_COLOR = (0.22, 0.24, 0.27)


def load_site(raw) -> dict:
    out = dict(SITE_DEFAULT, gates=[])
    if isinstance(raw, dict):
        for k in ("wall", "pillars"):
            if k in raw:
                out[k] = bool(raw[k])
        for k, lo, hi in (("h", 0.3, 6.0), ("t", 0.05, 1.0),
                          ("pillar", 0.1, 1.5)):
            try:
                out[k] = round(min(max(float(raw.get(k, out[k])), lo), hi), 3)
            except (TypeError, ValueError):
                pass
        for g in raw.get("gates") or []:
            try:
                out["gates"].append({
                    "side": int(g["side"]), "pos": float(g["pos"]),
                    "w": min(max(float(g["w"]), 0.6), 15.0),
                    "kind": g.get("kind") if g.get("kind") in
                    ("single", "double", "sliding") else "double"})
            except (KeyError, TypeError, ValueError):
                continue
    return out


def load_grid(raw) -> dict:
    out = dict(GRID_DEFAULT, xs=[], ys=[])
    if isinstance(raw, dict):
        out["on"] = bool(raw.get("on", False))
        if raw.get("source") in ("columns", "corners", "spacing", "cad"):
            out["source"] = raw["source"]
        lines = []
        for ln in raw.get("lines") or []:
            try:
                lines.append({"a": [float(ln["a"][0]), float(ln["a"][1])],
                              "b": [float(ln["b"][0]), float(ln["b"][1])],
                              "label": str(ln.get("label") or "")[:6]})
            except (KeyError, TypeError, ValueError, IndexError):
                continue
        out["lines"] = lines[:80]
        for k in ("xs", "ys"):
            try:
                out[k] = [round(float(v), 3) for v in raw.get(k) or []
                          if 0.2 <= float(v) <= 100][:60]
            except (TypeError, ValueError):
                pass
        for k in ("ox", "oy", "ext"):
            try:
                out[k] = float(raw.get(k, out[k]))
            except (TypeError, ValueError):
                pass
    return out


def side_frame(corners, i):
    """(start, unit along, unit inward normal, length) of plot side i."""
    n = len(corners)
    a, b = corners[i % n], corners[(i + 1) % n]
    L = math.dist(a, b) or 1.0
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    # corners are counter-clockwise: inside is on the left
    return a, u, (-u[1], u[0]), L


def gate_box(corners, g, t):
    """The gate's opening across the wall: 4 corners (a little deeper than
    the wall, so the cut goes clean through)."""
    a, u, nv, L = side_frame(corners, g["side"])
    c = min(max(g["pos"], g["w"] / 2), L - g["w"] / 2)
    h = g["w"] / 2
    p0 = (a[0] + u[0] * (c - h), a[1] + u[1] * (c - h))
    p1 = (a[0] + u[0] * (c + h), a[1] + u[1] * (c + h))
    d0, d1 = -0.05, t + 0.05
    return [(p0[0] + nv[0] * d0, p0[1] + nv[1] * d0),
            (p1[0] + nv[0] * d0, p1[1] + nv[1] * d0),
            (p1[0] + nv[0] * d1, p1[1] + nv[1] * d1),
            (p0[0] + nv[0] * d1, p0[1] + nv[1] * d1)], (p0, p1, u, nv)


def build(corners, site, z0):
    """[(name, kind, faces, color)] — the wall pieces, pillars, gates —
    and the plan symbols [(a, b)…] (gate swings) at z0."""
    from shapely.geometry import Polygon

    from .engine import walls as W
    out, sym = [], []
    if not site.get("wall") or len(corners) < 3:
        return out, sym
    t, h = float(site["t"]), float(site["h"])
    plot = Polygon(corners)
    if not plot.is_valid:
        plot = plot.buffer(0)
    inner = plot.buffer(-t, join_style=2)
    ring = plot.difference(inner)
    gates = []
    for g in site["gates"]:
        if 0 <= g["side"] < len(corners):
            quad, frame = gate_box(corners, g, t)
            gates.append((g, frame))
            ring = ring.difference(Polygon(quad))
    pieces = list(getattr(ring, "geoms", [ring]))
    for k, pc in enumerate(pieces):
        if pc.is_empty or pc.area < 1e-4:
            continue
        piece = {"outer": _ccw(list(pc.exterior.coords)[:-1]),
                 "holes": [list(reversed(_ccw(list(r.coords)[:-1])))
                           for r in pc.interiors]}
        out.append((f"Boundary wall {k + 1}", "boundary",
                    W.solid(piece, z0, z0 + h), WALL_COLOR))
    if site.get("pillars"):
        s = float(site["pillar"])
        spots = []
        n = len(corners)
        for i in range(n):                       # the corners, inside
            b, c = corners[i], corners[(i + 1) % n]
            p = inner.exterior.interpolate(inner.exterior.project(
                _pt(b))) if not inner.is_empty else None
            mid = ((b[0] + p.x) / 2, (b[1] + p.y) / 2) if p else b
            spots.append((mid, _angle(b, c)))
        for g, (p0, p1, u, nv) in gates:          # the gate's jambs
            for p in (p0, p1):
                q = (p[0] + nv[0] * t / 2 - u[0] * s / 2 * (1 if p is p0
                                                            else -1),
                     p[1] + nv[1] * t / 2 - u[1] * s / 2 * (1 if p is p0
                                                            else -1))
                spots.append((q, math.degrees(math.atan2(u[1], u[0]))))
        for k, (c, ang) in enumerate(spots):
            sq = _square(c, s, ang)
            out.append((f"Pillar {k + 1}", "pillar",
                        W.solid({"outer": _ccw(sq), "holes": []}, z0,
                                z0 + h + 0.15), PILLAR_COLOR))
    for k, (g, (p0, p1, u, nv)) in enumerate(gates):
        wv = math.dist(p0, p1)
        mid_d = t / 2
        gh = max(h - 0.15, 0.6)
        leaves = [(0.0, wv)] if g["kind"] != "double" else \
            [(0.0, wv / 2 - 0.01), (wv / 2 + 0.01, wv)]
        for j, (s0, s1) in enumerate(leaves):
            a = (p0[0] + u[0] * s0 + nv[0] * mid_d,
                 p0[1] + u[1] * s0 + nv[1] * mid_d)
            b = (p0[0] + u[0] * s1 + nv[0] * mid_d,
                 p0[1] + u[1] * s1 + nv[1] * mid_d)
            leaf = _band(a, b, 0.05)
            out.append((f"Gate {k + 1}" + (f" leaf {j + 1}" if len(leaves) > 1
                                           else ""), "gate",
                        W.solid({"outer": _ccw(leaf), "holes": []},
                                z0 + 0.05, z0 + 0.05 + gh), GATE_COLOR))
        # plan symbol: swings opening inwards, or the sliding track
        if g["kind"] == "sliding":
            e = (p1[0] + u[0] * wv + nv[0] * (t + 0.15),
                 p1[1] + u[1] * wv + nv[1] * (t + 0.15))
            s_ = (p0[0] + nv[0] * (t + 0.15), p0[1] + nv[1] * (t + 0.15))
            sym.append((s_, e))
        else:
            hinges = [(p0, u, wv if g["kind"] == "single" else wv / 2)]
            if g["kind"] == "double":
                hinges.append((p1, (-u[0], -u[1]), wv / 2))
            for hp, du, r in hinges:
                tip = (hp[0] + nv[0] * (t + r), hp[1] + nv[1] * (t + r))
                base = (hp[0] + nv[0] * t, hp[1] + nv[1] * t)
                sym.append((base, tip))
                prev = None
                for q in range(13):
                    ang = math.radians(90 * q / 12)
                    v = (du[0] * math.cos(ang) + nv[0] * math.sin(ang),
                         du[1] * math.cos(ang) + nv[1] * math.sin(ang))
                    p = (base[0] + v[0] * r, base[1] + v[1] * r)
                    if prev:
                        sym.append((prev, p))
                    prev = p
    return out, sym


def _pt(p):
    from shapely.geometry import Point
    return Point(p[0], p[1])


def _angle(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _square(c, s, ang):
    r = math.radians(ang)
    ca, sa = math.cos(r), math.sin(r)
    h = s / 2
    return [(c[0] + x * ca - y * sa, c[1] + x * sa + y * ca)
            for x, y in ((-h, -h), (h, -h), (h, h), (-h, h))]


def _band(a, b, w):
    L = math.dist(a, b) or 1.0
    nx, ny = -(b[1] - a[1]) / L * w / 2, (b[0] - a[0]) / L * w / 2
    return [(a[0] - nx, a[1] - ny), (b[0] - nx, b[1] - ny),
            (b[0] + nx, b[1] + ny), (a[0] + nx, a[1] + ny)]


def _ccw(loop):
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(loop, loop[1:] + loop[:1]))
    return list(loop) if a >= 0 else list(reversed(loop))


# ---- the column grid -----------------------------------------------------------------
def _cluster(vals, tol=0.15):
    vals = sorted(vals)
    out = []
    for v in vals:
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [round(sum(c) / len(c), 3) for c in out]


def axes(arch, grid):
    """(xs, ys): the grid's axes (m) — vertical lines at xs, horizontal at
    ys — from the columns, the wall corners, or the bays typed."""
    from .engine import structure as S
    src = grid["source"]
    if src == "spacing":
        xs, ys = [grid["ox"]], [grid["oy"]]
        for d in grid["xs"]:
            xs.append(round(xs[-1] + d, 3))
        for d in grid["ys"]:
            ys.append(round(ys[-1] + d, 3))
        return (xs if grid["xs"] else []), (ys if grid["ys"] else [])
    pts = []
    if src == "columns":
        pts = [(float(e["x"]), float(e["y"])) for e in arch["structure"]
               if e["type"] == "column"]
    if not pts:                       # no columns: the walls' corners
        for lv in arch["levels"]:
            walls = [w for w in arch["walls"] if w["level"] == lv["id"]]
            pts += [tuple(p) for p in S.wall_corners(walls)]
    if not pts:
        return [], []
    xs = _cluster([p[0] for p in pts])
    ys = _cluster([p[1] for p in pts])
    # an axis carries at least two points (or it is a lone corner)
    xs = [x for x in xs if sum(1 for p in pts if abs(p[0] - x) <= 0.15) >= 2]
    ys = [y for y in ys if sum(1 for p in pts if abs(p[1] - y) <= 0.15) >= 2]
    return xs[:40], ys[:40]


def letters(i: int) -> str:
    """A, B, … Z, AA, AB… (I and O left out, as on drawings)."""
    abc = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, len(abc))
        s = abc[r] + s
    return s


def grid_lines(xs, ys, box, ext, bubble=0.45):
    """[(a, b)] line segments (axes dash-dotted + bubble circles) and
    [(x, y, label)] the bubbles' centres, in plan (m)."""
    x0, y0, x1, y1 = box
    segs, tags = [], []
    lo_y, hi_y = y0 - ext, y1 + ext
    lo_x, hi_x = x0 - ext, x1 + ext

    def dashdot(a, b):
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L else (1, 0)
        k = 0.0
        pat = (0.8, 0.15, 0.1, 0.15)
        j = 0
        while k < L:
            e = min(k + pat[j % 4], L)
            if j % 2 == 0:
                segs.append(((a[0] + u[0] * k, a[1] + u[1] * k),
                             (a[0] + u[0] * e, a[1] + u[1] * e)))
            k = e
            j += 1

    def circle(c):
        prev = None
        for q in range(25):
            ang = 2 * math.pi * q / 24
            p = (c[0] + bubble * math.cos(ang), c[1] + bubble * math.sin(ang))
            if prev:
                segs.append((prev, p))
            prev = p
    for i, x in enumerate(xs):
        dashdot((x, lo_y), (x, hi_y))
        for c in ((x, lo_y - bubble), (x, hi_y + bubble)):
            circle(c)
            tags.append((c[0], c[1], str(i + 1)))
    for i, y in enumerate(ys):
        dashdot((lo_x, y), (hi_x, y))
        for c in ((lo_x - bubble, y), (hi_x + bubble, y)):
            circle(c)
            tags.append((c[0], c[1], letters(i)))
    return segs, tags


def grid_from_cad(segs, texts, circles, min_len=3.0):
    """The CAD's grid: long lines on the grid layers (each kept once),
    labelled by the text in (or next to) the bubble at either end —
    else numbered 1, 2, 3 (upright axes) and lettered A, B, C (level ones),
    left to right and bottom up."""
    lines = []
    for a, b in segs:
        if math.dist(a, b) < min_len:
            continue
        dup = False
        for ln in lines:                        # the same axis drawn twice
            if _seg_close(ln, (a, b)):
                dup = True
                break
        if not dup:
            lines.append((tuple(a), tuple(b)))
    out = []
    for a, b in lines:
        label = ""
        for end in (a, b):
            near = [t for t in texts
                    if math.dist(end, (t[0], t[1])) <= 1.2 and
                    len(t[2].strip()) <= 3]
            if near:
                label = min(near, key=lambda t: math.dist(end, (t[0],
                                                                t[1])))[2]
                break
        out.append({"a": list(a), "b": list(b), "label": label.strip()})
    ups = sorted([g for g in out if _upright(g)],
                 key=lambda g: (g["a"][0] + g["b"][0]) / 2)
    flats = sorted([g for g in out if not _upright(g)],
                   key=lambda g: (g["a"][1] + g["b"][1]) / 2)
    for i, g in enumerate(ups):
        g["label"] = g["label"] or str(i + 1)
    for i, g in enumerate(flats):
        g["label"] = g["label"] or letters(i)
    return ups + flats


def _upright(g):
    return abs(g["b"][1] - g["a"][1]) >= abs(g["b"][0] - g["a"][0])


def _seg_close(p, q, tol=0.05):
    (a, b), (c, d) = p, q
    return (math.dist(a, c) < tol and math.dist(b, d) < tol) or \
        (math.dist(a, d) < tol and math.dist(b, c) < tol)


def cad_grid_lines(lines, bubble=0.45):
    """The CAD's axes as drawn (dash-dotted) with a bubble at each end."""
    segs, tags = [], []
    for g in lines:
        a, b = tuple(g["a"]), tuple(g["b"])
        L = math.dist(a, b)
        if L < 1e-6:
            continue
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        k, j = 0.0, 0
        pat = (0.8, 0.15, 0.1, 0.15)
        while k < L:
            e = min(k + pat[j % 4], L)
            if j % 2 == 0:
                segs.append(((a[0] + u[0] * k, a[1] + u[1] * k),
                             (a[0] + u[0] * e, a[1] + u[1] * e)))
            k = e
            j += 1
        for c in ((a[0] - u[0] * bubble, a[1] - u[1] * bubble),
                  (b[0] + u[0] * bubble, b[1] + u[1] * bubble)):
            prev = None
            for q in range(25):
                ang = 2 * math.pi * q / 24
                p = (c[0] + bubble * math.cos(ang), c[1] + bubble * math.sin(ang))
                if prev:
                    segs.append((prev, p))
                prev = p
            tags.append((c[0], c[1], g["label"]))
    return segs, tags
