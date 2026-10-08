# SPDX-License-Identifier: GPL-3.0-or-later
"""Railings — along any path, level (a parapet, a balcony edge) or
sloped (a stair flight): posts, a handrail, and the infill of its type.

``faces(path, height, kind)``: ``path`` = [(x, y, z)…], z = the walking
surface under the railing at that point (the nosing line on a stair);
the railing stands ``height`` over it. Faces as the engine makes them
({"loop", "holes", "color"}).
"""
from __future__ import annotations

import math

#: kind → label (the panel's list, in this order)
TYPES = [("solid", "Solid parapet (masonry, plastered)"),
         ("ss_bars", "Stainless steel — vertical balusters"),
         ("ms_grill", "MS grill — painted bars, top & bottom rail"),
         ("glass", "Frameless glass + steel handrail"),
         ("glass_post", "Glass panels between steel posts"),
         ("pipe", "Steel pipe rails (horizontal)"),
         ("wood", "Timber handrail on timber balusters"),
         ("wall_rail", "Low wall + steel railing over it")]
LABEL = dict(TYPES)

SS = (0.78, 0.79, 0.80, 1.0)          # stainless steel
MS = (0.17, 0.18, 0.20, 1.0)          # mild steel, painted dark
GLASS = (0.66, 0.82, 0.90, 0.35)
TIMBER = (0.55, 0.38, 0.22, 1.0)
MASONRY = (0.88, 0.86, 0.82, 1.0)


def _bar(p, q, w, h, color):
    """A bar from ``p`` to ``q`` (3D, its axis), section ``w`` wide in plan
    and ``h`` tall — its sides vertical, a slope kept (a stair's rail)."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:                      # vertical: a post, square section
        x, y = p[0], p[1]
        za, zb = sorted((p[2], q[2]))
        a = w / 2
        return _box_xy([(x - a, y - a), (x + a, y - a), (x + a, y + a),
                        (x - a, y + a)], za, zb, color)
    nx, ny = -dy / L * w / 2, dx / L * w / 2
    c = [(p[0] - nx, p[1] - ny, p[2] - h / 2), (q[0] - nx, q[1] - ny, q[2] - h / 2),
         (q[0] + nx, q[1] + ny, q[2] - h / 2), (p[0] + nx, p[1] + ny, p[2] - h / 2),
         (p[0] - nx, p[1] - ny, p[2] + h / 2), (q[0] - nx, q[1] - ny, q[2] + h / 2),
         (q[0] + nx, q[1] + ny, q[2] + h / 2), (p[0] + nx, p[1] + ny, p[2] + h / 2)]
    return _hexa(c, color)


def _hexa(c, color):
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    return [{"loop": [c[i] for i in q], "holes": [], "color": color}
            for q in quads]


def _box_xy(pts, za, zb, color):
    c = [(x, y, za) for x, y in pts] + [(x, y, zb) for x, y in pts]
    return _hexa(c, color)


def _panel(p, q, z_lo, z_hi, t, color):
    """A slab standing on the line p → q: its foot ``z_lo`` and head
    ``z_hi`` over the walking line (sloped with it), ``t`` thick."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    if L < 1e-6 or z_hi - z_lo < 0.01:
        return []
    nx, ny = -dy / L * t / 2, dx / L * t / 2
    c = [(p[0] - nx, p[1] - ny, p[2] + z_lo), (q[0] - nx, q[1] - ny, q[2] + z_lo),
         (q[0] + nx, q[1] + ny, q[2] + z_lo), (p[0] + nx, p[1] + ny, p[2] + z_lo),
         (p[0] - nx, p[1] - ny, p[2] + z_hi), (q[0] - nx, q[1] - ny, q[2] + z_hi),
         (q[0] + nx, q[1] + ny, q[2] + z_hi), (p[0] + nx, p[1] + ny, p[2] + z_hi)]
    return _hexa(c, color)


def _lerp(p, q, f):
    return (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f,
            p[2] + (q[2] - p[2]) * f)


def _up(p, dz):
    return (p[0], p[1], p[2] + dz)


def _stations(p, q, step):
    """Points along p → q at most ``step`` apart (both ends kept)."""
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    n = max(1, int(math.ceil(L / step - 1e-9)))
    return [_lerp(p, q, k / n) for k in range(n + 1)]


def faces(path, height=1.0, kind="ss_bars", t=0.115, gap=0.0) -> list:
    """The railing along ``path`` ([(x, y, z)…]) — see the module doc.
    ``gap``: the balusters' (or the glass panels' / pipe posts') spacing,
    0 = the type's own."""
    gap = float(gap or 0.0)
    if gap and gap < 0.05:
        gap = 0.05
    pts = [tuple(map(float, q)) for q in path]
    pts = [q for i, q in enumerate(pts)
           if i == 0 or math.hypot(q[0] - pts[i - 1][0],
                                   q[1] - pts[i - 1][1]) > 1e-4]
    if len(pts) < 2:
        return []
    H = max(float(height), 0.3)
    out = []
    segs = list(zip(pts, pts[1:]))
    if kind == "solid":                        # a masonry upstand + coping
        for p, q in segs:
            out += _panel(p, q, 0.0, H - 0.05, t, MASONRY)
            out += _panel(p, q, H - 0.05, H, t + 0.05, MASONRY)
        return out
    if kind == "wall_rail":                     # 2'-0" wall, steel above
        wall = min(0.6, H * 0.6)
        for p, q in segs:
            out += _panel(p, q, 0.0, wall, t, MASONRY)
            for s in _stations(p, q, gap or 0.12)[1:-1]:
                out += _bar(_up(s, wall), _up(s, H - 0.03), 0.016, 0.016, SS)
            out += _bar(_up(p, H - 0.025), _up(q, H - 0.025), 0.05, 0.05, SS)
        return out
    # posts: at the path's corners and ends, and at most this far apart
    post_gap = {"glass": 0.0, "glass_post": 1.2, "pipe": 1.2,
                "wood": 1.5, "ms_grill": 1.5, "ss_bars": 1.5}.get(kind, 1.5)
    if gap and kind in ("glass_post", "pipe"):
        post_gap = max(gap, 0.3)
    post_w = {"wood": 0.08, "glass_post": 0.05, "pipe": 0.05}.get(kind, 0.045)
    rail_c = {"wood": TIMBER, "ms_grill": MS}.get(kind, SS)
    posts = []
    for p, q in segs:
        st = _stations(p, q, post_gap) if post_gap else [p, q]
        for s in st:
            if not posts or math.hypot(s[0] - posts[-1][0],
                                       s[1] - posts[-1][1]) > 0.05:
                posts.append(s)
    if kind != "glass":
        for s in posts:
            out += _bar(s, _up(s, H - 0.02), post_w, post_w, rail_c)
    # the handrail on top, the run of the whole path
    hw = {"wood": 0.07}.get(kind, 0.05)
    for p, q in segs:
        out += _bar(_up(p, H - 0.025), _up(q, H - 0.025), hw, 0.05, rail_c)
    for p, q in segs:
        if kind == "ss_bars":
            for s in _stations(p, q, gap or 0.11)[1:-1]:
                out += _bar(_up(s, 0.05), _up(s, H - 0.05), 0.016, 0.016, SS)
            out += _bar(_up(p, 0.06), _up(q, 0.06), 0.03, 0.02, SS)
        elif kind == "ms_grill":
            for s in _stations(p, q, gap or 0.12)[1:-1]:
                out += _bar(_up(s, 0.08), _up(s, H - 0.05), 0.016, 0.016, MS)
            for z in (0.08, H - 0.12):
                out += _bar(_up(p, z), _up(q, z), 0.04, 0.03, MS)
        elif kind == "glass":                  # in a floor channel
            out += _panel(p, q, 0.0, 0.06, 0.06, SS)
            out += _panel(p, q, 0.06, H - 0.05, 0.015, GLASS)
        elif kind == "glass_post":
            for a, b in zip(_stations(p, q, post_gap),
                            _stations(p, q, post_gap)[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < 0.1:
                    continue
                f0, f1 = 0.04 / L, 1 - 0.04 / L
                out += _panel(_lerp(a, b, f0), _lerp(a, b, f1), 0.1,
                              H - 0.1, 0.012, GLASS)
        elif kind == "pipe":
            for z in (0.25, 0.5, 0.75):
                if z < H - 0.1:
                    out += _bar(_up(p, z * H / 1.0), _up(q, z * H / 1.0),
                                0.035, 0.035, SS)
        elif kind == "wood":
            for s in _stations(p, q, gap or 0.14)[1:-1]:
                out += _bar(_up(s, 0.06), _up(s, H - 0.05), 0.035, 0.035,
                            TIMBER)
            out += _bar(_up(p, 0.07), _up(q, 0.07), 0.06, 0.04, TIMBER)
    return out
