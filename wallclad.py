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
]
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


def faces_of(kind, R, P, s_a, s_b, seed) -> list:
    out = []
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
            s_a, s_b = (0.0, L) if ln <= 0 else (
                max(L / 2 + off - ln / 2, 0.0), min(L / 2 + off + ln / 2, L))
            if s_b - s_a < 0.1:
                continue
            seed = zlib.crc32(str(w["id"]).encode())
            for sg in _sides(doc, w, mid, n, t, rooms):
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
                    p_ = float(o.get("pos", 0.0))
                    ww = float(o.get("w", 0.9))
                    zs = z_of[lid] + float(o.get("sill", 0.0) or 0.0)
                    R = R.difference(box(p_ - ww / 2 - 0.03, zs - 0.03 if
                                         zs > zf + 0.05 else zf - 1,
                                         p_ + ww / 2 + 0.03,
                                         zs + float(o.get("h", 2.1)) + 0.03))
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
