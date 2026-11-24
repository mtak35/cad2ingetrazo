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
         ("wall_rail", "Low wall + steel railing over it"),
         ("baluster", "Stone balustrade — turned balusters, newel posts, "
                      "coping"),
         # 3.64.122: more types (the reference sheets)
         ("baluster_vase", "Stone balustrade — fat vase balusters, square "
                           "piers"),
         ("baluster_pier", "Stone balustrade — slim balusters, ball-topped "
                           "piers"),
         ("baluster_panel", "Stone balustrade — panelled piers, pyramid "
                            "caps"),
         ("iron_belly", "Wrought iron — belly (lens) bars"),
         ("iron_wave", "Wrought iron — wavy scroll bars"),
         ("iron_mesh", "Square mesh screen — dark steel"),
         ("iron_geo", "Geometric nested-square panels — dark steel"),
         ("panel_diamond", "Solid panel with diamond inlays"),
         ("alu_bars", "Grey aluminium — flat bars, posts, fascia")]
LABEL = dict(TYPES)

SS = (0.78, 0.79, 0.80, 1.0)          # stainless steel
MS = (0.17, 0.18, 0.20, 1.0)          # mild steel, painted dark
GLASS = (0.66, 0.82, 0.90, 0.35)
TIMBER = (0.55, 0.38, 0.22, 1.0)
MASONRY = (0.88, 0.86, 0.82, 1.0)
STONE = (0.93, 0.91, 0.86, 1.0)       # a cast-stone balustrade
IRON = (0.10, 0.10, 0.11, 1.0)        # black wrought iron
ALU = (0.52, 0.54, 0.57, 1.0)         # grey powder-coated aluminium
PANEL = (0.66, 0.64, 0.60, 1.0)       # a painted panel
INLAY = (0.97, 0.97, 0.95, 1.0)


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


def _run_on(pts, ea, eb):
    """The path run on ``ea`` before its first point and ``eb`` past its
    last (level): a corner's rails meeting full, not notched."""
    pts = list(pts)
    if len(pts) >= 2 and ea > 0:
        p, q = pts[0], pts[1]
        L = math.hypot(q[0] - p[0], q[1] - p[1]) or 1.0
        pts[0] = (p[0] - (q[0] - p[0]) / L * ea,
                  p[1] - (q[1] - p[1]) / L * ea, p[2])
    if len(pts) >= 2 and eb > 0:
        p, q = pts[-2], pts[-1]
        L = math.hypot(q[0] - p[0], q[1] - p[1]) or 1.0
        pts[-1] = (q[0] + (q[0] - p[0]) / L * eb,
                   q[1] + (q[1] - p[1]) / L * eb, q[2])
    return pts


#: a turned baluster's profile (radius, fraction of its height): foot block,
#: neck, bulb, ring, neck, collar — as the white stone ones of a terrace
_BAL = [(0.62, 0.0), (0.62, 0.05), (0.36, 0.07), (0.30, 0.12), (0.52, 0.28),
        (0.56, 0.38), (0.30, 0.52), (0.36, 0.58), (0.30, 0.64),
        (0.40, 0.86), (0.62, 0.90), (0.62, 1.0)]


def _lathe(x, y, z0, h, r, prof, color, n=8):
    """A turned solid at (x, y): ``prof`` = [(radius factor, height
    fraction)], ``r`` the full radius, ``n`` sides."""
    rings = []
    for f, g in prof:
        rr = r * f
        rings.append([(x + rr * math.cos(2 * math.pi * (k + 0.5) / n),
                       y + rr * math.sin(2 * math.pi * (k + 0.5) / n),
                       z0 + h * g) for k in range(n)])
    out = []
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            k2 = (k + 1) % n
            out.append({"loop": [a[k], a[k2], b[k2], b[k]], "holes": [],
                        "color": color})
    out.append({"loop": rings[-1][::1], "holes": [], "color": color})
    out.append({"loop": rings[0][::-1], "holes": [], "color": color})
    return out


def _baluster_rail(pts, H, t, gap, run_on):
    """The stone balustrade along ``pts``: a plinth rail, turned balusters
    every ``gap`` (the type's 0.20 m), a heavy coping on top, a newel post
    (with its cap and finial) at the corners, the ends and every 2.4 m."""
    out = []
    segs = list(zip(pts, pts[1:]))
    rail_h = 0.12
    cop_h = 0.09
    bal_h = max(H - rail_h - cop_h, 0.2)
    bw = 0.075                     # a baluster's radius
    for p, q in segs:
        out += _panel(p, q, 0.0, rail_h, 0.17, STONE)
        out += _panel(p, q, H - cop_h, H, 0.22, STONE)
        out += _panel(p, q, H - cop_h - 0.03, H - cop_h, 0.18, STONE)
        for s in _stations(p, q, max(gap or 0.0, 0.17) if gap else 0.19)[1:-1]:
            out += _lathe(s[0], s[1], s[2] + rail_h, bal_h, bw, _BAL, STONE)
    # newel posts
    posts = []
    for p, q in segs:
        for s in _stations(p, q, 2.4):
            if not posts or math.hypot(s[0] - posts[-1][0],
                                       s[1] - posts[-1][1]) > 0.05:
                posts.append(s)
    for s in posts:
        a = 0.13
        out += _box_xy([(s[0] - a, s[1] - a), (s[0] + a, s[1] - a),
                        (s[0] + a, s[1] + a), (s[0] - a, s[1] + a)],
                       s[2], s[2] + H + 0.05, STONE)
        c = 0.18
        out += _box_xy([(s[0] - c, s[1] - c), (s[0] + c, s[1] - c),
                        (s[0] + c, s[1] + c), (s[0] - c, s[1] + c)],
                       s[2] + H + 0.05, s[2] + H + 0.12, STONE)
        out += _lathe(s[0], s[1], s[2] + H + 0.12, 0.34, 0.14,
                      [(0.5, 0.0), (0.9, 0.15), (1.0, 0.4), (0.8, 0.7),
                       (0.4, 0.92), (0.2, 1.0)], STONE)
    return out


# ---- 3.64.122: more railing types --------------------------------------------
_VASE = [(0.70, 0.0), (0.70, 0.07), (0.44, 0.10), (0.40, 0.20),
         (0.78, 0.38), (0.98, 0.54), (0.78, 0.70), (0.42, 0.86),
         (0.56, 0.90), (0.56, 1.0)]
_BALL = [(0.35, 0.0), (0.80, 0.14), (1.0, 0.5), (0.80, 0.86), (0.35, 1.0)]
_PYR = [(1.0, 0.0), (0.04, 1.0)]


def _plate(p, q, pts_sz, a0, a1, color):
    """A flat shape standing on p → q: ``pts_sz`` = [(s metres along, z
    over the walking line)] convex, a0..a1 across the path."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return []
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    n = len(pts_sz)

    def P(s, z, a):
        f = s / L
        return (p[0] + dx * f + nx * a, p[1] + dy * f + ny * a,
                p[2] + (q[2] - p[2]) * f + z)
    front = [P(s, z, a1) for s, z in pts_sz]
    back = [P(s, z, a0) for s, z in reversed(pts_sz)]
    out = [{"loop": front, "holes": [], "color": color},
           {"loop": back, "holes": [], "color": color}]
    for i in range(n):
        j = (i + 1) % n
        out.append({"loop": [P(*pts_sz[i], a0), P(*pts_sz[j], a0),
                             P(*pts_sz[j], a1), P(*pts_sz[i], a1)],
                    "holes": [], "color": color})
    return out


def _pier_posts(pts, step):
    posts = []
    for p, q in zip(pts, pts[1:]):
        for s in _stations(p, q, step):
            if not posts or math.hypot(s[0] - posts[-1][0],
                                       s[1] - posts[-1][1]) > 0.05:
                posts.append(s)
    return posts


def _stone_rail(pts, H, gap, prof, rr, step_b, pier_w, pier_cap, pier_step,
                rail_h=0.14, cop_h=0.10, panels=False):
    out = []
    segs = list(zip(pts, pts[1:]))
    bal_h = max(H - rail_h - cop_h, 0.2)
    for p, q in segs:
        out += _panel(p, q, 0.0, rail_h, 0.22, STONE)
        out += _panel(p, q, H - cop_h, H, 0.26, STONE)
        for s in _stations(p, q, max(gap or 0.0, 0.05) if gap else step_b
                           )[1:-1]:
            out += _lathe(s[0], s[1], s[2] + rail_h, bal_h, rr, prof, STONE,
                          n=10)
    for s in _pier_posts(pts, pier_step):
        a = pier_w / 2
        out += _box_xy([(s[0] - a, s[1] - a), (s[0] + a, s[1] - a),
                        (s[0] + a, s[1] + a), (s[0] - a, s[1] + a)],
                       s[2], s[2] + H + 0.04, STONE)
        if panels:                      # a raised panel band, a pyramid cap
            b = a + 0.015
            out += _box_xy([(s[0] - b, s[1] - b), (s[0] + b, s[1] - b),
                            (s[0] + b, s[1] + b), (s[0] - b, s[1] + b)],
                           s[2] + H * 0.30, s[2] + H * 0.80, STONE)
        c = a + 0.05
        out += _box_xy([(s[0] - c, s[1] - c), (s[0] + c, s[1] - c),
                        (s[0] + c, s[1] + c), (s[0] - c, s[1] + c)],
                       s[2] + H + 0.04, s[2] + H + 0.10, STONE)
        if pier_cap == "ball":
            out += _lathe(s[0], s[1], s[2] + H + 0.10, 0.28, 0.14, _BALL,
                          STONE, n=12)
        elif pier_cap == "pyramid":
            out += _lathe(s[0], s[1], s[2] + H + 0.10, 0.26, c * 1.42, _PYR,
                          STONE, n=4)
    return out


def _iron_posts(pts, H, color, step=1.5, w=0.05):
    out = []
    for s in _pier_posts(pts, step):
        out += _bar(s, _up(s, H - 0.02), w, w, color)
    return out


def _iron_frame(pts, H, color, bottom=0.06):
    out = []
    for p, q in zip(pts, pts[1:]):
        out += _bar(_up(p, H - 0.025), _up(q, H - 0.025), 0.05, 0.05, color)
        out += _bar(_up(p, bottom), _up(q, bottom), 0.04, 0.04, color)
        out += _bar(_up(p, bottom + 0.14), _up(q, bottom + 0.14), 0.03,
                    0.03, color)
    return out


def _curved_bars(pts, H, gap, bulge, wave, pair):
    """Bars bulging along the path (belly pairs) or waving (scrolls)."""
    out = []
    z0, z1 = 0.10, H - 0.07
    nseg = 4
    for p, q in zip(pts, pts[1:]):
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        if L < 1e-6:
            continue
        ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
        step = max(gap or 0.0, 0.05) if gap else (0.16 if pair else 0.11)
        sts = _stations(p, q, step)[1:-1]
        for k, s in enumerate(sts):
            bars = ((-0.5, 1.0), (0.5, -1.0)) if pair else ((0.0, 1.0),)
            for off, sg in bars:
                pts3 = []
                for m in range(nseg + 1):
                    f = m / nseg
                    z = z0 + (z1 - z0) * f
                    if pair:
                        d = off * 0.05 + sg * bulge * math.sin(math.pi * f)
                    else:
                        d = sg * bulge * math.sin(2 * math.pi * f * wave)
                    pts3.append((s[0] + ux * d, s[1] + uy * d, s[2] + z))
                for a, b in zip(pts3, pts3[1:]):
                    out += _bar(a, b, 0.014, 0.014, IRON)
    return out


def _custom_rail(pts, H, kind, gap, t):
    segs = list(zip(pts, pts[1:]))
    out = []
    if kind == "baluster_vase":
        return _stone_rail(pts, H, gap, _VASE, 0.085, 0.30, 0.22, None, 3.0)
    if kind == "baluster_pier":
        return _stone_rail(pts, H, gap, _BAL, 0.06, 0.17, 0.30, "ball", 2.5,
                           rail_h=0.12, cop_h=0.09)
    if kind == "baluster_panel":
        return _stone_rail(pts, H, gap, _BAL, 0.06, 0.17, 0.30, "pyramid",
                           2.2, rail_h=0.12, cop_h=0.09, panels=True)
    if kind == "iron_belly":
        out += _iron_posts(pts, H, IRON) + _iron_frame(pts, H, IRON)
        return out + _curved_bars(pts, H, gap, 0.035, 1, True)
    if kind == "iron_wave":
        out += _iron_posts(pts, H, IRON) + _iron_frame(pts, H, IRON)
        return out + _curved_bars(pts, H, gap, 0.05, 1, False)
    if kind == "iron_mesh":
        out += _iron_posts(pts, H, IRON, 1.5, 0.06)
        for p, q in segs:
            out += _bar(_up(p, H - 0.03), _up(q, H - 0.03), 0.06, 0.06, IRON)
            out += _bar(_up(p, 0.03), _up(q, 0.03), 0.05, 0.06, IRON)
            pit = max(gap or 0.0, 0.04) if gap else 0.075
            for s in _stations(p, q, pit)[1:-1]:
                out += _bar(_up(s, 0.05), _up(s, H - 0.05), 0.012, 0.012,
                            IRON)
            z = 0.05 + pit
            while z < H - 0.06:
                out += _bar(_up(p, z), _up(q, z), 0.012, 0.012, IRON)
                z += pit
        return out
    if kind == "iron_geo":
        out += _iron_posts(pts, H, IRON, 0.9, 0.05)
        for p, q in segs:
            out += _bar(_up(p, H - 0.025), _up(q, H - 0.025), 0.05, 0.05,
                        IRON)
            out += _bar(_up(p, 0.05), _up(q, 0.05), 0.04, 0.04, IRON)
            L = math.hypot(q[0] - p[0], q[1] - p[1])
            n = max(1, int(round(L / 0.9)))
            w = L / n
            for k in range(n):
                s0, s1 = k * w, (k + 1) * w
                for r in range(3):
                    d = 0.10 + 0.075 * r
                    a, b = s0 + d, s1 - d
                    z0, z1 = 0.05 + d, H - 0.05 - d
                    if b - a < 0.05 or z1 - z0 < 0.05:
                        continue
                    A, B = _lerp(p, q, a / L), _lerp(p, q, b / L)
                    out += _bar(_up(A, z0), _up(B, z0), 0.014, 0.014, IRON)
                    out += _bar(_up(A, z1), _up(B, z1), 0.014, 0.014, IRON)
                    out += _bar(_up(A, z0), _up(A, z1), 0.014, 0.014, IRON)
                    out += _bar(_up(B, z0), _up(B, z1), 0.014, 0.014, IRON)
        return out
    if kind == "panel_diamond":
        for p, q in segs:
            L = math.hypot(q[0] - p[0], q[1] - p[1])
            out += _panel(p, q, 0.0, H - 0.07, max(t, 0.10), PANEL)
            out += _panel(p, q, H - 0.07, H, max(t, 0.10) + 0.06, ALU)
            n = max(1, int(round(L / 0.9)))
            zc = (H - 0.07) / 2
            h_ = min(0.12, (H - 0.07) * 0.3)
            for k in range(n):
                sc = (k + 0.5) * L / n
                d = [(sc - h_, zc), (sc, zc - h_), (sc + h_, zc),
                     (sc, zc + h_)]
                ta = max(t, 0.10) / 2
                out += _plate(p, q, d, -ta - 0.012, -ta, INLAY)
                out += _plate(p, q, d, ta, ta + 0.012, INLAY)
        return out
    if kind == "alu_bars":
        out += _iron_posts(pts, H, ALU, 1.2, 0.06)
        for p, q in segs:
            out += _panel(p, q, 0.0, 0.12, 0.08, ALU)
            out += _bar(_up(p, H - 0.03), _up(q, H - 0.03), 0.07, 0.05, ALU)
            for s in _stations(p, q, max(gap or 0.0, 0.05) if gap else 0.10
                               )[1:-1]:
                out += _bar(_up(s, 0.12), _up(s, H - 0.05), 0.02, 0.02, ALU)
        return out
    return []


_CUSTOM = ("baluster_vase", "baluster_pier", "baluster_panel", "iron_belly",
           "iron_wave", "iron_mesh", "iron_geo", "panel_diamond", "alu_bars")


def faces(path, height=1.0, kind="ss_bars", t=0.115, gap=0.0,
          floor=None, no_post=(False, False), run_on=(0.0, 0.0)) -> list:
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
    if kind in _CUSTOM:                        # 3.64.122
        return _custom_rail(pts, H, kind, gap, t)
    if kind == "solid":                        # a masonry upstand + coping
        for p, q in segs:
            out += _panel(p, q, 0.0, H - 0.05, t, MASONRY)
            out += _panel(p, q, H - 0.05, H, t + 0.05, MASONRY)
        return out
    if kind == "baluster":
        return _baluster_rail(pts, H, t, gap, run_on)
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
    if posts and no_post[1]:                  # a corner's shared post:
        posts = posts[:-1]                    # the other railing's
    if posts and no_post[0]:
        posts = posts[1:]
    if kind != "glass":
        for s in posts:
            b_ = s
            if floor is not None:            # a stair: each post fixed down
                try:                         # on the tread under it
                    zf = floor(s[0], s[1])
                    if zf is not None and zf < s[2] - 0.005:
                        b_ = (s[0], s[1], zf)
                except Exception:  # noqa: BLE001
                    pass
            out += _bar(b_, _up(s, H - 0.02), post_w, post_w, rail_c)
    # the handrail on top, the run of the whole path
    hw = {"wood": 0.07}.get(kind, 0.05)
    rp = _run_on(pts, run_on[0] and hw / 2, run_on[1] and hw / 2)
    for p, q in zip(rp, rp[1:]):
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
