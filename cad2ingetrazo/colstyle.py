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

STYLES = (("round_smooth", "Round smooth (base and capital)"),
          ("round_fluted", "Round fluted"),
          ("corinthian", "Fluted with Corinthian capital"),
          ("square_smooth", "Square smooth (plinth and cap)"))
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


def rcc_faces(c, outline, z0, z1) -> list:
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
    kh = min(0.075, 0.05 * H)            # the kicker
    joint += _solid(kick, z0, z0 + kh)
    z = z0 + kh
    lift = 1.2                           # a shuttering lift
    while z < z1 - 1e-3:
        zt = min(z + lift, z1)
        body += _solid(sh, z, max(zt - (0.006 if zt < z1 else 0.0), z + 1e-3))
        if zt < z1:                      # the joint, a hair proud
            jj = [(cx + (p[0] - cx) * (1 + 0.004 / max(
                math.dist(p, (cx, cy)), 0.05)),
                cy + (p[1] - cy) * (1 + 0.004 / max(
                    math.dist(p, (cx, cy)), 0.05))) for p in sh]
            joint += _solid(jj, zt - 0.006, zt)
        z = zt
    return [(body, CONCRETE), (joint, JOINT)]


__all__ = ["faces", "rcc_faces", "STYLES", "default_style"]
