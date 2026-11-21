# SPDX-License-Identifier: GPL-3.0-or-later
"""Two ground levels — a site on a slope (3.64.66).

A drawing whose plans are titled «LOWER GROUND FLOOR PLAN» and «UPPER
GROUND FLOOR PLAN» stands on two grounds: the lower road (the lower
ground floor opens on it) and the upper one (the upper ground floor's
plaza is on the earth). What it changes:

* the two floors named so; the upper one is the model's ground floor
  (at its CAD level note, «LEV.+17'-0"»), the lower one under it at its
  own note («LEV.+5'-6"») — no basement: no RCC ring, its doors and
  windows kept;
* the plot's ground at the lower road (the plan's «LEV.±0'-0"» beside
  its road level «520.0»);
* the earth under the upper ground floor (where the lower floor is not)
  filled up to it, faced with retaining walls;
* the boundary wall standing on the ground it runs over: on the lower
  road at the lower side, up on the upper plaza at the upper side.

``doc["hill"]`` = {"on", "lower", "upper" (level ids), "low" (the lower
ground, m), "roads": [[x, y, z]…] (the road levels noted)}.
"""
from __future__ import annotations

import math
import re

LOWER_RX = re.compile(r"\bLOWER\s+GROUND\b", re.I)
UPPER_RX = re.compile(r"\bUPPER\s+GROUND\b", re.I)
PLAN_RX = re.compile(r"\bPLAN\s*$", re.I)
#: the retaining walls' face (the perspective's white podium)
FACE = (0.90, 0.89, 0.86)
DEFAULT_NAME = re.compile(r"^(Ground floor|Floor \d+|Level \d+|Basement \d+|"
                          r"\d+(?:st|nd|rd|th) floor|Ground Floor|Roof)$",
                          re.I)


def _clean(t: str) -> str:
    return re.sub(r"%%[UuOo]", "", str(t or "")).strip()


def titles(doc) -> dict:
    """{level id: its plan's title} — the biggest «… PLAN» text."""
    out = {}
    for t in doc.get("texts") or []:
        s = _clean(t.get("text"))
        if not PLAN_RX.search(s) or len(s) > 60:
            continue
        lid = t.get("level")
        h = float(t.get("h", 0.0) or 0.0)
        if lid not in out or h > out[lid][1]:
            out[lid] = (s, h)
    return {k: v[0] for k, v in out.items()}


def detect(doc):
    """(lower level id, upper level id) or None."""
    ids = [lv["id"] for lv in doc["arch"]["levels"]]
    t = titles(doc)
    lo = [lid for lid in ids if LOWER_RX.search(t.get(lid, ""))]
    up = [lid for lid in ids if UPPER_RX.search(t.get(lid, ""))]
    if lo and up and lo[0] != up[0]:
        return lo[0], up[0]
    return None


def on(doc) -> bool:
    h = doc.get("hill") or {}
    ids = {lv["id"] for lv in doc["arch"]["levels"]}
    return bool(h.get("on")) and h.get("lower") in ids and \
        h.get("upper") in ids


def zoned(doc) -> bool:
    """3.64.89 — the plot has level parts («Site · ground»): those levels
    are the site's grounds; the hillside makes no ground of its own, it
    only brings the steps and ramps to them."""
    if not on(doc):
        return False
    from . import project as PJ
    try:
        return len(PJ.plot_zones(doc)) >= 2
    except Exception:  # noqa: BLE001
        return False


def zone_fn(doc):
    """fn(x, y) → the level of the plot part there (m, the model's datum)."""
    from . import project as PJ
    zs = PJ.plot_zones(doc)
    return lambda x, y: PJ._zone_level(doc, PJ.zone_dz(zs, x, y))


def apply(doc) -> bool:
    """Before the levels are set from the CAD's notes: the two ground
    floors named, the upper one the ground floor, the lower one under
    it. True when the site has two grounds."""
    pair = detect(doc)
    old = doc.get("hill") or {}
    if not pair:
        if old.get("on") and old.get("manual") and on(doc):
            pair = old["lower"], old["upper"]
        else:
            if old.get("on"):
                doc["hill"] = {}
            return False
    lo, up = pair
    levels = doc["arch"]["levels"]
    il = next(i for i, lv in enumerate(levels) if lv["id"] == lo)
    iu = next(i for i, lv in enumerate(levels) if lv["id"] == up)
    if il > iu:                       # (the lower one below the upper one)
        levels[il], levels[iu] = levels[iu], levels[il]
        il, iu = iu, il
    for i, lv in enumerate(levels):
        lv["kind"] = "basement" if i < iu else (
            "ground" if i == iu else "floor")
    for lid, nm in ((lo, "Lower Ground Floor"), (up, "Upper Ground Floor")):
        lv = next(x for x in levels if x["id"] == lid)
        if not lv.get("name") or DEFAULT_NAME.match(str(lv["name"])):
            lv["name"] = nm
    doc["hill"] = dict(old, on=True, lower=lo, upper=up)
    return True


def finish(doc) -> None:
    """After the levels are set: the plinth field cleared (the CAD's note
    sets the upper ground floor), the road levels and the lower ground."""
    if not on(doc):
        return
    st = doc["settings"]
    st["ground_ffl"] = 0.0           # as the CAD's level notes set it
    from . import project as PJ
    roads = []
    for lid, ms in (doc.get("marks") or {}).items():
        rel = [(m["x"], m["y"], m["v"]) for m in ms
               if m.get("v") is not None]
        for m in ms:
            if m.get("a") is None:
                continue
            near = [(math.hypot(x - m["x"], y - m["y"]), v)
                    for x, y, v in rel]
            near = [q for q in near if q[0] < 1.5]
            if near:
                roads.append([round(m["x"], 3), round(m["y"], 3),
                              round(min(near)[1], 4)])
    for t in doc.get("texts") or []:     # «520.0» under «LEV.±0'-0"»
        if not re.fullmatch(r"\s*\d{2,5}(?:\.\d+)?\s*", str(t.get("text"))):
            continue
        ms = (doc.get("marks") or {}).get(t.get("level")) or []
        near = [(math.hypot(m["x"] - t["x"], m["y"] - t["y"]), m["v"])
                for m in ms if m.get("v") is not None]
        near = [q for q in near if q[0] < 1.2]
        if near:
            roads.append([round(t["x"], 3), round(t["y"], 3),
                          round(min(near)[1], 4)])
    h = doc["hill"]
    h["roads"] = roads
    el = PJ.elevations(doc["arch"])
    il = next(i for i, lv in enumerate(doc["arch"]["levels"])
              if lv["id"] == h["lower"])
    low = min([r[2] for r in roads] or [el[il] - 0.15])
    h["low"] = round(min(low, el[il]), 4)
    try:                      # 3.64.71: the upper plaza's lowest terrace
        ms_ = plaza_marks(doc)
        h["plaza"] = round(min(m[2] for m in ms_), 4) if ms_ else None
    except Exception:  # noqa: BLE001
        h["plaza"] = None



# ---------------------------------------------------------------------------
# The ground: lower road and upper plaza
# ---------------------------------------------------------------------------
NOT_AREA = re.compile(r"DIM|TEXT|TEX\b|TEX |ANNO|ARROW|TITLE|NORTH|GRID|"
                      r"BORDER|LOGO|DEFPOINT", re.I)


def _polys(s):
    from shapely.geometry import Polygon
    try:
        g = Polygon(s["corners"], [h for h in s.get("holes") or []
                                   if len(h) >= 3]).buffer(0)
    except Exception:  # noqa: BLE001
        return None
    return g if not g.is_empty else None


def plan_area(pl, cell=0.5, grow=2) -> list:
    """What a floor's plan covers: its lines (not the notes, dimensions,
    north arrow) on a grid of ``cell`` m, thickened ``grow`` cells, the
    outside flooded from the edges, the rest thinned back — the outer
    rings [[x, y]…] of the pieces of 20 m² and more (model metres)."""
    import numpy as np
    from shapely.geometry import box
    from shapely.ops import unary_union
    lay = pl["layers"]
    sg = np.array([s[:4] for s in pl["segs"]
                   if not NOT_AREA.search(str(lay[s[4]]))], dtype=float)
    if len(sg) < 3:
        return []
    x0 = min(sg[:, 0].min(), sg[:, 2].min()) - (grow + 2) * cell
    y0 = min(sg[:, 1].min(), sg[:, 3].min()) - (grow + 2) * cell
    x1 = max(sg[:, 0].max(), sg[:, 2].max()) + (grow + 2) * cell
    y1 = max(sg[:, 1].max(), sg[:, 3].max()) + (grow + 2) * cell
    nx = int((x1 - x0) / cell) + 1
    ny = int((y1 - y0) / cell) + 1
    if nx * ny > 4_000_000:
        return []
    occ = np.zeros((ny, nx), dtype=bool)
    L = np.hypot(sg[:, 2] - sg[:, 0], sg[:, 3] - sg[:, 1])
    k = np.maximum((L / (cell * 0.5)).astype(int) + 1, 1)
    for n in np.unique(k):
        rows = sg[k == n]
        t = np.linspace(0.0, 1.0, n + 1)
        xs = rows[:, 0:1] + (rows[:, 2:3] - rows[:, 0:1]) * t
        ys = rows[:, 1:2] + (rows[:, 3:4] - rows[:, 1:2]) * t
        ix = ((xs - x0) / cell).astype(int).ravel()
        iy = ((ys - y0) / cell).astype(int).ravel()
        occ[iy, ix] = True

    def dil(a, r):
        for _ in range(r):
            b = a.copy()
            b[1:, :] |= a[:-1, :]
            b[:-1, :] |= a[1:, :]
            b[:, 1:] |= a[:, :-1]
            b[:, :-1] |= a[:, 1:]
            a = b
        return a
    occ = dil(occ, grow)
    out = np.zeros_like(occ)
    out[0, :] = out[-1, :] = True
    out[:, 0] = out[:, -1] = True
    out &= ~occ
    while True:
        nxt = dil(out, 1) & ~occ
        if (nxt == out).all():
            break
        out = nxt
    inside = ~dil(out, grow)
    boxes = []
    for r in range(ny):
        row = inside[r]
        if not row.any():
            continue
        d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
        st, en = np.where(d == 1)[0], np.where(d == -1)[0]
        for a, b in zip(st, en):
            boxes.append(box(x0 + a * cell, y0 + r * cell,
                             x0 + b * cell, y0 + (r + 1) * cell))
    if not boxes:
        return []
    g = unary_union(boxes)
    res = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type == "Polygon" and q.area >= 20.0:
            q = q.simplify(cell * 0.6)
            res.append([[round(x, 3), round(y, 3)]
                        for x, y in list(q.exterior.coords)[:-1]])
    return res


def low_z(doc) -> float:
    """The lower road's ground."""
    from . import project as PJ
    h = doc.get("hill") or {}
    if h.get("low") is not None and on(doc):
        return float(h["low"])
    return PJ.plot_top(doc)


def lower_footprint(doc):
    """What the lower ground floor builds (its floor, its walls round)."""
    from shapely.ops import unary_union
    from . import project as PJ
    from .engine import walls as W
    h = doc.get("hill") or {}
    arch = doc["arch"]
    gs = [g for s in arch["structure"] if s["type"] == "slab"
          and s["level"] == h.get("lower") and not s.get("skip")
          and not s.get("roof")
          for g in [_polys(s)] if g is not None]
    ws = [w for w in arch["walls"] if w["level"] == h.get("lower")]
    if ws:
        try:
            from shapely.geometry import Polygon
            pieces = [pc for pcs in W.plan(ws).values() for pc in pcs]
            fp = PJ._outer_loop(pieces)
            if fp:
                gs.append(Polygon(fp).buffer(0))
        except Exception:  # noqa: BLE001
            pass
    return unary_union(gs).buffer(0.02) if gs else None


def high_area(doc):
    """The upper ground: what the upper ground floor's plan covers (inside
    the plot), less what the lower ground floor builds — shapely, or
    None."""
    if not on(doc) or zoned(doc):
        return None
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    h = doc["hill"]
    rings = (doc.get("plan_area") or {}).get(h["upper"]) or []
    gs = []
    for r in rings:
        try:
            g = Polygon(r).buffer(0)
            if not g.is_empty:
                gs.append(g)
        except Exception:  # noqa: BLE001
            pass
    if not gs:
        return None
    g = unary_union(gs)
    plot = doc["arch"].get("plot")
    if plot:
        try:
            pg = Polygon(plot["corners"]).buffer(0)
            if pg.intersection(g).area > 0.3 * g.area:
                g = g.intersection(pg)
        except Exception:  # noqa: BLE001
            pass
    fp = lower_footprint(doc)
    if fp is not None:
        g = g.difference(fp)
    return g if not g.is_empty and g.area > 1.0 else None


def plaza_marks(doc, H=None) -> list:
    """3.64.71: the upper plaza's own levels — the upper floor's notes
    out on its open ground (below the floor, «LEV.+13'-6"», «+16'-0"»…):
    [(x, y, z)]."""
    from shapely.geometry import Point
    from . import project as PJ
    if not on(doc):
        return []
    H = high_area(doc) if H is None else H
    if H is None:
        return []
    arch = doc["arch"]
    up = doc["hill"]["upper"]
    el = PJ.elevations(arch)
    iu = next(i for i, lv in enumerate(arch["levels"]) if lv["id"] == up)
    Hb = H.buffer(1.0)
    out = []
    for m in (doc.get("marks") or {}).get(up) or []:
        v = m.get("v")
        if v is None or float(v) > el[iu] - 0.1 or \
                float(v) < low_z(doc) + 0.3:
            continue
        if Hb.contains(Point(m["x"], m["y"])):
            out.append((float(m["x"]), float(m["y"]), float(v)))
    return out


def terraces(doc, H=None) -> list:
    """The upper ground cut into its terraces, each at its note's level
    (the nearest note) — [(polygon, z)]; [] with no notes."""
    from shapely.geometry import MultiPoint, Point
    from shapely.ops import unary_union, voronoi_diagram
    H = high_area(doc) if H is None else H
    ms = plaza_marks(doc, H)
    if H is None or not ms:
        return []
    if len(ms) == 1:
        return [(H, ms[0][2])]
    vd = voronoi_diagram(MultiPoint([(x, y) for x, y, _z in ms]),
                         envelope=H.envelope.buffer(50.0))
    by = {}
    for cell in vd.geoms:
        k = next((m for m in ms if cell.contains(Point(m[0], m[1]))), None)
        if k is None:
            continue
        c = cell.intersection(H)
        if c.is_empty:
            continue
        by.setdefault(round(k[2], 3), []).append(c)
    return [(unary_union(cs), z) for z, cs in sorted(by.items())]


def lower_spots(doc) -> list:
    """3.64.72: the lower ground's spot levels — the road levels noted
    and the lower floor's notes out on its open ground: [(x, y, z)]."""
    from shapely.geometry import Point
    if not on(doc):
        return []
    fp = lower_footprint(doc)
    out = [(float(r[0]), float(r[1]), float(r[2]))
           for r in (doc["hill"].get("roads") or [])]
    for m in (doc.get("marks") or {}).get(doc["hill"]["lower"]) or []:
        if m.get("v") is None:
            continue
        if fp is not None and fp.buffer(0.3).contains(Point(m["x"], m["y"])):
            continue
        out.append((float(m["x"]), float(m["y"]), float(m["v"])))
    return out


def low_terrain_fn(doc):
    """fn(x, y) → the lower ground's level: the spot levels blended
    (inverse distance, the nearest four) — the road rising along the
    site, the forecourts at their notes."""
    if zoned(doc):
        return zone_fn(doc)
    low = float((doc.get("hill") or {}).get("low", 0.0) or 0.0)
    sp = lower_spots(doc)
    if not sp:
        return lambda x, y: low

    def at(x, y):
        ds = sorted(((x - a) ** 2 + (y - b) ** 2, z) for a, b, z in sp)[:4]
        if ds[0][0] < 0.04:
            return ds[0][1]
        w = [1.0 / d for d, _z in ds]
        return sum(wi * z for wi, (_d, z) in zip(w, ds)) / sum(w)
    return at


def level_ground_fn(doc, lid):
    """fn(x, y) → what one stands on at (x, y) on a two-ground site, for
    the steps and ramps of level ``lid``: its floor where it builds, else
    the ground there (the upper plaza's terraces, the lower ground)."""
    from shapely.geometry import Point
    from shapely.prepared import prep
    from . import project as PJ
    arch = doc["arch"]
    el = PJ.elevations(arch)
    i = next(k for k, lv in enumerate(arch["levels"]) if lv["id"] == lid)
    if lid == doc["hill"].get("lower"):
        fp = lower_footprint(doc)
    else:
        from shapely.ops import unary_union
        gs = [g for s_ in arch["structure"] if s_["type"] == "slab"
              and s_["level"] == lid and not s_.get("roof")
              for g in [_polys(s_)] if g is not None]
        fp = unary_union(gs) if gs else None
    pf = prep(fp.buffer(-0.05)) if fp is not None else None
    gfn = ground_fn(doc)

    def at(x, y):
        if pf is not None and pf.contains(Point(x, y)):
            try:
                return el[i] + PJ.floor_offset_at(doc, lid, (x, y))
            except Exception:  # noqa: BLE001
                return el[i]
        return gfn(x, y)
    return at


def ground_fn(doc):
    """fn(x, y) → the ground's level there: the upper ground (the plot's
    top) on the upper plaza (with 1.5 m round it), else the lower road."""
    from shapely.geometry import Point
    from shapely.prepared import prep
    from . import project as PJ
    top = PJ.plot_top(doc)
    if not on(doc):
        return lambda x, y: top
    if zoned(doc):
        return zone_fn(doc)
    lowf = low_terrain_fn(doc)        # 3.64.72: the lower ground sloped
    H = high_area(doc)
    if H is None:
        return lowf
    pH = prep(H.buffer(1.5))
    ms = plaza_marks(doc, H)
    if not ms:
        return lambda x, y: top if pH.contains(Point(x, y)) else lowf(x, y)

    def at(x, y):                 # (the nearest terrace's level)
        if not pH.contains(Point(x, y)):
            return lowf(x, y)
        return min(ms, key=lambda m: (m[0] - x) ** 2 + (m[1] - y) ** 2)[2]
    return at


def terrain_faces(polys, fn, cell=3.0) -> list:
    """The ground as a surface over ``polys`` (shapely), each point at
    fn(x, y): cut on a ``cell`` grid, each piece fanned / triangulated —
    [[(x, y, z)…]] faces, upward."""
    import shapely
    from shapely.geometry import box
    out = []
    for g in polys:
        for q in getattr(g, "geoms", [g]):
            if q.geom_type != "Polygon" or q.area < 0.05:
                continue
            x0, y0, x1, y1 = q.bounds
            nx = max(int((x1 - x0) / cell) + 1, 1)
            ny = max(int((y1 - y0) / cell) + 1, 1)
            for i in range(nx):
                for j in range(ny):
                    c = box(x0 + i * cell, y0 + j * cell,
                            x0 + (i + 1) * cell, y0 + (j + 1) * cell)
                    pc = q.intersection(c)
                    for r in getattr(pc, "geoms", [pc]):
                        if r.geom_type != "Polygon" or r.area < 1e-4:
                            continue
                        try:
                            tris = shapely.constrained_delaunay_triangles(r)
                        except Exception:  # noqa: BLE001
                            tris = None
                        for t in (getattr(tris, "geoms", []) if tris
                                  is not None else []):
                            cs = list(t.exterior.coords)[:3]
                            a = (cs[1][0] - cs[0][0]) * (cs[2][1] - cs[0][1]) \
                                - (cs[1][1] - cs[0][1]) * (cs[2][0] - cs[0][0])
                            if abs(a) < 1e-8:
                                continue
                            if a < 0:
                                cs = [cs[0], cs[2], cs[1]]
                            out.append([(x, y, fn(x, y)) for x, y in cs])
    return out


def steps_groups(doc) -> list:
    """3.64.72: the steps the plans draw (their STEPS layer) on a two-ground
    site, each run between what is at its two ends — the floor, a terrace,
    the lower ground — one riser for each line."""
    if not on(doc):
        return []
    from PySide6.QtGui import QVector3D
    from shapely.geometry import Point
    from core.group import Group
    from core.mesh import Mesh
    from . import project as PJ
    from .host import KEY, level_layer
    out = []
    for lid in (doc["hill"]["lower"], doc["hill"]["upper"]):
        try:
            sets = PJ.cad_steps(doc, lid)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("hillside.steps cad_steps")
            continue
        if not sets:
            continue
        G = level_ground_fn(doc, lid)
        mesh = Mesh()
        n = 0
        for cs in sets:
            try:
                if cs.get("own") and cs.get("plines"):
                    ps = list(cs["plines"])
                    tread = float(cs.get("tread", 0.3) or 0.3)
                    st = PJ.step_strips(ps, tread)
                    # the two ends: past the first riser up-side, past the
                    # last one down-side
                    up = ps[0].buffer(st[0][1] * (tread + 0.6),
                                      single_sided=True).difference(
                        ps[0].buffer(st[0][1] * (tread + 0.05),
                                     single_sided=True))
                    dn = ps[-1].buffer(-st[-1][1] * 0.6,
                                       single_sided=True)
                    cu, cd = up.representative_point(), \
                        dn.representative_point()
                    za, zb = G(cu.x, cu.y), G(cd.x, cd.y)
                    strips = [(pg, k) for k, (pg, _sg) in enumerate(st)]
                    if za < zb:          # (drawn from the foot up)
                        za, zb = zb, za
                        strips = [(pg, len(st) - 1 - k) for pg, k in strips]
                    ztop, zfoot = za, zb
                else:
                    strips = list(cs.get("strips") or [])
                    if not strips:
                        continue
                    c = cs["zone"].representative_point()
                    ztop = G(c.x, c.y)
                    foot = max(strips, key=lambda q: q[1])[0]
                    fc = foot.centroid
                    zfoot = G(fc.x, fc.y)
                    if ztop - zfoot < 0.05:
                        zfoot = ztop - 0.1524 * int(cs.get("n") or
                                                    len(strips))
                nr = max(max(k for _p, k in strips) + 1, 1)
                H = ztop - zfoot
                if H < 0.05 or H > 6.0:
                    continue
                r = H / nr
                for pg, k in strips:
                    zt = ztop - k * r
                    for f in PJ._prism(pg, zfoot - 0.05, zt, 1e-4):
                        PJ._safe_add(mesh, [QVector3D(*q) for q in f["loop"]],
                                     [[QVector3D(*q) for q in h]
                                      for h in f.get("holes") or []])
                n += 1
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("hillside.steps")
        if not n:
            continue
        PJ._soften(mesh)
        lv = next(x for x in doc["arch"]["levels"] if x["id"] == lid)
        g = Group(mesh, name=f"Steps (CAD) · {n} runs · {lv['name']}")
        g.component = False
        g.material = {"color": (0.86, 0.84, 0.80), "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ifc = {"class": "IfcStair", "name": "Steps"}
        g.ext = {KEY: {"type": "hill_steps", "id": "hill-steps-" + lid,
                       "level": lid}}
        out.append(g)
        _ = Point
    return out


def ramp_zs(doc, r, zs):
    """3.64.72: a ramp on a two-ground site from what is at its low end to
    what is at its high end (its sections' levels, evenly between)."""
    if not on(doc) or r.get("level") not in (doc["hill"].get("lower"),
                                             doc["hill"].get("upper")):
        return zs
    secs = r.get("sections") or []
    if len(secs) < 2:
        return zs
    G = level_ground_fn(doc, r["level"])

    def mid(sc):
        return ((sc[0][0] + sc[1][0]) / 2, (sc[0][1] + sc[1][1]) / 2)
    a, b = mid(secs[0]), mid(secs[-1])
    L = math.dist(a, b)
    if L < 0.3:
        return zs
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    za = G(a[0] - ux * 0.8, a[1] - uy * 0.8)
    zb = G(b[0] + ux * 0.8, b[1] + uy * 0.8)
    if abs(za - zb) < 0.05:
        return zs
    n = len(zs)
    return [za + (zb - za) * k / max(n - 1, 1) for k in range(n)]


APRON = 2.5      # m — the forecourt kept low round the lower floor


def _apron(doc, parts):
    """3.64.74 — the earth beside the lower ground floor was as high as its
    walls (the upper terraces' levels), burying its doors and windows.
    Within APRON of its walls the earth stays at the lower floor's own level
    (a forecourt), the terraces rising beyond it."""
    L = lower_footprint(doc)
    if L is None or L.is_empty:
        return parts
    try:
        from . import project as PJ
        h = doc["hill"]
        ev = PJ.elevations(doc["arch"])
        zf = ev.get(h["lower"]) if isinstance(ev, dict) else None
        if zf is None:
            zf = next((e for lv, e in zip(doc["arch"]["levels"], ev)
                       if lv["id"] == h["lower"]), None)
        zf = float(zf) if zf is not None else 0.0
    except Exception:  # noqa: BLE001
        return parts
    ring = L.buffer(APRON).difference(L)
    out = []
    for g, z in parts:
        near = g.intersection(ring)
        far = g.difference(ring)
        if not far.is_empty:
            out.append((far, z))
        if not near.is_empty:
            out.append((near, min(z, zf + 0.05)))
    return out


def fill_groups(doc):
    """The earth of the upper ground (where the lower floor is not), from
    the lower road up to the upper plaza — its top the plaza, its sides
    the retaining walls."""
    if not on(doc) or zoned(doc):
        return []
    from PySide6.QtGui import QVector3D
    from core.group import Group
    from core.mesh import Mesh
    from . import project as PJ
    from .engine import structure as S
    from .engine import walls as W
    from .host import KEY, TERRAIN_LAYER
    H = high_area(doc)
    if H is None:
        return []
    low = low_z(doc)
    top = PJ.plot_top(doc)
    if top - low < 0.25:
        return []
    mesh = Mesh()
    n = 0
    parts = terraces(doc, H) or [(H, top)]      # 3.64.71: each terrace at
    parts = _apron(doc, parts)                  # 3.64.74: lower-floor forecourt
    for q, ztop in [(q_, z_) for g_, z_ in parts     # its own level
                    for q_ in getattr(g_, "geoms", [g_])]:
        if q.geom_type != "Polygon" or q.area < 0.5 or ztop - low < 0.2:
            continue
        q = q.simplify(0.02)
        outer = S._ccw([tuple(c) for c in list(q.exterior.coords)[:-1]])
        holes = [list(reversed(S._ccw([tuple(c) for c in
                                       list(r.coords)[:-1]])))
                 for r in q.interiors]
        for f in W.solid({"outer": outer, "holes": holes}, low, ztop):
            if isinstance(f, dict):
                PJ._safe_add(mesh, [QVector3D(*c) for c in f["loop"]],
                             [[QVector3D(*c) for c in hh]
                              for hh in f["holes"]])
            else:
                PJ._safe_add(mesh, [QVector3D(*c) for c in f])
        n += 1
    if not n:
        return []
    PJ._soften(mesh)
    gr = Group(mesh, name="Upper ground — earth fill and retaining walls")
    gr.component = False
    gr.material = {"color": FACE, "opacity": 1.0}
    gr.layer = TERRAIN_LAYER
    gr.ifc = {"class": "IfcWall", "name": "Retaining walls"}
    gr.ext = {KEY: {"type": "hill_fill", "id": "hill_fill",
                    "level": doc["hill"]["lower"]}}
    return [gr]


BOUND_RX = re.compile(r"BOUNDA?RY|BOUNDRY|COMPOUND", re.I)


def bound_lines(pl) -> list:
    """At the import: the plan's boundary-wall lines (not the plot's own
    limit line) — [[x0, y0, x1, y1]…] in model metres."""
    lay = pl["layers"]
    return [[round(s[0], 3), round(s[1], 3), round(s[2], 3), round(s[3], 3)]
            for s in pl["segs"] if BOUND_RX.search(str(lay[s[4]]))
            and math.dist(s[:2], s[2:4]) > 0.05]


def drawn_centres(doc):
    """The boundary walls as the plans draw them (3.64.68): one line of
    each double line, the beds' outlines (small closed shapes) left
    out, merged — shapely lines, or None."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import linemerge, polygonize, unary_union
    segs = []
    bl = doc.get("bound_lines") or {}
    lo = (doc.get("hill") or {}).get("lower")
    # 3.64.70: on a two-ground site the lower ground floor's plan draws
    # the whole boundary (the upper plan's lines are its beds, steps…)
    use = [lo] if on(doc) and bl.get(lo) else list(bl)
    for lid in use:
        segs += [((a, b), (c, d)) for a, b, c, d in bl.get(lid) or []]
    if len(segs) < 3:
        return None
    lines = [LineString(s) for s in segs]
    beds = []
    for f in polygonize(unary_union(lines)):
        r = f.minimum_rotated_rectangle
        cs = list(r.exterior.coords)[:4]
        sh = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
        if 1.0 < f.area < 150.0 and sh > 1.2:
            beds.append(Polygon(f.exterior).buffer(0.08))
    bu = unary_union(beds) if beds else None
    kept = []
    for ln in sorted(lines, key=lambda q: -q.length):
        if ln.length < 0.4:
            continue
        if bu is not None and bu.contains(ln):
            continue
        (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
        a = math.atan2(y1 - y0, x1 - x0)
        dup = False
        for k in kept:            # the other face of a double line
            (u0, v0), (u1, v1) = k.coords[0], k.coords[-1]
            b = math.atan2(v1 - v0, u1 - u0)
            da = abs((a - b + math.pi / 2) % math.pi - math.pi / 2)
            if da < math.radians(6) and k.distance(ln) < 0.4 and \
                    k.buffer(0.45).intersection(ln).length > 0.5 * ln.length:
                dup = True
                break
        if not dup:
            kept.append(ln)
    if not kept:
        return None
    m = linemerge(unary_union(kept))
    pcs = []
    for g in getattr(m, "geoms", [m]):
        if g.length < 3.0:              # (a scrap, a step's edge)
            continue
        c0, c1 = g.coords[0], g.coords[-1]
        if math.dist(c0, c1) < 0.6:     # a closed outline: a bed, a
            try:                        # planter — not the boundary
                if Polygon(list(g.coords)).buffer(0).area < 200.0:
                    continue
            except Exception:  # noqa: BLE001
                pass
        pcs.append(g)
    if not pcs:
        return None
    from shapely.geometry import MultiLineString
    return MultiLineString([list(g.coords) for g in pcs])


def drawn_parts(doc, site, z0) -> list:
    """The boundary wall built along the lines the plans draw (not round
    the plot): a low wall with its coping and the design's panels over
    it (or a solid wall), piers at the bays — [(name, kind, faces,
    colour)], standing on ``z0`` (``lift`` sets it on the ground)."""
    from shapely.geometry import LineString, MultiLineString
    from . import project as PJ
    from . import site as SITE
    from . import siteorn as SO
    cl = drawn_centres(doc)
    if cl is None:
        return []
    t = float(site.get("t", 0.23))
    h = float(site.get("h", 2.1))
    gap = max(float(site.get("pier_gap", 3.0) or 3.0), 1.5)
    pier = float(site.get("pillar", 0.35))
    style = site.get("front_style") or site.get("style", "plain")
    fin = site.get("front_finish") or site.get("finish", "plaster")
    col = SITE.WALL_FINISHES.get(fin, ("", SITE.WALL_COLOR))[1]
    over = style in SO.PIER_STYLES
    solid_top = z0 + (min(float(site.get("solid_h", 0.9)), h - 0.2)
                      if over else h - 0.075)
    # each run cut every bay (the wall then steps with the ground)
    runs = []
    for ln in cl.geoms:
        cs = list(ln.coords)
        for a, b in zip(cs, cs[1:]):
            L = math.dist(a, b)
            k = max(int(round(L / gap)), 1)
            for j in range(k):
                p = (a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k)
                q = (a[0] + (b[0] - a[0]) * (j + 1) / k,
                     a[1] + (b[1] - a[1]) * (j + 1) / k)
                runs.append(LineString([p, q]))
    at = ground_fn(doc)
    from shapely.geometry import Point, Polygon
    try:
        plot_g = Polygon(doc["arch"]["plot"]["corners"]).buffer(-0.3)
    except Exception:  # noqa: BLE001
        plot_g = None
    out = []
    for k, ln in enumerate(runs, 1):
        body = ln.buffer(t / 2, cap_style=2, join_style=2)
        # 3.64.69: on the upper ground's edge (the lower ground on its
        # other side): a parapet over the retaining wall, not a boundary
        (ax_, ay_), (bx_, by_) = ln.coords[0], ln.coords[-1]
        L_ = max(math.dist((ax_, ay_), (bx_, by_)), 1e-6)
        nx_, ny_ = -(by_ - ay_) / L_, (bx_ - ax_) / L_
        mx_, my_ = (ax_ + bx_) / 2, (ay_ + by_) / 2
        p1 = (mx_ + nx_ * 2.0, my_ + ny_ * 2.0)
        p2 = (mx_ - nx_ * 2.0, my_ - ny_ * 2.0)
        g1, g2 = at(*p1), at(*p2)
        if plot_g is not None and (not plot_g.contains(Point(*p1)) or
                                   not plot_g.contains(Point(*p2))):
            g1 = g2                  # (on the plot's edge: a full wall)
        if abs(g1 - g2) > 1.0:
            out.append((f"Parapet {k}", "boundary",
                        PJ._prism(body, z0, z0 + 1.05, 1e-5), col))
            cp = ln.buffer(t / 2 + 0.04, cap_style=2, join_style=2)
            out.append((f"Parapet {k} coping", "boundary",
                        PJ._prism(cp, z0 + 1.05, z0 + 1.12, 1e-5),
                        SITE.CAP_COLOR))
            continue
        out.append((f"Boundary wall {k}", "boundary",
                    PJ._prism(body, z0, solid_top, 1e-5), col))
        cp = ln.buffer(t / 2 + 0.04, cap_style=2, join_style=2)
        out.append((f"Boundary wall {k} coping", "boundary",
                    PJ._prism(cp, solid_top, solid_top + 0.075, 1e-5),
                    SITE.CAP_COLOR))
        if over:
            for nm_, fs_, c_ in SO.ornaments(style, MultiLineString(
                    [list(ln.coords)]), z0, solid_top + 0.075, h, t,
                    gap * 2, pier):
                out.append((nm_, "boundary", fs_, c_ or col))
        if site.get("pillars", True):             # a pier at its start
            a = ln.coords[0]
            from shapely.geometry import box
            sq = box(a[0] - pier / 2, a[1] - pier / 2, a[0] + pier / 2,
                     a[1] + pier / 2)
            out.append((f"Pillar {k}", "boundary",
                        PJ._prism(sq, z0, z0 + h + 0.1, 1e-5),
                        tuple(min(1.0, c * 0.95) for c in col)))
    return out


def densify(corners, front, step=3.0):
    """The plot's corners with its sides cut every ``step`` m (the wall
    then follows the ground side by side, stepping where the upper
    ground begins) and its front sides renumbered: (corners, front)."""
    out, fr = [], []
    n = len(corners)
    front = set(front or [])
    for i in range(n):
        a, b = corners[i], corners[(i + 1) % n]
        L = math.dist(a, b)
        k = max(int(round(L / step)), 1) if L > 1.5 * step else 1
        for j in range(k):
            t = j / k
            if i in front:
                fr.append(len(out))
            out.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
    return out, fr


def lift(doc, parts, z0):
    """The boundary wall's parts (built standing on ``z0``) set on the
    ground they run over: each point up by the ground there."""
    if not on(doc):
        return parts
    at = ground_fn(doc)
    cache = {}

    def dz(x, y):
        k = (round(x, 2), round(y, 2))
        if k not in cache:
            cache[k] = at(x, y) - z0
        return cache[k]

    def mv(p):
        return (p[0], p[1], p[2] + dz(p[0], p[1]))

    def face(f):
        if isinstance(f, dict):
            return dict(f, loop=[mv(p) for p in f["loop"]],
                        holes=[[mv(p) for p in hh] for hh in
                               f.get("holes") or []])
        return [mv(p) for p in f]
    out = []
    for part in parts:
        if isinstance(part, tuple):
            k = next((i for i, v in enumerate(part) if isinstance(v, list)),
                     None)
            if k is None:
                out.append(part)
            else:
                out.append(part[:k] + ([face(f) for f in part[k]],) +
                           part[k + 1:])
        elif isinstance(part, list):
            out.append([face(f) for f in part])
        elif isinstance(part, dict) and "faces" in part:
            out.append(dict(part, faces=[face(f) for f in part["faces"]]))
        else:
            out.append(part)
    return out
