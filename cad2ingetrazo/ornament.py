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
CORNICE = ((0.08, 0.22), (0.16, 0.14), (0.30, 0.06))   # (height, projection), top first: the widest ring on top (3.64.119; was upside down)
PLINTH_H = 0.45
PLINTH_D = 0.05
QUOIN_H = 0.30
QUOIN_W = (0.45, 0.28)
QUOIN_D = 0.035
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
    """A band round an outline (outside it, ``d`` out), z0..z1.
    3.64.76: one mitred solid — the corners meet exactly (the old boxes
    overran each other at every corner: overlapping faces)."""
    try:
        from . import modern as MD
        band = poly.buffer(d, join_style=2, mitre_limit=3.0).difference(
            poly.buffer(-float(inset), join_style=2, mitre_limit=3.0)
            if inset else poly)
        fs = MD._solid(band, z0, z1, col)
        if fs:
            return fs
    except Exception:  # noqa: BLE001
        pass
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
    # 3.64.78: the columns standing at the outline (a corner column is
    # thicker than the wall): the bands and quoins go round them, not
    # into them
    try:
        from shapely.geometry import Polygon as _Pg
        from shapely.ops import unary_union as _uu
        from .engine import structure as S_
        cols = []
        for c in arch.get("structure") or []:
            if c.get("type") == "column" and c.get("level") == lid:
                q = _Pg([tuple(v[:2]) for v in S_.column_outline(c)]
                        ).buffer(0.01)
                if not q.is_empty and q.intersects(poly.boundary.buffer(
                        0.05)):
                    cols.append(q)
        if cols:
            u = _uu([poly] + cols).buffer(0.02, join_style=2).buffer(
                -0.02, join_style=2)
            poly = max(getattr(u, "geoms", [u]), key=lambda g: g.area)
            poly = _Pg(poly.exterior)
    except Exception:  # noqa: BLE001
        pass
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly.simplify(0.03)


def _floor_outline(arch, lid, fallback):
    """3.64.77: a floor band follows the FLOOR slab's edge (balconies and
    terraces that project, the slab as cast), not the walls below it; the
    walls' outline when that level has no slab."""
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        ps = []
        for e in arch.get("structure") or []:
            if e.get("type") != "slab" or e.get("level") != lid or \
                    e.get("roof") or e.get("auto_roof"):
                continue
            c = e.get("corners") or []
            if len(c) >= 3:
                q = Polygon([tuple(v[:2]) for v in c]).buffer(0)
                if not q.is_empty:
                    ps.append(q)
        has_slab = bool(ps)
        if not ps:
            # 3.64.109: no slab record on this floor: the floor is what its
            # rooms (terraces, open lobbies included) cover
            try:
                from .engine import spaces as SP_
                for r_ in SP_.of_level(arch, lid):
                    q = r_.get("poly")
                    if q is not None and not q.is_empty and r_.get(
                            "area", 2.0) >= 1.0:
                        ps.append(q.buffer(0))
            except Exception:  # noqa: BLE001
                pass
        # 3.64.111: the railings of the floor stand on the slab's OUTER
        # edge: they are part of the floor's extent
        try:
            from shapely.geometry import LineString
            for w_ in arch.get("walls") or []:
                if w_.get("level") == lid and w_.get("rail") and "a" in w_:
                    ps.append(LineString([tuple(w_["a"][:2]),
                                          tuple(w_["b"][:2])]).buffer(0.08))
        except Exception:  # noqa: BLE001
            pass
        if not ps:
            return fallback
        if len(ps) > 1 and not has_slab:
            # no slab record: close the notches between the rooms and the
            # railings (the floor runs on to the railing): the outer edge
            try:
                cl = unary_union(ps + ([fallback] if fallback is not None
                                       else [])).buffer(0.9, join_style=2) \
                    .buffer(-0.9, join_style=2)
                if not cl.is_empty:
                    ps = [cl]
            except Exception:  # noqa: BLE001
                pass
        if fallback is None:        # 3.64.109: a floor with no walls of its own
            u = unary_union(ps).buffer(0.02).buffer(-0.02)
            if u.is_empty:
                return None
            if u.geom_type != "Polygon":
                u = max(u.geoms, key=lambda g: g.area)
            return Polygon(u.exterior).simplify(0.03)
        u = unary_union(ps + [fallback]).buffer(0.02).buffer(-0.02)
        if u.geom_type != "Polygon":
            u = max(u.geoms, key=lambda g: g.area)
        u = Polygon(u.exterior).simplify(0.03)
        if u.is_empty or u.area < 0.8 * fallback.area:
            return fallback
        return u
    except Exception:  # noqa: BLE001
        return fallback


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
    """Corner stones on BOTH faces of every outside corner: each course one
    mitred L-shaped block — a long arm on one face, a short one on the
    other, alternating up the corner (3.64.78: boxes along each side left
    one of the faces bare where the walls were not quite square)."""
    from shapely.geometry import Polygon as _Pg
    from . import modern as MD
    ring = poly.buffer(QUOIN_D, join_style=2, mitre_limit=3.0).difference(
        poly)
    out = []
    big = 1.5 * QUOIN_D          # the strips hold the ring's corner only
    for b, u1, u2 in _corners(poly):
        def strip(u, a0, a1):
            n = (-u[1], u[0])
            return _Pg([(b[0] + u[0] * a0 - n[0] * big,
                         b[1] + u[1] * a0 - n[1] * big),
                        (b[0] + u[0] * a1 - n[0] * big,
                         b[1] + u[1] * a1 - n[1] * big),
                        (b[0] + u[0] * a1 + n[0] * 0.01,
                         b[1] + u[1] * a1 + n[1] * 0.01),
                        (b[0] + u[0] * a0 + n[0] * 0.01,
                         b[1] + u[1] * a0 + n[1] * 0.01)])
        k, z = 0, z0 + 0.05
        shapes = {}
        while z + QUOIN_H <= z1 - 0.05:
            w1, w2 = QUOIN_W if k % 2 == 0 else QUOIN_W[::-1]
            key = (w1, w2)
            if key not in shapes:
                shapes[key] = ring.intersection(
                    strip(u1, -w1, QUOIN_D + 0.002).union(
                        strip(u2, -(QUOIN_D + 0.002), w2)))
            out += MD._solid(shapes[key], z, z + QUOIN_H - 0.03, col)
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
    # 3.64.123: the arch as the window is drawn (its rise and shape), not
    # always a semicircle — the ring sits on the frame's own edge
    from .engine import structure as S_
    rise = min(S_.head_size(o), zt - zs - 0.05) if arched else 0.0
    if arched and rise <= 0.02:
        arched = False
    zspr = zt - rise if arched else zt
    out = []
    sw = SURR_W * (1.6 if door else 1.0)
    # jambs
    out += _box(p0, u, nl, s0 - sw, s0, a0, a1, zs, zspr, trim)
    out += _box(p0, u, nl, s1, s1 + sw, a0, a1, zs, zspr, trim)
    if arched:
        cx = float(o["pos"])
        sty = o.get("arch") or "semi"
        inner = S_.arch_pts(s0, s1, zspr, zt, 16, sty)
        outer = S_.arch_pts(s0 - sw, s1 + sw, zspr, zt + sw, 16, sty)
        if len(inner) == len(outer) and len(inner) >= 3:
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


def _sconce(p, u, nl, sg, face, z, metal) -> list:
    """A modern wall light: a slim black cylinder casting up and down
    (its two warm glows)."""
    from .engine import walls as W
    q = (p[0] + nl[0] * sg * (face + 0.07), p[1] + nl[1] * sg * (face + 0.07))
    ring = [(q[0] + 0.05 * math.cos(2 * math.pi * k / 10),
             q[1] + 0.05 * math.sin(2 * math.pi * k / 10)) for k in range(10)]
    out = []
    for f in W.solid({"outer": ring, "holes": []}, z, z + 0.28):
        d = dict(f) if isinstance(f, dict) else {"loop": f, "holes": []}
        d["color"] = _c4(metal)
        out.append(d)
    glow = (1.0, 0.86, 0.55, 1.0)
    for z0, z1 in ((z + 0.28, z + 0.30), (z - 0.02, z)):
        for f in W.solid({"outer": ring, "holes": []}, z0, z1):
            d = dict(f) if isinstance(f, dict) else {"loop": f, "holes": []}
            d["color"] = glow
            out.append(d)
    return out


def _lantern(p, u, nl, sg, face, z, metal, kind="lantern") -> list:
    if kind == "sconce":
        return _sconce(p, u, nl, sg, face, z + 0.1, metal)
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
    if not look or look.get("style") in (None, "", "none"):
        return []
    on = (lambda k_: bool(look.get(k_, True)))   # 3.64.51: each its own
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
    from .lookstyle import is_look_roof
    roofed = {e["level"] for e in arch["structure"]
              if is_look_roof(e) and not e.get("annex")}
    for i, p in polys.items():
        z0 = el[i]
        z1 = z0 + float(levels[i]["height"])
        fs = []
        if i == g and on("plinth"):                  # the plinth
            fs += _ring(p, z0 - 0.35, z0 + PLINTH_H - 0.35, PLINTH_D, stone)
        nxt = [j for j in order if el[j] > z0 + 0.5]
        pb = None
        if nxt and on("bands"):                      # a floor band over it
            zb = el[nxt[0]]
            # 3.64.109: the floor slab's edge (a terrace slab with no walls
            # of its own too), never the walls' outline
            pb = _floor_outline(arch, levels[nxt[0]]["id"],
                                p if nxt[0] in polys else None)
        if pb is not None:
            # 3.64.108: the band's top at the floor finish's top, along
            # the floor slab's edge
            st_ = doc.get("settings") or {}
            ft_ = float(st_.get("finish_t", 0.0508) or 0.0) \
                if st_.get("finish_on", True) else 0.0
            try:
                zb += float(PJ.open_offset(doc, levels[nxt[0]]["id"]))
            except Exception:  # noqa: BLE001
                pass
            fs += _ring(pb, zb + ft_ - STRING_H, zb + ft_, STRING_D, trim)
        if levels[i]["id"] in roofed and on("cornice"):  # the eaves' cornice
            zc = z1
            for h_, d_ in CORNICE:
                fs += _ring(p, zc - h_, zc, d_, trim)
                zc -= h_ * 0.55
        if on("quoins") and look.get("quoins", True):
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
        if not on("surrounds"):
            if o["kind"] == "door" and i == g and float(o["w"]) >= 0.9 \
                    and (main is None or float(o["w"]) > float(main[1]["w"])):
                main = (w, o)
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
    # 3.64.47: the arcades' colonettes, the main door's tiled canopy
    try:
        fs = _colonettes(arch, ws, idx, el, polys, trim)
        if fs:
            out.append(("Look arcade colonettes", fs))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("ornament._colonettes")
    if main is not None and on("entrance_canopy") and not _covered(
            arch, main[0], main[1], polys[g], el, g):
        try:
            fs = _canopy(main[0], main[1], el[g], polys[g], trim)
            if fs:
                out.append(("Look entrance canopy", fs))
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("ornament._canopy")
    try:                         # 3.64.49: the front's extras
        fs = _front_extras(doc, arch, ws, idx, el, polys, g, outer, trim,
                           stone, metal, look)
        if fs:
            out.append(("Look front details", fs))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("ornament._front_extras")
    try:                         # 3.64.55: the styles' own elements
        from . import stylekit as SK
        out += SK.faces(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("stylekit.faces")
    try:                         # 3.64.53: the modern massing
        from . import modern as MD
        out += MD.faces(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("modern.faces")
    try:                         # 3.64.113: geometrical wall panels
        from . import wallpanels as WP
        out += WP.faces(doc)
        out += WP.arch_faces(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("wallpanels.faces")
    try:                         # 3.64.119: pergolas, louvers
        from . import elevparts as EP
        out += EP.faces(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("elevparts.faces")
    try:                         # 3.64.47: the front's main door
        from . import lookstyle as LS2
        _fr, fw, fo = LS2.front_side(doc, outer)
        if fw is not None:
            main = (fw, fo)
    except Exception:  # noqa: BLE001
        pass
    if main is not None and on("lanterns"):
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
                fs += _lantern(p, u, nl, sg, t / 2, el[g] + 2.1, metal,
                                look.get("light_style", "lantern"))
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


def classical_columns(doc, order="ionic") -> int:
    """The outside free-standing columns (a porch's, a veranda's) drawn
    classical: architectural, of the order given. How many."""
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
        if c.get("astyle") != order:
            c["role"] = "architectural"
            c["astyle"] = order
            n += 1
    return n


def _side(w, o, poly):
    """(seg, u, nl, sg, face) of an opening's wall: sg = +1 when its
    outside is on nl's side."""
    from shapely.geometry import Point
    from .engine import walls as W
    seg = W.centre(w)
    if seg.kind != "line":
        return None
    t = float(w["t"])
    u = seg.u
    nl = (-u[1], u[0])
    c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
    probe = (c[0] + nl[0] * (t / 2 + 0.25), c[1] + nl[1] * (t / 2 + 0.25))
    sg = -1.0 if poly.buffer(-0.05).contains(Point(probe)) else 1.0
    return seg, u, nl, sg, t / 2


def _colonettes(arch, ws, idx, el, polys, trim) -> list:
    """A slim column (base, round shaft, capital) in each pier of an
    arcade, standing proud of the wall's face."""
    from .engine import walls as W
    groups_ = {}
    for o in arch["openings"]:
        if o.get("arcade") and o["wall"] in ws:
            groups_.setdefault((o["wall"], o["arcade"]), []).append(o)
    out = []
    for (wid, _tag), ops in groups_.items():
        w = ws[wid]
        i = idx.get(w["level"])
        if i not in polys or len(ops) < 2:
            continue
        ops.sort(key=lambda o: float(o["pos"]))
        sd = _side(w, ops[0], polys[i])
        if sd is None:
            continue
        seg, u, nl, sg, face = sd
        z0 = el[i]
        piers = [(float(a["pos"]) + float(a["w"]) / 2 +
                  float(b["pos"]) - float(b["w"]) / 2) / 2
                 for a, b in zip(ops, ops[1:])]
        # and the two ends
        piers = [float(ops[0]["pos"]) - float(ops[0]["w"]) / 2 - 0.12] + \
            piers + [float(ops[-1]["pos"]) + float(ops[-1]["w"]) / 2 + 0.12]
        o0 = ops[0]
        zs = z0 + float(o0.get("sill", 0.0) or 0.0)
        zspr = zs + float(o0["h"]) - float(o0["w"]) / 2
        r = 0.075
        for s_ in piers:
            c = seg.at(s_ / max(seg.L, 1e-9))
            cc = (c[0] + nl[0] * sg * (face + r + 0.01),
                  c[1] + nl[1] * sg * (face + r + 0.01))
            ring = [(cc[0] + r * math.cos(2 * math.pi * k / 12),
                     cc[1] + r * math.sin(2 * math.pi * k / 12))
                    for k in range(12)]
            for f in W.solid({"outer": ring, "holes": []}, zs + 0.12,
                             zspr - 0.14):
                d = dict(f) if isinstance(f, dict) else {"loop": f,
                                                         "holes": []}
                d["color"] = trim
                out.append(d)
            cb = (c[0], c[1])
            a0, a1 = (face, face + 2 * r + 0.04) if sg > 0 else \
                (-face - 2 * r - 0.04, -face)
            out += _box(seg.p0, u, nl, s_ - r - 0.03, s_ + r + 0.03, a0, a1,
                        zs, zs + 0.12, trim)                  # its base
            out += _box(seg.p0, u, nl, s_ - r - 0.05, s_ + r + 0.05, a0,
                        a1 + (0.02 if sg > 0 else 0.0), zspr - 0.14, zspr,
                        trim)                                 # its capital
            del cb
        # one sill along the whole arcade
        b0, b1 = (face, face + SILL_D) if sg > 0 else (-face - SILL_D, -face)
        if zs > z0 + 0.1:
            out += _box(seg.p0, u, nl, piers[0] - 0.15, piers[-1] + 0.15,
                        b0, b1, zs - SILL_H, zs, trim)
    return out


def _canopy(w, o, z0, poly, trim) -> list:
    """A small clay-tile hip roof over the main door on two stone
    corbels — the perspective's entrance canopy."""
    from .engine import structure as S
    sd = _side(w, o, poly)
    if sd is None:
        return []
    seg, u, nl, sg, face = sd
    half = float(o["w"]) / 2 + 0.55
    depth = 1.05
    s0 = float(o["pos"]) - half
    s1 = float(o["pos"]) + half
    base = z0 + float(o.get("sill", 0.0) or 0.0) + float(o["h"]) + 0.42

    def P(s_, a_):
        a_ = a_ * sg
        return [round(seg.p0[0] + u[0] * s_ + nl[0] * a_, 4),
                round(seg.p0[1] + u[1] * s_ + nl[1] * a_, 4)]
    corners = [P(s0, face), P(s1, face), P(s1, face + depth),
               P(s0, face + depth)]
    r = {"type": "roof", "kind": "hip", "corners": corners, "slope": 25.0,
         "overhang": 0.08, "t": 0.10, "ridge": "long"}
    out = []
    for f in S.roof_faces(r, base):
        d = dict(f) if isinstance(f, dict) else {"loop": f, "holes": []}
        out.append(d)
    # its fascia / soffit board and two corbels under its front corners
    a0, a1 = (face, face + depth) if sg > 0 else (-face - depth, -face)
    out += _box(seg.p0, u, nl, s0, s1, a0, a1, base - 0.12, base, trim)
    c0, c1 = (face, face + 0.40) if sg > 0 else (-face - 0.40, -face)
    for s_ in (s0 + 0.12, s1 - 0.12):
        out += _box(seg.p0, u, nl, s_ - 0.09, s_ + 0.09, c0, c1,
                    base - 0.45, base - 0.12, trim)
    return out


def _covered(arch, w, o, poly, el, g) -> bool:
    """The door stands under a floor or slab above (a veranda, a porch):
    no canopy of its own."""
    from shapely.geometry import Point, Polygon
    sd = _side(w, o, poly)
    if sd is None:
        return True
    seg, u, nl, sg, face = sd
    c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
    p = Point(c[0] + nl[0] * sg * (face + 0.6), c[1] + nl[1] * sg *
              (face + 0.6))
    ids = {lv["id"] for i, lv in enumerate(arch["levels"])
           if el[i] > el[g] + 0.5}
    for e in arch["structure"]:
        if e["type"] == "slab" and (e["level"] in ids or (
                e["level"] == arch["levels"][g]["id"] and e.get("roof"))):
            try:
                if Polygon(e["corners"]).buffer(0).contains(p):
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


def _disc(p0, u, nl, s_, zc, r, a0, a1, col, n=18) -> list:
    """A round boss on a wall's face (s_ along it, zc its centre)."""
    quad = [(s_ + r * math.cos(2 * math.pi * k / n),
             zc + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    return _prism(p0, u, nl, quad, a0, a1, col)


def _front_extras(doc, arch, ws, idx, el, polys, g, outer, trim, stone,
                  metal, look) -> list:
    """The front's details: corbels under its balconies and terraces, a
    clay-tile pent roof along a terrace over the car porch, a medallion on
    each blank stretch of its upper walls, lanterns beside its windows."""
    from shapely.geometry import LineString, Point
    from . import lookstyle as LS
    from .engine import walls as W
    fr, _w, _o = LS.front_side(doc, outer)
    if fr is None:
        return []
    levels = arch["levels"]
    gid = levels[g]["id"]
    roof_c = _c4(look.get("roof_c") or (look.get("roof") if isinstance(
        look.get("roof"), list) else None) or (0.75, 0.40, 0.28))
    out = []
    # the ground floor's walls (to know what stands under a terrace)
    lo_walls = [LineString([w["a"][:2], w["b"][:2]]).buffer(
        float(w["t"]) / 2 + 0.15) for w in arch["walls"]
        if w["level"] == gid and "a" in w and not w.get("rail")]
    for w in arch["walls"]:
        if not w.get("rail") or w["level"] == gid or "a" in w and False:
            continue
        i = idx.get(w["level"])
        if i is None:
            continue
        seg = W.centre(w)
        if seg.kind != "line" or seg.L < 1.0:
            continue
        u = seg.u
        nl = (-u[1], u[0])
        if abs(nl[0] * fr[0] + nl[1] * fr[1]) < 0.85:
            continue
        sg = 1.0 if nl[0] * fr[0] + nl[1] * fr[1] > 0 else -1.0
        zf = el[i]
        # corbels under the slab's edge, every 1.2 m
        k = max(2, int(seg.L / 1.2) + 1) if look.get("corbels", True) else 0
        for j in range(k):
            s_ = 0.25 + (seg.L - 0.5) * j / (k - 1)
            a0, a1 = (-0.45, 0.0) if sg > 0 else (0.0, 0.45)
            out += _box(seg.p0, u, nl, s_ - 0.09, s_ + 0.09, a0, a1,
                        zf - 0.55, zf - 0.12, trim)
            out += _box(seg.p0, u, nl, s_ - 0.11, s_ + 0.11,
                        a0 - (0.02 if sg > 0 else 0.0),
                        a1 + (0.0 if sg > 0 else 0.02), zf - 0.12,
                        zf - 0.08, trim)
        # over the car porch (nothing under it): a tile pent roof along it
        mid = seg.at(0.5)
        under = any(p_.contains(Point(mid)) for p_ in lo_walls)
        if not under and look.get("porch_canopy", True):
            d_ = 0.85
            z_hi, z_lo = zf + 0.35, zf - 0.20
            a_in, a_out = 0.0, d_
            # (s, a) in the wall's frame, a outwards along fr
            P = (lambda s__, a__, z__: (seg.p0[0] + u[0] * s__ + nl[0] *
                                        sg * a__,
                                        seg.p0[1] + u[1] * s__ + nl[1] *
                                        sg * a__, z__))
            s0, s1 = -0.15, seg.L + 0.15
            top = [P(s0, a_in, z_hi), P(s1, a_in, z_hi),
                   P(s1, a_out, z_lo), P(s0, a_out, z_lo)]
            bot = [P(s0, a_in, z_hi - 0.08), P(s0, a_out, z_lo - 0.08),
                   P(s1, a_out, z_lo - 0.08), P(s1, a_in, z_hi - 0.08)]
            if sg < 0:
                top, bot = list(reversed(top)), list(reversed(bot))
            out.append({"loop": top, "holes": [], "color": roof_c})
            out.append({"loop": bot, "holes": [], "color": roof_c})
            # the tiles' courses (ridges every 0.25 m) and a fascia
            n_ = int((s1 - s0) / 0.25)
            for j in range(n_ + 1):
                s_ = s0 + j * (s1 - s0) / max(n_, 1)
                ridge = [P(s_ - 0.04, a_in, z_hi + 0.04),
                         P(s_ + 0.04, a_in, z_hi + 0.04),
                         P(s_ + 0.04, a_out, z_lo + 0.04),
                         P(s_ - 0.04, a_out, z_lo + 0.04)]
                out.append({"loop": ridge if sg > 0 else
                            list(reversed(ridge)), "holes": [],
                            "color": roof_c})
            a0, a1 = (a_out - 0.04, a_out + 0.02)
            out += _box(seg.p0, u, nl, s0, s1,
                        *((a0, a1) if sg > 0 else (-a1, -a0)),
                        z_lo - 0.22, z_lo - 0.06, trim)
    # medallions on the blank stretches of the front's upper walls,
    # lanterns beside its windows
    ops_by = {}
    for o in arch["openings"]:
        ops_by.setdefault(o["wall"], []).append(o)
    for w in arch["walls"]:
        if w["id"] not in outer or w.get("rail") or str(
                w.get("name", "")).lower().startswith("corner"):
            continue
        i = idx.get(w["level"])
        if i not in polys:
            continue
        seg = W.centre(w)
        if seg.kind != "line" or seg.L < 1.2:
            continue
        nl = (-seg.u[1], seg.u[0])
        if abs(nl[0] * fr[0] + nl[1] * fr[1]) < 0.85:
            continue
        probe = seg.at(0.5)
        t = float(w["t"])
        pr = (probe[0] + nl[0] * (t / 2 + 0.25),
              probe[1] + nl[1] * (t / 2 + 0.25))
        sg = -1.0 if polys[i].buffer(-0.05).contains(Point(pr)) else 1.0
        face = t / 2
        a0, a1 = (face, face + 0.04) if sg > 0 else (-face - 0.04, -face)
        b0, b1 = (face, face + 0.08) if sg > 0 else (-face - 0.08, -face)
        zf = el[i]
        h = float(levels[i]["height"])
        ops = ops_by.get(w["id"], [])
        if not ops and seg.L >= 1.6 and look.get("lanterns", True) and \
                look.get("light_style") == "sconce":
            for s_ in (seg.L / 2 - 0.6, seg.L / 2, seg.L / 2 + 0.6):
                p = seg.at(s_ / seg.L)
                out += _sconce(p, seg.u, nl, sg, face, zf + h * 0.62,
                               metal)
        if not ops and i != g and seg.L >= 1.6 and \
                look.get("medallions", True):
            sc = seg.L / 2
            zc = zf + h * 0.55
            out += _disc(seg.p0, seg.u, nl, sc, zc, 0.46, a0, a1, trim)
            for dx, dz in ((0.36, 0), (-0.36, 0), (0, 0.36), (0, -0.36)):
                out += _disc(seg.p0, seg.u, nl, sc + dx, zc + dz, 0.2, a0,
                             b1 if sg > 0 else a1, trim)
            out += _disc(seg.p0, seg.u, nl, sc, zc, 0.26, b0, b1, stone)
        for o in ops:
            if o["kind"] != "window" or float(o["w"]) < 1.0 or \
                    o.get("arcade") or not look.get("lanterns", True):
                continue
            zt = zf + float(o.get("sill", 0.0) or 0.0) + float(o["h"])
            for s_ in (float(o["pos"]) - float(o["w"]) / 2 - 0.42,
                       float(o["pos"]) + float(o["w"]) / 2 + 0.42):
                if 0.2 < s_ < seg.L - 0.2:
                    p = seg.at(s_ / seg.L)
                    out += _lantern(p, seg.u, nl, sg, face, zt - 0.75,
                                    metal, look.get("light_style",
                                                    "lantern"))
    return out
