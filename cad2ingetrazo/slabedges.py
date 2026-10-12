# SPDX-License-Identifier: GPL-3.0-or-later
"""The slab's edges: a slab extended out to its walls, to the railings
the CAD draws (the rail layer) and to the projections it draws in hidden
(dashed) lines; railings set on its free edges; sun shades (chajjas) over
the windows; the floor finish carried out to the slab's edge; granite
thresholds in the door openings; an opening in the slab closed.

``doc["sunshades"]`` = {level id: {"d": depth, "t": thickness, "ext":
past each jamb}} — the floors whose outer windows wear a sun shade.
"""
from __future__ import annotations

import math
import re

#: dashed lines on these layers never mark a slab's projection
NOT_EDGE = re.compile(
    r"CEIL|GRID|GIRD|AXIS|FURN|PIPE|DIM|TEXT|SECTION|HATCH|SPLIT|FIXT|"
    r"EQUIP|TREE|LANDSC|SYMB|ARROW|LIGHT|ELEC|PLUMB|SANIT|DUCT|BEAM|PLOT|"
    r"SITE|BOUND|SETBACK|ROAD|STAIR|PARK|RAMP|DOOR|SWING|WIN", re.I)
GRANITE = (0.20, 0.20, 0.22, 1.0)
SHADE = (0.80, 0.80, 0.78, 1.0)
RAIL_H = 1.0668                      # 3'-6"


# ---- geometry helpers ---------------------------------------------------------
def _poly(pts):
    from shapely.geometry import Polygon
    p = Polygon([tuple(q[:2]) for q in pts])
    return p if p.is_valid else p.buffer(0)


def _largest(g, near=None):
    if g.is_empty:
        return None
    ps = [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon"]
    if not ps:
        return None
    if near is not None:
        hit = [p for p in ps if p.contains(near)]
        if hit:
            return hit[0]
    return max(ps, key=lambda p: p.area)


def _ring_pts(p) -> list:
    if p.geom_type != "Polygon":
        p = max(getattr(p, "geoms", [p]), key=lambda q: q.area)
    pts = list(p.simplify(0.005).exterior.coords)[:-1]
    a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
            in zip(pts, pts[1:] + pts[:1]))
    if a < 0:
        pts = pts[::-1]
    return [[round(x, 4), round(y, 4)] for x, y in pts]


def wall_polys(walls) -> list:
    """The walls' footprints (shapely), as built."""
    from .engine import walls as W
    out = []
    plans = W.plan([w for w in walls if not w.get("rail")])
    for pcs in plans.values():
        for pc in pcs:
            try:
                p = _poly(pc["outer"])
                if not p.is_empty:
                    out.append(p)
            except Exception:  # noqa: BLE001
                continue
    return out


def floor_level_of(doc, slab) -> str:
    """The level a slab is the floor of: its own, or for a slab cast over
    a floor (``top``), the floor above it."""
    lid = slab["level"]
    if not slab.get("top"):
        return lid
    from .engine import model as M
    arch = doc["arch"]
    el = M.elevations(arch)
    order = [arch["levels"][i]["id"] for i in
             sorted(range(len(arch["levels"])), key=lambda i: el[i])]
    k = order.index(lid) if lid in order else -1
    return order[k + 1] if 0 <= k < len(order) - 1 else lid


def _walls_for(doc, slab) -> list:
    arch = doc["arch"]
    fl = floor_level_of(doc, slab)
    ws = [w for w in arch["walls"] if w["level"] == fl]
    if not ws and fl != slab["level"]:
        ws = [w for w in arch["walls"] if w["level"] == slab["level"]]
    return ws


# ---- extend -------------------------------------------------------------------
def extend_to_walls(doc, slab) -> bool:
    """The slab grown out to the outer faces of the walls it carries (those
    standing on it or at its edge). True when its outline changed."""
    from shapely.ops import unary_union
    sp = _poly(slab["corners"])
    if sp.is_empty:
        return False
    reach = sp.buffer(1.0)
    ws = [p for p in wall_polys(_walls_for(doc, slab)) if p.intersects(reach)]
    if not ws:
        return False
    u = unary_union([sp] + ws).buffer(0.03, join_style=2).buffer(
        -0.03, join_style=2)
    p = _largest(u, sp.representative_point())
    if p is None or p.area <= sp.area + 0.01:
        return False
    slab["corners"] = _ring_pts(p)
    return True


def extend_to_selected(doc, slab, wall_ids, reach=12.0) -> int:
    """The slab carried out to the walls picked (on any level): each wall's
    footprint and the strip between it and the slab joined to the slab —
    the hull of the wall and the slab's nearby edge, so a wall standing
    off the slab (a boundary wall, a balcony's end wall) is reached too.
    The number of walls it reached."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    from .engine import walls as W
    sp = _poly(slab["corners"])
    if sp.is_empty:
        return 0
    arch = doc["arch"]
    ids = set(wall_ids)
    picked = [w for w in arch["walls"] if w["id"] in ids]
    if not picked:
        return 0
    polys = {}
    for lid in {w["level"] for w in picked}:
        mine = [w for w in arch["walls"] if w["level"] == lid
                and not w.get("rail")]
        for wid, pcs in W.plan(mine).items():
            if wid in ids:
                for pc in pcs:
                    try:
                        polys.setdefault(wid, []).append(_poly(pc["outer"]))
                    except Exception:  # noqa: BLE001
                        pass
    adds, n = [], 0
    for w in picked:
        ps = polys.get(w["id"])
        if not ps:                      # a railing / curved wall: its line
            try:
                ps = [LineString([tuple(q) for q in W.points_of(w)]).buffer(
                    max(float(w["t"]) / 2, 0.03), cap_style=2)]
            except Exception:  # noqa: BLE001
                continue
        wp = unary_union(ps)
        d = wp.distance(sp)
        if d > reach:
            continue
        near = sp.intersection(wp.buffer(d + 0.05, join_style=2))
        adds.append(unary_union([wp, near]).convex_hull if not near.is_empty
                    else wp)
        n += 1
    if not adds:
        return 0
    u = unary_union([sp] + adds).buffer(0.01, join_style=2).buffer(
        -0.01, join_style=2)
    p = _largest(u, sp.representative_point())
    if p is None or p.area <= sp.area + 0.01:
        return 0
    slab["corners"] = _ring_pts(p)
    return n


def extend_outline(outline, lines, reach=4.0, half=0.06) -> list:
    """An outline grown to the lines drawn round it within ``reach`` (the
    railings, the dashed projections): the gap between them and the
    building filled. The outline as it was when no line is near."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    sp = _poly(outline)
    if sp.is_empty or not lines:
        return outline
    inside = sp.buffer(-0.05)
    zone = sp.buffer(reach)
    ls = []
    for a, b in lines:
        if math.dist(tuple(a), tuple(b)) < 0.25:
            continue
        L = LineString([tuple(a[:2]), tuple(b[:2])])
        if not L.intersects(zone) or inside.contains(L):
            continue
        ls.append(L)
    if not ls:
        return outline
    U = unary_union(ls)
    grown = unary_union([sp, U.buffer(half, cap_style=2, join_style=2)])
    R = reach / 2.0 + 0.1
    closed = grown.buffer(R, join_style=2).buffer(-R, join_style=2)
    clip = unary_union([sp, U.buffer(reach, cap_style=2, join_style=2)])
    p = _largest(closed.intersection(clip).buffer(0.01).buffer(-0.01),
                 sp.representative_point())
    if p is None or p.area <= sp.area + 0.05:
        return outline
    return _ring_pts(p)


def rails_from_cad(pl, is_rail, lid, kind="ss_bars", h=RAIL_H) -> list:
    """Railing walls from the lines on the rail layers: a pair of lines a
    rail's width apart → one railing on their centre line; a single line
    → a railing on it."""
    from .engine import walldetect
    lay = pl["layers"]
    segs = [s for s in pl["segs"] if is_rail(lay[s[4]])]
    if not segs:
        return []
    found, _ops = walldetect.walls_from(segs, 0.02, 0.35)
    recs = []
    from shapely.geometry import LineString
    cent = [LineString([a, b]) for a, b, _t in found]
    for a, b, t in found:
        recs.append(((a, b), max(float(t), 0.05)))
    for s in segs:                       # the single lines left over
        L = LineString([(s[0], s[1]), (s[2], s[3])])
        if L.length < 0.3:
            continue
        if any(c.distance(L.interpolate(0.5, normalized=True)) < 0.4
               for c in cent):
            continue
        recs.append((((s[0], s[1]), (s[2], s[3])), 0.05))
    out = []
    for (a, b), t in recs:
        out.append({"kind": "line", "a": [round(a[0], 4), round(a[1], 4)],
                    "b": [round(b[0], 4), round(b[1], 4)],
                    "t": round(min(t, 0.23), 3), "align": "centre",
                    "side": 1, "height": round(h, 4), "base": 0.0,
                    "level": lid, "rail": kind})
    return out


def dashed_lines(pl) -> list:
    """The hidden (dashed) lines of the plan that may mark a slab's
    projection: [((x, y), (x, y))]."""
    dsh = pl.get("dashed") or []
    if len(dsh) != len(pl["segs"]):
        return []
    lay = pl["layers"]
    return [((s[0], s[1]), (s[2], s[3])) for s, d in zip(pl["segs"], dsh)
            if d and not NOT_EDGE.search(lay[s[4]])]


# ---- railings on the slab's free edges -------------------------------------
def free_edges(doc, slab, gap=0.2) -> list:
    """The stretches of the slab's edge no wall stands on: [((x, y), (x,
    y))] counter-clockwise (the slab on their left)."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    pts = [tuple(p) for p in _ring_pts(_poly(slab["corners"]))]
    if len(pts) < 3:
        return []
    ws = wall_polys(_walls_for(doc, slab))
    rails = [LineString([tuple(w["a"]), tuple(w["b"])]).buffer(0.2)
             for w in _walls_for(doc, slab) if w.get("rail") and "a" in w]
    cover = unary_union([p.buffer(gap) for p in ws] + rails) \
        if ws or rails else None
    out = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        L = LineString([a, b])
        if L.length < 0.3:
            continue
        rest = L.difference(cover) if cover is not None else L
        for g in getattr(rest, "geoms", [rest]):
            if g.geom_type != "LineString" or g.length < 0.3:
                continue
            c = list(g.coords)
            out.append((c[0], c[-1]))
    return out


def add_edge_rails(doc, slab, kind="ss_bars", h=RAIL_H, t=0.05) -> int:
    """A railing along every free edge of the slab, set in by half its
    width, on the floor the slab carries. The number made."""
    from .engine import model as M
    arch = doc["arch"]
    lid = floor_level_of(doc, slab)
    recs = []
    for a, b in free_edges(doc, slab):
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux                       # into the slab
        o = t / 2 + 0.01
        recs.append({"kind": "line",
                     "a": [round(a[0] + nx * o, 4), round(a[1] + ny * o, 4)],
                     "b": [round(b[0] + nx * o, 4), round(b[1] + ny * o, 4)],
                     "t": t, "align": "centre", "side": 1,
                     "height": round(h, 4), "base": 0.0, "level": lid,
                     "rail": kind})
    if not recs:
        return 0
    made = M.new_walls(arch["walls"], recs)
    n0 = sum(1 for w in arch["walls"] if str(w.get("name", ""))
             .startswith("Balcony railing"))
    for k, w in enumerate(made, 1):
        w["name"] = f"Balcony railing {n0 + k}"
        w["rail"] = kind
    arch["walls"] += made
    return len(made)


def remove_edge_rails(doc, slab) -> int:
    """The railings standing on this slab's edge taken away."""
    from shapely.geometry import LineString
    sp = _poly(slab["corners"])
    edge = sp.exterior.buffer(0.3)
    lid = floor_level_of(doc, slab)
    arch = doc["arch"]
    gone = {w["id"] for w in arch["walls"]
            if w["level"] == lid and w.get("rail") and "a" in w and
            edge.contains(LineString([tuple(w["a"]), tuple(w["b"])]))}
    arch["walls"] = [w for w in arch["walls"] if w["id"] not in gone]
    return len(gone)


# ---- close an opening -----------------------------------------------------------
def close_hole(doc, slab, k) -> bool:
    """The slab's opening ``k`` closed (a hand-drawn shaft forgotten too)."""
    hs = slab.get("holes") or []
    if not 0 <= k < len(hs):
        return False
    h = hs.pop(k)
    for key in ("shafts", "man"):
        if slab.get(key):
            slab[key] = [x for x in slab[key] if x != h]
    hp = _poly(h)
    doc["man_shafts"] = [m for m in doc.get("man_shafts") or []
                         if _poly(m["pts"]).intersection(hp).area <
                         0.5 * max(hp.area, 1e-6)]
    slab.setdefault("closed", []).append(
        [round(hp.centroid.x, 3), round(hp.centroid.y, 3)])
    return True


# ---- sun shades over the windows ----------------------------------------------
def set_sunshades(doc, lid, d=0.6096, t=0.1016, ext=0.1524) -> None:
    doc.setdefault("sunshades", {})[lid] = {
        "d": round(min(max(float(d), 0.15), 2.0), 4),
        "t": round(min(max(float(t), 0.05), 0.3), 4),
        "ext": round(min(max(float(ext), 0.0), 1.0), 4)}


def remove_sunshades(doc, lid) -> None:
    (doc.get("sunshades") or {}).pop(lid, None)


def _footprint(walls):
    from shapely.ops import unary_union
    ps = wall_polys(walls)
    if not ps:
        return None
    u = unary_union(ps).buffer(2.0, join_style=2).buffer(-2.0, join_style=2)
    from shapely.geometry import Polygon
    return unary_union([Polygon(p.exterior) for p in getattr(u, "geoms", [u])
                        if p.geom_type == "Polygon"])


def sunshade_faces(doc, lid, z0) -> list:
    """The faces of the sun shades over the outer windows of a level."""
    from shapely.geometry import Point

    from .engine import structure as S
    from .engine import walls as W
    cfg = (doc.get("sunshades") or {}).get(lid)
    if not cfg:
        return []
    arch = doc["arch"]
    mine = [w for w in arch["walls"] if w["level"] == lid]
    fp = _footprint(mine)
    if fp is None:
        return []
    by = {w["id"]: w for w in mine}
    out = []
    for o in arch["openings"]:
        w = by.get(o["wall"])
        if w is None or o["kind"] != "window" or \
                w.get("kind", "line") != "line" or w.get("rail"):
            continue
        seg = W.centre(w)
        p0, u = seg.p0, seg.u
        n = (-u[1], u[0])
        t2 = float(w["t"]) / 2
        mid = (p0[0] + u[0] * o["pos"], p0[1] + u[1] * o["pos"])
        probe = lambda s: fp.contains(Point(mid[0] + n[0] * s * (t2 + 0.4),  # noqa: E731
                                            mid[1] + n[1] * s * (t2 + 0.4)))
        a_in, b_in = probe(1), probe(-1)
        if a_in == b_in:                   # an inner wall: no shade
            continue
        side = -1 if a_in else 1
        zt = z0 + float(o.get("sill", 0.0)) + float(o["h"])
        s0 = o["pos"] - o["w"] / 2 - cfg["ext"]
        s1 = o["pos"] + o["w"] / 2 + cfg["ext"]
        ca, cb = (t2 - 0.02, t2 + cfg["d"]) if side > 0 else \
            (-t2 - cfg["d"], -t2 + 0.02)
        out += S._box(p0, u, n, s0, s1, ca, cb, zt, zt + cfg["t"], SHADE)
    return out


# ---- floor finish to the slab's edge, granite thresholds ------------------------
def edge_finish_polys(doc, lid, rooms) -> list:
    """The parts of a floor's slab outside its rooms and walls (balconies,
    the slab carried out to its railings, a porch): shapely polygons."""
    from shapely.ops import unary_union

    from . import project as PJ
    arch = doc["arch"]
    slabs = PJ._floor_slabs(doc, lid)
    if not slabs:
        return []
    ps = []
    for s in slabs:
        try:
            p = _poly(s["corners"])
            for h in s.get("holes") or []:
                if len(h) >= 3:
                    p = p.difference(_poly(h))
            ps.append(p)
        except Exception:  # noqa: BLE001
            continue
    if not ps:
        return []
    mine = [w for w in arch["walls"] if w["level"] == lid]
    cut = [r["poly"] for r in rooms] + wall_polys(mine)
    cores = [_poly(e["corners"]) for e in arch["structure"]
             if e["type"] in ("core", "column") and e["level"] == lid
             and e.get("corners")]
    rest = unary_union(ps).difference(unary_union(cut + cores).buffer(0.01))
    return [p for p in getattr(rest, "geoms", [rest])
            if p.geom_type == "Polygon" and p.area >= 0.6 and
            p.minimum_rotated_rectangle.area > 0 and
            min(_mrr_sides(p)) >= 0.4]


def _mrr_sides(p):
    q = list(p.minimum_rotated_rectangle.exterior.coords)
    return (math.dist(q[0], q[1]), math.dist(q[1], q[2]))


def threshold_faces(doc, lid, z0, t, level_at=None) -> list:
    """A granite threshold in every door opening of the level: the door's
    width by the wall's thickness, its top flush with the finished floor
    (the higher of the two rooms it joins when they differ), down to the
    slab. ``level_at(pt)`` → (slab top, finish top) at a point; without it
    the floor at ``z0`` with a finish ``t`` thick."""
    from .engine import structure as S
    from .engine import walls as W
    arch = doc["arch"]
    by = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    out = []
    for o in arch["openings"]:
        w = by.get(o["wall"])
        if w is None or o["kind"] != "door" or \
                w.get("kind", "line") != "line" or float(o.get("sill", 0)) > 0.05:
            continue
        seg = W.centre(w)
        n = (-seg.u[1], seg.u[0])
        t2 = float(w["t"]) / 2
        za, zb = z0, z0 + t
        if level_at is not None:
            c = (seg.p0[0] + seg.u[0] * o["pos"],
                 seg.p0[1] + seg.u[1] * o["pos"])
            lv = []
            for sd in (1, -1):
                q = (c[0] + n[0] * sd * (t2 + 0.3),
                     c[1] + n[1] * sd * (t2 + 0.3))
                try:
                    lv.append(level_at(q))
                except Exception:  # noqa: BLE001
                    pass
            if lv:
                za = min(b for b, _f in lv)
                zb = max(f_ for _b, f_ in lv)
        if zb - za < 0.005:
            continue
        out += S._box(seg.p0, seg.u, n, o["pos"] - o["w"] / 2,
                      o["pos"] + o["w"] / 2, -t2, t2, za, zb, GRANITE)
    return out
