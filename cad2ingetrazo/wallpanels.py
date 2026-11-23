"""3.64.113: geometrical panels on the external walls — a raised pattern
(diamonds, squares, hexagons, triangles, a diamond lattice) over the
blank stretches of every outside wall, kept clear of the windows and
doors, the corners and the floor bands. Part of the elevation design
(``doc["look"]``: ``geo_panel``, ``geo_where``, ``geo_size``); drawn again
at every rebuild, so it follows the plans (ornament.faces)."""
from __future__ import annotations

import math

PATTERNS = [("none", "None"),
            ("diamonds", "Diamonds (raised rhombi)"),
            ("squares", "Squares (raised tiles)"),
            ("hexagons", "Hexagons (honeycomb)"),
            ("triangles", "Triangles (alternating)"),
            ("lattice", "Diamond lattice (raised bars)")]
WHERE = [("front", "Front elevation only"),
         ("all", "Every outside wall")]
DEPTH = 0.035
MAX_TILES = 9000


def _cells(kind, c, s0, s1, z0, z1):
    """Convex tiles [(s, z), …] over the box, cell size ``c``."""
    out = []
    if kind == "squares":
        h = c * 0.40
        i = 0
        s = s0 + c / 2
        while s < s1:
            z = z0 + c / 2
            while z < z1:
                out.append([(s - h, z - h), (s + h, z - h), (s + h, z + h),
                            (s - h, z + h)])
                z += c
            s += c
            i += 1
    elif kind == "diamonds":
        h = c * 0.92
        ni = int((s1 - s0) / c) + 3
        nj = int((z1 - z0) / c) + 3
        for i in range(-1, ni):
            for j in range(-1, nj):
                if (i + j) % 2:
                    continue
                s, z = s0 + c / 2 + i * c, z0 + c / 2 + j * c
                out.append([(s - h, z), (s, z - h), (s + h, z), (s, z + h)])
    elif kind == "hexagons":
        r = c * 0.52
        dx, dy = 1.5 * r * 1.04, math.sqrt(3) * r * 1.04
        i = 0
        s = s0 + r
        while s < s1:
            z = z0 + dy / 2 + (dy / 2 if i % 2 else 0.0)
            while z < z1:
                out.append([(s + r * 0.92 * math.cos(math.radians(a)),
                             z + r * 0.92 * math.sin(math.radians(a)))
                            for a in range(0, 360, 60)])
                z += dy
            s += dx
            i += 1
    elif kind == "triangles":
        w, h = c, c * 0.866
        nj = int((z1 - z0) / h) + 2
        ni = int((s1 - s0) / w) + 2
        k = 0.86
        for j in range(nj):
            for i in range(ni):
                s, z = s0 + i * w, z0 + j * h
                up = [(s, z), (s + w, z), (s + w / 2, z + h)]
                dn = [(s + w / 2, z + h), (s + w * 1.5, z + h),
                      (s + w, z)]
                for tri in (up, dn):
                    cx = sum(p[0] for p in tri) / 3
                    cz = sum(p[1] for p in tri) / 3
                    out.append([(cx + (p[0] - cx) * k, cz + (p[1] - cz) * k)
                                for p in tri])
    return out


def _lattice(c, s0, s1, z0, z1):
    """Diagonal bars both ways (a shapely geometry in (s, z))."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    lines = []
    k = -(z1 - z0)
    while k < (s1 - s0) + c:
        lines.append(LineString([(s0 + k, z0), (s0 + k + (z1 - z0), z1)]))
        lines.append(LineString([(s0 + k, z1), (s0 + k + (z1 - z0), z0)]))
        k += c
    return unary_union([ln.buffer(0.018, cap_style=2) for ln in lines])


def _openings(arch, levels, i, p, q, u, n, recs=False):
    """The openings in the walls along an edge, as (s0, s1, z0, z1) boxes
    (z from the level's floor); a corner window's legs full height."""
    from shapely.geometry import LineString

    from .engine import walls as W
    ln = LineString([p, q])
    ws = {w["id"]: w for w in arch["walls"]}
    lid = levels[i]["id"]
    out = []
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or "a" not in w or w["level"] != lid:
            continue
        m = LineString([w["a"][:2], w["b"][:2]])
        if ln.distance(m.interpolate(0.5, True)) > float(w["t"]) + 0.3:
            continue
        seg = W.centre(w)
        if seg.kind != "line":
            continue
        c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
        s = (c[0] - p[0]) * u[0] + (c[1] - p[1]) * u[1]
        hw = float(o["w"]) / 2
        sill = float(o.get("sill", 0.0) or 0.0)
        out.append((s - hw, s + hw, sill, sill + float(o.get("h", 2.1)))
                   + ((o,) if recs else ()))
    for w in arch["walls"]:
        if "a" not in w or w["level"] != lid or not str(
                w.get("name", "")).lower().startswith("corner window"):
            continue
        m = LineString([w["a"][:2], w["b"][:2]])
        if ln.distance(m.interpolate(0.5, True)) > float(w["t"]) + 0.3:
            continue
        sa = [(x - p[0]) * u[0] + (y - p[1]) * u[1]
              for x, y in (w["a"][:2], w["b"][:2])]
        out.append((min(sa) - 0.1, max(sa) + 0.1, 0.0, 99.0)
                   + ((None,) if recs else ()))
    return out


def faces(doc) -> list:
    """[(name, faces)] — the panels, level by level."""
    look = doc.get("look") or {}
    kind = look.get("geo_panel") or "none"
    if kind in ("none", "") or look.get("style") in (None, "", "none"):
        return []
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    from . import lookstyle as LS
    from . import modern as MD
    arch, levels, el, order, g, polys = MD._ctx(doc)
    clad = MD._c4(look.get("clad"), (0.80, 0.80, 0.78))
    c = min(max(float(look.get("geo_size", 0.30) or 0.30), 0.12), 1.0)
    fr_dir = None
    if look.get("geo_where", "front") == "front":
        try:
            fr_dir, _w, _o = LS.front_side(doc, LS._outer_walls(arch))
        except Exception:  # noqa: BLE001
            fr_dir = None
        if fr_dir is None:
            return []
    out, budget = [], MAX_TILES
    for i, poly in polys.items():
        fs = []
        h_lv = float(levels[i]["height"])
        z_lo = el[i] + (0.60 if i == g else 0.40)
        z_hi = el[i] + h_lv - 0.40
        if z_hi - z_lo < 0.8:
            continue
        for p, q, u, n, L in MD._edges(poly):
            if L < 1.2:
                continue
            if fr_dir is not None and n[0] * fr_dir[0] + n[1] * fr_dir[1] \
                    < 0.85:
                continue
            fr = MD._Frame(p, u, n)
            free = box(0.45, z_lo, L - 0.45, z_hi)
            holes = [box(a - 0.30, el[i] + z0 - 0.30, b + 0.30,
                         el[i] + z1 + 0.30)
                     for a, b, z0, z1 in _openings(arch, levels, i, p, q, u,
                                                   n)]
            if holes:
                free = free.difference(unary_union(holes))
            free = free.buffer(-0.10, join_style=2)
            if free.is_empty:
                continue
            for part in getattr(free, "geoms", [free]):
                if part.geom_type != "Polygon" or part.area < 0.5:
                    continue
                s0, z0_, s1, z1_ = part.bounds
                if s1 - s0 < 0.6 or z1_ - z0_ < 0.6:
                    continue
                if kind == "lattice":
                    lat = _lattice(c, s0, s1, z0_, z1_).intersection(part)
                    for pg in getattr(lat, "geoms", [lat]):
                        if pg.geom_type == "Polygon" and pg.area > 1e-3:
                            fs += fr.holed(pg, -0.005, DEPTH, clad)
                            budget -= 8
                    continue
                for tile in _cells(kind, c, s0, s1, z0_, z1_):
                    if budget <= 0:
                        break
                    if not part.contains(Polygon(tile)):
                        continue
                    fs += fr.plate(tile, -0.005, DEPTH, clad)
                    budget -= 1
        if fs:
            out.append((f"Look geometric panels · {levels[i]['name']}", fs))
    return out


def _arch_shape(sc, w, z0, z1, arched):
    """The opening's outline in (s, z): a rectangle, with a semicircular
    (a pointed-horseshoe look: slightly wider) head when arched."""
    from shapely.geometry import Point, box
    hw = w / 2
    if not arched or z1 - z0 < w * 0.75:
        return box(sc - hw, z0, sc + hw, z1)
    zc = z1 - hw
    return box(sc - hw, z0, sc + hw, zc).union(
        Point(sc, zc).buffer(hw, 24).intersection(
            box(sc - hw * 1.2, zc - 0.05, sc + hw * 1.2, z1 + 0.5)))


def arch_faces(doc) -> list:
    """3.64.114: a carved panel round each big arched door / window
    (Moorish / Gulf villas): a raised frame, a band of diamond relief in
    it, the opening's arch kept clear."""
    look = doc.get("look") or {}
    if not look.get("arch_panels") or look.get("style") in (None, "", "none"):
        return []
    from shapely.geometry import Polygon, box

    from . import lookstyle as LS
    from . import modern as MD
    arch, levels, el, order, g, polys = MD._ctx(doc)
    trim = MD._c4(look.get("trim"), (0.93, 0.90, 0.84))
    fr_dir = None
    if look.get("geo_where", "front") == "front":
        try:
            fr_dir, _w, _o = LS.front_side(doc, LS._outer_walls(arch))
        except Exception:  # noqa: BLE001
            fr_dir = None
        if fr_dir is None:
            return []
    out = []
    for i, poly in polys.items():
        fs = []
        h_lv = float(levels[i]["height"])
        base = el[i] + (0.60 if i == g else 0.25)
        top_max = el[i] + h_lv - 0.30
        for p, q, u, n, L in MD._edges(poly):
            if L < 1.2:
                continue
            if fr_dir is not None and n[0] * fr_dir[0] + n[1] * fr_dir[1] \
                    < 0.85:
                continue
            fr = MD._Frame(p, u, n)
            ops = _openings(arch, levels, i, p, q, u, n, recs=True)
            for a, b, z0, z1, o in ops:
                if o is None or b - a < 0.9:
                    continue
                arched = (o.get("head") == "arch") or \
                    (o.get("kind") == "door" and look.get("door_arch"))
                if not arched:
                    continue
                sc, w = (a + b) / 2, b - a
                zb = max(el[i] + z0 - 0.30, base)
                zt = min(el[i] + z1 + 0.55, top_max)
                if zt - zb < w * 0.9:
                    continue
                m_ = min(0.55, a - 0.12, L - 0.12 - b)   # (at a corner: less)
                if m_ < 0.25:
                    continue
                rect = box(sc - w / 2 - m_, zb, sc + w / 2 + m_, zt)
                if any(o2 is not o and not (b2 + 0.15 < rect.bounds[0] or
                                            a2 - 0.15 > rect.bounds[2]) and
                       z1_ > zb and z0_ + el[i] < zt
                       for a2, b2, z0_, z1_, o2 in ops
                       for z1_ in [el[i] + z1_]):
                    continue
                hole = _arch_shape(sc, w, el[i] + z0, el[i] + z1, True)
                frame = rect.difference(hole.buffer(0.04))
                fs += fr.holed(frame, -0.005, 0.03, trim)
                ring = rect.buffer(-0.07).difference(hole.buffer(0.10))
                tiles = 0
                for part in getattr(ring, "geoms", [ring]):
                    if part.geom_type != "Polygon" or part.area < 0.02:
                        continue
                    s0, z0_, s1, z1_ = part.bounds
                    for tile in _cells("diamonds", 0.16, s0, s1, z0_, z1_):
                        if tiles > 400:
                            break
                        if part.contains(Polygon(tile)):
                            fs += fr.plate(tile, 0.03, 0.055, trim)
                            tiles += 1
        if fs:
            out.append((f"Look arch panels · {levels[i]['name']}", fs))
    return out
