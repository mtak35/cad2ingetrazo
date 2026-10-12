# SPDX-License-Identifier: GPL-3.0-or-later
"""Corner and bay windows: glazing the plan draws where the walls stop — two
(or more) parallel window lines turning a corner, square or chamfered,
running from one wall to another where no wall is drawn. Each leg becomes
a window wall: a curtain wall with an opaque panel under the sill and
over the head, glass between (so the glass turns the corner).
"""
from __future__ import annotations

import math


def _clusters(segs, gap=0.3, ang_tol=4.0):
    """Parallel lines within ``gap`` of each other and overlapping →
    one centre line each: [(a, b, spread)]."""
    items = []
    for s in segs:
        a, b = (s[0], s[1]), (s[2], s[3])
        L = math.dist(a, b)
        if L < 0.15:
            continue
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
        items.append([a, b, L, ang])
    used = [False] * len(items)
    out = []
    for i, (a, b, L, ang) in enumerate(items):
        if used[i]:
            continue
        used[i] = True
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        n = (-u[1], u[0])
        grp = [i]
        changed = True
        while changed:
            changed = False
            for j, (c, d, L2, ang2) in enumerate(items):
                if used[j]:
                    continue
                da = abs((ang2 - ang + 90.0) % 180.0 - 90.0)
                if da > ang_tol:
                    continue
                offs = [(p[0] - a[0]) * n[0] + (p[1] - a[1]) * n[1]
                        for p in (c, d)]
                if min(abs(o) for o in offs) > gap + 0.5 * 0:
                    # within the gap of any line of the group
                    near = False
                    for k in grp:
                        e, f = items[k][0], items[k][1]
                        o_ = (c[0] - e[0]) * n[0] + (c[1] - e[1]) * n[1]
                        if abs(o_) <= gap:
                            near = True
                            break
                    if not near:
                        continue
                # overlapping along the line (or end to end within 0.15)
                s_g = [((p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1])
                       for k in grp for p in items[k][:2]]
                s_c = [((p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1])
                       for p in (c, d)]
                if max(s_c) < min(s_g) - 0.15 or min(s_c) > max(s_g) + 0.15:
                    continue
                used[j] = True
                grp.append(j)
                changed = True
        ss = [((p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1])
              for k in grp for p in items[k][:2]]
        os_ = [((p[0] - a[0]) * n[0] + (p[1] - a[1]) * n[1])
               for k in grp for p in items[k][:2]]
        mid = (min(os_) + max(os_)) / 2
        s0, s1 = min(ss), max(ss)
        pa = (a[0] + u[0] * s0 + n[0] * mid, a[1] + u[1] * s0 + n[1] * mid)
        pb = (a[0] + u[0] * s1 + n[0] * mid, a[1] + u[1] * s1 + n[1] * mid)
        out.append((pa, pb, max(os_) - min(os_), len(grp)))
    return out


def _chains(lines, tol=0.25):
    """Centre lines joined end to end (within ``tol``): [[indices]]."""
    n = len(lines)
    adj = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if min(math.dist(p, q) for p in lines[i][:2]
                   for q in lines[j][:2]) <= tol:
                adj[i].add(j)
                adj[j].add(i)
    seen, out = set(), []
    for i in range(n):
        if i in seen:
            continue
        stack, comp = [i], []
        seen.add(i)
        while stack:
            k = stack.pop()
            comp.append(k)
            for m in adj[k]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        out.append(comp)
    return out


def _axis(wall_lines):
    """The plan's main direction (°, 0–90) from its longest walls."""
    best, tot = 0.0, {}
    for a, b in wall_lines:
        L = math.dist(a, b)
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90.0
        k = round(ang)
        tot[k] = tot.get(k, 0.0) + L
    if tot:
        best = max(tot, key=tot.get)
    return float(best)


def _unit(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 1e-9 else (1.0, 0.0)


def _continues(p, u, wall_recs, reach=0.6):
    """The wall the window leg ending at ``p`` (running on along ``u``)
    carries on: one parallel to it, ``p`` on its line and near its end —
    (wall end point, the wall's centre-line foot of ``p``, t) or None."""
    best = None
    for a, b, t in wall_recs:
        L = math.dist(a, b)
        if L < 0.1:
            continue
        w = _unit(a, b)
        if abs(w[0] * u[1] - w[1] * u[0]) > math.sin(math.radians(5.0)):
            continue                          # not parallel
        off = abs((p[0] - a[0]) * w[1] - (p[1] - a[1]) * w[0])
        if off > t / 2 + 0.12:
            continue                          # not on the wall's line
        s = (p[0] - a[0]) * w[0] + (p[1] - a[1]) * w[1]
        # the wall's end that faces the window, and the gap to it
        for e, gap in ((a, -s), (b, s - L)):
            if -t <= gap <= reach:
                # the wall must lie ahead of the leg (along u)
                ahead = (e[0] - p[0]) * u[0] + (e[1] - p[1]) * u[1]
                if ahead < -t:
                    continue
                foot = (a[0] + w[0] * s, a[1] + w[1] * s)
                if best is None or abs(gap) < best[3]:
                    best = (e, foot, t, abs(gap))
    return best[:3] if best else None


def _line_x(p, u, q, v):
    """Where the line p + s·u meets q + r·v (None: parallel)."""
    den = u[0] * v[1] - u[1] * v[0]
    if abs(den) < 1e-6:
        return None
    s = ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / den
    return (p[0] + u[0] * s, p[1] + u[1] * s)


def find(window_segs, wall_polys, min_len=0.9, max_len=9.0,
         wall_lines=None, wall_recs=None):
    """The corner / bay window legs: [((x, y), (x, y), thickness)].

    A corner window closes the building's outline where a corner has no
    wall: glazing drawn double (a wall's two faces) that turns the corner
    (square or chamfered) and carries on the walls at both its ends — each
    leg put on that wall's centre line, as thick as it, and run up to its
    end. A bay window stands out of the outline from wall to wall. Glass
    inside the building (a shower screen, a partition) is no window."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    if not window_segs or not wall_polys:
        return []
    walls = unary_union(wall_polys)
    inside = walls.buffer(0.12)
    if wall_recs is None:
        wall_recs = [(a, b, 0.2) for a, b in (wall_lines or [])]
    # the building's outline: the walls with their gaps closed
    u_ = walls.buffer(2.0, join_style=2).buffer(-2.0, join_style=2)
    foot = unary_union([Polygon(g.exterior) for g in
                        getattr(u_, "geoms", [u_]) if g.geom_type == "Polygon"])
    core = foot.buffer(-0.45, join_style=2)
    free = []
    for s in window_segs:
        L = LineString([(s[0], s[1]), (s[2], s[3])])
        if L.length < 0.15 or L.length > max_len:
            continue
        if inside.contains(L.interpolate(0.5, normalized=True)):
            continue                     # a window in a wall: done already
        if walls.distance(L) > 1.5:
            continue                     # far from the building
        free.append(s)
    # glazing is drawn double: single lines are partitions, rails, glass
    ax = _axis(wall_lines or [(a, b) for a, b, _t in wall_recs])

    def _ok(c):                          # along the axes or a 45° chamfer
        g = math.degrees(math.atan2(c[1][1] - c[0][1], c[1][0] - c[0][0]))
        ang = (g - ax) % 90.0
        return min(ang, 90.0 - ang) <= 4.0 or abs(ang - 45.0) <= 6.0
    cl = [c for c in _clusters(free) if math.dist(c[0], c[1]) >= 0.25
          and c[3] >= 2 and _ok(c)]
    out = []
    for comp in _chains(cl, tol=0.3):
        legs = [list(cl[k][:3]) for k in comp]
        tot = sum(math.dist(l[0], l[1]) for l in legs)
        if tot < min_len:
            continue
        kinds = []
        for l in legs:
            g = math.degrees(math.atan2(l[1][1] - l[0][1],
                                        l[1][0] - l[0][0]))
            ang = (g - ax) % 90.0
            if min(ang, 90.0 - ang) <= 4.0:
                d_ = (g - ax) % 180
                kinds.append("x" if min(d_, 180 - d_) < 45 else "y")
            elif abs(ang - 45.0) <= 6.0:
                kinds.append("c")
            else:
                kinds.append(None)
        if None in kinds or not ("x" in kinds and "y" in kinds):
            continue                     # it must turn a corner
        # the chain's free ends: (leg, which end)
        ends = []
        for i, l in enumerate(legs):
            for k in (0, 1):
                p = l[k]
                if not any(min(math.dist(p, q) for q in o[:2]) <= 0.3
                           for j, o in enumerate(legs) if j != i):
                    ends.append((i, k))
        if len(ends) != 2:
            continue
        if not all(walls.distance(Point(legs[i][k])) <= 0.6
                   for i, k in ends):
            continue                     # a free line, a door leaf
        cont = {}
        for i, k in ends:
            l = legs[i]
            p, q = l[k], l[1 - k]
            c_ = _continues(p, _unit(q, p), wall_recs)
            if c_ is not None:
                cont[(i, k)] = c_
        mids = [((l[0][0] + l[1][0]) / 2, (l[0][1] + l[1][1]) / 2)
                for l in legs]
        outside = all(not core.contains(Point(m)) for m in mids)
        if len(cont) < 2 and not (outside and not foot.contains(
                Point(mids[len(mids) // 2]))):
            continue                     # glass inside the building
        # each leg on the line of the wall it carries on, as thick as it
        ts = [c_[2] for c_ in cont.values()]
        t_def = max(ts) if ts else max(0.1, min(
            max(l[2] for l in legs) + 0.05, 0.3))
        lines = []
        for i, l in enumerate(legs):
            u = _unit(l[0], l[1])
            p = l[0]
            t = t_def
            for (j, k), (e, f, tw) in cont.items():
                if j == i:
                    # move the leg's line onto the wall's centre line
                    n = (-u[1], u[0])
                    d = (f[0] - l[k][0]) * n[0] + (f[1] - l[k][1]) * n[1]
                    p = (l[0][0] + n[0] * d, l[0][1] + n[1] * d)
                    t = tw
            lines.append([p, u, t])
        newl = []
        for i, (l, (p, u, t)) in enumerate(zip(legs, lines)):
            s0 = (l[0][0] - p[0]) * u[0] + (l[0][1] - p[1]) * u[1]
            s1 = (l[1][0] - p[0]) * u[0] + (l[1][1] - p[1]) * u[1]
            A = (p[0] + u[0] * s0, p[1] + u[1] * s0)
            B = (p[0] + u[0] * s1, p[1] + u[1] * s1)
            newl.append([A, B, t])
        # the free ends run up to the wall they carry on
        for (i, k), (e, f, tw) in cont.items():
            p, u, t = lines[i]
            s = (e[0] - p[0]) * u[0] + (e[1] - p[1]) * u[1]
            newl[i][k] = (p[0] + u[0] * s, p[1] + u[1] * s)
        # the joints: both legs to where their lines cross
        for i in range(len(legs)):
            for j in range(i + 1, len(legs)):
                for ki in (0, 1):
                    for kj in (0, 1):
                        if math.dist(legs[i][ki], legs[j][kj]) > 0.3:
                            continue
                        x = _line_x(lines[i][0], lines[i][1],
                                    lines[j][0], lines[j][1])
                        if x is None or math.dist(x, legs[i][ki]) > 0.6:
                            m = legs[i][ki]
                            x = ((m[0] + legs[j][kj][0]) / 2,
                                 (m[1] + legs[j][kj][1]) / 2)
                        newl[i][ki] = x
                        newl[j][kj] = x
        for A, B, t in newl:
            if math.dist(A, B) >= 0.2:
                out.append((A, B, t))
    return out
