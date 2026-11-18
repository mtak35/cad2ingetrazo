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
    if not on(doc):
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


def ground_fn(doc):
    """fn(x, y) → the ground's level there: the upper ground (the plot's
    top) on the upper plaza (with 1.5 m round it), else the lower road."""
    from shapely.geometry import Point
    from shapely.prepared import prep
    from . import project as PJ
    top = PJ.plot_top(doc)
    if not on(doc):
        return lambda x, y: top
    low = low_z(doc)
    H = high_area(doc)
    if H is None:
        return lambda x, y: low
    pH = prep(H.buffer(1.5))
    return lambda x, y: top if pH.contains(Point(x, y)) else low


def fill_groups(doc):
    """The earth of the upper ground (where the lower floor is not), from
    the lower road up to the upper plaza — its top the plaza, its sides
    the retaining walls."""
    if not on(doc):
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
    for q in getattr(H, "geoms", [H]):
        if q.geom_type != "Polygon" or q.area < 0.5:
            continue
        q = q.simplify(0.02)
        outer = S._ccw([tuple(c) for c in list(q.exterior.coords)[:-1]])
        holes = [list(reversed(S._ccw([tuple(c) for c in
                                       list(r.coords)[:-1]])))
                 for r in q.interiors]
        for f in W.solid({"outer": outer, "holes": holes}, low, top):
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
