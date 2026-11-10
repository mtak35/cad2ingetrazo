# SPDX-License-Identifier: GPL-3.0-or-later
"""Travelators (inclined moving walks) and escalators from the plan.

A supermarket / mall plan draws them on an ESCALATOR / TRAVELATOR layer:
the outline of the unit (a long box 0.8–2.2 m wide), the break line where
it passes the cut plane (the part beyond it is above), arrows of travel
and a note — «TRAVELATOR», «12 DEG», «14'-8" HEIGHT». Each becomes a
record in ``doc["escalators"]`` and a 3D unit: the flat landing at the
foot, the inclined belt (or steps), the balustrades with their handrails
and the truss under it, up to the landing at the top.
"""
from __future__ import annotations

import math
import re

KIND_RX = re.compile(r"TRAV[AEO]L+ATOR|TRAVOLATOR|MOVING\s?WALK|"
                     r"PEOPLE\s?MOVER", re.I)
ESC_RX = re.compile(r"ESCALAT", re.I)
DEG_RX = re.compile(r"(\d+(?:\.\d+)?)\s*°?\s*(?:DEG|DIG|DEGREE|°)", re.I)
HEIGHT_RX = re.compile(r"(\d+)\s*'\s*-?\s*(\d+(?:\.\d+)?)?\s*\"?\s*(?:HEIGHT|"
                       r"RISE|HT)", re.I)

COLOR_BELT = (0.22, 0.23, 0.25)
COLOR_STEEL = (0.72, 0.74, 0.77)
COLOR_GLASS = (0.70, 0.85, 0.90)
COLOR_RAIL = (0.10, 0.10, 0.10)


def _feet(m) -> float:
    ft = float(m.group(1))
    inch = float(m.group(2) or 0.0)
    return (ft * 12.0 + inch) * 0.0254


def detect(pl, lid, is_esc, floor_h=3.66) -> list:
    """The travelators / escalators of a placed plan: segments on the layers
    ``is_esc(layer)`` says are escalators'. [record]."""
    from shapely.geometry import LineString, Point
    from shapely.ops import polygonize, unary_union
    lay = pl["layers"]
    segs = [s for s in pl["segs"] if is_esc(lay[s[4]])]
    if len(segs) < 4:
        return []
    lines = []
    for s in segs:
        a, b = (s[0], s[1]), (s[2], s[3])
        d = math.dist(a, b)
        if d < 1e-4:
            continue
        ex, ey = (b[0] - a[0]) / d * 0.003, (b[1] - a[1]) / d * 0.003
        lines.append(LineString([(a[0] - ex, a[1] - ey),
                                 (b[0] + ex, b[1] + ey)]))
    faces = [f for f in polygonize(unary_union(lines)) if f.area > 1.0]
    # the outline's parts either side of the break line (drawn a little
    # apart): one unit
    whole = unary_union([f.buffer(0.25, join_style=2) for f in faces]) \
        .buffer(-0.25, join_style=2) if faces else None
    if whole is None:
        return []
    out = []
    for g in getattr(whole, "geoms", [whole]):
        if g.geom_type != "Polygon":
            continue
        m = g.minimum_rotated_rectangle
        cs = list(m.exterior.coords)[:-1]
        e1, e2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        L, W = max(e1, e2), min(e1, e2)
        if not (0.7 <= W <= 2.6 and L >= 4.0 and L / W >= 2.5):
            continue
        if g.area < 0.6 * m.area:
            continue
        # its axis: the long sides' middle line
        if e1 >= e2:
            a = ((cs[1][0] + cs[2][0]) / 2, (cs[1][1] + cs[2][1]) / 2)
            b = ((cs[3][0] + cs[0][0]) / 2, (cs[3][1] + cs[0][1]) / 2)
        else:
            a = ((cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2)
            b = ((cs[2][0] + cs[3][0]) / 2, (cs[2][1] + cs[3][1]) / 2)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        # its note: kind, angle, height
        kind, deg, rise = "travelator", None, None
        for t in pl.get("texts") or ():
            p = Point(float(t["x"]), float(t["y"]))
            if g.buffer(1.5).contains(p):
                s_ = str(t.get("text", ""))
                if ESC_RX.search(s_):
                    kind = "escalator"
                if KIND_RX.search(s_):
                    kind = "travelator"
                md = DEG_RX.search(s_)
                if md:
                    deg = float(md.group(1))
                mh = HEIGHT_RX.search(s_)
                if mh:
                    rise = _feet(mh)
        # the top: the end the break line (a line across it, short of the
        # outline's ends) lies nearer — the part beyond it is above the cut
        brk = []
        for s in segs:
            p0, p1 = (s[0], s[1]), (s[2], s[3])
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            if not g.buffer(0.3).contains(Point(mid)):
                continue
            d = math.dist(p0, p1)
            if d < 0.3:
                continue
            across = abs(((p1[0] - p0[0]) * ux + (p1[1] - p0[1]) * uy) / d)
            if across > 0.35:
                continue
            t = (mid[0] - a[0]) * ux + (mid[1] - a[1]) * uy
            if 0.12 * L < t < 0.88 * L and d > 0.6 * W:
                brk.append(t)
        if brk:
            tb = sorted(brk)[len(brk) // 2]
            if tb < L / 2:               # the break nearer a: a is the top
                a, b = b, a
                ux, uy = -ux, -uy
        if deg is None:
            deg = 12.0 if kind == "travelator" else 30.0
        deg = min(max(deg, 5.0), 35.0)
        if rise is None:
            rise = floor_h
        out.append({"level": lid, "kind": kind,
                    "a": [round(a[0], 4), round(a[1], 4)],
                    "b": [round(b[0], 4), round(b[1], 4)],
                    "w": round(W, 3), "deg": round(deg, 2),
                    "rise": round(rise, 3)})
    return out


def _box(p0, u, n, s0, s1, w0, w1, z0f, z1f, color):
    """A block along the unit: from s0 to s1 along ``u``, from w0 to w1
    across (``n``), its bottom and top heights given as functions of s."""
    def P(s, w, z):
        return (p0[0] + u[0] * s + n[0] * w, p0[1] + u[1] * s + n[1] * w, z)
    b0, b1, t0, t1 = z0f(s0), z0f(s1), z1f(s0), z1f(s1)
    q = [P(s0, w0, b0), P(s1, w0, b1), P(s1, w1, b1), P(s0, w1, b0),
         P(s0, w0, t0), P(s1, w0, t1), P(s1, w1, t1), P(s0, w1, t0)]
    F = [[q[0], q[3], q[2], q[1]], [q[4], q[5], q[6], q[7]],
         [q[0], q[1], q[5], q[4]], [q[1], q[2], q[6], q[5]],
         [q[2], q[3], q[7], q[6]], [q[3], q[0], q[4], q[7]]]
    return [{"loop": f, "color": color} for f in F]


def faces(rec, z0) -> list:
    """The 3D faces of one unit standing on a floor at ``z0``."""
    a, b = rec["a"], rec["b"]
    L = math.dist(a, b)
    if L < 1.0:
        return []
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])
    W = float(rec.get("w", 1.4))
    rise = float(rec.get("rise", 3.66))
    tan = math.tan(math.radians(float(rec.get("deg", 12.0))))
    run = rise / max(tan, 1e-3)
    flat = max((L - run) / 2.0, 0.6)
    if run > L - 1.2:                    # the outline is the measure
        run = L - 1.2
        flat = 0.6
    s1 = flat
    s2 = flat + run

    def top(s):                          # the walking surface's height
        if s <= s1:
            return z0 + 0.05
        if s >= s2:
            return z0 + rise
        return z0 + 0.05 + (s - s1) / run * (rise - 0.05)

    def under(s):                        # the truss's bottom
        return max(z0, top(s) - 0.9) if s > s1 else z0

    hw = W / 2
    out = []
    # truss / casing under the belt
    for k in range(12):
        sa = s1 + run * k / 12 if k else 0.0
        sb = s1 + run * (k + 1) / 12 if k < 11 else L
        out += _box(a, u, n, sa, sb, -hw, hw,
                    lambda s: under(s), lambda s: top(s) - 0.06,
                    COLOR_STEEL)
    # the belt: its pallets / steps
    stepped = rec.get("kind") == "escalator"
    if stepped:
        ns = max(int(run / 0.4), 4)
        out += _box(a, u, n, 0.0, s1, -hw + 0.12, hw - 0.12,
                    lambda s: z0, lambda s: z0 + 0.05, COLOR_BELT)
        for k in range(ns):
            sa = s1 + run * k / ns
            sb = s1 + run * (k + 1) / ns
            zt = z0 + 0.05 + (k + 1) / ns * (rise - 0.05)
            out += _box(a, u, n, sa, sb, -hw + 0.12, hw - 0.12,
                        lambda s, zt=zt: zt - 0.2, lambda s, zt=zt: zt,
                        COLOR_BELT)
        out += _box(a, u, n, s2, L, -hw + 0.12, hw - 0.12,
                    lambda s: z0 + rise - 0.05, lambda s: z0 + rise,
                    COLOR_BELT)
    else:
        for sa, sb in ((0.0, s1), (s1, s2), (s2, L)):
            out += _box(a, u, n, sa, sb, -hw + 0.12, hw - 0.12,
                        lambda s: top(s) - 0.06, lambda s: top(s),
                        COLOR_BELT)
    # balustrades: the skirt, the glass, the handrail — both sides
    for side in (-1, 1):
        w0, w1 = (hw - 0.12, hw) if side > 0 else (-hw, -hw + 0.12)
        for sa, sb in ((0.25, s1), (s1, s2), (s2, L - 0.25)):
            if sb - sa < 0.05:
                continue
            out += _box(a, u, n, sa, sb, w0, w1,
                        lambda s: top(s) - 0.06, lambda s: top(s) + 0.12,
                        COLOR_STEEL)
            gm = (w0 + w1) / 2
            out += _box(a, u, n, sa, sb, gm - 0.006, gm + 0.006,
                        lambda s: top(s) + 0.12, lambda s: top(s) + 0.92,
                        COLOR_GLASS)
            out += _box(a, u, n, sa, sb, gm - 0.04, gm + 0.04,
                        lambda s: top(s) + 0.92, lambda s: top(s) + 1.0,
                        COLOR_RAIL)
    return out
