"""3.64.46: the classical trims of a perspective's look (``doc["look"]``),
made from the model as it stands at every rebuild — so they follow the
plans:

- a stone plinth round the ground floor, string courses (floor bands) at
  every upper floor, a stepped cornice under the eaves;
- quoins (alternate stone blocks) up every outside corner;
- window surrounds: an architrave round each outside window — round its
  arch, with a keystone, on an arched one — and a projecting sill;
- the main door in a moulded arch with pilasters and a keystone, and two
  wall lanterns beside it;
- the outside free-standing columns drawn classical (Ionic), as an
  architectural column.

``doc["look"]`` = {"style", "trim", "stone", "metal"} (colours 0..1) —
set by lookstyle.apply, cleared when no perspective is followed.
"""
from __future__ import annotations

import math

from .engine.structure import _box

STRING_H = 0.25        # a floor band's height
STRING_D = 0.07        # … its projection
CORNICE = ((0.30, 0.06), (0.16, 0.14), (0.08, 0.22))   # (height, projection)
PLINTH_H = 0.45
PLINTH_D = 0.05
QUOIN_H = 0.30
QUOIN_W = (0.45, 0.28)
QUOIN_D = 0.03
SURR_W = 0.12          # a window's architrave
SURR_D = 0.05
SILL_H = 0.08
SILL_D = 0.08


def _c4(c):
    c = list(c)[:3]
    return (float(c[0]), float(c[1]), float(c[2]), 1.0)


def _ccw(pts):
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(pts, pts[1:] + pts[:1]))
    return list(pts) if a >= 0 else list(reversed(pts))


def _ring(poly, z0, z1, d, col, inset=0.0) -> list:
    """A band round an outline (outside it, ``d`` out), z0..z1."""
    out = []
    for ring in [poly.exterior]:
        pts = _ccw([(x, y) for x, y in list(ring.coords)[:-1]])
        n_ = len(pts)
        for i in range(n_):
            p, q = pts[i], pts[(i + 1) % n_]
            L = math.dist(p, q)
            if L < 0.05:
                continue
            u = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
            nl = (-u[1], u[0])                 # inward (left of CCW)
            out += _box(p, u, nl, -d, L + d, -d, inset, z0, z1, col)
    return out


def _outline(arch, lid):
    from . import lookstyle as LS
    poly, _ws = LS._outline(arch, lid)
    if poly is None:
        return None
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly.simplify(0.03)


def _corners(poly) -> list:
    """The outline's outside (convex) corners: [(p, u_prev, u_next)]."""
    poly = poly.simplify(0.15)
    pts = _ccw([(x, y) for x, y in list(poly.exterior.coords)[:-1]])
    out = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        u1 = (b[0] - a[0], b[1] - a[1])
        u2 = (c[0] - b[0], c[1] - b[1])
        L1, L2 = math.hypot(*u1), math.hypot(*u2)
        if L1 < 0.6 or L2 < 0.6:
            continue
        cr = u1[0] * u2[1] - u1[1] * u2[0]
        if cr > 0.2 * L1 * L2:                 # a left turn: convex (CCW)
            out.append((b, (u1[0] / L1, u1[1] / L1), (u2[0] / L2,
                                                        u2[1] / L2)))
    return out


def _quoins(poly, z0, z1, col) -> list:
    out = []
    for b, u1, u2 in _corners(poly):
        k, z = 0, z0 + 0.05
        while z + QUOIN_H <= z1 - 0.05:
            w1, w2 = QUOIN_W if k % 2 == 0 else QUOIN_W[::-1]
            # along the side before the corner (ends at it) and after it
            n1 = (-u1[1], u1[0])
            n2 = (-u2[1], u2[0])
            out += _box(b, u1, n1, -w1, QUOIN_D, -QUOIN_D, 0.0, z,
                        z + QUOIN_H - 0.03, col)
            out += _box(b, u2, n2, -QUOIN_D, w2, -QUOIN_D, 0.0, z,
                        z + QUOIN_H - 0.03, col)
            z += QUOIN_H
            k += 1
    return out


def _arc_pts(cx, cz, r, n=14):
    return [(cx + r * math.cos(math.pi * k / n),
             cz + r * math.sin(math.pi * k / n)) for k in range(n + 1)]


def _surround(w, o, z0, poly, trim, stone, door=False) -> list:
    """An opening's architrave (round its arch, with a keystone, on an
    arched one) and sill, on the wall's outside face."""
    from shapely.geometry import Point
    from .engine import walls as W
    seg = W.centre(w)
    if seg.kind != "line":
        return []
    t = float(w["t"])
    u = seg.u
    nl = (-u[1], u[0])
    c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
    # the outside: the side away from the building's outline
    probe = (c[0] + nl[0] * (t / 2 + 0.25), c[1] + nl[1] * (t / 2 + 0.25))
    sg = -1.0 if poly.buffer(-0.05).contains(Point(probe)) else 1.0
    face = t / 2
    a0, a1 = (face, face + SURR_D) if sg > 0 else (-face - SURR_D, -face)
    wd = float(o["w"])
    s0, s1 = float(o["pos"]) - wd / 2, float(o["pos"]) + wd / 2
    p0 = seg.p0
    zs = z0 + float(o.get("sill", 0.0) or 0.0)
    zt = zs + float(o["h"])
    arched = o.get("head") == "arch"
    r = wd / 2
    zspr = zt - r if arched else zt
    out = []
    sw = SURR_W * (1.6 if door else 1.0)
    # jambs
    out += _box(p0, u, nl, s0 - sw, s0, a0, a1, zs, zspr, trim)
    out += _box(p0, u, nl, s1, s1 + sw, a0, a1, zs, zspr, trim)
    if arched:
        cx = float(o["pos"])
        inner = _arc_pts(cx, zspr, r)
        outer = _arc_pts(cx, zspr, r + sw)
        for (x0_, z0_), (x1_, z1_), (X0, Z0), (X1, Z1) in zip(
                inner, inner[1:], outer, outer[1:]):
            # a voussoir: the quad between the two arcs, given depth
            quad = [(x0_, z0_), (x1_, z1_), (X1, Z1), (X0, Z0)]
            out += _prism(p0, u, nl, quad, a0, a1, trim)
        # the keystone
        out += _box(p0, u, nl, cx - 0.09, cx + 0.09, a0 - 0.02, a1 + 0.02,
                    zt - 0.02, zt + sw + 0.10, stone)
    else:
        out += _box(p0, u, nl, s0 - sw, s1 + sw, a0, a1, zt, zt + sw, trim)
        # a cornice hood over it
        out += _box(p0, u, nl, s0 - sw - 0.06, s1 + sw + 0.06,
                    *((a0, a1 + 0.05) if sg > 0 else (a0 - 0.05, a1)),
                    zt + sw, zt + sw + 0.07, trim)
    if not door and zs > z0 + 0.1:
        b0, b1 = (face, face + SILL_D) if sg > 0 else (-face - SILL_D, -face)
        out += _box(p0, u, nl, s0 - sw - 0.05, s1 + sw + 0.05, b0, b1,
                    zs - SILL_H, zs, trim)
    return out


def _prism(p0, u, nl, quad, a0, a1, col) -> list:
    """A flat shape in the wall's plane (s along it, z up) given depth
    a0..a1 across."""
    from .engine import walls as W

    def P(s, a, z):
        return (p0[0] + u[0] * s + nl[0] * a, p0[1] + u[1] * s + nl[1] * a, z)
    # solid() works in (x, y) → map (s, z) as (x, y) and depth as its z
    fs = W.solid({"outer": _ccw(quad), "holes": []}, a0, a1)
    out = []
    for f in fs:
        loop = f["loop"] if isinstance(f, dict) else f
        # (s, z, a) → world; (s, z, a) is left-handed against (u, n, z):
        # flip the loop to keep it outward
        pts = [P(x, d, y) for x, y, d in loop]
        out.append({"loop": list(reversed(pts)), "holes": [], "color": col})
    return out


def _lantern(p, u, nl, sg, face, z, metal) -> list:
    from . import siteorn as SO
    q = (p[0] + nl[0] * sg * (face + 0.18), p[1] + nl[1] * sg * (face + 0.18))
    out = _box(p, u, nl, -0.03, 0.03,
               *((face, face + 0.18) if sg > 0 else (-face - 0.18, -face)),
               z + 0.25, z + 0.29, _c4(metal))
    for fs, col in SO.lamp(q, z, 0.3):
        for f in fs:
            d = dict(f) if isinstance(f, dict) else {"loop": f, "holes": []}
            d["color"] = _c4(col)
            out.append(d)
    return out


def faces(doc) -> list:
    """Every trim of the look: [(name, faces)]."""
    look = doc.get("look") or {}
    if look.get("style") != "mediterranean":
        return []
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    trim = _c4(look.get("trim") or (0.93, 0.90, 0.84))
    stone = _c4(look.get("stone") or (0.80, 0.74, 0.64))
    metal = look.get("metal") or (0.1, 0.1, 0.1)
    order = sorted(range(len(levels)), key=lambda i: el[i])
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    built = [i for i in order if el[i] >= el[g] - 1e-6 and any(
        w["level"] == levels[i]["id"] and not w.get("rail") and not str(
            w.get("name", "")).lower().startswith(("roof parapet",
                                                   "roof edge"))
        for w in arch["walls"])]
    out = []
    polys = {}
    for i in built:
        p = _outline(arch, levels[i]["id"])
        if p is not None:
            polys[i] = p
    roofed = {e["level"] for e in arch["structure"]
              if e["type"] == "roof" and e.get("look")}
    for i, p in polys.items():
        z0 = el[i]
        z1 = z0 + float(levels[i]["height"])
        fs = []
        if i == g:                                   # the plinth
            fs += _ring(p, z0 - 0.35, z0 + PLINTH_H - 0.35, PLINTH_D, stone)
        nxt = [j for j in order if el[j] > z0 + 0.5]
        if nxt and nxt[0] in polys:                  # a floor band over it
            zb = el[nxt[0]]
            fs += _ring(p, zb - 0.10, zb - 0.10 + STRING_H, STRING_D, trim)
        if levels[i]["id"] in roofed:                # the eaves' cornice
            zc = z1
            for h_, d_ in CORNICE:
                fs += _ring(p, zc - h_, zc, d_, trim)
                zc -= h_ * 0.55
        fs += _quoins(p, z0, z1, stone)
        out.append((f"Look trims · {levels[i]['name']}", fs))
    # window and door surrounds, lanterns by the main door
    ws = {w["id"]: w for w in arch["walls"]}
    idx = {lv["id"]: k for k, lv in enumerate(levels)}
    from . import lookstyle as LS
    outer = LS._outer_walls(arch)
    by_lv = {}
    main = None
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or w["id"] not in outer or \
                str(w.get("name", "")).lower().startswith("corner"):
            continue
        i = idx.get(w["level"])
        if i not in polys:
            continue
        if o["kind"] == "window" and float(o["w"]) >= 0.5:
            by_lv.setdefault(i, []).extend(
                _surround(w, o, el[i], polys[i], trim, stone))
        elif o["kind"] == "door" and i == g and float(o["w"]) >= 0.9:
            by_lv.setdefault(i, []).extend(
                _surround(w, o, el[i], polys[i], trim, stone, door=True))
            if main is None or float(o["w"]) > float(main[1]["w"]):
                main = (w, o)
    for i, fs in by_lv.items():
        out.append((f"Look surrounds · {levels[i]['name']}", fs))
    if main is not None:
        from shapely.geometry import Point
        from .engine import walls as W
        w, o = main
        seg = W.centre(w)
        if seg.kind == "line":
            t = float(w["t"])
            u = seg.u
            nl = (-u[1], u[0])
            c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
            probe = (c[0] + nl[0] * (t / 2 + 0.25), c[1] + nl[1] *
                     (t / 2 + 0.25))
            sg = -1.0 if polys[g].buffer(-0.05).contains(Point(probe)) \
                else 1.0
            fs = []
            for s_ in (-1, 1):
                d_ = float(o["w"]) / 2 + 0.45
                p = (c[0] + u[0] * s_ * d_, c[1] + u[1] * s_ * d_)
                fs += _lantern(p, u, nl, sg, t / 2, el[g] + 2.1, metal)
            out.append(("Look lanterns · main door", fs))
    return out


def groups(doc) -> list:
    from core.group import Group

    from . import project as PJ
    from .host import KEY
    out = []
    for name, fs in faces(doc):
        if not fs:
            continue
        g = Group(PJ._mesh_of(fs), name=name)
        g.component = False
        g.material = {"color": fs[0]["color"][:3], "opacity": 1.0,
                      "name": "GRC / stone trim"}
        g.ifc = {"class": "IfcBuildingElementProxy", "name": name}
        g.ext = {KEY: {"type": "look_trim"}}
        out.append(g)
    return out


def classical_columns(doc) -> int:
    """The outside free-standing columns (a porch's, a veranda's) drawn
    classical: architectural, Ionic. How many."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    arch = doc["arch"]
    n = 0
    by_lv = {}
    for w in arch["walls"]:
        if "a" in w and not w.get("rail"):
            by_lv.setdefault(w["level"], []).append(
                LineString([w["a"][:2], w["b"][:2]]).buffer(
                    float(w["t"]) / 2 + 0.05, cap_style=2))
    U = {k: unary_union(v) for k, v in by_lv.items()}
    for c in arch["structure"]:
        if c["type"] != "column":
            continue
        u_ = U.get(c["level"])
        if u_ is not None and u_.contains(Point(c["x"], c["y"])):
            continue                       # in a wall: structural
        if c.get("astyle") != "ionic":
            c["role"] = "architectural"
            c["astyle"] = "ionic"
            n += 1
    return n
