# SPDX-License-Identifier: GPL-3.0-or-later
"""Architectural columns drawn as their style shows them — not a plain box
like a structural RCC column:

* ``round_smooth``  — a plinth, a moulded base, a plain round shaft, a
  capital (echinus and abacus);
* ``round_fluted``  — the same with a fluted shaft;
* ``corinthian``    — a fluted shaft under a tall bell capital of leaves
  (in rings) and a moulded abacus;
* ``square_smooth`` — a square pier: plinth, shaft, a capping band.

``faces(c, outline, z0, z1, style)`` → [(faces, colour)] in the world.

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

import math

STYLES = (("doric", "Doric (fluted, no base, cushion capital)"),
          ("ionic", "Ionic (scroll volutes)"),
          ("corinthian", "Corinthian (acanthus leaves)"),
          ("composite", "Composite (volutes over leaves)"),
          ("tuscan", "Tuscan (plain shaft, simple capital)"),
          ("round_smooth", "Round smooth (base and capital)"),
          ("round_fluted", "Round fluted"),
          ("square_smooth", "Square smooth (plinth and cap)"))
ORDERS = ("doric", "ionic", "corinthian", "composite", "tuscan")
WHITE = (0.95, 0.94, 0.91)
SHADE = (0.88, 0.87, 0.84)


def default_style(c) -> str:
    return "round_smooth" if c.get("shape") == "round" else "square_smooth"


def _ccw(pts):
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(pts, pts[1:] + pts[:1]))
    return list(pts) if a >= 0 else list(reversed(pts))


def _solid(pts, z0, z1):
    from .engine import walls as W
    return W.solid({"outer": _ccw(pts), "holes": []}, z0, z1)


def _circle(cx, cy, r, n=28):
    return [(cx + r * math.cos(2 * math.pi * k / n),
             cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _fluted(cx, cy, r, flutes=20, depth=None, per=4):
    depth = depth if depth is not None else min(0.02, r * 0.08)
    n = flutes * per
    return [(cx + (r - depth * (0.5 + 0.5 * math.cos(
        flutes * 2 * math.pi * k / n))) * math.cos(2 * math.pi * k / n),
        cy + (r - depth * (0.5 + 0.5 * math.cos(
            flutes * 2 * math.pi * k / n))) * math.sin(2 * math.pi * k / n))
        for k in range(n)]


def _star(cx, cy, r_out, r_in, pts=8, rot=0.0):
    out = []
    for k in range(2 * pts):
        r = r_out if k % 2 == 0 else r_in
        t = rot + math.pi * k / pts
        out.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return out


def _rect(cx, cy, w, d, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + ca * x - sa * y, cy + sa * x + ca * y)
            for x, y in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2),
                         (-w / 2, d / 2))]


def _prism(pts, o, u, v, n, L):
    """Faces of the 2D outline ``pts`` (in the plane o + a·u + b·v)
    pushed ``L`` along ``n`` — a solid lying any way (a volute's roll)."""
    def P(a, b, t):
        return (o[0] + u[0] * a + v[0] * b + n[0] * t,
                o[1] + u[1] * a + v[1] * b + n[1] * t,
                o[2] + u[2] * a + v[2] * b + n[2] * t)
    pts = _ccw(list(pts))
    out = [[P(a, b, L) for a, b in pts],
           [P(a, b, 0.0) for a, b in reversed(pts)]]
    for (a0, b0), (a1, b1) in zip(pts, pts[1:] + pts[:1]):
        out.append([P(a0, b0, 0.0), P(a1, b1, 0.0), P(a1, b1, L),
                    P(a0, b0, L)])
    return out


def _spiral_disc(r, turns=2.2, n=40, w=None):
    """A volute's face: the band of a spiral of Archimedes from ``r`` in to
    the eye, as one outline (outer edge out, inner edge back)."""
    w = w if w is not None else r * 0.22
    outer, inner = [], []
    for k in range(n + 1):
        f = k / n
        th = 2 * math.pi * turns * f
        rr = r * (1.0 - 0.82 * f)
        ww = w * (1.0 - 0.6 * f)
        outer.append((rr * math.cos(th), rr * math.sin(th)))
        inner.append(((rr - ww) * math.cos(th), (rr - ww) * math.sin(th)))
    return outer + list(reversed(inner))


def _volutes(cx, cy, ang, zc, D, r, depth, diagonal=False):
    """The two (four, ``diagonal``) scrolls of an Ionic / Composite
    capital: a rolled cushion each side, its spiral standing out on the
    front and the back."""
    out = []
    ca, sa = math.cos(ang), math.sin(ang)
    dirs = [(ca, sa), (-ca, -sa)]
    if diagonal:
        q = math.pi / 4
        dirs = [(math.cos(ang + q + k * math.pi / 2),
                 math.sin(ang + q + k * math.pi / 2)) for k in range(4)]
    for dx, dy in dirs:
        # the roll: a cylinder lying across (its axis ⟂ the side)
        ax = (-dy, dx, 0.0)                  # along the face
        off = D * (0.62 if not diagonal else 0.66)
        ox, oy = cx + dx * off, cy + dy * off
        circ = [(r * math.cos(2 * math.pi * k / 20),
                 r * math.sin(2 * math.pi * k / 20)) for k in range(20)]
        o = (ox - ax[0] * depth / 2, oy - ax[1] * depth / 2, zc)
        out += _prism(circ, o, (dx, dy, 0.0), (0.0, 0.0, 1.0), ax, depth)
        # the spiral band, proud of both ends
        sp = _spiral_disc(r * 1.04)
        for sgn in (-1, 1):
            o2 = (ox + ax[0] * sgn * depth / 2, oy + ax[1] * sgn * depth / 2,
                  zc)
            nn = (ax[0] * sgn, ax[1] * sgn, 0.0)
            out += _prism(sp, o2, (dx, dy, 0.0), (0.0, 0.0, 1.0), nn, 0.012)
    return out


def _order(style, cx, cy, ang, D, z0, z1) -> list:
    """[(faces, colour)] of a column of one of the five orders, after the
    plates (Doric, Ionic, Corinthian, Composite, Tuscan)."""
    H = max(z1 - z0, 0.5)
    r = D / 2
    out, shade = [], []
    z = z0
    # the base: none for the Greek Doric; Tuscan a plinth and a torus;
    # the others an Attic base (plinth, torus, scotia, torus)
    if style != "doric":
        ph = min(0.16, 0.05 * H)
        out += _solid(_rect(cx, cy, D * 1.32, D * 1.32, ang), z, z + ph)
        z += ph
        tb = min(0.07, 0.025 * H)
        out += _solid(_circle(cx, cy, r * 1.2), z, z + tb)
        z += tb
        if style != "tuscan":
            shade += _solid(_circle(cx, cy, r * 1.02), z, z + 0.03)  # scotia
            z += 0.03
            out += _solid(_circle(cx, cy, r * 1.12), z, z + 0.045)
            z += 0.045
    # the capital's height (the Corinthian's tall bell)
    cap = {"doric": 0.45, "tuscan": 0.5, "ionic": 0.55, "corinthian": 1.15,
           "composite": 1.15}[style] * D
    cap = min(max(cap, 0.18), 0.32 * H)
    ab = min(0.10, 0.12 * D + 0.02)
    zs1 = z1 - cap
    if style == "doric":
        shaft = _fluted(cx, cy, r, flutes=20, depth=min(0.028, r * 0.1),
                        per=6)
    elif style == "tuscan":
        shaft = _circle(cx, cy, r, 36)
    else:
        shaft = _fluted(cx, cy, r, flutes=24, depth=min(0.022, r * 0.08))
    out += _solid(shaft, z, zs1)
    # the astragal / necking ring
    shade += _solid(_circle(cx, cy, r * 1.06), zs1, zs1 + 0.03)
    zc0 = zs1 + 0.03
    if style in ("doric", "tuscan"):
        # neck (Tuscan), the echinus flaring out in rings, the abacus
        if style == "tuscan":
            out += _solid(_circle(cx, cy, r * 0.98), zc0, zc0 + 0.25 *
                          (z1 - ab - zc0))
            zc0 += 0.25 * (z1 - ab - zc0)
        n_ = 5
        for k in range(n_):
            za = zc0 + (z1 - ab - zc0) * k / n_
            zb = zc0 + (z1 - ab - zc0) * (k + 1) / n_
            out += _solid(_circle(cx, cy, r * (1.02 + 0.28 * (k + 1) / n_)),
                          za, zb)
        out += _solid(_rect(cx, cy, D * 1.42, D * 1.42, ang), z1 - ab, z1)
        return [(out, WHITE), (shade, SHADE)]
    if style in ("corinthian", "composite"):
        # the bell: rows of acanthus leaves curling out
        zb_top = z1 - ab - (0.30 * cap if style == "composite" else 0.10 *
                            cap)
        n_ = 6
        for k in range(n_):
            za = zc0 + (zb_top - zc0) * k / n_
            zb = zc0 + (zb_top - zc0) * (k + 1) / n_
            ro = r * (1.0 + 0.38 * (k + 1) / n_)
            leaf = _star(cx, cy, ro, ro * (0.78 if k % 2 == 0 else 0.86), 8,
                         rot=ang + (math.pi / 8) * (k % 2))
            (out if k % 2 == 0 else shade).extend(_solid(leaf, za, zb))
        if style == "corinthian":       # the small corner helices
            out += _volutes(cx, cy, ang, zb_top + 0.02 * cap, D * 0.95,
                            r * 0.18, r * 0.16, diagonal=True)
            zab = z1 - ab
        else:                           # Composite: an Ionic echinus and
            zec = zb_top                # big diagonal volutes over it
            out += _solid(_circle(cx, cy, r * 1.12), zec, zec + 0.08 * cap)
            out += _volutes(cx, cy, ang, zec + 0.14 * cap, D * 0.95,
                            r * 0.30, r * 0.26, diagonal=True)
            zab = z1 - ab
        # the abacus, its sides hollowed (a star of 4 points cut short)
        out += _solid(_star(cx, cy, D * 0.98, D * 0.74, 4,
                            rot=ang + math.pi / 4), zab, z1)
        return [(out, WHITE), (shade, SHADE)]
    # Ionic: egg-and-dart echinus, the cushion with its two scrolls, a
    # thin abacus
    ze = zc0
    out += _solid(_star(cx, cy, r * 1.16, r * 1.08, 12, rot=ang), ze,
                  ze + 0.30 * (z1 - ab - ze))
    zv = ze + 0.30 * (z1 - ab - ze)
    out += _solid(_rect(cx, cy, D * 1.2, D * 1.05, ang), zv, z1 - ab -
                  0.01)                   # the cushion (bolster)
    rv = min(0.36 * cap, r * 0.42)
    out += _volutes(cx, cy, ang, z1 - ab - rv * 0.95, D * 0.95, rv,
                    D * 1.02)
    out += _solid(_rect(cx, cy, D * 1.32, D * 1.32, ang), z1 - ab * 0.7, z1)
    return [(out, WHITE), (shade, SHADE)]


def faces(c, outline, z0, z1, style=None) -> list:
    """[(faces, colour)] of the architectural column ``c`` (its record),
    its plan ``outline`` [(x, y)], from z0 to z1."""
    style = style or c.get("astyle") or default_style(c)
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    ang = math.radians(float(c.get("angle", 0.0) or 0.0))
    w = float(c.get("w", max(xs) - min(xs)))
    d = float(c.get("d", w) or w) if c.get("shape") != "round" else w
    H = max(z1 - z0, 0.5)
    D = min(w, d)
    out, shade = [], []
    if style in ORDERS:
        return _order(style, cx, cy, ang, D, z0, z1)
    if style == "square_smooth":
        ph = min(0.25, 0.08 * H)
        out += _solid(_rect(cx, cy, w * 1.25, d * 1.25, ang), z0, z0 + ph)
        out += _solid(_rect(cx, cy, w * 1.12, d * 1.12, ang), z0 + ph,
                      z0 + ph + 0.04)
        ch = min(0.22, 0.07 * H)
        out += _solid(_rect(cx, cy, w, d, ang), z0 + ph + 0.04, z1 - ch)
        shade += _solid(_rect(cx, cy, w * 1.1, d * 1.1, ang), z1 - ch,
                        z1 - ch + 0.05)
        out += _solid(_rect(cx, cy, w * 1.22, d * 1.22, ang),
                      z1 - ch + 0.05, z1)
        return [(out, WHITE), (shade, SHADE)]
    r = D / 2
    ph = min(0.2, 0.06 * H)              # the square plinth
    out += _solid(_rect(cx, cy, D * 1.3, D * 1.3, ang), z0, z0 + ph)
    tb = min(0.07, 0.03 * H)             # the torus / the moulded base
    out += _solid(_circle(cx, cy, r * 1.18), z0 + ph, z0 + ph + tb)
    shade += _solid(_circle(cx, cy, r * 1.08), z0 + ph + tb,
                    z0 + ph + tb + 0.025)
    zs0 = z0 + ph + tb + 0.025
    if style == "corinthian":
        cap = min(max(1.0 * D, 0.35), 0.35 * H)
    else:
        cap = min(0.16, 0.06 * H)
    ab = min(0.09, 0.03 * H)             # the abacus
    zs1 = z1 - cap - ab
    shaft = _fluted(cx, cy, r) if style in ("round_fluted", "corinthian") \
        else _circle(cx, cy, r)
    out += _solid(shaft, zs0, zs1)
    shade += _solid(_circle(cx, cy, r * 1.06), zs1, zs1 + 0.03)  # astragal
    if style == "corinthian":
        # the bell: rings of leaves flaring out to the abacus
        n_ = 5
        for k in range(n_):
            za = zs1 + 0.03 + (cap - 0.03) * k / n_
            zb = zs1 + 0.03 + (cap - 0.03) * (k + 1) / n_
            ro = r * (1.0 + 0.32 * (k + 1) / n_)
            leaf = _star(cx, cy, ro, ro * 0.82, 8,
                         rot=(math.pi / 8) * (k % 2))
            (out if k % 2 == 0 else shade).extend(_solid(leaf, za, zb))
        abacus = _rect(cx, cy, D * 1.45, D * 1.45, ang)
        out += _solid(abacus, z1 - ab, z1)
        return [(out, WHITE), (shade, SHADE)]
    # the echinus and the square abacus
    out += _solid(_circle(cx, cy, r * 1.2), zs1 + 0.03, z1 - ab)
    out += _solid(_rect(cx, cy, D * 1.4, D * 1.4, ang), z1 - ab, z1)
    return [(out, WHITE), (shade, SHADE)]


CONCRETE = (0.62, 0.62, 0.60)
JOINT = (0.50, 0.50, 0.49)


#: the reinforcement's colours (the bars dark steel, the links red as
#: on the drawings) and how much of the concrete shows over it
STEEL = (0.22, 0.22, 0.24)
LINK = (0.78, 0.12, 0.12)
XRAY = 0.42


def rcc_faces(c, outline, z0, z1, rebar=False) -> list:
    """[(faces, colour)] of a STRUCTURAL column: bare reinforced concrete
    as cast — the plain section (rectangular with chamfered arrises, or
    round), its shuttering joints showing every 1.2 m, a kicker at its foot
    and its top cut square under the slab. No base, no capital."""
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    H = max(z1 - z0, 0.3)
    body, joint = [], []
    if c.get("shape") == "round":
        r = float(c.get("w", max(xs) - min(xs))) / 2

        def sec(rr):
            return _circle(cx, cy, rr, 32)
        sh = sec(r)
        kick = sec(r + 0.012)
    else:
        pts = [tuple(p[:2]) for p in outline]
        if len(pts) > 4 or len(pts) < 3:
            ang = math.radians(float(c.get("angle", 0.0) or 0.0))
            w = float(c.get("w", max(xs) - min(xs)))
            d = float(c.get("d", w) or w)
            pts = _rect(cx, cy, w, d, ang)
        ch = 0.02                       # 20 mm chamfered arrises
        sh = []
        n = len(pts)
        for i in range(n):
            a, b, c2 = pts[i - 1], pts[i], pts[(i + 1) % n]
            for q in (a, c2):
                L = math.dist(b, q) or 1.0
                sh.append((b[0] + (q[0] - b[0]) * ch / L,
                           b[1] + (q[1] - b[1]) * ch / L))
        # the corners' two cut points in order (from a, to c)
        kick = [((p[0] - cx) * 1.0 + cx, (p[1] - cy) * 1.0 + cy) for p in sh]
        kick = [(cx + (p[0] - cx) * (1 + 0.024 / max(math.dist(p, (cx, cy)),
                                                       0.05)),
                 cy + (p[1] - cy) * (1 + 0.024 / max(math.dist(p, (cx, cy)),
                                                       0.05)))
                for p in sh]
    # one clean pour, floor to soffit: no joints, no kicker — no lines on
    # the elevations
    body += _solid(sh, z0, z1)
    if not rebar:
        return [(body, CONCRETE), (joint, JOINT)]
    # its reinforcement seen through the concrete (an x-ray view): the
    # main bars and the links / the helix, cover 40 mm
    bars, links = [], []
    cov = 0.04
    if c.get("shape") == "round":
        r = float(c.get("w", max(xs) - min(xs))) / 2
        rr = max(r - cov - 0.008, 0.03)
        nb = 6 if r < 0.3 else 8
        for k in range(nb):
            a_ = 2 * math.pi * k / nb
            bx, by = cx + rr * math.cos(a_), cy + rr * math.sin(a_)
            bars += _solid(_circle(bx, by, 0.008, 8), z0 + 0.02, z1 - 0.02)
        zz = z0 + 0.1
        while zz < z1 - 0.05:           # the helix, as rings
            ring = _circle(cx, cy, rr + 0.012, 24)
            inner_ = _circle(cx, cy, rr + 0.004, 24)
            links += W_ring(ring, inner_, zz, zz + 0.008)
            zz += 0.10
    else:
        w = float(c.get("w", max(xs) - min(xs)))
        d = float(c.get("d", w) or w)
        ang = math.radians(float(c.get("angle", 0.0) or 0.0))
        if len(outline) == 4:            # its true sides, as drawn
            w = math.dist(outline[0], outline[1])
            d = math.dist(outline[1], outline[2])
            ang = math.atan2(outline[1][1] - outline[0][1],
                             outline[1][0] - outline[0][0])
        hw, hd = w / 2 - cov - 0.01, d / 2 - cov - 0.01
        ca, sa = math.cos(ang), math.sin(ang)

        def P(a, b):
            return (cx + ca * a - sa * b, cy + sa * a + ca * b)
        spots = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
        if w > 0.45:
            spots += [(0.0, -hd), (0.0, hd)]
        if d > 0.45:
            spots += [(-hw, 0.0), (hw, 0.0)]
        for a, b in spots:
            bx, by = P(a, b)
            bars += _solid(_circle(bx, by, 0.009, 8), z0 + 0.02, z1 - 0.02)
        zz = z0 + 0.1
        lo = [P(-hw - 0.012, -hd - 0.012), P(hw + 0.012, -hd - 0.012),
              P(hw + 0.012, hd + 0.012), P(-hw - 0.012, hd + 0.012)]
        li = [P(-hw - 0.004, -hd - 0.004), P(hw + 0.004, -hd - 0.004),
              P(hw + 0.004, hd + 0.004), P(-hw - 0.004, hd + 0.004)]
        while zz < z1 - 0.05:           # the links every 150 mm
            links += W_ring(lo, li, zz, zz + 0.008)
            zz += 0.15
    clear = (CONCRETE[0], CONCRETE[1], CONCRETE[2], XRAY)
    return [(body, clear), (joint, (JOINT[0], JOINT[1], JOINT[2], XRAY)),
            (bars, STEEL), (links, LINK)]


def W_ring(outer, inner, z0, z1) -> list:
    """A flat ring (a link, a turn of the helix) between two outlines."""
    from .engine import walls as W
    return W.solid({"outer": _ccw(list(outer)),
                    "holes": [list(reversed(_ccw(list(inner))))]}, z0, z1)


__all__ = ["faces", "rcc_faces", "STYLES", "ORDERS", "default_style"]
