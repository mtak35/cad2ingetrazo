# SPDX-License-Identifier: GPL-3.0-or-later
"""A floor's walls as ONE solid, the CAD plan's own outline: the wall
bands the CAD's wall lines close round (each wall's pieces where the CAD
has none), merged — no joint where two walls meet, no step where the
pairing of the lines read two thicknesses — then cut by the doors and
windows (each long face one face with its openings out of it, the
openings' jambs, sills and heads).

``cad_region`` is worked out when a floor is read from the CAD (kept in
``doc["wall_outline"][level]``); ``merged_faces`` builds the solid.
"""
from __future__ import annotations

import math


def cad_region(segs, model_polys) -> list:
    """The CAD's wall bands — the cells its wall lines close round that
    the walls read from it cover — as [[outer, hole, …], …] (plan
    coordinates)."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    if not segs or not model_polys:
        return []
    lines = []
    for s in segs:
        if math.dist((s[0], s[1]), (s[2], s[3])) > 0.005:
            lines.append(LineString([(s[0], s[1]), (s[2], s[3])]))
    if not lines:
        return []
    try:
        noded = unary_union(lines)
        cells = list(polygonize(noded))
    except Exception:  # noqa: BLE001
        return []
    U = unary_union(model_polys)
    Ub = U.buffer(0.05)
    keep = []
    for c in cells:
        if c.area < 0.002 or c.area > 40.0:
            continue
        try:
            if c.intersection(Ub).area >= 0.6 * c.area and \
                    not c.buffer(-0.35).area > 0.25 * c.area:
                keep.append(c)
        except Exception:  # noqa: BLE001
            continue
    if not keep:
        return []
    R = unary_union(keep).buffer(0.002, join_style=2).buffer(
        -0.002, join_style=2)
    out = []
    for g in getattr(R, "geoms", [R]):
        if g.geom_type != "Polygon" or g.area < 0.01:
            continue
        g = g.simplify(0.002)
        out.append([[[round(x, 4), round(y, 4)] for x, y in
                     list(g.exterior.coords)[:-1]]] +
                   [[[round(x, 4), round(y, 4)] for x, y in
                     list(r.coords)[:-1]] for r in g.interiors])
    return out


def region_of(stored):
    """The stored outline as a shapely shape, or None."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    ps = []
    for p in stored or []:
        try:
            ps.append(Polygon(p[0], p[1:]).buffer(0))
        except Exception:  # noqa: BLE001
            continue
    return unary_union(ps) if ps else None


def merged_faces(U, fps, b, top) -> list:
    """Faces of the plan shape ``U`` raised from ``b`` to ``top``, cut by
    the openings ``fps`` = [(footprint polygon, zs, zt)]."""
    from shapely.geometry import LineString, box
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    eps = 1e-4
    faces = []
    cuts = []
    for fp, zs, zt in fps:
        zs = max(b, zs)
        zt = min(top, zt)
        if zt - zs < 0.01:
            continue
        g = fp.intersection(U)
        if g.is_empty or g.area < 1e-5:
            continue
        cuts.append((g, zs, zt))

    def ring_faces(ring, outward_ccw):
        cs = list(ring.coords)[:-1]
        n_ = len(cs)
        for i in range(n_):
            p, q = cs[i], cs[(i + 1) % n_]
            L = math.dist(p, q)
            if L < 1e-6:
                continue
            d = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
            edge = LineString([p, q])
            holes = []
            for g, zs, zt in cuts:
                try:
                    x = edge.intersection(g.buffer(1e-4))
                except Exception:  # noqa: BLE001
                    continue
                if x.is_empty or x.length < 0.005:
                    continue
                ts = [((c[0] - p[0]) * d[0] + (c[1] - p[1]) * d[1])
                      for gg in getattr(x, "geoms", [x])
                      for c in gg.coords]
                t0, t1 = max(min(ts), 0.0), min(max(ts), L)
                if t1 - t0 < 0.005:
                    continue
                holes.append(box(t0, zs - (eps if zs <= b + eps else 0),
                                 t1, zt + (eps if zt >= top - eps else 0)))
            region = box(0, b, L, top)
            if holes:
                region = region.difference(unary_union(holes))
            for g in getattr(region, "geoms", [region]):
                if g.is_empty or g.area < 1e-8 or g.geom_type != "Polygon":
                    continue
                g = orient(g, 1.0)

                def P3(tz, p=p, d=d):
                    return (p[0] + d[0] * tz[0], p[1] + d[1] * tz[0], tz[1])
                faces.append({"loop": [P3(c) for c in
                                       list(g.exterior.coords)[:-1]],
                              "holes": [[P3(c) for c in list(r.coords)[:-1]]
                                        for r in g.interiors]})

    for poly in getattr(U, "geoms", [U]):
        if poly.geom_type != "Polygon" or poly.area < 1e-5:
            continue
        poly = orient(poly, 1.0)          # outer CCW, holes CW: outward
        ring_faces(poly.exterior, True)
        for r in poly.interiors:
            ring_faces(r, False)
        # top and bottom, less what the openings reaching them take
        tcut = [g for g, zs, zt in cuts if zt >= top - eps]
        bcut = [g for g, zs, zt in cuts if zs <= b + eps]
        for z, cut_, up in ((top, tcut, True), (b, bcut, False)):
            g = poly.difference(unary_union(cut_)) if cut_ else poly
            for gg in getattr(g, "geoms", [g]):
                if gg.geom_type != "Polygon" or gg.area < 1e-6:
                    continue
                gg = orient(gg, 1.0 if up else -1.0)
                faces.append({"loop": [(x, y, z) for x, y in
                                       list(gg.exterior.coords)[:-1]],
                              "holes": [[(x, y, z) for x, y in
                                         list(r.coords)[:-1]]
                                        for r in gg.interiors]})
    # the openings' own faces: jambs (the cut's edges inside the wall),
    # sill and head
    bound = U.boundary
    for g, zs, zt in cuts:
        for gg in getattr(g, "geoms", [g]):
            if gg.geom_type != "Polygon":
                continue
            gg = orient(gg, 1.0)
            cs = list(gg.exterior.coords)[:-1]
            for i in range(len(cs)):
                p, q = cs[i], cs[(i + 1) % len(cs)]
                if math.dist(p, q) < 1e-5:
                    continue
                mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                from shapely.geometry import Point
                if bound.distance(Point(mid)) < 2e-3:
                    continue              # on the wall's face: open
                # facing into the opening
                faces.append([(q[0], q[1], zs), (p[0], p[1], zs),
                              (p[0], p[1], zt), (q[0], q[1], zt)])
            if zs > b + eps:              # the sill, looking up
                faces.append({"loop": [(x, y, zs) for x, y in cs],
                              "holes": []})
            if zt < top - eps:            # the head, looking down
                faces.append({"loop": [(x, y, zt) for x, y in cs[::-1]],
                              "holes": []})
    return faces


def footprint(w, o, seg, extra=0.05):
    """An opening's plan footprint through its (straight) wall."""
    from shapely.geometry import Polygon
    p0, u = seg.p0, seg.u
    n = (-u[1], u[0])
    s0 = float(o["pos"]) - float(o["w"]) / 2
    s1 = float(o["pos"]) + float(o["w"]) / 2
    h = float(w["t"]) / 2 + extra
    pts = []
    for s, c in ((s0, -h), (s1, -h), (s1, h), (s0, h)):
        pts.append((p0[0] + u[0] * s + n[0] * c, p0[1] + u[1] * s + n[1] * c))
    return Polygon(pts)
