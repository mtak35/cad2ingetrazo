# SPDX-License-Identifier: GPL-3.0-or-later
"""Interior wall cladding on a wall's face — the designer walls of a
bedroom / lounge: fluted walnut, a back-lit stone headboard panel, a
back-lit marble TV wall, beige panels with brass strips, and the
headboard wall that puts the stone between fluted walnut.

Set on a wall (Edit ▸ Wall cladding, or Edit type for every wall of the
type): ``clad`` (a key of TYPES, "none"), ``clad_side`` (clad_in — the
room side, the main room's on a partition —, clad_both, clad_l, clad_r:
left / right of the wall's drawn direction), ``clad_h`` (0 = up to the false ceiling, else
from the floor finish), ``clad_len`` (0 = the whole wall) and
``clad_off`` (its centre moved along the wall from the middle). Doors
and windows in the wall are left open, with a margin.
"""
from __future__ import annotations

import math
import re
import zlib

#: key → label
TYPES = [
    ("none", "No cladding"),
    ("fluted_walnut", "Fluted walnut panels (vertical slats, LED edges)"),
    ("stone_backlit", "Textured stone panel, back-lit edges, brass trim"),
    ("marble_backlit", "Marble slab wall, back-lit (TV wall)"),
    ("panel_brass", "Beige wall panels with brass inlay strips"),
    ("headboard_combo", "Headboard wall: back-lit stone between fluted "
                        "walnut"),
    # 3.64.37 (his pictures): headboards centred on the room's own stretch
    # of the wall, never past the room's corners
    ("hb_channel", "Headboard: vertical channel-tufted velvet + wall "
                   "mouldings"),
    ("hb_marble_fluted", "Headboard: book-matched marble between fluted "
                         "panels + classic mouldings"),
    ("hb_grid_gold", "Headboard: upholstered panel grid in a gold frame + "
                     "moulded frames and sconces"),
    ("hb_diamond", "Headboard: diamond-tufted (buttoned) panel + "
                   "mouldings"),
    ("hb_wood_slats", "Headboard: walnut slats with LED cove, wing "
                      "panels"),
]
#: the headboard designs (a set width, on the room's stretch of the wall)
HEADBOARDS = ("hb_channel", "hb_marble_fluted", "hb_grid_gold", "hb_diamond",
              "hb_wood_slats")
BY = dict(TYPES)
SIDES = [("clad_in", "The room side (the main room on a partition)"),
         ("clad_both", "Both faces of the wall"),
         ("clad_l", "Left face (as the wall is drawn, a → b)"),
         ("clad_r", "Right face (as the wall is drawn, a → b)")]

WALNUT = (0.45, 0.26, 0.14)
WALNUT_DK = (0.27, 0.15, 0.08)
STONE = (0.80, 0.72, 0.62)
STONE_JOINT = (0.70, 0.62, 0.52)
MARBLE = (0.94, 0.89, 0.81)
VEIN = (0.80, 0.66, 0.50)
PANEL = (0.86, 0.81, 0.75)
BRASS = (0.80, 0.62, 0.30)
LED = (1.0, 0.86, 0.60)
BATH = re.compile(r"BATH|TOILET|W\.?C|WASH|POWDER|STORE|KITCHEN|DRESS|"
                  r"PASSAGE|CORRIDOR|LOBBY|STAIR|LIFT|SHAFT|DUCT", re.I)


# ---- geometry in the wall's (along s, up z) plane ------------------------
def _sz_solid(poly, c0, c1, P, col) -> list:
    """A slab of the (s, z) polygon ``poly`` standing ``c0``..``c1`` off
    the wall face (P(s, z, c) → world): its faces as {"loop", "holes",
    "color"}."""
    out = []
    for g in getattr(poly, "geoms", [poly]):
        if g.geom_type != "Polygon" or g.area < 1e-5:
            continue
        g = g.simplify(0.0005)
        ext = list(g.exterior.coords)[:-1]
        if g.exterior.is_ccw:
            ext = ext[::-1]
        holes = [list(h.coords)[:-1] for h in g.interiors]
        holes = [h if LinearRingCCW(h) else h[::-1] for h in holes]
        front = [P(s, z, c1) for s, z in ext]
        back = [P(s, z, c0) for s, z in ext[::-1]]
        out.append({"loop": front, "holes": [[P(s, z, c1) for s, z in h]
                                             for h in holes], "color": col})
        out.append({"loop": back, "holes": [[P(s, z, c0) for s, z in h[::-1]]
                                            for h in holes], "color": col})
        for ring in [ext] + [h for h in holes]:
            for (s0, z0), (s1, z1) in zip(ring, ring[1:] + ring[:1]):
                out.append({"loop": [P(s0, z0, c0), P(s1, z1, c0),
                                     P(s1, z1, c1), P(s0, z0, c1)],
                            "color": col})
    return out


def LinearRingCCW(pts) -> bool:
    a = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1]))
    return a > 0


def _fluted(R, P, out, s_a, s_b):
    from shapely.geometry import box
    out += _sz_solid(R, 0.0, 0.012, P, WALNUT_DK)            # backing
    z0, z1 = R.bounds[1], R.bounds[3]
    s = s_a + 0.012
    while s < s_b - 0.012:
        out += _sz_solid(R.intersection(box(s, z0, s + 0.035, z1)), 0.012,
                         0.034, P, WALNUT)
        s += 0.055
    for s_ in (s_a, s_b - 0.012):                            # LED edges
        out += _sz_solid(R.intersection(box(s_, z0, s_ + 0.012, z1)),
                         0.0, 0.036, P, LED)


def _stone(R, P, out, seed):
    from shapely.geometry import box
    out += _sz_solid(R, 0.0, 0.018, P, LED)                  # glow behind
    p = R.buffer(-0.035, join_style=2)
    if p.is_empty:
        return
    out += _sz_solid(p, 0.018, 0.045, P, STONE)
    s0, z0, s1, z1 = p.bounds
    s = s0 + 0.6                                             # tile joints
    while s < s1 - 0.1:
        out += _sz_solid(p.intersection(box(s - 0.002, z0, s + 0.002, z1)),
                         0.045, 0.046, P, STONE_JOINT)
        s += 0.6
    z = z0 + 0.6
    while z < z1 - 0.1:
        out += _sz_solid(p.intersection(box(s0, z - 0.002, s1, z + 0.002)),
                         0.045, 0.046, P, STONE_JOINT)
        z += 0.6
    for s_ in (s0, s1 - 0.008):                              # brass trim
        out += _sz_solid(p.intersection(box(s_, z0, s_ + 0.008, z1)),
                         0.045, 0.050, P, BRASS)


def _marble(R, P, out, seed):
    from shapely import affinity
    from shapely.geometry import LineString
    out += _sz_solid(R, 0.0, 0.015, P, LED)
    p = R.buffer(-0.025, join_style=2)
    if p.is_empty:
        return
    out += _sz_solid(p, 0.015, 0.035, P, MARBLE)
    s0, z0, s1, z1 = p.bounds
    rnd = (seed % 997) / 997.0
    k = 0
    s = s0 - (z1 - z0)
    while s < s1:
        j = ((seed >> (k % 20)) & 7) / 7.0
        ln = LineString([(s + 0.2 * j, z0), (s + 0.35 + 0.3 * rnd,
                                              (z0 + z1) / 2),
                         (s + (z1 - z0) * 0.8 + 0.2 * j, z1)])
        v = ln.buffer(0.004 + 0.004 * j, cap_style=2).intersection(p)
        out += _sz_solid(v, 0.035, 0.0356, P, VEIN)
        s += 0.55 + 0.25 * j
        k += 1


def _panels(R, P, out, s_a, s_b):
    from shapely.geometry import box
    out += _sz_solid(R, 0.0, 0.018, P, PANEL)
    z0, z1 = R.bounds[1], R.bounds[3]
    n = max(int(round((s_b - s_a) / 1.2)), 1)
    for i in range(n + 1):
        s = s_a + (s_b - s_a) * i / n
        out += _sz_solid(R.intersection(box(s - 0.006, z0, s + 0.006, z1)),
                         0.018, 0.022, P, BRASS)


VELVET = (0.56, 0.56, 0.57)
GREIGE = (0.78, 0.74, 0.68)
MINK = (0.72, 0.64, 0.56)
TRIM = (0.90, 0.89, 0.86)
GOLD = (0.78, 0.62, 0.28)
WHITE = (0.93, 0.93, 0.92)
EBONY = (0.10, 0.09, 0.09)


def _frame(R, s0, z0, s1, z1, w, P, out, col, c1=0.015):
    """A moulding frame (picture-frame panel) on the wall."""
    from shapely.geometry import box
    if s1 - s0 < 3 * w or z1 - z0 < 3 * w:
        return
    ring = box(s0, z0, s1, z1).difference(box(s0 + w, z0 + w, s1 - w,
                                               z1 - w))
    out += _sz_solid(R.intersection(ring), 0.0, c1, P, col)


def _headboard(kind, R, P, s_a, s_b, seed) -> list:
    """3.64.37: a headboard design centred on s_a..s_b (the room's
    stretch of the wall), clipped to R (the face, the openings out)."""
    from shapely.geometry import LineString, Point, box
    out = []
    zf, zt = R.bounds[1], R.bounds[3]
    span = s_b - s_a
    mid = (s_a + s_b) / 2
    H_ = zt - zf
    if span < 0.6 or H_ < 1.0:
        return out
    W_ = min(2.0, span - 0.1)                   # (a king bed's width)
    h0, h1 = mid - W_ / 2, mid + W_ / 2
    side = min(0.75, (span - W_) / 2 - 0.12)    # the side panels' width
    def C(poly):
        return R.intersection(poly)
    if kind == "hb_channel":
        top = zf + min(1.55, H_ - 0.3)
        out += _sz_solid(C(box(h0, zf, h1, top)), 0.0, 0.04, P, VELVET)
        k = max(int(round(W_ / 0.17)), 4)
        cw = W_ / k
        for i in range(k):
            a_ = h0 + i * cw + 0.006
            b_ = h0 + (i + 1) * cw - 0.006
            out += _sz_solid(C(box(a_, zf + 0.02, b_, top - 0.05)), 0.04,
                             0.10, P, VELVET)
            out += _sz_solid(C(box(a_ + 0.02, top - 0.05, b_ - 0.02, top)),
                             0.04, 0.09, P, VELVET)     # the round top
        if top + 0.4 < zt - 0.2:                         # a frame above
            _frame(R, h0, top + 0.15, h1, zt - 0.22, 0.03, P, out, TRIM)
        if side > 0.3:                                   # tall side frames
            for a_, b_ in ((h0 - 0.12 - side, h0 - 0.12),
                           (h1 + 0.12, h1 + 0.12 + side)):
                _frame(R, a_, zf + 0.9, b_, zt - 0.22, 0.03, P, out, TRIM)
    elif kind == "hb_marble_fluted":
        mw = min(1.6, W_ * 0.8)
        m0, m1 = mid - mw / 2, mid + mw / 2
        out += _sz_solid(C(box(m0, zf, m1, zt)), 0.0, 0.02, P, MARBLE)
        for sg in (1, -1):                  # book-matched veins (a V)
            for j in range(4):
                d_ = 0.12 + 0.13 * j
                ln = LineString([(mid, zf + 1.0 + d_ * 1.6),
                                 (mid + sg * (mw / 2 - 0.05), zf + 1.0 +
                                  d_ * 0.5 + (zt - zf - 1.0) * 0.55),
                                 (mid + sg * 0.15 * j, zt)])
                v_ = ln.buffer(0.006 + 0.004 * (j % 2), cap_style=2)
                out += _sz_solid(C(v_.intersection(box(m0, zf, m1, zt))),
                                 0.02, 0.021, P, (0.18, 0.17, 0.16))
        fl = min(0.55, (span - mw) / 2 - 0.05)
        for a_, b_ in ((m0 - fl, m0), (m1, m1 + fl)):    # fluted panels
            if fl < 0.15:
                break
            out += _sz_solid(C(box(a_, zf, b_, zt)), 0.0, 0.01, P, WHITE)
            x = a_ + 0.01
            while x < b_ - 0.03:
                out += _sz_solid(C(box(x, zf, x + 0.022, zt)), 0.01, 0.03,
                                 P, WHITE)
                x += 0.045
        ws_ = (span - mw) / 2 - fl - 0.15            # classic mouldings
        if ws_ > 0.35:
            for a_, b_ in ((m0 - fl - 0.1 - ws_, m0 - fl - 0.1),
                           (m1 + fl + 0.1, m1 + fl + 0.1 + ws_)):
                _frame(R, a_, zf + 0.3, b_, zt - 0.3, 0.035, P, out, TRIM,
                       0.02)
                for cs_, cz_ in ((a_, zt - 0.3), (b_, zt - 0.3)):
                    out += _sz_solid(C(Point(cs_, cz_ - 0.05).buffer(
                        0.07)), 0.0, 0.03, P, TRIM)   # corner ornaments
        hw = min(1.95, span - 0.2)                     # the bed's own
        top = zf + 1.2                                 # headboard
        out += _sz_solid(C(box(mid - hw / 2, zf + 0.2, mid + hw / 2, top)),
                         0.03, 0.12, P, EBONY)
        out += _sz_solid(C(box(mid - hw / 2 + 0.06, zf + 0.26,
                               mid + hw / 2 - 0.06, top - 0.06)), 0.12,
                         0.16, P, GREIGE)
    elif kind == "hb_grid_gold":
        top = zf + min(2.3, H_ - 0.25)
        out += _sz_solid(C(box(h0, zf, h1, top)), 0.0, 0.10, P, GOLD)
        rows = [(zf + 0.02, zf + 0.75), (zf + 0.77, zf + 1.55),
                (zf + 1.57, top - 0.04)]
        pat = [(0.25, 0.5, 0.25), (0.33, 0.34, 0.33), (0.2, 0.3, 0.3, 0.2)]
        for (za, zb), fr in zip(rows, pat):
            x = h0 + 0.04
            ww_ = W_ - 0.08
            for f_ in fr:
                # the inner cells split once more, as in the picture
                cuts = [f_ * ww_] if f_ < 0.3 else [f_ * ww_ / 2] * 2
                for cw in cuts:
                    out += _sz_solid(C(box(x + 0.006, za, x + cw - 0.006,
                                           zb)), 0.10, 0.17, P, MINK)
                    x += cw
        if side > 0.35:
            for a_, b_ in ((h0 - 0.15 - side, h0 - 0.15),
                           (h1 + 0.15, h1 + 0.15 + side)):
                _frame(R, a_, zf + 0.95, b_, zt - 0.3, 0.035, P, out, WHITE,
                       0.02)
                cs_ = (a_ + b_) / 2                       # the sconce
                out += _sz_solid(C(box(cs_ - 0.12, zf + 1.55, cs_ + 0.12,
                                       zf + 1.85)), 0.0, 0.07, P, GOLD)
                out += _sz_solid(C(box(cs_ - 0.10, zf + 1.30, cs_ + 0.10,
                                       zf + 1.55)), 0.0, 0.03, P, LED)
    elif kind == "hb_diamond":
        top = zf + min(1.6, H_ - 0.3)
        P_ = box(h0, zf, h1, top)
        out += _sz_solid(C(P_), 0.0, 0.09, P, GREIGE)
        pitch = 0.22
        n_ = int(W_ / pitch) + 2
        for sg in (1, -1):                   # the creases
            for i in range(-n_, 2 * n_):
                x0 = h0 + i * pitch
                ln = LineString([(x0, zf), (x0 + sg * (top - zf), top)])
                out += _sz_solid(C(ln.buffer(0.005).intersection(P_)), 0.09,
                                 0.092, P, (0.62, 0.58, 0.52))
        z = zf + pitch / 2                   # the buttons
        r_ = 0
        while z < top - 0.05:
            x = h0 + (pitch / 2 if r_ % 2 else pitch)
            while x < h1 - 0.05:
                out += _sz_solid(C(Point(x, z).buffer(0.018, 6)), 0.09,
                                 0.105, P, (0.55, 0.50, 0.44))
                x += pitch
            z += pitch / 2
            r_ += 1
        out += _sz_solid(C(box(h0 - 0.04, zf, h0, top + 0.04)), 0.0, 0.11,
                         P, GOLD)
        out += _sz_solid(C(box(h1, zf, h1 + 0.04, top + 0.04)), 0.0, 0.11,
                         P, GOLD)
        out += _sz_solid(C(box(h0, top, h1, top + 0.04)), 0.0, 0.11, P,
                         GOLD)
        if side > 0.3:
            for a_, b_ in ((h0 - 0.12 - side, h0 - 0.12),
                           (h1 + 0.12, h1 + 0.12 + side)):
                _frame(R, a_, zf + 0.9, b_, zt - 0.22, 0.03, P, out, TRIM)
    elif kind == "hb_wood_slats":
        top = zt - 0.02
        ww_ = min(W_ + 0.8, span - 0.1)
        a0, a1 = mid - ww_ / 2, mid + ww_ / 2
        out += _sz_solid(C(box(a0, zf, a1, top)), 0.0, 0.012, P, WALNUT_DK)
        x = a0 + 0.01
        while x < a1 - 0.03:
            out += _sz_solid(C(box(x, zf, x + 0.04, top)), 0.012, 0.035, P,
                             WALNUT)
            x += 0.06
        out += _sz_solid(C(box(a0, top - 0.04, a1, top)), 0.0, 0.04, P,
                         LED)                     # the cove's glow
        hb_top = zf + 1.15
        out += _sz_solid(C(box(h0, zf + 0.25, h1, hb_top)), 0.035, 0.11, P,
                         GREIGE)
        for a_, b_ in ((h0 - 0.45, h0), (h1, h1 + 0.45)):   # wing panels
            out += _sz_solid(C(box(max(a_, a0), zf + 0.25, min(b_, a1),
                                   hb_top)), 0.035, 0.09, P, GREIGE)
    return out


def faces_of(kind, R, P, s_a, s_b, seed) -> list:
    out = []
    if kind in HEADBOARDS:
        return _headboard(kind, R, P, s_a, s_b, seed)
    if kind == "fluted_walnut":
        _fluted(R, P, out, s_a, s_b)
    elif kind == "stone_backlit":
        _stone(R, P, out, seed)
    elif kind == "marble_backlit":
        _marble(R, P, out, seed)
    elif kind == "panel_brass":
        _panels(R, P, out, s_a, s_b)
    elif kind == "headboard_combo":
        from shapely.geometry import box
        z0, z1 = R.bounds[1] - 1, R.bounds[3] + 1
        L = s_b - s_a
        m0 = s_a + L * 0.25
        m1 = s_b - L * 0.25
        _stone(R.intersection(box(m0, z0, m1, z1)), P, out, seed)
        for a_, b_ in ((s_a, m0), (m1, s_b)):
            q = R.intersection(box(a_, z0, b_, z1))
            if not q.is_empty:
                _fluted(q, P, out, a_, b_)
    return out


# ---- where and how high ---------------------------------------------------
def _sides(doc, w, seg_mid, n, t, rooms) -> list:
    """The faces to clad: +1 (left of a → b), −1 (right)."""
    want = w.get("clad_side") or "clad_in"
    if want == "clad_both":
        return [1, -1]
    if want == "clad_l":
        return [1]
    if want == "clad_r":
        return [-1]
    from shapely.geometry import Point
    score = {}
    for sg in (1, -1):
        pt = Point(seg_mid[0] + n[0] * sg * (t / 2 + 0.3),
                   seg_mid[1] + n[1] * sg * (t / 2 + 0.3))
        for r in rooms:
            if r["poly"].contains(pt):
                nm = str(r.get("name", ""))
                score[sg] = (0 if BATH.search(nm) else 1, r["area"])
                break
    if not score:
        return [1]
    return [max(score, key=lambda k: score[k])]


def sides_now(doc, w) -> list:
    """The faces of wall ``w`` its cladding is on now: [+1] left, [−1]
    right, [1, −1] both (the room side worked out as the model does)."""
    from .engine import spaces
    from .engine import walls as W
    want = w.get("clad_side") or "clad_in"
    if want != "clad_in":
        return _sides(doc, w, (0, 0), (0, 1), 0.0, [])
    try:
        seg = W.centre(w)
        a, b = seg.p0, seg.p1
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        rooms = [r for r in spaces.of_level(doc["arch"], w["level"])
                 if r["area"] >= 1.0]
        return _sides(doc, w, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
                      (-u[1], u[0]), float(w["t"]), rooms)
    except Exception:  # noqa: BLE001
        return [1]


def flipped(doc, w) -> str:
    """``clad_side`` with the cladding on the wall's other face (both
    faces stay both)."""
    now = sides_now(doc, w)
    if len(now) > 1:
        return "clad_both"
    return "clad_r" if now[0] == 1 else "clad_l"


def _ceiling_h(doc, lid, rooms, pt) -> float | None:
    """The false ceiling's height over the floor where ``pt`` stands."""
    from shapely.geometry import Point
    for r in rooms:
        if r["poly"].contains(Point(pt)):
            rec = r.get("rec") or {}
            if rec.get("ceiling") == "none":
                return None
            if rec.get("ceiling_h"):
                return float(rec["ceiling_h"])
            break
    c = (doc.get("ceilings") or {}).get(lid)
    if c:
        return float(c.get("h", 2.4384))
    return None


def groups(doc) -> list:
    """A group per clad wall face (IfcCovering), tagged as its wall's, so
    a click on the cladding picks the wall (and its cladding fields)."""
    from shapely.geometry import box

    from core.group import Group

    from . import finishes as FN
    from . import project as PJ
    from .engine import spaces
    from .engine import walls as W
    from .host import KEY, level_layer
    arch = doc["arch"]
    clad = [w for w in arch["walls"] if w.get("clad") in BY
            and w.get("clad") != "none" and w.get("kind", "line") == "line"
            and not w.get("rail") and w.get("type") != "curtain"]
    if not clad:
        return []
    st = doc["settings"]
    elev = PJ.elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    lvh = {lv["id"]: float(lv.get("height") or 3.0) for lv in arch["levels"]}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    fin = float(st.get("finish_t", 0.0508) or 0.0) \
        if st.get("finish_on", True) else 0.0
    ops_of = {}
    for o in arch["openings"]:
        ops_of.setdefault(o.get("wall"), []).append(o)
    rooms_of = {}
    plans_of = {}
    out = []
    for w in clad:
        lid = w["level"]
        if lid not in z_of:
            continue
        try:
            if lid not in rooms_of:
                rooms_of[lid] = [r for r in spaces.of_level(arch, lid)
                                 if r["area"] >= 1.0]
            rooms = rooms_of[lid]
            seg = W.centre(w)
            a, b = seg.p0, seg.p1
            L = math.dist(a, b)
            if L < 0.2:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            n = (-u[1], u[0])
            t = float(w["t"])
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            zf = z_of[lid] + fin
            if w.get("height", "level") == "level":
                ztop = z_of[lid] + lvh[lid]
            else:
                ztop = z_of[lid] + float(w.get("base", 0.0) or 0.0) + \
                    float(w["height"])
            ln = float(w.get("clad_len") or 0.0)
            off = float(w.get("clad_off") or 0.0)
            if lid not in plans_of:
                plans_of[lid] = W.plan([x for x in arch["walls"]
                                        if x["level"] == lid
                                        and not x.get("rail")])
            seed = zlib.crc32(str(w["id"]).encode())
            rpoly_ = None
            if w.get("clad_room"):          # 3.64.35: that room's only
                from shapely.geometry import Point as _Pt
                q_ = _Pt(*w["clad_room"])
                rpoly_ = next((r["poly"] for r in rooms
                               if r["poly"].contains(q_)), None)
            sides_ = _sides(doc, w, mid, n, t, rooms)
            if rpoly_ is not None and (w.get("clad_side") or "clad_in") \
                    == "clad_in":           # the face looking into it
                sides_ = [sg_ for sg_ in (1, -1) if FN.room_clip(
                    w, "l" if sg_ == 1 else "r", rpoly_)] or sides_
            for sg in sides_:
                # the face's own ends (mitred at the corners: no gap)
                f_a, f_b = FN._face_span(w, sg, L, plans_of[lid])
                s_a, s_b = (f_a, f_b) if ln <= 0 else (
                    max(L / 2 + off - ln / 2, f_a),
                    min(L / 2 + off + ln / 2, f_b))
                if rpoly_ is not None:
                    cl_ = FN.room_clip(w, "l" if sg == 1 else "r", rpoly_)
                    if not cl_:
                        continue
                    c0_, c1_ = max(cl_, key=lambda c: c[1] - c[0])
                    s_a, s_b = max(s_a, c0_), min(s_b, c1_)
                if w["clad"] in HEADBOARDS:   # 3.64.37: the room's own
                    f_a2, f_b2 = FN._face_span(w, sg, L, plans_of[lid])
                    if rpoly_ is not None:       # stretch of the wall
                        cl2_ = FN.room_clip(w, "l" if sg == 1 else "r",
                                            rpoly_)
                        if cl2_:
                            c0_, c1_ = max(cl2_, key=lambda c: c[1] - c[0])
                            f_a2, f_b2 = max(f_a2, c0_), min(f_b2, c1_)
                    s_a, s_b = f_a2, f_b2   # (centred on it, inside it)
                if s_b - s_a < 0.1:
                    continue
                side_pt = (mid[0] + n[0] * sg * (t / 2 + 0.3),
                           mid[1] + n[1] * sg * (t / 2 + 0.3))
                hh = float(w.get("clad_h") or 0.0)
                if hh > 0:
                    z1 = zf + hh
                else:
                    ch = _ceiling_h(doc, lid, rooms, side_pt)
                    z1 = z_of[lid] + fin + ch if ch else ztop - float(
                        st.get("slab_t", 0.15) or 0.15)
                z1 = min(z1, ztop)
                if z1 - zf < 0.1:
                    continue
                R = box(s_a, zf, s_b, z1)
                for o in ops_of.get(w["id"], []):
                    if o.get("niche") and int((o["niche"] or {}).get(
                            "face", 1)) != sg:
                        continue             # 3.64.36: a niche's back face
                    p_ = float(o.get("pos", 0.0))
                    ww = float(o.get("w", 0.9))
                    zs = z_of[lid] + float(o.get("sill", 0.0) or 0.0)
                    mg = max(0.03, FN.op_margin(o))   # clear of the trim
                    R = R.difference(box(p_ - ww / 2 - mg, zs - mg if
                                         zs > zf + 0.05 else zf - 1,
                                         p_ + ww / 2 + mg,
                                         zs + float(o.get("h", 2.1)) + mg))
                cb_ = FN.cwin_box(w, z_of[lid], L, 0.03)
                if cb_ is not None:          # a corner window's glass
                    R = R.difference(cb_)
                if R.is_empty:
                    continue
                f0 = sg * t / 2

                def P(s, z, c, a=a, u=u, n=n, f0=f0, sg=sg):
                    cc = f0 + sg * c
                    return (a[0] + u[0] * s + n[0] * cc,
                            a[1] + u[1] * s + n[1] * cc, z)
                fs = faces_of(w["clad"], R, P, s_a, s_b, seed)
                if sg < 0:                  # mirrored: the loops turned
                    for f in fs:
                        f["loop"] = f["loop"][::-1]
                        f["holes"] = [h[::-1] for h in f.get("holes") or []]
                if not fs:
                    continue
                g = Group(PJ._mesh_of(fs), name=f"{BY[w['clad']].split(' (')[0]}"
                          f" · {w.get('name') or 'Wall'} · {names[lid]}")
                g.component = False
                g.material = {"color": PANEL, "opacity": 1.0}
                g.layer = level_layer(names[lid])
                g.ifc = {"class": "IfcCovering", "name": "Wall cladding"}
                g.ext = {KEY: {"type": "wall", "id": w["id"], "level": lid,
                               "part": "clad"}}
                out.append(g)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("wallclad.groups")
    return out
