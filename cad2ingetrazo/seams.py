"""Clean wall junctions: the lines where two walls meet hidden.

Each wall is its own group (selectable, a component type), so where one
wall runs on into the next — a T, a butt joint, a mitred corner, the
joint line across the top — both groups draw their outline there and the
model shows a seam.  This finds, per level, every edge of a wall that is
NOT a true edge of the walls taken together (their union) and marks it
hidden: the walls read as one plastered mass, the real corners stay.

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

TOL = 0.004          # m: on a line / inside a wall
CORNER = 0.006       # m: an edge this close to a corner of the union is one


def _plan_of(faces):
    """A wall element's plan (shapely), and its z range."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys, zs = [], []
    for f in faces:
        lp = f["loop"] if isinstance(f, dict) else f
        zs += [q[2] for q in lp]
        if len(lp) >= 3 and max(q[2] for q in lp) - min(q[2] for q in lp) \
                < 1e-6:
            try:
                p = Polygon([(q[0], q[1]) for q in lp])
                if not p.is_valid:
                    p = p.buffer(0)
                if p.area > 1e-6:
                    polys.append(p)
            except Exception:  # noqa: BLE001
                pass
    if not polys or not zs:
        return None, (0.0, 0.0)
    return unary_union(polys), (min(zs), max(zs))


def _edges(faces):
    for f in faces:
        lp = f["loop"] if isinstance(f, dict) else f
        loops = [lp] + list((f.get("holes") or []) if isinstance(f, dict)
                            else [])
        for L in loops:
            n = len(L)
            for i in range(n):
                yield tuple(L[i]), tuple(L[(i + 1) % n])


def _stacked(a, b, me, solids, z):
    """A level edge ``a``–``b`` at height ``z`` where another solid's face
    carries straight on, flush, above or below it (a wall under the slab's
    plastered edge): the joint line between the two — hidden."""
    from shapely.geometry import LineString
    if abs(a[0] - b[0]) + abs(a[1] - b[1]) < 1e-4:
        return False
    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    ln = None
    for x in solids:
        if x[0] == me:
            continue
        lo, hi = x[2]
        if not (abs(lo - z) < 0.01 or abs(hi - z) < 0.01):
            continue
        bb = x[5] if len(x) > 5 else None
        if bb is not None and (x0 < bb[0] or y0 < bb[1] or x1 > bb[2]
                               or y1 > bb[3]):
            continue
        if ln is None:
            ln = LineString([(a[0], a[1]), (b[0], b[1])])
            if ln.length < 1e-4:
                return False
        if x[4].contains(ln):
            return True
    return False


def solids_of(items) -> list:
    """[(key, faces)] -> the outlines the flush-joint test reads."""
    from shapely.prepared import prep
    out = []
    for key, faces in items:
        pl, zr = _plan_of(faces)
        if pl is not None:
            b = pl.bounds
            out.append((key, pl, zr, None, prep(pl.boundary.buffer(TOL)),
                        (b[0] - TOL, b[1] - TOL, b[2] + TOL, b[3] + TOL)))
    return out


def hidden_edges(walls, slabs=(), solids=None) -> dict:
    """``walls``: [(key, faces)] of ONE level. -> {key: {((x, y, z),
    (x, y, z)), …}} the world edges to hide, endpoints rounded to the
    mm and sorted."""
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from shapely.prepared import prep
    plans = []
    for key, faces in walls:
        pl, zr = _plan_of(faces)
        if pl is not None:
            b = pl.bounds
            plans.append((key, pl, zr, prep(pl.buffer(TOL, join_style=2)),
                          (b[0] - TOL, b[1] - TOL, b[2] + TOL, b[3] + TOL)))
    # every solid's outline (walls and slabs), for the flush joints between
    # one stacked on the other
    if solids is None:
        solids = solids_of(list(walls) + list(slabs))
    if not plans and not slabs:
        return {}
    if not plans:
        plans_u = [_plan_of(f)[0] for _k, f in slabs]
    U = unary_union([x[1] for x in plans] or
                    [p for p in plans_u if p is not None]).buffer(
        1e-5, join_style=2).buffer(-1e-5, join_style=2)
    bnd = U.boundary
    corners = []
    for g in getattr(U, "geoms", [U]):
        if g.geom_type != "Polygon":
            continue
        for r in [g.exterior] + list(g.interiors):
            corners += list(r.coords)[:-1]
    from shapely.geometry import MultiPoint
    cps = MultiPoint(corners) if corners else None
    out = {}
    wkeys = {k for k, _f in walls}
    for key, faces in list(walls) + list(slabs):
        others = [x for x in plans if x[0] != key]
        hide = set()
        for a, b in _edges(faces):
            vert = abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4
            flat = abs(a[2] - b[2]) < 1e-4
            if not (vert or flat):
                continue
            if flat and _stacked(a, b, key, solids, a[2]):
                hide.add(tuple(sorted((tuple(round(v, 3) + 0.0 for v in a),
                                       tuple(round(v, 3) + 0.0
                                             for v in b)))))
                continue
            if key not in wkeys:
                continue
            zlo, zhi = min(a[2], b[2]), max(a[2], b[2])
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            m = None
            cover = []
            for x in others:
                if not (x[2][0] - 0.01 <= zlo and x[2][1] + 0.01 >= zhi):
                    continue
                bb = x[4]
                if mx < bb[0] or my < bb[1] or mx > bb[2] or my > bb[3]:
                    continue
                if m is None:
                    m = Point(mx, my)
                if x[3].contains(m):
                    cover.append(x)
            if not cover:
                continue
            if vert:
                # a true corner of the walls together stays
                if cps is not None and m.distance(cps) < CORNER:
                    continue
            else:
                # a line along the outside of the walls stays (the top's,
                # the foot's outline); one across them is the joint
                if m.distance(bnd) < TOL:
                    continue
            k = tuple(sorted((tuple(round(v, 3) + 0.0 for v in a),
                              tuple(round(v, 3) + 0.0 for v in b))))
            hide.add(k)
        if hide:
            out[key] = hide
    return out


def to_local(seg_set, fr) -> frozenset:
    """World edges -> the element frame ``fr`` (as components.local_faces),
    rounded to the mm."""
    import math
    ox, oy, oz, ang = fr
    a = math.radians(ang)
    c, s = math.cos(a), math.sin(a)

    def L(q):
        x, y = q[0] - ox, q[1] - oy
        return (round(x * c + y * s, 3) + 0.0,
                round(-x * s + y * c, 3) + 0.0, round(q[2] - oz, 3) + 0.0)
    return frozenset(tuple(sorted((L(p), L(q)))) for p, q in seg_set)


def apply(mesh, local_set) -> int:
    """Mark the mesh's edges in ``local_set`` hidden. Returns how many."""
    if not local_set:
        return 0
    n = 0
    for e in mesh.edges:
        p, q = e.v0.position, e.v1.position
        k = tuple(sorted(((round(p.x(), 3) + 0.0, round(p.y(), 3) + 0.0,
                           round(p.z(), 3) + 0.0),
                          (round(q.x(), 3) + 0.0, round(q.y(), 3) + 0.0,
                           round(q.z(), 3) + 0.0))))
        if k in local_set:
            e.hidden = True
            n += 1
    return n
