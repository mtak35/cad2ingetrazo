# SPDX-License-Identifier: GPL-3.0-or-later
"""The CAD2IngeTrazo project: levels made from CAD plans, every element an
editable record, the model rebuilt from them — ONE Ctrl+Z each time.

The document slot (``scene.plugin_data["cad2ingetrazo"]``):

    {"arch":   ArchXQ-format building — project, levels, walls, openings,
               structure (columns, beams, slabs + holes, footings, roofs),
               rooms (names);  engine/model.py says every field,
     "imports": {level id: how its plan was read — file, units, base point,
               insertion, rotation, layer patterns, wall thicknesses},
     "texts":  [{"level", "text", "x", "y", "h", "rot"}]   the CAD's words,
     "settings": the defaults of the panel}

Everything ``build`` makes is a group tagged ``ext["cad2ingetrazo"] =
{"type", "id", "level"}`` on its level's layer (+ an IFC class), and the
plan-only annotations (dimension chains, texts, room labels) on each
level's «Annotations» layer.
"""
from __future__ import annotations

import copy
import fnmatch
import math
import re
import os

from . import cadread
from .engine import model as M
from .engine import spaces
from .engine import structure as S
from .engine import walldetect
from .engine import walls as W
from . import site as SITE_
from .host import (BOUNDARY_LAYER, FOUNDATION, KEY, LAYER_PREFIX, SITE,
                   SYMBOL_LAYER,
                   TERRAIN_LAYER, ann_layer, dim_layer, is_ann_layer,
                   level_layer, text_layer)

from .host import area_txt  # noqa: E402
PLOT_KEY = "__plot__"            # the import that gave the plot

#: the panel's defaults (the user's last choices live in QSettings)
DEFAULTS = {
    "walls": "*WALL*, A-WALL*, *MUR*",
    "doors": "*DOOR*, A-DOOR*",
    "windows": "*WIND*, *GLAZ*, A-GLAZ*",
    "columns": "*COL*, S-COL*",
    "beams": "*BEAM*, S-BEAM*",
    "slab": "*SLAB*, *FLOOR*OUTLINE*",
    "holes": "*STAIR*, *SHAFT*, *LIFT*, *VOID*, *DUCT*, *OPENING*",
    "text": "*",
    "plot": "*PLOT*, *SITE*, *BOUNDARY*, *PROP*",
    "footings": "*FOOT*, *FOUND*, *FNDN*",
    "stairs": "*STAIR*, *ESCAL*",
    "grid": "*GRID*, *AXIS*",
    "lift": "*LIFT*, *ELEVATOR*, *CORE*",
    "parking": "*PARK*",
    "cars": "*CAR*, *VEHIC*",
    "ramps": "*RAMP*",
    "cars_lib": True, "cad_lines": True, "levels_cad": True, "car_model": "suv", "park_nums": True, "marks_on": True, "ramp_t": 0.20,
    "win_style": "sliding", "door_style": "hinged", "door2_style": "hinged",
    "door_head": "flat", "win_head": "flat",
    "door_frame": "auto", "win_frame": "auto", "floor_h": 2.9972,
    "tmin": 0.08, "tmax": 0.40,
    "door_h": 2.10, "win_h": 1.20, "sill": 0.90,
    "slab_on": True, "slab_t": 0.15, "slab_pos": "top",
    "stair_rail": "ss_bars", "stair_rail_h": 0.9144, "stair_rail_sides": "inner",
    "stair_rail_off": 0.05, "stair_rail_gap": 0.0, "stair_rail_ext": 0.0,
    "parapet_rail": "solid",
    "finish_on": True, "finish_t": 0.0508,
    "beam_h": 0.45,
    "ann_rooms": True, "ann_texts": True,
    "auto_layers": True,
    "found_level": -1.50,          # m, the footings' bottom (±0.00 = floor)
    "plinth": 0.15,                # m, ground floor above the plot's ground
    "stair_type": "monolithic", "stair_waist": 0.1524,   # 6" waist slab
    "stair_nosing": 0.025, "stair_tread": 0.05,
}

IFC = {"wall": "IfcWall", "column": "IfcColumn", "beam": "IfcBeam",
       "slab": "IfcSlab", "footing": "IfcFooting", "roof": "IfcRoof",
       "core": "IfcWall"}
OPENING_IFC = {"door": "IfcDoor", "window": "IfcWindow", "void": "IfcOpeningElement"}
COLOR = {"stair": (0.74, 0.73, 0.70), "wall": (0.88, 0.86, 0.82), "column": (0.70, 0.71, 0.72),
         "core": (0.70, 0.71, 0.72),
         "beam": (0.66, 0.67, 0.69), "slab": (0.76, 0.77, 0.78),
         "footing": (0.60, 0.60, 0.58), "roof": (0.66, 0.36, 0.27),
         "opening": (0.94, 0.94, 0.92), "symbols": (0.17, 0.19, 0.22),
         "ramp": (0.64, 0.64, 0.62), "parking": (0.95, 0.95, 0.90),
         "landscape": (0.42, 0.66, 0.30), "car": (0.6, 0.6, 0.6),
         "room": (0.87, 0.84, 0.77), "stairrail": (0.78, 0.79, 0.80)}
BUILT = ("wall", "column", "core", "beam", "slab", "footing", "roof", "opening",
         "symbols", "parking", "ramp", "landscape", "car", "room", "stair",
         "stairrail")


# =====================================================================================
# The document
# =====================================================================================
def empty() -> dict:
    return {"arch": M.load({"project": M.new_project(name="")}),
            "imports": {}, "texts": [], "settings": dict(DEFAULTS),
            "site": SITE_.load_site(None), "grid": SITE_.load_grid(None),
            "stairs": [], "stair_cad": {}, "materials": {},
            "parking": {}, "ramps": [], "marks": {}, "landscape": {},
            "comp_names": {}}


def load(raw) -> dict:
    """A complete, valid project from whatever the document holds."""
    raw = raw if isinstance(raw, dict) else {}
    doc = empty()
    if isinstance(raw.get("arch"), dict):
        doc["arch"] = M.load(raw["arch"])
        if doc["arch"].get("project") is None:
            doc["arch"]["project"] = M.new_project(name="")
    ids = {lv["id"] for lv in doc["arch"]["levels"]}
    doc["imports"] = {k: v for k, v in (raw.get("imports") or {}).items()
                      if (k in ids or k in (FOUNDATION, PLOT_KEY))
                      and isinstance(v, dict)}
    doc["texts"] = [t for t in raw.get("texts") or []
                    if isinstance(t, dict) and t.get("level") in ids]
    doc["settings"].update({k: v for k, v in (raw.get("settings") or {}).items()
                            if k in DEFAULTS})
    doc["site"] = SITE_.load_site(raw.get("site"))
    doc["materials"] = {k: {"name": str(v.get("name", ""))[:40],
                            "color": [float(c) for c in v.get("color",
                                                              [0.8] * 3)][:3]}
                        for k, v in (raw.get("materials") or {}).items()
                        if isinstance(v, dict)}
    doc["stairs"] = [s for s in raw.get("stairs") or []
                     if isinstance(s, dict) and s.get("level") in ids
                     and (s.get("to") in ids or s.get("to") is None)
                     and len(s.get("corners") or []) == 4]
    doc["stair_cad"] = {k: v for k, v in (raw.get("stair_cad") or {}).items()
                        if k in ids and isinstance(v, list)}
    doc["grid"] = SITE_.load_grid(raw.get("grid"))
    doc["parking"] = {k: v for k, v in (raw.get("parking") or {}).items()
                      if k in ids and isinstance(v, dict)}
    doc["ramps"] = [r for r in raw.get("ramps") or []
                    if isinstance(r, dict) and r.get("level") in ids
                    and len(r.get("sections") or []) >= 2]
    doc["marks"] = {k: v for k, v in (raw.get("marks") or {}).items()
                    if k in ids and isinstance(v, list)}
    doc["landscape"] = {k: v for k, v in (raw.get("landscape") or {}).items()
                        if k in ids and isinstance(v, list)}
    # the component types' marks and names (components.py)
    doc["comp_names"] = {str(k): {kk: str(vv)[:80] for kk, vv in v.items()
                                  if kk in ("mark", "name")}
                         for k, v in (raw.get("comp_names") or {}).items()
                         if isinstance(v, dict) and v.get("mark")}
    return doc


def get(scene) -> dict:
    return load(copy.deepcopy((getattr(scene, "plugin_data", {}) or {})
                              .get(KEY)))


def elevations(arch):
    ground = (arch.get("project") or {}).get("ground_level", 0.0) or 0.0
    return M.elevations(arch["levels"], ground)


def level_by_id(arch, lid):
    return next((lv for lv in arch["levels"] if lv["id"] == lid), None)


# =====================================================================================
# A level from its CAD plan
# =====================================================================================
def _patterns(text: str):
    return [p.strip().upper() for p in str(text or "").split(",") if p.strip()]


def _match(name: str, pats) -> bool:
    n = (name or "").upper()
    return any(fnmatch.fnmatchcase(n, p) for p in pats)


def _rect_column(pts):
    """A column from a closed 4-corner outline: centre, sides, angle."""
    if len(pts) != 4:
        return None
    a, b, c = pts[0], pts[1], pts[2]
    w = math.dist(a, b)
    d = math.dist(b, c)
    if w < 0.05 or d < 0.05 or w > 3.0 or d > 3.0:
        return None
    cx = sum(p[0] for p in pts) / 4
    cy = sum(p[1] for p in pts) / 4
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    return {"x": round(cx, 4), "y": round(cy, 4), "w": round(w, 3),
            "d": round(d, 3), "angle": round(ang, 3), "shape": "rect"}


def columns_from(pl, pats, lay) -> list:
    """The columns a plan draws on its column layers: every closed outline
    (a polyline, or loose lines that close one), the outermost of nested
    ones, as a rectangle — up to a 15 m shear wall — or, when it is not
    one, an L / T / C section; circles as round columns."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union
    shapes = []
    for lp in pl["loops"]:
        if _match(lp["layer"], pats) and len(lp["pts"]) >= 3:
            g = Polygon(lp["pts"]).buffer(0)
            if g.geom_type == "Polygon":
                shapes.append(g)
    lines = [LineString([(s[0], s[1]), (s[2], s[3])]) for s in pl["segs"]
             if _match(lay[s[4]], pats) and
             math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-4]
    if lines:
        try:
            for f in polygonize(unary_union(lines)):
                if not any(sh.buffer(0.01).contains(f.representative_point())
                           for sh in shapes):
                    shapes.append(f)
        except Exception:  # noqa: BLE001
            pass
    shapes = [g for g in shapes if 0.0025 <= g.area <= 40.0]
    shapes.sort(key=lambda g: -g.area)
    kept = []
    for g in shapes:                  # a column drawn twice, or with an
        if any(k.buffer(0.02).contains(g) for k in kept):  # inner outline
            continue
        kept.append(g)
    out = []
    for g in kept:
        g = g.simplify(0.003)
        mrr = g.minimum_rotated_rectangle
        ring = list(mrr.exterior.coords)[:4]
        a, b, c = ring[0], ring[1], ring[2]
        w, d = math.dist(a, b), math.dist(b, c)
        if min(w, d) < 0.05 or max(w, d) > 15.0:
            continue
        if g.area >= 0.97 * mrr.area:            # a rectangle
            cx, cy = mrr.centroid.x, mrr.centroid.y
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            out.append({"x": round(cx, 4), "y": round(cy, 4),
                        "w": round(w, 3), "d": round(d, 3),
                        "angle": round(ang, 3), "shape": "rect"})
        else:                                    # an L / T / C section
            cx, cy = g.centroid.x, g.centroid.y
            pts = [[round(x - cx, 4), round(y - cy, 4)]
                   for x, y in list(g.exterior.coords)[:-1]]
            x0, y0, x1, y1 = g.bounds
            out.append({"x": round(cx, 4), "y": round(cy, 4),
                        "w": round(x1 - x0, 3), "d": round(y1 - y0, 3),
                        "angle": 0.0, "shape": "poly", "pts": pts})
    for ci in pl["circles"]:
        if _match(ci["layer"], pats) and 0.05 <= ci["r"] <= 1.5:
            out.append({"x": round(ci["c"][0], 4), "y": round(ci["c"][1], 4),
                        "w": round(2 * ci["r"], 3), "d": round(2 * ci["r"], 3),
                        "angle": 0.0, "shape": "round"})
    return out


def lift_cabin(shaft, gap=0.15) -> list:
    """A lift car in plan, in its shaft: the car (the shaft's rectangle set
    in by ``gap``), its counterweight along the back, and the X of the
    car — as plan segments."""
    from shapely.geometry import Polygon
    g = Polygon(shaft)
    if not g.is_valid or g.area < 1.0:
        return []
    r = g.minimum_rotated_rectangle
    q = list(r.exterior.coords)[:4]
    e1 = (q[1][0] - q[0][0], q[1][1] - q[0][1])
    e2 = (q[2][0] - q[1][0], q[2][1] - q[1][1])
    l1, l2 = math.hypot(*e1), math.hypot(*e2)
    if min(l1, l2) < 2 * gap + 0.6:
        return []
    u = (e1[0] / l1, e1[1] / l1)
    v = (e2[0] / l2, e2[1] / l2)
    o = q[0]

    def P(a, b):
        return (o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b)
    a0, a1 = gap, l1 - gap
    b0, b1 = gap, l2 - gap
    cw = min(0.25, (b1 - b0) * 0.15)            # the counterweight's depth
    car = [P(a0, b0 + cw + 0.05), P(a1, b0 + cw + 0.05), P(a1, b1),
           P(a0, b1)]
    out = list(zip(car, car[1:] + car[:1]))
    out += [(car[0], car[2]), (car[1], car[3])]
    m = (a0 + a1) / 2
    w = min(0.8, (a1 - a0) * 0.6) / 2
    cwt = [P(m - w, b0), P(m + w, b0), P(m + w, b0 + cw), P(m - w, b0 + cw)]
    out += list(zip(cwt, cwt[1:] + cwt[:1]))
    return out


#: dashed X marks on these are no slab opening (a ceiling, the grid…)
NOT_CUT = re.compile(r"CEIL|GRID|GIRD|AXIS|FURN|PIPE|DIM|TEXT|SECTION|"
                     r"HATCH|PROJ|SPLIT|F\.F|FIXT|EQUIP|TREE|LANDSC|SYMB|"
                     r"ARROW|LIGHT|ELEC|PLUMB|SANIT|DUCT.?LINE", re.I)


def slab_openings(segs, loops, skip=(), maxlen=8.0, maxarea=30.0) -> list:
    """Shaft / service openings in a floor slab, as the CAD draws them:
    a box crossed by an X (its two diagonals: their four ends are the
    opening's corners) or a closed outline. ``segs`` and ``loops`` are
    from the slab-hole layers (already in metres); ``skip``: outlines
    taken already (lift shafts). Returns the outlines, merged."""
    from shapely.geometry import MultiPoint, Polygon
    from shapely.ops import unary_union
    cand = []
    lines = []
    for s in segs:
        a, b = (s[0], s[1]), (s[2], s[3])
        L = math.dist(a, b)
        if 0.12 <= L <= maxlen:
            lines.append((a, b, L, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))
    # the X: two lines of about one length crossing at their middles
    lines.sort(key=lambda t: t[3])
    used = set()
    for i, (a, b, L, m) in enumerate(lines):
        if i in used:
            continue
        for j in range(i + 1, len(lines)):
            c, d, L2, m2 = lines[j]
            if m2[0] - m[0] > 0.05 * max(L, 1.0):
                break
            if j in used or math.dist(m, m2) > 0.03 * max(L, L2) + 0.01:
                continue
            if not 0.7 <= L / L2 <= 1.4:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            v = ((d[0] - c[0]) / L2, (d[1] - c[1]) / L2)
            if abs(u[0] * v[1] - u[1] * v[0]) < 0.25:     # parallel: no X
                continue
            g = MultiPoint([a, b, c, d]).convex_hull
            if g.geom_type == "Polygon" and 0.02 <= g.area <= maxarea:
                cand.append(g)
                used.update((i, j))
            break
    # closed outlines on the hole layers, of a shaft's size
    for lp in loops:
        if len(lp) >= 3:
            g = Polygon(lp)
            if g.is_valid and 0.05 <= g.area <= 30.0 and \
                    g.minimum_rotated_rectangle.length > 0:
                cand.append(g)
    taken = [Polygon(p).buffer(0.05) for p in skip if len(p) >= 3]
    cand = [g for g in cand if not any(t.intersects(g) for t in taken)]
    if not cand:
        return []
    u = unary_union([g.buffer(0.005) for g in cand]).buffer(-0.005)
    out = []
    for g in getattr(u, "geoms", [u]):
        if g.geom_type == "Polygon" and g.area >= 0.02:
            out.append([(round(x, 4), round(y, 4))
                        for x, y in list(g.simplify(0.01).exterior.coords)[:-1]])
    return out


def _poly_area(pts):
    return abs(0.5 * sum(p[0] * q[1] - q[0] * p[1]
                         for p, q in zip(pts, list(pts[1:]) + [pts[0]])))


def _outer_loop(pieces):
    """The outer contour of wall plan pieces (shapely)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = []
    for pc in pieces:
        p = Polygon(pc["outer"], pc["holes"])
        polys.append(p if p.is_valid else p.buffer(0))
    u = unary_union(polys).buffer(1e-4, join_style=2).buffer(-1e-4,
                                                             join_style=2)
    if u.is_empty:
        return None
    biggest = max(getattr(u, "geoms", [u]), key=lambda p: p.area)
    return list(biggest.exterior.coords)[:-1]


def _with_cores(blocks, cores, reach=2.5):
    """Slab outlines taking in the lift cores and the lobby between a core
    and the building (a gap of up to 2·``reach``)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    bp = [Polygon(b).buffer(0) for b in blocks if len(b) >= 3]
    cp = [Polygon(c).buffer(0) for c in cores if len(c) >= 3]
    if not bp or not cp:
        return blocks
    base = unary_union(bp)
    allp = unary_union(bp + cp)
    closed = allp.buffer(reach, join_style=2).buffer(-reach, join_style=2)
    near = unary_union([c.buffer(2 * reach + 0.5) for c in cp])
    add = closed.difference(base).intersection(near)
    u = unary_union([base] + cp + [add]).buffer(0.005, join_style=2) \
        .buffer(-0.005, join_style=2)
    out = []
    for g in sorted(getattr(u, "geoms", [u]), key=lambda q: -q.area):
        if g.geom_type == "Polygon" and g.area >= 20.0:
            out.append(list(g.simplify(0.005).exterior.coords)[:-1])
    return out or blocks


def _parking_slab(walls, segs, blocks, ratio=0.4):
    """A parking floor's slab: a close (concave) hull round its walls and
    the parking / ramp lines, with the wall blocks; the blocks it does
    not take stay their own slabs."""
    from shapely import concave_hull
    from shapely.geometry import MultiPoint, Polygon
    from shapely.ops import unary_union
    pts = [tuple(w["a"]) for w in walls if "a" in w] + \
        [tuple(w["b"]) for w in walls if "b" in w]
    pts += [(s_[0], s_[1]) for s_ in segs] + [(s_[2], s_[3]) for s_ in segs]
    if len(pts) < 3:
        return blocks
    hull = concave_hull(MultiPoint(pts), ratio=ratio)
    if hull.geom_type != "Polygon":
        return blocks
    bp = [Polygon(b) for b in blocks]
    big = unary_union([hull] + [b for b in bp if b.intersects(hull)])
    big = big.buffer(0.01, join_style=2).buffer(-0.01, join_style=2)
    if big.geom_type != "Polygon":
        big = max(big.geoms, key=lambda g: g.area)
    out = [list(big.simplify(0.01).exterior.coords)[:-1]]
    out += [b for b, p in zip(blocks, bp) if not p.intersects(big)]
    return out


def _outer_loops(pieces, gap=1.25, least=20.0):
    """Every building block's outer contour: the wall pieces closed over
    their door / window gaps (up to 2·``gap``), each block of
    ``least`` m² or more."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = []
    for pc in pieces:
        p = Polygon(pc["outer"], pc["holes"])
        polys.append(p if p.is_valid else p.buffer(0))
    if not polys:
        return []
    u = unary_union(polys).buffer(gap, join_style=2).buffer(-gap,
                                                           join_style=2)
    out = []
    for g in sorted(getattr(u, "geoms", [u]), key=lambda p: -p.area):
        if g.geom_type == "Polygon" and g.area >= least:
            out.append(list(g.simplify(0.005).exterior.coords)[:-1])
    return out


ROLE_KEYS = ("walls", "doors", "windows", "columns", "beams", "slab", "holes",
             "text", "plot", "footings", "stairs", "grid", "lift", "parking",
             "cars", "ramps")


def layer_patterns(drawing, how, st):
    """({role: patterns}, {role: [layers found]}): with «auto» on, each
    role the drawing's layers show (detect.py) takes those layers; the
    roles nothing shows keep the typed patterns."""
    from . import detect
    found = {}
    if how.get("auto", st.get("auto_layers", True)):
        found = detect.roles(drawing, float(how.get("tmin", st["tmin"])),
                             float(how.get("tmax", st["tmax"])))
    P = {}
    for k in ROLE_KEYS:
        typed = _patterns(how.get(k, st.get(k, "")))
        P[k] = [n.upper() for n in found.get(k) or []] and \
            [_escape(n) for n in found[k]] or typed
    return P, {k: v for k, v in found.items() if v}


def _escape(name: str) -> str:
    return "".join("[" + c + "]" if c in "*?[]" else c
                   for c in str(name).upper())


def north_from_cad(drawing: dict, region=None):
    """The north of a CAD plan, in degrees CLOCKWISE from the drawing's +Y
    (up), or None: a north-arrow block's turn, else a compass drawn in
    lines with an «N» at the tip of its needle (the longest line that ends
    at the letter, read from its tail to the tip). The arrow nearest the
    floor picked (``region``) wins."""
    import re as _re
    cand = []
    for b in drawing.get("inserts") or []:
        if _re.search(r"NORTH|N[-_ ]?ARROW|COMPASS|NORTE|NORD",
                      str(b.get("name", "")), _re.I):
            cand.append(((b.get("x", 0.0), b.get("y", 0.0)),
                         (-float(b.get("rot", 0.0) or 0.0)) % 360.0))
    if not cand:
        segs = drawing.get("segs") or []
        for t in drawing.get("texts") or []:
            if str(t.get("text", "")).strip().upper() not in ("N", "NORTH"):
                continue
            if _re.search(r"GRID|AXIS|GRD", str(t.get("layer", "")), _re.I):
                continue
            h = max(float(t.get("h", 0) or 0), 1e-6)
            tx, ty = float(t["x"]), float(t["y"])
            best = None
            for x0, y0, x1, y1, _l in segs:
                for (ax, ay), (bx, by) in (((x0, y0), (x1, y1)),
                                           ((x1, y1), (x0, y0))):
                    # b: the tip, near the letter; a: the tail, far off
                    if math.hypot(bx - tx, by - ty) > 2.5 * h:
                        continue
                    L = math.hypot(bx - ax, by - ay)
                    if L < 3 * h or L > 25 * h:
                        continue
                    if best is None or L > best[0]:
                        best = (L, ax, ay, bx, by)
            if best is None:
                continue
            L, ax, ay, bx, by = best
            # a compass: other lines cross near the needle's middle
            mx, my = (ax + bx) / 2, (ay + by) / 2
            near = sum(1 for x0, y0, x1, y1, _l in segs
                       if math.hypot((x0 + x1) / 2 - mx, (y0 + y1) / 2 - my)
                       < 0.6 * L)
            if near < 6:
                continue
            ang = math.degrees(math.atan2(bx - ax, by - ay)) % 360.0
            cand.append(((tx, ty), ang))
    if not cand:
        return None
    if region:
        cx, cy = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
        cand.sort(key=lambda c: math.hypot(c[0][0] - cx, c[0][1] - cy))
    return round(cand[0][1], 2)


def north_from_imports(doc: dict):
    """The CAD's north for a model imported before the north was read:
    from the first level's file (None when it has no north arrow)."""
    st = doc["settings"]
    for k, how in doc["imports"].items():
        if k.startswith("__") or not how.get("file") or \
                not os.path.exists(how["file"]):
            continue
        nd = north_from_cad(cadread.read(how["file"], how.get("unit")),
                            how.get("region"))
        if nd is None:
            continue
        st["north_cad"] = round((nd - float(how.get("rot", 0.0))) % 360.0, 2)
        if st.get("north_src", "cad") == "cad":
            set_north(doc, st["north_cad"], "cad")
        return st["north_cad"]
    return None


def set_north(doc: dict, deg: float, src: str = "manual") -> None:
    """The project north, degrees clockwise from the model's +Y (plans'
    up): the north arrows, the elevations' names."""
    doc["arch"].setdefault("project", {})["north_deg"] = \
        round(float(deg) % 360.0, 2)
    doc["settings"]["north_src"] = src


def north_of(doc: dict) -> float:
    return float((doc["arch"].get("project") or {}).get("north_deg", 0.0)
                 or 0.0)


def import_level(doc: dict, lid: str, path: str, how: dict) -> dict:
    """Read ``path`` onto level ``lid`` in place of what an earlier import
    of it made: walls with their doors and windows, columns, beams, the
    floor slab with its holes, the room names and the CAD's texts.
    ``how``: unit, base mode/point, insertion, rotation, layer patterns.
    Returns a report {walls, openings, columns, beams, slab, texts, rooms,
    skipped: [why…], far_km}."""
    st = doc["settings"]
    arch = doc["arch"]
    raw = cadread.read(path, how.get("unit"))
    drawing = cadread.crop(raw, how.get("region"))
    base = cadread.base_point(drawing, how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    far = cadread.far_from_base(drawing, base)
    pl = cadread.place(drawing, base, (how.get("ix", 0.0), how.get("iy", 0.0)),
                       how.get("rot", 0.0))
    lay = pl["layers"]
    P, roles_found = layer_patterns(drawing, how, st)
    # the project north, read from the CAD's north arrow (the whole file,
    # not only the floor picked); the import's own turn turns it too
    try:
        nd = north_from_cad(raw, how.get("region"))
    except Exception:  # noqa: BLE001
        nd = None
    if nd is not None:
        st["north_cad"] = round((nd - float(how.get("rot", 0.0))) % 360.0, 2)
        if st.get("north_src", "cad") == "cad":
            set_north(doc, st["north_cad"], "cad")
    rep = {"walls": 0, "openings": 0, "columns": 0, "beams": 0, "slab": 0,
           "holes": 0, "texts": 0, "rooms": 0, "skipped": [],
           "far_km": far / 1000.0, "unit_note": drawing["unit_note"],
           "unit_k": drawing["unit"],
           "layers": {n: 0 for n in lay}, "roles": roles_found}
    for s in pl["segs"]:
        rep["layers"][lay[s[4]]] += 1

    # what an earlier import of this level made goes
    old_walls = {w["id"] for w in arch["walls"] if w["level"] == lid}
    arch["walls"] = [w for w in arch["walls"] if w["level"] != lid]
    arch["openings"] = [o for o in arch["openings"]
                        if o["wall"] not in old_walls]
    arch["structure"] = [e for e in arch["structure"]
                         if e["level"] != lid or e["type"] in ("footing",
                                                               "roof")]
    arch["rooms"] = [r for r in arch["rooms"] if r["level"] != lid]
    doc["texts"] = [t for t in doc["texts"] if t["level"] != lid]

    # walls and their openings
    wall_segs = [s for s in pl["segs"] if _match(lay[s[4]], P["walls"])]
    tmin = float(how.get("tmin", st["tmin"]))
    tmax = float(how.get("tmax", st["tmax"]))
    if how.get("auto", st.get("auto_layers", True)):
        # automatic: every wall the plan holds — 3" partitions to 18"
        # walls — whatever the range typed
        tmin, tmax = min(tmin, 0.07), max(tmax, 0.46)
    found, ops = walldetect.walls_from(wall_segs, tmin, tmax,
                                       context=pl["segs"])
    recs = [{"kind": "line", "a": [round(a[0], 4), round(a[1], 4)],
             "b": [round(b[0], 4), round(b[1], 4)],
             "t": round(t * 200) / 200, "align": "centre", "side": 1,
             "height": "level", "base": 0.0, "level": lid}
            for a, b, t in found]
    recs, shifted = heal_walls(recs)
    made = M.new_walls(arch["walls"], recs)
    arch["walls"] += made
    rep["walls"] = len(made)
    orecs = []
    for op in ops:
        k, pos, width = op[:3]
        kind = op[3] if len(op) > 3 else ("door" if width <= 1.2
                                          else "window")
        hinge = op[4] if len(op) > 4 else -1
        face = op[5] if len(op) > 5 else 1
        style = ""
        if kind == "sliding":                  # open to the floor, nothing
            kind, style = "door", "sliding"    # drawn: a glass sliding door
        door = kind == "door"
        # the hinge and the side the leaf opens to, as the CAD's swing
        # shows them (the wall's line runs a → b; «left» = at a)
        orecs.append({"kind": kind, "wall": made[k]["id"],
                      "pos": round(pos + shifted[k], 4), "w": round(width, 3),
                      "h": float(st["door_h"] if door else st["win_h"]),
                      "sill": 0.0 if door else float(st["sill"]),
                      "swing": "right" if hinge > 0 else "left",
                      "face": face or 1,
                      "style": style or ("hinged" if door else
                                         st.get("win_style", "sliding"))})
    # doors and windows drawn as blocks (named DOOR…, WINDOW…, or on the
    # door / window layers): placed in the wall they stand in — and a gap
    # the walls showed takes its kind from the block over it
    orecs, rep["blocks"] = _block_openings(pl, made, orecs, P, st)
    for o in orecs:
        door_rule(o)
        opening_types(o, st)
    arch["openings"] += M.new_openings(arch["openings"], orecs)

    # columns: closed outlines, loose lines and circles on the column
    # layers — rectangles (long shear walls too), and L / T / C sections
    cols = columns_from(pl, P["columns"], lay)
    seen = set()
    crecs = []
    for c in cols:                     # a column drawn twice (block + lines)
        key = (round(c["x"], 2), round(c["y"], 2))
        if key in seen:
            continue
        seen.add(key)
        crecs.append(dict(c, type="column", level=lid, anchor="centre",
                          base=0.0, height="level", fit=False))
    # lift cores: the RCC walls round the shafts, as one solid (like the
    # columns); the shafts cut the floor slab
    lift_segs = [s for s in pl["segs"] if _match(lay[s[4]], P["lift"])]
    cores, shafts, ldoors = lift_cores(lift_segs)
    lrecs = [{"type": "core", "level": lid,
              "corners": [[round(p[0], 4), round(p[1], 4)] for p in c],
              "holes": [[[round(p[0], 4), round(p[1], 4)] for p in h]
                        for h in hs],
              "base": 0.0, "height": "level", "doors": []}
             for c, hs in cores]
    if lrecs:                    # each shaft to the core walling it in
        from shapely.geometry import Polygon as _Pg2
        for sh in shafts:
            sp = _Pg2(sh)
            best = min(lrecs, key=lambda r: _Pg2(r["corners"]).distance(sp))
            best.setdefault("shafts", []).append(
                [[round(p[0], 4), round(p[1], 4)] for p in sh])
    # a lift well drawn in the walls and the columns only (no lift layer),
    # its name written in it: «LIFT», «LIFT WELL», «ELEVATOR»
    for sh in lift_wells_by_text(pl, P, shafts,
                                 [c for c, _h in cores]):
        shafts.append(sh)
        rep["lift_wells"] = rep.get("lift_wells", 0) + 1
    if lrecs:                    # each landing door to the core it is in
        from shapely.geometry import Point as _Pt, Polygon as _Pg
        for dr in ldoors:
            m = _Pt((dr["a"][0] + dr["b"][0]) / 2,
                    (dr["a"][1] + dr["b"][1]) / 2)
            best = min(lrecs, key=lambda r: _Pg(r["corners"]).distance(m))
            best["doors"].append(dict(dr, h=max(2.1, float(st["door_h"]))))
    # the lift wells stay hollow on every floor (the lowest one too: the
    # pit under it)
    # beams: pairs of lines on the beam layers
    beam_segs = [s for s in pl["segs"] if _match(lay[s[4]], P["beams"])]
    brecs = []
    if beam_segs:
        bw, _bo = walldetect.walls_from(beam_segs, 0.12, 1.0)
        brecs = [{"type": "beam", "level": lid,
                  "a": [round(a[0], 4), round(a[1], 4)],
                  "b": [round(b[0], 4), round(b[1], 4)],
                  "w": round(t, 3), "h": float(st["beam_h"]), "fit": False}
                 for a, b, t in bw]
    # the floor slab: an outline on the slab layers, or round the walls
    srecs = []
    if st.get("slab_on", True):
        cands = [lp["pts"] for lp in pl["loops"]
                 if _match(lp["layer"], P["slab"]) and _poly_area(lp["pts"]) > 1]
        if cands:
            outlines = [max(cands, key=_poly_area)]
        else:                  # round the walls: every building block
            mine = [w for w in arch["walls"] if w["level"] == lid]
            plans = W.plan([w for w in mine if W.why_not(w) is None])
            blocks = _outer_loops([pc for ps in plans.values() for pc in ps])
            # a parking floor: the drive and the ramps under the slab too —
            # a close hull round the walls, the bays and the ramps
            pk = [s_ for s_ in pl["segs"] if _match(lay[s_[4]], P["parking"])
                  or _match(lay[s_[4]], P["ramps"])]
            if pk and mine:
                try:
                    blocks = _parking_slab(mine, pk, blocks)
                except Exception:  # noqa: BLE001
                    from .host import log_error
                    log_error("project._parking_slab")
            # the lift cores and their lobbies: under the slab too (the
            # gap between a core and the building, up to 5 m, closed)
            if lrecs:
                try:
                    blocks = _with_cores(blocks, [r["corners"] for r in lrecs])
                except Exception:  # noqa: BLE001
                    from .host import log_error
                    log_error("project._with_cores")
            outlines = [[[round(p[0], 4), round(p[1], 4)] for p in S._ccw(o)]
                        for o in blocks]
        from shapely.geometry import Point, Polygon
        # shafts and slab openings: X-marked boxes and closed outlines on
        # the slab-hole layers (stair and lift wells: their own parts)
        hsegs = [s for s in pl["segs"] if _match(lay[s[4]], P["holes"])
                 and not _match(lay[s[4]], P["stairs"])]
        hloops = [lp["pts"] for lp in pl["loops"]
                  if _match(lp["layer"], P["holes"])
                  and not _match(lp["layer"], P["stairs"])]
        openings_all = slab_openings(hsegs, hloops, shafts)
        # an X in a hidden (dashed) line type: the slab cut there, on any
        # layer but a ceiling's, the grid's, the furniture's…
        dsh = pl.get("dashed") or []
        if len(dsh) == len(pl["segs"]):
            xsegs = [s for s, dd in zip(pl["segs"], dsh)
                     if dd and not NOT_CUT.search(lay[s[4]])
                     and not _match(lay[s[4]], P["stairs"])]
            xo = slab_openings(xsegs, [], shafts + openings_all, maxlen=30.0,
                               maxarea=400.0)
            rep["voids"] = len(xo)
            openings_all = openings_all + xo
        rep["shafts"] = 0
        for outline in outlines:
            poly = Polygon(outline)
            inner = poly.buffer(-0.02) if poly.is_valid else poly.buffer(0)
            sh_open = [h for h in openings_all
                       if inner.contains(Polygon(h).representative_point())]
            holes = [list(h) for h in sh_open]
            for sh in shafts:
                cut = Polygon(sh).intersection(inner)
                for g in getattr(cut, "geoms", [cut]):
                    if g.geom_type == "Polygon" and g.area > 0.5:
                        holes.append(list(g.exterior.coords)[:-1])
            srecs.append({"type": "slab", "level": lid,
                          "corners": [[round(p[0], 4), round(p[1], 4)]
                                      for p in outline],
                          "holes": [[[round(p[0], 4), round(p[1], 4)]
                                     for p in h] for h in holes],
                          "t": float(st["slab_t"]), "offset": 0.0,
                          "shafts": [[[p[0], p[1]] for p in h]
                                     for h in sh_open]})
            rep["slab"] += 1
            rep["holes"] += len(holes)
            rep["shafts"] += len(sh_open)
    new = [r for r in crecs + lrecs + brecs + srecs if S.why_not(r) is None]
    arch["structure"] += M.new_elements(arch["structure"], new)
    rep["columns"] = sum(1 for r in new if r["type"] == "column")
    rep["beams"] = sum(1 for r in new if r["type"] == "beam")
    rep["cores"] = sum(1 for r in new if r["type"] == "core")

    # the CAD's words, and the rooms named by the text inside them
    texts = [dict(t, level=lid) for t in pl["texts"]
             if _match(t["layer"], P["text"])]
    doc["texts"] += [{k: t[k] for k in ("level", "text", "x", "y", "h", "rot",
                                        "layer")} for t in texts]
    rep["texts"] = len(texts)
    mine = [w for w in arch["walls"] if w["level"] == lid]
    from shapely.geometry import Point
    rrecs = []
    for room in spaces.found(mine):
        inside = [t for t in texts
                  if room["poly"].contains(Point(t["x"], t["y"]))
                  and len(t["text"]) <= 40 and not
                  t["text"].replace(".", "").replace(",", "").strip()
                  .isdigit()]
        if inside:
            name = max(inside, key=lambda t: t["h"])["text"].split("\n")[0]
            rrecs.append({"id": "", "level": lid, "x": room["at"][0],
                          "y": room["at"][1], "name": name.strip()[:60]})
    arch["rooms"] = M._rooms(arch["rooms"] + rrecs,
                             {lv["id"] for lv in arch["levels"]})
    rep["rooms"] = len(spaces.found(mine))

    # stair wells drawn on the stair layers (Stairs builds them, floor to
    # floor)
    from . import stairs as ST
    wells = ST.from_cad(pl, lambda n: _match(n, P["stairs"]))
    if wells:
        doc["stair_cad"][lid] = wells
    else:
        doc["stair_cad"].pop(lid, None)
    rep["stairs"] = len(wells)

    # car parking, car ramps and the level notes, as the CAD draws them
    try:
        rep.update(_parking_import(doc, lid, pl, P))
    except Exception:  # noqa: BLE001 — never blocks the floor
        from .host import log_error
        log_error("project._parking_import")

    # the CAD's column grid: its axes, as drawn, on every plan
    gsegs = [((s[0], s[1]), (s[2], s[3])) for s in pl["segs"]
             if _match(lay[s[4]], P["grid"])]
    if gsegs:
        gtexts = [(t["x"], t["y"], t["text"]) for t in pl["texts"]]
        glines = SITE_.grid_from_cad(gsegs, gtexts, pl["circles"])
        if glines:
            have = doc["grid"].get("lines") or [] \
                if doc["grid"]["source"] == "cad" else []
            keep = [g for g in have if not any(SITE_._seg_close(
                (tuple(g["a"]), tuple(g["b"])), (tuple(n["a"]), tuple(n["b"])),
                0.15) for n in glines)]
            doc["grid"] = SITE_.load_grid(dict(doc["grid"], on=True,
                                               source="cad",
                                               lines=keep + glines))
            rep["grid"] = len(glines)
            # the grid's bubble texts: drawn by the grid itself — not twice
            # as the CAD's words too
            ends = [(tuple(g["a"]), g["label"]) for g in glines] + \
                [(tuple(g["b"]), g["label"]) for g in glines]

            def bubble(t):
                if t["level"] != lid:
                    return False
                if _match(t.get("layer", ""), P["grid"]) or re.search(
                        r"GRID|GIRD|AXIS|AXES", str(t.get("layer", "")).upper()):
                    return True
                w = str(t["text"]).strip()
                return any(w == lab and math.dist((t["x"], t["y"]), e) < 2.5
                           for e, lab in ends)
            before = len(doc["texts"])
            doc["texts"] = [t for t in doc["texts"] if not bubble(t)]
            rep["texts"] = max(0, rep.get("texts", 0) -
                               (before - len(doc["texts"])))

    # the plot, when this part of the drawing holds its boundary
    rep["plot"] = False
    mine_plot = not doc["arch"].get("plot") or \
        doc["imports"].get(PLOT_KEY, {}).get("level") == lid
    if mine_plot and (roles_found.get("plot") or how.get("plot_from_cad")):
        loop = plot_from_loop(pl, P)
        if loop and set_plot(doc, loop) is None:
            rep["plot"] = True
            doc["imports"][PLOT_KEY] = dict(how, file=str(path), level=lid)

    # openings the wall can't hold (too tall, at an end…) are left out
    rep["skipped"] += validate_openings(arch)
    rep["openings"] = sum(1 for o in arch["openings"]
                          if o["wall"] in {w["id"] for w in made})
    try:
        mt = os.path.getmtime(path)
    except OSError:
        mt = 0.0
    doc["imports"][lid] = dict(how, file=str(path), mtime=mt,
                               unit_k=drawing["unit"])
    # the floor levels the CAD notes («LEV. +4'-0"»): the levels set so
    if st.get("levels_cad", True):
        try:
            rep["levels_set"] = levels_from_cad(doc)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.levels_from_cad")
        try:                     # one floor at several levels, as noted
            arch["structure"] = [e for e in arch["structure"]
                                 if not (e.get("zone") and e["level"] == lid)]
            rep["zones"] = slab_zones(doc, lid)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.slab_zones")
    return rep


def _parking_import(doc, lid, pl, P) -> dict:
    """The level's parking bays and cars, its ramps (their wells cut in the
    slabs) and its level notes."""
    from . import parking as PK
    lay = pl["layers"]

    def on(s, role):
        return _match(lay[s[4]], P[role])
    bays = [[[round(s[0], 4), round(s[1], 4)], [round(s[2], 4), round(s[3], 4)]]
            for s in pl["segs"] if on(s, "parking")]
    carl = [[[round(s[0], 4), round(s[1], 4)], [round(s[2], 4), round(s[3], 4)]]
            for s in pl["segs"] if on(s, "cars")]
    cars = []
    for ins in pl.get("inserts", ()):
        if _match(ins["layer"], P["cars"]) or \
                re.search(r"(^|[^A-Z])(CAR|VEHIC)", str(ins["name"]).upper()):
            c = PK.car_of(ins)
            if c:
                cars.append(c)
    stalls = PK.stalls_of(bays, cars)
    if bays or cars:
        doc["parking"][lid] = {"bays": bays, "carlines": carl, "cars": cars,
                               "stalls": stalls}
    else:
        doc["parking"].pop(lid, None)
    # ramps: the old ones of this level out (their wells closed), the new in
    _ramp_uncut(doc, lid)
    doc["ramps"] = [r for r in doc["ramps"] if r["level"] != lid]
    rsegs = [s[:4] for s in pl["segs"] if on(s, "ramps")]
    arrows = [(i["x"], i["y"], i["rot"]) for i in pl.get("inserts", ())
              if re.search(r"ARR|ARROW", (str(i["name"]) + " " +
                                          str(i["layer"])).upper())]
    made = PK.ramps_from(rsegs, pl["texts"], arrows) if rsegs else []
    try:                # the pieces, turns and lanes: one ramp per route
        made = PK.routes(made, rsegs, pl["texts"]) or made
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.routes")
    try:                # widened to the walls round them (no gap left)
        from shapely.ops import unary_union as _uu
        from shapely.geometry import Polygon as _Pg
        mine_w = [w for w in doc["arch"]["walls"] if w["level"] == lid]
        pcs = [pc for ps in W.plan([w for w in mine_w
                                    if W.why_not(w) is None]).values()
               for pc in ps]
        wall_u = _uu([_Pg(pc["outer"], pc["holes"]).buffer(0) for pc in pcs])
        for r in made:
            PK.to_walls(r, wall_u)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.to_walls")
    try:                # ends cut along a slanted edge the plan draws
        for r in made:
            PK.fit_ends(r, rsegs)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.to_walls")
    for i, r in enumerate(made):
        r.update(level=lid, id=f"ramp-{lid}-{i + 1}", name=f"Ramp {i + 1}",
                 t=float(doc["settings"].get("ramp_t", 0.20)))
    doc["ramps"] += made
    cut = _ramp_cut(doc, lid)
    # level notes («LEV. +4'-0"», «FFL …»)
    marks = []
    for t in pl["texts"]:
        v = PK.level_note(t["text"])
        if v:
            marks.append({"x": round(t["x"], 4), "y": round(t["y"], 4),
                          "text": v[0], "v": v[1],
                          "a": PK.abs_level(t["text"])})
    if marks:
        doc["marks"][lid] = marks
    else:
        doc["marks"].pop(lid, None)
    # landscape (soft) areas: in green
    from . import landscape as LS
    try:
        green = LS.areas(pl)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.landscape")
        green = []
    if green:
        doc["landscape"][lid] = [[list(p) for p in a] for a in green]
    else:
        doc["landscape"].pop(lid, None)
    return {"bays": len(bays), "cars": len(cars), "stalls": len(stalls),
            "ramps": len(made),
            "ramp_cuts": cut, "marks": len(marks), "green": len(green)}


def _ramp_level_above(arch, lid):
    el = elevations(arch)
    ids = [v["id"] for _e, v in sorted(zip(el, arch["levels"]),
                                       key=lambda p: p[0])]
    i = ids.index(lid) if lid in ids else -1
    return ids[i + 1] if 0 <= i < len(ids) - 1 else None


def _ramp_level_below(arch, lid):
    el = elevations(arch)
    ids = [v["id"] for _e, v in sorted(zip(el, arch["levels"]),
                                       key=lambda p: p[0])]
    i = ids.index(lid) if lid in ids else -1
    return ids[i - 1] if i > 0 else None


def slab_on_top(doc) -> bool:
    """Each floor's slab cast OVER it, on its walls (the default) — not
    under it at its floor level."""
    return (doc.get("settings") or {}).get("slab_pos", "top") == "top"


def apply_slab_pos(doc) -> None:
    """The levels' main slabs marked for where they stand (``top``: over
    the floor) — the CAD zones, the parts sunk / raised and the roof
    slabs keep theirs."""
    on_top = slab_on_top(doc)
    for s in doc["arch"]["structure"]:
        if s["type"] != "slab" or s.get("zone") or s.get("user") \
                or s.get("roof"):
            continue
        if on_top:
            s["top"] = True
        else:
            s.pop("top", None)


def recut_wells(doc) -> dict:
    """The stair and ramp wells cut again in the slabs that hold them now
    (after the slabs moved over / under the floors)."""
    from . import stairs as ST
    out = {"stairs": 0, "ramps": 0}
    try:
        out["stairs"] = ST.auto(doc).get("cuts", 0)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.recut_wells stairs")
    for lv in doc["arch"]["levels"]:
        try:
            _ramp_uncut(doc, lv["id"])
            for r in doc["ramps"]:
                if r["level"] == lv["id"]:
                    r.pop("cut", None)
            out["ramps"] += _ramp_cut(doc, lv["id"])
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.recut_wells ramps")
    return out


def _ramp_cut(doc, lid) -> int:
    """A ramp going down: its well in its own floor's slab; going up: in
    the slab of the floor above."""
    from . import parking as PK
    from . import stairs as ST
    arch = doc["arch"]
    n = 0
    for r in doc["ramps"]:
        if r["level"] != lid:
            continue
        if slab_on_top(doc):     # the slab over each floor is its own
            where = _ramp_level_below(arch, lid) if float(r["rise"]) < 0 \
                else lid
        else:
            where = lid if float(r["rise"]) < 0 \
                else _ramp_level_above(arch, lid)
        if where is None:
            continue
        fp = PK.footprint(r, pads=True)
        n += _cut_exact(arch, where, fp)
        r.setdefault("cut", []).append(where)
    return n


def _cut_exact(arch, lid, shape) -> int:
    """``shape`` (shapely) cut out of the level's slabs exactly: joined
    with the holes it touches, never widened to a hull (the slab round a
    lift core stays)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    n = 0
    for s in arch["structure"]:
        if s["type"] != "slab" or s["level"] != lid:
            continue
        outer = Polygon(s["corners"])
        if not outer.is_valid:
            outer = outer.buffer(0)
        part = outer.buffer(-0.02).intersection(shape)
        if part.is_empty or part.area < 0.5:
            continue
        holes = [Polygon(h).buffer(0) for h in s.get("holes") or []
                 if len(h) >= 3]
        touch = [h for h in holes if h.intersects(part)]
        keep = [h for h in holes if not h.intersects(part)]
        u = unary_union(touch + [part]).intersection(outer.buffer(-0.02))
        new = []
        for g in getattr(u, "geoms", [u]):
            if g.geom_type == "Polygon" and g.area >= 0.05:
                new.append([[round(x, 4), round(y, 4)] for x, y in
                            list(g.simplify(0.01).exterior.coords)[:-1]])
        s["holes"] = [[[round(x, 4), round(y, 4)] for x, y in
                       list(h.exterior.coords)[:-1]] for h in keep] + new
        n += 1
    return n


def _ramp_uncut(doc, lid) -> None:
    """The wells the level's ramps cut before, closed."""
    from shapely.geometry import Polygon

    from . import parking as PK
    olds = [PK.footprint(r, pads=True) for r in doc["ramps"]
            if r["level"] == lid]
    if not olds:
        return
    for s in doc["arch"]["structure"]:
        if s["type"] != "slab":
            continue
        keep = []
        for h in s.get("holes") or []:
            hp = Polygon(h)
            if hp.is_valid and hp.area >= 0.5 and any(
                    hp.intersection(o).area >= 0.8 * hp.area for o in olds):
                continue
            keep.append(h)
        s["holes"] = keep


SINGLE_MAX = 4 * 0.3048          # 4'-0": one leaf at most
DOUBLE_MAX = 8 * 0.3048          # 8'-0": two leaves at most


def lift_cores(segs, tmin=0.14, tmax=0.60, close=0.8):
    """([(outline, holes)], [shaft outline]) from the lines of the lift
    layers (metres): the core's concrete is every thin closed strip the
    lines make (a wall 6"–24" thick) that joins the core's outside —
    the cabins, their frames and the counterweights stand free inside
    and are not walls; a shaft is what the core holds round, its door
    gaps closed."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    lines = []
    for s in segs:
        a, b = (s[0], s[1]), (s[2], s[3])
        d = math.dist(a, b)
        if d < 1e-4:
            continue
        ex, ey = (b[0] - a[0]) / d * 0.004, (b[1] - a[1]) / d * 0.004
        lines.append(LineString([(a[0] - ex, a[1] - ey),
                                 (b[0] + ex, b[1] + ey)]))
    if len(lines) < 4:
        return [], [], []
    faces = [f for f in polygonize(unary_union(lines)) if f.area > 0.01]
    if not faces:
        return [], [], []
    whole = unary_union(faces)
    foot = whole.buffer(close, join_style=2).buffer(-close, join_style=2)
    # a bank of lifts drawn as one U of wall (no walls between the cars,
    # the front only piers): the closing leaves it open — its hull then
    parts = []
    for g in getattr(whole.buffer(close, join_style=2), "geoms",
                     [whole.buffer(close, join_style=2)]):
        f = foot.intersection(g)
        hull = whole.intersection(g).convex_hull
        if hull.area > 1.0 and f.area < 0.6 * hull.area:
            f = hull
        parts.append(f)
    foot = unary_union(parts)
    if foot.geom_type == "Polygon":
        from shapely.geometry import Polygon as _Pf
        foot = _Pf(foot.exterior)
    rim = foot.boundary
    thin = [f for f in faces if not f.interiors
            and not f.buffer(-tmin / 2).is_empty
            and f.buffer(-tmax / 2).is_empty]
    if not thin:
        return [], [], []
    u = unary_union([f.buffer(0.003, join_style=2) for f in thin]) \
        .buffer(-0.003, join_style=2)
    keep = [g for g in getattr(u, "geoms", [u])
            if g.geom_type == "Polygon" and g.area > 0.05
            and g.buffer(0.02).intersects(rim)]
    if not keep:
        return [], [], []
    core = unary_union(keep)
    cores = []
    for g in getattr(core, "geoms", [core]):
        g = g.simplify(0.005)
        cores.append(([p[:2] for p in list(g.exterior.coords)[:-1]],
                      [[p[:2] for p in list(h.coords)[:-1]]
                       for h in g.interiors]))
    rest = foot.difference(core.buffer(0.001))
    from shapely.geometry import LineString as _LS
    from shapely.ops import linemerge
    edge = foot.exterior if foot.geom_type == "Polygon" else foot.boundary
    shafts, doors = [], []
    for g in getattr(rest, "geoms", [rest]):
        if g.geom_type != "Polygon" or g.area < 1.0:
            continue
        cen = g.centroid
        # its door: where the shaft reaches the core's outside — a gap
        # through the front wall, as deep as the wall beside it
        mouth = g.exterior.intersection(edge.buffer(0.01))
        mouth = linemerge(mouth) if mouth.geom_type == "MultiLineString" \
            else mouth
        for ln in getattr(mouth, "geoms", [mouth]):
            if ln.geom_type != "LineString":
                continue
            a, b = ln.coords[0], ln.coords[-1]
            L = math.dist(a, b)
            if not 0.6 <= L <= 2.6:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            n = (-u[1], u[0])
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if (cen.x - m[0]) * n[0] + (cen.y - m[1]) * n[1] < 0:
                n = (-n[0], -n[1])                   # into the shaft
            t = 0.0
            for e, sg in ((b, 1), (a, -1)):          # the wall beside it
                q = (e[0] + u[0] * sg * 0.06, e[1] + u[1] * sg * 0.06)
                ray = _LS([(q[0] - n[0] * 0.02, q[1] - n[1] * 0.02),
                           (q[0] + n[0] * 0.8, q[1] + n[1] * 0.8)])
                t = max(t, core.intersection(ray).length)
            if not 0.08 <= t <= 0.75:
                continue
            g = g.difference(_LS([a, b]).buffer(t + 0.005, cap_style=2))
            ca = (a[0] + n[0] * t / 2, a[1] + n[1] * t / 2)
            cb = (b[0] + n[0] * t / 2, b[1] + n[1] * t / 2)
            doors.append({"a": [round(ca[0], 4), round(ca[1], 4)],
                          "b": [round(cb[0], 4), round(cb[1], 4)],
                          "t": round(t, 3)})
        g = max(getattr(g, "geoms", [g]), key=lambda q: q.area)
        if g.area > 0.5:
            shafts.append([p[:2] for p in
                           list(g.simplify(0.01).exterior.coords)[:-1]])
    return cores, shafts, doors


def split_wall(doc, wall_id, s0, s1) -> tuple:
    """A straight wall cut into its part from ``s0`` to ``s1`` (m from its
    start) and what is left either side — each its own wall, the same
    type, height and thickness, so the part can be changed alone (a
    curtain wall, a railing, another height…). Openings go with the part
    they stand in; a cut that would fall through a door or window moves
    to clear it. (the part's wall id, None) or (None, why)."""
    arch = doc["arch"]
    w = next((x for x in arch["walls"] if x["id"] == wall_id), None)
    if w is None:
        return None, "no such wall"
    if w.get("kind", "line") != "line":
        return None, "only straight walls can be split"
    a, b = tuple(w["a"]), tuple(w["b"])
    L = math.dist(a, b)
    s0, s1 = sorted((float(s0), float(s1)))
    ops = [o for o in arch["openings"] if o["wall"] == wall_id]
    gap = S.END_GAP + 0.01

    def clear(c, down):
        for _ in range(4):           # step past the openings in the way
            hit = next((o for o in ops
                        if o["pos"] - o["w"] / 2 - gap < c
                        < o["pos"] + o["w"] / 2 + gap), None)
            if hit is None:
                return c
            c = hit["pos"] - hit["w"] / 2 - gap if down else \
                hit["pos"] + hit["w"] / 2 + gap
        return c
    s0 = clear(s0, True)
    s1 = clear(s1, False)
    cuts = [c for c in (s0, s1) if 0.05 < c < L - 0.05]
    if not cuts:
        return None, "the part is the whole wall — edit the wall itself"
    if len(cuts) == 2 and cuts[1] - cuts[0] < 0.05:
        return None, "the part is too short"
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    edges = [0.0] + cuts + [L]

    def P(t):
        return [round(a[0] + u[0] * t, 4), round(a[1] + u[1] * t, 4)]
    pieces = list(zip(edges, edges[1:]))
    # the part asked for: the piece between s0 and s1
    want = max(range(len(pieces)), key=lambda i: min(pieces[i][1], s1)
               - max(pieces[i][0], s0))
    keep = {k: v for k, v in w.items() if k not in ("id", "name", "a", "b")}
    recs, ids = [], []
    for i, (t0, t1) in enumerate(pieces):
        if i == 0:                    # the first piece keeps the wall's id
            w["a"], w["b"] = P(t0), P(t1)
            ids.append(w["id"])
            continue
        recs.append(dict(keep, a=P(t0), b=P(t1)))
    made = M.new_walls(arch["walls"], recs)
    arch["walls"] += made
    ids += [m["id"] for m in made]
    for o in ops:                     # each opening to its piece
        for (t0, t1), wid in zip(pieces, ids):
            if t0 <= o["pos"] < t1:
                o["wall"] = wid
                o["pos"] = round(o["pos"] - t0, 4)
                break
    return ids[want], None


LIFT_WORD = re.compile(r"(^|[^A-Z])(LIFTS?|ELEVATORS?|ELEV)([^A-Z]|$)")
NOT_LIFT = re.compile(r"LOBBY|MACHINE|M/C|FRONT|PASSAGE|CORRIDOR|ROOM")


def lift_wells_by_text(pl, P, shafts, cores) -> list:
    """Lift shafts that only a word shows: the smallest space the walls,
    the columns and the lift lines close round a «LIFT» / «LIFT WELL» /
    «ELEVATOR» text (1–40 m²), where no shaft or core is yet."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union
    lay = pl["layers"]
    have = [Polygon(h).buffer(0.05) for h in shafts if len(h) >= 3] + \
        [Polygon(c).buffer(0.05) for c in cores if len(c) >= 3]
    pats = list(P.get("walls") or []) + list(P.get("columns") or []) + \
        list(P.get("lift") or [])
    out = []
    for t in pl.get("texts") or []:
        w = str(t.get("text", "")).upper()
        if not LIFT_WORD.search(w) or NOT_LIFT.search(w):
            continue
        pt = Point(t["x"], t["y"])
        if any(h.contains(pt) for h in have) or \
                any(Polygon(o).contains(pt) for o in out):
            continue
        lines = [LineString([(s[0], s[1]), (s[2], s[3])])
                 for s in pl["segs"]
                 if abs((s[0] + s[2]) / 2 - pt.x) < 8
                 and abs((s[1] + s[3]) / 2 - pt.y) < 8
                 and math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-4
                 and _match(lay[s[4]], pats)]
        for lp in pl.get("loops") or []:
            if _match(lp["layer"], pats) and len(lp["pts"]) >= 3:
                q = Polygon(lp["pts"])
                if q.is_valid and q.area < 60 and q.distance(pt) < 8:
                    lines.append(LineString(list(lp["pts"]) +
                                            [lp["pts"][0]]))
        if len(lines) < 4:
            continue
        fs = [f for f in polygonize(unary_union(lines))
              if f.contains(pt) and 1.0 <= f.area <= 40.0]
        if not fs:
            continue
        f = min(fs, key=lambda q: q.area).simplify(0.01)
        out.append([(round(x, 4), round(y, 4))
                    for x, y in list(f.exterior.coords)[:-1]])
    return out


SINGLE_TYPES = ("hinged", "main", "glass", "alu_glass", "louvre", "glazed",
                "pocket", "folding")
DOUBLE_TYPES = ("hinged", "main", "glass", "alu_glass", "louvre", "glazed",
                "pocket")


def to_curtain(doc, wall_ids) -> tuple:
    """Walls made curtain walls: their windows go (the glass is the wall),
    their doors fitted to the grid — 4'-0" to 8'-0" wide (one leaf up to
    4', two above), keeping their own door type and frame. (windows removed,
    doors fitted)."""
    arch = doc["arch"]
    ids = set(wall_ids)
    walls = {w["id"]: w for w in arch["walls"]}
    for wid in ids:
        if wid in walls:
            walls[wid]["type"] = "curtain"
    gone = [o for o in arch["openings"]
            if o["wall"] in ids and o["kind"] in ("window", "void")]
    arch["openings"] = [o for o in arch["openings"] if o not in gone]
    fitted = 0
    for o in arch["openings"]:
        if o["wall"] not in ids or o["kind"] != "door":
            continue
        w = walls[o["wall"]]
        L = W.centre(w).L
        width = min(max(float(o["w"]), SINGLE_MAX), DOUBLE_MAX)
        width = min(width, max(L - 0.2, 0.6))
        pos = min(max(float(o["pos"]), width / 2 + 0.05), L - width / 2 - 0.05)
        # the door keeps its own type and frame (the default door option
        # or what was picked for it) — only its width and leaves fitted
        o.update(w=round(width, 4), pos=round(pos, 4),
                 leaves=1 if width <= SINGLE_MAX + 0.02 else 2,
                 head="flat")
        fitted += 1
    return len(gone), fitted


PARAPET_NAMES = ("Terrace parapet", "Balcony railing", "Roof parapet")


def is_parapet(w) -> bool:
    return str(w.get("name", "")).startswith(PARAPET_NAMES)


def apply_parapet_rail(doc, kind, level=None) -> int:
    """Every parapet (terraces, the roof, balconies) of ``level`` (None =
    all) built as a railing of ``kind`` — «solid» = a masonry wall again.
    The number changed."""
    n = 0
    for w in doc["arch"]["walls"]:
        if not is_parapet(w) or (level and w["level"] != level):
            continue
        if kind in (None, "", "solid"):
            if w.pop("rail", None):
                n += 1
        elif w.get("rail") != kind:
            w["rail"] = kind
            n += 1
    return n


CW_DOOR_STYLES = (("alu_glass", "Glass door, aluminium frame (hinged)"),
                  ("glass", "Frameless glass door (patch fittings)"),
                  ("sliding", "Sliding glass door"))


def add_cw_door(doc, wall_id, style="alu_glass", width=None, pos=None,
                leaves=None) -> tuple:
    """A door in a curtain wall, set into its glazing grid: as wide as
    whole bays (one bay, or two when a bay is under 3'-0"), 4'-0" to
    8'-0" unless typed, centred on a bay (or on a mullion for two bays)
    nearest ``pos`` — the first place free of the wall's other doors.
    (record, None) or (None, why not)."""
    arch = doc["arch"]
    w = next((x for x in arch["walls"] if x["id"] == wall_id), None)
    if w is None:
        return None, "No such wall"
    if w.get("type") != "curtain":
        return None, "Not a curtain wall"
    seg = W.centre(w)
    L = float(seg.L)
    nv = max(1, int(round(L / max(float(w.get("grid", 1.5) or 1.5), 0.3))))
    bay = L / nv
    if width is None:
        nb = 1 if bay >= 0.9 else 2
        width = nb * bay
        width = min(max(width, SINGLE_MAX), DOUBLE_MAX)
    width = min(float(width), L - 0.1)
    nb = max(1, int(round(width / bay)))
    if pos is None:
        pos = L / 2
    # the centres a door of nb bays can take: bay centres (odd nb) or
    # mullions (even nb), nearest the place asked for first
    cands = [(k + nb / 2) * bay for k in range(0, nv - nb + 1)] or [L / 2]
    cands.sort(key=lambda c: abs(c - float(pos)))
    others = [(float(o["pos"]) - float(o["w"]) / 2,
               float(o["pos"]) + float(o["w"]) / 2)
              for o in arch["openings"] if o["wall"] == wall_id]
    h = float(doc["settings"].get("door_h", 2.1))
    for c in cands:
        a, b = c - width / 2, c + width / 2
        if a < 0.02 or b > L - 0.02:
            continue
        if any(not (b <= s0 - 0.02 or a >= s1 + 0.02) for s0, s1 in others):
            continue
        lv = leaves or (1 if width <= SINGLE_MAX + 0.02 or style == "sliding"
                        else 2)
        rec = {"kind": "door", "wall": wall_id, "pos": round(c, 4),
               "w": round(width, 4), "h": h, "sill": 0.0, "swing": "left",
               "face": 1, "style": style, "leaves": lv, "head": "flat",
               "frame": "aluminium"}
        why = check_record(doc, "opening", rec)
        if why:
            continue
        arch["openings"] += M.new_openings(arch["openings"], [rec])
        return arch["openings"][-1], None
    return None, "No free bay wide enough for it on this curtain wall"


def opening_types(o, st) -> None:
    """The import's door / window types and heads (part 5) on a door or
    window the plan gave: a single leaf → the single-door type, two
    leaves → the double type; the head (flat, transom, arch), the door
    raised so its leaf stays a full 2.1 m under a transom / an arch."""
    if o.get("kind") == "door":
        sty = o.get("style") or "hinged"
        two = S.leaves_of(o) == 2
        if sty in ("hinged", "double", "french"):
            want = st.get("door2_style" if two else "door_style", "hinged")
            want = {"double": "hinged", "french": "glazed"}.get(want, want)
            if want in (DOUBLE_TYPES if two else SINGLE_TYPES):
                o["style"] = want
            o["leaves"] = 2 if two else 1
        o["head"] = st.get("door_head", "flat")
    elif o.get("kind") == "window":
        o["head"] = st.get("win_head", "flat")
    if o.get("kind") in ("door", "window"):
        o["frame"] = st.get("door_frame" if o["kind"] == "door"
                            else "win_frame", "auto")
    fit_head(o)


def fit_head(o) -> None:
    """A door with a transom or an arch top: tall enough for a 2.1 m leaf
    under it."""
    if o.get("kind") != "door" or (o.get("head") or "flat") == "flat":
        return
    hs = S.head_size(o)
    o["h"] = round(max(float(o["h"]), 2.1 + hs), 3)


def door_rule(o) -> None:
    """A hinged door as wide as a room is not a door: up to 4' one leaf,
    up to 7' two leaves, wider a glass sliding door (a sliding one stays
    sliding)."""
    if o.get("kind") != "door" or o.get("style") == "sliding":
        return
    if o.get("style") in ("double", "french"):       # the older way
        o["style"] = "glazed" if o["style"] == "french" else "hinged"
        o["leaves"] = 2
    if not o.get("style"):
        o["style"] = "hinged"
    w = float(o["w"])
    if w > DOUBLE_MAX + 0.02:
        o["style"], o["leaves"] = "sliding", 1
    elif w > SINGLE_MAX + 0.02:
        o["leaves"] = 2
    elif w <= SINGLE_MAX * 0.75:
        o["leaves"] = 1
    else:
        o.setdefault("leaves", 1)


def _block_openings(pl, made, orecs, P, st):
    """(openings, blocks used): ``orecs`` with the kinds the blocks give,
    and an opening for every door / window block on a wall without one."""
    from . import detect
    used = 0
    out = [dict(o) for o in orecs]
    for ins in pl.get("inserts", ()):
        kind = detect.block_kind(ins["name"])
        if kind is None:
            if _match(ins["layer"], P["doors"]):
                kind = "door"
            elif _match(ins["layer"], P["windows"]):
                kind = "window"
        if kind is None or ins.get("depth", 0) > 2:
            continue
        bstyle = detect.block_style(ins["name"], kind) or \
            ("hinged" if kind == "door" else st.get("win_style", "sliding"))
        best = None
        for w in made:
            a, b, t = w["a"], w["b"], float(w["t"])
            L = math.dist(a, b)
            if L < 0.3:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            al = [(c[0] - a[0]) * ux + (c[1] - a[1]) * uy
                  for c in ins["corners"]]
            pe = [-(c[0] - a[0]) * uy + (c[1] - a[1]) * ux
                  for c in ins["corners"]]
            lo, hi = max(min(al), 0.0), min(max(al), L)
            if hi - lo < 0.3 or min(pe) > t / 2 + 0.02 or \
                    max(pe) < -t / 2 - 0.02:
                continue                       # the block isn't in this wall
            # a door block holds its swing: the wall is at its edge, and
            # the run along the wall is the leaf
            score = (hi - lo) - 0.1 * min(abs(min(pe)), abs(max(pe)))
            if best is None or score > best[0]:
                best = (score, w, (lo + hi) / 2, hi - lo)
        if best is None:
            continue
        _s, w, pos, width = best
        if not 0.4 <= width <= 6.0:
            continue
        used += 1
        clash = [o for o in out if o["wall"] == w["id"]
                 and abs(o["pos"] - pos) < (o["w"] + width) / 2 - 0.05]
        if clash:
            for o in clash:                  # the gap was right: its kind
                door = kind == "door"
                o["style"] = bstyle              # the block's symbol rules
                o.update(kind=kind,
                         h=float(st["door_h"] if door else st["win_h"]),
                         sill=0.0 if door else float(st["sill"]))
            continue
        door = kind == "door"
        out.append({"kind": kind, "wall": w["id"], "pos": round(pos, 4),
                    "w": round(width, 3),
                    "h": float(st["door_h"] if door else st["win_h"]),
                    "sill": 0.0 if door else float(st["sill"]),
                    "swing": "left", "face": 1, "style": bstyle})
    return out, used


def heal_walls(recs, reach=None):
    """Clean joints: every wall end that stops short of (or runs past)
    another wall is brought onto that wall's centre line — L and T joints
    then meet exactly and the plan shows them as one, mitred and joined.
    Openings measured from an end keep their place (only ends near
    another wall move, by a few centimetres)."""
    def line_hit(p, d, a, b):
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-9:
            return None
        t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den
        s = ((a[0] - p[0]) * d[1] - (a[1] - p[1]) * d[0]) / den
        return t, s
    out = [dict(r, a=list(r["a"]), b=list(r["b"])) for r in recs]
    shift = [0.0] * len(out)          # how far each wall's «a» end moved out
    for i, w in enumerate(out):
        for end in ("a", "b"):
            p = w[end]
            q = w["b" if end == "a" else "a"]
            L = math.dist(p, q)
            if L < 1e-6:
                continue
            d = ((p[0] - q[0]) / L, (p[1] - q[1]) / L)     # outwards
            lim = reach or (float(w["t"]) * 0.75 + 0.30)
            best = None
            for j, o in enumerate(out):
                if j == i:
                    continue
                r = line_hit(p, d, o["a"], o["b"])
                if r is None:
                    continue
                t, s = r
                Lo = math.dist(o["a"], o["b"])
                slack = (float(o["t"]) / 2 + 0.05) / max(Lo, 1e-6)
                if -lim <= t <= lim and -slack <= s <= 1 + slack:
                    if best is None or abs(t) < abs(best):
                        best = t
            if best is not None and abs(best) > 1e-4:
                w[end] = [round(p[0] + d[0] * best, 4),
                          round(p[1] + d[1] * best, 4)]
                if end == "a":
                    shift[i] = best
    return out, shift


def validate_openings(arch) -> list:
    """Drop the openings their wall cannot hold; the reasons."""
    info = S.levels_info(arch, M.elevations)
    walls = {w["id"]: w for w in arch["walls"]}
    ok, why = [], []
    for o in arch["openings"]:
        w = walls.get(o["wall"])
        if w is None:
            continue
        li = info[w["level"]]
        r = S.opening_room(o, w, ok, li["under"] - li["z0"] - float(
            w.get("base", 0.0)))
        if r is None:
            ok.append(o)
        else:
            why.append(f"{o['name']}: {r}")
    arch["openings"] = ok
    return why


# ---- whole-building helpers (the Structure and Roof steps) ---------------------------
def add_corner_columns(doc, lid, size=0.30) -> int:
    arch = doc["arch"]
    walls = [w for w in arch["walls"] if w["level"] == lid]
    have = {(round(e["x"], 2), round(e["y"], 2)) for e in arch["structure"]
            if e["type"] == "column" and e["level"] == lid}
    recs = []
    for p in S.wall_corners(walls):
        if (round(p[0], 2), round(p[1], 2)) in have:
            continue
        recs.append({"type": "column", "level": lid, "x": round(p[0], 4),
                     "y": round(p[1], 4), "w": size, "d": size, "angle": 0.0,
                     "shape": "rect", "anchor": "centre", "base": 0.0,
                     "height": "level", "fit": False})
    arch["structure"] += M.new_elements(arch["structure"], recs)
    return len(recs)


def add_beams_on_walls(doc, lid, w=0.20, h=0.45) -> int:
    arch = doc["arch"]
    recs = []
    for wall in arch["walls"]:
        if wall["level"] != lid or wall.get("kind", "line") != "line":
            continue
        s = W.centre(wall)
        recs.append({"type": "beam", "level": lid,
                     "a": [round(s.at(0.0)[0], 4), round(s.at(0.0)[1], 4)],
                     "b": [round(s.at(1.0)[0], 4), round(s.at(1.0)[1], 4)],
                     "w": min(w, float(wall["t"])), "h": h, "fit": True})
    recs = [r for r in recs if S.why_not(r) is None]
    arch["structure"] = [e for e in arch["structure"]
                         if not (e["type"] == "beam" and e["level"] == lid)]
    arch["structure"] += M.new_elements(arch["structure"], recs)
    return len(recs)


def add_footings(doc, pad=1.2, pad_d=None, strip=0.6, strip_d=None) -> int:
    """Pads under the lowest level's columns, strips under its walls —
    down to the foundation level (unless depths are given)."""
    arch = doc["arch"]
    d = footing_depth(doc)
    pad_d = d if pad_d is None else pad_d
    strip_d = d if strip_d is None else strip_d
    low = arch["levels"][0]["id"]
    arch["structure"] = [e for e in arch["structure"] if e["type"] != "footing"]
    recs = [{"type": "footing", "level": low, "kind": "pad", "x": e["x"],
             "y": e["y"], "w": pad, "d": pad_d, "angle": e.get("angle", 0.0)}
            for e in arch["structure"]
            if e["type"] == "column" and e["level"] == low]
    walls = [w for w in arch["walls"] if w["level"] == low]
    recs += [dict(r, type="footing", level=low, kind="strip", w=strip,
                  d=strip_d) for r in S.strips_under(walls)]
    recs = [r for r in recs if S.why_not(r) is None]
    arch["structure"] += M.new_elements(arch["structure"], recs)
    return len(recs)


def set_roof(doc, kind="hip", slope=25.0, overhang=0.6, parapet=1.0,
             t=0.20) -> bool:
    """One roof over the top level's walls (replaces the one before)."""
    arch = doc["arch"]
    arch["structure"] = [e for e in arch["structure"] if e["type"] != "roof"]
    if kind == "none":
        return True
    top = arch["levels"][-1]["id"]
    walls = [w for w in arch["walls"] if w["level"] == top]
    corners = S.roof_outline(walls, _outer_loop, kind)
    if not corners:
        return False
    rec = {"type": "roof", "level": top, "kind": kind, "corners": corners,
           "slope": slope, "overhang": overhang, "t": t, "ridge": "long",
           "parapet": parapet if kind == "flat" else 0.0, "pt": 0.15}
    if S.why_not(rec):
        return False
    arch["structure"] += M.new_elements(arch["structure"], [rec])
    return True


# ---- one element -------------------------------------------------------------------
LISTS = {"wall": "walls", "opening": "openings"}


def find_record(doc, kind, rid):
    arch = doc["arch"]
    if kind == "room":
        return room_record(doc, rid)
    if kind in ("stair", "stairrail"):
        return next((s for s in doc.get("stairs") or [] if s["id"] == rid),
                    None)
    if kind == "ramp":
        return next((r for r in doc.get("ramps") or [] if r["id"] == rid),
                    None)
    if kind == "dig":
        return next((d for d in arch.get("digs") or [] if d["id"] == rid),
                    None)
    pool = arch[LISTS.get(kind, "structure")]
    return next((r for r in pool if r["id"] == rid), None)


def delete_record(doc, kind, rid) -> None:
    arch = doc["arch"]
    if kind == "wall":
        arch["walls"] = [w for w in arch["walls"] if w["id"] != rid]
        arch["openings"] = [o for o in arch["openings"] if o["wall"] != rid]
    elif kind == "opening":
        arch["openings"] = [o for o in arch["openings"] if o["id"] != rid]
    elif kind == "stair":
        doc["stairs"] = [s for s in doc.get("stairs") or []
                         if s["id"] != rid]
    elif kind == "dig":
        arch["digs"] = [d for d in arch.get("digs") or [] if d["id"] != rid]
    elif kind == "stairrail":      # the stair stays, without its railing
        s = find_record(doc, "stair", rid)
        if s is not None:
            s["rail"] = "none"
    elif kind == "room":           # its own finish / level go: defaults
        arch["rooms"] = [r for r in arch["rooms"] if r["id"] != rid]
    elif kind == "ramp":
        r = find_record(doc, "ramp", rid)
        if r is not None:
            _ramp_uncut(doc, r["level"])
            doc["ramps"] = [x for x in doc["ramps"] if x["id"] != rid]
            _ramp_cut(doc, r["level"])
    else:
        arch["structure"] = [e for e in arch["structure"] if e["id"] != rid]


def check_record(doc, kind, rec) -> str | None:
    """Why ``rec`` (changed) can't be built — None when it can."""
    arch = doc["arch"]
    if kind == "wall":
        return W.why_not(rec)
    if kind in ("stair", "stairrail"):
        h = float(rec.get("rail_h") or 0.9)
        if not 0.3 <= h <= 2.0:
            return "a railing is 1'-0\" to 6'-6\" high"
        g = float(rec.get("rail_gap") or 0.0)
        if g and g < 0.05:
            return "balusters are at least 50 mm apart (0 = the type's)"
        return None
    if kind == "room":
        return None if 0.0 <= float(rec.get("finish", 0.0)) <= 0.3 else \
            "a floor finish is 0–300 mm thick"
    if kind == "ramp":
        return None if 0.05 <= float(rec.get("t", 0.2)) <= 1.0 else \
            "a ramp slab is 0.05–1.0 m thick"
    if kind == "opening":
        wall = find_record(doc, "wall", rec["wall"])
        info = S.levels_info(arch, M.elevations)[wall["level"]]
        return S.opening_room(rec, wall, arch["openings"],
                              info["under"] - info["z0"])
    return S.why_not(rec)


# =====================================================================================
# The model, made again — ONE Ctrl+Z
# =====================================================================================
def group_anchor(g):
    """The low corner of a group's box, where it is now (an instance's
    placement included) — compared with the one it was built at."""
    try:
        vs = list(g.mesh.vertices)
    except Exception:  # noqa: BLE001
        return None
    if not vs:
        return None
    x = min(v.position.x() for v in vs)
    y = min(v.position.y() for v in vs)
    z = min(v.position.z() for v in vs)
    xf = getattr(g, "xform", None)
    if xf is not None:
        from PySide6.QtGui import QVector3D
        q = xf.map(QVector3D(x, y, z))
        return (q.x(), q.y(), q.z())
    return (x, y, z)


def moved_openings(scene, doc, seen: dict) -> list:
    """Doors / windows moved with the host's Move tool: [(record, new
    pos)], the move taken along their wall (the hole follows). ``seen``
    keeps the moves already taken (an undo brings the moved group back:
    it is not taken twice)."""
    walls = {w["id"]: w for w in doc["arch"]["walls"]}
    out = []
    for g in list(scene.groups):
        tag = tag_of(g)
        if not tag or tag.get("type") != "opening" or "at" not in tag:
            continue
        now = group_anchor(g)
        if now is None:
            continue
        dx, dy = now[0] - tag["at"][0], now[1] - tag["at"][1]
        if math.hypot(dx, dy) < 0.005:
            continue
        key = (getattr(g, "uid", id(g)), round(now[0], 3), round(now[1], 3))
        if key in seen:
            continue
        seen[key] = True
        rec = find_record(doc, "opening", tag["id"])
        w = walls.get(rec["wall"]) if rec else None
        if w is None or w.get("kind", "line") != "line":
            continue
        seg = W.centre(w)
        ds = dx * seg.u[0] + dy * seg.u[1]
        L = math.dist(seg.p0, seg.p1) if hasattr(seg, "p1") else None
        half = float(rec["w"]) / 2
        pos = float(rec["pos"]) + ds
        if L is not None:
            pos = min(max(pos, half + 0.05), L - half - 0.05)
        out.append((rec, round(pos, 4)))
    return out


def tag_of(group):
    rec = (getattr(group, "ext", None) or {}).get(KEY)
    return rec if isinstance(rec, dict) else None


def _soften(mesh) -> None:
    """Seams between faces of one plane drawn smooth (a wall cut in panels
    by its openings reads as one face)."""
    for e in mesh.edges:
        fs = list(getattr(e, "faces", ()) or [])
        if len(fs) != 2:
            continue
        n1, n2 = fs[0].normal(), fs[1].normal()
        if n1.dotProduct(n1, n2) < 0.99995:
            continue
        p, q = fs[1].vertices[0], fs[0].vertices[0]
        if abs(n1.dotProduct(p - q, n1)) < 1e-3:
            e.soft = True


def symbol_lines(o, wall, seg):
    """A door in plan: its leaf open 90° to the inside, and its swing."""
    p0, u = seg.p0, seg.u
    n = (-u[1], u[0])
    t = float(wall["t"]) / 2
    s0, s1 = o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2

    def P(s, c):
        return (p0[0] + u[0] * s + n[0] * c, p0[1] + u[1] * s + n[1] * c)
    inside = float(o.get("face", 1) or 1)          # the side it opens to
    if o.get("style") == "sliding":         # 4' panels on two tracks
        q = float(wall["t"]) / 6
        W = s1 - s0
        npan = max(2, int(math.ceil(W / (4 * 0.3048) - 1e-6)))
        pw = W / npan
        out = [(P(s0, -q), P(s0, q)), (P(s1, -q), P(s1, q))]
        for k in range(npan):
            c = -q if k % 2 == 0 else q
            a0 = s0 + k * pw - (0.03 if k else 0.0)
            a1 = s0 + (k + 1) * pw + (0.03 if k < npan - 1 else 0.0)
            out.append((P(a0, c), P(a1, c)))
        return out
    fr, hd, lf = S.FRAME, S.FRAME_DEPTH / 2, S.LEAF
    inside = 1.0 if inside >= 0 else -1.0

    def leaf(hinge, away, r):
        # the leaf open 90° (a 40 mm wooden panel, as in 3D) and its
        # swing back to the frame
        b = hinge + away * lf
        c0, c1 = inside * hd, inside * (hd + r)
        out = [(P(hinge, c0), P(hinge, c1)), (P(hinge, c1), P(b, c1)),
               (P(b, c1), P(b, c0))]
        h = P(hinge, c0)
        a0 = math.atan2(n[1] * inside, n[0] * inside)
        a1 = math.atan2(u[1] * away, u[0] * away)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        pts = [(h[0] + r * math.cos(a0 + da * k / 12),
                h[1] + r * math.sin(a0 + da * k / 12)) for k in range(13)]
        return out + list(zip(pts, pts[1:]))
    style = o.get("style") or "hinged"
    if S.leaves_of(o) == 2 and style in S.HINGED_TYPES + ("double",
                                                          "french"):
        r = (s1 - s0 - 2 * fr) / 2               # two leaves, one each side
        return leaf(s0 + fr, 1.0, r) + leaf(s1 - fr, -1.0, r)
    W = s1 - s0 - 2 * fr
    if style == "pocket":
        # the leaf in its pocket (dashed run inside the wall) and the frame
        out = [(P(s0, -t), P(s0, t)), (P(s1, -t), P(s1, t))]
        a = s0 + fr - W + 0.10
        k = 8
        for i in range(k):
            if i % 2 == 0:
                out.append((P(a + (s0 + fr + 0.10 - a) * i / k, 0.0),
                            P(a + (s0 + fr + 0.10 - a) * (i + 1) / k, 0.0)))
        return out
    if style == "folding":
        # bi-fold leaves, folded zig-zag (as in 3D)
        k = max(2, int(math.ceil(W / 0.5)))
        k += k % 2
        lw = W / k
        ang = math.radians(60.0)
        x, out = s0 + fr, []
        for i in range(k):
            c_a = 0.0 if i % 2 == 0 else inside * lw * math.sin(ang)
            c_b = inside * lw * math.sin(ang) if i % 2 == 0 else 0.0
            xb = x + lw * math.cos(ang)
            out.append((P(x, c_a), P(xb, c_b)))
            x = xb
        # the dashed line where they close
        for i in range(0, 10, 2):
            out.append((P(s0 + fr + W * i / 10, 0.0),
                        P(s0 + fr + W * (i + 1) / 10, 0.0)))
        return out
    if style in ("rolling", "garage"):
        # closed across the opening; a rolling shutter's box line behind
        out = [(P(s0, -0.02), P(s1, -0.02)), (P(s0, 0.02), P(s1, 0.02))]
        if style == "rolling":
            c = -(t + 0.12)
            out.append((P(s0, c), P(s1, c)))
            out += [(P(s0, -t), P(s0, c)), (P(s1, -t), P(s1, c))]
        else:                                   # garage: the track inside
            for sg in (s0 + 0.05, s1 - 0.05):
                for i in range(0, 8, 2):
                    out.append((P(sg, inside * (t + 0.3 * i)),
                                P(sg, inside * (t + 0.3 * (i + 1)))))
        return out
    r = s1 - s0 - 2 * fr
    if o.get("swing", "left") == "left":
        return leaf(s0 + fr, 1.0, r)
    return leaf(s1 - fr, -1.0, r)


def _groups(arch, doc=None):
    """Every element as a tagged group on its level's layer, named by its
    component type («D-01 · Hinged door…»). Elements of the same geometry
    (the doors of one type, the walls of the typical floors…) share ONE
    definition mesh, placed by instances — components."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh

    from . import components as CP
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    info = S.levels_info(arch, M.elevations)
    walls_by = {w["id"]: w for w in arch["walls"]}
    recs = {}
    for w in arch["walls"]:
        recs[("wall", w["id"])] = w
    for o in arch["openings"]:
        recs[("opening", o["id"])] = o
    for e_ in arch["structure"]:
        recs[(e_["type"], e_["id"])] = e_
    cat = CP.catalogue(doc) if doc is not None else {}
    elems = S.build(arch, M.elevations)
    # 1: each element in its own frame, and how many share its shape
    prep, count = [], {}
    for e in elems:
        z0 = info[e["level"]]["z0"] if e["level"] in info else 0.0
        fr = CP.frame_of_element(e, arch, walls_by, z0)
        lf = CP.local_faces(e["faces"], fr)
        key = (e["kind"], CP.shape_key(lf))
        count[key] = count.get(key, 0) + 1
        prep.append((e, fr, lf, key))
    protos: dict = {}

    def mesh_of(lf):
        mesh = Mesh()
        for lp, hs, col in lf:
            face = mesh.add_face([QVector3D(*q) for q in lp],
                                 [[QVector3D(*q) for q in h] for h in hs])
            if col is not None and face is not None:
                face.attrs["color"] = col[:3]
                if len(col) > 3 and col[3] < 1.0:
                    face.attrs["opacity"] = col[3]
        _soften(mesh)
        return mesh
    out = []
    for e, fr, lf, key in prep:
        rec = recs.get((e["kind"] if e["kind"] != "opening" else "opening",
                        e["id"]))
        t, tkey = None, None
        if rec is not None:
            tk = CP.type_of(e["kind"], rec, walls_by)
            tkey = tk[1] if tk else None
            t = cat.get(tkey) if tkey else None
        name = CP.display(t) if t else e["name"]
        cls = OPENING_IFC.get(e.get("okind")) if e["kind"] == "opening" \
            else IFC.get(e["kind"])
        tag = {KEY: {"type": e["kind"], "id": e["id"], "level": e["level"],
                     **({"okind": e["okind"]} if e.get("okind") else {}),
                     **({"ctype": tkey, "mark": t["mark"]} if t else {})}}
        if t and t.get("lib"):                # an IngeTrazo library model
            try:
                from . import library as LB
                lg = LB.groups_for(t["lib"], fr, lf, name,
                                   level_layer(names[e["level"]]), tag,
                                   {"class": cls, "name": name}
                                   if cls else None)
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project._groups library")
                lg = None
            if lg:
                out += lg
                continue
        if count[key] > 1:                    # a component: shared mesh
            if key not in protos:
                protos[key] = mesh_of(lf)
            g = Group(protos[key], name=name)
            g.xform = CP.placement(fr)
            g.component = True
        else:                                 # one of a kind: a group
            g = Group(mesh_of(CP.local_faces(e["faces"],
                                             (0.0, 0.0, 0.0, 0.0))),
                      name=name)
            g.component = False
        g.material = {"color": COLOR[e["kind"]], "opacity": 1.0}
        g.layer = level_layer(names[e["level"]])
        cls = OPENING_IFC.get(e.get("okind")) if e["kind"] == "opening" \
            else IFC.get(e["kind"])
        if cls:
            g.ifc = {"class": cls, "name": name}
        g.ext = {KEY: {"type": e["kind"], "id": e["id"], "level": e["level"],
                       **({"okind": e["okind"]} if e.get("okind") else {}),
                       **({"ctype": tkey, "mark": t["mark"]}
                          if t else {})}}
        if e["kind"] == "opening":            # where it was built: a Move
            at = group_anchor(g)              # of it is followed (the hole
            if at is not None:                # in the wall goes along)
                g.ext[KEY]["at"] = [round(v, 5) for v in at]
        out.append(g)
    walls = walls_by
    # doors' leaves and swings, for the plans (hidden in 3D)
    per: dict = {}
    for o in arch["openings"]:
        w = walls.get(o["wall"])
        if o["kind"] != "door" or w is None or w.get("kind", "line") != "line":
            continue
        z = info[w["level"]]["z0"] + 0.002
        per.setdefault(w["level"], []).extend(
            ((a[0], a[1], z), (b[0], b[1], z))
            for a, b in symbol_lines(o, w, W.centre(w)))
    # the lift cabins in their shafts (plans only): the car, set in from
    # the shaft's walls, its door side open, and «LIFT»
    for e in arch["structure"]:
        if e["type"] != "core" or e["level"] not in info:
            continue
        z = info[e["level"]]["z0"] + 0.004
        ln = per.setdefault(e["level"], [])
        for h in e.get("shafts") or e.get("holes") or []:
            for a, b in lift_cabin(h):
                ln.append(((a[0], a[1], z), (b[0], b[1], z)))
    # shafts through the slabs: their outline and the X, in the plans
    for e in arch["structure"]:
        if e["type"] != "slab" or e["level"] not in info:
            continue
        z = info[e["level"]]["z0"] + 0.002
        for h in e.get("shafts") or []:
            pts = [tuple(p) for p in h]
            ln = per.setdefault(e["level"], [])
            ln.extend(((p[0], p[1], z), (q[0], q[1], z))
                      for p, q in zip(pts, pts[1:] + pts[:1]))
            if len(pts) == 4:
                for p, q in ((pts[0], pts[2]), (pts[1], pts[3])):
                    ln.append(((p[0], p[1], z), (q[0], q[1], z)))
    for lid, segs in per.items():
        mesh = Mesh()
        for a, b in segs:
            try:
                mesh.add_edge(QVector3D(*a), QVector3D(*b))
            except ValueError:
                pass
        if mesh.edges:
            g = Group(mesh, name=f"Door symbols · {names[lid]}")
            g.component = False
            g.layer = ann_layer(names[lid])     # its own plan only
            g.ext = {KEY: {"type": "symbols", "id": f"sym-{lid}",
                           "level": lid}}
            out.append(g)
    return out


def _annotations(doc, opts):
    """Each level's plan-only notes: dimension chains round its walls, the
    CAD's texts, room names with areas — (dimensions, labels)."""
    from PySide6.QtGui import QVector3D

    from core.dimension import Dimension
    from core.textlabel import TextLabel

    from . import sheets
    arch = doc["arch"]
    elev = elevations(arch)
    dims, labels = [], []
    used = set()
    for i, lv in enumerate(arch["levels"]):
        lid, z = lv["id"], elev[i] + 0.01
        layer = ann_layer(lv["name"])
        tlayer = text_layer(lv["name"])
        dlayer = dim_layer(lv["name"])
        if opts.get("dims", True):
            for ch in sheets.chains(arch, lid, z):
                pts, nrm = ch[0], ch[1]
                overall = len(ch) > 3 and ch[3]
                off = 1.2 if overall else 0.6
                pairs = [(pts[0], pts[-1])] if overall else \
                    list(zip(pts, pts[1:]))
                for a, b in pairs:
                    dims.append(Dimension(QVector3D(*a), QVector3D(*b),
                                          QVector3D(nrm[0] * off,
                                                    nrm[1] * off, 0.0),
                                          layer=dlayer))
        rooms = spaces.of_level(arch, lid)
        if opts.get("rooms", True):
            for r in rooms:
                labels.append(TextLabel(QVector3D(r["at"][0], r["at"][1], z),
                                        QVector3D(0, 0, 0),
                                        f"{r['name']}\n{area_txt(r['area'])}",
                                        layer=tlayer))
                if r["rec"] is not None:
                    used.add((lid, r["name"]))
        if opts.get("texts", True):
            for t in doc["texts"]:
                if t["level"] != lid or (lid, t["text"].split("\n")[0]
                                         .strip()) in used:
                    continue
                labels.append(TextLabel(QVector3D(t["x"], t["y"], z),
                                        QVector3D(0, 0, 0), t["text"],
                                        layer=tlayer))
    plot = arch.get("plot")
    if plot:
        from .engine import plotgeo
        layer = ann_layer(SITE)
        z = plot_top(doc) + 0.02
        pts = plot["corners"]
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            nx, ny = plotgeo.outward_normal(a, b)
            dims.append(Dimension(QVector3D(a[0], a[1], z),
                                  QVector3D(b[0], b[1], z),
                                  QVector3D(nx * 1.0, ny * 1.0, 0.0),
                                  layer=layer))
        _roles, _d, area = plotgeo.setbacks_of(plot)
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        txt = f"PLOT  {area_txt(plotgeo.area(pts))}"
        if area:
            txt += f"\nBuildable  {area_txt(plotgeo.area(area))}"
        labels.append(TextLabel(QVector3D(cx, cy, z), QVector3D(0, 0, 0), txt,
                                layer=layer))
    # the excavations / fills: name, bottom (or top) and volume
    try:
        from . import excavation as EX
        ground = plot_top(doc)
        for d in arch.get("digs") or []:
            pts = d["corners"]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            zb = EX.bottom_z(d, doc, ground)
            word = "TOP" if d.get("kind") == "fill" else "BOTTOM"
            labels.append(TextLabel(
                QVector3D(cx, cy, max(zb, ground) + 0.03), QVector3D(0, 0, 0),
                f"{d['name'].upper()}\n{word} {zb - ground:+.2f} m · "
                f"{EX.volume(d, doc, ground):,.0f} m³",
                layer=ann_layer(SITE)))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._annotations digs")
    return dims, labels


# =====================================================================================
# The plot (site) — ArchXQ's demarcation: corners, setbacks, area
# =====================================================================================
def _stair_groups(doc):
    """Each stair and its railing: two groups named by their component
    types («ST-01 · Dog-leg stair…», «RL-03 · Stainless steel…»); the
    same stair on the typical floors is ONE shared definition."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh

    from . import components as CP
    from . import stairs as ST
    arch = doc["arch"]
    elev = elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    cat = CP.catalogue(doc)
    recs = {s_["id"]: s_ for s_ in doc.get("stairs") or []}
    stt = doc.get("settings") or {}
    prep, count = [], {}
    for name, sid, lid, parts, layer, rails in ST.groups(
            doc, z_of, lambda lid: level_layer(names[lid])):
        z = z_of[lid]
        for kind, ps in (("stair", parts), ("stairrail", rails)):
            if not ps:
                continue
            faces = []
            for fs, colour in ps:
                for f in fs:
                    d_ = dict(f) if isinstance(f, dict) else {"loop": f}
                    d_.setdefault("holes", [])
                    if colour is not None:
                        d_["color"] = colour
                    faces.append(d_)
            lf = CP.local_faces(faces, (0.0, 0.0, z, 0.0))
            key = (kind, CP.shape_key(lf))
            count[key] = count.get(key, 0) + 1
            prep.append((kind, name, sid, lid, layer, z, lf, key))
    protos, out = {}, []
    for kind, name, sid, lid, layer, z, lf, key in prep:
        if key not in protos:
            mesh = Mesh()
            for lp, hs, col in lf:
                face = mesh.add_face([QVector3D(*q) for q in lp],
                                     [[QVector3D(*q) for q in h]
                                      for h in hs])
                if face is not None and col is not None:
                    face.attrs["color"] = tuple(col[:3])
                    if len(col) > 3 and col[3] < 1.0:
                        face.attrs["opacity"] = col[3]
            _soften(mesh)
            protos[key] = mesh
        rec = dict(recs.get(sid) or {}, **ST.eff(recs.get(sid) or {}, stt))
        tk = CP.type_of(kind, rec)
        t = cat.get(tk[1]) if tk else None
        nm = CP.display(t) if t else (name if kind == "stair"
                                      else f"{name} railing")
        if t and t.get("lib"):                # an IngeTrazo library model
            try:
                from . import library as LB
                lg = LB.groups_for(
                    t["lib"], (0.0, 0.0, z, 0.0), lf, f"{nm} · {names[lid]}",
                    layer, {KEY: {"type": kind, "id": sid, "level": lid,
                                  "ctype": tk[1], "mark": t["mark"]}})
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project._stair_groups library")
                lg = None
            if lg:
                out += lg
                continue
        g = Group(protos[key], name=f"{nm} · {names[lid]}")
        g.xform = CP.placement((0.0, 0.0, z, 0.0))
        g.component = count[key] > 1
        g.material = {"color": COLOR["stair"], "opacity": 1.0}
        g.layer = layer
        g.ifc = {"class": "IfcStair" if kind == "stair" else "IfcRailing",
                 "name": nm}
        g.ext = {KEY: {"type": kind, "id": sid, "level": lid,
                       **({"ctype": tk[1], "mark": t["mark"]} if t else {})}}
        out.append(g)
    return out


def _mesh_of(faces):
    from PySide6.QtGui import QVector3D

    from core.mesh import Mesh
    mesh = Mesh()
    for f in faces:
        face = mesh.add_face([QVector3D(*q) for q in f["loop"]],
                             [[QVector3D(*q) for q in hh]
                              for hh in f.get("holes") or []])
        if face is not None and f.get("color") is not None:
            face.attrs["color"] = tuple(f["color"][:3])
    return mesh


def cad_floor(marks):
    """A level's own floor level from its CAD notes: ("rel", metres) — the
    most common «LEV. +4'-0"» — else ("abs", number) — the most common
    «LEV. 102.00» — else None."""
    from collections import Counter
    rel = Counter(round(m["v"], 4) for m in marks or ()
                  if m.get("v") is not None)
    if rel:
        v, _n = max(rel.items(), key=lambda kv: (kv[1], -abs(kv[0])))
        return "rel", v
    ab = Counter(round(m["a"], 4) for m in marks or ()
                 if m.get("a") is not None)
    if ab:
        v, _n = max(ab.items(), key=lambda kv: (kv[1], -kv[0]))
        return "abs", v
    return None


def levels_from_cad(doc) -> list:
    """The levels' floor levels as their CAD plans note them («LEV. +4'-0"»
    on a floor sets that floor at +4'-0"; floors noted only in absolute
    levels — «LEV. 102.00» — keep their distances to each other): the
    ground floor's level and the storey heights between noted floors are
    set so. Returns [(level name, new elevation)]."""
    arch = doc["arch"]
    levels = arch["levels"]
    if not levels:
        return []
    k_abs = 0.3048 if any(
        (h or {}).get("unit_k") in (0.0254, 0.3048)
        for h in doc["imports"].values()) else 1.0
    elev = elevations(arch)
    want = {}
    abs_ = {}
    for i, lv in enumerate(levels):
        f = cad_floor(doc["marks"].get(lv["id"]))
        if f and f[0] == "rel":
            want[i] = f[1]
        elif f:
            abs_[i] = f[1]
    if abs_:                    # absolute-only floors: from one anchor
        if want:
            # an anchor noted both ways is rare: the absolute floors keep
            # their spacing above the lowest one, set at its present level
            pass
        i0 = min(abs_)
        for i, a in abs_.items():
            want.setdefault(i, round(elev[i0] + (a - abs_[i0]) * k_abs, 4))
    if not want:
        return []
    g = next(i for i, r in enumerate(levels) if r["kind"] == "ground")
    proj = arch.setdefault("project", {})
    changed = []
    if g in want:
        proj["ground_level"] = round(want[g], 4)
    else:
        # the ground floor unnoted: it stays, the others move about it
        pass
    for i in range(len(levels)):
        if i == g or i not in want:
            continue
        el = elevations(arch)
        if i > g:
            j = i - 1                   # the storey below takes the change
            h = levels[j]["height"] + (want[i] - el[i])
        else:
            j = i                       # a basement: its own storey height
            h = levels[j]["height"] + (el[i] - want[i])
        if 1.5 <= h <= 15.0:
            levels[j]["height"] = round(h, 4)
    el = elevations(arch)
    for i, lv in enumerate(levels):
        if abs(el[i] - elev[i]) > 1e-4:
            changed.append((lv["name"], el[i]))
    return changed


def open_offset(doc, lid) -> float:
    """The level's open floor (its main slab) against its floor level:
    where the drive, the parking, the ramps and the landscape stand."""
    for e in doc["arch"]["structure"]:
        if e["type"] == "slab" and e["level"] == lid and not e.get("zone"):
            return float(e.get("offset", 0.0) or 0.0)
    return 0.0


def note_levels(doc, lid) -> list:
    """The level's notes as [(x, y, metres on the relative datum)]: the
    relative ones as they are, the absolute ones (RL) through the datum a
    pair of notes side by side gives («LEV. 75.50» beside «LEV.+3'-6"»)."""
    marks = doc["marks"].get(lid) or []
    k_abs = 0.3048 if any((h or {}).get("unit_k") in (0.0254, 0.3048)
                          for h in doc["imports"].values()) else 1.0
    rel = [(m["x"], m["y"], m["v"]) for m in marks if m.get("v") is not None]
    ab = [(m["x"], m["y"], m["a"]) for m in marks if m.get("a") is not None]
    offs = []
    for x, y, a in ab:
        near = [v for (x2, y2, v) in rel if math.hypot(x2 - x, y2 - y) < 1.5]
        if near:
            offs.append(near[0] - a * k_abs)
    out = list(rel)
    if offs:
        offs.sort()
        off = offs[len(offs) // 2]
        out += [(x, y, round(a * k_abs + off, 4)) for x, y, a in ab]
    return out


def slab_zones(doc, lid) -> list:
    """One floor at several levels, as its CAD notes it: each room takes
    the level noted in it, the open floor round the rooms (a drive, a
    lobby) the level most noted there — the level's slab cut in pieces at
    their own heights (an offset from the floor's level). Returns
    [(zone, offset m)] of the pieces not at the floor's level."""
    from collections import Counter

    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    arch = doc["arch"]
    notes = note_levels(doc, lid)
    if len(notes) < 2:
        return []
    f = cad_floor(doc["marks"].get(lid))
    base = f[1] if f and f[0] == "rel" else Counter(
        round(v, 3) for _x, _y, v in notes).most_common(1)[0][0]
    slabs = [e for e in arch["structure"]
             if e["type"] == "slab" and e["level"] == lid
             and not e.get("zone")]
    if not slabs:
        return []
    rooms = [r["poly"] for r in spaces.of_level(arch, lid)
             if r.get("poly") is not None and r["area"] >= 1.0]
    floor = unary_union([Polygon(sl["corners"]).buffer(0) for sl in slabs])
    rooms_u = unary_union(rooms) if rooms else Polygon()

    def mode(vals):
        c = Counter(round(v, 3) for v in vals)
        return max(c.items(), key=lambda kv: (kv[1], -abs(kv[0] - base)))[0]
    room_lv = []
    for r in rooms:
        vs = [v for x, y, v in notes if r.contains(Point(x, y))]
        room_lv.append(mode(vs) if vs else base)
    open_vs = [v for x, y, v in notes if floor.contains(Point(x, y))
               and not rooms_u.contains(Point(x, y))]
    open_lv = mode(open_vs) if open_vs else base
    out = []
    t = float(slabs[0]["t"])
    holes_all = [Polygon(h).buffer(0) for sl in slabs
                 for h in sl.get("holes") or [] if len(h) >= 3]
    # the open floor at its level: the slabs themselves, lowered / raised
    if abs(open_lv - base) > 0.005:
        for sl in slabs:
            sl["offset"] = round(open_lv - base, 4)
        out.append(("open floor", round(open_lv - base, 4)))
    # each room whose level is not the open floor's: its own piece
    new = []
    for r, lv in zip(rooms, room_lv):
        if abs(lv - open_lv) <= 0.005:
            continue
        part = r.intersection(floor)
        for g in getattr(part, "geoms", [part]):
            if g.geom_type != "Polygon" or g.area < 1.0:
                continue
            hs = [list(h.exterior.coords)[:-1] for h in holes_all
                  if h.within(g.buffer(0.01))]
            # thick enough to fill the step down to the open floor's slab
            step = max(0.0, lv - open_lv)
            new.append({"type": "slab", "level": lid, "zone": True,
                        "corners": [[round(x, 4), round(y, 4)] for x, y in
                                    list(g.simplify(0.005).exterior.coords)[:-1]],
                        "holes": [[[round(x, 4), round(y, 4)] for x, y in h]
                                  for h in hs],
                        "t": round(t + step, 4),
                        "offset": 0.0 if abs(lv - base) < 0.005
                        else round(lv - base, 4)})
    new = [r_ for r_ in new if S.why_not(r_) is None]
    if new:
        arch["structure"] += M.new_elements(arch["structure"], new)
        levels = Counter(r_["offset"] for r_ in new)
        out += [(f"{n} room(s)", o) for o, n in levels.items()]
    return out


def level_marks(doc) -> dict:
    """{level id: [(x, y, text)]} — the CAD's level notes, else the
    level's own floor level beside its biggest room."""
    from .host import len_txt
    arch = doc["arch"]
    elev = elevations(arch)
    out = {}
    for i, lv in enumerate(arch["levels"]):
        lid = lv["id"]
        cad = doc["marks"].get(lid) or []
        if cad:
            out[lid] = [(m["x"], m["y"], m["text"]) for m in cad]
            continue
        if not any(w["level"] == lid for w in arch["walls"]):
            continue
        rooms = spaces.of_level(arch, lid)
        if rooms:
            r = max(rooms, key=lambda r: r["area"])
            x, y = r["at"][0], r["at"][1] - 0.9
        else:
            sl = [st for st in arch["structure"]
                  if st["type"] == "slab" and st["level"] == lid]
            if not sl:
                continue
            cs = sl[0]["corners"]
            x = sum(p[0] for p in cs) / len(cs)
            y = sum(p[1] for p in cs) / len(cs)
        e = elev[i]
        sign = "±" if abs(e) < 0.005 else ("+" if e > 0 else "-")
        out[lid] = [(x, y, f"FFL {sign}{len_txt(abs(e))}")]
    return out



# =====================================================================================
# Rooms: floor finish each, and a floor sunk / raised (its slab part)
# =====================================================================================
def room_key(lid, room) -> str:
    """A room found's id: its record's, else its level and label point."""
    rec = room.get("rec")
    if rec:
        return rec["id"]
    return f"{lid}@{room['at'][0]:.3f},{room['at'][1]:.3f}"


def room_record(doc, rid):
    """The record of the room ``rid`` — made (with its found name) when
    the room had none yet. None when no room is there."""
    from shapely.geometry import Point
    arch = doc["arch"]
    rec = next((r for r in arch["rooms"] if r["id"] == rid), None)
    if rec is not None:
        return rec
    if "@" not in str(rid):
        return None
    lid, xy = str(rid).split("@", 1)
    try:
        x, y = (float(v) for v in xy.split(","))
    except ValueError:
        return None
    room = next((r for r in spaces.of_level(arch, lid)
                 if r["poly"].buffer(0.01).contains(Point(x, y))), None)
    if room is None:
        return None
    if room.get("rec"):
        return room["rec"]
    rec = {"id": rid, "level": lid, "x": round(x, 4), "y": round(y, 4),
           "name": room["name"]}
    arch["rooms"].append(rec)
    return rec


def room_finish(doc, rec) -> float:
    """The floor finish of a room (m): its own, else the default."""
    if rec and rec.get("finish") is not None:
        return float(rec["finish"])
    return float(doc["settings"].get("finish_t", 0.0508))


def _carrier_t(doc, lid) -> float:
    """Thickness of the slab that carries the floor of ``lid``."""
    arch = doc["arch"]
    want = lid
    if slab_on_top(doc):
        want = _ramp_level_below(arch, lid)
    for s in arch["structure"]:
        if s["type"] == "slab" and s["level"] == want and not (
                s.get("zone") or s.get("user")):
            return float(s["t"])
    return float(doc["settings"].get("slab_t", 0.15))


def sync_room_floors(doc) -> int:
    """Each room with its floor sunk / raised (``fz``) gets its slab part
    at that level (its outline the room's, made again as its walls move);
    the parts of rooms set back to 0 go. The parts made."""
    arch = doc["arch"]
    keep = [s for s in arch["structure"]
            if not (s["type"] == "slab" and s.get("room"))]
    new = []
    by_level = {}
    for rec in arch["rooms"]:
        fz = float(rec.get("fz", 0.0) or 0.0)
        if abs(fz) < 0.001:
            continue
        rooms = by_level.setdefault(rec["level"],
                                    spaces.of_level(arch, rec["level"]))
        room = next((r for r in rooms if r.get("rec") is not None
                     and r["rec"]["id"] == rec["id"]), None)
        if room is None:
            continue
        poly = room["poly"].simplify(0.005)
        new.append({"type": "slab", "level": rec["level"], "user": True,
                    "room": rec["id"],
                    "corners": [[round(x, 4), round(y, 4)] for x, y in
                                list(poly.exterior.coords)[:-1]],
                    "holes": [], "t": _carrier_t(doc, rec["level"]),
                    "offset": round(fz, 4)})
    new = [r for r in new if S.why_not(r) is None]
    arch["structure"] = keep
    if new:
        arch["structure"] += M.new_elements(arch["structure"], new)
    return len(new)


def sunk_area(doc, lid, pts, offset) -> bool:
    """An area of the floor of ``lid`` (a polygon drawn in the model)
    sunk (−) or raised (+) by ``offset`` m: a slab part of its own."""
    from shapely.geometry import Polygon
    poly = Polygon(pts).buffer(0)
    if poly.is_empty or poly.area < 0.05:
        return False
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    rec = {"type": "slab", "level": lid, "user": True,
           "corners": [[round(x, 4), round(y, 4)] for x, y in
                       list(poly.exterior.coords)[:-1]],
           "holes": [], "t": _carrier_t(doc, lid),
           "offset": round(float(offset), 4)}
    if S.why_not(rec) is not None:
        return False
    doc["arch"]["structure"] += M.new_elements(doc["arch"]["structure"],
                                               [rec])
    return True


def floor_offset_at(doc, lid, pt) -> float:
    """The floor's level at ``pt`` against its floor level: a part sunk /
    raised by hand there, a CAD level zone, else the open floor."""
    from shapely.geometry import Point, Polygon
    P = Point(pt)
    parts = S.floor_parts(doc["arch"], lid)
    for flag in ("user", "zone"):
        for s in parts:
            if s.get(flag) and Polygon(s["corners"]).buffer(0).contains(P):
                return float(s.get("offset", 0.0))
    return open_offset(doc, lid)


def _finish_groups(doc):
    """Every room's floor finish: a layer of its own thickness on its
    floor (over the slab, its level sunk / raised with it), named by its
    type («FF-01 · Floor finish 2"») — the same room on the typical floors
    one shared component — ([groups], [labels])."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh

    from . import components as CP
    st = doc["settings"]
    if not st.get("finish_on", True):
        return [], []
    arch = doc["arch"]
    elev = elevations(arch)
    cat = CP.catalogue(doc)
    prep, count = [], {}
    for i, lv in enumerate(arch["levels"]):
        lid = lv["id"]
        if not any(w["level"] == lid for w in arch["walls"]):
            continue
        for room in spaces.of_level(arch, lid):
            if room["area"] < 1.0:          # a duct / shaft: no finish
                continue
            f = room_finish(doc, room.get("rec"))
            if f < 0.001:
                continue
            z = elev[i] + floor_offset_at(doc, lid, room["at"])
            poly = room["poly"]
            piece = {"outer": S._ccw([tuple(q) for q in
                                      list(poly.exterior.coords)[:-1]]),
                     "holes": [list(reversed(S._ccw(
                         [tuple(q) for q in list(h.coords)[:-1]])))
                         for h in poly.interiors]}
            faces = W.solid(piece, 0.0, f)
            if not faces:
                continue
            lf = CP.local_faces(faces, (0.0, 0.0, 0.0, 0.0))
            key = CP.shape_key(lf)
            count[key] = count.get(key, 0) + 1
            prep.append((lv, lid, room, f, z, lf, key))
    protos, out = {}, []
    for lv, lid, room, f, z, lf, key in prep:
        if key not in protos:
            mesh = Mesh()
            for lp, hs, _c in lf:
                mesh.add_face([QVector3D(*q) for q in lp],
                              [[QVector3D(*q) for q in h] for h in hs])
            protos[key] = mesh
        tk = CP.type_of("room", {"finish_t": f})
        t = cat.get(tk[1])
        g = Group(protos[key], name=(f"{t['mark']} · " if t else "")
                  + f"Floor finish {room['name']} · {lv['name']}")
        g.xform = CP.placement((0.0, 0.0, z, 0.0))
        g.component = count[key] > 1
        g.material = {"color": COLOR["room"], "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ext = {KEY: {"type": "room", "id": room_key(lid, room),
                       "level": lid,
                       **({"ctype": tk[1], "mark": t["mark"]} if t else {})}}
        out.append(g)
    return out, []

def _parking_groups(doc):
    """Parking (paint + cars), each ramp (a sloped RC slab) and their plan
    symbols, with the level marks — (groups, labels)."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh
    from core.textlabel import TextLabel

    from . import parking as PK
    arch = doc["arch"]
    st = doc["settings"]
    elev = elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    out, labels = [], []
    plan = {}                                     # level → 2D lines
    for lid, pk in doc["parking"].items():
        if lid not in z_of:
            continue
        z = z_of[lid] + open_offset(doc, lid)
        faces = []
        # the bay lines painted as one clean, joined shape
        faces += PK.paint_union(pk.get("bays") or [], z + 0.004)
        if faces:
            g = Group(_mesh_of(faces), name=f"Parking · {names[lid]}")
            g.component = False
            g.material = {"color": (0.95, 0.95, 0.9), "opacity": 1.0}
            g.layer = level_layer(names[lid])
            g.ext = {KEY: {"type": "parking", "id": f"park-{lid}",
                           "level": lid}}
            out.append(g)
        lines = [(tuple(a), tuple(b)) for a, b in pk.get("bays") or []]
        plan.setdefault(lid, []).extend(lines)
        # the bays numbered, and how many cars the floor parks
        stalls = pk.get("stalls")
        if stalls is None or (stalls and "ang" not in stalls[0]):
            stalls = PK.stalls_of(pk.get("bays") or [], pk.get("cars") or [])
        # a car in every bay: IngeTrazo's library models, as instances
        if stalls and st.get("cars_lib", True):
            from . import cars as CARS
            try:
                out += CARS.groups(
                    stalls, z, st.get("car_model", "suv"),
                    level_layer(names[lid]),
                    lambda k, _l=lid: {KEY: {"type": "car",
                                             "id": f"car-{_l}-{k + 1}",
                                             "level": _l}},
                    lambda k: f"Car P{k + 1}")
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project.cars")
        if stalls and st.get("park_nums", True):
            for k, sl in enumerate(stalls):
                labels.append(TextLabel(
                    QVector3D(sl["c"][0], sl["c"][1], z + 0.02),
                    QVector3D(0, 0, 0), f"P{k + 1}",
                    layer=text_layer(names[lid])))
            xs = [sl["c"][0] for sl in stalls]
            ys = [sl["c"][1] for sl in stalls]
            labels.append(TextLabel(
                QVector3D((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                          z + 0.02), QVector3D(0, 0, 0),
                f"CAR PARKING: {len(stalls)} CARS",
                layer=text_layer(names[lid])))
    # landscape areas, in green
    from . import landscape as LS
    g_i = next((i for i, lv in enumerate(arch["levels"])
                if lv["kind"] == "ground"), None)
    for lid, areas_ in doc.get("landscape", {}).items():
        if lid not in z_of or not areas_:
            continue
        # on the floor's finish (over its slab, never hidden under it)
        z = z_of[lid] + open_offset(doc, lid) + 0.012
        faces = [f for a in areas_ for f in LS.faces(a, z)]
        g = Group(_mesh_of(faces), name=f"Landscape · {names[lid]}")
        g.component = False
        g.material = {"color": LS.GREEN[:3], "opacity": 1.0}
        g.layer = level_layer(names[lid])
        g.ext = {KEY: {"type": "landscape", "id": f"green-{lid}",
                       "level": lid}}
        out.append(g)
    for r in doc["ramps"]:
        lid = r["level"]
        if lid not in z_of:
            continue
        z = z_of[lid] + open_offset(doc, lid)
        tt = float(r.get("t", st.get("ramp_t", 0.2)))
        faces = PK.ramp_faces(r, z, tt) + PK.pad_faces(r, z, tt)
        g = Group(_mesh_of(faces), name=f"{r['name']} · {names[lid]}")
        g.component = False
        g.material = {"color": (0.64, 0.64, 0.62), "opacity": 1.0}
        g.layer = level_layer(names[lid])
        g.ifc = {"class": "IfcRamp", "name": r["name"]}
        g.ext = {KEY: {"type": "ramp", "id": r["id"], "level": lid}}
        out.append(g)
        lines, (x, y, word) = PK.ramp_plan(r)
        plan.setdefault(lid, []).extend(lines + PK.pad_lines(r))
        rise = float(r["rise"])
        from .host import len_txt
        labels.append(TextLabel(QVector3D(x, y, z + 0.02), QVector3D(0, 0, 0),
                                f"RAMP {word} {len_txt(abs(rise))}",
                                layer=text_layer(names[lid])))
    if st.get("marks_on", True):
        for lid, ms in level_marks(doc).items():
            z = z_of[lid]
            for x, y, txt in ms:
                lines, (tx, ty) = PK.mark_lines(x, y)
                plan.setdefault(lid, []).extend(lines)
                labels.append(TextLabel(QVector3D(tx, ty, z + 0.02),
                                        QVector3D(0, 0, 0), txt,
                                        layer=text_layer(names[lid])))
    for lid, lines in plan.items():
        z = z_of[lid] + open_offset(doc, lid) + 0.006
        mesh = Mesh()
        for a, b in lines:
            try:
                mesh.add_edge(QVector3D(a[0], a[1], z), QVector3D(b[0], b[1], z))
            except ValueError:
                pass
        if mesh.edges:
            g = Group(mesh, name=f"Parking, ramps, levels · {names[lid]}")
            g.component = False
            g.layer = ann_layer(names[lid])          # its own plan only
            g.ext = {KEY: {"type": "symbols", "id": f"pk-{lid}",
                           "level": lid}}
            out.append(g)
    return out, labels


def _site_groups(doc):
    """Boundary wall, pillars, gates (their own layer) and the gates'
    swings (the site plan's notes)."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh
    arch = doc["arch"]
    plot = arch.get("plot")
    if not plot or not doc["site"]["wall"]:
        return []
    from .engine import plotgeo
    corners = plotgeo.clean(plot["corners"])
    z0 = plot_top(doc)
    parts, sym = SITE_.build(corners, doc["site"], z0)
    low = arch["levels"][0]["id"]
    out = []
    for k, (name, kind, faces, color) in enumerate(parts):
        mesh = Mesh()
        for f in faces:
            if isinstance(f, dict):
                mesh.add_face([QVector3D(*q) for q in f["loop"]],
                              [[QVector3D(*q) for q in hh] for hh in f["holes"]])
            else:
                mesh.add_face([QVector3D(*q) for q in f])
        _soften(mesh)
        g = Group(mesh, name=name)
        g.component = False
        g.material = {"color": color, "opacity": 1.0}
        g.layer = BOUNDARY_LAYER
        g.ifc = {"class": "IfcWall" if kind == "boundary" else
                 "IfcColumn" if kind == "pillar" else "IfcDoor",
                 "name": name}
        g.ext = {KEY: {"type": "site", "id": f"site-{k}", "level": low}}
        out.append(g)
    if sym:
        mesh = Mesh()
        for a, b in sym:
            try:
                mesh.add_edge(QVector3D(a[0], a[1], z0 + 0.02),
                              QVector3D(b[0], b[1], z0 + 0.02))
            except ValueError:
                pass
        g = Group(mesh, name="Gate swings")
        g.component = False
        g.layer = ann_layer(SITE)
        g.ext = {KEY: {"type": "symbols", "id": "gates", "level": low}}
        out.append(g)
    return out


def _grid_groups(doc):
    """The column grid on every plan: axes and bubbles (lines) on each
    level's notes layer — their figures are labels (sheets) and drawn to
    scale in the model (labels.py)."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh
    grid = doc["grid"]
    arch = doc["arch"]
    if not grid["on"]:
        return [], []
    if grid["source"] == "cad" and grid.get("lines"):
        segs, tags = SITE_.cad_grid_lines(grid["lines"])
    else:
        xs, ys = SITE_.axes(arch, grid)
        if not xs and not ys:
            return [], []
        box = _grid_box(arch, xs, ys)
        segs, tags = SITE_.grid_lines(xs, ys, box, float(grid["ext"]))
    from core.textlabel import TextLabel
    elev = elevations(arch)
    groups, labels = [], []
    for i, lv in enumerate(arch["levels"]):
        if not any(w["level"] == lv["id"] for w in arch["walls"]):
            continue
        z = elev[i] + 0.015
        mesh = Mesh()
        for a, b in segs:
            try:
                mesh.add_edge(QVector3D(a[0], a[1], z), QVector3D(b[0], b[1], z))
            except ValueError:
                pass
        g = Group(mesh, name=f"Grid · {lv['name']}")
        g.component = False
        g.layer = ann_layer(lv["name"])
        g.ext = {KEY: {"type": "symbols", "id": f"grid-{lv['id']}",
                       "level": lv["id"]}}
        groups.append(g)
        labels += [TextLabel(QVector3D(x, y, z), QVector3D(0, 0, 0), t,
                             layer=text_layer(lv["name"]))
                   for x, y, t in tags]
    return groups, labels


def _grid_box(arch, xs, ys):
    pts = [p for w in arch["walls"] for p in (w.get("a"), w.get("b"))
           if isinstance(p, list)]
    px = [p[0] for p in pts] + list(xs)
    py = [p[1] for p in pts] + list(ys)
    if not px:
        return (0.0, 0.0, 1.0, 1.0)
    return (min(px), min(py), max(px), max(py))


def grid_tags(doc):
    """[(x, y, label)] of the grid's bubbles (for the scaled labels)."""
    grid = doc["grid"]
    if not grid["on"]:
        return []
    if grid["source"] == "cad" and grid.get("lines"):
        return SITE_.cad_grid_lines(grid["lines"])[1]
    xs, ys = SITE_.axes(doc["arch"], grid)
    if not xs and not ys:
        return []
    return SITE_.grid_lines(xs, ys, _grid_box(doc["arch"], xs, ys),
                            float(grid["ext"]))[1]


def add_roof_level(doc, parapet_h=1.0, parapet_t=0.15, slab_t=0.15,
                   height=3.0) -> str | None:
    """A «Roof» level over the top floor: a terrace slab round the outside
    of the top floor's walls, and a parapet wall along its edge (its outer
    face flush with the slab's). Made again when there is one already.
    None, or why not."""
    from shapely.geometry import Polygon
    arch = doc["arch"]
    old = next((lv for lv in arch["levels"] if lv["name"] == "Roof"), None)
    if old is not None:                        # the roof level made before
        lid = old["id"]
        ids = {w["id"] for w in arch["walls"] if w["level"] == lid}
        arch["walls"] = [w for w in arch["walls"] if w["level"] != lid]
        arch["openings"] = [o for o in arch["openings"] if o["wall"] not in ids]
        arch["structure"] = [e for e in arch["structure"] if e["level"] != lid]
        arch["rooms"] = [r for r in arch["rooms"] if r["level"] != lid]
        arch["levels"] = [lv for lv in arch["levels"] if lv["id"] != lid]
    tops = [lv for lv in arch["levels"]
            if any(w["level"] == lv["id"] for w in arch["walls"])]
    if not tops:
        return "No floor with walls yet"
    top = tops[-1]
    outline = S.inside_walls([w for w in arch["walls"]
                              if w["level"] == top["id"]], _outer_loop)
    if not outline:
        return "The top floor's walls enclose nothing"
    before = {x["id"] for x in arch["levels"]}
    arch["levels"] = M.add_floor(arch["levels"], height=height)
    new = next(x for x in arch["levels"] if x["id"] not in before)
    new["name"] = "Roof"
    arch["levels"] = M.fix_levels(arch["levels"])
    lid = new["id"]
    rec = {"type": "slab", "level": lid, "corners": outline, "holes": [],
           "t": slab_t, "offset": 0.0}
    if S.why_not(rec) is None:
        arch["structure"] += M.new_elements(arch["structure"], [rec])
    if parapet_h > 0:
        ring = Polygon(outline).buffer(-parapet_t / 2, join_style=2)
        pts = list(ring.exterior.coords)[:-1] if not ring.is_empty else []
        recs = [{"kind": "line", "a": [round(a[0], 4), round(a[1], 4)],
                 "b": [round(b[0], 4), round(b[1], 4)], "t": parapet_t,
                 "align": "centre", "side": 1, "height": parapet_h,
                 "base": 0.0, "level": lid}
                for a, b in zip(pts, pts[1:] + pts[:1]) if math.dist(a, b) > 0.05]
        made_ = M.new_walls(arch["walls"], recs)
        rk = doc["settings"].get("parapet_rail", "solid")
        for k_, w_ in enumerate(made_, 1):
            w_["name"] = f"Roof parapet {k_}"
            if rk and rk != "solid":
                w_["rail"] = rk
        arch["walls"] += made_
    arch["rooms"] = M._rooms(arch["rooms"] + [{
        "id": "", "level": lid, "name": "Roof terrace",
        "x": sum(p[0] for p in outline) / len(outline),
        "y": sum(p[1] for p in outline) / len(outline)}],
        {lv["id"] for lv in arch["levels"]})
    return None


def plot_top(doc) -> float:
    """The plot's ground: under the ground floor by the plinth."""
    arch = doc["arch"]
    elev = elevations(arch)
    g = next(i for i, lv in enumerate(arch["levels"]) if lv["kind"] == "ground")
    return elev[g] - float(doc["settings"].get("plinth", 0.15))


def set_plot(doc, corners, front=None, dist=None) -> str | None:
    """The plot from its corners (m); None, or why not."""
    from .engine import plotgeo
    pts = plotgeo.clean([[float(p[0]), float(p[1])] for p in corners])
    why = plotgeo.why_not(pts)
    if why:
        return why
    n = len(pts)
    old = doc["arch"].get("plot") or {}
    fr = front if front is not None else [False] * n
    if len(fr) != n:
        fr = [False] * n
    if not any(fr):                       # the side nearest the road: the
        fr = [False] * n                  # longest one facing «south»
        best = max(range(n), key=lambda i: (
            -plotgeo.outward_normal(pts[i], pts[(i + 1) % n])[1],
            math.dist(pts[i], pts[(i + 1) % n])))
        fr[best] = True
    raw = {"corners": pts, "uid": old.get("uid") or "plot",
           "thickness": 0.10, "heights": [0.0] * n, "closing": n - 1,
           "breaks": [], "sb_front": fr, "sb_custom": [None] * n,
           "sb_role": [None] * n,
           "sb_dist": dist or old.get("sb_dist") or
           {"front": 3.0, "back": 1.5, "sides": 1.0}}
    arch = dict(doc["arch"], plot=raw)
    doc["arch"]["plot"] = M.load(arch)["plot"]
    return None


def plot_from_loop(drawing_placed, P) -> list | None:
    """The largest closed outline on the plot layers (model m)."""
    cands = [lp["pts"] for lp in drawing_placed["loops"]
             if _match(lp["layer"], P["plot"]) and _poly_area(lp["pts"]) > 20]
    return max(cands, key=_poly_area) if cands else None


def _dig_groups(doc):
    """The excavations and fills (ArchXQ's terrain): each its own group on
    the terrain layer, named with its depth and volume."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh

    from . import excavation as EX
    arch = doc["arch"]
    digs = arch.get("digs") or []
    if not digs:
        return []
    ground = plot_top(doc)
    low = arch["levels"][0]["id"]
    out = []
    for d in digs:
        try:
            fs = EX.faces(d, doc, ground)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project._dig_groups")
            continue
        if not fs:
            continue
        mesh = Mesh()
        for f, col in fs:
            face = mesh.add_face([QVector3D(*q) for q in f["loop"]],
                                 [[QVector3D(*q) for q in h]
                                  for h in f["holes"]])
            if face is not None:
                face.attrs["color"] = tuple(col[:3])
        _soften(mesh)
        g = Group(mesh, name=f"{d['name']} · "
                  f"{EX.volume(d, doc, ground):,.0f} m³")
        g.component = False
        g.material = {"color": EX.EARTH[:3], "opacity": 1.0}
        g.layer = TERRAIN_LAYER
        g.ifc = {"class": "IfcEarthworksCut" if d.get("kind") != "fill"
                 else "IfcEarthworksFill", "name": d["name"]}
        g.ext = {KEY: {"type": "dig", "id": d["id"], "level": low}}
        out.append(g)
    return out


def _plot_groups(doc):
    """The plot: a ground plate (the building's footprint cut out of it)
    on the plot layer; the setback line, dashed, for the site plan."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh

    from .engine import plotgeo
    arch = doc["arch"]
    plot = arch.get("plot")
    if not plot:
        return []
    top = plot_top(doc)
    pts = plotgeo.clean(plot["corners"])
    holes = []
    low = arch["levels"][0]["id"]
    for lid in (low, next(lv["id"] for lv in arch["levels"]
                          if lv["kind"] == "ground")):
        walls = [w for w in arch["walls"] if w["level"] == lid]
        if walls:
            pieces = [pc for pcs in W.plan(walls).values() for pc in pcs]
            fp = _outer_loop(pieces)
            if fp and plotgeo.within(fp, pts, margin=0.0):
                holes = [list(reversed(S._ccw([tuple(p) for p in fp])))]
            break
    out = []
    mesh = Mesh()
    # the excavations open the ground: the plate is the plot less the
    # building and the cuts (merged where they overlap)
    from . import excavation as EX
    plates = [(S._ccw([tuple(p) for p in pts]), holes)]
    cuts = EX.ground_holes(doc)
    if cuts:
        try:
            from shapely.geometry import Polygon as _Pg
            from shapely.ops import unary_union as _uu
            g = _Pg(pts, [list(h) for h in holes]).buffer(0).difference(
                _uu([_Pg(c).buffer(0) for c in cuts]))
            plates = []
            for q in getattr(g, "geoms", [g]):
                if q.geom_type != "Polygon" or q.area < 0.01:
                    continue
                plates.append((S._ccw([tuple(c) for c in
                                       list(q.exterior.coords)[:-1]]),
                               [list(reversed(S._ccw(
                                   [tuple(c) for c in list(h.coords)[:-1]])))
                                for h in q.interiors]))
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project._plot_groups cuts")
    fs_ = []
    for outer, hs in plates:
        fs_ += W.solid({"outer": outer, "holes": hs}, top - 0.10, top)
    for f in fs_:
        if isinstance(f, dict):
            mesh.add_face([QVector3D(*q) for q in f["loop"]],
                          [[QVector3D(*q) for q in h] for h in f["holes"]])
        else:
            mesh.add_face([QVector3D(*q) for q in f])
    _soften(mesh)
    g = Group(mesh, name="Plot")
    g.component = False
    g.material = {"color": (0.62, 0.70, 0.52), "opacity": 1.0}
    g.layer = TERRAIN_LAYER
    g.ifc = {"class": "IfcSite", "name": "Plot"}
    g.ext = {KEY: {"type": "plot", "id": "plot", "level": low}}
    out.append(g)
    _roles, _d, area = plotgeo.setbacks_of(plot)
    if area:
        mesh = Mesh()
        z = top + 0.02
        n = len(area)
        for i in range(n):
            a, b = area[i], area[(i + 1) % n]
            L = math.dist(a, b)
            k = 0.0
            while k < L:                       # dashes 0.6 on, 0.3 off
                e = min(k + 0.6, L)
                pa = (a[0] + (b[0] - a[0]) * k / L, a[1] + (b[1] - a[1]) * k / L)
                pb = (a[0] + (b[0] - a[0]) * e / L, a[1] + (b[1] - a[1]) * e / L)
                try:
                    mesh.add_edge(QVector3D(pa[0], pa[1], z),
                                  QVector3D(pb[0], pb[1], z))
                except ValueError:
                    pass
                k += 0.9
        g = Group(mesh, name="Setback line")
        g.component = False
        g.layer = ann_layer(SITE)
        g.ext = {KEY: {"type": "symbols", "id": "setbacks", "level": low}}
        out.append(g)
    return out


# =====================================================================================
# The foundation plan
# =====================================================================================
def footing_depth(doc) -> float:
    """From the footings' top (under the lowest slab) down to the
    foundation level."""
    arch = doc["arch"]
    info = S.levels_info(arch, M.elevations)
    li = info[arch["levels"][0]["id"]]
    top = li["z0"] - li["slab"]
    return round(max(top - float(doc["settings"].get("found_level", -1.5)),
                     0.2), 3)


def import_foundation(doc: dict, path: str, how: dict) -> dict:
    """Footings from the foundation plan: closed outlines and circles on
    the footing layers become pads, pairs of lines strips — all down to
    the foundation level. Replaces the footings before."""
    st = doc["settings"]
    arch = doc["arch"]
    drawing = cadread.crop(cadread.read(path, how.get("unit")),
                           how.get("region"))
    base = cadread.base_point(drawing, how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    pl = cadread.place(drawing, base, (how.get("ix", 0.0), how.get("iy", 0.0)),
                       how.get("rot", 0.0))
    P, found = layer_patterns(drawing, how, st)
    lay = pl["layers"]
    low = arch["levels"][0]["id"]
    d = footing_depth(doc)
    recs = []
    for lp in pl["loops"]:
        if not _match(lp["layer"], P["footings"]):
            continue
        pts = lp["pts"]
        if len(pts) == 4:
            a, b, c = pts[0], pts[1], pts[2]
            w = max(math.dist(a, b), math.dist(b, c))
            if 0.3 <= w <= 8.0:
                recs.append({"type": "footing", "level": low, "kind": "pad",
                             "x": round(sum(p[0] for p in pts) / 4, 4),
                             "y": round(sum(p[1] for p in pts) / 4, 4),
                             "w": round(w, 3), "d": d,
                             "angle": round(math.degrees(math.atan2(
                                 b[1] - a[1], b[0] - a[0])), 3)})
    for ci in pl["circles"]:
        if _match(ci["layer"], P["footings"]) and 0.15 <= ci["r"] <= 4:
            recs.append({"type": "footing", "level": low, "kind": "pad",
                         "x": round(ci["c"][0], 4), "y": round(ci["c"][1], 4),
                         "w": round(2 * ci["r"], 3), "d": d, "angle": 0.0})
    segs = [s for s in pl["segs"] if _match(lay[s[4]], P["footings"])]
    if segs:
        found_strips, _o = walldetect.walls_from(segs, 0.25, 2.5)
        for a, b, t in found_strips:
            recs.append({"type": "footing", "level": low, "kind": "strip",
                         "a": [round(a[0], 4), round(a[1], 4)],
                         "b": [round(b[0], 4), round(b[1], 4)],
                         "w": round(t, 3), "d": d})
    recs = [r for r in recs if S.why_not(r) is None]
    if recs:
        arch["structure"] = [e for e in arch["structure"]
                             if e["type"] != "footing"]
        arch["structure"] += M.new_elements(arch["structure"], recs)
        try:
            mt = os.path.getmtime(path)
        except OSError:
            mt = 0.0
        doc["imports"][FOUNDATION] = dict(how, file=str(path), mtime=mt)
    return {"pads": sum(1 for r in recs if r["kind"] == "pad"),
            "strips": sum(1 for r in recs if r["kind"] == "strip"),
            "roles": found, "depth": d}


def _views_command(viewport, arch, opts):
    """The plan / elevation / section scenes, the clean 3D scene and the
    cut planes, made again with the model (the sheets left as they are)."""
    from PySide6.QtGui import QVector3D

    from . import sheets
    vopts = {"paper": "A3", "scale": "auto", "cut": float(opts.get("cut",
                                                               1.2)),
             "elev": "yes", "sect": "yes", "dims": "no", "rooms": "no"}
    try:
        planes, views, _sh = sheets.make(arch, M.elevations, vopts)
    except Exception:  # noqa: BLE001 — never block the model for its views
        from .host import log_error
        log_error("project._views_command")
        return None
    if not views:
        return None
    els = S.build(arch, M.elevations)
    pts = [q for e in els for f in e["faces"]
           for q in (f["loop"] if isinstance(f, dict) else f)]
    bbox = None
    if pts:
        bbox = (QVector3D(min(p[0] for p in pts), min(p[1] for p in pts),
                          min(p[2] for p in pts)),
                QVector3D(max(p[0] for p in pts), max(p[1] for p in pts),
                          max(p[2] for p in pts)))
    cmd, _m, _r = sheets.swap_command(
        viewport, planes, views, None, bbox,
        ann_layers=[ann_layer(lv["name"]) for lv in arch["levels"]]
        + [text_layer(lv["name"]) for lv in arch["levels"]]
        + [dim_layer(lv["name"]) for lv in arch["levels"]]
        + [ann_layer(SITE)])
    return cmd


def store_only(viewport, doc) -> None:
    """Store ``doc`` without making the model again (a setting the model
    does not show, as the north): one Ctrl+Z."""
    from core.history import Command
    new = copy.deepcopy(doc)

    class _Store(Command):
        def do(self, sc):
            self.old = copy.deepcopy(sc.plugin_data.get(KEY))
            sc.plugin_data[KEY] = copy.deepcopy(new)
            sc.version += 1

        def undo(self, sc):
            sc.plugin_data[KEY] = copy.deepcopy(self.old)
            sc.version += 1

    viewport.history.execute(_Store())
    viewport.update()


def commit(viewport, doc, opts=None) -> None:
    """Store ``doc`` and make the model again from it: groups, door
    symbols, annotations, layers — ONE undo step (with the sheets' scenes
    and planes left as they are)."""
    from core.history import Command
    from core.layers import Layer

    opts = opts or {}
    arch = doc["arch"]
    arch["levels"] = M.fix_levels(arch["levels"])
    apply_slab_pos(doc)
    try:
        sync_room_floors(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.sync_room_floors")
    new_groups = _groups(arch, doc)
    try:
        new_groups += _stair_groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._stair_groups")
    try:
        new_groups += _plot_groups(doc)
        new_groups += _site_groups(doc)
        new_groups += _dig_groups(doc)
    except Exception:  # noqa: BLE001 — the plot never blocks the building
        from .host import log_error
        log_error("project._plot_groups")
    try:
        new_dims, new_labels = _annotations(doc, opts)
    except Exception:  # noqa: BLE001 — the notes never block the model
        from .host import log_error
        log_error("project._annotations")
        new_dims, new_labels = [], []
    try:
        pg, pl_ = _parking_groups(doc)
        new_groups += pg
        new_labels += pl_
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._parking_groups")
    try:
        fg, fl = _finish_groups(doc)
        new_groups += fg
        new_labels += fl
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._finish_groups")
    try:
        gg, gl = _grid_groups(doc)
        new_groups += gg
        new_labels += gl
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._grid_groups")
    _apply_materials(new_groups, doc.get("materials") or {})
    data = copy.deepcopy(doc)
    want = [level_layer(lv["name"]) for lv in arch["levels"]] + \
        [ann_layer(lv["name"]) for lv in arch["levels"]] + \
        [text_layer(lv["name"]) for lv in arch["levels"]] + \
        [dim_layer(lv["name"]) for lv in arch["levels"]] + \
        ([TERRAIN_LAYER, ann_layer(SITE)] if arch.get("plot") else []) + \
        ([BOUNDARY_LAYER] if arch.get("plot") and doc["site"]["wall"] else [])

    class _Rebuild(Command):
        def __init__(self):
            self.before = None

        def _mine(self, sc):
            return ([g for g in sc.groups if tag_of(g)],
                    [d for d in sc.dimensions
                     if str(d.layer or "").startswith(LAYER_PREFIX)],
                    [t for t in sc.text_labels
                     if str(t.layer or "").startswith(LAYER_PREFIX)])

        def do(self, sc):
            if self.before is None:
                g, d, t = self._mine(sc)
                self.before = {"groups": g, "dims": d, "texts": t,
                               "at": sc.groups.index(g[0]) if g else
                               len(sc.groups),
                               "layers": list(sc.layers),
                               "data": copy.deepcopy(sc.plugin_data.get(KEY))}
                have = {L.name for L in sc.layers}
                self.added = []
                for name in want:
                    if name not in have:
                        L = Layer(name)
                        if name == SYMBOL_LAYER or is_ann_layer(name):
                            L.visible = False       # 2D: the plans show them
                        self.added.append(L)
            b = self.before
            sc.groups[:] = [g for g in sc.groups if g not in b["groups"]]
            at = min(b["at"], len(sc.groups))
            sc.groups[at:at] = new_groups
            sc.dimensions[:] = [d for d in sc.dimensions
                                if d not in b["dims"]] + new_dims
            sc.text_labels[:] = [t for t in sc.text_labels
                                 if t not in b["texts"]] + new_labels
            for L in self.added:
                if L not in sc.layers:
                    sc.layers.append(L)
            # this project's layers no level uses any more, left empty
            used = {getattr(g, "layer", None) for g in sc.groups}
            sc.layers[:] = [L for L in sc.layers
                            if not (L.name.startswith(LAYER_PREFIX)
                                    and L.name not in want
                                    and L.name not in used)]
            sc.plugin_data[KEY] = copy.deepcopy(data)
            for d in new_dims:
                try:
                    d.bind(sc)
                except Exception:  # noqa: BLE001
                    pass
            sc.selection.clear()
            sc.version += 1

        def undo(self, sc):
            b = self.before
            sc.groups[:] = [g for g in sc.groups if g not in new_groups]
            at = min(b["at"], len(sc.groups))
            sc.groups[at:at] = b["groups"]
            sc.dimensions[:] = [d for d in sc.dimensions
                                if d not in new_dims] + b["dims"]
            sc.text_labels[:] = [t for t in sc.text_labels
                                 if t not in new_labels] + b["texts"]
            sc.layers[:] = b["layers"]
            if b["data"] is None:
                sc.plugin_data.pop(KEY, None)
            else:
                sc.plugin_data[KEY] = copy.deepcopy(b["data"])
            sc.selection.clear()
            sc.version += 1

    from core.history import CompoundCommand
    cmds = [_Rebuild()]
    views = _views_command(viewport, arch, opts)
    if views is not None:
        cmds.append(views)
    viewport.history.execute(CompoundCommand(cmds))
    err = getattr(viewport.history, "last_error", None)
    if err:
        raise RuntimeError(err)
    from .host import refresh_host_layers
    refresh_host_layers(viewport)
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    viewport.update()


# =====================================================================================
# Slabs for every floor, and floors laid over each other
# =====================================================================================
def auto_slabs(doc, t=0.15, replace=False) -> int:
    """A floor slab on every level that has walls: its outline the outer
    contour of the level's walls. ``replace``: the slabs there before go
    (their holes are kept when the new outline still holds them)."""
    from shapely.geometry import Polygon
    arch = doc["arch"]
    made = 0
    for lv in arch["levels"]:
        walls = [w for w in arch["walls"] if w["level"] == lv["id"]]
        if not walls:
            continue
        have = [e for e in arch["structure"]
                if e["type"] == "slab" and e["level"] == lv["id"]]
        if have and not replace:
            continue
        plans = W.plan([w for w in walls if W.why_not(w) is None])
        outlines = [[[round(p[0], 4), round(p[1], 4)] for p in S._ccw(o)]
                    for o in _outer_loops([pc for ps in plans.values()
                                           for pc in ps])]
        if not outlines:
            continue
        arch["structure"] = [e for e in arch["structure"] if e not in have]
        for outline in outlines:      # each building block its slab
            poly = Polygon(outline)
            holes = [h for s in have for h in s.get("holes") or []
                     if poly.contains(Polygon(h))]
            shafts = [h for s in have for h in s.get("shafts") or []
                      if poly.contains(Polygon(h))]
            rec = {"type": "slab", "level": lv["id"], "corners": outline,
                   "holes": holes, "shafts": shafts, "t": t, "offset": 0.0}
            if S.why_not(rec) is None:
                arch["structure"] += M.new_elements(arch["structure"], [rec])
                made += 1
    return made


def _shift(rec, dx, dy):
    for k in ("a", "b", "m", "c"):
        p = rec.get(k)
        if isinstance(p, list) and len(p) == 2:
            rec[k] = [round(p[0] + dx, 4), round(p[1] + dy, 4)]
    if "x" in rec and "y" in rec:
        rec["x"] = round(float(rec["x"]) + dx, 4)
        rec["y"] = round(float(rec["y"]) + dy, 4)
    for k in ("corners",):
        if isinstance(rec.get(k), list):
            rec[k] = [[round(p[0] + dx, 4), round(p[1] + dy, 4)]
                      for p in rec[k]]
    if isinstance(rec.get("holes"), list):
        rec["holes"] = [[[round(p[0] + dx, 4), round(p[1] + dy, 4)]
                         for p in h] for h in rec["holes"]]


_VEC_KEYS = ("d", "u", "n", "dir")          # directions: turned, not moved
_ANG_KEYS = ("ang", "angle", "rot")         # angles in degrees
_KEEP_KEYS = ("level", "id", "name", "text", "layer", "kind", "type")


def _xf(x, pt, vec, da):
    """``x`` with every point mapped by ``pt``, direction by ``vec`` and
    angle turned by ``da``° — walked through dicts and lists."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if k in _KEEP_KEYS:
                out[k] = v
            elif k in _ANG_KEYS and isinstance(v, (int, float)):
                out[k] = round((float(v) + da) % 360.0, 4) if da else v
            elif k in _VEC_KEYS and _is_pt(v):
                out[k] = vec(v)
            elif k in ("x", "y"):
                out[k] = v                   # done with its pair below
            else:
                out[k] = _xf(v, pt, vec, da)
        if isinstance(x.get("x"), (int, float)) and \
                isinstance(x.get("y"), (int, float)):
            out["x"], out["y"] = pt([x["x"], x["y"]])
        return out
    if isinstance(x, list):
        if _is_pt(x):
            return pt(x)
        return [_xf(v, pt, vec, da) for v in x]
    return x


def _is_pt(v):
    return isinstance(v, list) and len(v) == 2 and \
        all(isinstance(q, (int, float)) and not isinstance(q, bool)
            for q in v)


def transform_level(doc, lid, pt, vec, da) -> None:
    """Everything on level ``lid`` mapped: walls (their doors and windows
    go with them), structure, rooms, texts, stairs, parking, ramps, level
    marks and landscape."""
    arch = doc["arch"]
    for key in ("walls", "rooms"):
        arch[key] = [_xf(e, pt, vec, da) if e.get("level") == lid else e
                     for e in arch[key]]
    arch["structure"] = [_xf(e, pt, vec, da)
                         if e.get("level") == lid and e["type"] != "footing"
                         else e for e in arch["structure"]]
    doc["texts"] = [_xf(t, pt, vec, da) if t.get("level") == lid else t
                    for t in doc["texts"]]
    doc["stairs"] = [_xf(st, pt, vec, da) if st.get("level") == lid else st
                     for st in doc.get("stairs") or []]
    doc["ramps"] = [_xf(r, pt, vec, da) if r.get("level") == lid else r
                    for r in doc.get("ramps") or []]
    for key in ("stair_cad", "parking", "marks", "landscape"):
        m = doc.get(key)
        if isinstance(m, dict) and lid in m:
            m[lid] = _xf(m[lid], pt, vec, da)


def move_level(doc, lid, dx, dy) -> None:
    """Everything on level ``lid`` moved by (dx, dy) m — and its import
    remembers it, so importing the plan again lands in the same place."""
    transform_level(doc, lid,
                    lambda p: [round(p[0] + dx, 4), round(p[1] + dy, 4)],
                    lambda v: list(v), 0.0)
    how = doc["imports"].get(lid)
    if how:
        how["ix"] = round(float(how.get("ix", 0.0)) + dx, 4)
        how["iy"] = round(float(how.get("iy", 0.0)) + dy, 4)


def level_centre(doc, lid):
    """The middle of the level's walls (their bounding box), or None."""
    pts = [p for w in doc["arch"]["walls"] if w["level"] == lid
           for p in (w.get("a"), w.get("b")) if _is_pt(p)]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def rotate_level(doc, lid, deg, centre=None) -> bool:
    """Everything on level ``lid`` turned ``deg``° (anticlockwise) about
    ``centre`` (default: the middle of its walls) — and its import
    remembers it (insert point and rotation), so importing the plan again
    lands the same way. False when the level has no walls."""
    c = centre or level_centre(doc, lid)
    if c is None or not deg:
        return False
    r = math.radians(deg)
    cs, sn = math.cos(r), math.sin(r)

    def pt(p):
        x, y = p[0] - c[0], p[1] - c[1]
        return [round(c[0] + x * cs - y * sn, 4),
                round(c[1] + x * sn + y * cs, 4)]

    def vec(v):
        return [round(v[0] * cs - v[1] * sn, 6),
                round(v[0] * sn + v[1] * cs, 6)]
    transform_level(doc, lid, pt, vec, deg)
    how = doc["imports"].get(lid)
    if how:                 # model = R(rot)·(p − base)·k + insert
        ix, iy = pt([float(how.get("ix", 0.0)), float(how.get("iy", 0.0))])
        how["ix"], how["iy"] = ix, iy
        how["rot"] = round((float(how.get("rot", 0.0)) + deg) % 360.0, 4)
    return True


def overlap_offset(doc, lid, ref, method="best"):
    """(dx, dy, how good) that lays level ``lid`` over level ``ref``:
    «best» — the move that puts the most wall corners on the other floor's
    corners; «ll» — lower-left corners of the outlines together; «centre»
    — the outlines' centres together."""
    arch = doc["arch"]
    mw = [w for w in arch["walls"] if w["level"] == lid]
    rw = [w for w in arch["walls"] if w["level"] == ref]
    if not mw or not rw:
        return None
    if method in ("ll", "centre"):
        def box(walls):
            pts = [p for w in walls for p in (w.get("a"), w.get("b"))
                   if isinstance(p, list)]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            return min(xs), min(ys), max(xs), max(ys)
        a, b = box(mw), box(rw)
        if method == "ll":
            return b[0] - a[0], b[1] - a[1], None
        return ((b[0] + b[2]) / 2 - (a[0] + a[2]) / 2,
                (b[1] + b[3]) / 2 - (a[1] + a[3]) / 2, None)
    mc = [tuple(p) for p in S.wall_corners(mw)][:150]
    rc = [tuple(p) for p in S.wall_corners(rw)][:150]
    if not mc or not rc:
        return None
    tol = 0.06
    grid = {}
    for p in rc:
        grid.setdefault((round(p[0] / tol), round(p[1] / tol)), []).append(p)

    def score(dx, dy):
        n = 0
        for x, y in mc:
            qx, qy = x + dx, y + dy
            k = (round(qx / tol), round(qy / tol))
            if any(math.dist((qx, qy), p) <= tol
                   for i in (-1, 0, 1) for j in (-1, 0, 1)
                   for p in grid.get((k[0] + i, k[1] + j), ())):
                n += 1
        return n
    best = (score(0.0, 0.0), 0.0, 0.0)
    seen = set()
    # the moves tried: a corner of this floor onto any of the other's —
    # this floor's outermost corners are enough to find it
    cand = sorted(mc, key=lambda p: p[0] + p[1])[:12] + \
        sorted(mc, key=lambda p: -p[0] - p[1])[:12] + \
        sorted(mc, key=lambda p: p[0] - p[1])[:8] + \
        sorted(mc, key=lambda p: p[1] - p[0])[:8]
    for x, y in dict.fromkeys(cand):
        for u, v in rc:
            dx, dy = round(u - x, 3), round(v - y, 3)
            key = (round(dx / tol), round(dy / tol))
            if key in seen:
                continue
            seen.add(key)
            s = score(dx, dy)
            if s > best[0] or (s == best[0] and math.hypot(dx, dy)
                               < math.hypot(best[1], best[2])):
                best = (s, dx, dy)
    return best[1], best[2], best[0] / max(len(mc), 1)


def stair_trace(doc, lid):
    """The stairs drawn on the level's CAD plan (its stair layers' tread
    lines), traced: [[flight…] per stair] — see stairs.trace."""
    from . import stairs as ST
    how = doc["imports"].get(lid)
    if not how or not how.get("file"):
        return []
    st = doc["settings"]
    try:
        drawing = cadread.crop(cadread.read(how["file"], how.get("unit")),
                               how.get("region"))
    except Exception:  # noqa: BLE001 — the file moved: no tracing
        return []
    base = cadread.base_point(drawing, how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    pl = cadread.place(drawing, base, (how.get("ix", 0.0), how.get("iy", 0.0)),
                       how.get("rot", 0.0))
    P, _f = layer_patterns(drawing, how, st)
    lay = pl["layers"]
    segs = [((s[0], s[1]), (s[2], s[3])) for s in pl["segs"]
            if _match(lay[s[4]], P["stairs"])]
    words = [(t["x"], t["y"], t["text"]) for t in pl["texts"]]
    return ST.trace(segs, words) if segs else []


# ---- materials (finishes) ----------------------------------------------------------------
MATERIAL_KINDS = [("wall", "Walls"), ("slab", "Slabs"), ("column", "Columns"),
                  ("core", "Lift core walls"),
                  ("beam", "Beams"), ("footing", "Footings"), ("roof", "Roof"),
                  ("stair", "Stairs"), ("opening", "Door / window frames"),
                  ("plot", "Plot (ground)"), ("site", "Boundary wall"),
                  ("ramp", "Car ramps"), ("parking", "Parking (paint, cars)"),
                  ("room", "Floor finishes (rooms)")]
DEFAULT_MATERIAL = {"wall": "Plaster, white", "slab": "RCC slab",
                    "column": "RCC", "core": "RCC", "beam": "RCC", "footing": "PCC / RCC",
                    "roof": "Roof finish", "stair": "RCC, terrazzo",
                    "opening": "Aluminium frame", "plot": "Lawn",
                    "site": "Brick, plastered", "ramp": "RCC, broom finish",
                    "parking": "Road paint", "room": "Floor tiles"}


def material_of(doc, kind):
    m = (doc.get("materials") or {}).get(kind) or {}
    col = m.get("color") or list(COLOR.get(kind, (0.75, 0.75, 0.75)))[:3]
    if kind == "plot" and not m.get("color"):
        col = [0.62, 0.70, 0.52]
    if kind == "site" and not m.get("color"):
        col = list(SITE_.WALL_COLOR)
    return {"name": m.get("name") or DEFAULT_MATERIAL.get(kind, kind),
            "color": col}


def _apply_materials(groups, mats):
    """The finishes chosen in the panel: each element's colour and its
    material's name (kept on the group for schedules / IFC)."""
    if not mats:
        return
    for g in groups:
        t = (tag_of(g) or {}).get("type")
        m = mats.get(t) or (mats.get("column") if t == "core" else None)
        if not m:
            continue
        mat = dict(g.material or {})
        if m.get("color"):
            mat["color"] = tuple(m["color"][:3])
        if m.get("name"):
            mat["name"] = m["name"]
        g.material = mat
        if t == "wall" or t == "stair":          # painted faces follow too
            for f in g.mesh.faces:
                c = f.attrs.get("color")
                if c is None or t == "wall":
                    f.attrs["color"] = tuple(m["color"][:3])


def update_from_cad(doc) -> list:
    """Every level read again from its CAD plan with the settings it was
    imported with (the file may have changed): [(level name, report)]."""
    out = []
    for lv in list(doc["arch"]["levels"]):
        how = doc["imports"].get(lv["id"])
        if not how or not how.get("file"):
            continue
        try:
            rep = import_level(doc, lv["id"], how["file"], dict(how))
        except Exception as e:  # noqa: BLE001
            rep = {"error": str(e)}
        out.append((lv["name"], rep))
    how = doc["imports"].get(FOUNDATION)
    if how and how.get("file"):
        try:
            out.append(("Foundation", import_foundation(doc, how["file"],
                                                        dict(how))))
        except Exception as e:  # noqa: BLE001
            out.append(("Foundation", {"error": str(e)}))
    from . import stairs as ST           # the stairs, as the plans draw them
    try:
        ST.auto(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.update_from_cad stairs")
    return out


def cad_changed(doc) -> list:
    """The levels whose CAD file is newer than their import."""
    out = []
    names = {lv["id"]: lv["name"] for lv in doc["arch"]["levels"]}
    names[FOUNDATION] = "Foundation"
    for lid, how in doc["imports"].items():
        f = how.get("file")
        if not f or lid not in names:
            continue
        try:
            if os.path.getmtime(f) > float(how.get("mtime", 0)) + 1:
                out.append(names[lid])
        except OSError:
            pass
    return out
