# SPDX-License-Identifier: GPL-3.0-or-later
"""Curtains at the windows, on the room side: a rod over the window (its
brackets on the wall) and two pleated fabric panels drawn open, gathered
at the two ends of the rod — down to the floor, or a little under the
sill of a high window.

Settings: ``curtains`` (on/off), ``curtain_color`` (a key of COLORS),
``curtain_len`` («floor» or «sill»).
"""
from __future__ import annotations

import math

COLORS = [("cream", "Cream", (0.88, 0.83, 0.72)),
          ("white", "White (sheer)", (0.95, 0.95, 0.93)),
          ("grey", "Grey", (0.62, 0.63, 0.64)),
          ("beige", "Beige", (0.80, 0.70, 0.56)),
          ("blue", "Blue", (0.40, 0.50, 0.64)),
          ("maroon", "Maroon", (0.48, 0.20, 0.22))]
ROD = (0.25, 0.25, 0.26, 1.0)
OFF = 0.12            # m: the curtain's line off the wall's face
OVER = 0.15           # m: the rod past each side of the window
PLEAT = 0.09          # m: one pleat (a fold out and back)
DEEP = 0.035          # m: how far a pleat stands out


def _room_side(doc, w, seg, pos, rooms):
    """+1 / −1: the side of the wall (along its normal) a room lies on;
    0 when both sides (an inner window) or neither are rooms."""
    from shapely.geometry import Point
    n = (-seg.u[1], seg.u[0])
    c = (seg.p0[0] + seg.u[0] * pos, seg.p0[1] + seg.u[1] * pos)
    t2 = float(w["t"]) / 2
    hit = []
    for sd in (1, -1):
        q = Point(c[0] + n[0] * sd * (t2 + 0.4), c[1] + n[1] * sd * (t2 + 0.4))
        hit.append(any(r["poly"].contains(q) for r in rooms))
    if hit[0] and not hit[1]:
        return 1
    if hit[1] and not hit[0]:
        return -1
    return 0


def _panel(p0, u, n, sa, sb, c, za, zb, col):
    """A pleated panel from sa to sb along the wall at offset c: a zigzag
    of vertical strips (one face each)."""
    out = []
    W = sb - sa
    k = max(2, int(round(W / (PLEAT / 2))))
    pts = []
    for i in range(k + 1):
        s = sa + W * i / k
        cc = c + (DEEP if i % 2 else 0.0)
        pts.append((p0[0] + u[0] * s + n[0] * cc, p0[1] + u[1] * s + n[1] * cc))
    for a, b in zip(pts, pts[1:]):
        out.append({"loop": [(a[0], a[1], za), (b[0], b[1], za),
                             (b[0], b[1], zb), (a[0], a[1], zb)],
                    "holes": [], "color": col})
        out.append({"loop": [(a[0], a[1], za), (a[0], a[1], zb),
                             (b[0], b[1], zb), (b[0], b[1], za)],
                    "holes": [], "color": col})          # both faces
    return out


def faces(doc, lid, z0) -> list:
    """The curtains of every window on level ``lid`` (floor at ``z0``)."""
    from .engine import spaces
    from .engine import structure as S
    from .engine import walls as W
    st = doc["settings"]
    every = bool(st.get("curtains"))
    if not every and not any(o.get("curtain") == "curtain_on"
                             for o in doc["arch"]["openings"]):
        return []
    arch = doc["arch"]
    col = dict((k, c) for k, _l, c in COLORS).get(
        st.get("curtain_color", "cream"), COLORS[0][2]) + (1.0,)
    to_floor = st.get("curtain_len", "floor") == "floor"
    rooms = spaces.of_level(arch, lid)
    by = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    out = []
    for o in arch["openings"]:
        w = by.get(o["wall"])
        if w is None or o["kind"] != "window" or \
                w.get("kind", "line") != "line" or w.get("type") == "curtain":
            continue
        if o.get("curtain") == "curtain_off" or \
                (not every and o.get("curtain") != "curtain_on"):
            continue                       # this window: none
        seg = W.centre(w)
        sd = _room_side(doc, w, seg, float(o["pos"]), rooms)
        if not sd:
            continue
        u = seg.u
        n = (-u[1] * sd, u[0] * sd)              # into the room
        p0 = seg.p0
        t2 = float(w["t"]) / 2
        s0 = float(o["pos"]) - float(o["w"]) / 2 - OVER
        s1 = float(o["pos"]) + float(o["w"]) / 2 + OVER
        sill = float(o.get("sill", 0.9))
        head = sill + float(o["h"])
        zr = z0 + head + 0.12                    # the rod
        zb = z0 + 0.02 if (to_floor or sill < 0.5) else \
            z0 + max(sill - 0.15, 0.02)
        c = t2 + OFF
        # the rod and its two brackets
        out += S._box(p0, u, n, s0 - 0.03, s1 + 0.03, c - 0.012, c + 0.012,
                      zr - 0.012, zr + 0.012, ROD)
        for sb_ in (s0 + 0.05, s1 - 0.05):
            out += S._box(p0, u, n, sb_ - 0.01, sb_ + 0.01, t2, c,
                          zr - 0.01, zr + 0.01, ROD)
        # two panels, drawn open: each a third of the rod, gathered
        pw = max((s1 - s0) * 0.22, 0.25)
        for a, b in ((s0, s0 + pw), (s1 - pw, s1)):
            out += _panel(p0, u, n, a, b, c - DEEP / 2, zb, zr - 0.02, col)
    return out
