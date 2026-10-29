# SPDX-License-Identifier: GPL-3.0-or-later
"""Curtains at the windows, on the room side: a rod over the window (its
brackets on the wall) and two pleated fabric panels drawn open, gathered
at the two ends of the rod — down to the floor, or a little under the
sill of a high window.

Or blinds: vertical louvre blinds (fabric vanes hung from a head rail,
half turned), horizontal venetian blinds (slats tilted, aluminium or
wood) and roller blinds (half down) — at the windows and at the glazed
sliding doors.

Settings: ``curtains`` (on/off), ``curtain_type`` (a key of TYPES),
``curtain_color`` (a key of COLORS), ``curtain_len`` («floor» or
«sill»). A window / door of its own: ``curtain`` (curtain_on, blind_v,
blind_h, roller, curtain_off).
"""
from __future__ import annotations

import math

COLORS = [("cream", "Cream", (0.88, 0.83, 0.72)),
          ("white", "White (sheer)", (0.95, 0.95, 0.93)),
          ("grey", "Grey", (0.62, 0.63, 0.64)),
          ("beige", "Beige", (0.80, 0.70, 0.56)),
          ("blue", "Blue", (0.40, 0.50, 0.64)),
          ("maroon", "Maroon", (0.48, 0.20, 0.22))]
COLORS += [("alu", "Aluminium (blinds)", (0.80, 0.81, 0.82)),
           ("walnut", "Walnut wood (blinds)", (0.42, 0.27, 0.16)),
           ("oak", "Light oak (blinds)", (0.74, 0.60, 0.42)),
           ("charcoal", "Charcoal", (0.25, 0.26, 0.28))]
TYPES = [("curtain", "Curtains (pleated, drawn open)"),
         ("blind_v", "Vertical louvre blinds"),
         ("blind_h", "Horizontal venetian blinds"),
         ("roller", "Roller blinds")]
ON = ("curtain_on", "blind_v", "blind_h", "roller")
#: the doors that take a curtain / blind: the glazed ones that slide
DOOR_STYLES = ("sliding", "folding", "glazed", "alu_glass", "glass")
RAIL = (0.90, 0.90, 0.90, 1.0)
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


def _inner_side(doc, lid, w, seg, pos, rooms):
    """A curtain asked for on a window the rooms do not tell (both sides
    rooms, or none read): the side under the floor slab and not out on a
    balcony — else the wall's own side."""
    import re
    from shapely.geometry import Point, Polygon
    n = (-seg.u[1], seg.u[0])
    c = (seg.p0[0] + seg.u[0] * pos, seg.p0[1] + seg.u[1] * pos)
    t2 = float(w["t"]) / 2
    score = []
    for sd in (1, -1):
        q = Point(c[0] + n[0] * sd * (t2 + 0.4),
                  c[1] + n[1] * sd * (t2 + 0.4))
        v = 0
        for r in rooms:
            if r["poly"].contains(q):
                v += 1 if not re.search(r"BALCON|TERRACE|SIT\s*OUT|OPEN",
                                        str(r.get("name", "")), re.I) else -1
        for e in doc["arch"]["structure"]:
            if e["type"] == "slab" and e["level"] == lid and \
                    e.get("corners"):
                try:
                    if Polygon(e["corners"]).contains(q):
                        v += 1
                except Exception:  # noqa: BLE001
                    pass
        score.append(v)
    if score[0] > score[1]:
        return 1
    if score[1] > score[0]:
        return -1
    return int(w.get("side", 1) or 1)


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
    if not every and not any(o.get("curtain") in ON
                             for o in doc["arch"]["openings"]):
        return []
    deflt = st.get("curtain_type") if st.get("curtain_type") in \
        dict(TYPES) else "curtain"
    arch = doc["arch"]
    col = dict((k, c) for k, _l, c in COLORS).get(
        st.get("curtain_color", "cream"), COLORS[0][2]) + (1.0,)
    to_floor = st.get("curtain_len", "floor") == "floor"
    rooms = spaces.of_level(arch, lid)
    by = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    out = []
    for o in arch["openings"]:
        w = by.get(o["wall"])
        if w is None or w.get("kind", "line") != "line" or \
                w.get("type") == "curtain":
            continue
        if not (o["kind"] == "window" or (o["kind"] == "door" and str(
                o.get("style") or "") in DOOR_STYLES)):
            continue
        if o.get("curtain") == "curtain_off" or \
                (not every and o.get("curtain") not in ON):
            continue                       # this window: none
        kind = {"curtain_on": "curtain"}.get(o.get("curtain"),
                                             o.get("curtain"))
        if kind not in dict(TYPES):
            kind = deflt
        seg = W.centre(w)
        sd = _room_side(doc, w, seg, float(o["pos"]), rooms)
        if not sd and o.get("curtain") in ON:
            sd = _inner_side(doc, lid, w, seg, float(o["pos"]), rooms)
        if not sd:
            continue
        u = seg.u
        n = (-u[1] * sd, u[0] * sd)              # into the room
        p0 = seg.p0
        t2 = float(w["t"]) / 2
        s0 = float(o["pos"]) - float(o["w"]) / 2 - OVER
        s1 = float(o["pos"]) + float(o["w"]) / 2 + OVER
        sill = float(o.get("sill", 0.0 if o["kind"] == "door" else 0.9)
                     or 0.0)
        head = sill + float(o["h"])
        zr = z0 + head + 0.12                    # the rod
        zb = z0 + 0.02 if (to_floor or sill < 0.5) else \
            z0 + max(sill - 0.15, 0.02)
        c = t2 + OFF
        if kind != "curtain":              # a blind, over the opening
            out += _blind(kind, p0, u, n, float(o["pos"]), float(o["w"]),
                          t2, z0 + sill, z0 + head, z0, col, to_floor,
                          o["kind"] == "door")
            continue
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


def _quad(a, b, za, zb, col) -> list:
    """A thin vertical strip from plan point a to b, both faces."""
    return [{"loop": [(a[0], a[1], za), (b[0], b[1], za),
                      (b[0], b[1], zb), (a[0], a[1], zb)],
             "holes": [], "color": col},
            {"loop": [(a[0], a[1], za), (a[0], a[1], zb),
                      (b[0], b[1], zb), (b[0], b[1], za)],
             "holes": [], "color": col}]


def _blind(kind, p0, u, n, pos, w, t2, zs, zh, z0, col, to_floor,
           door) -> list:
    """A blind over an opening (centre ``pos`` along the wall, width ``w``,
    sill ``zs``, head ``zh``) on the room side: its head rail and its
    vanes / slats / fabric."""
    from .engine import structure as S
    out = []
    s0 = pos - w / 2 - 0.05
    s1 = pos + w / 2 + 0.05
    c = t2 + 0.07                          # the blind's line off the wall
    zr = zh + 0.10                         # the head rail
    out += S._box(p0, u, n, s0, s1, c - 0.03, c + 0.03, zr - 0.035,
                  zr + 0.035, RAIL)
    for sb_ in (s0 + 0.04, s1 - 0.04):      # its brackets to the wall
        out += S._box(p0, u, n, sb_ - 0.01, sb_ + 0.01, t2, c - 0.03,
                      zr - 0.02, zr + 0.02, RAIL)
    zb = z0 + 0.02 if (door or to_floor or zs - z0 < 0.5) else zs - 0.02

    def P(s, cc):
        return (p0[0] + u[0] * s + n[0] * cc, p0[1] + u[1] * s + n[1] * cc)
    if kind == "blind_v":                   # vanes 89 mm, turned 35°
        vw, gap = 0.089, 0.080
        k = max(2, int((s1 - s0) / gap))
        ca, sa = math.cos(math.radians(35)), math.sin(math.radians(35))
        for i in range(k):
            sm = s0 + (i + 0.5) * (s1 - s0) / k
            a = P(sm - vw / 2 * ca, c - vw / 2 * sa)
            b = P(sm + vw / 2 * ca, c + vw / 2 * sa)
            out += _quad(a, b, zb, zr - 0.035, col)
        return out
    if kind == "blind_h":                   # slats 50 mm, tilted 25°
        sw, gap = 0.050, 0.045
        top = zr - 0.04
        k = max(2, int((top - zb) / gap))
        ca, sa = math.cos(math.radians(25)), math.sin(math.radians(25))
        for i in range(k):
            zm = top - (i + 0.5) * (top - zb) / k
            za = zm - sw / 2 * sa
            zz = zm + sw / 2 * sa
            ci, co = c - sw / 2 * ca, c + sw / 2 * ca
            a0, a1 = P(s0 + 0.01, ci), P(s1 - 0.01, ci)
            b0, b1 = P(s0 + 0.01, co), P(s1 - 0.01, co)
            out.append({"loop": [(a0[0], a0[1], zz), (a1[0], a1[1], zz),
                                 (b1[0], b1[1], za), (b0[0], b0[1], za)],
                        "holes": [], "color": col})
            out.append({"loop": [(a0[0], a0[1], zz), (b0[0], b0[1], za),
                                 (b1[0], b1[1], za), (a1[0], a1[1], zz)],
                        "holes": [], "color": col})
        for sl in (s0 + (s1 - s0) * 0.25, s0 + (s1 - s0) * 0.75):
            a, b = P(sl, c - 0.002), P(sl + 0.004, c - 0.002)
            out += _quad(a, b, zb, top, (0.85, 0.85, 0.82, 1.0))  # tapes
        return out
    # roller: the roll and the fabric half down
    out += S._box(p0, u, n, s0 + 0.02, s1 - 0.02, c + 0.03, c + 0.075,
                  zr - 0.03, zr + 0.03, col)
    zf = zr - 0.03 - (zr - zb) * 0.5
    a, b = P(s0 + 0.03, c + 0.05), P(s1 - 0.03, c + 0.05)
    out += _quad(a, b, zf, zr - 0.03, col)
    out += S._box(p0, u, n, s0 + 0.03, s1 - 0.03, c + 0.04, c + 0.06,
                  zf - 0.02, zf, RAIL)                     # bottom bar
    return out
