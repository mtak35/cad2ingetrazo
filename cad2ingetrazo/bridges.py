# SPDX-License-Identifier: GPL-3.0-or-later
"""Doors and windows the walls alone do not hold.

A plan often draws a door between the ends of two walls that run across
it (a lobby's fins, a row of piers), or a window's glazing from pier to
pier with no wall line along it: the wall there is only implied. Here
every door swing (an arc on the door layers, its leaf from the hinge) and
every window band (glazing lines side by side on the window layers) is
looked for in the walls found; one no wall holds gets a short wall of its
own, exactly as wide as the door / window, holding it. A wall that holds
the symbol but no opening there gets the opening.

The piers drawn as closed boxes on the wall layers (too square to be a
wall) become solid piers (columns), so the bands between them stand
between solids.
"""
from __future__ import annotations

import math

ANG = 4.0             # ° parallel
_DBG = None
DOOR_R = (0.45, 1.35)  # m, a leaf's width
WIN_MIN = 0.35        # m, a window band's least length
BAND_MAX = 0.45       # m, a window band's most depth across


def _u(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 1e-9 else (1.0, 0.0)


def _ang(u):
    return math.degrees(math.atan2(u[1], u[0])) % 180.0


def _adiff(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


# ---- the symbols ------------------------------------------------------------------
def door_symbols(pl, is_door) -> list:
    """[(jamb A, jamb B, leaves)] — each door the swings show: a single
    leaf from its hinge (A) to the closed leaf's end (B); a pair of leaves
    meeting in the middle from hinge to hinge."""
    arcs = [a for a in pl.get("arcs") or () if is_door(a["layer"])
            and DOOR_R[0] <= a["r"] <= DOOR_R[1]]
    lay = pl["layers"]
    leaves = [((s[0], s[1]), (s[2], s[3])) for s in pl["segs"]
              if is_door(lay[s[4]])]
    one = []
    for a in arcs:
        c, r = tuple(a["c"]), a["r"]
        e0, e1 = tuple(a["p0"]), tuple(a["p1"])
        sweep = math.degrees(math.acos(max(-1.0, min(1.0, (
            (e0[0] - c[0]) * (e1[0] - c[0]) + (e0[1] - c[1]) * (e1[1] - c[1]))
            / (r * r)))))
        if not 55.0 <= sweep <= 120.0:
            continue
        # the open leaf: a line from the hinge to one end of the swing; the
        # door's other jamb: the other end (where the closed leaf lies)

        def leaf_at(e):
            for p, q in leaves:
                for x, y in ((p, q), (q, p)):
                    if math.dist(x, c) < 0.06 + 0.05 * r and \
                            math.dist(y, e) < 0.12 + 0.1 * r:
                        return True
            return False
        l0, l1 = leaf_at(e0), leaf_at(e1)
        if l0 and not l1:
            closed = e1
        elif l1 and not l0:
            closed = e0
        else:
            closed = None              # decided by its pair / the walls
        one.append({"c": c, "r": r, "e": (e0, e1), "closed": closed})
    out, used = [], set()
    # pairs: two swings whose closed ends meet (a double door)
    for i, a in enumerate(one):
        if i in used:
            continue
        best = None
        for j, b in enumerate(one):
            if j <= i or j in used or abs(a["r"] - b["r"]) > 0.25 * a["r"]:
                continue
            for ea in a["e"]:
                for eb in b["e"]:
                    d = math.dist(ea, eb)
                    span = math.dist(a["c"], b["c"])
                    if d < 0.12 and abs(span - a["r"] - b["r"]) < 0.15:
                        if best is None or d < best[0]:
                            best = (d, j)
        if best is not None:
            j = best[1]
            used |= {i, j}
            out.append((a["c"], one[j]["c"], 2))
    for i, a in enumerate(one):
        if i in used:
            continue
        cl = a["closed"]
        if cl is None:
            continue
        out.append((a["c"], cl, 1))
    return out


def window_bands(pl, is_win, is_line=None) -> list:
    """[(p, q, depth)] — glazing drawn as lines side by side: the band's
    centre line from end to end and its depth across — with the «line»
    layer's lines lying along it, right beside it (a CNC grille set in the
    same opening: the wall is that much thicker)."""
    lay = pl["layers"]
    ls = []
    for s in pl["segs"]:
        if not is_win(lay[s[4]]):
            continue
        a, b = (s[0], s[1]), (s[2], s[3])
        if math.dist(a, b) < 0.25:
            continue
        ls.append((a, b))
    n = len(ls)
    par = list(range(n))

    def root(k):
        while par[k] != k:
            par[k] = par[par[k]]
            k = par[k]
        return k
    info = []
    for a, b in ls:
        u = _u(a, b)
        if u[0] < -1e-9 or (abs(u[0]) < 1e-9 and u[1] < 0):
            u = (-u[0], -u[1])
        nv = (-u[1], u[0])
        info.append((u, nv, _ang(u)))
    # cells to keep it quick on big plans
    cells: dict = {}
    for i, (a, b) in enumerate(ls):
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        cells.setdefault((int(m[0] // 3), int(m[1] // 3)), []).append(i)
    for i, (a, b) in enumerate(ls):
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        cx, cy = int(m[0] // 3), int(m[1] // 3)
        u, nv, ag = info[i]
        s0 = sorted((a[0] * u[0] + a[1] * u[1], b[0] * u[0] + b[1] * u[1]))
        o = m[0] * nv[0] + m[1] * nv[1]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cells.get((cx + dx, cy + dy), ()):
                    if j <= i or _adiff(info[j][2], ag) > ANG:
                        continue
                    c, d = ls[j]
                    mj = ((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)
                    if abs(mj[0] * nv[0] + mj[1] * nv[1] - o) > BAND_MAX:
                        continue
                    s1 = sorted((c[0] * u[0] + c[1] * u[1],
                                 d[0] * u[0] + d[1] * u[1]))
                    ov = min(s0[1], s1[1]) - max(s0[0], s1[0])
                    if ov >= 0.5 * min(s0[1] - s0[0], s1[1] - s1[0]):
                        par[root(j)] = root(i)
    groups: dict = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)
    out = []
    for g in groups.values():
        if len(g) < 2:
            continue
        u, nv, _a = info[g[0]]
        offs, ss = [], []
        for i in g:
            a, b = ls[i]
            offs += [a[0] * nv[0] + a[1] * nv[1], b[0] * nv[0] + b[1] * nv[1]]
            ss += [a[0] * u[0] + a[1] * u[1], b[0] * u[0] + b[1] * u[1]]
        # the band's length: the span most of its lines share (a frame's
        # short returns do not lengthen it)
        lo, hi = min(ss), max(ss)
        if hi - lo < WIN_MIN:
            continue
        if is_line is not None:              # a grille beside the glass
            o0, o1 = min(offs), max(offs)
            for s_ in pl["segs"]:
                if not is_line(lay[s_[4]]):
                    continue
                a, b = (s_[0], s_[1]), (s_[2], s_[3])
                if math.dist(a, b) < 0.3 or _adiff(_ang(_u(a, b)),
                                                   _a) > ANG:
                    continue
                sa = sorted((a[0] * u[0] + a[1] * u[1],
                             b[0] * u[0] + b[1] * u[1]))
                if min(sa[1], hi) - max(sa[0], lo) < 0.6 * min(
                        sa[1] - sa[0], hi - lo):
                    continue
                for x in (a, b):
                    ox = x[0] * nv[0] + x[1] * nv[1]
                    if o0 - 0.2 <= ox <= o1 + 0.2:
                        offs.append(ox)
        o = (min(offs) + max(offs)) / 2
        depth = max(offs) - min(offs)
        if depth < 0.04 or hi - lo > 6.0:
            continue
        p = (u[0] * lo + nv[0] * o, u[1] * lo + nv[1] * o)
        q = (u[0] * hi + nv[0] * o, u[1] * hi + nv[1] * o)
        out.append((p, q, depth))
    return out


def piers(pl, is_wall, walls) -> list:
    """[shapely polygon] — closed boxes on the wall layers (0.15–2.5 m²,
    no longer than twice their width) that no wall found covers."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union
    lay = pl["layers"]
    segs = [LineString([(s[0], s[1]), (s[2], s[3])]) for s in pl["segs"]
            if is_wall(lay[s[4]])]
    if not segs:
        return []
    polys = list(polygonize(unary_union(segs)))
    polys += [Polygon(lp["pts"]).buffer(0) for lp in pl.get("loops") or ()
              if is_wall(lp["layer"]) and len(lp["pts"]) >= 3]
    wp = []
    for w in walls:
        try:
            wp.append(LineString([w["a"], w["b"]]).buffer(
                float(w["t"]) / 2, cap_style=2))
        except Exception:  # noqa: BLE001
            continue
    W_ = unary_union(wp) if wp else Polygon()
    out = []
    for p in polys:
        if not p.is_valid or p.is_empty:
            continue
        a = p.area
        if not 0.15 <= a <= 2.5:
            continue
        r = p.minimum_rotated_rectangle
        cs = list(r.exterior.coords)
        s1, s2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        if min(s1, s2) < 0.25 or max(s1, s2) > 2.0 * min(s1, s2):
            continue
        if p.area < 0.75 * r.area:
            continue
        if not W_.is_empty and p.intersection(W_).area > 0.4 * a:
            continue
        if any(p.buffer(0.02).contains(q.centroid) and q.area > a
               for q in out):
            continue
        out = [q for q in out if not p.contains(q.centroid)] + [p]
    return out


# ---- placing them -----------------------------------------------------------------
def _host(walls, p, q, depth=0.0):
    """(wall, pos of the middle, along-width) of the wall that holds the
    segment p–q in its band, else None."""
    u = _u(p, q)
    ag = _ang(u)
    m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    L = math.dist(p, q)
    best = None
    for w in walls:
        a, b = w["a"], w["b"]
        Lw = math.dist(a, b)
        if Lw < 1e-6:
            continue
        uw = _u(a, b)
        if _adiff(_ang(uw), ag) > ANG * 2:
            continue
        t = float(w["t"])
        nw = (-uw[1], uw[0])
        off = abs((m[0] - a[0]) * nw[0] + (m[1] - a[1]) * nw[1])
        if off > t / 2 + 0.06 + depth / 2:
            continue
        pos = (m[0] - a[0]) * uw[0] + (m[1] - a[1]) * uw[1]
        if not 0.0 <= pos <= Lw:
            continue
        if best is None or off < best[0]:
            best = (off, w, pos)
    if best is None:
        return None
    return best[1], best[2], L


def _covered(openings, wall, pos, w):
    """The opening of ``wall`` already over pos ± w/2, else None."""
    for o in openings:
        if o["wall"] != wall["id"]:
            continue
        if abs(float(o["pos"]) - pos) < (float(o["w"]) + w) / 2 - 0.05:
            return o
    return None


def _near_t(walls, pts, default):
    """The thickness of the wall nearest the points (a door's jambs end
    on the walls round it), else ``default``."""
    best = None
    for w in walls:
        a, b = w["a"], w["b"]
        Lw = math.dist(a, b)
        if Lw < 1e-6:
            continue
        uw = _u(a, b)
        for p in pts:
            s = (p[0] - a[0]) * uw[0] + (p[1] - a[1]) * uw[1]
            s = max(0.0, min(Lw, s))
            x = (a[0] + uw[0] * s, a[1] + uw[1] * s)
            d = math.dist(x, p) - float(w["t"]) / 2
            if best is None or d < best[0]:
                best = (d, float(w["t"]))
    if best is not None and best[0] < 0.35:
        return min(max(best[1], 0.10), 0.35)
    return default


def bridge(arch, lid, pl, is_door, is_win, is_wall, st,
           is_line=None, is_col=None) -> dict:
    """The doors / windows / piers no wall holds placed (see the module):
    walls, openings and piers added to ``arch``; how many of each."""
    from .engine import model as M
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail")]
    ops = [o for o in arch["openings"]]
    rep = {"doors": 0, "windows": 0, "bridges": 0, "piers": 0}
    new_w, new_o = [], []

    def add(p, q, kind, t, leaves=1):
        L = math.dist(p, q)
        if L < 0.3:
            return
        h = _host(walls + new_w, p, q, t)
        if _DBG is not None:
            _DBG.append((kind, p, q, h is not None and h[0].get("id"),
                         h is not None and _covered(ops + new_o, h[0], h[1],
                                                    h[2]),
                         solids is not None and solids.contains(
                             __import__("shapely.geometry").geometry.Point(p))
                         and solids.contains(
                             __import__("shapely.geometry").geometry.Point(q))))
        if h is not None and kind == "window":
            # glazing over a wall the plan draws whole (no gap): a glass
            # railing on it, a window shown above — not an opening here
            hit = _covered(ops + new_o, h[0], h[1], h[2])
            if hit is None or hit.get("kind") != "void" or hit.get("hl"):
                return
        if h is None and kind == "window":
            # an implied wall: only between two solids (walls, piers,
            # columns) — glazing standing free is not a window
            from shapely.geometry import Point
            if solids is None or not (solids.contains(Point(p)) and
                                      solids.contains(Point(q))):
                return
        if h is not None:
            w, pos, wd = h
            Lw = math.dist(w["a"], w["b"])
            hit = _covered(ops + new_o, w, pos, wd)
            if hit is not None:
                # a gap read as «nothing drawn» that the swing / glazing
                # says is a door / window: made so
                if hit.get("kind") == "void" and not hit.get("hl"):
                    hit.update({k: v for k, v in _op(
                        kind, w["id"], float(hit["pos"]), float(hit["w"]),
                        leaves, st).items() if k not in ("pos", "w",
                                                         "wall")})
                    rep["doors" if kind == "door" else "windows"] += 1
                    rep.setdefault("typed", []).append(hit)
                return
            wd = min(wd, Lw - 0.24)
            pos = min(max(pos, wd / 2 + 0.11), Lw - wd / 2 - 0.11)
            if wd < 0.3:
                return
            new_o.append(_op(kind, w["id"], pos, wd, leaves, st))
        else:
            u = _u(p, q)
            ext = 0.12                         # into the walls at its ends
            a = (round(p[0] - u[0] * ext, 4), round(p[1] - u[1] * ext, 4))
            b = (round(q[0] + u[0] * ext, 4), round(q[1] + u[1] * ext, 4))
            rec = {"kind": "line", "a": list(a), "b": list(b),
                   "t": round(t * 200) / 200, "align": "centre", "side": 1,
                   "height": "level", "base": 0.0, "level": lid,
                   "bridge": kind}
            w = M.new_walls(arch["walls"] + new_w, [rec])[0]
            new_w.append(w)
            rep["bridges"] += 1
            new_o.append(_op(kind, w["id"], L / 2 + ext, L, leaves, st))
        rep["doors" if kind == "door" else "windows"] += 1

    # the piers first: solids the glazing may stand between
    prs = piers(pl, is_wall, walls)
    solids = None
    try:
        from shapely.geometry import LineString, Polygon
        from shapely.ops import unary_union
        from .engine import structure as S_
        sl = [LineString([w["a"], w["b"]]).buffer(float(w["t"]) / 2,
                                                   cap_style=2)
              for w in walls if math.dist(w["a"], w["b"]) > 1e-6]
        for c in arch["structure"]:
            if c["type"] == "column" and c["level"] == lid:
                try:
                    sl.append(Polygon(S_.column_outline(c)).buffer(0))
                except Exception:  # noqa: BLE001
                    continue
        sl += prs
        # and the plan's own lines on the wall layers (a pier drawn as a
        # few lines, a jamb's return)
        lay = pl["layers"]
        sl += [LineString([(s_[0], s_[1]), (s_[2], s_[3])]).buffer(0.03)
               for s_ in pl["segs"] if (is_wall(lay[s_[4]]) or (
                   is_col is not None and is_col(lay[s_[4]]))) and
               math.dist((s_[0], s_[1]), (s_[2], s_[3])) > 0.05]
        solids = unary_union(sl).buffer(0.25) if sl else None
    except Exception:  # noqa: BLE001
        solids = None
    for a, b, n in door_symbols(pl, is_door):
        t = _near_t(walls, (a, b), 0.115)
        add(a, b, "door", t, n)
    for p, q, depth in window_bands(pl, is_win, is_line):
        t = min(max(depth + 0.02, 0.115), 0.46)
        add(p, q, "window", t)
    arch["walls"] += new_w
    rep["_new"] = new_o                  # the caller types and adds them
    # the piers: solids between the bands
    if prs:
        from .engine import structure as S
        recs = []
        for p in prs:
            c = p.centroid
            pts = [[round(x - c.x, 4), round(y - c.y, 4)]
                   for x, y in list(p.exterior.coords)[:-1]]
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            recs.append({"type": "column", "level": lid,
                         "x": round(c.x, 4), "y": round(c.y, 4),
                         "shape": "poly", "w": round(max(xs) - min(xs), 3),
                         "d": round(max(ys) - min(ys), 3), "angle": 0.0,
                         "anchor": "centre", "base": 0.0, "pts": pts,
                         "height": "level", "fit": False, "pier": True})
        recs = [r for r in recs if S.why_not(r) is None]
        arch["structure"] += M.new_elements(arch["structure"], recs)
        rep["piers"] = len(recs)
    return rep


def _op(kind, wid, pos, w, leaves, st):
    door = kind == "door"
    return {"kind": kind, "wall": wid, "pos": round(pos, 4),
            "w": round(w, 3),
            "h": float(st["door_h"] if door else st["win_h"]),
            "sill": 0.0 if door else float(st["sill"]),
            "swing": "left", "face": 1,
            "style": ("double" if leaves == 2 else "hinged") if door
            else st.get("win_style", "sliding")}
