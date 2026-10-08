# SPDX-License-Identifier: GPL-3.0-or-later
"""Staircases from the plans, floor to floor, with their wells cut in the
slabs — and terraces and balconies on any floor.

Where a stair is: a closed outline (or the lines) on a stair layer of the
CAD plan, else a room named STAIR… on the level, else the stair of the
floor below (a stair core goes up the building). A long, narrow well
gets one straight flight; a squarer one a dog-leg — two flights side by
side and a half landing. Risers about 175 mm, goings up to 300 mm.

``doc["stairs"]`` = [{"id", "level" (from), "to", "corners" [4 pts],
                       "kind": "straight" | "dogleg", "risers", "rise",
                       "going", "flip": bool}]
"""
from __future__ import annotations

import math
import uuid

RISER = 0.175
GOING_MAX = 0.30
GOING_MIN = 0.22
STAIR_COLOR = (0.74, 0.73, 0.70)


# ---- where -----------------------------------------------------------------------------
def rect_of(pts):
    """(centre, u (long axis), w (across), L (along)) of the smallest
    rectangle round ``pts``."""
    from shapely.geometry import MultiPoint
    r = MultiPoint([tuple(p[:2]) for p in pts]).minimum_rotated_rectangle
    c = list(r.exterior.coords)[:4]
    e0 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e1 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l0, l1 = math.hypot(*e0), math.hypot(*e1)
    if l0 >= l1:
        u, L, w = (e0[0] / l0, e0[1] / l0), l0, l1
    else:
        u, L, w = (e1[0] / l1, e1[1] / l1), l1, l0
    if u[0] < -1e-9 or (abs(u[0]) < 1e-9 and u[1] < 0):
        u = (-u[0], -u[1])                    # one way round, always
    cx = sum(p[0] for p in c) / 4
    cy = sum(p[1] for p in c) / 4
    return (cx, cy), u, w, L


def corners_of(centre, u, w, L):
    v = (-u[1], u[0])
    cx, cy = centre
    return [[round(cx + a * u[0] * L / 2 + b * v[0] * w / 2, 4),
             round(cy + a * u[1] * L / 2 + b * v[1] * w / 2, 4)]
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def from_cad(pl, match_stairs) -> list:
    """Stair wells in a placed drawing: closed outlines on the stair
    layers (2–40 m²), else the box round the stair layers' lines."""
    out = []
    for lp in pl["loops"]:
        if match_stairs(lp["layer"]):
            a = _area(lp["pts"])
            if 2.0 <= a <= 40.0:
                out.append(lp["pts"])
    if not out:
        lay = pl["layers"]
        segs = [s for s in pl["segs"] if match_stairs(lay[s[4]])]
        if len(segs) >= 6:
            pts = [(s[0], s[1]) for s in segs] + [(s[2], s[3]) for s in segs]
            _c, _u, w, L = rect_of(pts)
            if 2.0 <= w * L <= 40.0:
                out.append(pts)
    return [corners_of(*rect_of(p)) for p in out]


def from_rooms(arch, lid) -> list:
    """Rooms named STAIR… (STAIRCASE, STAIRS, ESCALERA…) on the level."""
    from .engine import spaces
    out = []
    try:
        rooms = spaces.of_level(arch, lid)
    except Exception:  # noqa: BLE001
        return out
    for r in rooms:
        n = str(r.get("name", "")).upper()
        if any(k in n for k in ("STAIR", "ESCAL", "ESCADA", "TREPP",
                                "SCALA")) and 2.0 <= r["area"] <= 60.0:
            poly = r.get("poly")
            pts = list(poly.exterior.coords)[:-1] if poly is not None else None
            if pts:
                out.append(corners_of(*rect_of(pts)))
    return out


def _area(pts):
    return abs(0.5 * sum(a[0] * b[1] - b[0] * a[1]
                         for a, b in zip(pts, list(pts[1:]) + [pts[0]])))


# ---- how --------------------------------------------------------------------------------
def design(corners, H, flip=False) -> dict:
    """Risers, going and kind for a well and a storey height H."""
    _c, _u, w, L = rect_of(corners)
    n = max(int(math.ceil(H / (RISER + 0.005))), 2)
    rise = H / n
    straight_run = (n - 1) * GOING_MIN
    if L >= straight_run + 0.9 or w < 1.6:
        g = min(GOING_MAX, max((L - 0.9) / (n - 1), 0.15))
        return {"kind": "straight", "risers": n, "rise": round(rise, 4),
                "going": round(g, 4), "flip": flip}
    dl = w / 2                                   # half landing, square
    n1 = int(math.ceil(n / 2))
    g = min(GOING_MAX, max((L - dl) / max(n1 - 1, 1), 0.15))
    return {"kind": "dogleg", "risers": n, "rise": round(rise, 4),
            "going": round(g, 4), "flip": flip}


def steps(st, z0) -> list:
    """[(name, footprint [4 pts], z bottom, z top)] — the stair as blocks:
    each step from the floor up to its tread (a solid stair), and the
    landing."""
    (cx, cy), u, w, L = rect_of(st["corners"])
    v = (-u[1], u[0])
    if st.get("flip"):
        v = (-v[0], -v[1])
    o = (cx - u[0] * L / 2 - v[0] * w / 2, cy - u[1] * L / 2 - v[1] * w / 2)

    def P(a, b):                     # a along u from the start, b across
        return (o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b)

    def quad(a0, a1, b0, b1):
        return [P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b1)]
    n, rise, g = st["risers"], st["rise"], st["going"]
    out = []
    if st["kind"] == "straight":
        start = max((L - (n - 1) * g) / 2, 0.0)  # centred in the well
        for k in range(1, n):
            out.append((f"Step {k}", quad(start + (k - 1) * g,
                                          start + k * g, 0.0, w),
                        z0, z0 + k * rise))
        return out
    dl = w / 2
    n1 = int(math.ceil(n / 2))
    n2 = n - n1
    for k in range(1, n1):                       # first flight, side 0…w/2
        out.append((f"Step {k}", quad((k - 1) * g, k * g, 0.0, w / 2 - 0.01),
                    z0, z0 + k * rise))
    out.append(("Landing", quad(L - dl, L, 0.0, w), z0, z0 + n1 * rise))
    for k in range(1, n2):                       # second flight, back
        a1 = L - dl - (k - 1) * g
        out.append((f"Step {n1 + k}", quad(a1 - g, a1, w / 2 + 0.01, w),
                    z0, z0 + (n1 + k) * rise))
    return out


# ---- doing it ---------------------------------------------------------------------------
def auto(doc, cad=None, flip=False) -> dict:
    """Stairs on every floor, as the plans draw them: the tread lines of
    each level's stair layer give the flights (their width, risers, turn
    and landings — completed with a return flight when the plan shows the
    lower flight only); where the plan has no stair lines, a stair well
    (an outline on the stair layer, a room named STAIR…) gets a standard
    stair; a level with neither takes the floor below's. Each stair goes
    up to the next level and cuts its well in that level's slab. Replaces
    the stairs before (and the wells they cut)."""
    from shapely.geometry import Point

    from . import project as PJ
    from .engine import model as M
    from .engine import spaces
    from .engine import structure as S
    arch = doc["arch"]
    _uncut(doc)
    # what each stair set for itself survives a re-make (by where it is)
    kept = {}
    for s0 in doc.get("stairs") or []:
        cs0 = s0.get("corners") or []
        if cs0 and any(s0.get(k) for k in OWN):
            kept[(s0["level"], round(sum(p[0] for p in cs0) / len(cs0), 1),
                  round(sum(p[1] for p in cs0) / len(cs0), 1))] = \
                {k: s0[k] for k in OWN if s0.get(k)}
    doc["stairs"] = []
    levels = arch["levels"]
    info = S.levels_info(arch, M.elevations)
    cad = cad if cad is not None else doc.get("stair_cad") or {}
    made, cut, traced_n = 0, 0, 0
    carried = []
    for i, lv in enumerate(levels):
        up = levels[i + 1] if i + 1 < len(levels) else None
        if up is not None and not any(
                w["level"] == up["id"] for w in arch["walls"]) and \
                not any(e["level"] == up["id"] for e in arch["structure"]):
            up = None                       # nothing built up there yet
        if up is None:
            # the top floor (or nothing above yet): its stairs as the plan
            # draws them, one storey high — no well to cut up there
            if str(lv.get("name", "")).strip().lower() == "roof" or \
                    not any(w["level"] == lv["id"] for w in arch["walls"]):
                continue
            H = float(lv.get("height") or 3.0)
        else:
            H = info[up["id"]]["z0"] - info[lv["id"]]["z0"]
        n_need = max(int(math.ceil(H / (RISER + 0.005))), 2)
        recs = []
        try:
            chains = PJ.stair_trace(doc, lv["id"])
        except Exception:  # noqa: BLE001
            chains = []
        try:
            rooms = spaces.of_level(arch, lv["id"])
        except Exception:  # noqa: BLE001
            rooms = []
        for flights in chains:
            if sum(len(f["lines"]) for f in flights) < 3:
                continue
            m = _mid(flights[0]["lines"][0])
            room = next((r["poly"] for r in rooms
                         if r["poly"].buffer(0.3).contains(Point(m))), None)
            fl, lands = complete(flights, n_need, room)
            n = sum(len(f["lines"]) for f in fl)
            st = {"traced": True, "flights": [
                {"lines": [[list(a), list(b)] for a, b in f["lines"]],
                 "d": list(f["d"]), "w": f["w"], "g": f["g"]} for f in fl],
                "landings": lands, "risers": n, "rise": round(H / n, 4),
                "going": round(fl[0]["g"], 4), "kind": "traced"}
            st["corners"] = outline_of(st)
            recs.append(st)
            traced_n += 1
        if not recs:
            wells = list(cad.get(lv["id"]) or []) or \
                from_rooms(arch, lv["id"])
            for corners in wells:
                recs.append(dict(design(corners, H, flip), corners=corners))
        if not recs and carried:                  # the floor below's stair
            recs = [dict(r) for r in carried]
            for r in recs:
                if r.get("traced"):
                    n = r["risers"]
                    r["rise"] = round(H / n, 4)
        if recs:
            carried = recs
        for r in recs:
            r = dict(r, id=uuid.uuid4().hex[:8], level=lv["id"],
                     to=up["id"] if up is not None else None)
            cs1 = r.get("corners") or []
            if cs1 and kept:
                r.update(kept.get((lv["id"], round(sum(
                    p[0] for p in cs1) / len(cs1), 1), round(sum(
                        p[1] for p in cs1) / len(cs1), 1)), {}))
            doc["stairs"].append(r)
            made += 1
            if PJ.slab_on_top(doc):
                # the slab over this floor is its own: the well in it
                cut += _cut(arch, lv["id"], r["corners"])
            elif up is not None:
                cut += _cut(arch, up["id"], r["corners"])
    return {"stairs": made, "cuts": cut, "traced": traced_n}


def _cut(arch, lid, corners) -> int:
    """The well cut in the level's slab(s) that hold it."""
    from shapely.geometry import Polygon
    hole = Polygon(corners)
    n = 0
    for s in arch["structure"]:
        if s["type"] != "slab" or s["level"] != lid:
            continue
        outer = Polygon(s["corners"])
        if not outer.is_valid:
            outer = outer.buffer(0)
        part = outer.buffer(-0.02).intersection(hole)
        if part.is_empty or part.area < 0.5:
            continue
        holes = s.setdefault("holes", [])
        if any(Polygon(h).intersects(part) for h in holes):
            # an opening drawn there already (the CAD's stair hole):
            # widened to the whole well
            merged = Polygon(part)
            keep = []
            for h in holes:
                if Polygon(h).intersects(merged):
                    merged = merged.union(Polygon(h))
                else:
                    keep.append(h)
            merged = merged.convex_hull.intersection(outer.buffer(-0.02))
            holes[:] = keep
            part = merged
        geom = getattr(part, "geoms", [part])
        for gpart in geom:
            if gpart.geom_type == "Polygon" and gpart.area >= 0.5:
                holes.append([[round(x, 4), round(y, 4)]
                              for x, y in list(gpart.exterior.coords)[:-1]])
                n += 1
    return n


def _uncut(doc) -> None:
    """The wells the stairs before cut, closed again."""
    from shapely.geometry import Polygon
    arch = doc["arch"]
    olds = [Polygon(st["corners"]) for st in doc.get("stairs") or []]
    for s in arch["structure"]:
        if s["type"] != "slab" or not olds:
            continue
        keep = []
        for h in s.get("holes") or []:
            hp = Polygon(h)
            if any(hp.is_valid and o.is_valid and
                   hp.intersection(o).area >= 0.9 * hp.area and
                   hp.area >= 0.5 for o in olds):
                continue
            keep.append(h)
        s["holes"] = keep


#: what one stair may set for itself (else the panel's defaults)
OWN = ("stype", "rail", "rail_h", "rail_sides", "rail_off", "rail_gap",
       "rail_ext")
SIDES = ("inner", "outer", "both", "none")


def _own(st, k, stt, sk, dv):
    v = st.get(k)
    return stt.get(sk, dv) if v is None or v == "" else v


def eff(st, stt) -> dict:
    """The stair's own type and railing, or the defaults."""
    return {"stype": st.get("stype") or stt.get("stair_type", "monolithic"),
            "rail": st.get("rail") or stt.get("stair_rail", "ss_bars"),
            "rail_h": float(st.get("rail_h") or stt.get("stair_rail_h",
                                                       0.9144)),
            "rail_sides": st.get("rail_sides")
            or stt.get("stair_rail_sides", "inner"),
            "rail_off": float(_own(st, "rail_off", stt, "stair_rail_off",
                                   0.05)),
            "rail_gap": float(_own(st, "rail_gap", stt, "stair_rail_gap",
                                   0.0)),
            "rail_ext": float(_own(st, "rail_ext", stt, "stair_rail_ext",
                                   0.0))}


def groups(doc, z_of, layer_of):
    """[(name, stair id, level id, [(faces, colour)…], layer,
    [(faces, colour)…] of its railing)]."""
    stt = doc.get("settings") or {}
    out = []
    for st in doc.get("stairs") or []:
        z0 = z_of.get(st["level"])
        if z0 is None:
            continue
        e = eff(st, stt)
        parts = build(st, z0, e["stype"], float(stt.get("stair_waist", 0.15)),
                      float(stt.get("stair_nosing", 0.025)),
                      float(stt.get("stair_tread", 0.05)), None)
        rails = build_rail(st, z0, e["rail"], e["rail_h"], e["rail_sides"],
                           e["rail_off"], e["rail_gap"], e["rail_ext"])
        out.append((f"Stair {len(out) + 1}", st["id"], st["level"], parts,
                    layer_of(st["level"]), rails))
    return out


def _runs(st, z0, off=0.05):
    """Each flight's two side lines over the nosings, ``off`` in from its
    edges: [(flight, is-left, (x, y, z) foot, (x, y, z) head)]."""
    flights, _landings = as_flights(st)
    rise = st["rise"]
    runs, count = [], 0
    for f in flights:
        lines = [((ln[0][0], ln[0][1]), (ln[1][0], ln[1][1]))
                 for ln in f["lines"]]
        m = len(lines)
        if m < 2:
            count += m
            continue
        a0, b0 = lines[0]
        d = tuple(f["d"])
        wv = math.dist(a0, b0) or float(f["w"])
        r = ((b0[0] - a0[0]) / wv, (b0[1] - a0[1]) / wv)
        ss = [((ln[0][0] + ln[1][0]) / 2 - (a0[0] + b0[0]) / 2) * d[0] +
              ((ln[0][1] + ln[1][1]) / 2 - (a0[1] + b0[1]) / 2) * d[1]
              for ln in lines]
        zb = z0 + count * rise
        o_ = min(max(float(off), 0.0), wv / 2 - 0.05)
        for tside in (o_, wv - o_):
            p_ = _at(a0, d, r, ss[0], tside)
            q_ = _at(a0, d, r, ss[m - 1], tside)
            runs.append((len(runs) // 2, tside < wv / 2,
                         (p_[0], p_[1], zb + rise), (q_[0], q_[1],
                                                     zb + m * rise)))
        count += m
    return runs


def build_rail(st, z0, rail, h=0.9, sides="inner", off=0.05, gap=0.0,
               ext=0.0) -> list:
    """[(faces, colour)] of the stair's railing alone: its type, height,
    sides (inner / outer / both / none), inset from the flight's edge,
    baluster spacing (0 = the type's) and run-on past the first and the
    last nosing."""
    if not rail or rail == "none" or sides == "none":
        return []
    runs = _runs(st, z0, off)
    return railing(st, runs, rail, h, sides, gap, ext, off) if runs else []

def _ccw(loop):
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(loop, loop[1:] + loop[:1]))
    return list(loop) if a >= 0 else list(reversed(loop))


# ---- terraces and balconies ----------------------------------------------------------------
def terrace(doc, lid, h=1.0, t=0.15) -> dict:
    """The roof of the floor below that this floor does not cover becomes
    its terrace: this level's slab grows over it, and a parapet runs on
    its open edges (not where this floor's walls stand)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    arch = doc["arch"]
    ids = [lv["id"] for lv in arch["levels"]]
    i = ids.index(lid)
    if i == 0:
        return {"why": "No floor below this one"}
    below = ids[i - 1]
    bw = [w for w in arch["walls"] if w["level"] == below]
    tw = [w for w in arch["walls"] if w["level"] == lid]
    if not bw or not tw:
        return {"why": "This floor and the one below need walls"}
    bo = S.inside_walls(bw, PJ._outer_loop)
    to = S.inside_walls(tw, PJ._outer_loop)
    if not bo or not to:
        return {"why": "No outline"}
    bp, tp = Polygon(bo), Polygon(to)
    region = bp.difference(tp.buffer(0.01, join_style=2))
    parts = [p for p in getattr(region, "geoms", [region])
             if p.geom_type == "Polygon" and p.area >= 1.0]
    if not parts:
        return {"why": "This floor covers the whole floor below — no terrace"}
    slabs = [e for e in arch["structure"]
             if e["type"] == "slab" and e["level"] == lid
             and not (e.get("zone") or e.get("user") or e.get("roof"))]
    if PJ.slab_on_top(doc):
        # the terrace stands on the slab over the floor below — nothing
        # more over it: this level's own slab (over this floor) kept off
        # the terrace
        open_u = unary_union(parts).buffer(0.005, join_style=2)
        for sl in slabs:
            poly = Polygon(sl["corners"]).buffer(0)
            if not poly.intersects(open_u):
                continue
            rest = poly.difference(open_u)
            g = max(getattr(rest, "geoms", [rest]), key=lambda q: q.area,
                    default=None)
            if g is None or g.is_empty or g.geom_type != "Polygon" or \
                    g.area < 1.0:
                continue
            sl["corners"] = [[round(x, 4), round(y, 4)]
                             for x, y in list(g.simplify(0.005)
                                              .exterior.coords)[:-1]]
            sl["holes"] = [h for h in sl.get("holes") or []
                           if g.contains(Polygon(h).buffer(-0.01))]
    else:
        # the slab of this level (at its floor): over both
        full = unary_union([bp, tp]).buffer(0.001, join_style=2)
        if full.geom_type != "Polygon":
            full = max(full.geoms, key=lambda g: g.area)
        holes = [h for s_ in slabs for h in s_.get("holes") or []]
        arch["structure"] = [e for e in arch["structure"] if e not in slabs]
        t_slab = float(slabs[0]["t"]) if slabs else 0.15
        rec = {"type": "slab", "level": lid,
               "corners": [[round(x, 4), round(y, 4)]
                           for x, y in list(full.exterior.coords)[:-1]],
               "holes": holes, "t": t_slab, "offset": 0.0,
               "shafts": [h for s_ in slabs for h in s_.get("shafts") or []]}
        if S.why_not(rec) is None:
            arch["structure"] += M.new_elements(arch["structure"], [rec])
    # the terrace made before on this level: its parapets go
    arch["walls"] = [w for w in arch["walls"] if not (
        w["level"] == lid and str(w.get("name", "")).startswith("Terrace"))]
    recs = parapet_runs(parts, tp, t, h, lid)
    made = M.new_walls(arch["walls"], recs)
    rk = doc["settings"].get("parapet_rail", "solid")
    for k, w in enumerate(made, 1):
        w["name"] = f"Terrace parapet {k}"
        if rk and rk != "solid":
            w["rail"] = rk
    arch["walls"] += made
    area = sum(p.area for p in parts)
    arch["rooms"] = [r for r in arch["rooms"]
                     if not (r["level"] == lid and r["name"] == "Terrace")]
    arch["rooms"] = M._rooms(arch["rooms"] + [{
        "id": "", "level": lid, "name": "Terrace",
        "x": parts[0].representative_point().x,
        "y": parts[0].representative_point().y}], set(ids))
    return {"area": area, "parapets": len(recs)}


def parapet_runs(parts, tp, t, h, lid) -> list:
    """The parapet walls round the terrace ``parts`` on their open edges:
    each run ONE chain of walls sharing their end points (so the corners
    close clean), set in by half its width from the slab's edge, and
    carried up to the face of this floor's walls where it meets them."""
    from shapely.geometry import LineString, Point
    from shapely.ops import linemerge
    out = []
    near = t / 2 + 0.03                       # the run along this floor
    edge = tp.buffer(near, join_style=2)
    for p in parts:
        inset = p.buffer(-t / 2, join_style=2)
        for g in getattr(inset, "geoms", [inset]):
            if g.geom_type != "Polygon" or g.area < 0.05:
                continue
            ring = LineString(list(g.exterior.simplify(0.01).coords))
            rest = ring.difference(edge)
            if rest.is_empty:
                continue
            if rest.geom_type == "MultiLineString":
                rest = linemerge(rest)
            for run in getattr(rest, "geoms", [rest]):
                if run.geom_type != "LineString" or run.length < 0.2:
                    continue
                pts = [tuple(q) for q in run.coords]
                closed = math.dist(pts[0], pts[-1]) < 1e-6
                if not closed:
                    # an end at this floor's walls: on to their face
                    for k, k2 in ((0, 1), (-1, -2)):
                        a_, b_ = pts[k], pts[k2]
                        if tp.distance(Point(a_)) > near + 0.05:
                            continue
                        L = math.dist(a_, b_) or 1.0
                        ux, uy = (a_[0] - b_[0]) / L, (a_[1] - b_[1]) / L
                        d = tp.exterior.distance(Point(a_)) + 0.01
                        pts[k] = (a_[0] + ux * d, a_[1] + uy * d)
                for a_, b_ in zip(pts, pts[1:]):
                    if math.dist(a_, b_) < 0.05:
                        continue
                    out.append({"kind": "line",
                                "a": [round(a_[0], 4), round(a_[1], 4)],
                                "b": [round(b_[0], 4), round(b_[1], 4)],
                                "t": t, "align": "centre", "side": 1,
                                "height": h, "base": 0.0, "level": lid})
    return out


def balcony(doc, wall_id, depth=1.2, width=0.0, pos=None, h=1.0, t=0.10,
            slab_t=0.15) -> dict:
    """A balcony out of a wall: a slab ``depth`` deep, ``width`` long
    (0 = the wall's length; ``pos`` its centre along the wall, else the
    middle), on the wall's outer side, with a railing round it."""
    from shapely.geometry import Point, Polygon

    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    from .engine import walls as W
    arch = doc["arch"]
    w = next((x for x in arch["walls"] if x["id"] == wall_id), None)
    if w is None or w.get("kind", "line") != "line":
        return {"why": "Select a straight wall"}
    lid = w["level"]
    cl = W.centre(w)
    a, b = cl.at(0.0), cl.at(1.0)
    L = math.dist(a, b)
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    nrm = (-u[1], u[0])
    mine = [x for x in arch["walls"] if x["level"] == lid]
    out = S.inside_walls(mine, PJ._outer_loop)
    poly = Polygon(out) if out else None
    if next((lv["kind"] for lv in arch["levels"] if lv["id"] == lid),
            "floor") != "floor":
        return {"why": "a balcony hangs from an upper floor — select a wall "
                       "of Level 2 or above (its plan: Level list ▸ Plan)"}
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    side_out = []
    for sgn in (1, -1):                     # just past each face
        q = (mid[0] + nrm[0] * sgn * (float(w["t"]) / 2 + 0.06),
             mid[1] + nrm[1] * sgn * (float(w["t"]) / 2 + 0.06))
        side_out.append(poly is None or not poly.buffer(-0.01).contains(
            Point(q)))
    if side_out == [False, False]:
        return {"why": "this wall has rooms on both sides — select an "
                       "outside wall"}
    if not side_out[0]:
        nrm = (-nrm[0], -nrm[1])
    width = L if width <= 0 else min(width, L + 2.0)
    c = L / 2 if pos is None else min(max(pos, 0.0), L)
    face = float(w["t"]) / 2                     # the wall's outer face
    s0, s1 = c - width / 2, c + width / 2
    p = lambda s, d: (a[0] + u[0] * s + nrm[0] * d,  # noqa: E731
                      a[1] + u[1] * s + nrm[1] * d)
    quad = [p(s0, face), p(s1, face), p(s1, face + depth), p(s0, face + depth)]
    rec = {"type": "slab", "level": lid,
           "corners": [[round(x, 4), round(y, 4)] for x, y in quad],
           "holes": [], "t": slab_t, "offset": 0.0}
    why = S.why_not(rec)
    if why:
        return {"why": why}
    arch["structure"] += M.new_elements(arch["structure"], [rec])
    rails = []
    d = depth - t / 2 + face
    for (sa, da), (sb, db) in (((s0 + t / 2, face), (s0 + t / 2, d)),
                               ((s0 + t / 2, d), (s1 - t / 2, d)),
                               ((s1 - t / 2, d), (s1 - t / 2, face))):
        A, B = p(sa, da), p(sb, db)
        rails.append({"kind": "line", "a": [round(A[0], 4), round(A[1], 4)],
                      "b": [round(B[0], 4), round(B[1], 4)], "t": t,
                      "align": "centre", "side": 1, "height": h,
                      "base": 0.0, "level": lid})
    made = M.new_walls(arch["walls"], rails)
    for k, w_ in enumerate(made, 1):
        w_["name"] = f"Balcony railing {k}"
        rk_ = doc["settings"].get("parapet_rail", "solid")
        if rk_ and rk_ != "solid":
            w_["rail"] = rk_
    arch["walls"] += made
    mid = p((s0 + s1) / 2, face + depth / 2)
    arch["rooms"] = M._rooms(arch["rooms"] + [{
        "id": "", "level": lid, "name": "Balcony", "x": mid[0], "y": mid[1]}],
        {lv["id"] for lv in arch["levels"]})
    return {"area": width * depth, "level": lid}


# ---- stairs traced from the plan's tread lines -------------------------------------------
def _unit(a, b):
    L = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def trace(segs, words=()):
    """Flights from the tread lines of a stair layer (model m):
    [[flight, …] per stair], a flight = {"lines": [(a, b)…] in climbing
    order (a on the left), "d": climbing direction, "w", "g"}. ``words``:
    [(x, y, text)] — UP marks a stair's foot, DN its head."""
    cand = []
    for (a, b) in segs:
        L = math.dist(a, b)
        if 0.5 <= L <= 2.6:
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
            cand.append((round(ang) % 180, round(L / 0.05), a, b))
    groups = {}
    for ang, lk, a, b in cand:
        groups.setdefault((ang, lk), []).append((a, b))
    flights = []
    split = []
    for (ang, lk), lines in groups.items():
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        n = (-u[1], u[0])
        # the same tread line drawn twice: once
        uniq = []
        for a, b in lines:
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if not any(math.dist(m, q) < 0.01 for q, _l in uniq):
                uniq.append((m, (a, b)))
        # flights side by side (a U-stair's two arms: same length, same
        # direction) apart: by where they sit along the treads
        al = sorted(uniq, key=lambda t: t[0][0] * u[0] + t[0][1] * u[1])
        part = [al[0]]
        for t in al[1:]:
            pa = part[-1][0][0] * u[0] + part[-1][0][1] * u[1]
            if t[0][0] * u[0] + t[0][1] * u[1] - pa > 0.10:
                split.append((ang, lk, [l for _m, l in part]))
                part = []
            part.append(t)
        split.append((ang, lk, [l for _m, l in part]))
    for ang, _lk, lines in split:
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        n = (-u[1], u[0])
        rows = sorted(((((a[0] + b[0]) / 2) * n[0] + ((a[1] + b[1]) / 2) * n[1],
                        ((a[0] + b[0]) / 2) * u[0] + ((a[1] + b[1]) / 2) * u[1],
                        a, b) for a, b in lines))
        run = [rows[0]]
        for r in rows[1:] + [None]:
            ok = False
            if r is not None:
                s = r[0] - run[-1][0]
                prev = run[-1][0] - run[-2][0] if len(run) > 1 else s
                ok = 0.18 <= s <= 0.40 and abs(s - prev) < 0.04 and \
                    abs(r[1] - run[-1][1]) < 0.10
            if ok:
                run.append(r)
                continue
            if len(run) >= 2:
                gs = [run[k + 1][0] - run[k][0] for k in range(len(run) - 1)]
                ls = []
                for _o, _t, a, b in run:
                    if (b[0] - a[0]) * u[0] + (b[1] - a[1]) * u[1] < 0:
                        a, b = b, a
                    ls.append((tuple(a), tuple(b)))
                flights.append({"lines": ls, "d": n,
                                "w": math.dist(*ls[0]),
                                "g": sum(gs) / len(gs)})
            if r is not None:
                run = [r]
    # stairs: flights near each other
    # (every flight within 1.2 m of another one of the stair, whatever
    # order they come in: merged)
    boxes = [_fbox(f) for f in flights]
    root = list(range(len(flights)))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for i in range(len(flights)):
        for j in range(i + 1, len(flights)):
            if _boxdist(boxes[i], boxes[j]) < 1.2:
                root[find(i)] = find(j)
    by = {}
    for i, f in enumerate(flights):
        by.setdefault(find(i), []).append(f)
    return [_chain(st, words) for st in by.values()]


def _fbox(f):
    xs = [p[0] for ln in f["lines"] for p in ln]
    ys = [p[1] for ln in f["lines"] for p in ln]
    return min(xs), min(ys), max(xs), max(ys)


def _boxdist(a, b):
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def _mid(ln):
    return ((ln[0][0] + ln[1][0]) / 2, (ln[0][1] + ln[1][1]) / 2)


def _flip(f):
    lines = [(b, a) for a, b in reversed(f["lines"])]
    return dict(f, lines=lines, d=(-f["d"][0], -f["d"][1]))


def _chain(fl, words):
    """The flights in climbing order, each pointing up."""
    ups = [(x, y) for x, y, t in words if t.strip().upper() == "UP"]
    dns = [(x, y) for x, y, t in words if t.strip().upper() in ("DN", "DOWN")]

    def near(p, pts):
        return min((math.dist(p, q) for q in pts), default=1e9)
    # the foot: the flight end nearest an UP (else farthest from a DN)
    best = None
    for i, f in enumerate(fl):
        for end, ln in ((0, f["lines"][0]), (1, f["lines"][-1])):
            m = _mid(ln)
            score = near(m, ups) if ups else (-near(m, dns) if dns else
                                               (end, i))
            if best is None or score < best[0]:
                best = (score, i, end)
    _s, i, end = best
    first = fl[i] if end == 0 else _flip(fl[i])
    order = [first]
    rest = [f for k, f in enumerate(fl) if k != i]
    while rest:
        top = _mid(order[-1]["lines"][-1])
        k, e = min(((k, e) for k in range(len(rest)) for e in (0, 1)),
                   key=lambda ke: math.dist(top, _mid(
                       rest[ke[0]]["lines"][0 if ke[1] == 0 else -1])))
        f = rest.pop(k)
        order.append(f if e == 0 else _flip(f))
    # a flight marked DN (the one going down to the floor below, drawn
    # on this plan beside the up flights) is not part of this stair
    if dns and ups and len(order) > 1:
        def mid_of(f):
            return _mid(f["lines"][len(f["lines"]) // 2])
        keep = [order[0]]
        for f in order[1:]:
            m = mid_of(f)
            if near(m, dns) < near(m, ups) and near(m, dns) < 2.5:
                continue
            keep.append(f)
        order = keep
    for f in order:                    # every line: a on the climber's left
        d = f["d"]
        f["lines"] = [(a, b) if (b[0] - a[0]) * d[1] - (b[1] - a[1]) * d[0]
                      > 0 else (b, a) for a, b in f["lines"]]
    return order


def complete(flights, n_needed, room=None):
    """The flights drawn, and — when they hold fewer risers than the
    storey needs (a plan shows the lower flight only) — a half landing and
    a return flight beside the last one, on the side the stair room
    leaves free. Returns (flights, landings) with landings as
    {"corners", "after"} (risers climbed before it)."""
    from shapely.geometry import Polygon
    flights = [dict(f) for f in flights]
    landings = []
    count = 0
    for i, f in enumerate(flights[:-1]):
        count += len(f["lines"])
        nx = flights[i + 1]
        la, lb = f["lines"][-1]
        fa, fb = nx["lines"][0]
        d = f["d"]
        depth = f["w"] if d[0] * nx["d"][0] + d[1] * nx["d"][1] < -0.5 else 0.0
        pts = [la, lb, fa, fb]
        pts += [(p[0] + d[0] * depth, p[1] + d[1] * depth) for p in pts]
        # the landing: square to the flight it ends (its last tread line
        # and the next flight's first one, boxed along the flight) — the
        # corner square of an L, the full width of a U's half landing
        landings.append({"corners": _box_along(pts, d), "after": count})
    have = sum(len(f["lines"]) for f in flights)
    if n_needed > have and flights:
        f = flights[-1]
        d, w, g = f["d"], f["w"], f["g"]
        a, b = f["lines"][-1]
        left = (-d[1], d[0])           # a is on the left of the climber
        best = None
        for side in (1, -1):
            off = (left[0] * side * (w + 0.10), left[1] * side * (w + 0.10))
            land = [a, b, (a[0] + off[0], a[1] + off[1]),
                    (b[0] + off[0], b[1] + off[1])]
            land += [(p[0] + d[0] * w, p[1] + d[1] * w) for p in land]
            c, u, lw, L = rect_of(land)
            box = corners_of(c, u, lw, L)
            score = Polygon(box).intersection(room).area if room is not None \
                else side
            if best is None or score > best[0]:
                best = (score, side, off, box)
        _s, side, off, box = best
        landings.append({"corners": box, "after": have})
        k = n_needed - have
        # the return flight: beside, coming back down the well
        a2 = (a[0] + off[0], a[1] + off[1])
        b2 = (b[0] + off[0], b[1] + off[1])
        back = (-d[0], -d[1])
        lines = []
        for j in range(k):
            s = g * j
            lines.append(((b2[0] + back[0] * s, b2[1] + back[1] * s),
                          (a2[0] + back[0] * s, a2[1] + back[1] * s)))
        flights.append({"lines": lines, "d": back, "w": w, "g": g})
    # the arrival: a landing at the floor above, the width of the last
    # flight, square past its last riser (the stair never ends on a hole)
    if flights:
        f = flights[-1]
        d, w = f["d"], float(f["w"])
        la, lb = f["lines"][-1]
        pts = [la, lb, (la[0] + d[0] * w, la[1] + d[1] * w),
               (lb[0] + d[0] * w, lb[1] + d[1] * w)]
        landings.append({"corners": _box_along(pts, d),
                         "after": sum(len(x["lines"]) for x in flights),
                         "arrival": True})
    return flights, landings


def _box_along(pts, d):
    """The box round points, its sides along d and across it."""
    L = math.hypot(d[0], d[1]) or 1.0
    u = (d[0] / L, d[1] / L)
    v = (-u[1], u[0])
    su = [p[0] * u[0] + p[1] * u[1] for p in pts]
    sv = [p[0] * v[0] + p[1] * v[1] for p in pts]
    a0, a1, b0, b1 = min(su), max(su), min(sv), max(sv)

    def P(a, b):
        return [round(u[0] * a + v[0] * b, 4), round(u[1] * a + v[1] * b, 4)]
    return [P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b1)]


def traced_steps(st, z0):
    """Blocks of a traced stair: between each two lines of a flight, and
    the landings, each from the floor up to its level."""
    rise = st["rise"]
    out = []
    count = 0
    for f in st["flights"]:
        lines = f["lines"]
        for j in range(len(lines) - 1):
            (a0, b0), (a1, b1) = lines[j], lines[j + 1]
            out.append((f"Step {count + j + 1}", [a0, b0, b1, a1], z0,
                        z0 + (count + j + 1) * rise))
        count += len(lines)
    for lg in st.get("landings") or []:
        out.append(("Landing", [tuple(p) for p in lg["corners"]], z0,
                    z0 + lg["after"] * rise))
    return out


def outline_of(st):
    """The stair's well: its flights and landings — not its arrival
    landing, which is the floor above's own slab."""
    pts = [p for f in st["flights"] for ln in f["lines"] for p in ln]
    pts += [tuple(p) for lg in st.get("landings") or []
            if not lg.get("arrival") for p in lg["corners"]]
    return corners_of(*rect_of(pts))


def terraces_all(doc, h=1.0, t=0.15) -> list:
    """A terrace on every floor that leaves part of the floor below open:
    [(level name, area)]."""
    out = []
    for lv in doc["arch"]["levels"]:
        if lv["kind"] != "floor" or lv["name"] == "Roof":
            continue
        r = terrace(doc, lv["id"], h, t)
        if not r.get("why"):
            out.append((lv["name"], r["area"]))
    return out


# ---- stair types: how a flight is made ----------------------------------------------------
TYPES = [("monolithic", "Monolithic RCC (waist slab)"),
         ("solid", "Solid / masonry (filled)"),
         ("open", "Open riser — steel / timber on stringers"),
         ("cantilever", "Cantilever (floating treads)")]
CONCRETE = (0.74, 0.73, 0.70, 1.0)
TIMBER = (0.62, 0.45, 0.30, 1.0)
STEEL = (0.25, 0.27, 0.30, 1.0)


def as_flights(st):
    """A standard (designed) stair in the traced form: flights of riser
    lines and landings."""
    if st.get("traced"):
        return st["flights"], st.get("landings") or []
    (cx, cy), u, w, L = rect_of(st["corners"])
    v = (-u[1], u[0])
    if st.get("flip"):
        v = (-v[0], -v[1])
    o = (cx - u[0] * L / 2 - v[0] * w / 2, cy - u[1] * L / 2 - v[1] * w / 2)

    def P(a, b):
        return [o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b]
    n, g = st["risers"], st["going"]
    if st["kind"] == "straight":
        start = max((L - (n - 1) * g) / 2, 0.0)
        lines = [[P(start + k * g, w), P(start + k * g, 0.0)] for k in range(n)]
        return [{"lines": lines, "d": list(u), "w": w, "g": g}], []
    dl = w / 2
    n1 = int(math.ceil(n / 2))
    n2 = n - n1
    # the first flight's last riser is the half landing's edge (the spare
    # length stays at its foot, on the floor)
    s1 = max(L - dl - (n1 - 1) * g, 0.0)
    f1 = [[P(s1 + k * g, w / 2 - 0.01), P(s1 + k * g, 0.0)]
          for k in range(n1)]
    f2 = [[P(L - dl - k * g, w / 2 + 0.01), P(L - dl - k * g, w)]
          for k in range(n2)]
    land = {"corners": [P(L - dl, 0), P(L, 0), P(L, w), P(L - dl, w)],
            "after": n1}
    return ([{"lines": f1, "d": list(u), "w": w / 2, "g": g},
             {"lines": f2, "d": [-u[0], -u[1]], "w": w / 2, "g": g}],
            [land])


def _prism(profile, o, d, r, t0, t1):
    """A solid from a profile [(s, z)] in the vertical plane along ``d``
    (from ``o``), run across ``r`` from t0 to t1: side faces and the
    faces round its edges."""
    def P(s, t, z):
        return (o[0] + d[0] * s + r[0] * t, o[1] + d[1] * s + r[1] * t, z)
    faces = [[P(s, t0, z) for s, z in profile],
             [P(s, t1, z) for s, z in reversed(profile)]]
    n = len(profile)
    for i in range(n):
        (s0, z0), (s1, z1) = profile[i], profile[(i + 1) % n]
        if abs(s0 - s1) < 1e-9 and abs(z0 - z1) < 1e-9:
            continue
        faces.append([P(s0, t0, z0), P(s0, t1, z0), P(s1, t1, z1),
                      P(s1, t0, z1)])
    return faces


def _clean(profile):
    out = []
    for p in profile:
        if not out or abs(p[0] - out[-1][0]) > 1e-6 or \
                abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-6 and \
            abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def build(st, z0, kind="monolithic", waist=0.15, nosing=0.025,
          tread_t=0.05, rail=None, rail_h=0.9, rail_sides="inner",
          rail_off=0.05, rail_gap=0.0, rail_ext=0.0):
    """[(faces, colour)] of a stair of the chosen type — with its railing
    (``rail``: a railings type; None / "none" = no railing)."""
    from .engine import walls as W
    flights, landings = as_flights(st)
    rise = st["rise"]
    out = []
    count = 0
    runs = []                         # each flight's two side lines, sloped
    for f in flights:
        lines = [((ln[0][0], ln[0][1]), (ln[1][0], ln[1][1]))
                 for ln in f["lines"]]
        m = len(lines)
        if m < 2:
            count += m
            continue
        a0, b0 = lines[0]
        d = tuple(f["d"])
        o = a0
        wv = math.dist(a0, b0) or float(f["w"])
        r = ((b0[0] - a0[0]) / wv, (b0[1] - a0[1]) / wv)
        ss = [((ln[0][0] + ln[1][0]) / 2 - (a0[0] + b0[0]) / 2) * d[0] +
              ((ln[0][1] + ln[1][1]) / 2 - (a0[1] + b0[1]) / 2) * d[1]
              for ln in lines]
        g = (ss[-1] - ss[0]) / (m - 1) if m > 1 else float(f["g"])
        zb = z0 + count * rise
        zk = [zb + k * rise for k in range(m + 1)]
        # the railing's line: over the nosings, from the first to the top
        for tside in (0.05, wv - 0.05):
            p_ = _at(o, d, r, ss[0], tside)
            q_ = _at(o, d, r, ss[m - 1], tside)
            runs.append((len(runs) // 2, tside < wv / 2,
                         (p_[0], p_[1], zb + rise), (q_[0], q_[1], zk[m])))
        tan = rise / g if g > 1e-6 else 1.0
        cos = 1.0 / math.sqrt(1.0 + tan * tan)
        nos = nosing if kind in ("monolithic", "solid") else 0.0
        if kind == "solid":
            for k in range(1, m):
                q = [_at(o, d, r, ss[k - 1] - nos, 0), _at(o, d, r, ss[k], 0),
                     _at(o, d, r, ss[k], wv), _at(o, d, r, ss[k - 1] - nos, wv)]
                out.append((W.solid({"outer": _ccw(q), "holes": []},
                                    zb, zk[k]), CONCRETE))
        elif kind == "monolithic":
            prof = []

            def root(s):
                return zb + (s - ss[0]) * tan
            off = waist / cos
            T = waist                           # the landing's thickness
            if count == 0:                      # from the floor
                s_x = ss[0] + off / tan
                prof.append((ss[0], zb))
            else:                               # from a landing: the soffit
                s_x = None                      # kinks into the landing's
                s_k = ss[0] + max(off - T, 0.0) / tan
                if s_k > ss[0] + 1e-6:
                    prof.append((s_k, zb - T))
                prof.append((ss[0], zb - T))
                prof.append((ss[0], zb))
            for k in range(1, m):
                tn = min(0.03, rise / 3)
                prof += [(ss[k - 1], zk[k] - tn), (ss[k - 1] - nos, zk[k] - tn),
                         (ss[k - 1] - nos, zk[k]), (ss[k], zk[k])]
            ends_on = any(int(lg.get("after", -1)) == count + m
                          for lg in landings)
            if not ends_on:                     # no landing: the flight's
                prof.append((ss[m - 1], zk[m]))  # top runs on to the slab
            # into the landing (or the floor) above: the waist runs on
            # under it until its soffit meets the landing's — one clean
            # kink line, no step under the landing's edge
            s_e = ss[m - 1] + (zk[m] - T - (root(ss[m - 1]) - off)) / tan
            if ends_on:
                prof.append((ss[m - 1], zk[m] - T))
            else:
                prof.append((s_e, zk[m]))
            if s_e > ss[m - 1] + 1e-6:
                prof.append((s_e, zk[m] - T))
            if s_x is not None and s_x < s_e:
                prof.append((s_x, zb))
            out.append((_prism(_clean(prof), o, d, r, 0.0, wv), CONCRETE))
        else:                                   # open / cantilever treads
            sw = 0.05 if kind == "open" else 0.0
            for k in range(1, m):
                q = [_at(o, d, r, ss[k - 1] - nosing, sw),
                     _at(o, d, r, ss[k], sw),
                     _at(o, d, r, ss[k], wv - sw),
                     _at(o, d, r, ss[k - 1] - nosing, wv - sw)]
                out.append((W.solid({"outer": _ccw(q), "holes": []},
                                    zk[k] - tread_t, zk[k]), TIMBER))
            if kind == "open":                  # two steel stringers
                D = 0.25

                def top(s):
                    return zb + (s - ss[0]) * tan + rise + 0.05
                s0, s1 = ss[0] - nosing, ss[m - 1]
                prof = [(s0, top(s0)), (s1, top(s1)),
                        (s1, top(s1) - D / cos), (s0, top(s0) - D / cos)]
                if count == 0:
                    prof = [(x, max(z, zb)) for x, z in prof]
                for t0, t1 in ((0.0, sw), (wv - sw, wv)):
                    out.append((_prism(_clean(prof), o, d, r, t0, t1), STEEL))
        count += m
    if rail and rail != "none" and rail_sides != "none" and runs:
        out += build_rail(st, z0, rail, rail_h, rail_sides, rail_off,
                          rail_gap, rail_ext)
    for lg in landings:
        zl = z0 + lg["after"] * rise
        th = {"monolithic": waist, "solid": zl - z0, "open": 0.10,
              "cantilever": 0.15}[kind]
        out.append((W.solid({"outer": _ccw([tuple(p) for p in lg["corners"]]),
                             "holes": []}, zl - max(th, 0.05), zl),
                    CONCRETE if kind in ("monolithic", "solid") else TIMBER))
    return out


def _ext(path, ext, at_end):
    """The path run on ``ext`` past its first (or last) point, level."""
    if ext <= 0 or len(path) < 2:
        return path
    if at_end:
        p, q = path[-2], path[-1]
    else:
        p, q = path[1], path[0]
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    if L < 1e-6:
        return path
    e = (q[0] + (q[0] - p[0]) / L * ext, q[1] + (q[1] - p[1]) / L * ext, q[2])
    return path + [e] if at_end else [e] + path


def railing(st, runs, kind, h=0.9, sides="inner", gap=0.0, ext=0.0,
            inset=0.05) -> list:
    """[(faces, colour)] of the stair's railing: on the inner side of its
    flights (the side by the well, joined across each landing), the outer
    (the wall side), or both. A single straight flight has no well: both
    sides, unless «inner» / «outer» picks one."""
    from .engine import railings as RL
    if sides == "none":
        return []
    nfl = max(r[0] for r in runs) + 1
    cs = st.get("corners") or []
    cx = sum(p[0] for p in cs) / len(cs) if cs else 0.0
    cy = sum(p[1] for p in cs) / len(cs) if cs else 0.0

    def far(r):
        mx, my = (r[2][0] + r[3][0]) / 2, (r[2][1] + r[3][1]) / 2
        return math.hypot(mx - cx, my - cy)
    both = sides == "both" or (nfl == 1 and sides not in ("outer",)
                               and not st.get("rail_sides"))
    out = []
    if both:
        for i in range(nfl):
            for r in (r for r in runs if r[0] == i):
                path = [r[2], r[3]]
                if i == 0:
                    path = _ext(path, ext, False)
                if i == nfl - 1:
                    path = _ext(path, ext, True)
                out.append((RL.faces(path, h, kind, gap=gap), None))
        return out
    picked = []
    for i in range(nfl):
        two = [r for r in runs if r[0] == i]
        if nfl == 1:                   # one flight: inner = its left side
            picked.append(next((r for r in two
                                if r[1] == (sides != "outer")), two[0]))
            continue
        picked.append(max(two, key=far) if sides == "outer"
                      else min(two, key=far))
    lands = [lg for lg in (as_flights(st)[1] or []) if not lg.get("arrival")]
    # one railing from the bottom to the top, across the landings (the
    # outer one turns round the landing's far corners)
    paths, path = [], []
    for r in picked:
        p, q = r[2], r[3]
        if path and math.hypot(p[0] - path[-1][0], p[1] - path[-1][1]) > \
                (3.0 if sides != "outer" else 8.0):
            paths.append(path)
            path = []
        if path:                      # across the landing, at its level
            last = path[-1]
            if sides == "outer" and lands:
                # round the landing: on along the last flight to its far
                # edge, across it, and back to the next flight
                pl = path[-2]
                L = math.hypot(last[0] - pl[0], last[1] - pl[1]) or 1.0
                u = ((last[0] - pl[0]) / L, (last[1] - pl[1]) / L)
                mid = ((last[0] + p[0]) / 2, (last[1] + p[1]) / 2)
                lg = min(lands, key=lambda g: min(
                    math.hypot(c[0] - mid[0], c[1] - mid[1])
                    for c in g["corners"]))
                k = max((c[0] - last[0]) * u[0] + (c[1] - last[1]) * u[1]
                        for c in lg["corners"]) - inset
                kp = (p[0] - last[0]) * u[0] + (p[1] - last[1]) * u[1]
                if k > 0.05:
                    path.append((last[0] + u[0] * k, last[1] + u[1] * k,
                                 last[2]))
                    if k - kp > 0.05:
                        path.append((p[0] + u[0] * (k - kp),
                                     p[1] + u[1] * (k - kp), last[2]))
            path.append((p[0], p[1], path[-1][2]))
        path += [p, q]
    if len(path) >= 2:
        paths.append(path)
    if paths:
        paths[0] = _ext(paths[0], ext, False)
        paths[-1] = _ext(paths[-1], ext, True)
    return [(RL.faces(pth, h, kind, gap=gap), None) for pth in paths
            if len(pth) >= 2]


def _at(o, d, r, s, t):
    return (o[0] + d[0] * s + r[0] * t, o[1] + d[1] * s + r[1] * t)
