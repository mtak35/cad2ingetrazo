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


def coplanar_hidden(items, probe: float = 0.0025,
                    plane_tol: float = 0.003, zbands=None):
    """3.64.165: the joints between faces that lie in ONE plane — the
    line where a wall's face carries on into the next wall, the slab's
    plastered edge or the wall over it: nothing shows between floors on
    an elevation.  ``items``: [(key, faces)] of the walls, slabs and the
    like (world faces).  An edge of a vertical face is a joint where, an
    instant outside it in that plane, ANOTHER face (the same way round)
    covers the plane along the edge — where it covers only a part (the
    upper wall's windows), the edge is split there and just the covered
    stretches hidden.  -> ({key: {edge, …}}, {id(loop): {edge index:
    [t, …]}}): the edges to hide (like ``hidden_edges``) and the
    points to add on the loops (``split_loops``).

    3.64.166: with ``zbands`` [(z0, z1), …] and a ``plane_tol`` of a few
    cm it is the LEDGE pass — only the level (horizontal) edges that lie
    in a band (the floor lines) and a face that stands up to ``plane_tol``
    in front of / behind the one carrying on past the edge: a wall on a
    wall of another thickness shows no line at the floor."""
    import math
    from collections import defaultdict
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    def newell(lp):
        nx = ny = nz = 0.0
        for i in range(len(lp)):
            a, b = lp[i], lp[(i + 1) % len(lp)]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        return nx, ny, nz

    ANG = math.radians(0.1)
    planes = defaultdict(list)
    for key, faces in items:
        for f in faces:
            lp = f["loop"] if isinstance(f, dict) else f
            if len(lp) < 3:
                continue
            nx, ny, nz = newell(lp)
            nl = math.sqrt(nx * nx + ny * ny + nz * nz)
            if nl < 1e-9 or abs(nz) / nl > 0.02:
                continue
            h = math.hypot(nx, ny)
            ang = math.atan2(ny, nx)
            d = (nx * lp[0][0] + ny * lp[0][1]) / h
            holes = list((f.get("holes") or []) if isinstance(f, dict)
                         else [])
            r = (key, [lp] + holes, ang, d)
            planes[(round(ang / ANG), round(d / plane_tol))].append(r)

    out = defaultdict(set)
    splits = defaultdict(dict)

    def ek(a, b):
        return tuple(sorted((tuple(round(v, 3) + 0.0 for v in a),
                             tuple(round(v, 3) + 0.0 for v in b))))
    for (ka, kd), prim in planes.items():
        cand = []
        for da in (-1, 0, 1):
            for dd in (-1, 0, 1):
                cand += planes.get((ka + da, kd + dd), [])
        if len(cand) < 2:
            continue
        ang0 = prim[0][2]
        ux, uy = -math.sin(ang0), math.cos(ang0)

        def poly(r):
            loops = r[1]
            try:
                P = Polygon([(q[0] * ux + q[1] * uy, q[2]) for q in loops[0]],
                            [[(q[0] * ux + q[1] * uy, q[2]) for q in h]
                             for h in loops[1:]])
                if not P.is_valid:
                    P = P.buffer(0)
                return P
            except Exception:  # noqa: BLE001
                return None
        polys = []
        for r in cand:
            P = poly(r)
            if P is not None and not P.is_empty and P.area > 1e-8:
                polys.append((r, P))
        if len(polys) < 2:
            continue
        tree = STRtree([p for _r, p in polys])
        pset = {id(r) for r in prim}
        for r, P in polys:
            if id(r) not in pset:
                continue
            for loop in r[1]:
                n = len(loop)
                for i in range(n):
                    a, b = loop[i], loop[(i + 1) % n]
                    vert = abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4
                    flat = abs(a[2] - b[2]) < 1e-4
                    if not (vert or flat) or (vert and flat):
                        continue
                    if zbands is not None and (vert or not any(
                            z0 <= a[2] <= z1 for z0, z1 in zbands)):
                        continue
                    ua, ub = a[0] * ux + a[1] * uy, b[0] * ux + b[1] * uy
                    if flat and abs(ua - ub) < 0.02:
                        continue
                    A = (ua, a[2])
                    B = (ub, b[2])
                    L = math.hypot(B[0] - A[0], B[1] - A[1])
                    if L < 0.02:
                        continue
                    w = (0.0, 1.0) if flat else (1.0, 0.0)
                    # which side is OUT of this face (the middle's probes)
                    mx, my = (A[0] + B[0]) / 2, (A[1] + B[1]) / 2
                    from shapely.geometry import Point
                    i1 = P.contains(Point(mx + w[0] * probe, my + w[1] * probe))
                    i2 = P.contains(Point(mx - w[0] * probe, my - w[1] * probe))
                    if i1 == i2:
                        continue
                    sg = -1.0 if i1 else 1.0
                    S0 = (A[0] + sg * w[0] * probe, A[1] + sg * w[1] * probe)
                    S1 = (B[0] + sg * w[0] * probe, B[1] + sg * w[1] * probe)
                    ln = LineString([S0, S1])
                    cov = []
                    for j in tree.query(ln):
                        r2, P2 = polys[j]
                        if r2 is r:
                            continue
                        if zbands is not None and abs(r2[3] - r[3]) \
                                > plane_tol:
                            continue
                        g = P2.intersection(ln)
                        if not g.is_empty:
                            cov.append(g)
                    if not cov:
                        continue
                    U = unary_union(cov)
                    segs = []
                    for g in getattr(U, "geoms", [U]):
                        if g.geom_type == "LineString" and g.length > 0.02:
                            cs = list(g.coords)
                            ts = sorted(
                                ((c[0] - S0[0]) * (S1[0] - S0[0])
                                 + (c[1] - S0[1]) * (S1[1] - S0[1]))
                                / (L * L) for c in (cs[0], cs[-1]))
                            segs.append((max(0.0, ts[0]), min(1.0, ts[1])))
                    if not segs:
                        continue
                    segs.sort()
                    merged = [list(segs[0])]
                    for s0, s1 in segs[1:]:
                        if s0 <= merged[-1][1] + 0.002:
                            merged[-1][1] = max(merged[-1][1], s1)
                        else:
                            merged.append([s0, s1])
                    tm = 0.002 / L if L > 0 else 0.0
                    pts = []

                    def at(t):
                        return tuple(a[k] + (b[k] - a[k]) * t
                                     for k in range(3))
                    for s0, s1 in merged:
                        s0 = 0.0 if s0 < tm + 0.005 / L else s0
                        s1 = 1.0 if s1 > 1.0 - tm - 0.005 / L else s1
                        if s1 - s0 < 0.02 / L:
                            continue
                        pts.append((s0, s1))
                    if not pts:
                        continue
                    key = r[0]
                    for s0, s1 in pts:
                        out[key].add(ek(at(s0), at(s1)))
                        for t in (s0, s1):
                            if 0.0 < t < 1.0:
                                splits[id(loop)].setdefault(i, []).append(t)
    return dict(out), dict(splits)


def split_loops(items, splits) -> int:
    """Add the break points ``coplanar_hidden`` found to the face loops
    (in place) — on EVERY loop of the elements that has one of them on an
    edge (the wall's bottom / top face shares the joint's edge with its
    side face) — so the edge is two (or more) mesh edges there and the
    covered stretch alone is hidden.  -> how many loops were changed."""
    if not splits:
        return 0
    from shapely.geometry import Point, box
    from shapely.strtree import STRtree
    idmap = {}
    for _k, faces in items:
        for f in faces:
            lp = f["loop"] if isinstance(f, dict) else f
            idmap[id(lp)] = lp
            for h in ((f.get("holes") or []) if isinstance(f, dict) else []):
                idmap[id(h)] = h
    pts = {}
    for lid, sp in splits.items():
        lp = idmap.get(lid)
        if lp is None:
            continue
        n = len(lp)
        for i, ts in sp.items():
            a, b = lp[i], lp[(i + 1) % n]
            for t in ts:
                q = tuple(a[k] + (b[k] - a[k]) * t for k in range(3))
                pts[tuple(round(v, 4) for v in q)] = q
    if not pts:
        return 0
    P3 = list(pts.values())
    tree = STRtree([Point(q[0], q[1]) for q in P3])
    E = 1e-4

    def fix(lp):
        out, ch = [], False
        n = len(lp)
        for i in range(n):
            c, d = lp[i], lp[(i + 1) % n]
            out.append(tuple(c))
            dx, dy, dz = d[0] - c[0], d[1] - c[1], d[2] - c[2]
            L2 = dx * dx + dy * dy + dz * dz
            if L2 < 1e-6:
                continue
            L = L2 ** 0.5
            hits = []
            for j in tree.query(box(min(c[0], d[0]) - E, min(c[1], d[1]) - E,
                                    max(c[0], d[0]) + E,
                                    max(c[1], d[1]) + E)):
                q = P3[j]
                vx, vy, vz = q[0] - c[0], q[1] - c[1], q[2] - c[2]
                t = (vx * dx + vy * dy + vz * dz) / L2
                if t * L <= 1e-3 or (1.0 - t) * L <= 1e-3:
                    continue
                if abs(vx - t * dx) < E and abs(vy - t * dy) < E \
                        and abs(vz - t * dz) < E:
                    hits.append((t, q))
            if hits:
                ch = True
                last = None
                for t, q in sorted(hits):
                    if last is not None and t - last < 1e-6:
                        continue
                    out.append(tuple(q))
                    last = t
        return out if ch else lp
    n = 0
    for _key, faces in items:
        for idx, f in enumerate(faces):
            if isinstance(f, dict):
                lp = f["loop"]
                hs = f.get("holes") or []
                nl = fix(lp)
                nh = [fix(h) for h in hs]
                if nl is not lp or any(x is not y for x, y in zip(nh, hs)):
                    g = dict(f)
                    g["loop"] = nl
                    if hs:
                        g["holes"] = nh
                    faces[idx] = g
                    n += 1
            else:
                nl = fix(f)
                if nl is not f:
                    faces[idx] = nl
                    n += 1
    return n


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
