# SPDX-License-Identifier: GPL-3.0-or-later
"""The «line» layer, read by where its lines lie:

* inside a wall's thickness, along it — a CNC grille (jali) set in that
  wall's opening (the opening gets the grille; a wall with no opening
  there gets one, a grille in it);
* closing round an area — a low platform (a plinth, a planter's bed, an
  ablution's seats, the compound's paving) at the level its notes give
  («LEV+1'-0"»; several notes: each part at its nearest), else 1'-6"
  over the floor under it; a closed strip thinner than 0.4 m is a low
  wall;
* anything else, outside the walls — a low wall (a pair of lines its two
  faces; one line alone, a 4½" wall on it).

``analyze`` keeps what it read in ``doc["lowparts"][level]``; ``groups``
builds them (with the grilles).
"""
from __future__ import annotations

import math

LOW_WALL_H = 0.6096        # 2'-0"
LOW_WALL_T = 0.1143        # 4½"
PLAT_H = 0.4572            # 1'-6"


def _u(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 1e-9 else (1.0, 0.0)


def _adiff(u, v):
    c = abs(u[0] * v[0] + u[1] * v[1])
    return math.degrees(math.acos(min(1.0, c)))


def analyze(doc, lid, pl, is_line) -> dict:
    """Read the level's «line» layer (see the module). The report."""
    from shapely.geometry import LineString, MultiPoint, Point, Polygon
    from shapely.ops import polygonize_full, unary_union, voronoi_diagram

    from . import project as PJ
    from . import slabedges as SE
    from .engine import model as M
    from .engine import walls as W
    arch = doc["arch"]
    st = doc["settings"]
    rep = {"grilles": 0, "low_walls": 0, "platforms": 0}
    lay = pl["layers"]
    segs = [((s[0], s[1]), (s[2], s[3])) for s in pl["segs"]
            if is_line(lay[s[4]]) and math.dist((s[0], s[1]),
                                                (s[2], s[3])) > 0.05]
    loops = [lp["pts"] for lp in pl.get("loops") or ()
             if is_line(lp["layer"]) and len(lp["pts"]) >= 3]
    doc.setdefault("lowparts", {}).pop(lid, None)
    if not segs and not loops:
        return rep
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and W.why_not(w) is None]
    ops = [o for o in arch["openings"]
           if o["wall"] in {w["id"] for w in walls}]
    # 1. in a wall, along it: a grille in its opening
    rest = []
    new_o = []
    for a, b in segs:
        L = math.dist(a, b)
        u = _u(a, b)
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        host = None
        for w in walls:
            wa, wb = w["a"], w["b"]
            Lw = math.dist(wa, wb)
            if Lw < 1e-6:
                continue
            uw = _u(wa, wb)
            if _adiff(u, uw) > 5.0:
                continue
            nw = (-uw[1], uw[0])
            off = abs((m[0] - wa[0]) * nw[0] + (m[1] - wa[1]) * nw[1])
            if off > float(w["t"]) / 2 + 0.02:
                continue
            s0 = sorted(((a[0] - wa[0]) * uw[0] + (a[1] - wa[1]) * uw[1],
                         (b[0] - wa[0]) * uw[0] + (b[1] - wa[1]) * uw[1]))
            if s0[1] < 0.05 or s0[0] > Lw - 0.05:
                continue
            host = (w, s0, Lw)
            break
        if host is None:
            rest.append((a, b))
            continue
        w, (s0, s1), Lw = host
        hit = False
        for o in ops + new_o:
            if o["wall"] != w["id"]:
                continue
            p0, p1 = o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2
            if min(p1, s1) - max(p0, s0) > 0.4 * (s1 - s0):
                if not o.get("grille"):
                    o["grille"] = st.get("jali_style", "cnc")
                    rep["grilles"] += 1
                hit = True
        if hit or L < 0.45:
            continue
        # no opening there: a grilled opening, as wide as the line
        s0, s1 = max(s0, 0.11), min(s1, Lw - 0.11)
        if s1 - s0 < 0.3:
            continue
        if any(o["wall"] == w["id"] and abs(o["pos"] - (s0 + s1) / 2) <
               (o["w"] + s1 - s0) / 2 + 0.05 for o in ops + new_o):
            continue
        new_o.append({"kind": "void", "wall": w["id"],
                      "pos": round((s0 + s1) / 2, 4), "w": round(s1 - s0, 3),
                      "h": float(st.get("win_h", 1.2)),
                      "sill": float(st.get("sill", 0.9)), "swing": "left",
                      "face": 1, "style": "",
                      "grille": st.get("jali_style", "cnc")})
        rep["grilles"] += 1
    if new_o:
        arch["openings"] += M.new_openings(arch["openings"], new_o)
    # 2. the rest: closed areas (platforms, thin ones low walls), and the
    # loose lines (low walls)
    lines = [LineString([a, b]) for a, b in rest]
    lines += [LineString(list(p) + [p[0]]) for p in loops]
    if not lines:
        return rep
    try:
        WP = unary_union(SE.wall_polys(walls)) if walls else Polygon()
    except Exception:  # noqa: BLE001
        WP = Polygon()
    floor = unary_union([PJ._poly_of(s_) for s_ in arch["structure"]
                         if s_["type"] == "slab" and s_["level"] == lid
                         and not s_.get("zone")] or [Polygon()])
    polys, cuts, dangles, _inv = polygonize_full(unary_union(lines))
    low_walls, plats = [], []
    used = []
    for p in getattr(polys, "geoms", []):
        if not p.is_valid or p.area < 0.05:
            continue
        r = p.minimum_rotated_rectangle
        cs = list(r.exterior.coords)
        s1, s2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        short, long_ = min(s1, s2), max(s1, s2)
        if short < 0.40 and long_ > 3 * short and p.area > 0.6 * r.area:
            # a closed strip: a low wall as thick as it
            i0 = 0 if s1 >= s2 else 1
            a_, b_ = cs[i0], cs[i0 + 1]
            c_ = cs[(i0 + 2) % 4]
            off = ((c_[0] - b_[0]) / 2, (c_[1] - b_[1]) / 2)
            low_walls.append({"a": [round(a_[0] + off[0], 4),
                                    round(a_[1] + off[1], 4)],
                              "b": [round(b_[0] + off[0], 4),
                                    round(b_[1] + off[1], 4)],
                              "t": round(short, 3)})
            used.append(p)
            continue
        q = p
        if not WP.is_empty:
            q = q.difference(WP)
        # round the building (the compound's paving): the floor's out
        if not floor.is_empty and p.contains(floor.representative_point()):
            q = q.difference(floor.buffer(0.01))
        if q.is_empty or q.area < 0.05:
            continue
        plats.append(q)
    # the loose lines: pairs (two faces of one wall), singles
    loose = []
    for g in (cuts, dangles):
        for ln in getattr(g, "geoms", []):
            if ln.length > 0.25:
                loose.append(ln)
    # merge collinear pieces cut at crossings
    taken = [False] * len(loose)
    for i, ln in enumerate(loose):
        if taken[i]:
            continue
        (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
        u = _u((x0, y0), (x1, y1))
        nv = (-u[1], u[0])
        best = None
        for j in range(i + 1, len(loose)):
            if taken[j]:
                continue
            l2 = loose[j]
            (a0, b0), (a1, b1) = l2.coords[0], l2.coords[-1]
            if _adiff(u, _u((a0, b0), (a1, b1))) > 4.0:
                continue
            m2 = l2.interpolate(0.5, normalized=True)
            gap = abs((m2.x - x0) * nv[0] + (m2.y - y0) * nv[1])
            if not 0.04 <= gap <= 0.35:
                continue
            sa = sorted((x0 * u[0] + y0 * u[1], x1 * u[0] + y1 * u[1]))
            sb = sorted((a0 * u[0] + b0 * u[1], a1 * u[0] + b1 * u[1]))
            ov = min(sa[1], sb[1]) - max(sa[0], sb[0])
            if ov < 0.6 * min(sa[1] - sa[0], sb[1] - sb[0]):
                continue
            if best is None or gap < best[0]:
                best = (gap, j, ov, sa, sb)
        if best is not None:
            gap, j, _ov, sa, sb = best
            taken[i] = taken[j] = True
            lo, hi = max(sa[0], sb[0]), min(sa[1], sb[1])
            m2 = loose[j].interpolate(0.5, normalized=True)
            o0 = x0 * nv[0] + y0 * nv[1]
            o1 = m2.x * nv[0] + m2.y * nv[1]
            oc = (o0 + o1) / 2
            p_ = (u[0] * lo + nv[0] * oc, u[1] * lo + nv[1] * oc)
            q_ = (u[0] * hi + nv[0] * oc, u[1] * hi + nv[1] * oc)
            low_walls.append({"a": [round(p_[0], 4), round(p_[1], 4)],
                              "b": [round(q_[0], 4), round(q_[1], 4)],
                              "t": round(gap, 3)})
        else:
            # one line alone is an edge (a step, a change of floor, the
            # paving's), never a wall: only two faces paired, or a closed
            # strip, make a low wall
            taken[i] = True
    # the platforms' levels: their notes (each part to its nearest), else
    # PLAT_H over what is under them
    notes = []
    base = None
    try:
        f = PJ.cad_floor(doc["marks"].get(lid), PJ.note_weight(doc, lid))
        if f and f[0] == "rel":
            base = f[1]
            notes = [(x, y, v) for x, y, v in PJ.note_levels(doc, lid)
                     if floor.is_empty or not floor.contains(Point(x, y))]
    except Exception:  # noqa: BLE001
        notes = []
    out_p = []
    try:
        from shapely.ops import unary_union as _uu
        allb = _uu([q for q in plats if not q.is_empty]).bounds
    except Exception:  # noqa: BLE001
        allb = None
    for q in plats:
        for pg in getattr(q, "geoms", [q]):
            if pg.geom_type != "Polygon" or pg.area < 0.05:
                continue
            if pg.area < 0.5:
                continue                 # a tile, a jali's box: no floor
            if allb is not None and pg.area > 30.0:
                b_ = pg.bounds
                edge = sum(1 for k_ in range(4)
                           if abs(b_[k_] - allb[k_]) < 0.3)
                if edge >= 3:
                    rep["site_skipped"] = rep.get("site_skipped", 0) + 1
                    continue             # the plot's own open ground round
                                         # the building: the site, no floor
            here = [(x, y, v) for x, y, v in notes
                    if pg.contains(Point(x, y))]
            if not here:
                continue                 # no level written in it: none
            # one area, one level: the level written in it most often (the
            # lowest of those alike) — no line drawn, no level split
            from collections import Counter as _C
            cnt = _C(round(v, 3) for _x, _y, v in here)
            v0 = min(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            parts = [(pg, v0)]
            for part, v in parts:
                for g in getattr(part, "geoms", [part]):
                    if g.geom_type != "Polygon" or g.area < 0.05:
                        continue
                    out_p.append({
                        "pts": [[round(x, 4), round(y, 4)] for x, y in
                                list(g.exterior.coords)[:-1]],
                        "holes": [[[round(x, 4), round(y, 4)] for x, y in
                                   list(h.coords)[:-1]] for h in g.interiors],
                        "v": None if v is None or base is None
                        else round(v - base, 4)})
    doc["lowparts"][lid] = {"walls": low_walls, "plats": out_p}
    rep["low_walls"] = len(low_walls)
    rep["platforms"] = len(out_p)
    return rep


# ---- building ---------------------------------------------------------------------
JALI_STYLES = ("cnc", "cnc_square", "cnc_round", "cnc_hex", "cnc_star",
               "cnc_lattice")
#: 3.64.78: decorated wrought-iron grilles (bars with spear heads, scrolls,
#: rings, a frame that follows an arch) — «ms» is the scroll one
WI_STYLES = ("ms", "wi_scroll", "wi_spear", "wi_circle")
_WI_CACHE = {}


def _spiral(cx, cy, r0, r1, turns, a0, sgn, n=26):
    """A spiral of the scroll: from radius r1 (outer) in to r0, ``turns``
    turns, starting at angle a0, turning ``sgn`` (+1 / -1)."""
    pts = []
    for i in range(n + 1):
        f = i / n
        r = r1 + (r0 - r1) * f
        a = a0 + sgn * turns * 2 * math.pi * f
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _wi_shape(W_, H_, style, arch_rise=0.0):
    """The 2D shape [0, W_] × [0, H_] of a wrought-iron window grille:
    frame, vertical bars with spear heads, a mid rail, and (by style) the
    S-scrolls and rings in the upper zone."""
    key = (round(W_, 2), round(H_, 2), style, round(arch_rise, 2))
    if key in _WI_CACHE:
        return _WI_CACHE[key]
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import unary_union
    bw, bar = 0.035, 0.017
    clip = box(0, 0, W_, H_)
    if arch_rise > 0.05:
        rs = min(arch_rise, W_ / 2.0, H_ * 0.6)
        spring = H_ - rs
        top = Polygon([(W_ / 2 + (W_ / 2) * math.cos(math.pi * k / 24),
                        spring + rs * math.sin(math.pi * k / 24))
                       for k in range(25)])
        clip = unary_union([box(0, 0, W_, spring), top])
    inner = clip.buffer(-bw, join_style=2)
    if inner.is_empty:
        return clip
    parts = [clip.difference(inner)]                       # the frame
    x0, x1, y0, y1 = 0.0, W_, 0.0, H_
    zone = 0.58 if style != "wi_spear" else 1.0     # the scroll zone starts
    ymid = H_ * zone
    rail = 0.022
    nb = max(2, int(round(W_ / 0.13)))
    gap = W_ / nb
    for i in range(1, nb):                                  # the bars
        x = gap * i
        parts.append(box(x - bar / 2, y0, x + bar / 2, y1))
    if style in ("ms", "wi_scroll", "wi_circle") and H_ > 0.7:
        # the upper zone: clear the bars there, set scrolls and rings
        zone_poly = box(bw, ymid + rail, W_ - bw, H_ - bw)
        zone_poly = zone_poly.intersection(inner)
        parts = [g.difference(zone_poly) if g is not parts[0] else g
                 for g in parts]
        parts.append(box(bw, ymid - rail / 2, W_ - bw, ymid + rail / 2))
        nbay = max(1, int(round(W_ / 0.42)))
        bw_ = (W_ - 2 * bw) / nbay
        hz = H_ - bw - ymid - rail
        for j in range(nbay):
            cx = bw + bw_ * (j + 0.5)
            cy = ymid + rail + hz / 2
            r = max(0.06, min(bw_ * 0.30, hz * 0.38))
            for sg in (-1, 1):
                c = (cx + sg * r * 1.0, cy)
                pts = _spiral(c[0], c[1], r * 0.18, r, 1.25,
                              math.pi if sg > 0 else 0.0, -sg)
                parts.append(LineString(pts).buffer(bar * 0.6, cap_style=1,
                                                    resolution=2))
            parts.append(Point(cx, cy).buffer(r * 0.34, resolution=6)
                         .difference(Point(cx, cy).buffer(r * 0.34 - bar,
                                                          resolution=6)))
            # S joining the bay's top and bottom rails
            parts.append(LineString([(cx, ymid + rail), (cx, cy - r * 0.36)])
                         .buffer(bar / 2, cap_style=2))
            parts.append(LineString([(cx, cy + r * 0.36),
                                     (cx, H_ - bw)]).buffer(bar / 2,
                                                           cap_style=2))
            if style == "wi_circle":
                parts.append(Point(cx, cy).buffer(r * 1.55, resolution=8)
                             .difference(Point(cx, cy).buffer(
                                 r * 1.55 - bar, resolution=8)))
        # a lower rail and a row of small rings between the bars' feet
        parts.append(box(bw, bw, W_ - bw, bw + rail))
    else:
        parts.append(box(bw, H_ * 0.5 - rail / 2, W_ - bw, H_ * 0.5 + rail / 2))
        parts.append(box(bw, bw, W_ - bw, bw + rail))
    # spear heads over the bars at the top of the lower zone (or the top)
    ytop = ymid - rail / 2 if style in ("ms", "wi_scroll", "wi_circle") and \
        H_ > 0.7 else H_ - bw - 0.10
    for i in range(1, nb):
        x = gap * i
        if style == "wi_spear" or ytop < H_ - bw - 0.01:
            parts.append(Polygon([(x - 0.04, ytop), (x, ytop + 0.10),
                                  (x + 0.04, ytop)]))
    shape = unary_union([g for g in parts if g is not None
                         and not g.is_empty]).intersection(clip)
    if shape.is_empty:
        shape = clip.difference(inner)
    _WI_CACHE[key] = shape
    return shape


def _jali_holes(style, W_, yb, hh, rim):
    """The cut-outs of one jali panel [0, W_] × [yb, yb + hh] in a pattern:
    cnc (diamonds), cnc_square, cnc_round, cnc_hex (staggered), cnc_star
    (8-point stars) or cnc_lattice (basket-weave slots)."""
    import math as _m

    from shapely.geometry import Polygon
    from shapely import affinity

    def ngon(cx, cy, r, k, rot=0.0):
        return Polygon([(cx + r * _m.cos(rot + 2 * _m.pi * i / k),
                         cy + r * _m.sin(rot + 2 * _m.pi * i / k))
                        for i in range(k)])

    if style == "cnc_hex":
        px, py, stag = 0.15, 0.13, True
    elif style == "cnc_star":
        px, py, stag = 0.19, 0.19, False
    elif style == "cnc_lattice":
        px, py, stag = 0.16, 0.16, False
    elif style == "cnc_square":
        px, py, stag = 0.15, 0.15, False
    elif style == "cnc_round":
        px, py, stag = 0.15, 0.15, False
    else:
        px, py, stag = 0.16, 0.16, False
    nx, ny = int((W_ - 2 * rim) / px), int((hh - 2 * rim) / py)
    if nx < 1 or ny < 1:
        return []
    x0 = (W_ - nx * px) / 2 + px / 2
    y0 = yb + (hh - ny * py) / 2 + py / 2
    out = []
    for j in range(ny):
        sh = px / 2 if (stag and j % 2) else 0.0
        for i in range(nx - (1 if sh else 0)):
            cx, cy = x0 + i * px + sh, y0 + j * py
            if style == "cnc_square":
                h = 0.05
                out.append(Polygon([(cx - h, cy - h), (cx + h, cy - h),
                                    (cx + h, cy + h), (cx - h, cy + h)]))
            elif style == "cnc_round":
                out.append(ngon(cx, cy, 0.052, 14))
            elif style == "cnc_hex":
                out.append(ngon(cx, cy, 0.06, 6, _m.pi / 6))
            elif style == "cnc_star":
                sq = Polygon([(cx - 0.05, cy - 0.05), (cx + 0.05, cy - 0.05),
                              (cx + 0.05, cy + 0.05), (cx - 0.05, cy + 0.05)])
                out.append(sq.union(affinity.rotate(sq, 45, (cx, cy))))
            elif style == "cnc_lattice":
                if (i + j) % 2:
                    out.append(Polygon([(cx - 0.06, cy - 0.018),
                                        (cx + 0.06, cy - 0.018),
                                        (cx + 0.06, cy + 0.018),
                                        (cx - 0.06, cy + 0.018)]))
                else:
                    out.append(Polygon([(cx - 0.018, cy - 0.06),
                                        (cx + 0.018, cy - 0.06),
                                        (cx + 0.018, cy + 0.06),
                                        (cx - 0.018, cy + 0.06)]))
            else:
                h = 0.055
                out.append(Polygon([(cx - h, cy), (cx, cy - h),
                                    (cx + h, cy), (cx, cy + h)]))
    return out


def _grille_faces(w, o, z0, out_sign=None):
    """A CNC grille (jali) panel filling the opening ``o`` of wall ``w``:
    a 30 mm panel cut with a diamond lattice, in the wall's middle — a
    window's on its outer side."""
    from shapely import affinity
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    from . import project as PJ
    a, b = w["a"], w["b"]
    u = _u(a, b)
    n = (-u[1], u[0])
    t = float(w["t"])
    s0 = float(o["pos"]) - float(o["w"]) / 2
    s1 = float(o["pos"]) + float(o["w"]) / 2
    zb = float(o.get("sill", 0.0))
    zt = zb + float(o["h"])
    th = 0.03
    off = 0.0
    side = o.get("grille_side") or "exterior"
    if out_sign is None:              # no rooms to tell: the face's back
        out_sign = -(1 if o.get("face", 1) >= 0 else -1)
    edge = t / 2 - th / 2 - 0.005     # flush with the wall's face
    if side == "exterior":
        off = edge * out_sign
    elif side == "interior":
        off = -edge * out_sign
    W_, H_ = s1 - s0, zt - zb
    if W_ < 0.2 or H_ < 0.2:
        return []
    rim = 0.04
    if o.get("grille") in WI_STYLES:           # 3.64.78: wrought iron
        rise = 0.0
        if o.get("head") == "arch" or o.get("arch"):
            rise = W_ / 2.0
        shp = _wi_shape(W_, H_, o["grille"], rise)
        faces = PJ._prism(shp, 0.0, 0.026, 0.0001)
        out = []
        th = 0.026
        for f in faces:
            loop = [(a[0] + u[0] * (s0 + x) + n[0] * (off + z - th / 2),
                     a[1] + u[1] * (s0 + x) + n[1] * (off + z - th / 2),
                     z0 + zb + y) for x, y, z in f["loop"]]
            hs = [[(a[0] + u[0] * (s0 + x) + n[0] * (off + z - th / 2),
                    a[1] + u[1] * (s0 + x) + n[1] * (off + z - th / 2),
                    z0 + zb + y) for x, y, z in h]
                  for h in f.get("holes") or []]
            out.append({"loop": list(reversed(loop)),
                        "holes": [list(reversed(h)) for h in hs]})
        return out
    sty = o.get("grille") if o.get("grille") in JALI_STYLES else "cnc"
    # in panels at most ~1.2 m high (the jali's own frames): each face keeps
    # a few dozen holes — a tall window's in one face would take seconds to
    # draw every time the model changes
    k_ = max(1, int(math.ceil(H_ / 1.2)))
    hh = H_ / k_
    faces = []
    for r_ in range(k_):
        yb = r_ * hh
        panel = box(0, yb, W_, yb + hh)
        holes = _jali_holes(sty, W_, yb, hh, rim)
        if holes:
            panel = panel.difference(unary_union(holes))
        faces += PJ._prism(panel, 0.0, th, 0.0001)
    out = []
    for f in faces:
        loop = [(a[0] + u[0] * (s0 + x) + n[0] * (off + z - th / 2),
                 a[1] + u[1] * (s0 + x) + n[1] * (off + z - th / 2),
                 z0 + zb + y) for x, y, z in f["loop"]]
        hs = [[(a[0] + u[0] * (s0 + x) + n[0] * (off + z - th / 2),
                a[1] + u[1] * (s0 + x) + n[1] * (off + z - th / 2),
                z0 + zb + y) for x, y, z in h] for h in f.get("holes") or []]
        # (x, z, y) → (along, up, across) mirrors: the loops turned back
        out.append({"loop": list(reversed(loop)),
                    "holes": [list(reversed(h)) for h in hs]})
    return out


def _outward(arch, w, cache, Point):
    """+1 / -1: the side of wall ``w`` (along its left normal) that faces
    out of the building — the side with no room of its level; None when
    both or neither side has one (an inner wall, an open plan)."""
    lid = w["level"]
    if lid not in cache:
        from shapely.ops import unary_union
        from .engine import spaces
        try:
            ps = [r["poly"] for r in spaces.of_level(arch, lid)]
            cache[lid] = unary_union(ps).buffer(0.02) if ps else None
        except Exception:  # noqa: BLE001
            cache[lid] = None
    U = cache[lid]
    if U is None:
        return None
    a, b = w["a"], w["b"]
    u = _u(a, b)
    n = (-u[1], u[0])
    d = float(w["t"]) / 2 + 0.2
    ins = []
    for f in (0.25, 0.5, 0.75):
        mx = a[0] + (b[0] - a[0]) * f
        my = a[1] + (b[1] - a[1]) * f
        ins.append((U.contains(Point(mx + n[0] * d, my + n[1] * d)),
                    U.contains(Point(mx - n[0] * d, my - n[1] * d))))
    lp = sum(1 for x, _ in ins if x)
    rp = sum(1 for _, y in ins if y)
    if lp > rp:
        return -1
    if rp > lp:
        return 1
    return None


def _ring_faces(w, o, z0):
    """An arched opening's voussoirs on both faces of its wall: ablaq —
    dark and light stones in turn — or one plain band."""
    from shapely.geometry import Polygon

    from . import project as PJ
    from .engine import structure as S
    a, b = w["a"], w["b"]
    u = _u(a, b)
    n = (-u[1], u[0])
    t = float(w["t"])
    s0 = float(o["pos"]) - float(o["w"]) / 2
    s1 = float(o["pos"]) + float(o["w"]) / 2
    zs = float(o.get("sill", 0.0))
    zt = zs + float(o["h"])
    rise = min(S.head_size(o), zt - zs - 0.05)
    if rise <= 0.02:
        return []
    zsp = zt - rise
    sty = o.get("arch") or "semi"
    rw = min(max(0.16 * float(o["w"]), 0.18), 0.6)
    k = 16
    inner = S.arch_pts(s0, s1, zsp, zt, k, sty)
    outer = S.arch_pts(s0 - rw, s1 + rw, zsp, zt + rw, k, sty)
    if len(inner) != len(outer) or len(inner) < 3:
        return []
    ablaq = o.get("ring") == "ablaq"
    dark, light = (0.22, 0.20, 0.20), (0.94, 0.92, 0.86)
    out = []
    m = len(inner)
    step = 1 if m <= 24 else 2
    blocks = [(i, min(i + step, m - 1)) for i in range(0, m - 1, step)]
    th = 0.025
    for bi, (i, j) in enumerate(blocks):
        poly = Polygon(inner[i:j + 1] + list(reversed(outer[i:j + 1])))
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area < 1e-5:
            continue
        col = (dark if bi % 2 else light) if ablaq else light
        for side in (1, -1):
            off = side * (t / 2 + th / 2)
            for f in PJ._prism(poly, -th / 2, th / 2, 1e-6):
                loop = [(a[0] + u[0] * x + n[0] * (off + zz),
                         a[1] + u[1] * x + n[1] * (off + zz), z0 + y)
                        for x, y, zz in f["loop"]]
                out.append({"loop": list(reversed(loop)), "holes": [],
                            "color": col})
    return out


GRILLE_COLOR = (0.93, 0.92, 0.88)
LOW_COLOR = (0.88, 0.86, 0.82)


def groups(doc):
    """The low walls, low platforms and grilles of every level."""
    from shapely.geometry import LineString, Point, Polygon

    from core.group import Group
    from . import project as PJ
    from .host import KEY, level_layer
    arch = doc["arch"]
    st = doc["settings"]
    elev = PJ.elevations(arch)
    out = []
    fin = float(st.get("finish_t", 0.0508) or 0.0) \
        if st.get("finish_on", True) else 0.0
    hw = float(st.get("low_wall_h", LOW_WALL_H) or LOW_WALL_H)
    hp = float(st.get("low_plat_h", PLAT_H) or PLAT_H)
    gi = next((i for i, lv in enumerate(arch["levels"])
               if lv.get("kind") == "ground"), None)
    zg = PJ.plot_top(doc) if gi is not None else 0.0
    for i, lv in enumerate(arch["levels"]):
        lid = lv["id"]
        lp = (doc.get("lowparts") or {}).get(lid) or {}
        ground = i == gi
        try:
            from shapely.ops import unary_union
            floor = unary_union([PJ._poly_of(s_) for s_ in arch["structure"]
                                 if s_["type"] == "slab"
                                 and s_["level"] == lid
                                 and not s_.get("zone")] or [Polygon()])
        except Exception:  # noqa: BLE001
            floor = None

        def under(x, y):
            """The top of what a part stands on at (x, y)."""
            if floor is not None and not floor.is_empty and \
                    floor.buffer(0.01).contains(Point(x, y)):
                return elev[i] + PJ.floor_offset_at(doc, lid, (x, y)) + fin
            return zg if ground else elev[i] + fin

        def grp(name, faces, kind, k, color):
            g = Group(PJ._mesh_of(faces), name=f"{name} · {lv['name']}")
            g.component = False
            g.material = {"color": color, "opacity": 1.0}
            g.layer = level_layer(lv["name"])
            g.ifc = {"class": "IfcWall" if kind == "lowwall" else
                     "IfcSlab" if kind == "lowplat" else "IfcMember",
                     "name": name}
            g.ext = {KEY: {"type": "lowpart", "id": f"{kind}-{lid}-{k}",
                           "level": lid}}
            return g
        plats = []
        faces = []
        # never over the steps (they climb from the paving to the doors)
        steps_u = None
        if lp.get("plats") and lv.get("kind") == "ground":
            try:
                from shapely.ops import unary_union as _uu
                sp_ = [pg_ for _n, parts_ in PJ.platform_parts(doc)["steps"]
                       for pg_, _t in parts_]
                steps_u = _uu(sp_).buffer(0.03) if sp_ else None
            except Exception:  # noqa: BLE001
                steps_u = None
        for k, p in enumerate(lp.get("plats") or (), 1):
            try:
                pg = Polygon(p["pts"], p.get("holes") or []).buffer(0)
            except Exception:  # noqa: BLE001
                continue
            if steps_u is not None:
                pg = pg.difference(steps_u)
                if pg.is_empty or pg.area < 0.3:
                    continue
            c = pg.representative_point()
            z0 = under(c.x, c.y)
            top = elev[i] + p["v"] if p.get("v") is not None else z0 + hp
            if top - z0 < 0.02:
                continue
            plats.append((pg, top))
            faces += PJ._prism(pg, min(z0, zg if ground else z0), top)
        if faces:
            out.append(grp("Low platforms (CAD lines)", faces, "lowplat", 0,
                           LOW_COLOR))
        faces = []
        for k, w in enumerate(lp.get("walls") or (), 1):
            a, b = w["a"], w["b"]
            if math.dist(a, b) < 0.1:
                continue
            ln = LineString([a, b])
            m = ln.interpolate(0.5, normalized=True)
            z0 = under(m.x, m.y)
            for pg, top in plats:              # on a platform: from its top
                if pg.buffer(0.02).contains(m):
                    z0 = max(z0, top)
            poly = ln.buffer(max(float(w["t"]), 0.05) / 2, cap_style=2)
            faces += PJ._prism(poly, z0, z0 + hw, 0.002)
        if faces:
            out.append(grp("Low walls (CAD lines)", faces, "lowwall", 0,
                           LOW_COLOR))
    # the grilles in the openings
    walls = {w["id"]: w for w in arch["walls"]}
    lvi = {lv["id"]: i for i, lv in enumerate(arch["levels"])}
    by_lv = {}
    rooms_of = {}
    for o in arch["openings"]:
        if o.get("grille") in (None, "", "none", False):
            continue                     # («none» picked: no jali)
        w = walls.get(o["wall"])
        if w is None or w.get("kind", "line") != "line":
            continue
        z0 = elev[lvi[w["level"]]] + float(w.get("base", 0.0) or 0.0)
        try:
            sg = _outward(arch, w, rooms_of, Point)
        except Exception:  # noqa: BLE001
            sg = None
        try:
            by_lv.setdefault(w["level"], []).extend(
                _grille_faces(w, o, z0, sg))
        except Exception:  # noqa: BLE001
            continue
    rings = {}
    for o in arch["openings"]:
        if o.get("head") != "arch" or o.get("ring") not in ("ablaq", "plain"):
            continue
        w = walls.get(o["wall"])
        if w is None or w.get("kind", "line") != "line":
            continue
        z0 = elev[lvi[w["level"]]] + float(w.get("base", 0.0) or 0.0)
        try:
            rings.setdefault(w["level"], []).extend(_ring_faces(w, o, z0))
        except Exception:  # noqa: BLE001
            continue
    for lid, faces in rings.items():
        if not faces:
            continue
        lv = arch["levels"][lvi[lid]]
        g = Group(PJ._mesh_of(faces), name=f"Arch voussoirs · {lv['name']}")
        g.component = False
        g.material = {"color": (0.94, 0.92, 0.86), "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ifc = {"class": "IfcMember", "name": "Arch voussoirs"}
        g.ext = {KEY: {"type": "lowpart", "id": f"rings-{lid}",
                       "level": lid}}
        out.append(g)
    for lid, faces in by_lv.items():
        if not faces:
            continue
        lv = arch["levels"][lvi[lid]]
        g = Group(PJ._mesh_of(faces), name=f"CNC grilles · {lv['name']}")
        g.component = False
        g.material = {"color": GRILLE_COLOR, "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ifc = {"class": "IfcMember", "name": "CNC grille"}
        g.ext = {KEY: {"type": "lowpart", "id": f"grille-{lid}",
                       "level": lid}}
        out.append(g)
    return out
