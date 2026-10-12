# SPDX-License-Identifier: GPL-3.0-or-later
"""Corner and bay windows: glazing the plan draws OUTSIDE the walls — two
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


def find(window_segs, wall_polys, min_len=0.9, max_len=9.0,
         wall_lines=None):
    """The corner / bay window legs: [((x, y), (x, y), thickness)] — chains
    of window centre lines outside the walls that run from a wall to a
    wall (both ends of the chain within 0.6 m of one) and turn (two legs
    or more), or run along one wall's gap."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    if not window_segs or not wall_polys:
        return []
    walls = unary_union(wall_polys)
    inside = walls.buffer(0.12)
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
    cl = [c for c in _clusters(free) if math.dist(c[0], c[1]) >= 0.25]
    out = []
    for comp in _chains(cl):
        legs = [cl[k] for k in comp]
        tot = sum(math.dist(l[0], l[1]) for l in legs)
        if tot < min_len:
            continue
        # the chain's free ends: endpoints touching no other leg
        ends = []
        for i, l in enumerate(legs):
            for p in l[:2]:
                if not any(min(math.dist(p, q) for q in o[:2]) <= 0.25
                           for j, o in enumerate(legs) if j != i):
                    ends.append(p)
        if len(ends) < 2:
            continue
        if not all(walls.distance(Point(p)) <= 0.6 for p in ends):
            continue                     # a door leaf, a free line
        # a corner window: legs along the plan's axes (and 45° chamfers
        # between them), turning — never a door leaf at an angle
        ax = _axis(wall_lines or [])
        kinds = []
        for l in legs:
            ang = (math.degrees(math.atan2(l[1][1] - l[0][1],
                                           l[1][0] - l[0][0])) - ax) % 90.0
            off = min(ang, 90.0 - ang)
            if off <= 4.0:
                d_ = (math.degrees(math.atan2(l[1][1] - l[0][1],
                                              l[1][0] - l[0][0])) - ax) % 180
                kinds.append("x" if min(d_, 180 - d_) < 45 else "y")
            elif abs(ang - 45.0) <= 6.0:
                kinds.append("c")
            else:
                kinds.append(None)
        if None in kinds or not ("x" in kinds and "y" in kinds):
            continue
        if any(l[3] < 2 for l, k in zip(legs, kinds) if k in ("x", "y")):
            continue                     # glazing: drawn double
        for l in legs:
            out.append((l[0], l[1], max(0.1, min(l[2] + 0.05, 0.3))))
    # legs meeting at a corner: their ends brought together
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            ai, bi, ti = out[i]
            aj, bj, tj = out[j]
            for pi_k, p in ((0, ai), (1, bi)):
                for pj_k, q in ((0, aj), (1, bj)):
                    if 1e-6 < math.dist(p, q) <= 0.3:
                        m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                        li = list(out[i])
                        lj = list(out[j])
                        li[pi_k] = m
                        lj[pj_k] = m
                        out[i], out[j] = tuple(li), tuple(lj)
    return out
