# SPDX-License-Identifier: GPL-3.0-or-later
"""Landscape (soft) areas from a CAD plan: closed outlines on landscape
layers (LANDSCAPE, LAWN, GRASS, GREEN, PLANT…) and the area the drawing's
lines close round a «LANDSCAPE» / «LAWN» / «GARDEN» text — laid in green
on the floor (3D and the plans)."""
from __future__ import annotations

import math
import re

LAYER_RX = re.compile(r"LANDSC|L-PLNT|PLANT|LAWN|GRASS|TURF|GREEN|GARDEN|"
                      r"HEDGE|SHRUB|SOFT.?SCAPE|VERDE|JARDIN|CESPED", re.I)
TEXT_RX = re.compile(r"LANDSCAP|LAWN|GARDEN|GREEN\s*AREA|GRASS|PLANTER|"
                     r"JARDIN|SOFT\s*SCAPE", re.I)
GREEN = (0.42, 0.66, 0.30, 1.0)
#: 3.64.4: a hatch the plan fills a lawn with (AutoCAD's GRASS…)
PATTERN_RX = re.compile(r"GRASS|TURF|LAWN|GRAVEL|EARTH|SWAMP", re.I)
#: the lawn's grass, IngeTrazo's library (the first there)
GRASS_KEYS = ("ground/grass_lawn.png", "floor/grass.jpg", "ground/grass.png",
              "floor/grass_2.jpg")


def areas(pl, reach=(7.0, 25.0), least=0.8, most=4000.0) -> list:
    """Outlines (lists of (x, y)) of the landscape areas of a placed
    drawing (metres)."""
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import polygonize, unary_union
    lay = pl["layers"]
    out = []
    for lp in pl["loops"]:
        if LAYER_RX.search(lp["layer"] or "") and len(lp["pts"]) >= 3:
            g = Polygon(lp["pts"])
            if g.is_valid and least <= g.area <= most:
                out.append(g)
    # the plan's lawn hatches (a GRASS pattern, or any hatch on a
    # landscape layer): each hatch's outline
    for fl in pl.get("fills") or ():
        pat = str(fl.get("pattern") or "")
        if fl.get("solid") or not (PATTERN_RX.search(pat) or (
                LAYER_RX.search(str(fl.get("layer") or "")) and
                not re.search(r"ANSI|SOLID", pat, re.I))):
            continue
        pts = fl.get("pts") or []
        if len(pts) < 3:
            continue
        try:
            g = Polygon(pts).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if not g.is_empty and g.area >= 0.05:
            out.append(g)
    words = [t for t in pl["texts"] if TEXT_RX.search(t["text"] or "")]
    if words:
        import numpy as np
        S = np.array([s[:4] for s in pl["segs"]], dtype=float) \
            if pl["segs"] else np.zeros((0, 4))
        for t in words:
            p = Point(t["x"], t["y"])
            if any(g.contains(p) for g in out):
                continue
            for r_ in reach:              # a small window first, then wider
                f = _around(pl, S, lay, p, r_, least, most)
                if f is not None:
                    out.append(f)
                    break
    if not out:
        return []
    # (hatch pieces drawn edge to edge: joined, the hairline gaps closed)
    u = unary_union([g.buffer(0.01, join_style=2) for g in out]).buffer(
        -0.01, join_style=2)
    res = []
    gs_ = []
    for g in getattr(u, "geoms", [u]):
        gs_ += _no_holes(g) if g.geom_type == "Polygon" else []
    for g in gs_:
        if g.geom_type == "Polygon" and g.area >= min(least, 0.3):
            res.append([(round(a, 4), round(b, 4))
                        for a, b in list(g.simplify(0.01).exterior.coords)[:-1]])
    return res


def _no_holes(g) -> list:
    """A polygon with holes (a lawn round a building, round its stones)
    cut into pieces without any: across each hole's middle, line by line
    (the outlines keep no holes)."""
    from shapely.geometry import LineString
    from shapely.ops import split
    todo, out = [g], []
    guard = 0
    while todo and guard < 400:
        guard += 1
        q = todo.pop()
        if q.geom_type != "Polygon" or q.is_empty:
            continue
        if not q.interiors:
            out.append(q)
            continue
        c = q.interiors[0].centroid
        b = q.bounds
        try:
            parts = split(q, LineString([(c.x, b[1] - 1), (c.x, b[3] + 1)]))
            ps = [p for p in getattr(parts, "geoms", [parts])
                  if p.geom_type == "Polygon"]
        except Exception:  # noqa: BLE001
            ps = []
        if len(ps) < 2:
            out.append(q)          # (could not cut: as it is)
            continue
        todo += ps
    return out


def _around(pl, S, lay, p, reach, least, most):
    """The smallest area the lines close round point p, within reach."""
    import numpy as np
    from shapely.geometry import LineString, box
    from shapely.ops import polygonize, unary_union
    if True:
        if True:
            x, y = p.x, p.y
            m = ((np.minimum(S[:, 0], S[:, 2]) <= x + reach)
                 & (np.maximum(S[:, 0], S[:, 2]) >= x - reach)
                 & (np.minimum(S[:, 1], S[:, 3]) <= y + reach)
                 & (np.maximum(S[:, 1], S[:, 3]) >= y - reach))
            # lines on text / dimension layers close nothing
            lines = [LineString([(a, b), (c, d)])
                     for (a, b, c, d), li in zip(S[m], np.nonzero(m)[0])
                     if math.hypot(c - a, d - b) > 1e-4
                     and not re.search(r"TEXT|DIM|ANNO|HATCH",
                                       lay[pl["segs"][li][4]], re.I)]
            if not lines:
                return None
            frame = box(x - reach, y - reach, x + reach, y + reach)
            faces = [f for f in polygonize(unary_union(lines + [frame.exterior]))
                     if f.contains(p) and least <= f.area <= most]
            if faces:
                f = min(faces, key=lambda g: g.area)
                if f.buffer(-1e-3).within(frame.buffer(-0.01)):
                    return f
            return None


def faces(outline, z) -> list:
    """A green surface (facing up) over an outline, at z."""
    pts = [tuple(p) for p in outline]
    a2 = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1]))
    if a2 < 0:
        pts = pts[::-1]
    return [{"loop": [(p[0], p[1], z) for p in pts], "holes": [],
             "color": GREEN}]


PAVER_LAYER_RX = re.compile(r"HATCH|PAV|STONE|STEP|TILE|PATH|WALKWAY", re.I)


def pavers(pl, lawns) -> list:
    """The stepping stones / pavers the plan draws in its lawns: closed
    outlines (0.05–3 m², on a hatch / paving layer) inside them."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if not lawns:
        return []
    L = unary_union([Polygon(a).buffer(0) for a in lawns]).buffer(0.05)
    out = []
    for lp in pl.get("loops") or ():
        if not PAVER_LAYER_RX.search(str(lp.get("layer") or "")) or \
                LAYER_RX.search(str(lp.get("layer") or "")) or \
                len(lp.get("pts") or ()) < 3:
            continue
        try:
            g = Polygon(lp["pts"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if g.is_empty or not (0.05 <= g.area <= 3.0) or not L.contains(g):
            continue
        out.append([(round(a, 4), round(b, 4))
                    for a, b in list(g.exterior.coords)[:-1]])
    return out
