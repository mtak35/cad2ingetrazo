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
import uuid
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
    "bikes": "*BIKE*, *MOTORCYCLE*, *SCOOTER*",
    "rails": "*RAIL*, *GRILL*",
    "ramps": "*RAMP*",
    "steps": "*STEP*",
    "lines": "LINE, LINES",
    "low_wall_h": 0.6096, "low_plat_h": 0.4572, "bridge_openings": True,
    "round_lib": True, "round_lib_key": "online:katorlegaz-019",
    "cars_lib": True, "cad_lines": True, "levels_cad": True, "car_model": "suv", "park_nums": True, "marks_on": True, "ramp_t": 0.20,
    "win_style": "sliding", "door_style": "hinged", "door2_style": "hinged",
    "door_head": "flat", "win_head": "flat", "arch_style": "pointed",
    "hl_arch_style": "pointed",
    "void_arch": False,
    "door_frame": "auto", "win_frame": "auto", "floor_h": 3.048,
    "tmin": 0.08, "tmax": 0.40,
    "door_h": 2.10, "win_h": 1.20, "sill": 0.90,
    "slab_on": True, "slab_t": 0.1016, "slab_pos": "bottom", "ground_slab": False,
    "stair_rail": "ss_bars", "stair_rail_h": 0.9144, "stair_rail_sides": "inner",
    "stair_rail_off": 0.05, "stair_rail_gap": 0.0, "stair_rail_ext": 0.0,
    "parapet_rail": "solid",
    "finish_on": True, "finish_t": 0.0508,
    "beam_h": 0.6096, "beam_on": "columns", "beam_span": 10.0, "beam_w": 0.2032,   # 8" x 24" beams
    "ann_rooms": True, "ann_texts": True,
    "auto_layers": True,
    "found_level": -1.50,          # m, the footings' bottom (±0.00 = floor)
    "plinth": 0.15,                # m, ground floor above the plot's ground
    "ground_ffl": 0.6096,          # m, ground F.F.L. above N.G.L. (0 = CAD)
    "rail_needs_text": True,       # railings only where the CAD writes them
    "stair_max_flight": 14,        # risers in one flight at most
    "stair_shape": "u",            # a standard stair: a U-turn
    "walls_at_columns": True,      # walls broken at the column faces
    "rcc_fills": True,             # hatched / filled walls: RCC structure
    "steps_v": 2,                  # floor steps 6" / 12" (from 3.25)
    "gffl_v": 2,                   # 3.14: +2'-0" the default
    "stair_headroom_cut": True, "stair_head": 2.1336,   # 7'-0" headroom
    "stair_well": "railing", "corner_windows": True, "slab_to_columns": True,
    "level_groups": False, "shoring_on": "plot",          # each level one group in 3D
    "found_type": "isolated_strip", "raft_t": 0.6096, "raft_off": 0.6096,
    "stair_type": "monolithic", "stair_waist": 0.1524,   # 6" waist slab
    "stair_riser": 0.1778, "stair_going": 0.2794,       # 7" riser, 11" tread
    "bike_model": "lib", "bike_lib": None,              # motorbikes: library
    "slab_extend_cad": True, "rail_h": 1.0668,          # 3'-6" railings
    "thresholds": True, "finish_to_edge": True,
    "curtains": True, "curtain_color": "cream", "curtain_len": "floor",
    "terrace_rails": True, "plaster_t": 0.0127, "terrace_mat": "",
    "terrace_rail_kind": "railing", "terrace_curb_h": 0.3048, "roof_auto": False, "roof_parapet": True, "auto_rail_sig": "", "ext_finish_drop": 0.3048, "gate_lib": True, "platform": True, "entry_steps": True, "hi_poly": False, "parapet_style": "coping", "riser_max": 0.1524, "tread_ext": 0.3048, "auto_openings": True, "cad_furniture": False, "fitout_on": True, "bath_fixtures": True, "top_stair": False, "sheet_units": "drawing",
    "sheet_pen_cut": 0.5, "sheet_pen_profile": 0.35,
    "sheet_pen_edge": 0.18, "sheet_pen_dim": 0.18,
    "section_box": None,
    "basement_rcc": True, "retain_t": 0.3048,           # 12" RCC retaining
    "shoring": False, "shoring_type": "piles", "shoring_d": 0.6096,
    "shoring_embed": 3.048,                              # 10'-0" below
    "stair_nosing": 0.025, "stair_tread": 0.05, "stair_fin": "marble", "stair_fin_t": 0.02, "stair_fin_rt": 0.015, "stair_nose_type": "square", "stair_fin_follow": True,
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

def _safe_add(mesh, loop, holes=None):
    """``mesh.add_face`` that survives a bad hole (two openings touching,
    one closed to nothing, one out past its face): the holes cleaned —
    merged, kept inside — and, failing that, the face without them."""
    try:
        return mesh.add_face(loop, holes) if holes else mesh.add_face(loop)
    except Exception:  # noqa: BLE001
        pass
    if not holes:
        return None
    try:
        from PySide6.QtGui import QVector3D
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        pts = [(q.x(), q.y(), q.z()) for q in loop]
        # the face's plane: drop the axis its normal runs along
        nx = ny = nz = 0.0
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        k = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
        nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        if abs((nx, ny, nz)[k]) / nl < 0.999:
            raise ValueError("not on an axis plane")
        ax = [i for i in range(3) if i != k]

        def two(q):
            return (q[ax[0]], q[ax[1]])
        outer = Polygon([two(q) for q in pts]).buffer(0)
        hs = []
        for h in holes:
            hp = [(q.x(), q.y(), q.z()) for q in h]
            if len(hp) < 3:
                continue
            g = Polygon([two(q) for q in hp]).buffer(0)
            if not g.is_empty and g.area > 1e-6:
                hs.append(g)
        u = unary_union(hs).intersection(outer.buffer(-1e-4)) if hs else None
        good = []
        if u is not None and not u.is_empty:
            ref = pts[0][k]
            for g in getattr(u, "geoms", [u]):
                if g.geom_type != "Polygon" or g.area < 1e-6:
                    continue
                ring = []
                for c in list(g.exterior.coords)[:-1]:
                    v = [0.0, 0.0, 0.0]
                    v[ax[0]], v[ax[1]] = c[0], c[1]
                    v[k] = ref
                    ring.append(QVector3D(*v))
                good.append(ring)
        if good:
            return mesh.add_face(loop, good)
    except Exception:  # noqa: BLE001
        pass
    try:
        return mesh.add_face(loop)
    except Exception:  # noqa: BLE001
        return None

def empty() -> dict:
    return {"arch": M.load({"project": M.new_project(name="")}),
            "imports": {}, "texts": [], "settings": dict(DEFAULTS),
            "site": SITE_.load_site(None), "grid": SITE_.load_grid(None),
            "stairs": [], "stair_cad": {}, "materials": {},
            "parking": {}, "ramps": [], "marks": {}, "landscape": {},
            "off3d": [], "roof_terraces": [],
            "comp_names": {}, "man_shafts": [], "ceilings": {},
            "furniture": [], "ffl_marks": [], "slab_edges": {},
            "sunshades": {}, "lowparts": {}, "domes": [], "minarets": [],
            "chhatris": [], "fitout": []}


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
    rs_ = raw.get("settings") or {}
    if rs_ and "steps_v" not in rs_ and abs(float(rs_.get(
            "riser_max", 0.1778) or 0.1778) - 0.1778) < 1e-4 and abs(float(
            rs_.get("tread_ext", 0.2794) or 0.2794) - 0.2794) < 1e-4:
        # the floor steps' old defaults (7" / 11", never changed): 6" / 12"
        doc["settings"]["riser_max"] = DEFAULTS["riser_max"]
        doc["settings"]["tread_ext"] = DEFAULTS["tread_ext"]
    if (raw.get("settings") or {}) and "gffl_v" not in raw["settings"]:
        # a project from before 3.14: the ground floor at +2'-0" by default
        doc["settings"]["ground_ffl"] = DEFAULTS["ground_ffl"]
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
    # elements kept out of the 3D model (drawn on a floor they are not on)
    doc["off3d"] = sorted({str(k) for k in raw.get("off3d") or []
                           if isinstance(k, str) and "|" in k})
    doc["roof_terraces"] = [str(k) for k in raw.get("roof_terraces") or []
                            if isinstance(k, str)]
    # the component types' marks and names (components.py)
    doc["comp_names"] = {}
    for k, v in (raw.get("comp_names") or {}).items():
        if not isinstance(v, dict) or not v.get("mark"):
            continue
        ent = {kk: str(vv)[:80] for kk, vv in v.items()
               if kk in ("mark", "name")}
        lib = v.get("lib")              # a library model standing in
        if isinstance(lib, dict) and lib.get("key"):
            ent["lib"] = {kk: lib[kk] for kk in
                          ("key", "fit", "rot", "name", "entry") if kk in lib}
        mir = v.get("mirror")           # the type mirrored
        if isinstance(mir, dict) and (mir.get("x") or mir.get("y")):
            ent["mirror"] = {kk: True for kk in ("x", "y") if mir.get(kk)}
        doc["comp_names"][str(k)] = ent
    # openings cut by hand in the slabs (shafts), on a floor or through all
    doc["man_shafts"] = [m for m in raw.get("man_shafts") or []
                         if isinstance(m, dict) and m.get("id")
                         and len(m.get("pts") or []) >= 3
                         and (m.get("level") in ids or m.get("through"))]
    # false ceilings per level (ceilings.py), furniture placed in rooms,
    # level marks placed by hand, slab edges (railings / sun shades)
    doc["ceilings"] = {k: v for k, v in (raw.get("ceilings") or {}).items()
                       if k in ids and isinstance(v, dict)}
    doc["furniture"] = [f for f in raw.get("furniture") or []
                        if isinstance(f, dict) and f.get("level") in ids
                        and f.get("key")]
    # the fit-out read from the CAD (fitout.py): shower glass, cladding,
    # AC diffusers
    doc["fitout"] = [f for f in raw.get("fitout") or []
                     if isinstance(f, dict) and f.get("level") in ids
                     and f.get("kind") in ("glass", "clad", "diffuser",
                                           "light", "liftdoor")]
    doc["ffl_marks"] = [m for m in raw.get("ffl_marks") or []
                        if isinstance(m, dict) and m.get("level") in ids]
    # slab openings closed by hand: kept closed when the CAD is read again
    doc["closed_holes"] = [m for m in raw.get("closed_holes") or []
                           if isinstance(m, dict) and m.get("level") in ids]
    doc["slab_edges"] = {k: v for k, v in (raw.get("slab_edges") or {}).items()
                         if k in ids and isinstance(v, dict)}
    doc["sunshades"] = {k: v for k, v in (raw.get("sunshades") or {}).items()
                        if k in ids and isinstance(v, dict)}
    # the «line» layer's low walls and low platforms (lowparts.py)
    doc["lowparts"] = {k: v for k, v in (raw.get("lowparts") or {}).items()
                       if k in ids and isinstance(v, dict)}
    from . import domes as DM_                 # the domes (domes.py)
    doc["domes"] = [d for d in DM_.load(raw.get("domes")) if d["level"] in ids]
    from . import minarets as MN_              # minarets, chhatris
    for k_ in ("minarets", "chhatris"):
        doc[k_] = [d for d in MN_.load(raw.get(k_), k_) if d["level"] in ids]
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


_FLOOR = r"(FOUND\w*|FDN|BASE\w*|BSMT|GRD|GROUND|G\.?F|ROOF|TOP|\d+\s*(?:ST|ND|RD|TH)?)"
_RANGE = re.compile(_FLOOR + r"\s*(?:FLOOR|FLR|FL)?\.?\s*(?:TO|-|~)\s*" + _FLOOR)


def _floor_no(word: str) -> int:
    w = word.upper().replace(" ", "")
    if w.startswith(("FOUND", "FDN", "BASE", "BSMT")):
        return -99
    if w in ("GRD", "GROUND", "GF", "G.F"):
        return 0
    if w in ("ROOF", "TOP"):
        return 99
    m = re.match(r"\d+", w)
    return int(m.group()) if m else 0


def floor_range(layer: str):
    """(from, to) floors a layer's name says it runs through («S-CONC-4
    FOUNDATION TO 6TH» → (-99, 6), «COL.3RD TO 6TH» → (3, 6), «6TH TO
    ROOF» → (6, 99)), or None when it names no range."""
    m = _RANGE.search(str(layer).upper().replace("[", "").replace("]", ""))
    if not m:
        return None
    a, b = _floor_no(m.group(1)), _floor_no(m.group(2))
    return (min(a, b), max(a, b))


def level_floor_no(arch, lid) -> int:
    """A level's floor number: the ground floor 0, the floors above 1, 2…,
    the basements −1, −2…"""
    el = elevations(arch)
    order = sorted(range(len(arch["levels"])), key=lambda i: el[i])
    ids = [arch["levels"][i]["id"] for i in order]
    g = next((k for k, i in enumerate(order)
              if arch["levels"][i]["kind"] == "ground"), 0)
    return ids.index(lid) - g if lid in ids else 0


def column_layers_for(pats, floor: int) -> list:
    """The column layer patterns that stand on ``floor``: a layer naming a
    run of floors only where it runs; every other one everywhere."""
    out = []
    for p in pats:
        r = floor_range(p)
        if r is None or r[0] <= floor <= r[1]:
            out.append(p)
    return out


def _corner_windows(doc, lid, pl, P, how, made) -> int:
    """Corner windows of the placed plan ``pl`` on level ``lid`` (its walls
    ``made``): «Corner window n» added (its legs: walls carrying one
    window round the corner); the number of windows."""
    from shapely.geometry import Polygon as _PgW

    from . import cornerwin as CW
    arch = doc["arch"]
    st = doc["settings"]
    lay = pl["layers"]
    wsegs = [s_ for s_ in pl["segs"] if _match(lay[s_[4]], P["windows"])]
    wpl = W.plan([w for w in made if W.why_not(w) is None
                  and not str(w.get("name", "")).startswith("Corner window")])
    wpolys = [_PgW(pc["outer"]).buffer(0) for ps in wpl.values() for pc in ps]
    recs = []
    for w in made:
        if w.get("kind", "line") != "line" or W.why_not(w) is not None or \
                str(w.get("name", "")).startswith("Corner window"):
            continue
        c_ = W.centre(w)
        recs.append((tuple(c_.p0), tuple(c_.p1), float(w["t"])))
    rails_ = []
    legs = CW.find(wsegs, wpolys, wall_lines=[(a, b) for a, b, _t in recs],
                   wall_recs=recs, rails_out=rails_)
    if not legs and not rails_:
        return 0
    # each leg: a wall like the one it carries on (its thickness, height,
    # finish…) under the sill and over the head; between them ONE aluminium
    # window turning the corner (frame, corner post, glass) — the legs of
    # a chain share its id («cwin»)
    base_ws = [w for w in made if w.get("kind", "line") == "line"
               and W.why_not(w) is None
               and not str(w.get("name", "")).startswith("Corner window")]

    def _like(a, b, t):
        u = ((b[0] - a[0]), (b[1] - a[1]))
        L = math.hypot(*u) or 1.0
        u = (u[0] / L, u[1] / L)
        best, bd = None, 1e9
        for w in base_ws:
            c_ = W.centre(w)
            v = (c_.p1[0] - c_.p0[0], c_.p1[1] - c_.p0[1])
            Lv = math.hypot(*v) or 1.0
            if abs(u[0] * v[1] / Lv - u[1] * v[0] / Lv) > 0.09:
                continue
            dd = min(math.dist(p_, q_) for p_ in (a, b)
                     for q_ in (c_.p0, c_.p1))
            if dd < bd:
                best, bd = w, dd
        if best is None:
            best = min(base_ws, key=lambda w: min(
                math.dist(p_, tuple(q_)) for p_ in (a, b)
                for q_ in (w["a"], w["b"]))) if base_ws else None
        return best
    keep = ("type", "height", "base", "h", "material", "finish", "layer",
            "rcc", "top_att", "bot_att", "plaster", "skirting")
    # the legs in chains (sharing an end): one window each
    legs = [l for l in legs if math.dist(l[0], l[1]) >= 0.25]
    grp = list(range(len(legs)))

    def _root(k):
        while grp[k] != k:
            k = grp[k]
        return k
    for i_ in range(len(legs)):
        for j_ in range(i_ + 1, len(legs)):
            if min(math.dist(p_, q_) for p_ in legs[i_][:2]
                   for q_ in legs[j_][:2]) < 0.02:
                grp[_root(j_)] = _root(i_)
    # glazing round a terrace (two lines only, thinner than the walls it
    # joins: the railing's outline) is the terrace's railing, not a window —
    # made by terrace_railings (with every other railing round the terrace)
    if not legs:
        return 0
    have = {str(w.get("name", "")).split(" ·")[0] for w in arch["walls"]
            if str(w.get("name", "")).startswith("Corner window")}
    k_ = 1
    names, cids = {}, {}
    for i_ in range(len(legs)):
        r_ = _root(i_)
        if r_ not in names:
            while f"Corner window {k_}" in have:
                k_ += 1
            names[r_] = f"Corner window {k_}"
            have.add(names[r_])
            cids[r_] = uuid.uuid4().hex[:8]
    crecs, nm = [], []
    sill = float(st.get("sill", 0.9))
    win_h = float(st.get("win_h", 1.2))
    for i_, (a, b, t) in enumerate(legs):
        like = _like(a, b, t) or {}
        rec = {"kind": "line", "a": [round(a[0], 4), round(a[1], 4)],
               "b": [round(b[0], 4), round(b[1], 4)], "t": round(t, 3),
               "align": "centre", "side": 1, "height": "level", "base": 0.0,
               "level": lid, "type": "solid", "cwin": cids[_root(i_)],
               "cw_low": round(sill, 4), "cwin_h": round(win_h, 4)}
        for k2 in keep:
            if k2 in like and k2 != "type":
                rec[k2] = copy.deepcopy(like[k2])
        crecs.append(rec)
        nm.append(names[_root(i_)])
    made_c = M.new_walls(arch["walls"], crecs)
    seen_ = {}
    for w_, n_ in zip(made_c, nm):
        seen_[n_] = seen_.get(n_, 0) + 1
        w_["name"] = f"{n_} · leg {seen_[n_]}"
    arch["walls"] += made_c
    try:                  # glazing that is the wall, a door drawn in it
        _doors_on_glass(doc, lid, pl, P, made_c)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._doors_on_glass")
    return len(set(nm))


def _doors_on_glass(doc, lid, pl, P, legs) -> int:
    """The window layer drawn as the wall (glazing from wall to wall, no
    wall lines): where the plan draws a door in it (a swing / a door block
    across it) that glass leg is made a curtain wall and the door set into
    its grid there, as wide as drawn. The number of doors placed."""
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    if not legs:
        return 0
    lay = pl["layers"]
    dl = [LineString([(s_[0], s_[1]), (s_[2], s_[3])]) for s_ in pl["segs"]
          if _match(lay[s_[4]], P["doors"]) and
          math.hypot(s_[2] - s_[0], s_[3] - s_[1]) > 1e-4]
    marks = []
    if dl:
        u = unary_union([ln.buffer(0.03) for ln in dl])
        marks += [g for g in getattr(u, "geoms", [u])
                  if g.geom_type == "Polygon"]
    for ins in pl.get("inserts") or []:
        if _match(ins.get("layer", ""), P["doors"]) or \
                "DOOR" in str(ins.get("name", "")).upper():
            cs = ins.get("corners") or []
            if len(cs) >= 3:
                xs = [c[0] for c in cs]
                ys = [c[1] for c in cs]
                marks.append(box(min(xs), min(ys), max(xs), max(ys)))
    if not marks:
        return 0
    n = 0
    for w in legs:
        c_ = W.centre(w)
        a, b = tuple(c_.p0), tuple(c_.p1)
        L = math.dist(a, b)
        if L < 1.2:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        line = LineString([a, b])
        hits = []
        for m in marks:
            if m.distance(line) > 0.15:
                continue
            xs = [(q[0] - a[0]) * ux + (q[1] - a[1]) * uy
                  for q in m.exterior.coords]
            t0, t1 = max(min(xs), 0.0), min(max(xs), L)
            wd = t1 - t0
            if 0.6 <= wd <= 2.6:
                hits.append(((t0 + t1) / 2, wd))
        if not hits:
            continue
        if w.get("type") != "curtain":
            to_curtain(doc, [w["id"]])
        for pos, wd in hits:
            rec, _why = add_cw_door(doc, w["id"], width=wd, pos=pos)
            if rec is not None:
                n += 1
    return n


def cover_corner_windows(doc, lid) -> int:
    """The slabs over and under level ``lid`` (and its roof) carried out
    over its corner windows — the floor under them, the slab or roof over
    them; a slab made over a block that had none. The number changed."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    cws = [w for w in arch["walls"] if w["level"] == lid and
           str(w.get("name", "")).startswith("Corner window")]
    if not cws:
        return 0
    lines = []
    for w in cws:
        c_ = W.centre(w)
        lines.append((tuple(c_.p0), tuple(c_.p1), float(w["t"])))
    glass = unary_union([LineString([a, b]).buffer(t / 2, cap_style=2,
                                                   join_style=2)
                         for a, b, t in lines])
    el = elevations(arch)
    order = [arch["levels"][i]["id"] for i in
             sorted(range(len(arch["levels"])), key=lambda i: el[i])]
    k = order.index(lid) if lid in order else -1
    above = order[k + 1] if 0 <= k < len(order) - 1 else None
    on_top = slab_on_top(doc)
    over = [s for s in arch["structure"] if s["type"] == "slab" and (
        (s["level"] == lid and (s.get("top") or (
            on_top and not s.get("zone") and not s.get("user")))) or
        (not on_top and above is not None and s["level"] == above
         and not s.get("top")))]
    over += [s for s in arch["structure"]
             if s["type"] == "roof" and s["level"] == lid]
    cands = over + [s for s in _floor_slabs(doc, lid) if s not in over]
    n = 0
    for s in cands:
        if not s.get("corners") or s.get("zone"):
            continue
        sp = SE._poly(s["corners"])
        if sp.is_empty or sp.distance(glass) > 2.0 or \
                sp.buffer(0.02).contains(glass):
            continue
        hw = max(t for _a, _b, t in lines) / 2
        new = SE.extend_outline(s["corners"], [(a, b) for a, b, _t in lines],
                                reach=2.5, half=hw)
        if new is not s["corners"]:
            s["corners"] = [[round(p[0], 4), round(p[1], 4)] for p in new]
            n += 1
    # a block of walls closed by its corner windows with no slab over it
    covered = unary_union([SE._poly(s["corners"]) for s in over
                           if s.get("corners")] or [glass.buffer(0)])
    if not doc["settings"].get("slab_on", True):
        return n
    mine = [w for w in arch["walls"] if w["level"] == lid]
    plans = W.plan([w for w in mine if W.why_not(w) is None])
    recs = []
    for o in _outer_loops([pc for ps in plans.values() for pc in ps],
                          least=2.0):
        poly = SE._poly(o)
        if poly.is_empty or not poly.buffer(0.05).intersects(glass):
            continue
        if over and covered.intersection(poly).area > 0.5 * poly.area:
            continue
        rec = {"type": "slab", "level": lid if on_top or above is None
               else above,
               "corners": [[round(p[0], 4), round(p[1], 4)]
                           for p in S._ccw(o)],
               "holes": [], "shafts": [],
               "t": float(doc["settings"].get("slab_t", 0.15)),
               "offset": 0.0}
        if on_top or above is None:
            rec["top"] = True
        if S.why_not(rec) is None:
            recs.append(rec)
    if recs:
        arch["structure"] += M.new_elements(arch["structure"], recs)
        n += len(recs)
    return n


def redetect_corner_windows(doc, lids=None) -> dict:
    """Corner windows of levels ``lids`` (all imported ones by default) read
    again from their CAD plans — the rest of the level as it is (rooms,
    edits kept). {level id: n}."""
    arch = doc["arch"]
    st = doc["settings"]
    out = {}
    for lid, how in (doc.get("imports") or {}).items():
        if lids is not None and lid not in lids:
            continue
        if not isinstance(how, dict) or not how.get("file") or \
                lid not in {lv["id"] for lv in arch["levels"]}:
            continue
        raw = cadread.read(how["file"], how.get("unit"))
        drawing = cadread.crop(raw, how.get("region"))
        base = cadread.base_point(drawing, how.get("base", "origin"),
                                  (how.get("bx", 0.0), how.get("by", 0.0)))
        pl = cadread.place(drawing, base,
                           (how.get("ix", 0.0), how.get("iy", 0.0)),
                           how.get("rot", 0.0))
        P, _found = layer_patterns(drawing, how, st)
        gone = {w["id"] for w in arch["walls"] if w["level"] == lid and
                str(w.get("name", "")).startswith("Corner window")}
        arch["walls"] = [w for w in arch["walls"] if w["id"] not in gone]
        arch["openings"] = [o for o in arch["openings"]
                            if o["wall"] not in gone]
        mine = [w for w in arch["walls"] if w["level"] == lid]
        out[lid] = _corner_windows(doc, lid, pl, P, how, mine)
        if out[lid]:
            try:
                cover_corner_windows(doc, lid)
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project cover_corner_windows")
    return out


def _placed_plan(doc, lid):
    """(placed plan, layer patterns) of level ``lid``'s CAD import, or
    (None, None)."""
    how = (doc.get("imports") or {}).get(lid)
    if not isinstance(how, dict) or not how.get("file"):
        return None, None
    raw = cadread.read(how["file"], how.get("unit"))
    drawing = cadread.crop(raw, how.get("region"))
    base = cadread.base_point(drawing, how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    pl = cadread.place(drawing, base, (how.get("ix", 0.0), how.get("iy", 0.0)),
                       how.get("rot", 0.0))
    P, _f = layer_patterns(drawing, how, doc["settings"])
    return pl, P


CURB_H, CURB_T = 0.1524, 0.0762          # the terrace railing's upstand


RAIL_WORDS = re.compile(r"RAIL|RALL|BALCON|GRILL\s*RAIL|PARAPET\s*RAIL",
                        re.I)
TERRACE_WORDS = re.compile(r"TERRACE|TERACE|SIT\s*OUT|BALCON", re.I)


def _arc_line(a_, n=16):
    """A CAD arc ({c, r, p0, pm, p1}) as a polyline."""
    from shapely.geometry import LineString
    cx, cy = a_["c"]
    r = float(a_["r"])
    t0 = math.atan2(a_["p0"][1] - cy, a_["p0"][0] - cx)
    t1 = math.atan2(a_["p1"][1] - cy, a_["p1"][0] - cx)
    tm = math.atan2(a_["pm"][1] - cy, a_["pm"][0] - cx)
    ccw = (t1 - t0) % (2 * math.pi)
    if (tm - t0) % (2 * math.pi) > ccw:      # it runs the other way
        ccw = ccw - 2 * math.pi
    pts = [(cx + r * math.cos(t0 + ccw * k / n),
            cy + r * math.sin(t0 + ccw * k / n)) for k in range(n + 1)]
    return LineString(pts)


#: names of the outdoors on a plan: they never bring the floor slab out
OUTDOOR_WORDS = re.compile(
    r"SIDE\s*PASSAGE|BACK\s*PASSAGE|FRONT\s*PASSAGE|LAWN|DRIVE\s*WAY|"
    r"\bDRIVE\b|GARDEN|PARKING|\bROAD\b|STREET|\bPLOT\b|COURT\s*YARD|"
    r"\bYARD\b|SET\s*BACK|GREEN\s*(AREA|BELT)|BOUNDARY", re.I)


def drawn_floor(doc, lid, pl, P):
    """The floor as the plan draws it: every area its walls, glazing,
    railings and columns close (rooms, corridors, balconies out to their
    railings) — not a pocket open to the outside, not past a railing. A
    shapely polygon, or None when the plan's lines do not close round
    most of the building (then nothing is clipped)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    lay = pl["layers"]
    walls = [w for w in arch["walls"] if w["level"] == lid
             and W.why_not(w) is None]
    if not walls:
        return None
    ls = []
    for g in SE.wall_polys(walls):
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon":
                ls.append(q.exterior)
    for c in arch["structure"]:
        if c.get("type") == "column" and c.get("level") == lid:
            try:
                ls.append(Polygon(S.column_outline(c, 0.0)).exterior)
            except Exception:  # noqa: BLE001
                pass
    keep = [P["walls"], P["windows"], P.get("rails") or [], P["columns"]]

    def ok(name):
        return any(pp and _match(name, pp) for pp in keep)
    for s_ in pl["segs"]:
        if ok(lay[s_[4]]) and math.hypot(s_[2] - s_[0], s_[3] - s_[1]) > 0.01:
            ls.append(LineString([(s_[0], s_[1]), (s_[2], s_[3])]))
    for a_ in pl.get("arcs") or ():
        if ok(str(a_.get("layer", ""))):
            try:
                ls.append(_arc_line(a_))
            except Exception:  # noqa: BLE001
                pass
    try:
        faces = [g for g in polygonize(unary_union(ls)) if g.area >= 0.02]
    except Exception:  # noqa: BLE001
        return None
    if not faces:
        return None
    R = unary_union([g.buffer(0.005) for g in faces]).buffer(-0.005)
    # (a stray closed box far off is not the floor: the parts touching
    # the walls)
    WU = unary_union(SE.wall_polys(walls))
    R = unary_union([g for g in getattr(R, "geoms", [R])
                     if g.geom_type == "Polygon" and g.intersects(
                         WU.buffer(0.05))])
    return R if not R.is_empty else None


def strict_floor(doc, lid, pl=None, P=None) -> int:
    """An upper floor's slab as its own CAD plan draws it: inside its walls
    and the railings round its terraces — no part out past them (a shade
    over the floor below no plan draws), the terrace out to its railing.
    The slabs changed."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    lv = level_by_id(arch, lid) or {}
    if slab_on_top(doc) or lv.get("kind") in ("ground", "basement"):
        return 0
    ws = [w for w in arch["walls"] if w["level"] == lid
          and w.get("kind", "line") == "line" and W.why_not(w) is None
          and math.dist(w["a"], w["b"]) > 0.05]
    walls = [w for w in ws if not w.get("rail")]
    rails = [w for w in ws if w.get("rail") and not str(
        w.get("name", "")).startswith(AUTO_RAIL)]
    if not walls:
        return 0
    pieces = [LineString([w["a"], w["b"]]).buffer(
        float(w.get("t", 0.1)) / 2 + 0.03, cap_style=2, join_style=2)
        for w in walls + rails]
    # curved walls and railings (a balcony's), the columns
    for w in arch["walls"]:
        if w["level"] != lid or w.get("kind", "line") == "line":
            continue
        try:
            c_ = W.centre(w)
            pieces.append(LineString([c_.at(i / 24) for i in range(25)])
                          .buffer(float(w.get("t", 0.1)) / 2 + 0.03))
        except Exception:  # noqa: BLE001
            continue
    for c_ in arch["structure"]:
        if c_.get("type") == "column" and c_.get("level") == lid:
            try:
                pieces.append(Polygon(S.column_outline(c_, 0.0)).buffer(0.03))
            except Exception:  # noqa: BLE001
                continue
    band = unary_union(pieces)
    reach = 1.5
    u_ = band.buffer(reach, join_style=2).buffer(-reach, join_style=2)
    allowed = unary_union([Polygon(g.exterior) for g in getattr(
        u_, "geoms", [u_]) if g.geom_type == "Polygon" and
        Polygon(g.exterior).area >= 4.0])
    try:                 # the blocks the walls close (as the slab is made)
        ol_ = _outer_loops([], extra=[band])
        if ol_:
            allowed = unary_union([allowed] + [Polygon(o).buffer(0)
                                               for o in ol_])
    except Exception:  # noqa: BLE001
        pass
    if allowed.is_empty:
        return 0
    drawn_ = None
    try:
        if pl is None:
            pl, P = _placed_plan(doc, lid)
        if pl is not None and P is not None:
            drawn_ = drawn_floor(doc, lid, pl, P)
    except Exception:  # noqa: BLE001
        drawn_ = None
    n = 0
    for e in arch["structure"]:
        if e["type"] != "slab" or e["level"] != lid or e.get("roof") or \
                e.get("zone") or e.get("user") or e.get("top") or \
                not e.get("corners"):
            continue
        sp = SE._poly(e["corners"])
        new = (sp.union(allowed) if rails else sp).intersection(
            allowed.buffer(0.02, join_style=2))
        if drawn_ is not None:          # as the plan's lines close it
            cut_ = new.intersection(drawn_.buffer(0.02, join_style=2))
            if not cut_.is_empty and cut_.area >= 0.6 * new.area:
                new = cut_
        new = SE._largest(new, sp.representative_point())
        if new is None or new.area < 1.0 or \
                abs(new.area - sp.area) < 0.05 and \
                new.symmetric_difference(sp).area < 0.05:
            continue
        e["corners"] = [[round(x, 4), round(y, 4)]
                        for x, y in SE._ring_pts(new)]
        hs = [h for h in e.get("holes") or []
              if new.contains(Polygon(h).representative_point())]
        e["holes"] = hs
        n += 1
    return n


def rail_text_points(doc, lid, pl=None, terrace=False) -> list:
    """[(x, y)] of the CAD's texts on level ``lid`` that name a railing or
    a balcony («RAILING», «S.S RAIL», «BALCONY»…) — with ``terrace`` a
    terrace too («TERRACE», «BACK TERRACE», «SIT OUT»: a terrace upstairs
    is railed)."""
    src = (pl or {}).get("texts") if pl is not None else None
    if src is None:
        src = [t for t in doc.get("texts") or [] if t.get("level") == lid]
    return [(float(t["x"]), float(t["y"])) for t in src
            if RAIL_WORDS.search(str(t.get("text", ""))) or (
                terrace and TERRACE_WORDS.search(str(t.get("text", ""))))]


def basement_windows(doc) -> dict:
    """The windows in a basement's outside walls kept between the natural
    ground (0) and the ground floor (under its slab): a window that cannot
    fit there goes. {"moved", "removed"}."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    out = {"moved": 0, "removed": 0}
    info = S.levels_info(arch, M.elevations)
    g = next((lv for lv in arch["levels"] if lv.get("kind") == "ground"),
             None)
    if g is None:
        return out
    z_g = info[g["id"]]["z0"]
    slab_t = float(doc["settings"].get("slab_t", 0.1524) or 0.1524)
    # the ground floor read already: its level is the one to keep under
    # (before that, nothing is taken away — the levels may change yet)
    final = any(w["level"] == g["id"] for w in arch["walls"])
    for lv in arch["levels"]:
        if lv.get("kind") != "basement":
            continue
        lid = lv["id"]
        z0 = info[lid]["z0"]
        walls = [w for w in arch["walls"] if w["level"] == lid
                 and not w.get("rail") and W.why_not(w) is None]
        if not walls:
            continue
        try:
            u_ = unary_union(SE.wall_polys(walls)).buffer(
                1.0, join_style=2).buffer(-1.0, join_style=2)
            foot = unary_union([Polygon(q.exterior) for q in
                                getattr(u_, "geoms", [u_])
                                if q.geom_type == "Polygon"])
        except Exception:  # noqa: BLE001
            continue
        edge = foot.boundary
        outer = {w["id"]: w for w in walls if edge.distance(
            LineString([w["a"], w["b"]]).interpolate(0.5, normalized=True))
            < float(w.get("t", 0.2)) / 2 + 0.3}
        keep = []
        for o in arch["openings"]:
            w = outer.get(o["wall"])
            if w is None or o["kind"] != "window":
                keep.append(o)
                continue
            base = z0 + float(w.get("base", 0.0) or 0.0)
            lo = max(0.0, z0) + 0.15 - base          # over the ground
            hi = (z_g - slab_t) - 0.05 - base        # under the ground floor
            if hi - lo < 0.3:
                if final:
                    out["removed"] += 1
                    continue
                keep.append(o)
                continue
            h = min(float(o["h"]), hi - lo)
            sill = hi - h
            if abs(sill - float(o.get("sill", 0))) > 0.005 or \
                    abs(h - float(o["h"])) > 0.005:
                o["sill"], o["h"] = round(sill, 4), round(h, 4)
                out["moved"] += 1
            keep.append(o)
        arch["openings"] = keep
    return out


def rails_off_stairs(doc) -> int:
    """The terrace / balcony railings (walls) standing over a stair that
    climbs to their floor cut back off it — the stair's own railing runs
    with the flight. How many changed."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    from . import stairs as ST_
    arch = doc["arch"]
    n = 0
    for lv in arch["levels"]:
        lid = lv["id"]
        sfp = []
        for st_ in doc.get("stairs") or []:
            if st_.get("level") == lid:
                continue
            fl_, _lg = ST_.as_flights(st_)
            for f_ in fl_:
                ls_ = f_.get("lines") or []
                if len(ls_) < 2:
                    continue
                pg = Polygon([tuple(ls_[0][0][:2]), tuple(ls_[0][1][:2]),
                              tuple(ls_[-1][1][:2]), tuple(ls_[-1][0][:2])])
                sfp.append(pg.buffer(0))
        if not sfp:
            continue
        SU = unary_union(sfp).buffer(0.2, join_style=2)
        keep, add = [], []
        for w in arch["walls"]:
            if w["level"] != lid or not w.get("rail") or \
                    not str(w.get("name", "")).startswith(
                        ("Terrace railing", "Balcony railing")):
                keep.append(w)
                continue
            ln = LineString([w["a"], w["b"]])
            if not ln.intersects(SU):
                keep.append(w)
                continue
            n += 1
            g_ = ln.difference(SU)
            for q in getattr(g_, "geoms", [g_]):
                if q.geom_type == "LineString" and q.length >= 0.5:
                    c_ = list(q.coords)
                    add.append(dict({k: v for k, v in w.items()
                                     if k not in ("id",)},
                                    a=[round(c_[0][0], 4), round(c_[0][1], 4)],
                                    b=[round(c_[-1][0], 4),
                                       round(c_[-1][1], 4)]))
        if n:
            arch["walls"] = keep
            arch["walls"] += M.new_walls(arch["walls"], add) if add else []
    return n


def _meet_lines(lines, reach=0.35) -> list:
    """Straight railing runs whose ends stop short of / run past one
    another at a corner: each carried to where the two lines cross, so the
    corner closes cleanly (no gap, no overlap)."""
    ls = [[tuple(a), tuple(b)] for a, b in lines]

    def cross(p, q, r, s_):
        d1 = (q[0] - p[0], q[1] - p[1])
        d2 = (s_[0] - r[0], s_[1] - r[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            return None
        t = ((r[0] - p[0]) * d2[1] - (r[1] - p[1]) * d2[0]) / den
        return (p[0] + d1[0] * t, p[1] + d1[1] * t)
    for i in range(len(ls)):
        for ei in (0, 1):
            best = None
            for j in range(len(ls)):
                if j == i:
                    continue
                for ej in (0, 1):
                    dd = math.dist(ls[i][ei], ls[j][ej])
                    if dd > reach or (best is not None and dd >= best[0]):
                        continue
                    x = cross(ls[i][0], ls[i][1], ls[j][0], ls[j][1])
                    if x is None:
                        continue
                    if math.dist(x, ls[i][ei]) > reach + 0.1 or \
                            math.dist(x, ls[j][ej]) > reach + 0.1:
                        continue
                    best = (dd, j, ej, x)
            if best is not None:
                _d, j, ej, x = best
                ls[i][ei] = (round(x[0], 4), round(x[1], 4))
                ls[j][ej] = (round(x[0], 4), round(x[1], 4))
    return [(a, b) for a, b in ls if math.dist(a, b) > 0.05]


def terrace_railings(doc, lid, pl=None, P=None) -> dict:
    """The railings round level ``lid``'s terraces (the slab under it out
    past its walls): along the railing lines the CAD plan draws there
    (window / rail layers) — the terrace slab cut back to them, nothing
    beyond the railing — and along every other free edge of the terrace;
    each on a 3" × 6" upstand. The old «Terrace railing n» go first.
    {"lines", "edges", "trimmed"}."""
    import math as _m

    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union

    from . import cornerwin as CW
    from . import slabedges as SE
    arch = doc["arch"]
    st = doc["settings"]
    out = {"lines": 0, "edges": 0, "trimmed": 0}
    arch["walls"] = [w for w in arch["walls"] if not (
        w["level"] == lid and
        str(w.get("name", "")).startswith("Terrace railing"))]
    lv_ = level_by_id(arch, lid) or {}
    if not slab_on_top(doc) and lv_.get("kind") == "ground" and \
            not ground_slab_on(doc):
        return out            # the ground floor on the ground: no terrace
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and W.why_not(w) is None]
    wps = SE.wall_polys(walls)
    if not wps:
        return out
    u_ = unary_union(wps).buffer(1.0, join_style=2).buffer(-1.0,
                                                           join_style=2)
    foot = unary_union([Polygon(g.exterior) for g in getattr(u_, "geoms", [u_])
                        if g.geom_type == "Polygon"])
    slabs = [e for e in arch["structure"] if e["type"] == "slab"
             and not e.get("zone") and e.get("corners")
             and SE.floor_level_of(doc, e) == lid and
             (e["level"] != lid or not e.get("top"))]
    terr = []
    for e in slabs:
        sp = SE._poly(e["corners"])
        if sp.is_empty or sp.distance(foot) > 0.5:
            continue                     # a separate roof (a guard room)
        if sp.difference(foot.buffer(0.05)).area < 1.0:
            continue                     # nothing out past the walls
        terr.append(e)
    if not terr:
        return out
    if st.get("rail_needs_text", True):
        # a railing only where the CAD writes it (RAILING, BALCONY…): the
        # terraces with such a text on them or by their edge
        pts_ = rail_text_points(doc, lid, pl, terrace=True)
        terr = [e for e in terr if any(
            SE._poly(e["corners"]).difference(foot).buffer(2.0).contains(
                Point(x, y)) for x, y in pts_)]
        out["no_text"] = not terr
        if not terr:
            return out
    rk = st.get("parapet_rail", "ss_bars")
    rk = rk if rk and rk != "solid" else "ss_bars"
    rh = float(st.get("rail_h", 1.0668))
    ch_ = float(st.get("terrace_curb_h", 0.3048) or CURB_H)  # the upstand
    # the railing lines the plan draws round the terraces
    lines = []
    rail_lines = []                  # those on the rail layers, whole
    if pl is None and lid in (doc.get("imports") or {}):
        try:
            pl, P = _placed_plan(doc, lid)
        except Exception:  # noqa: BLE001
            pl = None
    if pl is not None and P is not None:
        lay = pl["layers"]
        zone = unary_union([SE._poly(e["corners"]) for e in terr]).buffer(0.4)
        near_walls = foot.buffer(0.3)
        segs, rsegs = [], []
        reach_ = foot.buffer(8.0, join_style=2)
        for s_ in pl["segs"]:
            is_r = _match(lay[s_[4]], P.get("rails") or [])
            if not (_match(lay[s_[4]], P["windows"]) or is_r):
                continue
            L = LineString([(s_[0], s_[1]), (s_[2], s_[3])])
            if L.length < 0.5:
                continue
            ang = _m.degrees(_m.atan2(s_[3] - s_[1], s_[2] - s_[0])) % 90.0
            if min(ang, 90.0 - ang) > 4.0:
                continue
            m_ = L.interpolate(0.5, normalized=True)
            if near_walls.contains(m_):
                continue
            if is_r and reach_.contains(m_):
                rsegs.append(s_)         # drawn as a railing: as drawn
            elif zone.contains(m_):
                segs.append(s_)
        for a, b, spread, _n in CW._clusters(segs, gap=0.3):
            if _m.dist(a, b) >= 0.8:
                lines.append((a, b))
        for a, b, spread, _n in CW._clusters(rsegs, gap=0.3):
            if _m.dist(a, b) >= 0.5:
                rail_lines.append((a, b))
    # the railing lines: the rail layer's run on to meet (their corners)
    rail_lines = _meet_lines(rail_lines, 0.35)
    lines = rail_lines + [ln for ln in lines if not any(
        LineString(ln).buffer(0.25).contains(LineString(r_).interpolate(
            0.5, normalized=True)) or LineString(r_).buffer(0.25).contains(
            LineString(ln).interpolate(0.5, normalized=True))
        for r_ in rail_lines)]
    # the terrace cut back to its railing lines (nothing beyond them)
    for a, b in lines:
        L = _m.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        nrm = (-u[1], u[0])
        # which side is «beyond» the railing: the side with less terrace
        # slab out there; alike, the side farther from the building
        allsl = unary_union([SE._poly(e["corners"]) for e in terr])

        def strip(sg, w_=1.5):
            return Polygon([a, b, (b[0] + nrm[0] * sg * w_,
                                   b[1] + nrm[1] * sg * w_),
                            (a[0] + nrm[0] * sg * w_,
                             a[1] + nrm[1] * sg * w_)])
        area_p = allsl.intersection(strip(1)).difference(foot).area
        area_m = allsl.intersection(strip(-1)).difference(foot).area
        if min(area_p, area_m) < 0.6 * max(area_p, area_m):
            if area_m < area_p:
                nrm = (-nrm[0], -nrm[1])
        else:
            dp = foot.distance(strip(1, 3.0))
            dm = foot.distance(strip(-1, 3.0))
            if abs(dp - dm) < 0.3:
                continue                     # no telling: leave the slab
            if dm > dp:
                nrm = (-nrm[0], -nrm[1])
        o_ = CURB_T / 2
        R = 3.5                              # an overhang, not a terrace
        cut = Polygon([(a[0] + nrm[0] * o_ - u[0] * 0.02,
                        a[1] + nrm[1] * o_ - u[1] * 0.02),
                       (b[0] + nrm[0] * o_ + u[0] * 0.02,
                        b[1] + nrm[1] * o_ + u[1] * 0.02),
                       (b[0] + nrm[0] * R + u[0] * 0.02,
                        b[1] + nrm[1] * R + u[1] * 0.02),
                       (a[0] + nrm[0] * R - u[0] * 0.02,
                        a[1] + nrm[1] * R - u[1] * 0.02)]).difference(foot)
        for e in terr:
            sp = SE._poly(e["corners"])
            if not sp.intersects(cut) or sp.intersection(cut).area < 0.05:
                continue
            rest = sp.difference(cut)
            rest = rest.buffer(-0.3, join_style=2).buffer(0.3, join_style=2)\
                .union(sp.difference(cut).intersection(foot.buffer(0.3)))
            rest = SE._largest(rest, sp.representative_point())
            if rest is not None and rest.area > 1.0:
                e["corners"] = [[round(x, 4), round(y, 4)]
                                for x, y in SE._ring_pts(rest)]
                out["trimmed"] += 1
    # a railing line left off the terrace (a second outline beyond the
    # one the slab now stops at): none
    left = unary_union([SE._poly(e["corners"]) for e in terr])
    keep_ = []
    edge_ = unary_union([g.exterior for g in getattr(left, "geoms", [left])
                         if g.geom_type == "Polygon"]).buffer(0.15)
    for a, b in rail_lines:              # the rail layer's: as drawn
        keep_.append((tuple(a), tuple(b)))
    for a, b in lines:                   # each along the terrace's edge
        if (a, b) in rail_lines:
            continue
        g_ = LineString([a, b]).intersection(left.buffer(0.12,
                                                         join_style=2))
        g_ = g_.intersection(edge_)
        parts_ = [q for q in getattr(g_, "geoms", [g_])
                  if q.geom_type == "LineString" and q.length >= 0.5]
        for q in parts_:
            c_ = list(q.coords)
            keep_.append((tuple(c_[0]), tuple(c_[-1])))
    lines = keep_
    # never over a stair coming up to this floor: its own railing runs
    # with the flight (one at this floor's height would float over it)
    try:
        from . import stairs as ST_
        sfp = []
        for st_ in doc.get("stairs") or []:
            if st_.get("level") == lid:
                continue
            fl_, _lg = ST_.as_flights(st_)
            for f_ in fl_:
                ls_ = f_.get("lines") or []
                if len(ls_) < 2:
                    continue
                sfp.append(Polygon([tuple(ls_[0][0]), tuple(ls_[0][1]),
                                    tuple(ls_[-1][1]), tuple(ls_[-1][0])])
                           .buffer(0))
        if sfp:
            SU = unary_union(sfp).buffer(0.2, join_style=2)
            cut_ = []
            for a, b in lines:
                g_ = LineString([a, b]).difference(SU)
                for q in getattr(g_, "geoms", [g_]):
                    if q.geom_type == "LineString" and q.length >= 0.5:
                        c_ = list(q.coords)
                        cut_.append((tuple(c_[0]), tuple(c_[-1])))
            out["off_stairs"] = len(lines) - len(cut_)
            lines = cut_
    except Exception:  # noqa: BLE001
        pass
    recs = []
    for a, b in lines:
        recs.append({"kind": "line", "a": [round(a[0], 4), round(a[1], 4)],
                     "b": [round(b[0], 4), round(b[1], 4)], "t": 0.05,
                     "align": "centre", "side": 1, "height": round(rh, 4),
                     "base": 0.0, "level": lid, "rail": rk,
                     "curb_h": ch_, "curb_t": CURB_T,
                     "curb_d": round(max(float(e_.get("t", 0.15))
                                         for e_ in terr), 4)})
    out["lines"] = len(recs)
    made = M.new_walls(arch["walls"], recs)
    arch["walls"] += made
    # every other free edge of the terraces: railed too — unless the plan
    # draws its railings (then only those: the CAD followed strictly)
    for e in ([] if lines else terr):
        for a, b in SE.free_edges(doc, e):
            L = _m.dist(a, b)
            if L < 0.3:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            nx, ny = -uy, ux                     # into the slab
            mid = Point((a[0] + b[0]) / 2 + nx * 0.2,
                        (a[1] + b[1]) / 2 + ny * 0.2)
            if foot.contains(mid):
                continue                         # inside the building
            o_ = CURB_T / 2
            rec = {"kind": "line",
                   "a": [round(a[0] + nx * o_, 4), round(a[1] + ny * o_, 4)],
                   "b": [round(b[0] + nx * o_, 4), round(b[1] + ny * o_, 4)],
                   "t": 0.05, "align": "centre", "side": 1,
                   "height": round(rh, 4), "base": 0.0, "level": lid,
                   "rail": rk, "curb_h": ch_, "curb_t": CURB_T,
                   "curb_d": round(float(e.get("t", 0.15)), 4)}
            m2 = M.new_walls(arch["walls"], [rec])
            arch["walls"] += m2
            made += m2
            out["edges"] += 1
    n0 = 0
    for w_ in made:
        n0 += 1
        w_["name"] = f"Terrace railing {n0}"
        w_["rail"] = rk
    if terrace_as_wall(st):
        out["corners"] = as_parapet_walls(made, rh)
    else:
        out["corners"] = join_rail_corners(doc, lid)
    return out


def restyle_terrace_railings(doc) -> int:
    """The terrace railings there are given the terrace edge set now — a
    railing on a 3" upstand ``terrace_curb_h`` high (the default), or the
    3" plastered wall — where they stand. How many."""
    st = doc["settings"]
    rk = st.get("parapet_rail", "ss_bars")
    rk = rk if rk and rk != "solid" else "ss_bars"
    rh = float(st.get("rail_h", 1.0668))
    ch_ = float(st.get("terrace_curb_h", 0.3048) or CURB_H)
    walls = [w for w in doc["arch"]["walls"]
             if str(w.get("name", "")).startswith("Terrace railing")]
    if terrace_as_wall(st):
        as_parapet_walls(walls, rh)
        return len(walls)
    for w in walls:
        lv = w["level"]
        t_ = max([float(e.get("t", 0.1016)) for e in doc["arch"]["structure"]
                  if e["type"] == "slab" and e["level"] == lv
                  and not e.get("grade")] or [0.0])
        w.update(rail=rk, t=0.05, height=round(rh, 4), base=0.0,
                 curb_h=round(ch_, 4), curb_t=CURB_T, curb_d=round(t_, 4))
        w["type"] = "solid"
    return len(walls)


#: the terrace parapet as a wall (by default): 3" thick, plastered
PARAPET_T = 0.0762


def terrace_as_wall(st) -> bool:
    """Terrace railings built as a 3" plastered wall (the default) rather
    than a railing on an upstand."""
    return (st or {}).get("terrace_rail_kind", "railing") == "wall3"


def as_parapet_walls(walls, h) -> int:
    """Railing records made walls: 3" thick, ``h`` tall, standing on the
    terrace floor — then their corners joined (each run to where the two
    lines cross), so the walls meet and merge clean. The corners joined."""
    for w in walls:
        for k in ("rail", "curb_h", "curb_t", "curb_d", "np_a", "np_b",
                  "cj_a", "cj_b"):
            w.pop(k, None)
        w["t"] = PARAPET_T
        w["height"] = round(float(h), 4)
        w["base"] = 0.0
        w["type"] = "solid"          # (a railing record came as glass)
    return join_wall_ends(walls)


def _square_cornered(g, tol=12.0) -> bool:
    """A polygon of square corners only (a box, an L, a T…) — no arrow
    head, no triangle."""
    try:
        sp = g.simplify(0.01)
        cs = list(sp.exterior.coords)[:-1]
    except Exception:  # noqa: BLE001
        return False
    if len(cs) < 4:
        return False
    for i in range(len(cs)):
        a, b, c = cs[i - 1], cs[i], cs[(i + 1) % len(cs)]
        v1 = (a[0] - b[0], a[1] - b[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        cosv = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        ang = math.degrees(math.acos(max(-1.0, min(1.0, cosv))))
        if abs(ang - 90.0) > tol and ang < 180.0 - tol:
            return False
    return True


def rcc_from_fills(arch, lid, pl) -> dict:
    """The CAD's hatches and solid fills in the walls (RCC work, as plans
    show it): a wall mostly covered by one is a structural RCC wall; a
    filled area no wall stands on — square-ish, up to 1.5 m a side — is an
    RCC column, a long thin one (up to 0.6 m thick) an RCC wall; a column
    under a fill is marked RCC. Big fills (floors, paving, lawns: over
    15 m²) are not walls. {"walls", "new_walls", "columns"}."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    out = {"walls": 0, "new_walls": 0, "columns": 0}
    fills = []
    skip_ = re.compile(r"ARROW|CAR|DOOR|STAIR|RAMP|TEXT|DIM|FURN|SAF|PARK|"
                       r"SECTION|GRID|TREE|PLANT|LAND|SYMB|NORTH|TILE|LOGO",
                       re.I)
    for f in (pl or {}).get("fills") or []:
        if skip_.search(str(f.get("layer", ""))):
            continue                     # an arrow head, a car, a door leaf
        try:
            g = Polygon(f["pts"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if g.is_empty or g.area < 0.01 or g.area > 15.0:
            continue
        # a triangle / an arrow head (well short of its box): not RCC —
        # an L / T of square corners (a corner column) is
        if g.area < 0.75 * g.minimum_rotated_rectangle.area and \
                not _square_cornered(g):
            continue
        fills.append(g)
    if not fills:
        return out
    FU = unary_union(fills)
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and w.get("kind", "line") == "line"
             and W.why_not(w) is None]
    wpolys = []
    for w in walls:
        try:
            wp = SE.wall_polys([w])
            wp = unary_union(wp) if wp else None
        except Exception:  # noqa: BLE001
            wp = None
        if wp is None or wp.is_empty:
            continue
        wpolys.append(wp)
        if FU.intersection(wp).area > 0.5 * wp.area:
            if not w.get("rcc"):
                w["rcc"] = True
                w["type"] = "solid"
                out["walls"] += 1
    WU = unary_union(wpolys) if wpolys else Polygon()
    cols = [c for c in arch["structure"] if c.get("type") == "column"
            and c.get("level") == lid]
    CU = []
    for c in cols:
        try:
            cp = Polygon(S.column_outline(c, 0.0)).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        CU.append(cp)
        if FU.intersection(cp).area > 0.4 * max(cp.area, 1e-6):
            c["rcc"] = True
    CUu = unary_union(CU) if CU else Polygon()
    new_cols, new_walls = [], []
    for comp in getattr(FU, "geoms", [FU]):
        if comp.geom_type != "Polygon" or comp.area < 0.02:
            continue
        if CUu.intersection(comp).area > 0.4 * comp.area:
            continue                     # a column there already (marked)
        r = comp.minimum_rotated_rectangle
        cs = list(r.exterior.coords)[:4]
        e1 = math.dist(cs[0], cs[1])
        e2 = math.dist(cs[1], cs[2])
        lo, hi = min(e1, e2), max(e1, e2)
        if lo < 0.08:
            continue
        on_wall = WU.buffer(0.03).intersection(comp).area > 0.4 * comp.area
        near_wall = WU.distance(comp) < 0.05 if not WU.is_empty else False
        if comp.area < 0.85 * r.area and hi <= 2.4 and \
                _square_cornered(comp):
            # an L / T hatched at a corner: a column of that shape (the
            # walls then stop at its faces)
            c_ = comp.centroid
            sp = comp.simplify(0.01)
            pts = [[round(x - c_.x, 4), round(y - c_.y, 4)]
                   for x, y in list(sp.exterior.coords)[:-1]]
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            new_cols.append({"type": "column", "level": lid,
                             "x": round(c_.x, 4), "y": round(c_.y, 4),
                             "shape": "poly",
                             "w": round(max(xs) - min(xs), 3),
                             "d": round(max(ys) - min(ys), 3),
                             "angle": 0.0, "anchor": "centre", "base": 0.0,
                             "pts": pts, "height": "level", "fit": False,
                             "rcc": True})
            continue
        squat = hi <= 1.5 and hi / lo <= 3.0
        if not (squat or not on_wall):
            continue                     # a long fill along a wall: the
            #                              wall marked RCC above
        if not near_wall and not on_wall:
            continue                     # loose in a room / outside: a
            #                              symbol, not structure
        if squat:                        # a column (in the wall's line too:
            #                              the wall breaks at its faces)
            a, b = (cs[0], cs[1]) if e1 >= e2 else (cs[1], cs[2])
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            c_ = r.centroid
            new_cols.append({"type": "column", "level": lid,
                             "x": round(c_.x, 4), "y": round(c_.y, 4),
                             "w": round(hi, 4), "d": round(lo, 4),
                             "angle": round(ang, 2), "shape": "rect",
                             "anchor": "centre", "base": 0.0,
                             "height": "level", "fit": False, "rcc": True})
        elif lo <= 0.6 and hi >= 0.6:               # a wall
            if e1 >= e2:
                a = ((cs[1][0] + cs[2][0]) / 2, (cs[1][1] + cs[2][1]) / 2)
                b = ((cs[3][0] + cs[0][0]) / 2, (cs[3][1] + cs[0][1]) / 2)
            else:
                a = ((cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2)
                b = ((cs[2][0] + cs[3][0]) / 2, (cs[2][1] + cs[3][1]) / 2)
            new_walls.append({"kind": "line",
                              "a": [round(a[0], 4), round(a[1], 4)],
                              "b": [round(b[0], 4), round(b[1], 4)],
                              "t": round(lo, 4), "align": "centre",
                              "side": 1, "height": "level", "base": 0.0,
                              "level": lid})
    if new_cols:
        made = M.new_elements(arch["structure"], new_cols)
        for m_ in made:
            m_["rcc"] = True
        arch["structure"] += made
        out["columns"] = len(made)
    if new_walls:
        made = M.new_walls(arch["walls"], new_walls)
        for m_ in made:
            m_["rcc"] = True
            m_["type"] = "solid"
        arch["walls"] += made
        out["new_walls"] = len(made)
    return out


def dedupe_walls(arch, lid) -> dict:
    """Two walls on one line, one over the other (a window band read as a
    wall of its own where the CAD draws the wall too): the thinner keeps
    only what runs past the thicker; its doors / windows over the thicker
    one go into it (unless that one has its own there). No wall face on
    another. {"merged", "trimmed"}."""
    out = {"merged": 0, "trimmed": 0}
    ws = [w for w in arch["walls"] if w["level"] == lid
          and w.get("kind", "line") == "line" and not w.get("rail")
          and W.why_not(w) is None and math.dist(w["a"], w["b"]) > 0.05]
    ws.sort(key=lambda w: (-float(w["t"]), -math.dist(w["a"], w["b"])))
    gone = set()
    new_walls, new_ops = [], []
    for i, H in enumerate(ws):
        if H["id"] in gone:
            continue
        a, b = H["a"], H["b"]
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-u[1], u[0])
        th = float(H["t"])
        for T in ws[i + 1:]:
            if T["id"] in gone or T is H:
                continue
            ta, tb = T["a"], T["b"]
            Lt = math.dist(ta, tb)
            ut = ((tb[0] - ta[0]) / Lt, (tb[1] - ta[1]) / Lt)
            if abs(u[0] * ut[1] - u[1] * ut[0]) > 0.05:
                continue                          # not parallel (±3°)
            oa = (ta[0] - a[0]) * n[0] + (ta[1] - a[1]) * n[1]
            ob = (tb[0] - a[0]) * n[0] + (tb[1] - a[1]) * n[1]
            if max(abs(oa), abs(ob)) > (th + float(T["t"])) / 2 - 0.02:
                continue                          # side by side, apart
            s0 = (ta[0] - a[0]) * u[0] + (ta[1] - a[1]) * u[1]
            s1 = (tb[0] - a[0]) * u[0] + (tb[1] - a[1]) * u[1]
            lo, hi = min(s0, s1), max(s0, s1)
            ov = min(hi, L) - max(lo, 0.0)
            if ov < 0.2:
                continue
            # the thin wall's openings over the host: into the host
            hops = [o for o in arch["openings"] if o["wall"] == H["id"]]
            for o in [o for o in arch["openings"] if o["wall"] == T["id"]]:
                c = (ta[0] + ut[0] * float(o["pos"]),
                     ta[1] + ut[1] * float(o["pos"]))
                sc = (c[0] - a[0]) * u[0] + (c[1] - a[1]) * u[1]
                if not 0.0 <= sc <= L:
                    continue
                o["_drop"] = True
                half = float(o["w"]) / 2
                if sc - half < 0.05 or sc + half > L - 0.05:
                    continue
                if any(abs(float(h["pos"]) - sc) < (float(h["w"]) + 2 * half)
                       / 2 - 0.05 for h in hops):
                    continue                     # the host has its own
                new_ops.append(dict(o, wall=H["id"], pos=round(sc, 4)))
            arch["openings"] = [o for o in arch["openings"]
                                if not o.pop("_drop", False)]
            # what runs past the host: kept as its own wall(s)
            rest = []
            for p0, p1 in ((lo, max(lo, min(hi, 0.0))),
                           (min(hi, max(lo, L)), hi)):
                if p1 - p0 >= 0.3:
                    rest.append((p0, p1))
            gone.add(T["id"])
            out["merged"] += 1
            for p0, p1 in rest:
                q0 = (a[0] + u[0] * p0 + n[0] * (oa + ob) / 2,
                      a[1] + u[1] * p0 + n[1] * (oa + ob) / 2)
                q1 = (a[0] + u[0] * p1 + n[0] * (oa + ob) / 2,
                      a[1] + u[1] * p1 + n[1] * (oa + ob) / 2)
                rec = {k: v for k, v in T.items()
                       if k not in ("id", "name", "a", "b")}
                rec["a"] = [round(q0[0], 4), round(q0[1], 4)]
                rec["b"] = [round(q1[0], 4), round(q1[1], 4)]
                nw = M.new_walls(arch["walls"] + new_walls, [rec])[0]
                new_walls.append(nw)
                # its openings there move with it
                for o in [o for o in arch["openings"]
                          if o["wall"] == T["id"]]:
                    c = (ta[0] + ut[0] * float(o["pos"]),
                         ta[1] + ut[1] * float(o["pos"]))
                    sc = (c[0] - a[0]) * u[0] + (c[1] - a[1]) * u[1]
                    if p0 <= sc <= p1:
                        o["wall"] = nw["id"]
                        o["pos"] = round(sc - p0, 4)
                out["trimmed"] += 1
    if gone:
        arch["walls"] = [w for w in arch["walls"] if w["id"] not in gone]
        arch["openings"] = [o for o in arch["openings"]
                            if o["wall"] not in gone]
    arch["walls"] += new_walls
    if new_ops:
        arch["openings"] += M.new_openings(arch["openings"], new_ops)
    return out


def walls_at_columns(arch, lid) -> dict:
    """No wall running on through a column: a wall the CAD draws through a
    column is broken at the column's faces (its pieces either side kept,
    a door / window staying with the piece it stands in, one inside the
    column left out); then the wall ends left short of / past one another
    at a corner are met cleanly. {"broken", "pieces", "joined"}."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    out = {"broken": 0, "pieces": 0, "joined": 0}
    cols = []
    for c in arch["structure"]:
        if c.get("type") != "column" or c.get("level") != lid:
            continue
        try:
            g = Polygon(S.column_outline(c, 0.0)).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if not g.is_empty and g.area > 0.01:
            cols.append(g)
    if cols:
        CU = unary_union(cols)
        keep, add, remap = [], [], {}
        for w in arch["walls"]:
            if w.get("level") != lid or w.get("rail") or \
                    w.get("kind", "line") != "line" or w.get("arcade"):
                keep.append(w)
                continue
            L = LineString([tuple(w["a"]), tuple(w["b"])])
            if L.length < 0.2 or CU.intersection(L).length < 0.05:
                keep.append(w)
                continue
            rest = L.difference(CU.buffer(0.002))
            parts = [q for q in getattr(rest, "geoms", [rest])
                     if q.geom_type == "LineString" and q.length >= 0.15]
            if len(parts) == 1 and parts[0].length > L.length - 0.02:
                keep.append(w)
                continue
            out["broken"] += 1
            ux = (w["b"][0] - w["a"][0]) / L.length
            uy = (w["b"][1] - w["a"][1]) / L.length
            pieces = []
            for q in parts:
                c0, c1 = q.coords[0], q.coords[-1]
                s0 = (c0[0] - w["a"][0]) * ux + (c0[1] - w["a"][1]) * uy
                s1 = (c1[0] - w["a"][0]) * ux + (c1[1] - w["a"][1]) * uy
                if s1 < s0:
                    c0, c1, s0, s1 = c1, c0, s1, s0
                pieces.append((s0, s1, c0, c1))
            pieces.sort()
            for k, (s0, s1, c0, c1) in enumerate(pieces):
                rec = dict(w, a=[round(c0[0], 4), round(c0[1], 4)],
                           b=[round(c1[0], 4), round(c1[1], 4)])
                if k == 0:
                    rec["id"] = w["id"]          # the first keeps its id
                    keep.append(rec)
                else:
                    rec.pop("id", None)
                    add.append(rec)
                remap.setdefault(w["id"], []).append((s0, s1, rec))
                out["pieces"] += 1
        made = M.new_walls(keep + add, [dict(r, name=None) for r in add]) \
            if add else []
        for r_, m_ in zip(add, made):
            r_.update(id=m_["id"], name=m_["name"])
        arch["walls"] = keep + add
        if remap:
            ops = []
            for o in arch["openings"]:
                ps = remap.get(o["wall"])
                if not ps:
                    ops.append(o)
                    continue
                pos, half = float(o["pos"]), float(o["w"]) / 2
                hit = next(((s0, s1, r_) for s0, s1, r_ in ps
                            if s0 - 0.03 <= pos - half and
                            pos + half <= s1 + 0.03), None)
                if hit is not None:
                    o["wall"], o["pos"] = hit[2]["id"], round(pos - hit[0], 4)
                    ops.append(o)
                    continue
                # across the column (a window band the CAD runs past it):
                # a window in each piece it overlaps, up to the column faces
                first = True
                for s0, s1, r_ in ps:
                    lo_, hi_ = max(pos - half, s0 + 0.02), min(pos + half,
                                                                s1 - 0.02)
                    if hi_ - lo_ < 0.3:
                        continue
                    o2 = dict(o, wall=r_["id"], w=round(hi_ - lo_, 3),
                              pos=round((lo_ + hi_) / 2 - s0, 4))
                    if first:
                        ops.append(o2)
                        first = False
                    else:
                        o2.pop("id", None)
                        o2.pop("name", None)
                        ops += M.new_openings(ops, [o2])
            arch["openings"] = ops
    ws_ = [w for w in arch["walls"] if w.get("level") == lid
           and not w.get("rail") and w.get("kind", "line") == "line"
           and W.why_not(w) is None]
    a0 = {w["id"]: tuple(w["a"]) for w in ws_}
    try:
        out["joined"] = join_wall_ends(ws_, reach=0.30)
    except Exception:  # noqa: BLE001
        pass
    # a wall end left inside a column (drawn into it, or carried there by
    # the corner joins): back to the column's face
    out["trimmed"] = 0
    if cols:
        for w in ws_:
            for end, other in (("a", "b"), ("b", "a")):
                P_ = Point(w[end])
                c_ = next((g for g in cols if g.buffer(-0.01).contains(P_)),
                          None)
                if c_ is None:
                    continue
                Lw = LineString([tuple(w[other]), tuple(w[end])])
                rest = Lw.difference(c_)
                part = next((q for q in getattr(rest, "geoms", [rest])
                             if q.geom_type == "LineString" and
                             Point(w[other]).distance(q) < 1e-6), None)
                if part is None or part.length < 0.15:
                    continue
                far = max(part.coords, key=lambda q: math.dist(q, w[other]))
                w[end] = [round(far[0], 4), round(far[1], 4)]
                out["trimmed"] += 1
    # the openings kept where they stand: a wall whose start moved shifts
    # their places along it; one now too close to an end (a window that
    # filled the bay to the column) is narrowed to fit
    byid = {w["id"]: w for w in ws_}
    keep_o, out["narrowed"] = [], 0
    for o in arch["openings"]:
        w = byid.get(o["wall"])
        if w is None:
            keep_o.append(o)
            continue
        L = math.dist(w["a"], w["b"])
        if L < 1e-6:
            continue
        ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
        oa = a0.get(w["id"], tuple(w["a"]))
        pos = float(o["pos"]) + (oa[0] - w["a"][0]) * ux + \
            (oa[1] - w["a"][1]) * uy
        half = float(o["w"]) / 2
        gap = S.END_GAP + 0.005
        if pos - half < gap or pos + half > L - gap:
            w_new = min(2 * (pos - gap), 2 * (L - gap - pos))
            if w_new < max(0.6 * float(o["w"]), 0.3):
                continue                 # no room left for it: it goes
            o["w"] = round(w_new, 3)
            out["narrowed"] += 1
        o["pos"] = round(pos, 4)
        keep_o.append(o)
    arch["openings"] = keep_o
    # an opening running into a column at its wall's end (an arch from
    # column to column): only as wide as the span clear of the columns
    if cols:
        CU_ = unary_union([g.buffer(0.005) for g in cols])
        for o in arch["openings"]:
            w = byid.get(o["wall"])
            if w is None:
                continue
            L = math.dist(w["a"], w["b"])
            if L < 0.3:
                continue
            ln = LineString([tuple(w["a"]), tuple(w["b"])])
            if not ln.intersects(CU_):
                continue
            ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
            pos, half = float(o["pos"]), float(o["w"]) / 2
            free = ln.difference(CU_)
            seg = None
            for q in getattr(free, "geoms", [free]):
                if q.geom_type != "LineString" or q.length < 0.05:
                    continue
                s_ = sorted(((c[0] - w["a"][0]) * ux + (c[1] - w["a"][1]) * uy)
                            for c in q.coords)
                if s_[0] - 1e-6 <= pos <= s_[-1] + 1e-6:
                    seg = (s_[0], s_[-1])
                    break
            if seg is None:
                continue
            lo_, hi_ = seg[0] + 0.03, seg[1] - 0.03
            if pos - half >= lo_ and pos + half <= hi_:
                continue
            nw_ = min(2 * half, hi_ - lo_)
            if nw_ < 0.3:
                continue
            o["w"] = round(nw_, 3)
            o["pos"] = round(min(max(pos, lo_ + nw_ / 2), hi_ - nw_ / 2), 4)
            out["narrowed"] += 1
    return out


def join_wall_ends(walls, reach=0.35) -> int:
    """Straight walls whose ends come within ``reach`` of each other: both
    run to where their centre lines cross (a clean mitred corner)."""
    def cross(a, b, c, d):
        r = (b[0] - a[0], b[1] - a[1])
        q = (d[0] - c[0], d[1] - c[1])
        den = r[0] * q[1] - r[1] * q[0]
        if abs(den) < 1e-9:
            return None
        t = ((c[0] - a[0]) * q[1] - (c[1] - a[1]) * q[0]) / den
        return (a[0] + r[0] * t, a[1] + r[1] * t)
    n = 0
    ws = [w for w in walls if w.get("kind", "line") == "line"]
    for i, w in enumerate(ws):
        for v in ws[i + 1:]:
            for ea in ("a", "b"):
                for eb in ("a", "b"):
                    if math.dist(w[ea], v[eb]) > reach:
                        continue
                    x = cross(w["a"], w["b"], v["a"], v["b"])
                    if x is None or math.dist(x, w[ea]) > reach or \
                            math.dist(x, v[eb]) > reach:
                        continue
                    w[ea] = [round(x[0], 4), round(x[1], 4)]
                    v[eb] = [round(x[0], 4), round(x[1], 4)]
                    n += 1
    return n


TERRACE_TILE = (0.72, 0.42, 0.30)          # terracotta tiles
DRAIN = (0.15, 0.15, 0.16)


def roof_terrace(doc, slab_id) -> dict:
    """The slab made a roof terrace floor: the level over it (a «Roof
    terrace» level when there is none), a railing on a 3" upstand along
    every free edge (corners joined, one post each), terrace tiles over
    it and rain-water outlets at its corners. {"level", "railings"} or
    {"error"}."""
    from . import slabedges as SE
    arch = doc["arch"]
    s = find_record(doc, "slab", slab_id)
    if s is None or not s.get("corners"):
        return {"error": "Select a slab"}
    lid = SE.floor_level_of(doc, s)
    if lid == s["level"] and (s.get("top") or s.get("roof")):
        ids_ = [lv["id"] for lv in arch["levels"]]
        if ids_.index(lid) != len(ids_) - 1:
            return {"error": "This slab has a floor over it already"}
        before = set(ids_)
        arch["levels"] = M.add_floor(arch["levels"], height=3.048)
        new = next(x for x in arch["levels"] if x["id"] not in before)
        new["name"] = "Roof terrace"
        arch["levels"] = M.fix_levels(arch["levels"])
        lid = new["id"]
    st = doc["settings"]
    rk = st.get("parapet_rail", "ss_bars")
    rk = rk if rk and rk != "solid" else "ss_bars"
    rh = float(st.get("rail_h", 1.0668))
    ch_ = float(st.get("terrace_curb_h", 0.3048) or CURB_H)  # the upstand
    # its edges no wall of the terrace floor stands on (the walls under
    # the slab carry it — the edge over them is open up here)
    from shapely.geometry import LineString as _LS
    from shapely.ops import unary_union as _uu
    ws_ = [w for w in arch["walls"] if w["level"] == lid]
    cover = _uu([p_.buffer(0.2) for p_ in SE.wall_polys(
        [w for w in ws_ if not w.get("rail")])] +
        [_LS([tuple(w["a"]), tuple(w["b"])]).buffer(0.2) for w in ws_
         if w.get("rail") and "a" in w]) if ws_ else None
    ring = [tuple(p_) for p_ in SE._ring_pts(SE._poly(s["corners"]))]
    edges = []
    for a, b in zip(ring, ring[1:] + ring[:1]):
        g_ = _LS([a, b])
        g_ = g_.difference(cover) if cover is not None else g_
        for q in getattr(g_, "geoms", [g_]):
            if q.geom_type == "LineString" and q.length >= 0.3:
                c_ = list(q.coords)
                edges.append((c_[0], c_[-1]))
    merged = []                          # one railing per straight run
    for a, b in edges:
        if merged:
            pa, pb = merged[-1]
            if math.dist(pb, a) < 0.02:
                u1 = (pb[0] - pa[0], pb[1] - pa[1])
                u2 = (b[0] - a[0], b[1] - a[1])
                cr = u1[0] * u2[1] - u1[1] * u2[0]
                if abs(cr) < 1e-3 * math.hypot(*u1) * math.hypot(*u2) and \
                        u1[0] * u2[0] + u1[1] * u2[1] > 0:
                    merged[-1] = (pa, b)
                    continue
        merged.append((a, b))
    edges = merged
    recs = []
    for a, b in edges:
        L = math.dist(a, b)
        if L < 0.3:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux                         # into the slab
        o_ = CURB_T / 2
        recs.append({"kind": "line",
                     "a": [round(a[0] + nx * o_, 4), round(a[1] + ny * o_, 4)],
                     "b": [round(b[0] + nx * o_, 4), round(b[1] + ny * o_, 4)],
                     "t": 0.05, "align": "centre", "side": 1,
                     "height": round(rh, 4), "base": 0.0, "level": lid,
                     "rail": rk, "curb_h": CURB_H, "curb_t": CURB_T,
                     "curb_d": round(float(s.get("t", 0.15)), 4)})
    made = M.new_walls(arch["walls"], recs)
    n0 = sum(1 for w in arch["walls"] if str(w.get("name", ""))
             .startswith("Terrace railing"))
    for k_, w_ in enumerate(made, 1):
        w_["name"] = f"Terrace railing {n0 + k_}"
        w_["rail"] = rk
    arch["walls"] += made
    if terrace_as_wall(st):
        as_parapet_walls(made, rh)
    else:
        join_rail_corners(doc, lid)
    rt = set(doc.get("roof_terraces") or [])
    rt.add(s["id"])
    doc["roof_terraces"] = sorted(rt)
    if not any(r["level"] == lid for r in arch["rooms"]):
        pts = s["corners"]
        arch["rooms"] = M._rooms(arch["rooms"] + [{
            "id": "", "level": lid, "name": "Roof terrace",
            "x": sum(p[0] for p in pts) / len(pts),
            "y": sum(p[1] for p in pts) / len(pts)}],
            {lv["id"] for lv in arch["levels"]})
    return {"level": lid, "railings": len(made)}


def roof_terrace_faces(doc, s, z_top) -> list:
    """Terrace tiles over the slab (inside its upstands, round its holes)
    and a rain-water outlet (a 6" grate) at each of its corners."""
    from . import slabedges as SE
    sp = SE._poly(s["corners"])
    if sp.is_empty:
        return []
    for h in s.get("holes") or []:
        sp = sp.difference(SE._poly(h))
    inner = sp.buffer(-(CURB_T + 0.005), join_style=2)
    out = []
    t_ = 0.025
    for g in getattr(inner, "geoms", [inner]):
        if g.geom_type != "Polygon" or g.area < 0.1:
            continue
        piece = {"outer": S._ccw(list(g.exterior.coords)[:-1]),
                 "holes": [list(reversed(S._ccw(list(r.coords)[:-1])))
                           for r in g.interiors]}
        for f in W.solid(piece, z_top, z_top + t_):
            d_ = dict(f) if isinstance(f, dict) else {"loop": f,
                                                      "holes": []}
            d_["color"] = TERRACE_TILE
            out.append(d_)
        # an outlet in each corner (inside the upstands)
        ring = list(g.exterior.coords)[:-1]
        for c in ring[::max(1, len(ring) // 4)][:4]:
            cx, cy = g.centroid.x, g.centroid.y
            L = math.hypot(cx - c[0], cy - c[1]) or 1.0
            px, py = c[0] + (cx - c[0]) / L * 0.15, c[1] + (cy - c[1]) / L * 0.15
            sq = {"outer": [(px - 0.075, py - 0.075), (px + 0.075, py - 0.075),
                            (px + 0.075, py + 0.075), (px - 0.075, py + 0.075)],
                  "holes": []}
            for f in W.solid(sq, z_top + t_, z_top + t_ + 0.004):
                d_ = dict(f) if isinstance(f, dict) else {"loop": f,
                                                          "holes": []}
                d_["color"] = DRAIN
                out.append(d_)
    return out


def join_rail_corners(doc, lid, reach=0.35) -> int:
    """The railings of level ``lid`` meeting at corners joined there: both
    run to where their lines cross, ONE post on the corner (the other
    railing's left out), handrails and upstands carried on to meet full —
    clean corners. The number of corners joined."""
    rails = [w for w in doc["arch"]["walls"] if w["level"] == lid
             and w.get("rail") and w.get("kind", "line") == "line"]
    for w in rails:
        for k_ in ("np_a", "np_b", "cj_a", "cj_b"):
            w.pop(k_, None)

    def cross(a, b, c, d):
        r = (b[0] - a[0], b[1] - a[1])
        s_ = (d[0] - c[0], d[1] - c[1])
        den = r[0] * s_[1] - r[1] * s_[0]
        if abs(den) < 1e-9 * (math.hypot(*r) * math.hypot(*s_) + 1e-12):
            return None
        t = ((c[0] - a[0]) * s_[1] - (c[1] - a[1]) * s_[0]) / den
        return (a[0] + r[0] * t, a[1] + r[1] * t)
    n = 0
    for i, w in enumerate(rails):
        for j in range(i + 1, len(rails)):
            v = rails[j]
            for ew in ("a", "b"):
                for ev in ("a", "b"):
                    p, q = tuple(w[ew]), tuple(v[ev])
                    if math.dist(p, q) > reach:
                        continue
                    x = cross(tuple(w["a"]), tuple(w["b"]), tuple(v["a"]),
                              tuple(v["b"]))
                    if x is None or math.dist(x, p) > 2 * reach:
                        x = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                        straight = True
                    else:
                        straight = False
                    w[ew] = [round(x[0], 4), round(x[1], 4)]
                    v[ev] = [round(x[0], 4), round(x[1], 4)]
                    v["np_" + ev] = True         # one post: w's
                    if not straight:
                        w["cj_" + ew] = True
                        v["cj_" + ev] = True
                    n += 1
    return n


def tidy_all_slabs(doc, lids=None) -> dict:
    """Every level's slabs (and roofs) carried out over their columns and
    their edges tidied. {level id: (columns reached, corners before,
    after)}."""
    from . import slabedges as SE
    arch = doc["arch"]
    out = {}
    for lv in arch["levels"]:
        lid = lv["id"]
        if lids is not None and lid not in lids:
            continue
        ss = [e for e in arch["structure"] if e["type"] == "slab"
              and e["level"] == lid and not e.get("zone")
              and e.get("corners")]
        if not ss:
            continue
        n0 = sum(len(e["corners"]) for e in ss)
        k = SE.extend_slabs_to_columns(doc, ss) \
            if doc["settings"].get("slab_to_columns", True) else 0
        for e in ss:
            SE.tidy_slab(e)
        for e in arch["structure"]:
            if e["type"] == "roof" and e["level"] == lid and e.get("corners"):
                SE.tidy_slab(e)
        out[lid] = (k, n0, sum(len(e["corners"]) for e in ss))
    return out


def stray_elements(doc, lid) -> list:
    """Elements of level ``lid`` that look drawn on a floor they are not
    on: on an upper floor, standing where the floor under it has no slab
    to carry them (a porch's pillars, a lower roof, the plot's walls the
    plan repeats) — [(kind, id, name, why)]."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    ids = [lv["id"] for lv in arch["levels"]]
    if lid not in ids:
        return []
    el = elevations(arch)
    order = sorted(range(len(ids)), key=lambda i: el[i])
    k = [ids[i] for i in order].index(lid)
    out = []
    if k == 0:
        return out                       # the ground carries everything
    floors = [SE._poly(s["corners"]) for s in _floor_slabs(doc, lid)
              if s.get("corners")]
    if not floors:
        return out
    support = unary_union(floors).buffer(0.3, join_style=2)
    for w in arch["walls"]:
        if w["level"] != lid or w.get("kind", "line") != "line":
            continue
        c_ = W.centre(w)
        P = LineString([c_.p0, c_.p1]).buffer(float(w["t"]) / 2,
                                               cap_style=2)
        if P.area > 0 and P.difference(support).area > 0.5 * P.area:
            out.append(("wall", w["id"], w.get("name", "wall"),
                        "no floor slab under it"))
    for e in arch["structure"]:
        if e["level"] != lid or e["type"] not in ("column", "beam", "core"):
            continue
        try:
            if e["type"] == "column":
                P = Polygon(S.column_outline(e, 0.0))
            elif e["type"] == "beam":
                P = LineString([tuple(e["a"]), tuple(e["b"])]).buffer(
                    float(e.get("w", 0.2)) / 2, cap_style=2)
            else:
                P = Polygon([tuple(q) for q in e["corners"]])
        except Exception:  # noqa: BLE001
            continue
        if P.area > 0 and P.difference(support).area > 0.5 * P.area:
            out.append((e["type"], e["id"], e.get("name", e["type"]),
                        "no floor slab under it"))
    for st in doc.get("stairs") or []:
        if st["level"] != lid:
            continue
        P = Polygon([tuple(q[:2]) for q in st["corners"]])
        if P.area > 0 and P.difference(support).area > 0.5 * P.area:
            out.append(("stair", st["id"], "Stair", "no floor slab under it"))
    return out


def opening_as(o, kind, st) -> dict:
    """The opening made a door / window / plain opening (void) with that
    type's own defaults (the import's height, sill and type — section 5):
    its width and place kept; a door as wide as a window two leaves or
    sliding by its width (the door rule)."""
    o = dict(o)
    old = o.get("kind")
    o["kind"] = kind
    for k_ in ("frame_w", "frame_d", "panel", "handle", "leaves", "head",
               "glass"):
        if old != kind:
            o.pop(k_, None)
    if kind == "door":
        o.update(h=float(st.get("door_h", 2.1336)), sill=0.0,
                 style=st.get("door_style", "hinged"))
        o.setdefault("swing", "left")
        o.setdefault("face", 1)
        door_rule(o)
        opening_types(o, st)
    elif kind == "window":
        o.update(h=float(st.get("win_h", 1.2)), sill=float(st.get("sill", 0.9)),
                 style=st.get("win_style", "sliding"))
    else:                                   # a plain opening, door high
        o.update(h=float(st.get("door_h", 2.1336)), sill=0.0, style="")
    return o


def revise_empty_openings(doc, lids=None) -> dict:
    """The glass sliding doors put in openings the CAD shows empty (no
    swing, no glazing, no door block over them) made plain openings — no
    door, a doorway to the door height. {level id: n changed}."""
    from . import detect
    arch = doc["arch"]
    st = doc["settings"]
    out = {}
    walls = {w["id"]: w for w in arch["walls"]}
    for lid, how in (doc.get("imports") or {}).items():
        if lids is not None and lid not in lids:
            continue
        if not isinstance(how, dict) or not how.get("file") or \
                lid not in {lv["id"] for lv in arch["levels"]}:
            continue
        raw = cadread.read(how["file"], how.get("unit"))
        drawing = cadread.crop(raw, how.get("region"))
        base = cadread.base_point(drawing, how.get("base", "origin"),
                                  (how.get("bx", 0.0), how.get("by", 0.0)))
        pl = cadread.place(drawing, base,
                           (how.get("ix", 0.0), how.get("iy", 0.0)),
                           how.get("rot", 0.0))
        P, _found = layer_patterns(drawing, how, st)
        blocks = []
        for ins in pl.get("inserts", ()):
            k_ = detect.block_kind(ins["name"])
            if k_ is None and (_match(ins["layer"], P["doors"]) or
                               _match(ins["layer"], P["windows"])):
                k_ = "door"
            if k_ is not None and ins.get("corners"):
                blocks.append(ins["corners"])
        n = 0
        for o in arch["openings"]:
            w = walls.get(o["wall"])
            if w is None or w["level"] != lid or o["kind"] != "door" or \
                    o.get("style") != "sliding" or \
                    w.get("kind", "line") != "line":
                continue
            seg = W.centre(w)
            mid = (seg.p0[0] + seg.u[0] * o["pos"],
                   seg.p0[1] + seg.u[1] * o["pos"])
            if walldetect._gap_kind(mid, float(o["w"]), seg.u, float(w["t"]),
                                    pl["segs"]) is not None:
                continue
            half = float(o["w"]) / 2 + 0.1
            if any(min(abs((c[0] - mid[0]) * seg.u[0] +
                           (c[1] - mid[1]) * seg.u[1]) for c in cs) < half
                   and min(abs(-(c[0] - mid[0]) * seg.u[1] +
                               (c[1] - mid[1]) * seg.u[0]) for c in cs) < 1.5
                   for cs in blocks):
                continue                     # a door block stands over it
            o.update(kind="void", style="", sill=0.0,
                     h=float(st.get("door_h", 2.1336)))
            for k_ in ("leaves", "frame", "glass", "head"):
                o.pop(k_, None)
            n += 1
        out[lid] = n
    return out


HIDDEN_SKIP = re.compile(r"CEIL|GRID|GIRD|AXIS|FURN|PIPE|DIM|TEXT|SECTION|"
                         r"HATCH|SPLIT|FIXT|EQUIP|TREE|LANDSC|SYMB|ARROW|"
                         r"LIGHT|ELEC|PLUMB|SANIT|SEWER|PLOT|SITE|BOUND|"
                         r"SETBACK|ROAD|STAIR|STEP", re.I)
HI_SILL, HI_H = 1.8288, 0.6096          # a high window: 6'-0" sill, 2'-0"


def apply_hidden_lines_new(doc) -> dict:
    """The hidden-line rules for the openings not read yet (new from an
    import, a re-import…): each opening read once — an edit by hand
    stays. {level id: counts}."""
    arch = doc["arch"]
    walls = {w["id"]: w["level"] for w in arch["walls"]}
    lids = sorted({walls.get(o["wall"]) for o in arch["openings"]
                   if not o.get("hl") and walls.get(o["wall"])})
    if not lids:
        return {}
    out = apply_hidden_lines(doc, lids, only_new=True)
    for o in arch["openings"]:
        if walls.get(o["wall"]) in lids:
            o["hl"] = 1
    return out


def apply_hidden_lines(doc, lids=None, only_new=False) -> dict:
    """What the plan's hidden (dashed) lines say, as drafted:

    - across an opening in an inner wall, with no door drawn: a plain
      opening (no door); crossing it (an X): an arch, no door;
    - in a window's opening: a high window (a ventilator over 6'-0");
    - outside an outer wall by a window: its sun shade (chajja), as deep
      as drawn (a longer run: the slab's projection — the slab follows it
      already);
    - in the stair: the flight going up (left as drawn);
    - crossing in open floor: the slab cut there (made at import).

    {level id: {"voids": n, "arches": n, "high": n, "shades": n}}."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union

    from . import detect
    from . import slabedges as SE
    from .engine import walldetect
    arch = doc["arch"]
    st = doc["settings"]
    out = {}
    walls = {w["id"]: w for w in arch["walls"]}
    for lid, how in (doc.get("imports") or {}).items():
        if lids is not None and lid not in lids:
            continue
        if not isinstance(how, dict) or not how.get("file") or \
                lid not in {lv["id"] for lv in arch["levels"]}:
            continue
        try:
            raw = cadread.read(how["file"], how.get("unit"))
        except Exception:  # noqa: BLE001
            continue
        drawing = cadread.crop(raw, how.get("region"))
        base = cadread.base_point(drawing, how.get("base", "origin"),
                                  (how.get("bx", 0.0), how.get("by", 0.0)))
        pl = cadread.place(drawing, base,
                           (how.get("ix", 0.0), how.get("iy", 0.0)),
                           how.get("rot", 0.0))
        dsh = pl.get("dashed") or []
        if len(dsh) != len(pl["segs"]) or not any(dsh):
            out[lid] = {}
            continue
        P, _found = layer_patterns(drawing, how, st)
        lay = pl["layers"]
        glz = [LineString([(s_[0], s_[1]), (s_[2], s_[3])])
               for s_, d_ in zip(pl["segs"], dsh)
               if not d_ and _match(lay[s_[4]], P["windows"])
               and math.hypot(s_[2] - s_[0], s_[3] - s_[1]) > 0.05]
        hid = [LineString([(s_[0], s_[1]), (s_[2], s_[3])])
               for s_, d_ in zip(pl["segs"], dsh)
               if d_ and not HIDDEN_SKIP.search(lay[s_[4]])
               and not _match(lay[s_[4]], P["stairs"])
               and math.hypot(s_[2] - s_[0], s_[3] - s_[1]) > 0.05]
        if not hid:
            out[lid] = {}
            continue
        blocks = []
        for ins in pl.get("inserts", ()):
            k_ = detect.block_kind(ins["name"])
            if k_ is None and _match(ins["layer"], P["doors"]):
                k_ = "door"
            if k_ == "door" and ins.get("corners"):
                blocks.append(ins["corners"])
        mine = [w for w in arch["walls"] if w["level"] == lid]
        fp = SE._footprint(mine)
        wp = unary_union(SE.wall_polys(mine)) if mine else None
        n = {"voids": 0, "arches": 0, "high": 0, "shades": 0}
        for o in arch["openings"]:
            w = walls.get(o["wall"])
            if w is None or w["level"] != lid or \
                    w.get("kind", "line") != "line":
                continue
            if only_new and o.get("hl"):
                continue
            seg = W.centre(w)
            u = seg.u
            nv = (-u[1], u[0])
            t2 = float(w["t"]) / 2
            mid = (seg.p0[0] + u[0] * o["pos"], seg.p0[1] + u[1] * o["pos"])
            hw = float(o["w"]) / 2
            span = LineString([(mid[0] - u[0] * hw, mid[1] - u[1] * hw),
                               (mid[0] + u[0] * hw, mid[1] + u[1] * hw)])
            band = span.buffer(t2 + 0.05, cap_style=2)
            par = cross = 0.0
            for ln in hid:
                if not ln.intersects(band):
                    continue
                piece = ln.intersection(band)
                (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
                L_ = math.hypot(x1 - x0, y1 - y0)
                c_ = abs((x1 - x0) * u[0] + (y1 - y0) * u[1]) / L_
                if c_ > 0.95:
                    par += piece.length
                elif 0.2 < c_ < 0.9:
                    cross += piece.length
            glass = 0.0                   # the window's glazing drawn
            for ln in glz:
                if not ln.intersects(band):
                    continue
                (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
                L_ = math.hypot(x1 - x0, y1 - y0)
                if abs((x1 - x0) * u[0] + (y1 - y0) * u[1]) / L_ > 0.95:
                    glass = max(glass, ln.intersection(band).length)
            hasglass = glass >= 0.5 * float(o["w"])
            # the inside / outside of the wall
            if fp is not None:
                a_in = fp.contains(Point(mid[0] + nv[0] * (t2 + 0.4),
                                         mid[1] + nv[1] * (t2 + 0.4)))
                b_in = fp.contains(Point(mid[0] - nv[0] * (t2 + 0.4),
                                         mid[1] - nv[1] * (t2 + 0.4)))
            else:
                a_in = b_in = True
            outer = a_in != b_in
            if o["kind"] == "window" and hasglass and \
                    par >= 0.5 * float(o["w"]) and \
                    float(o.get("sill", 0.0) or 0.0) < HI_SILL - 0.05:
                o.update(sill=HI_SILL, h=HI_H)      # a ventilator, up high
                n["high"] += 1
            elif o["kind"] == "window" and not hasglass and \
                    (par >= 0.5 * float(o["w"]) or
                     cross >= 0.5 * float(o["w"])):
                # no glazing, only the hidden line: an opening (no window)
                o.update(kind="void", style="", sill=0.0,
                         h=float(st.get("door_h", 2.1336)))
                for k_ in ("leaves", "frame", "glass", "shade_d"):
                    o.pop(k_, None)
                if cross >= 0.5 * float(o["w"]):
                    o["head"] = "arch"
                    o["arch"] = st.get("hl_arch_style", "pointed") or \
                        "pointed"
                    n["arches"] += 1
                else:
                    o.pop("head", None)
                    n["voids"] += 1
            elif o["kind"] in ("door", "void") and (par or cross):
                empty = walldetect._gap_kind(
                    mid, float(o["w"]), u, float(w["t"]),
                    pl["segs"]) is None and not any(
                    min(abs((c[0] - mid[0]) * u[0] + (c[1] - mid[1]) * u[1])
                        for c in cs) < hw + 0.1 and
                    min(abs(-(c[0] - mid[0]) * u[1] + (c[1] - mid[1]) * u[0])
                        for c in cs) < 1.5 for cs in blocks)
                if empty and (o["kind"] == "void" or
                              o.get("style") in ("sliding", "", None)):
                    arched = cross >= 0.5 * float(o["w"])
                    o.update(kind="void", style="", sill=0.0,
                             h=float(st.get("door_h", 2.1336)))
                    for k_ in ("leaves", "frame", "glass"):
                        o.pop(k_, None)
                    if arched:
                        o["head"] = "arch"
                        o["arch"] = st.get("hl_arch_style", "pointed") \
                            or "pointed"
                        n["arches"] += 1
                    else:
                        o.pop("head", None)
                        n["voids"] += 1
            # a sun shade drawn over an outer window
            if o["kind"] == "window" and outer:
                side = 1 if not a_in else -1     # toward the outside
                best = None
                for ln in hid:
                    if wp is not None and ln.intersects(wp):
                        continue
                    (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
                    L_ = math.hypot(x1 - x0, y1 - y0)
                    if L_ > float(o["w"]) + 1.6 or abs(
                            (x1 - x0) * u[0] + (y1 - y0) * u[1]) / L_ < 0.95:
                        continue
                    m_ = ln.interpolate(0.5, normalized=True)
                    off = ((m_.x - mid[0]) * nv[0] + (m_.y - mid[1]) * nv[1]) \
                        * side - t2
                    along = abs((m_.x - mid[0]) * u[0] + (m_.y - mid[1]) * u[1])
                    if 0.1 <= off <= 1.5 and along <= hw + 0.3 and \
                            L_ >= 0.6 * float(o["w"]):
                        if best is None or off < best:
                            best = off
                if best is not None:
                    o["shade_d"] = round(best, 4)
                    n["shades"] += 1
        out[lid] = n
    return out


def doors_at_windows(doc, lid, pl, P) -> int:
    """A door put where the plan draws a window (the shower's glass door,
    swinging inside a bathroom, taken for the door of the wall next to
    it): the window lines in the wall at that place win — the opening made
    a window as long as they run. How many."""
    from shapely.geometry import LineString
    arch = doc["arch"]
    lay = pl["layers"]
    byid = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    wins = [o for o in arch["openings"] if o["kind"] == "window"
            and o["wall"] in byid]
    sill_ = float(wins[0].get("sill", 1.0)) if wins else 1.0
    h_ = float(wins[0].get("h", 1.2)) if wins else 1.2
    wsegs = [s_ for s_ in pl["segs"] if _match(lay[s_[4]], P["windows"])
             and not re.search(r"GLASS|SHOWER", lay[s_[4]], re.I)]
    dsegs = [s_ for s_ in pl["segs"] if _match(lay[s_[4]], P["doors"])]
    n = 0
    for o in arch["openings"]:
        w = byid.get(o["wall"])
        if o["kind"] != "door" or w is None or \
                w.get("kind", "line") != "line":
            continue
        seg = W.centre(w)
        u = seg.u
        t2 = float(w["t"]) / 2 + 0.03
        p0 = float(o["pos"]) - float(o["w"]) / 2
        p1 = float(o["pos"]) + float(o["w"]) / 2

        def local(q):
            dx, dy = q[0] - seg.p0[0], q[1] - seg.p0[1]
            return dx * u[0] + dy * u[1], -dx * u[1] + dy * u[0]
        runs = []
        for s_ in wsegs:
            a, b = local((s_[0], s_[1])), local((s_[2], s_[3]))
            if abs(a[1]) > t2 or abs(b[1]) > t2 or \
                    abs(a[1] - b[1]) > 0.02:
                continue                     # not along, in the wall
            lo, hi = min(a[0], b[0]), max(a[0], b[0])
            if hi > p0 - 0.6 and lo < p1 + 0.6 and hi - lo > 0.2:
                runs.append((lo, hi))
        if len(runs) < 2:
            continue
        lo = min(r[0] for r in runs)
        hi = max(r[1] for r in runs)
        cover = max(0.0, min(hi, p1) - max(lo, p0))
        if cover < 0.5 * (p1 - p0):
            continue
        # the door's own lines at the wall (a leaf, a jamb): it is a door
        jamb = 0
        span = LineString([(seg.p0[0] + u[0] * p0, seg.p0[1] + u[1] * p0),
                           (seg.p0[0] + u[0] * p1, seg.p0[1] + u[1] * p1)])
        band = span.buffer(t2 + 0.1)
        for s_ in dsegs:
            if band.intersects(LineString([(s_[0], s_[1]), (s_[2], s_[3])])):
                jamb += 1
        if jamb >= 3:
            continue
        o["kind"] = "window"
        o["pos"] = round((lo + hi) / 2, 4)
        o["w"] = round(max(hi - lo, 0.3), 4)
        o["sill"] = round(sill_ if o["w"] > 0.9 else max(sill_, 1.5), 4)
        o["h"] = round(h_ if o["w"] > 0.9 else min(h_, 0.6), 4)
        o.pop("swing", None)
        o["style"] = ""
        n += 1
    return n


def single_line_walls(doc, lid, pl, P, t=0.1143) -> int:
    """A partition the plan draws as ONE line on the wall layer (two
    rooms back to back, a dressing room's side): a 4½" wall on it where
    it runs 1.5 m or more clear of the other walls, from a wall / column
    to a wall / column. How many."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    lay = pl["layers"]
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and W.why_not(w) is None]
    if not walls:
        return 0
    WU = unary_union(SE.wall_polys(walls))
    cols = [LineString([(s_[0], s_[1]), (s_[2], s_[3])]) for s_ in pl["segs"]
            if _match(lay[s_[4]], P["columns"])]
    CU = unary_union(cols).buffer(0.05) if cols else None
    stops = unary_union([WU] + ([CU] if CU is not None else []))
    lines = [LineString([(s_[0], s_[1]), (s_[2], s_[3])])
             for s_ in pl["segs"] if _match(lay[s_[4]], P["walls"])]
    lines = [L_ for L_ in lines if L_.length >= 1.0]
    recs = []
    from shapely.geometry import Point as _Pq
    for L_ in lines:
        free = L_.difference(WU.buffer(0.06))
        for g in getattr(free, "geoms", [free]):
            if g.geom_type != "LineString" or g.length < 1.0:
                continue
            a, b = g.coords[0], g.coords[-1]
            da, db = stops.distance(_Pq(a)), stops.distance(_Pq(b))
            if da > 0.6 or db > 0.6:
                continue                 # loose: not a partition
            if g.length < 1.5 and max(da, db) > 0.12:
                continue                 # short: wall to wall only
            # a wall's face drawn alone beside its partner: not one
            par = [m for m in lines if m is not L_ and m.length > 0.5
                   and abs(((m.coords[1][0] - m.coords[0][0]) *
                            (b[1] - a[1]) - (m.coords[1][1] - m.coords[0][1])
                            * (b[0] - a[0]))) < 0.08 * m.length * g.length
                   and m.distance(g) < 0.5 and
                   m.intersection(g.buffer(0.5, cap_style=2)).length >
                   0.5 * g.length]
            t_ = t
            if par:
                # its partner face: a wall of that thickness the pairing
                # missed (broken where another wall crosses it)
                m = min(par, key=lambda q: q.distance(g))
                gm = g.interpolate(0.5, normalized=True)
                dd = m.distance(gm)
                if not 0.07 <= dd <= 0.46:
                    continue
                q_ = m.interpolate(m.project(gm))
                ox, oy = (q_.x - gm.x) / 2, (q_.y - gm.y) / 2
                a = (a[0] + ox, a[1] + oy)
                b = (b[0] + ox, b[1] + oy)
                t_ = round(dd, 3)
            cl_ = LineString([a, b])
            if any(LineString([r_["a"], r_["b"]]).buffer(0.05).contains(
                    cl_.interpolate(0.5, normalized=True)) for r_ in recs):
                continue                 # (made from its partner already)
            recs.append({"kind": "line",
                         "a": [round(a[0], 4), round(a[1], 4)],
                         "b": [round(b[0], 4), round(b[1], 4)],
                         "t": t_, "align": "centre", "side": 1,
                         "height": "level", "base": 0.0, "level": lid})
    if not recs:
        return 0
    made = M.new_walls(arch["walls"], recs)
    arch["walls"] += made
    return len(made)


def wall_masses(doc, lid, pl, P) -> int:
    """Solid pieces of wall drawn as a closed outline on the wall layer
    (a thick pier, the wedge where two walls meet at an angle, a corridor
    wall's jog) that no wall or column fills: each made a column of that
    shape, so the wall runs on unbroken as drawn. How many."""
    from shapely.geometry import LineString, Point
    from shapely.ops import polygonize, unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    lay = pl["layers"]
    ls = [LineString([(s_[0], s_[1]), (s_[2], s_[3])]) for s_ in pl["segs"]
          if _match(lay[s_[4]], P["walls"])
          and math.hypot(s_[2] - s_[0], s_[3] - s_[1]) > 0.01]
    if len(ls) < 3:
        return 0
    try:
        faces = list(polygonize(unary_union(ls)))
    except Exception:  # noqa: BLE001
        return 0
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and W.why_not(w) is None]
    solids = []
    try:
        solids += list(SE.wall_polys(walls))
    except Exception:  # noqa: BLE001
        pass
    for c in arch["structure"]:
        if c.get("type") == "column" and c.get("level") == lid:
            try:
                from shapely.geometry import Polygon as _Pg
                solids.append(_Pg(S.column_outline(c, 0.0)).buffer(0))
            except Exception:  # noqa: BLE001
                pass
    SU = unary_union(solids) if solids else None
    texts = [Point(t["x"], t["y"]) for t in pl.get("texts") or ()]
    # door swings / leaves: a face they cross is a doorway, not a mass
    dl = [LineString([(s_[0], s_[1]), (s_[2], s_[3])]) for s_ in pl["segs"]
          if _match(lay[s_[4]], P["doors"])]
    DU = unary_union(dl) if dl else None
    recs = []
    for g in faces:
        if not 0.08 <= g.area <= 3.0:
            continue
        r = g.minimum_rotated_rectangle
        cs = list(r.exterior.coords)[:4]
        e1, e2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        lo, hi = min(e1, e2), max(e1, e2)
        if lo > 1.0 or hi > 4.0 or lo < 0.1:
            continue                    # a room / closet, or a wall's strip
        if SU is not None and SU.intersection(g).area > 0.3 * g.area:
            continue                    # a wall / column there already
        if any(g.contains(t) for t in texts):
            continue                    # a duct, a shaft (named)
        if DU is not None and DU.intersection(g).length > 0.05:
            continue
        # a mass touches the walls (it carries them on): two sides at least
        if SU is not None and g.buffer(0.05).intersection(SU).area < \
                0.04 * g.length:
            continue
        c_ = g.centroid
        sp = g.simplify(0.005)
        pts = [[round(x - c_.x, 4), round(y - c_.y, 4)]
               for x, y in list(sp.exterior.coords)[:-1]]
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        recs.append({"type": "column", "level": lid,
                     "x": round(c_.x, 4), "y": round(c_.y, 4),
                     "shape": "poly", "w": round(max(xs) - min(xs), 3),
                     "d": round(max(ys) - min(ys), 3), "angle": 0.0,
                     "anchor": "centre", "base": 0.0, "pts": pts,
                     "height": "level", "fit": False, "mass": True})
    if not recs:
        return 0
    arch["structure"] += M.new_elements(arch["structure"], recs)
    return len(recs)


def arches_between(doc, lid, pl, P) -> int:
    """An X in hidden (dashed) lines drawn between two columns, or a column
    and a wall end, with no wall across: an arch there (the plan's way to
    show one) — a wall from face to face holding an arched opening, the
    arch shape set (Islamic, pointed, by default). How many."""
    from shapely.geometry import LineString, MultiPoint, Point, Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    arch = doc["arch"]
    st = doc["settings"]
    dsh = pl.get("dashed") or []
    if len(dsh) != len(pl["segs"]) or not any(dsh):
        return 0
    lay = pl["layers"]
    hid = [LineString([(s_[0], s_[1]), (s_[2], s_[3])])
           for s_, d_ in zip(pl["segs"], dsh)
           if d_ and not HIDDEN_SKIP.search(lay[s_[4]])
           and not _match(lay[s_[4]], P["stairs"])
           and 0.6 < math.hypot(s_[2] - s_[0], s_[3] - s_[1]) < 9.0]
    if len(hid) < 2:
        return 0
    cols = []
    for c in arch["structure"]:
        if c.get("type") == "column" and c.get("level") == lid:
            try:
                cols.append(Polygon(S.column_outline(c, 0.0)).buffer(0))
            except Exception:  # noqa: BLE001
                pass
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and w.get("kind", "line") == "line"
             and W.why_not(w) is None]
    wps = SE.wall_polys(walls) if walls else []
    WU = unary_union(wps) if wps else Polygon()
    solids = unary_union(cols + list(wps)) if cols or wps else Polygon()
    if solids.is_empty:
        return 0
    used = set()
    recs, spans = [], []
    for i, a in enumerate(hid):
        if i in used:
            continue
        for j in range(i + 1, len(hid)):
            if j in used:
                continue
            b = hid[j]
            x = a.intersection(b)
            if x.is_empty or x.geom_type != "Point":
                continue
            # the two diagonals of one box: crossing near both middles
            if abs(a.project(x) / a.length - 0.5) > 0.2 or \
                    abs(b.project(x) / b.length - 0.5) > 0.2:
                continue
            box = MultiPoint(list(a.coords) + list(b.coords)) \
                .minimum_rotated_rectangle
            if box.geom_type != "Polygon":
                continue
            cs = list(box.exterior.coords)[:4]
            e1, e2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
            lo, hi = min(e1, e2), max(e1, e2)
            if lo < 0.08 or hi < 0.6:
                continue
            # a duct / shaft drawn as a crossed box (wider than a wall, or
            # named by its text): a slab opening, not an arch
            if lo > 0.5 or any(
                    box.buffer(0.3).contains(Point(t_["x"], t_["y"])) and
                    re.search(r"DUCT|SHAFT|VOID|O\.?T\.?S|SKY|LIFT|P\.?D\b",
                              str(t_.get("text", "")), re.I)
                    for t_ in pl.get("texts") or ()):
                used |= {i, j}
                continue
            if not WU.is_empty and box.intersection(WU).area > 0.3 * box.area:
                # a wall already across (a gap closed up, a plain opening
                # in it): its opening there arched
                hit_ = False
                for w_ in walls:
                    wl_ = LineString([w_["a"], w_["b"]])
                    if wl_.length < 0.3 or box.buffer(0.05).intersection(
                            wl_).length < 0.6 * min(wl_.length, hi):
                        continue
                    for o_ in arch["openings"]:
                        if o_["wall"] != w_["id"] or o_["kind"] != "void" \
                                or o_.get("head") == "arch":
                            continue
                        o_["head"] = "arch"
                        o_["arch"] = st.get("hl_arch_style", "pointed") \
                            or "pointed"
                        o_["h"] = round(max(float(o_["h"]), 0.5 * float(
                            o_["w"]) + 1.8), 3)
                        hit_ = True
                    if hit_ and w_.get("filler"):
                        w_["t"] = round(max(float(w_["t"]),
                                            max(min(lo, 0.6), 0.23)), 4)
                if hit_:
                    used |= {i, j}
                continue
            # the span's two ends (the short sides) at solids
            if e1 >= e2:
                m0 = ((cs[1][0] + cs[2][0]) / 2, (cs[1][1] + cs[2][1]) / 2)
                m1 = ((cs[3][0] + cs[0][0]) / 2, (cs[3][1] + cs[0][1]) / 2)
            else:
                m0 = ((cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2)
                m1 = ((cs[2][0] + cs[3][0]) / 2, (cs[2][1] + cs[3][1]) / 2)
            if solids.distance(Point(m0)) > 0.3 or \
                    solids.distance(Point(m1)) > 0.3:
                continue
            # face to face: the span clear of the columns / walls it joins
            run = LineString([m0, m1]).difference(solids.buffer(0.002))
            run = max((q for q in getattr(run, "geoms", [run])
                       if q.geom_type == "LineString"),
                      key=lambda q: q.length, default=None)
            if run is None or run.length < 0.5:
                continue
            m0, m1 = run.coords[0], run.coords[-1]
            hi = run.length
            used |= {i, j}
            t_ = max(min(lo, 0.6), 0.23)
            recs.append({"kind": "line", "a": [round(m0[0], 4), round(m0[1], 4)],
                         "b": [round(m1[0], 4), round(m1[1], 4)],
                         "t": round(t_, 4), "align": "centre", "side": 1,
                         "height": "level", "base": 0.0, "level": lid})
            spans.append(hi)
            break
    if not recs:
        return 0
    made = M.new_walls(arch["walls"], recs)
    arch["walls"] += made
    ops = []
    style = st.get("hl_arch_style", "pointed") or "pointed"
    door_h = float(st.get("door_h", 2.1336))
    for w_, L_ in zip(made, spans):
        w_["name"] = "Arch " + w_["name"].split()[-1]
        wd = round(max(L_ - 2 * 0.11, 0.3), 3)
        ops.append({"kind": "void", "wall": w_["id"], "pos": round(L_ / 2, 4),
                    "w": wd, "h": round(max(door_h, 0.5 * wd + 1.8), 3),
                    "sill": 0.0, "swing": "left", "face": 1, "style": "",
                    "head": "arch", "arch": style})
    arch["openings"] += M.new_openings(arch["openings"], ops)
    return len(made)


def redetect_columns(doc, lids=None) -> dict:
    """The columns of levels ``lids`` (all imported ones by default) read
    again from their CAD plans — nothing else on the level changes (walls,
    openings, edits kept). {level id: (before, after)}."""
    arch = doc["arch"]
    st = doc["settings"]
    out = {}
    for lid, how in (doc.get("imports") or {}).items():
        if lids is not None and lid not in lids:
            continue
        if not isinstance(how, dict) or not how.get("file") or \
                lid not in {lv["id"] for lv in arch["levels"]}:
            continue
        raw = cadread.read(how["file"], how.get("unit"))
        drawing = cadread.crop(raw, how.get("region"))
        base = cadread.base_point(drawing, how.get("base", "origin"),
                                  (how.get("bx", 0.0), how.get("by", 0.0)))
        pl = cadread.place(drawing, base,
                           (how.get("ix", 0.0), how.get("iy", 0.0)),
                           how.get("rot", 0.0))
        P, _found = layer_patterns(drawing, how, st)
        pats = column_layers_for(P["columns"], level_floor_no(arch, lid))
        cols = columns_from(pl, pats, pl["layers"])
        old = [e for e in arch["structure"]
               if e["type"] == "column" and e["level"] == lid]
        keep = {k: old[0][k] for k in ("base", "height") if old and k in old[0]}
        seen, recs = set(), []
        for c in cols:
            key = (round(c["x"], 2), round(c["y"], 2))
            if key in seen:
                continue
            seen.add(key)
            recs.append(dict(c, type="column", level=lid, anchor="centre",
                             base=keep.get("base", 0.0),
                             height=keep.get("height", "level"), fit=False))
        recs = [r for r in recs if S.why_not(r) is None]
        arch["structure"] = [e for e in arch["structure"]
                             if not (e["type"] == "column"
                                     and e["level"] == lid)]
        arch["structure"] += M.new_elements(arch["structure"], recs)
        out[lid] = (len(old), len(recs))
    return out


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
        # an outline drawn on three sides only (its fourth on another
        # layer, or left out): closed between its ends
        try:
            from shapely.geometry import Polygon as _Pg
            from shapely.ops import linemerge as _lm
            mg = _lm(unary_union(lines))
            for ch in getattr(mg, "geoms", [mg]):
                if ch.geom_type != "LineString" or ch.is_closed:
                    continue
                cs_ = list(ch.coords)
                if len(cs_) < 4 or math.dist(cs_[0], cs_[-1]) > 1.2:
                    continue
                g_ = _Pg(cs_).buffer(0)
                if g_.geom_type != "Polygon" or not 0.05 <= g_.area <= 4.0:
                    continue
                if g_.area < 0.8 * g_.minimum_rotated_rectangle.area:
                    continue
                if not any(sh.buffer(0.01).contains(g_.representative_point())
                           for sh in shapes):
                    shapes.append(g_)
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
        # a circle (drawn as a CIRCLE, or as a many-sided polyline): a
        # round column — taken from the circles below when one is there
        cg = g.centroid
        rr = max(math.dist((cg.x, cg.y), q) for q in g.exterior.coords)
        if len(g.exterior.coords) >= 11 and rr > 0.04 and \
                g.area >= 0.88 * math.pi * rr * rr:
            out.append({"x": round(cg.x, 4), "y": round(cg.y, 4),
                        "w": round(2 * rr, 3), "d": round(2 * rr, 3),
                        "angle": 0.0, "shape": "round"})
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
    # circles: one round column each — two round one centre (the shaft
    # and its base / finish) ONE column, its shaft the smaller
    cs = [ci for ci in pl["circles"]
          if _match(ci["layer"], pats) and 0.05 <= ci["r"] <= 1.5]
    cs.sort(key=lambda ci: -ci["r"])
    done = []
    for ci in cs:
        c = ci["c"]
        hit = next((d_ for d_ in done if math.dist(d_["c"], c) <
                    0.35 * d_["r"]), None)
        if hit is not None:
            hit["shaft"] = min(hit.get("shaft", hit["r"]), ci["r"])
            continue
        done.append({"c": c, "r": ci["r"]})
    for d_ in done:
        # the outlines found above for this circle (its disc, the ring
        # between two circles): the circle wins
        out = [o for o in out if not (math.dist(
            (o["x"], o["y"]), d_["c"]) < 0.35 * d_["r"] and
            max(float(o["w"]), float(o["d"])) <= 2.3 * d_["r"])]
        rec = {"x": round(d_["c"][0], 4), "y": round(d_["c"][1], 4),
               "w": round(2 * d_["r"], 3), "d": round(2 * d_["r"], 3),
               "angle": 0.0, "shape": "round"}
        if d_.get("shaft"):
            rec["shaft"] = round(2 * d_["shaft"], 3)
        out.append(rec)
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


def _outer_loops(pieces, gap=1.25, least=20.0, extra=(), names=None):
    """Every building block's outer contour: the wall pieces closed over
    their door / window gaps (up to 2·``gap``), each block of
    ``least`` m² or more."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = []
    for pc in pieces:
        p = Polygon(pc["outer"], pc["holes"])
        polys.append(p if p.is_valid else p.buffer(0))
    polys += [p for p in extra if p is not None and not p.is_empty]
    if not polys:
        return []
    u = unary_union(polys).buffer(gap, join_style=2).buffer(-gap,
                                                           join_style=2)
    out = []
    # a block open on one side (an ablution's front, a verandah's steps):
    # its walls running most of the way round — its convex outline
    try:
        raw_u = unary_union(polys)
        closed = [Polygon(g.exterior) for g in getattr(u, "geoms", [u])
                  if g.geom_type == "Polygon" and g.interiors]
        for comp in getattr(raw_u.buffer(0.3), "geoms", [raw_u.buffer(0.3)]):
            if any(c.intersection(comp).area > 0.5 * comp.area
                   for c in closed):
                continue                 # (mostly in a closed block)
            hull = comp.convex_hull.buffer(-0.3, join_style=2)
            if hull.is_empty or hull.area < least:
                continue
            # a block its walls close at a wider reach: that outline, not
            # the convex one (which runs past the plan's own walls)
            near = raw_u.intersection(comp).buffer(
                3.0, join_style=2).buffer(-3.0, join_style=2)
            if any(Polygon(g_.exterior).area >= 0.75 * hull.area
                   for g_ in getattr(near, "geoms", [near])
                   if g_.geom_type == "Polygon"):
                continue
            walls_len = raw_u.intersection(comp).area / 0.2
            if walls_len >= 0.6 * hull.length and \
                    raw_u.intersection(comp).area <= 0.35 * hull.area:
                if names is not None:
                    # only the parts of it the plan names (a lobby, a car
                    # porch): an unnamed corner outside is not the floor
                    from shapely.geometry import Point as _Pn
                    add_ = hull.difference(u)
                    keep_ = [g_ for g_ in getattr(add_, "geoms", [add_])
                             if g_.geom_type == "Polygon" and any(
                                 g_.buffer(0.3).contains(_Pn(x_, y_))
                                 for x_, y_ in names)]
                    hull = unary_union([u.intersection(hull)] + keep_)
                u = unary_union([u, hull])
    except Exception:  # noqa: BLE001
        pass
    for g in sorted(getattr(u, "geoms", [u]), key=lambda p: -p.area):
        # the block's whole outline counts (its rooms inside, not only the
        # walls' own area): a small ablution block closes a floor too
        big_ = g.geom_type == "Polygon" and \
            Polygon(g.exterior).area >= least
        if not big_ and names and g.geom_type == "Polygon" and \
                Polygon(g.exterior).area >= 2.0:
            # a small block of its own the plan names (a guard room)
            from shapely.geometry import Point as _Pb
            big_ = any(Polygon(g.exterior).contains(_Pb(x_, y_))
                       for x_, y_ in names)
        if big_:
            try:                  # without the slivers of the joints
                from . import slabedges as _SE
                out.append([tuple(q) for q in _SE._ring_pts(g)])
            except Exception:  # noqa: BLE001
                out.append(list(g.simplify(0.005).exterior.coords)[:-1])
    return out


ROLE_KEYS = ("walls", "doors", "windows", "columns", "beams", "slab", "holes",
             "text", "plot", "footings", "stairs", "grid", "lift", "parking",
             "cars", "ramps", "bikes", "rails", "steps", "lines")


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
    try:                       # partitions drawn as one line
        rep["single_walls"] = single_line_walls(doc, lid, pl, P)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.single_line_walls")
    # railings drawn on the rail layers: railing walls at the slab's edge
    # (the slab carried out to them below)
    from . import slabedges as SE
    edge_lines = []
    if P.get("rails"):
        try:
            rk = st.get("parapet_rail", "ss_bars")
            rk = rk if rk and rk != "solid" else "ss_bars"
            rrecs = SE.rails_from_cad(pl, lambda n: _match(n, P["rails"]),
                                      lid, rk, float(st.get("rail_h",
                                                            SE.RAIL_H)))
            if st.get("rail_needs_text", True):   # only where the CAD
                from shapely.geometry import LineString as _LS2   # says so
                from shapely.geometry import Point as _Pt2
                pts_ = rail_text_points(doc, lid, pl)
                # (a railing the RAIL layer draws beside steps — a
                # mimber's, a stair's side — is kept: only the terraces'
                # and balconies' edges need the text)
                from shapely.ops import unary_union as _uu2
                try:
                    stp_ = [_LS2([(s_[0], s_[1]), (s_[2], s_[3])])
                            for s_ in pl["segs"] if
                            _match(lay[s_[4]], P.get("steps") or [])]
                    stpu_ = _uu2(stp_) if stp_ else None
                except Exception:  # noqa: BLE001
                    stpu_ = None

                def _inside(r_):
                    return stpu_ is not None and _LS2(
                        [r_["a"], r_["b"]]).distance(stpu_) < 0.6
                try:                  # never a railing on a wall
                    wpu_ = _uu2([_LS2([w_["a"], w_["b"]]).buffer(
                        float(w_["t"]) / 2 + 0.02, cap_style=2)
                        for w_ in arch["walls"] if w_["level"] == lid
                        and not w_.get("rail")])
                    rrecs = [r_ for r_ in rrecs if _LS2(
                        [r_["a"], r_["b"]]).intersection(wpu_).length <
                        0.5 * _LS2([r_["a"], r_["b"]]).length]
                except Exception:  # noqa: BLE001
                    pass
                keep_ = [r_ for r_ in rrecs if _inside(r_) or any(
                    _LS2([r_["a"], r_["b"]]).distance(_Pt2(x, y)) < 3.0
                    for x, y in pts_)]
                # and the railing running on from a kept one (its corner)
                grew_ = True
                while grew_:
                    grew_ = False
                    for r_ in rrecs:
                        if r_ in keep_:
                            continue
                        if any(math.dist(p_, q_) < 0.05 for k_ in keep_
                               for p_ in (r_["a"], r_["b"])
                               for q_ in (k_["a"], k_["b"])):
                            keep_.append(r_)
                            grew_ = True
                rrecs = keep_
            made_r = M.new_walls(arch["walls"], rrecs)
            n0 = sum(1 for w in arch["walls"] if str(w.get("name", ""))
                     .startswith("Balcony railing"))
            for k_, w_ in enumerate(made_r, 1):
                w_["name"] = f"Balcony railing {n0 + k_}"
                w_["rail"] = rk
            arch["walls"] += made_r
            rep["railings"] = len(made_r)
            edge_lines += [(tuple(w_["a"]), tuple(w_["b"])) for w_ in made_r]
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project rails_from_cad")
    # the plan's dashed (projection) lines: the slab ABOVE this floor (a
    # porch roof, a shade) — the floor carried out to them only when slabs
    # are drawn on top of their floor; a floor stays as its plan draws it
    if st.get("slab_extend_cad", True):
        try:
            edge_lines += SE.dashed_lines(pl)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project dashed_lines")
    orecs = []
    for op in ops:
        k, pos, width = op[:3]
        kind = op[3] if len(op) > 3 else ("door" if width <= 1.2
                                          else "window")
        hinge = op[4] if len(op) > 4 else -1
        face = op[5] if len(op) > 5 else 1
        style = ""
        if kind == "sliding":                  # (older: a glass sliding
            kind, style = "door", "sliding"    # door when nothing drawn)
        if kind == "void":                     # nothing drawn: an opening
            orecs.append({"kind": "void", "wall": made[k]["id"],  # no door
                          "pos": round(pos + shifted[k], 4),
                          "w": round(width, 3), "h": float(st["door_h"]),
                          "sill": 0.0, "swing": "left", "face": 1,
                          "style": ""})
            continue
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

    # corner / bay windows: glazing drawn outside the walls, turning a
    # corner — window walls (glass between an opaque sill and head panel)
    if st.get("corner_windows", True):
        try:
            rep["corner_windows"] = _corner_windows(doc, lid, pl, P, how,
                                                    made)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project corner windows")

    # doors and windows no wall holds (a door between two fins, glazing
    # from pier to pier): a wall of their own, as wide as they are
    if st.get("bridge_openings", True):
        try:
            from . import bridges as BR
            br = BR.bridge(arch, lid, pl,
                           lambda n: _match(n, P["doors"]),
                           lambda n: _match(n, P["windows"]),
                           lambda n: _match(n, P["walls"]), st,
                           (lambda n: _match(n, P["lines"]))
                           if P.get("lines") else None,
                           lambda n: _match(n, P["columns"]))
            nw = br.pop("_new", [])
            for o in nw + br.pop("typed", []):
                door_rule(o)
                opening_types(o, st)
            arch["openings"] += M.new_openings(arch["openings"], nw)
            rep["bridged"] = br
            made = [w for w in arch["walls"] if w["level"] == lid
                    and not w.get("rail")]
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.bridges")

    # blocks named ARCH (an arched window / opening drawn as a block): the
    # opening under them takes an arched head
    try:
        rep["arched"] = arch_blocks(arch, lid, pl, st)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.arch_blocks")

    # columns: closed outlines, loose lines and circles on the column
    # layers — rectangles (long shear walls too), and L / T / C sections
    cols = columns_from(pl, column_layers_for(P["columns"],
                                              level_floor_no(arch, lid)),
                        lay)
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
            from shapely.geometry import Polygon
            mine = [w for w in arch["walls"] if w["level"] == lid]
            plans = W.plan([w for w in mine if W.why_not(w) is None])
            # the columns and piers close the walls' corners too
            cpolys = []
            for c_ in crecs + [e_ for e_ in arch["structure"]
                               if e_.get("type") == "column"
                               and e_.get("level") == lid]:
                try:
                    cpolys.append(Polygon(S.column_outline(c_, 0.0)).buffer(
                        0.02))
                except Exception:  # noqa: BLE001
                    continue
            try:                 # the spaces the plan names
                nm_ = [(float(t_["x"]), float(t_["y"]))
                       for t_ in pl.get("texts") or []
                       if re.search(r"[A-Z]{3}", str(t_.get("text", "")))
                       and not re.match(r"^\s*(UP|DN|DOWN)\b",
                                        str(t_.get("text", "")), re.I)
                       and not OUTDOOR_WORDS.search(str(t_.get("text", "")))]
            except Exception:  # noqa: BLE001
                nm_ = None
            # railings and glazing drawn round a balcony or a lobby left
            # open to it close the floor too (thin pieces, near the walls)
            try:
                from shapely.geometry import LineString as _Ls
                from shapely.ops import unary_union as _uuo
                wpu_ = _uuo([Polygon(pc["outer"]).buffer(0)
                             for ps in plans.values() for pc in ps])
                reach_ = wpu_.buffer(2.5)
                thin_ = []
                for s_ in pl["segs"]:
                    ln_ = lay[s_[4]]
                    if not (_match(ln_, P.get("rails") or []) or
                            _match(ln_, P["windows"]) or
                            _match(ln_, P["walls"])):
                        continue
                    L_ = _Ls([(s_[0], s_[1]), (s_[2], s_[3])])
                    if L_.length > 0.02 and reach_.contains(L_):
                        thin_.append(L_.buffer(0.06))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project slab thin pieces")
                thin_ = []
            blocks = _outer_loops([pc for ps in plans.values() for pc in ps],
                                  extra=cpolys, names=nm_)
            # (names of the outdoors — a side passage, the lawn, the
            # drive — do not bring the floor out there)
            nm2_ = []
            try:
                out_w_ = re.compile(
                    r"SIDE\s*PASSAGE|BACK\s*PASSAGE|FRONT\s*PASSAGE|LAWN|"
                    r"DRIVE|PORCH|GARDEN|PARKING|ROAD|STREET|PLOT|\bOPEN\b|"
                    r"COURT\s*YARD|YARD|SET\s*BACK|GREEN|SITE|BOUNDARY",
                    re.I)
                txt_ = [(float(t_["x"]), float(t_["y"]), str(t_.get("text",
                                                                    "")))
                        for t_ in pl.get("texts") or []]
                nm2_ = [(x_, y_) for x_, y_, s__ in txt_
                        if re.search(r"[A-Z]{3}", s__)
                        and not out_w_.search(s__)
                        and not re.match(r"^\s*(UP|DN|DOWN)\b", s__, re.I)]
            except Exception:  # noqa: BLE001
                nm2_ = []
            if thin_ and nm2_:
                # only the parts they close that the plan names (a
                # corridor, a room open to a balcony): no paving outside
                try:
                    from shapely.geometry import Point as _Pt
                    b1_ = _outer_loops([pc for ps in plans.values()
                                        for pc in ps],
                                       extra=cpolys + [_uuo(thin_)],
                                       names=nm_)
                    u0_ = _uuo([Polygon(b_).buffer(0) for b_ in blocks]) \
                        if blocks else Polygon()
                    u1_ = _uuo([Polygon(b_).buffer(0) for b_ in b1_])
                    add_ = u1_.difference(u0_.buffer(0.01))
                    keep_ = [g_ for g_ in getattr(add_, "geoms", [add_])
                             if g_.geom_type == "Polygon" and g_.area > 0.5
                             and any(g_.contains(_Pt(x_, y_))
                                     for x_, y_ in nm2_)]
                    if keep_:
                        uu_ = _uuo([u0_] + [g_.buffer(0.02) for g_ in keep_])
                        uu_ = uu_.buffer(-0.02, join_style=2)
                        blocks = [[tuple(q_) for q_ in list(
                            g_.exterior.coords)[:-1]]
                            for g_ in getattr(uu_, "geoms", [uu_])
                            if g_.geom_type == "Polygon" and g_.area >= 2.0]
                except Exception:  # noqa: BLE001
                    from .host import log_error
                    log_error("project slab named closure")
            try:                # not past what the plan's lines close
                dr_ = drawn_floor(doc, lid, pl, P)
                if dr_ is not None and blocks:
                    from shapely.ops import unary_union as _uud
                    ub_ = _uud([Polygon(b_).buffer(0) for b_ in blocks])
                    cut_ = ub_.intersection(dr_.buffer(0.02, join_style=2))
                    if not cut_.is_empty and cut_.area >= 0.6 * ub_.area \
                            and ub_.area - cut_.area > 1.0:
                        gs_ = sorted((g_ for g_ in getattr(cut_, "geoms",
                                                           [cut_])
                                      if g_.geom_type == "Polygon"
                                      and g_.area >= 2.0),
                                     key=lambda g_: -g_.area)
                        blocks = [[tuple(q_) for q_ in list(
                            g_.exterior.coords)[:-1]] for g_ in gs_]
                        rep["slab_drawn"] = round(ub_.area - cut_.area, 2)
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project slab drawn_floor")
            # a parking floor: the drive and the ramps under the slab too —
            # a close hull round the walls, the bays and the ramps
            pk = [s_ for s_ in pl["segs"] if _match(lay[s_[4]], P["parking"])
                  or _match(lay[s_[4]], P["ramps"])]
            # (bays drawn: a parking floor — ramps alone, a footpath's or
            # a road's, do not make one)
            if pk and mine and sum(1 for s_ in pk if _match(
                    lay[s_[4]], P["parking"])) >= 4:
                try:
                    blocks = _parking_slab(
                        [w for w in mine if not str(w.get("name", ""))
                         .startswith("Corner window")], pk, blocks)
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
        try:                 # a shaft named on the plan, boxed and X-ed on
            openings_all += labelled_shafts(pl, openings_all)  # any layer
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.labelled_shafts")
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
        lv_k = (level_by_id(arch, lid) or {}).get("kind")
        if lv_k == "ground" and not any(
                lv_.get("kind") == "basement" for lv_ in arch["levels"]):
            # the ground floor on the ground: its dashed lines are the slab
            # ABOVE projecting (a chajja, the porch roof) — the floor stays
            # as the walls close it
            edge_lines = [e_ for e_ in edge_lines if False]
        if edge_lines:            # out to the railings, the dashed edges
            try:
                ext = [SE.extend_outline(o, edge_lines) for o in outlines]
                rep["slab_extended"] = sum(1 for a_, b_ in zip(outlines, ext)
                                           if a_ is not b_)
                outlines = ext
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project extend_outline")
        try:                      # never past what the plan draws (and the
            lim_ = plan_limit(doc, lid, pl, P)      # areas its levels note)
        except Exception:  # noqa: BLE001
            lim_ = None
        if lim_ is not None and not lim_.is_empty:
            cl_ = []
            for o_ in outlines:
                try:
                    g_ = Polygon(o_).buffer(0).intersection(lim_)
                    g_ = max((q for q in getattr(g_, "geoms", [g_])
                              if q.geom_type == "Polygon"),
                             key=lambda q: q.area, default=None)
                    if g_ is not None and g_.area > 0.5 and \
                            g_.area < Polygon(o_).buffer(0).area - 0.05:
                        o_ = [[round(x, 4), round(y, 4)] for x, y in
                              list(g_.simplify(0.005).exterior.coords)[:-1]]
                        rep["slab_limited"] = rep.get("slab_limited", 0) + 1
                except Exception:  # noqa: BLE001
                    pass
                cl_.append(o_)
            outlines = cl_
        for outline in outlines:
            poly = Polygon(outline)
            inner = poly.buffer(-0.02) if poly.is_valid else poly.buffer(0)
            shut_ = [Point(m["x"], m["y"]) for m in
                     doc.get("closed_holes") or [] if m["level"] == lid]
            sh_open = [h for h in openings_all
                       if inner.contains(Polygon(h).representative_point())
                       and not any(Polygon(h).buffer(0.02).contains(q)
                                   for q in shut_)]
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
    # walls that stop short of one another (across a column, an arch, a
    # pier): closed up — the rooms close as the plan draws them
    if st.get("close_gaps", True):
        try:
            from . import bridges as BR
            cg = BR.close_gaps(arch, lid, pl,
                               lambda n: _match(n, P["walls"]) or
                               _match(n, P["columns"]), st)
            arch["openings"] += M.new_openings(arch["openings"],
                                               cg.pop("_new", []))
            rep["gaps"] = cg
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.close_gaps")
    if st.get("rcc_fills", True):    # hatched / filled walls: RCC work
        try:
            rep["rcc"] = rcc_from_fills(arch, lid, pl)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.rcc_from_fills")
    try:                     # an X of hidden lines between columns: an arch
        rep["arches_between"] = arches_between(doc, lid, pl, P)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.arches_between")
    if st.get("walls_at_columns", True):    # no wall on through a column
        try:
            rep["walls_at_columns"] = walls_at_columns(arch, lid)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.walls_at_columns")
    try:                          # no wall on another (a window band
        rep["dedupe"] = dedupe_walls(arch, lid)    # read as a wall too)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.dedupe_walls")
    if st.get("close_gaps", True):   # ends left short (of a column face,
        try:                          # a wall): carried into it, cleanly
            from . import bridges as BR
            cg2 = BR.close_gaps(arch, lid, pl,
                                lambda n: _match(n, P["walls"]) or
                                _match(n, P["columns"]), st,
                                only_extend=True)
            cg2.pop("_new", None)
            rep["ends_met"] = cg2.get("extended", 0)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.close_gaps ends")

    if rep.get("corner_windows"):    # the slab carried over them too
        try:
            cover_corner_windows(doc, lid)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project cover_corner_windows")
    # the slab: out over the columns / piers round it, its slivers gone
    try:
        mine_s = [e for e in arch["structure"]
                  if e["type"] == "slab" and e["level"] == lid
                  and not e.get("zone")]
        # (a floor on the ground is not carried out to the columns round
        # it — a porch's, a car porch's: only what its plan draws)
        on_grade_ = not slab_on_top(doc) and (level_by_id(arch, lid) or {})\
            .get("kind") in ("ground", "basement")
        if st.get("slab_to_columns", True):
            before_ = {id(s_): SE._poly(s_["corners"]) for s_ in mine_s}
            rep["slab_columns"] = SE.extend_slabs_to_columns(doc, mine_s)
            if on_grade_:
                # a floor on the ground carried out to its columns only
                # over the spaces the plan names there (an entrance lobby,
                # a car porch) — no unnamed corner outside
                from shapely.geometry import Point as _Pq
                from shapely.ops import unary_union as _uq
                nmq = [(float(t_["x"]), float(t_["y"]))
                       for t_ in pl.get("texts") or []
                       if re.search(r"[A-Z]{3}", str(t_.get("text", "")))
                       and not re.match(r"^\s*(UP|DN|DOWN)\b",
                                        str(t_.get("text", "")), re.I)
                       and not OUTDOOR_WORDS.search(str(t_.get("text", "")))]
                try:             # the CAD's steps part one space from
                    stp_ = _uq([pc_ for cs_ in cad_steps(doc, lid)   # the
                                for pc_, _r in cs_["strips"]]        # next
                               ).buffer(0.02)
                except Exception:  # noqa: BLE001
                    stp_ = None
                for s_ in mine_s:
                    b_ = before_.get(id(s_))
                    if b_ is None:
                        continue
                    a_ = SE._poly(s_["corners"])
                    add_ = a_.difference(b_)
                    if stp_ is not None and not stp_.is_empty:
                        add_ = add_.difference(stp_)
                    keep_ = [g_ for g_ in getattr(add_, "geoms", [add_])
                             if g_.geom_type == "Polygon" and g_.area > 0.2
                             and any(g_.buffer(0.2).contains(_Pq(x_, y_))
                                     for x_, y_ in nmq)]
                    new_ = _uq([b_] + keep_).buffer(
                        0.005, join_style=2).buffer(-0.005, join_style=2)
                    new_ = SE._largest(new_, b_.representative_point())
                    if new_ is not None and new_.area > 1.0:
                        s_["corners"] = [[round(x, 4), round(y, 4)]
                                         for x, y in SE._ring_pts(new_)]
        for s_ in mine_s:
            SE.tidy_slab(s_)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project slab columns / tidy")
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
    from . import parking as PK_
    for room in spaces.of_level(arch, lid):
        inside = [t for t in texts
                  if room["poly"].contains(Point(t["x"], t["y"]))
                  and len(t["text"]) <= 40 and not
                  t["text"].replace(".", "").replace(",", "").strip()
                  .isdigit()]
        # a name, not a note: no level note, no UP / DN, no landing
        names_ = [t for t in inside if not PK_.level_note(t["text"])
                  and not re.match(r"^\s*(UP|DN|DOWN|MID LANDING|LANDING)"
                                   r"\s*$", t["text"], re.I)
                  and not re.search(r"LEVEL|LEV\b", t["text"], re.I)]
        if not names_ and any(re.match(
                r"^\s*(UP|DN|DOWN)\s*$", t["text"], re.I) for t in inside):
            rrecs.append({"id": "", "level": lid, "x": room["at"][0],
                          "y": room["at"][1], "name": "STAIRCASE"})
            continue
        inside = names_ or inside
        if inside:
            name = max(inside, key=lambda t: t["h"])["text"].split("\n")[0]
            rrecs.append({"id": "", "level": lid, "x": room["at"][0],
                          "y": room["at"][1], "name": name.strip()[:60]})
    arch["rooms"] = M._rooms(arch["rooms"] + rrecs,
                             {lv["id"] for lv in arch["levels"]})
    rep["rooms"] = len(spaces.of_level(arch, lid))

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

    # a basement's outer walls: RCC retaining walls, no doors or windows
    lv_ = next((x for x in arch["levels"] if x["id"] == lid), None)
    if lv_ is not None and lv_.get("kind") == "basement" and \
            st.get("basement_rcc", True):
        try:
            rep["retaining"] = basement_walls(doc, lid)["walls"]
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.basement_walls")
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
    if st.get("hidden_rules", True):        # what the hidden lines say
        try:
            rep["hidden"] = apply_hidden_lines_new(doc).get(lid)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.apply_hidden_lines")
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
            rep["zones"] = slab_zones(doc, lid, pl, P)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.slab_zones")
    if P.get("lines"):            # the «line» layer: grilles, low walls,
        try:                      # low platforms (lowparts.py)
            from . import lowparts as LP
            rep["lines"] = LP.analyze(doc, lid, pl,
                                      lambda n: _match(n, P["lines"]))
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.lowparts")
    try:                                  # out over the floor below: its
        cap_lower_floor(doc, lid, plan_limit(doc, lid, pl, P))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.cap_lower_floor")
    try:                     # a basement's windows over the ground only
        rep["basement_windows"] = basement_windows(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.basement_windows")
    if st.get("terrace_rails", True):    # railings round its terraces
        try:
            rep["terrace_railings"] = terrace_railings(doc, lid, pl, P)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.terrace_railings")
    if st.get("floor_strict", True):    # the floor as its plan draws it
        try:
            rep["strict_floor"] = strict_floor(doc, lid, pl, P)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.strict_floor")
    try:                       # a door where the plan draws a window
        rep["doors_to_windows"] = doors_at_windows(doc, lid, pl, P)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.doors_at_windows")
    try:                       # wall pieces drawn as solid outlines
        rep["wall_masses"] = wall_masses(doc, lid, pl, P)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.wall_masses")
    try:                       # a shower's glass read as a window: no wall
        from . import fitout as FO
        rep["shower_walls"] = FO.shower_walls(doc, lid, pl)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.shower_walls")
    if st.get("cad_furniture", False):    # its furniture and fixtures
        try:
            from . import furnish as FU
            rep["furniture"] = FU.furnish(doc, [lid]).get(lid, {})
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.furnish")
    elif st.get("bath_fixtures", True):   # the WCs, vanities, showers only
        try:
            from . import furnish as FU
            rep["fixtures"] = FU.furnish(doc, [lid], only=FU.BATH_KINDS) \
                .get(lid, {})
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.furnish fixtures")
    try:                       # voids / ducts, shower glass, lift, lights…
        from . import fitout as FO
        rep["fitout"] = FO.analyze(doc, lid, pl)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.fitout")
    return rep


def outer_walls(arch, lid) -> list:
    """The walls on a level's outer edge (straight ones): their centre line
    along the outline of everything the level's walls enclose."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    ws = [w for w in arch["walls"] if w["level"] == lid and
          w.get("kind", "line") == "line" and not w.get("rail")]
    if not ws:
        return []
    u = unary_union([LineString([tuple(w["a"]), tuple(w["b"])]).buffer(
        float(w["t"]) / 2 + 0.06, cap_style=2, join_style=2) for w in ws])
    # the gaps the CAD leaves at doors bridged: the building's own outline
    u = u.buffer(2.0, join_style=2).buffer(-2.0, join_style=2)
    shells = [Polygon(p.exterior) for p in getattr(u, "geoms", [u])
              if p.geom_type == "Polygon" and Polygon(p.exterior).area > 15.0]
    if not shells:
        return []
    rings = [sh.exterior for sh in shells]
    out = []
    for w in ws:
        tol = float(w["t"]) / 2 + 0.25
        a, b = tuple(w["a"]), tuple(w["b"])
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if any(r.distance(Point(m)) <= tol and r.distance(Point(a)) <= tol
               and r.distance(Point(b)) <= tol for r in rings):
            out.append(w)
    return out


def basement_walls(doc, lid=None, t=None, on=True) -> dict:
    """A basement's outer walls (every basement's when ``lid`` is None) made
    RCC retaining walls, like a lift core's: their doors and windows taken
    out (the wall closed), at least ``t`` thick (the settings' 12" by
    default). ``on=False`` makes them ordinary walls again.
    {"walls": n, "openings": m}."""
    arch = doc["arch"]
    st = doc["settings"]
    t = float(t if t is not None else st.get("retain_t", 0.3048))
    lids = [lid] if lid else [lv["id"] for lv in arch["levels"]
                             if lv.get("kind") == "basement"]
    nw = no = 0
    for l_ in lids:
        for w in outer_walls(arch, l_):
            if not on:
                if w.pop("rcc", None):
                    nw += 1
                continue
            w["rcc"] = True
            w["type"] = "solid"
            if float(w["t"]) < t:
                w["t"] = round(t, 4)
            nm = str(w.get("name") or "")
            if not nm.startswith("RCC retaining wall"):
                w["name"] = f"RCC retaining wall {nw + 1}"
            nw += 1
            before = len(arch["openings"])
            arch["openings"] = [o for o in arch["openings"]
                                if o["wall"] != w["id"]]
            no += before - len(arch["openings"])
    return {"walls": nw, "openings": no}


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
    # motorbikes: their blocks, and the small bays the bike / parking lines
    # close (numbered M1, M2… as the cars are P1, P2…)
    bikel = [[[round(s[0], 4), round(s[1], 4)], [round(s[2], 4), round(s[3], 4)]]
             for s in pl["segs"] if P.get("bikes") and on(s, "bikes")]
    bikes = []
    for ins in pl.get("inserts", ()):
        nm = str(ins["name"]).upper()
        if (P.get("bikes") and _match(ins["layer"], P["bikes"])) or \
                re.search(r"BIKE|MOTOR\s?CYC|M\.?\s?CYCLE|SCOOTER|2.?WHEEL", nm):
            b = PK.bike_of(ins)
            if b:
                bikes.append(b)
    bstalls = []
    try:
        if bikel or bikes:
            bstalls = PK.bike_stalls(bikel + bays, bikes, stalls)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.bike_stalls")
    if bays or cars or bikes or bstalls:
        doc["parking"][lid] = {"bays": bays, "carlines": carl, "cars": cars,
                               "stalls": stalls, "bikelines": bikel,
                               "bikes": bikes, "bike_stalls": bstalls}
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
    land = [(t["x"], t["y"]) for t in pl["texts"]
            if re.search(r"LANDING|LNDG", str(t["text"]).upper())]
    for t in pl["texts"]:
        v = PK.level_note(t["text"])
        if v:
            m_ = {"x": round(t["x"], 4), "y": round(t["y"], 4),
                  "text": v[0], "v": v[1], "a": PK.abs_level(t["text"])}
            # a stair's mid landing («MID LANDING / LEV. 14'-0"»): not a
            # floor's level
            if any(math.hypot(t["x"] - x, t["y"] - y) < 2.5
                   for x, y in land):
                m_["landing"] = True
            marks.append(m_)
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


def ground_slab_on(doc) -> bool:
    """The ground floor on a concrete slab: asked for («Ground floor
    slab»), or a basement under it — the foundation platform turned to a
    slab like the other floors'."""
    st = doc.get("settings") or {}
    if st.get("ground_slab", False):
        return True
    return any(lv.get("kind") == "basement"
               for lv in (doc.get("arch") or {}).get("levels") or [])


def platform_on(doc) -> bool:
    """The foundation platform under the ground floor: slabs as floors, the
    ground floor on the ground (no slab, no basement), the option on."""
    return (not slab_on_top(doc) and not ground_slab_on(doc)
            and bool((doc.get("settings") or {}).get("platform", True)))


def slab_on_top(doc) -> bool:
    """Each floor's slab cast OVER it, on its walls (the default) — not
    under it at its floor level."""
    return (doc.get("settings") or {}).get("slab_pos", "top") == "top"


def cap_lower_floor(doc, lid, limit=None) -> int:
    """Slabs as floors: where the floor below reaches out past this floor,
    this floor's slab is carried out over it — flush with that floor's
    external walls and columns (their outer faces) — a terrace, railed
    round by ``terrace_railings``. This floor's slabs there are made one
    (their openings kept). How many slabs grew."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if slab_on_top(doc):
        return 0
    below = level_below(doc, lid)
    if below is None:
        return 0
    arch = doc["arch"]
    walls = [w for w in arch["walls"] if w["level"] == below
             and not w.get("rail") and W.why_not(w) is None
             and not str(w.get("name", "")).startswith(
                 ("Terrace railing", "Roof", "Opening"))]
    plans = W.plan([S._plastered(w, float(doc["settings"].get(
        "plaster_t", 0.0127) or 0.0)) for w in walls])
    loops = _outer_loops([pc for ps in plans.values() for pc in ps])
    polys = [Polygon(o).buffer(0) for o in loops]
    for e in arch["structure"]:
        if e["type"] in ("column", "core") and e["level"] == below and \
                len(e.get("corners") or []) >= 3:
            polys.append(Polygon([tuple(q[:2]) for q in e["corners"]])
                         .buffer(0))
        # the floor below's own outline (its porch, verandah…), as the
        # slab over it was before slabs were floors
        if e["type"] == "slab" and e["level"] == below and not (
                e.get("zone") or e.get("user") or e.get("roof")) and \
                len(e.get("corners") or []) >= 3:
            polys.append(Polygon([tuple(q[:2]) for q in e["corners"]])
                         .buffer(0))
    if not polys:
        return 0
    foot = unary_union(polys)
    if limit is not None and not limit.is_empty:
        # never past what this floor's own CAD plan draws (nor the areas
        # its level texts note): the floor below's roof beyond it stays a
        # roof, not this floor's terrace
        foot = foot.intersection(limit)
    mine = [e for e in arch["structure"] if e["type"] == "slab"
            and e["level"] == lid and not (e.get("zone") or e.get("user")
                                           or e.get("roof")
                                           or e.get("grade"))]
    if not mine:
        return 0
    own = unary_union([Polygon(e["corners"]).buffer(0) for e in mine])
    u = unary_union([own, foot]).buffer(1e-4, join_style=2).buffer(
        -1e-4, join_style=2)
    if u.area <= own.area + 0.5:
        return 0
    holes = [h for e in mine for h in e.get("holes") or []]
    shafts = [h for e in mine for h in e.get("shafts") or []]
    base = max(mine, key=lambda e: Polygon(e["corners"]).buffer(0).area)
    arch["structure"] = [e for e in arch["structure"] if e not in mine]
    made = []
    for g in getattr(u, "geoms", [u]):
        if g.geom_type != "Polygon" or g.area < 1.0:
            continue
        rec = dict(base)
        rec.pop("id", None)
        rec["corners"] = [[round(x, 4), round(y, 4)]
                          for x, y in S._ccw(list(g.exterior.coords)[:-1])]
        inside = g.buffer(0.05)
        rec["holes"] = [h for h in holes
                        if inside.contains(Polygon(h).buffer(0))]
        rec["shafts"] = [h for h in shafts
                         if inside.contains(Polygon(h).buffer(0))]
        made.append(rec)
    arch["structure"] += M.new_elements(arch["structure"], made)
    return len(made)


_PLAN_LIMIT: dict = {}


def plan_limit(doc, lid, pl, P):
    """The area level ``lid``'s CAD plan draws: the outline of its lines
    (walls, doors, windows, columns, the LINE and STEP layers, railings,
    slab edges, stairs) with gaps up to ~1 m closed and the areas inside
    filled, and the areas its level texts stand in — a floor goes no
    further. None when it cannot be told."""
    from shapely.geometry import LineString, Point
    from shapely.geometry import Polygon as _Pg
    from shapely.ops import unary_union
    if pl is None or P is None:
        return None
    key = (lid, id(pl), len(pl["segs"]))
    if key in _PLAN_LIMIT:
        return _PLAN_LIMIT[key]
    lay = pl["layers"]
    pats = []
    for k in ("walls", "doors", "windows", "columns", "lines", "steps",
              "rails", "slab", "stairs"):
        pats += list(P.get(k) or [])
    segs = [LineString([(s_[0], s_[1]), (s_[2], s_[3])]) for s_ in pl["segs"]
            if pats and _match(lay[s_[4]], pats)
            and math.dist((s_[0], s_[1]), (s_[2], s_[3])) > 0.02]
    if len(segs) < 3:
        return None
    # the lines thickened then thinned: an outline drawn in pieces, a
    # parapet with breaks, read as closed; what it rings, filled
    import shapely as _sh
    closed = _sh.union_all(_sh.buffer(segs, 0.6, quad_segs=1)).buffer(
        -0.45, quad_segs=1)
    outer = unary_union([_Pg(g.exterior) for g in getattr(closed, "geoms",
                                                         [closed])
                         if g.geom_type == "Polygon" and g.area > 0.5])
    if outer.is_empty:
        return None
    notes = [Point(x, y).buffer(1.0) for x, y, _v in note_levels(doc, lid)]
    lim = unary_union([outer] + notes).buffer(0.3, join_style=2)
    if len(_PLAN_LIMIT) > 8:
        _PLAN_LIMIT.clear()
    _PLAN_LIMIT[key] = lim
    return lim

def level_below(doc, lid):
    """The level under ``lid`` (by height), or None."""
    arch = doc["arch"]
    el = elevations(arch)
    order = [arch["levels"][i]["id"] for i in
             sorted(range(len(arch["levels"])), key=lambda i: el[i])]
    k = order.index(lid) if lid in order else -1
    return order[k - 1] if k > 0 else None


def face_to_slab(doc, pts, z, t=None) -> str | None:
    """A flat face drawn in the model made a slab: on the floor it lies at
    (its top the face — a slab of that floor, raised / sunk by the
    difference), or the roof over the top floor when it lies there. Its
    id, or None (no level near)."""
    from shapely.geometry import Polygon
    arch = doc["arch"]
    g = Polygon([tuple(p[:2]) for p in pts]).buffer(0)
    if g.is_empty or g.area < 0.05:
        return None
    if g.geom_type != "Polygon":
        g = max(g.geoms, key=lambda q: q.area)
    el = elevations(arch)
    t = float(t or doc["settings"].get("slab_t", 0.1016) or 0.1016)
    best = None
    for i, lv in enumerate(arch["levels"]):
        z0 = el[i]
        top = z0 + float(lv.get("height") or 3.0)
        for roof, ref in ((False, z0), (True, top)):
            if roof and lv["id"] != top_floor(doc):
                continue
            d = abs(float(z) - ref)
            if best is None or d < best[0]:
                best = (d, lv["id"], roof, float(z) - ref)
    if best is None or best[0] > 3.0:
        return None
    _d, lid, roof, off = best
    fin_ = float(doc["settings"].get("finish_t", 0.0508) or 0.0)
    if -0.005 <= off <= fin_ + 0.005:
        off = 0.0                  # drawn on the floor / its finish: level
    rec = {"type": "slab", "level": lid, "t": round(t, 4),
           "offset": round(off, 4) if abs(off) > 0.005 else 0.0,
           "corners": [[round(x, 4), round(y, 4)]
                       for x, y in S._ccw(list(g.exterior.coords)[:-1])],
           "holes": [], "name": "Slab (drawn)"}
    if roof:
        rec["roof"] = True
    elif rec["offset"]:
        rec["user"] = True         # sunk / raised: its finish follows it
    if S.why_not(rec) is not None:
        return None
    made = M.new_elements(arch["structure"], [rec])
    arch["structure"] += made
    return made[0]["id"] if made else None


def roof_top(doc, lid):
    """The top of the roof slab over level ``lid`` (absolute), or None."""
    arch = doc["arch"]
    r = [e for e in arch["structure"] if e["type"] == "slab"
         and e["level"] == lid and e.get("roof") and not e.get("user")]
    if not r:
        return None
    lv = level_by_id(arch, lid)
    el = elevations(arch)
    i = arch["levels"].index(lv)
    return el[i] + float(lv.get("height") or 3.0) + float(
        r[0].get("offset", 0.0) or 0.0)


def top_floor(doc):
    """The highest level with walls (not a «Roof» level), or None."""
    arch = doc["arch"]
    el = elevations(arch)
    best = None
    for i, lv in enumerate(arch["levels"]):
        if str(lv.get("name", "")).strip().lower() == "roof":
            continue
        if not any(w["level"] == lv["id"] and not w.get("rail")
                   for w in arch["walls"]):
            continue
        if best is None or el[i] > best[0]:
            best = (el[i], lv["id"])
    return best[1] if best else None


def ensure_roof(doc) -> str | None:
    """Slabs as floors: the roof slab over the top floor — its outline the
    outer faces of that floor's walls, its top at the floor's top — made
    when there is none (moved up when a floor is added on top: the one
    made on the floor below goes). The level it is on, or None."""
    if slab_on_top(doc) or not doc["settings"].get("roof_auto", False):
        return None
    arch = doc["arch"]
    top = top_floor(doc)
    if any(str(lv.get("name", "")).strip().lower() == "roof"
           for lv in arch["levels"]):
        top = None                       # a «Roof» level is the roof
    arch["structure"] = [e for e in arch["structure"] if not (
        e["type"] == "slab" and e.get("auto_roof") and e["level"] != top)]
    if top is None:
        return None
    if any(e["type"] == "roof" and e["level"] == top
           for e in arch["structure"]):
        arch["structure"] = [e for e in arch["structure"] if not (
            e["type"] == "slab" and e.get("auto_roof"))]
        return None                      # a hip / gable roof made there
    if any(e["type"] == "slab" and e["level"] == top and e.get("roof")
           for e in arch["structure"]):
        return top
    walls = [w for w in arch["walls"] if w["level"] == top
             and not w.get("rail") and W.why_not(w) is None
             and w.get("height", "level") == "level"]
    plans = W.plan([S._plastered(w, float(doc["settings"].get(
        "plaster_t", 0.0127) or 0.0)) for w in walls])
    loops = _outer_loops([pc for ps in plans.values() for pc in ps])
    t = float(doc["settings"].get("roof_t") or doc["settings"].get(
        "slab_t", 0.1016) or 0.1016)
    from shapely.geometry import Polygon as _Pg
    wells = []                    # the stairs going up to the roof: open
    for st_ in doc.get("stairs") or []:
        if st_.get("level") == top and not st_.get("to") and \
                len(st_.get("corners") or []) >= 3:
            wells.append([list(p[:2]) for p in st_["corners"]])
    made = []
    for o in loops:
        op = _Pg(o).buffer(0)
        hs = [w_ for w_ in wells if op.buffer(-0.05).intersects(_Pg(w_))]
        rec = {"type": "slab", "level": top, "roof": True, "auto_roof": True,
               "corners": [[round(p[0], 4), round(p[1], 4)]
                           for p in S._ccw(o)],
               "holes": hs, "t": t, "offset": 0.0, "name": "Roof slab"}
        if S.why_not(rec) is None:
            made.append(rec)
    arch["structure"] += M.new_elements(arch["structure"], made)
    return top if made else None


AUTO_RAIL = ("Roof edge railing", "Opening railing")


def _hole_key(lid, poly):
    c = poly.representative_point()
    return (lid, round(c.x, 1), round(c.y, 1))


def freeze_auto_rail(doc, wid) -> bool:
    """A railing made by itself (round the roof's edge, round an opening)
    about to be edited by hand: it and the rest of its set kept as they
    are from now on — named as plain railings, no longer made again — so
    the edit stays. True when it was one."""
    from shapely.geometry import LineString, Polygon
    arch = doc["arch"]
    st = doc["settings"]
    w = next((x for x in arch["walls"] if x.get("id") == wid), None)
    if w is None or not str(w.get("name", "")).startswith(AUTO_RAIL):
        return False
    lid = w["level"]
    if str(w["name"]).startswith("Roof edge railing"):
        st["roof_parapet"] = False
        k = 0
        for x in arch["walls"]:
            if x["level"] == lid and str(x.get("name", "")).startswith(
                    "Roof edge railing"):
                k += 1
                x["name"] = f"Roof railing {k}"
        return True
    ln = LineString([w["a"], w["b"]])     # an opening's: the hole it rings
    for e in arch["structure"]:
        if e["type"] != "slab" or e["level"] != lid:
            continue
        for h in e.get("holes") or []:
            try:
                hp = Polygon(h).buffer(0)
            except Exception:  # noqa: BLE001
                continue
            if hp.exterior.distance(ln) > 0.3:
                continue
            fr = st.setdefault("rail_frozen", [])
            key = list(_hole_key(lid, hp))
            if key not in fr:
                fr.append(key)
            ring = hp.exterior.buffer(0.3)
            k = sum(1 for x in arch["walls"] if str(x.get("name", ""))
                    .startswith("Opening parapet "))
            for x in arch["walls"]:
                if x["level"] == lid and str(x.get("name", "")).startswith(
                        "Opening railing") and ring.contains(
                        LineString([x["a"], x["b"]])):
                    k += 1
                    x["name"] = f"Opening parapet {k}"
            return True
    w["name"] = "Railing"                 # its hole not found: kept as it is
    return True


def opening_parapets(doc) -> int:
    """The railings made here (remade every rebuild): the terrace railing on
    its upstand round the roof's edge (``roof_parapet``) and round every
    opening drawn by hand in a slab or the roof. How many."""
    import math as _m

    from shapely.geometry import Polygon
    arch = doc["arch"]
    st = doc["settings"]
    # made again only when what they follow changed (the roof's outline,
    # the openings, the railing settings) — a railing edited by hand with
    # its handles keeps the edit until then
    import hashlib
    sig_src = repr((
        sorted(repr((e["level"], bool(e.get("roof")), e.get("offset"),
                     e.get("t"), e["corners"], e.get("holes")))
               for e in arch["structure"] if e["type"] == "slab"
               and not e.get("grade") and not e.get("zone")
               and (e.get("roof") or e.get("holes"))),
        sorted(repr((m.get("level"), m.get("pts"))) for m in
               doc.get("man_shafts") or []),
        [st.get(k) for k in ("parapet_rail", "rail_h", "terrace_curb_h",
                             "terrace_rail_kind", "roof_parapet",
                             "roof_parapet_h", "slab_pos")]))
    sig = hashlib.md5(sig_src.encode()).hexdigest()
    have = [w for w in arch["walls"]
            if str(w.get("name", "")).startswith(AUTO_RAIL)]
    if have and st.get("auto_rail_sig") == sig:
        return len(have)
    st["auto_rail_sig"] = sig
    arch["walls"] = [w for w in arch["walls"]
                     if not str(w.get("name", "")).startswith(AUTO_RAIL)]
    if slab_on_top(doc):
        return 0
    rk = st.get("parapet_rail", "ss_bars")
    rk = rk if rk and rk != "solid" else "ss_bars"
    rh = float(st.get("rail_h", 1.0668))
    ch_ = float(st.get("terrace_curb_h", 0.3048) or CURB_H)
    as_wall = terrace_as_wall(st)
    o_ = CURB_T / 2
    recs = []

    def ring(pts, lid, base, cd, inward, name, h_=None):
        rh_ = rh if h_ is None else float(h_)
        p = Polygon(pts).buffer(0)
        if p.is_empty or p.area < 0.04:
            return
        q = p.buffer(-o_ if inward else o_, join_style=2)
        if q.is_empty:
            return
        q = max(getattr(q, "geoms", [q]), key=lambda g: g.area)
        cs = list(q.exterior.coords)[:-1]
        for a, b in zip(cs, cs[1:] + cs[:1]):
            if _m.dist(a, b) < 0.05:
                continue
            r = {"kind": "line", "a": [round(a[0], 4), round(a[1], 4)],
                 "b": [round(b[0], 4), round(b[1], 4)], "align": "centre",
                 "side": 1, "base": round(base, 4), "level": lid,
                 "name": name}
            if as_wall:
                r.update(t=PARAPET_T, height=round(base + rh_, 4),
                         type="solid")
            else:
                r.update(t=0.05, height=round(base + rh_, 4), rail=rk,
                         curb_h=round(ch_, 4), curb_t=CURB_T,
                         curb_d=round(cd, 4))
            recs.append(r)
    # (a lift well, a duct read from the CAD: walled round, no railing)
    man = [Polygon(m["pts"]).buffer(0) for m in doc.get("man_shafts") or []
           if not (m.get("auto") == "lift" or m.get("auto") and re.search(
               r"DUCT|SHAFT|P\.?\s?D", str(m.get("note", "")), re.I))]
    frozen = {tuple(k) for k in st.get("rail_frozen") or []}
    stairs_up = [Polygon([tuple(p[:2]) for p in s_["corners"]]).buffer(0)
                 for s_ in doc.get("stairs") or []          # up to the roof
                 if not s_.get("to") and len(s_.get("corners") or []) >= 3]
    for e in arch["structure"]:
        if e["type"] != "slab" or e.get("grade") or e.get("zone"):
            continue
        lv = level_by_id(arch, e["level"])
        if lv is None:
            continue
        roof = bool(e.get("roof"))
        base = (float(lv.get("height") or 3.0) if roof else 0.0) + float(
            e.get("offset", 0.0) or 0.0)
        cd = float(e.get("t", 0.1016) or 0.1016)
        if roof and st.get("roof_parapet", True):
            ring(e["corners"], e["level"], base, cd, True,
                 "Roof edge railing", st.get("roof_parapet_h") or None)
        for h in e.get("holes") or []:       # the openings drawn by hand
            try:
                hp = Polygon(h).buffer(0)
            except Exception:  # noqa: BLE001
                continue
            if _hole_key(e["level"], hp) in frozen:
                continue                     # its railing edited by hand
            if any(hp.intersects(m) and hp.intersection(m).area >
                   0.5 * hp.area for m in man + (stairs_up if roof else [])):
                ring(h, e["level"], base, cd, False, "Opening railing")
    made = M.new_walls(arch["walls"], recs)
    for w, r in zip(made, recs):
        w["name"] = r["name"]
    arch["walls"] += made
    return len(made)


def to_floor_slabs(doc, t=0.1016) -> int:
    """A project made with slabs over each floor turned to slabs as floors:
    each floor's slab under it (the ground floor on the ground, its
    finishes only), ``t`` thick where they had the old default thickness —
    the walls follow. How many slabs changed thickness."""
    st = doc["settings"]
    old = float(st.get("slab_t", 0.15) or 0.15)
    st["slab_pos"] = "bottom"
    st["slab_t"] = round(float(t), 4)
    st.setdefault("ground_slab", False)
    n = 0
    for e in doc["arch"]["structure"]:
        if e["type"] != "slab" or e.get("zone") or e.get("user") or \
                e.get("roof"):
            continue
        if abs(float(e.get("t", old)) - old) < 1e-4 or \
                abs(float(e.get("t", old)) - 0.15) < 1e-4:
            e["t"] = round(float(t), 4)
            n += 1
    apply_slab_pos(doc)
    return n


def apply_slab_pos(doc) -> None:
    """The levels' main slabs marked for where they stand (``top``: over
    the floor) — the CAD zones, the parts sunk / raised and the roof
    slabs keep theirs."""
    on_top = slab_on_top(doc)
    ground = {lv["id"] for lv in doc["arch"]["levels"]
              if lv.get("kind") == "ground"}
    grade = not on_top and not ground_slab_on(doc)
    for s in doc["arch"]["structure"]:
        if s["type"] != "slab" or s.get("zone") or s.get("user") \
                or s.get("roof"):
            continue
        if on_top:
            s["top"] = True
        else:
            s.pop("top", None)
        # slabs as floors: the ground floor on the ground — its slab
        # outline kept for the floor finish (rooms, verandah, lobby, porch)
        # but no concrete slab made
        if grade and s["level"] in ground:
            s["grade"] = True
        else:
            s.pop("grade", None)


def _floor_slabs(doc, lid) -> list:
    """The slab records that make the floor of level ``lid``: with slabs
    cast over each floor, the main slab of the level below (and this
    level's own sunk / raised parts); else this level's slabs."""
    arch = doc["arch"]
    slabs = [s for s in arch["structure"] if s["type"] == "slab"]
    if not slab_on_top(doc):
        return [s for s in slabs if s["level"] == lid and not s.get("roof")]
    el = elevations(arch)
    order = [arch["levels"][i]["id"] for i in
             sorted(range(len(arch["levels"])), key=lambda i: el[i])]
    k = order.index(lid) if lid in order else -1
    below = order[k - 1] if k > 0 else None
    out = [s for s in slabs if s["level"] == lid and not s.get("top")]
    if below is not None:
        out += [s for s in slabs if s["level"] == below and s.get("top")]
    return out or [s for s in slabs if s["level"] == lid]


def add_man_shaft(doc, lid, pts, through=False, z=None,
                  roof=None) -> str | None:
    """A shaft / slab opening drawn by hand on the floor of ``lid`` (or
    through every floor): kept in ``doc["man_shafts"]`` and cut again into
    the slabs at every rebuild. Its id, or None when it cuts no slab."""
    import uuid
    from shapely.geometry import Polygon
    g = Polygon(pts).buffer(0)
    if g.is_empty or g.area < 0.04:
        return None
    if g.geom_type != "Polygon":
        g = max(g.geoms, key=lambda q: q.area)
    rec = {"id": uuid.uuid4().hex[:8], "level": lid, "through": bool(through),
           "pts": [[round(x, 4), round(y, 4)]
                   for x, y in list(g.exterior.coords)[:-1]]}
    if roof is None and z is not None and not through:
        rt = roof_top(doc, lid)            # drawn on the roof over it
        roof = rt is not None and abs(float(z) - rt) < 0.45
    if roof:
        rec["roof"] = True
    doc.setdefault("man_shafts", []).append(rec)
    n = apply_man_shafts(doc)
    if not n.get(rec["id"]):
        doc["man_shafts"].remove(rec)
        apply_man_shafts(doc)
        return None
    return rec["id"]


def remove_man_shaft(doc, sid) -> bool:
    before = len(doc.get("man_shafts") or [])
    doc["man_shafts"] = [m for m in doc.get("man_shafts") or []
                         if m["id"] != sid]
    apply_man_shafts(doc)
    return len(doc["man_shafts"]) < before


def _top_stair_wells(doc) -> None:
    """The top floor's stair, with the roof over it: its well cut in the
    roof (it arrives on the roof, railed round) — an automatic cut,
    remade at every rebuild."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    doc["man_shafts"] = [m for m in doc.get("man_shafts") or []
                         if m.get("auto") != "stair"]
    roofed = {s_["level"] for s_ in doc["arch"]["structure"]
              if s_["type"] == "slab" and s_.get("roof")}
    from . import stairs as ST
    for st in doc.get("stairs") or []:
        if st.get("to") or st.get("level") not in roofed:
            continue
        try:
            fl, ld = ST.as_flights(st)
            ps = []
            for f in fl:
                pts = [tuple(q[:2]) for ln in f["lines"] for q in ln]
                if len(pts) >= 3:
                    ps.append(Polygon(pts).convex_hull)
            for lg in ld:
                if not lg.get("arrival") and not lg.get("top"):
                    ps.append(Polygon([tuple(q[:2]) for q in lg["corners"]])
                              .buffer(0))
            g = unary_union(ps).buffer(0.05, join_style=2)
            g = g.convex_hull if g.geom_type != "Polygon" else g
        except Exception:  # noqa: BLE001
            continue
        doc["man_shafts"].append(
            {"id": "st" + str(st.get("id", ""))[:6], "level": st["level"],
             "through": False, "auto": "stair", "up": True, "own": False,
             "note": "STAIR",
             "pts": [[round(x, 4), round(y, 4)]
                     for x, y in list(g.exterior.coords)[:-1]]})


def apply_man_shafts(doc) -> dict:
    """The hand-drawn openings cut into the slabs they cross (the earlier
    cuts first taken out, so it can run at every rebuild): {id: slabs}."""
    from shapely.geometry import Polygon
    try:
        _top_stair_wells(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._top_stair_wells")
    arch = doc["arch"]
    slabs = [s for s in arch["structure"] if s["type"] == "slab"]
    # the same shaft drawn twice: once
    seen_, ms_ = set(), []
    for m in doc.get("man_shafts") or []:
        k_ = (m.get("level"), bool(m.get("through")),
              tuple(sorted((round(p[0], 2), round(p[1], 2))
                           for p in m["pts"])))
        if k_ not in seen_:
            seen_.add(k_)
            ms_.append(m)
    doc["man_shafts"] = ms_

    def _key(h):
        return tuple(sorted((round(p[0], 2), round(p[1], 2)) for p in h))
    # the earlier hand cuts out — by the «man» list, and (the loader does
    # not keep it) by their shapes: the holes cut by a hand-drawn shaft
    cut_keys = set()
    for m in ms_:
        try:
            hp = Polygon(m["pts"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        for s in slabs:
            try:
                g = hp.intersection(Polygon(s["corners"]).buffer(0)
                                    .buffer(-0.01))
            except Exception:  # noqa: BLE001
                continue
            for g_ in getattr(g, "geoms", [g]):
                if g_.geom_type == "Polygon" and g_.area >= 0.04:
                    cut_keys.add(_key([[x, y] for x, y in
                                       list(g_.exterior.coords)[:-1]]))
    for s in slabs:
        man = s.pop("man", None) or []
        mk = {_key(h) for h in man} | cut_keys
        if mk:
            s["holes"] = [h for h in s.get("holes") or [] if _key(h) not in mk]
            s["shafts"] = [h for h in s.get("shafts") or []
                           if _key(h) not in mk]
        # and any hole twice: once
        u_, hs_ = set(), []
        for h in s.get("holes") or []:
            if _key(h) not in u_:
                u_.add(_key(h))
                hs_.append(h)
        s["holes"] = hs_
    out = {}
    for m in doc.get("man_shafts") or []:
        hp = Polygon(m["pts"]).buffer(0)
        if m.get("auto"):                 # read from the CAD (fitout.py)
            from . import fitout as FO_
            targets = FO_.cut_targets(doc, m, slabs)
        else:
            targets = slabs if m.get("through") else (
                [s_ for s_ in slabs if s_["level"] == m["level"]
                 and s_.get("roof")] if m.get("roof")
                else _floor_slabs(doc, m["level"]))
        n = 0
        for s in targets:
            try:
                sp = Polygon(s["corners"]).buffer(0)
                cut = hp.intersection(sp.buffer(-0.01))
            except Exception:  # noqa: BLE001
                continue
            for g in getattr(cut, "geoms", [cut]):
                if g.geom_type != "Polygon" or g.area < 0.04:
                    continue
                h = [[round(x, 4), round(y, 4)]
                     for x, y in list(g.exterior.coords)[:-1]]
                s.setdefault("holes", []).append(h)
                s.setdefault("shafts", []).append(h)
                s.setdefault("man", []).append(h)
                n += 1
        out[m["id"]] = n
    # holes that overlap (a shaft drawn over a stair well, over another
    # shaft) joined: a slab face never has two holes over each other
    from shapely.ops import unary_union
    for s in slabs:
        hs = s.get("holes") or []
        if len(hs) < 2:
            continue
        try:
            ps = [Polygon(h).buffer(0) for h in hs if len(h) >= 3]
            if not any(ps[i].intersects(ps[j]) for i in range(len(ps))
                       for j in range(i + 1, len(ps))):
                continue
            u = unary_union(ps)
            s["holes"] = [[[round(x, 4), round(y, 4)] for x, y in
                           list(g.exterior.coords)[:-1]]
                          for g in getattr(u, "geoms", [u])
                          if g.geom_type == "Polygon" and g.area >= 0.04]
        except Exception:  # noqa: BLE001
            pass
    return out


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


def labelled_shafts(pl, have=()) -> list:
    """The shafts a plan names («GEN SHAFT», «IT SHAFT», «DUCT») where it
    draws them as a box crossed by an X on some layer that is not a hole
    layer: the box round the label, if an X crosses it. [outline]."""
    import re as _re

    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union
    out = []
    got = [Polygon(h).buffer(0.02) for h in have if len(h) >= 3]
    segs = pl.get("segs") or []
    for t in pl.get("texts") or []:
        if not _re.search(r"SHAFT|\bDUCT|\bP\.?\s?S\.?\b",
                          str(t.get("text", "")).upper()):
            continue
        P_ = Point(t["x"], t["y"])
        if any(g.contains(P_) for g in got):
            continue
        near = []
        for s_ in segs:
            if min(s_[0], s_[2]) > t["x"] + 2.0 or \
                    max(s_[0], s_[2]) < t["x"] - 2.0 or \
                    min(s_[1], s_[3]) > t["y"] + 2.0 or \
                    max(s_[1], s_[3]) < t["y"] - 2.0:
                continue
            a, b = (s_[0], s_[1]), (s_[2], s_[3])
            L = math.dist(a, b)
            if L < 0.05:
                continue
            ex, ey = (b[0] - a[0]) / L * 0.005, (b[1] - a[1]) / L * 0.005
            near.append(LineString([(a[0] - ex, a[1] - ey),
                                    (b[0] + ex, b[1] + ey)]))
        if len(near) < 4:
            continue
        faces = [f for f in polygonize(unary_union(near))
                 if 0.05 <= f.area <= 12.0]
        # the X splits the box in four: their union is the box
        box = None
        for f in sorted(faces, key=lambda f: f.area):
            if f.buffer(0.01).contains(P_):
                box = f
                break
        if box is None:
            continue
        # the box: the smallest ring of faces round the label that a
        # diagonal crosses — grow it over its neighbours sharing the X
        u = unary_union([f for f in faces
                         if f.buffer(0.01).intersects(box)
                         and f.area <= 4 * box.area]).buffer(0)
        hull = u.minimum_rotated_rectangle
        diag = math.dist(*list(hull.exterior.coords)[:2]) ** 2 + \
            math.dist(*list(hull.exterior.coords)[1:3]) ** 2
        diag = math.sqrt(diag)
        x_ = 0
        for ln in near:
            if ln.length >= 0.6 * diag and hull.buffer(0.03).contains(ln) \
                    and not any(abs(ln.length - math.dist(*e)) < 0.02
                                for e in zip(list(hull.exterior.coords)[:-1],
                                             list(hull.exterior.coords)[1:])):
                x_ += 1
        if x_ < 1 or hull.area > 12.0:
            continue
        out.append([(round(x, 4), round(y, 4))
                    for x, y in list(hull.exterior.coords)[:-1]])
        got.append(hull.buffer(0.02))
    return out


def add_labelled_shafts(doc, lids=None) -> int:
    """The named shafts (``labelled_shafts``) of the levels' CAD plans cut
    into the slabs that hold them, now — without importing again."""
    from shapely.geometry import Polygon
    n = 0
    for lid, how in (doc.get("imports") or {}).items():
        if lids is not None and lid not in lids:
            continue
        if not isinstance(how, dict) or not how.get("file"):
            continue
        try:
            drawing = cadread.crop(cadread.read(how["file"], how.get("unit")),
                                   how.get("region"))
            base = cadread.base_point(drawing, how.get("base", "origin"),
                                      (how.get("bx", 0.0), how.get("by", 0.0)))
            pl = cadread.place(drawing, base, (how.get("ix", 0.0),
                                               how.get("iy", 0.0)),
                               how.get("rot", 0.0))
        except Exception:  # noqa: BLE001
            continue
        slabs = [e for e in doc["arch"]["structure"] if e["type"] == "slab"
                 and e["level"] == lid and e.get("corners")]
        have = [h for e in slabs for h in e.get("holes") or []]
        for sh in labelled_shafts(pl, have):
            hp = Polygon(sh)
            for e in slabs:
                try:
                    if Polygon(e["corners"]).buffer(-0.02).contains(
                            hp.representative_point()):
                        h = [[round(x, 4), round(y, 4)] for x, y in sh]
                        e.setdefault("holes", []).append(h)
                        e.setdefault("shafts", []).append(h)
                        n += 1
                        break
                except Exception:  # noqa: BLE001
                    continue
    return n


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


def cornerwin_to_curtain(doc, wid) -> list:
    """A corner window made a curtain wall, floor to top round its corner
    (each leg a curtain wall, its grid about 4'-0", the corner post kept
    as the legs meet) — so doors can go into its panels. The legs' ids."""
    arch = doc["arch"]
    w = next((x for x in arch["walls"] if x.get("id") == wid), None)
    if w is None or not w.get("cwin"):
        return []
    cid = w["cwin"]
    ids = []
    for x in arch["walls"]:
        if x.get("cwin") != cid:
            continue
        for k in ("cwin", "cwin_h", "cw_low"):
            x.pop(k, None)
        x["type"] = "curtain"
        L = math.dist(x["a"], x["b"])
        x["grid"] = round(max(0.6, L / max(1, round(L / 1.2))), 4)
        x["cw_low"] = 0.0
        ids.append(x["id"])
    arch["openings"] = [o for o in arch["openings"]
                        if not (o["wall"] in ids and o["kind"] == "window")]
    return ids


def opening_convert(doc, oid, kind) -> tuple:
    """An opening made a door, a window, a plain opening (no door) or a
    piece of curtain wall (the wall cut at its jambs, that part glazed
    floor to top, its grid kept). (the record changed / the new curtain
    wall, None) or (None, why)."""
    arch = doc["arch"]
    o = next((x for x in arch["openings"] if x.get("id") == oid), None)
    if o is None:
        return None, "no such opening"
    if kind in ("door", "window", "void"):
        if o["kind"] == kind:
            return o, None
        new = dict(opening_as(dict(o), kind, doc["settings"]),
                   w=o["w"], pos=o["pos"], id=o["id"])
        if kind == "door":
            new["sill"] = 0.0
        if kind != "void":
            new.pop("grille", None)
        why = check_record(doc, "opening", new)
        if why:
            return None, why
        o.clear()
        o.update(new)
        return o, None
    if kind != "curtain":
        return None, "unknown type"
    wid = o["wall"]
    s0 = float(o["pos"]) - float(o["w"]) / 2
    s1 = float(o["pos"]) + float(o["w"]) / 2
    arch["openings"] = [x for x in arch["openings"] if x is not o]
    pid, why = split_wall(doc, wid, s0, s1)
    if why:
        arch["openings"].append(o)
        return None, why
    to_curtain(doc, [pid])
    part = next((x for x in arch["walls"] if x["id"] == pid), None)
    if part is not None:
        L = math.dist(part["a"], part["b"])
        part["grid"] = round(max(0.6, L / max(1, round(L / 1.2))), 4)
    return part, None


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


def arch_blocks(arch, lid, pl, st) -> int:
    """Openings under a block whose name says ARCH (MEHRAB / KAMAN too):
    an arched head of the chosen shape. How many."""
    n = 0
    walls = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    for b in pl.get("inserts") or ():
        if not re.search(r"ARCH|MEHRAB|MIHRAB|KAMAN|ARCO", str(b.get("name",
                                                                    "")).upper()):
            continue
        cs = b.get("corners") or []
        if len(cs) < 4:
            continue
        c = (sum(p[0] for p in cs) / len(cs), sum(p[1] for p in cs) / len(cs))
        best = None
        for o in arch["openings"]:
            w = walls.get(o["wall"])
            if w is None or w.get("kind", "line") != "line":
                continue
            a, bb = w["a"], w["b"]
            L = math.dist(a, bb)
            if L < 1e-6:
                continue
            u = ((bb[0] - a[0]) / L, (bb[1] - a[1]) / L)
            m = (a[0] + u[0] * o["pos"], a[1] + u[1] * o["pos"])
            d = math.dist(m, c)
            if d < max(0.35, float(o["w"]) / 2) and (best is None or d < best[0]):
                best = (d, o)
        if best is None:
            continue
        o = best[1]
        if o.get("head") != "arch":
            o["head"] = "arch"
            o["arch"] = st.get("arch_style", "semi") or "semi"
            fit_head(o)
            n += 1
    return n


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
    elif o.get("kind") == "void" and st.get("void_arch") and \
            not o.get("grille"):
        o["head"] = "arch"
    if o.get("head") == "arch":            # its shape (S.ARCHES)
        o["arch"] = st.get("arch_style", "semi") or "semi"
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
            cs_ = ins.get("ocorners") or ins["corners"]
            al = [(c[0] - a[0]) * ux + (c[1] - a[1]) * uy for c in cs_]
            pe = [-(c[0] - a[0]) * uy + (c[1] - a[1]) * ux for c in cs_]
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


def add_beams_on_walls(doc, lid, w=0.2032, h=0.6096) -> int:
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


def beam_lines_between_columns(cols, max_span=10.0, tol_deg=4.0):
    """The beam lines of a column layout: each column joined to the nearest
    column in each of its four grid directions (its own angle and square to
    it), within ``max_span``; each run trimmed to the columns' faces.
    [((x, y), (x, y))]."""
    from shapely.geometry import LineString, Polygon
    pts = [(float(c["x"]), float(c["y"])) for c in cols]
    polys = []
    for c in cols:
        try:
            polys.append(Polygon(S.column_outline(c, 0.0)).buffer(0))
        except Exception:  # noqa: BLE001
            polys.append(None)
    pairs = set()
    tol = math.radians(tol_deg)
    for i, c in enumerate(cols):
        a0 = math.radians(float(c.get("angle", 0.0) or 0.0))
        for k in range(4):
            ang = a0 + k * math.pi / 2
            ux, uy = math.cos(ang), math.sin(ang)
            best = None
            for j, q in enumerate(pts):
                if j == i:
                    continue
                dx, dy = q[0] - pts[i][0], q[1] - pts[i][1]
                along = dx * ux + dy * uy
                if along <= 0.3 or along > max_span:
                    continue
                side = abs(-dx * uy + dy * ux)
                if side > max(0.3, min(0.6, along * math.tan(tol))):
                    continue
                if best is None or along < best[0]:
                    best = (along, j)
            if best is not None:
                pairs.add(tuple(sorted((i, best[1]))))
    out = []
    for i, j in sorted(pairs):
        L = LineString([pts[i], pts[j]])
        for p_ in (polys[i], polys[j]):
            if p_ is not None and not p_.is_empty:
                L = L.difference(p_)
        if L.is_empty:
            continue
        g = max(getattr(L, "geoms", [L]), key=lambda x: x.length)
        if g.length < 0.3:
            continue
        a_, b_ = list(g.coords)[0], list(g.coords)[-1]
        out.append(((a_[0], a_[1]), (b_[0], b_[1])))
    return out


def add_beams_on_columns(doc, lid, w=0.2032, h=0.6096,
                         max_span=10.0) -> int:
    """Beams column to column on level ``lid`` (each its own element, under
    the slab over the level), replacing the level's beams. The number made
    — 0 when the level has fewer than two columns."""
    arch = doc["arch"]
    cols = [e for e in arch["structure"]
            if e["type"] == "column" and e["level"] == lid]
    if len(cols) < 2:
        return 0
    recs = [{"type": "beam", "level": lid,
             "a": [round(a[0], 4), round(a[1], 4)],
             "b": [round(b[0], 4), round(b[1], 4)],
             "w": w, "h": h, "fit": False}
            for a, b in beam_lines_between_columns(cols, max_span)]
    recs = [r for r in recs if S.why_not(r) is None]
    arch["structure"] = [e for e in arch["structure"]
                         if not (e["type"] == "beam" and e["level"] == lid)]
    arch["structure"] += M.new_elements(arch["structure"], recs)
    return len(recs)


FOUNDATION_TYPES = [
    ("isolated_strip", "Isolated pads + strip footings (under columns and "
                       "walls)"),
    ("isolated", "Isolated footings (pads under the columns)"),
    ("strip", "Strip footings (under the walls)"),
    ("combined", "Combined footings (columns close together share one)"),
    ("raft", "Raft / mat foundation (one slab under the building)")]


def align_beam(doc, bid, how="centre", reach=0.8) -> bool:
    """A beam slid sideways onto its columns: ``how`` = «centre» (on the
    columns' centre line), «left» / «right» — flush with the columns' face
    on that side in plan (for a beam running across the plan: «left» = the
    top face, «right» = the bottom face). The columns are those at its
    ends (within ``reach``). False when it reaches no column."""
    from shapely.geometry import Point, Polygon
    arch = doc["arch"]
    b = next((e for e in arch["structure"]
              if e["type"] == "beam" and e["id"] == bid), None)
    if b is None:
        return False
    a_, b_ = tuple(b["a"]), tuple(b["b"])
    L = math.dist(a_, b_)
    if L < 0.05:
        return False
    u = ((b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L)
    n = (-u[1], u[0])
    # «left / top» in plan: the side of smaller x for a beam running up the
    # plan, of larger y for one running across it
    if abs(u[1]) > abs(u[0]):
        if n[0] > 0:
            n = (-n[0], -n[1])
    elif n[1] < 0:
        n = (-n[0], -n[1])
    cols = [e for e in arch["structure"]
            if e["type"] == "column" and e["level"] == b["level"]]
    ext = []
    for end in (a_, b_):
        best = None
        for c in cols:
            try:
                pg = Polygon(S.column_outline(c, 0.0))
            except Exception:  # noqa: BLE001
                continue
            d = pg.distance(Point(end))
            if d <= reach and (best is None or d < best[0]):
                best = (d, pg)
        if best is not None:
            vs = [(q[0] - a_[0]) * n[0] + (q[1] - a_[1]) * n[1]
                  for q in list(best[1].exterior.coords)]
            ext.append((min(vs), max(vs)))
    if not ext:
        return False
    w = float(b.get("w", 0.2))
    if how == "left":
        off = min(hi for _lo, hi in ext) - w / 2
    elif how == "right":
        off = max(lo for lo, _hi in ext) + w / 2
    else:
        off = sum((lo + hi) / 2 for lo, hi in ext) / len(ext)
    if abs(off) < 1e-4:
        return True
    b["a"] = [round(a_[0] + n[0] * off, 4), round(a_[1] + n[1] * off, 4)]
    b["b"] = [round(b_[0] + n[0] * off, 4), round(b_[1] + n[1] * off, 4)]
    return True


def beams_at_column(doc, cid, reach=0.8) -> list:
    """The ids of the beams that end at column ``cid``."""
    from shapely.geometry import Point, Polygon
    arch = doc["arch"]
    c = next((e for e in arch["structure"]
              if e["type"] == "column" and e["id"] == cid), None)
    if c is None:
        return []
    pg = Polygon(S.column_outline(c, 0.0))
    return [e["id"] for e in arch["structure"]
            if e["type"] == "beam" and e["level"] == c["level"] and
            min(pg.distance(Point(e["a"])), pg.distance(Point(e["b"])))
            <= reach]


def add_footings(doc, pad=1.2, pad_d=None, strip=0.6, strip_d=None,
                 kind="isolated_strip", raft_t=0.6096,
                 raft_off=0.6096) -> int:
    """The foundation under the lowest level, down to the foundation level
    (unless depths are given), replacing the footings there:

    - ``isolated``: a pad under every column;
    - ``strip``: a strip under every wall;
    - ``isolated_strip``: both (as before);
    - ``combined``: pads, columns whose pads would touch (or come within
      1'-0") sharing one rectangular footing;
    - ``raft``: one raft ``raft_t`` thick under the whole building, out
      ``raft_off`` past its walls and columns."""
    arch = doc["arch"]
    d = footing_depth(doc)
    pad_d = d if pad_d is None else pad_d
    strip_d = d if strip_d is None else strip_d
    low = arch["levels"][0]["id"]
    arch["structure"] = [e for e in arch["structure"] if e["type"] != "footing"]
    cols = [e for e in arch["structure"]
            if e["type"] == "column" and e["level"] == low
            and e.get("role") != "architectural"]
    walls = [w for w in arch["walls"] if w["level"] == low]
    pads = [{"type": "footing", "level": low, "kind": "pad", "x": e["x"],
             "y": e["y"], "w": pad, "d": pad_d, "angle": e.get("angle", 0.0)}
            for e in cols]
    recs = []
    if kind in ("isolated", "isolated_strip"):
        recs += pads
    if kind in ("strip", "isolated_strip"):
        recs += [dict(r, type="footing", level=low, kind="strip", w=strip,
                      d=strip_d) for r in S.strips_under(walls)]
    if kind == "combined":
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        polys = [Polygon(S.pad_outline(p_)) for p_ in pads]
        groups, seen = [], set()
        for i in range(len(pads)):          # pads closer than 1'-0": joined
            if i in seen:
                continue
            g, todo = [], [i]
            seen.add(i)
            while todo:
                k = todo.pop()
                g.append(k)
                for j in range(len(pads)):
                    if j not in seen and polys[k].distance(polys[j]) < 0.3048:
                        seen.add(j)
                        todo.append(j)
            groups.append(g)
        for g in groups:
            if len(g) == 1:
                recs.append(pads[g[0]])
                continue
            r = unary_union([polys[k] for k in g]).minimum_rotated_rectangle
            recs.append({"type": "footing", "level": low, "kind": "combined",
                         "corners": [[round(x, 4), round(y, 4)] for x, y in
                                     list(r.exterior.coords)[:-1]],
                         "w": round(min(r.bounds[2] - r.bounds[0],
                                        r.bounds[3] - r.bounds[1]), 3),
                         "d": pad_d,
                         "name": f"Combined footing ({len(g)} columns)"})
    if kind == "raft":
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        parts = []
        try:
            plans = W.plan([w for w in walls if W.why_not(w) is None])
            parts += [Polygon(pc["outer"]) for ps in plans.values()
                      for pc in ps]
        except Exception:  # noqa: BLE001
            pass
        parts += [Polygon(S.column_outline(c, 0.0)) for c in cols]
        parts = [p_.buffer(0) for p_ in parts if not p_.is_empty]
        if parts:
            u = unary_union(parts).buffer(3.0, join_style=2).buffer(
                -3.0, join_style=2)
            for g_ in getattr(u, "geoms", [u]):
                if g_.geom_type != "Polygon" or g_.area < 4.0:
                    continue
                r = Polygon(g_.exterior).buffer(raft_off, join_style=2)
                r = r.simplify(0.02)
                recs.append({"type": "footing", "level": low, "kind": "raft",
                             "corners": [[round(x, 4), round(y, 4)] for x, y
                                         in list(r.exterior.coords)[:-1]],
                             "w": 1.0, "d": round(float(raft_t), 4),
                             "name": "Raft foundation"})
    recs = [r for r in recs if S.why_not(r) is None]
    arch["structure"] += M.new_elements(arch["structure"], recs)
    doc["settings"]["found_type"] = kind
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
    if kind == "furniture":
        return next((f for f in doc.get("furniture") or []
                     if f["id"] == rid), None)
    pool = arch[LISTS.get(kind, "structure")]
    return next((r for r in pool if r["id"] == rid), None)


def delete_record(doc, kind, rid, seg=None) -> None:
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
    elif kind == "furniture":
        doc["furniture"] = [f for f in doc.get("furniture") or []
                            if f["id"] != rid]
    elif kind == "stairrail":      # the stair stays, without its railing
        s = find_record(doc, "stair", rid)
        if s is not None:
            if seg is not None:    # one straight piece of it only
                sk = set(int(k) for k in s.get("rail_skip") or [])
                sk.add(int(seg))
                s["rail_skip"] = sorted(sk)
            else:
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
        gone = [e for e in arch["structure"] if e["id"] == rid]
        arch["structure"] = [e for e in arch["structure"] if e["id"] != rid]
        if any(e.get("auto_roof") for e in gone):
            # the roof slab deleted: not made again by itself
            doc["settings"]["roof_auto"] = False


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


def _type_mirror(e, recs, walls_by, cat):
    """(about x, about y) when the element's component type is mirrored,
    else None."""
    if not cat:
        return None
    from . import components as CP
    rec = recs.get(("opening" if e["kind"] == "opening" else e["kind"],
                    e["id"]))
    if rec is None:
        return None
    tk = CP.type_of(e["kind"], rec, walls_by)
    t = cat.get(tk[1]) if tk else None
    m = (t or {}).get("mirror") or {}
    if m.get("x") or m.get("y"):
        return (bool(m.get("x")), bool(m.get("y")))
    return None


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
    try:                    # the car ramps: walls and beams stop under them
        arch["_ramps"] = ramp_solids(doc) if doc is not None else []
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.ramp_solids")
        arch["_ramps"] = []
    try:                    # doors stand on their thresholds
        arch["_door_lift"] = door_lifts(doc) if doc is not None else {}
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.door_lifts")
        arch["_door_lift"] = {}
    if doc is not None:          # the floor finish: a curtain wall's foot
        st_ = doc.get("settings") or {}
        arch["_fin_t"] = float(st_.get("finish_t", 0.0508) or 0.0) \
            if st_.get("finish_on", True) else 0.0
    try:
        elems = S.build(arch, M.elevations)
    finally:
        arch.pop("_ramps", None)
        arch.pop("_door_lift", None)
        arch.pop("_fin_t", None)
    # 0: the lines where two walls meet — hidden (clean junctions)
    seam = {}
    try:
        from . import seams as SM
        by_lv, slabs_ = {}, []
        for i_, e in enumerate(elems):
            if e["kind"] == "wall" and not (recs.get(("wall", e["id"]))
                                            or {}).get("rail"):
                by_lv.setdefault(e["level"], []).append((i_, e["faces"]))
            elif e["kind"] == "slab":
                slabs_.append((i_, e["faces"]))
        sol_ = SM.solids_of([x for v in by_lv.values() for x in v]
                            + slabs_)
        for lv_, ws_ in by_lv.items():
            seam.update(SM.hidden_edges(ws_, solids=sol_))
        if slabs_:
            seam.update(SM.hidden_edges([], slabs_, solids=sol_))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.seams")
        seam = {}
    # 1: each element in its own frame, and how many share its shape
    prep, count = [], {}
    id_of = {id(e): i_ for i_, e in enumerate(elems)}
    for i_, e in enumerate(elems):
        z0 = info[e["level"]]["z0"] if e["level"] in info else 0.0
        fr = CP.frame_of_element(e, arch, walls_by, z0)
        lf = CP.local_faces(e["faces"], fr)
        # a type mirrored (Edit type ▸ Mirror): its elements drawn flipped
        mir = _type_mirror(e, recs, walls_by, cat)
        if mir:
            lf = CP.mirror_lf(lf, *mir)
        hid = SM.to_local(seam[i_], fr) if (i_ in seam and not mir) \
            else frozenset()
        key = (e["kind"], CP.shape_key(lf), hid)
        count[key] = count.get(key, 0) + 1
        prep.append((e, fr, lf, key, bool(mir)))
    protos: dict = {}

    def mesh_of(lf, hid=frozenset()):
        mesh = Mesh()
        for lp, hs, col in lf:
            face = _safe_add(mesh, [QVector3D(*q) for q in lp],
                                 [[QVector3D(*q) for q in h] for h in hs])
            if col is not None and face is not None:
                face.attrs["color"] = col[:3]
                if len(col) > 3 and col[3] < 1.0:
                    face.attrs["opacity"] = col[3]
        _soften(mesh)
        if hid:
            try:
                SM.apply(mesh, hid)
            except Exception:  # noqa: BLE001
                pass
        return mesh
    out = []
    st_ = (doc or {}).get("settings") or {}
    cols_by = {c_["id"]: c_ for c_ in arch["structure"]
               if c_["type"] == "column"}
    cols_lib_off = False
    for e, fr, lf, key, mirrored in prep:
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
        if not (t and t.get("lib")) and e["kind"] == "column" and \
                st_.get("round_lib", True) and not cols_lib_off:
            c_ = cols_by.get(e["id"])
            if c_ is not None and c_.get("shape") == "round":
                # a round column: the IngeTrazo library's column, its shaft
                # as thick as the plan's circle (base and capital wider)
                try:
                    from . import library as LB
                    key_ = str(st_.get("round_lib_key") or ROUND_LIB)
                    shaft = float(c_.get("shaft") or c_["w"])
                    W_ = shaft * ROUND_LIB_K
                    H_ = max(q[2] for lp_, _h, _c in lf for q in lp_)
                    Z0_ = min(q[2] for lp_, _h, _c in lf for q in lp_)
                    lfb = [([(-W_ / 2, -W_ / 2, Z0_), (W_ / 2, W_ / 2, H_)],
                            [], None)]
                    lg = LB.groups_for({"key": key_, "fit": "stretch"}, fr,
                                       lfb, name,
                                       level_layer(names[e["level"]]), tag,
                                       {"class": cls, "name": name}
                                       if cls else None)
                except Exception:  # noqa: BLE001
                    from .host import log_error
                    log_error("project._groups round column")
                    lg = None
                if lg:
                    out += lg
                    continue
        if t and t.get("lib"):                # an IngeTrazo library model
            try:
                from . import library as LB
                m_ = (t.get("mirror") or {})
                lg = LB.groups_for(t["lib"], fr, lf, name,
                                   level_layer(names[e["level"]]), tag,
                                   {"class": cls, "name": name}
                                   if cls else None,
                                   (bool(m_.get("x")), bool(m_.get("y"))))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project._groups library")
                lg = None
            if lg:
                out += lg
                continue
        if count[key] > 1 or mirrored:        # a component: shared mesh
            if key not in protos:
                protos[key] = mesh_of(lf, key[2])
            g = Group(protos[key], name=name)
            g.xform = CP.placement(fr)
            g.component = True
        else:                                 # one of a kind: a group
            g = Group(mesh_of(CP.local_faces(e["faces"],
                                             (0.0, 0.0, 0.0, 0.0)),
                              SM.to_local(seam[id_of[id(e)]],
                                          (0.0, 0.0, 0.0, 0.0))
                              if id_of.get(id(e)) in seam and not mirrored
                              else frozenset()),
                      name=name)
            g.component = False
        g.material = {"color": COLOR[e["kind"]], "opacity": 1.0}
        if e["kind"] == "wall" and (walls_by.get(e["id"]) or {}).get("rcc"):
            g.material = {"color": COLOR["core"], "opacity": 1.0}
        g.layer = level_layer(names[e["level"]])
        cls = OPENING_IFC.get(e.get("okind")) if e["kind"] == "opening" \
            else IFC.get(e["kind"])
        if cls:
            g.ifc = {"class": cls, "name": name}
        if e["kind"] == "column" and \
                (cols_by.get(e["id"]) or {}).get("role") == "architectural":
            # an architectural column (a casing, a decorative pier): the
            # walls' finish, not structure (no footing, not in the RCC
            # schedules)
            g.material = {"color": COLOR["wall"], "opacity": 1.0,
                          "name": "Plaster, painted"}
            g.ifc = {"class": "IfcColumn", "name": name,
                     "predefined": "USERDEFINED",
                     "object_type": "Architectural column",
                     "load_bearing": False}
        elif e["kind"] == "column" and cls:
            g.ifc = dict(g.ifc or {}, load_bearing=True,
                         object_type="Structural column")
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
PARAPET_STYLES = [("plain", "Plain (plastered)"),
                  ("coping", "With coping (cap on top)"),
                  ("band", "Coping + a band under it"),
                  ("grille", "Coping + MS grille over it (1'-0\")")]


def _parapet_groups(doc, groups):
    """The solid parapets' design (``parapet_style``): a coping on their
    top (a band under it, or a short grille over it) — on every solid
    parapet: the terraces', the roof's, the balconies', the openings'."""
    from shapely.geometry import LineString

    from core.group import Group

    from . import slabedges as SE
    style = doc["settings"].get("parapet_style", "coping")
    if style == "plain":
        return []
    arch = doc["arch"]
    names = PARAPET_NAMES + AUTO_RAIL + ("Terrace railing",)
    walls = {w["id"]: w for w in arch["walls"]
             if str(w.get("name", "")).startswith(names)
             and not w.get("rail") and w.get("kind", "line") == "line"}
    if not walls:
        return []
    lvn = {lv["id"]: lv["name"] for lv in arch["levels"]}
    out = []
    for g in groups:
        t = tag_of(g) or {}
        w = walls.get(t.get("id")) if t.get("type") == "wall" else None
        if w is None or getattr(g, "mesh", None) is None:
            continue
        try:
            xf = g.xform
            zs = [(xf.map(v.position) if xf is not None else v.position).z()
                  for v in g.mesh.vertices]
            top = max(zs)
            fp = SE.wall_polys([w])
        except Exception:  # noqa: BLE001
            continue
        if not fp:
            continue
        foot = fp[0]
        for p_ in fp[1:]:
            foot = foot.union(p_)
        faces = _prism(foot.buffer(0.04, join_style=2), top, top + 0.075)
        if style == "band":
            faces += _prism(foot.buffer(0.02, join_style=2), top - 0.20,
                            top - 0.14)
        if style == "grille":
            from .engine import railings as RL
            c_ = W.centre(w)
            path = [(c_.p0[0], c_.p0[1], top + 0.075),
                    (c_.p1[0], c_.p1[1], top + 0.075)]
            if LineString(path).length > 0.3:
                faces += RL.faces(path, 0.3048, "ms_grill", t=0.03)
        if not faces:
            continue
        cg = Group(_mesh_of(faces), name=f"Coping · {w.get('name', 'parapet')}")
        cg.component = False
        cg.material = {"color": (0.62, 0.61, 0.59), "opacity": 1.0}
        cg.layer = g.layer
        cg.ext = {KEY: {"type": "coping", "id": f"cope-{w['id']}",
                        "level": w["level"]}}
        cg.ifc = {"class": "IfcCovering", "name": "Coping"}
        if w["level"] in lvn:
            out.append(cg)
    return out


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
        items = [("stair", parts, None)] + \
            [("stairrail", [r_], k_) for k_, r_ in enumerate(rails or [])
             if r_[0]]
        for kind, ps, seg in items:
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
            try:                         # a mirrored stair / railing type
                r_ = dict(recs.get(sid) or {},
                          **ST.eff(recs.get(sid) or {}, stt))
                tk_ = CP.type_of(kind, r_)
                m_ = ((cat.get(tk_[1]) or {}).get("mirror") or {}) \
                    if tk_ else {}
                if m_.get("x") or m_.get("y"):
                    lf = CP.mirror_lf(lf, bool(m_.get("x")),
                                      bool(m_.get("y")))
            except Exception:  # noqa: BLE001
                pass
            key = (kind, CP.shape_key(lf))
            count[key] = count.get(key, 0) + 1
            prep.append((kind, name, sid, lid, layer, z, lf, key, seg))
    protos, out = {}, []
    for kind, name, sid, lid, layer, z, lf, key, seg in prep:
        if key not in protos:
            mesh = Mesh()
            for lp, hs, col in lf:
                face = _safe_add(mesh, [QVector3D(*q) for q in lp],
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
                       **({"seg": seg} if seg is not None else {}),
                       **({"ctype": tk[1], "mark": t["mark"]} if t else {})}}
        if seg is not None:
            g.name = f"{nm} · piece {seg + 1} · {names[lid]}"
        out.append(g)
    return out


def _mesh_of(faces):
    from PySide6.QtGui import QVector3D

    from core.mesh import Mesh
    mesh = Mesh()
    for f in faces:
        face = _safe_add(mesh, [QVector3D(*q) for q in f["loop"]],
                             [[QVector3D(*q) for q in hh]
                              for hh in f.get("holes") or []])
        if face is not None and f.get("color") is not None:
            face.attrs["color"] = tuple(f["color"][:3])
    return mesh


def note_weight(doc, lid):
    """fn(x, y) → how much a level note there says «the floor's level»:
    the area of the room it stands in, 1 inside the building's outline
    (its walls' hull), none outside it (the verandah, the compound)."""
    try:
        from shapely.geometry import MultiPoint, Point
        arch = doc["arch"]
        rooms = [r["poly"] for r in spaces.of_level(arch, lid)
                 if r.get("poly") is not None]
        pts = [tuple(p) for w in arch["walls"] if w["level"] == lid
               and not w.get("rail") for p in (w["a"], w["b"])]
        hull = MultiPoint(pts).convex_hull.buffer(-0.3) if len(pts) >= 3 \
            else None
    except Exception:  # noqa: BLE001
        return None

    def fn(x, y):
        p = Point(x, y)
        for r in rooms:
            if r.contains(p):
                return max(float(r.area), 1.0)
        return 1.0 if hull is not None and hull.contains(p) else 0.0
    return fn


def cad_floor(marks, weight=None):
    """A level's own floor level from its CAD notes: ("rel", metres) — the
    most common «LEV. +4'-0"» (``weight(x, y)``: how much a note counts —
    a note in the building's big hall more than one on the verandah) —
    else ("abs", number) — the most common «LEV. 102.00» — else None.
    A stair's mid-landing note does not count."""
    from collections import Counter
    marks = [m for m in marks or () if not m.get("landing")]
    rel = Counter()
    for m in marks:
        if m.get("v") is not None:
            rel[round(m["v"], 4)] += (weight(m["x"], m["y"]) if weight
                                      else 1.0)
    rel = Counter({k: v for k, v in rel.items() if v > 0}) or Counter(
        round(m["v"], 4) for m in marks if m.get("v") is not None)
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
        f = cad_floor(doc["marks"].get(lv["id"]),
                      note_weight(doc, lv["id"]))
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
        if 0.0 < want[g] <= 3.0:        # «LEV. +4'-0"» over the road /
            st_ = doc["settings"]        # N.G.L. (±0): the F.F.L. field
            st_["ground_ffl"] = round(want[g], 4)
            st_["plinth"] = round(want[g], 4)
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
    marks = [m for m in marks if not m.get("landing")]
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


def slab_zones(doc, lid, pl=None, P=None) -> list:
    """One floor at several levels, as its CAD notes it: each room takes
    the level noted in it; the floor round the rooms is cut by the walls
    into its areas (the hall, the lobby, the verandah, the ablution…) and
    each takes the level noted in it — an area noted at several levels
    (a verandah all round) shared out between its notes, each part to
    the nearest. The level's slab cut in pieces at their own heights (an
    offset from the floor's level). Returns [(zone, offset m)] of the
    pieces not at the floor's level."""
    from collections import Counter

    from shapely.geometry import MultiPoint, Point, Polygon
    from shapely.ops import unary_union, voronoi_diagram

    from . import slabedges as SE
    arch = doc["arch"]
    notes = note_levels(doc, lid)
    if len(notes) < 2:
        return []
    f = cad_floor(doc["marks"].get(lid), note_weight(doc, lid))
    base = f[1] if f and f[0] == "rel" else Counter(
        round(v, 3) for _x, _y, v in notes).most_common(1)[0][0]
    slabs = [e for e in arch["structure"]
             if e["type"] == "slab" and e["level"] == lid
             and not e.get("zone")]
    if not slabs:
        return []
    for sl in slabs:                     # the open floor: the floor's level
        sl.pop("offset", None)
    rooms = [r["poly"] for r in spaces.of_level(arch, lid)
             if r.get("poly") is not None and r["area"] >= 1.0]
    floor = unary_union([Polygon(sl["corners"]).buffer(0) for sl in slabs])
    rooms_u = unary_union(rooms) if rooms else Polygon()
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and W.why_not(w) is None]
    try:
        WP = unary_union(SE.wall_polys(walls)).buffer(0.01)
    except Exception:  # noqa: BLE001
        WP = Polygon()

    def mode(vals):
        c = Counter(round(v, 3) for v in vals)
        return max(c.items(), key=lambda kv: (kv[1], -abs(kv[0] - base)))[0]
    t = float(slabs[0]["t"])
    holes_all = [Polygon(h).buffer(0) for sl in slabs
                 for h in sl.get("holes") or [] if len(h) >= 3]
    pieces = []                          # (polygon, level)
    # a level noted holds on its floor until a line parts it from the next
    # level noted: the step risers, the LINE layer's edges (a platform, a
    # sunk floor) — the walls and doors do not part the levels
    div = Polygon()
    if pl is not None and P is not None:
        from shapely.geometry import LineString as _LS
        pats = list(P.get("steps") or []) + list(P.get("lines") or [])
        lay = pl["layers"]
        segs_ = [_LS([(s_[0], s_[1]), (s_[2], s_[3])]) for s_ in pl["segs"]
                 if pats and _match(lay[s_[4]], pats)
                 and math.dist((s_[0], s_[1]), (s_[2], s_[3])) >= 0.3]
        if segs_:
            # a line stopping short of a wall or of another line (a step
            # drawn to the plaster's face, a gap at a door) carried on to
            # it, up to 1.2 m: the areas it parts are closed
            from shapely.geometry import Point as _Pt
            stop = unary_union([WP] + segs_) if not WP.is_empty else \
                unary_union(segs_)
            ext_ = []
            for g_ in segs_:
                (ax, ay), (bx, by) = g_.coords[0], g_.coords[-1]
                L_ = math.dist((ax, ay), (bx, by))
                ux, uy = (bx - ax) / L_, (by - ay) / L_
                ends = []
                for (px, py), sg in (((ax, ay), -1), ((bx, by), 1)):
                    far = (px + sg * ux * 1.2, py + sg * uy * 1.2)
                    ray = _LS([(px + sg * ux * 0.02, py + sg * uy * 0.02), far])
                    others = stop.difference(g_.buffer(0.01))
                    hit = ray.intersection(others)
                    if hit.is_empty:
                        ends.append((px, py))
                        continue
                    dd = min((_Pt(px, py).distance(q) for q in getattr(
                        hit, "geoms", [hit])), default=None)
                    ends.append((px + sg * ux * (dd + 0.03),
                                 py + sg * uy * (dd + 0.03))
                                if dd is not None else (px, py))
                ext_.append(_LS([ends[0], ends[1]]))
            div = unary_union([g_.buffer(0.03, cap_style=2) for g_ in ext_])

    def parts_of(region):
        """The region's rooms and its open areas (as the walls part them)."""
        out_ = []
        for r in rooms:
            q = r.intersection(region)
            if not q.is_empty and q.area >= 0.5:
                out_.append(q)
        rest = region.difference(rooms_u).difference(WP)
        for comp in getattr(rest, "geoms", [rest]):
            if comp.geom_type == "Polygon" and comp.area >= 0.5:
                out_.append(comp)
        return out_
    regions = floor.difference(div) if not div.is_empty else floor
    for R in getattr(regions, "geoms", [regions]):
        if R.geom_type != "Polygon" or R.area < 0.5:
            continue
        here = [(x, y, v) for x, y, v in notes if R.buffer(0.05).contains(
            Point(x, y))]
        if not here:
            continue                     # no note: the floor's own level
        vals = {round(v, 3) for _x, _y, v in here}
        if len(vals) == 1:
            pieces.append((R, here[0][2]))
            continue
        for q in parts_of(R):            # several levels, no line between
            vs = [v for x, y, v in here if q.buffer(0.05).contains(Point(x, y))]
            if not vs:                   # the nearest note's level
                c_ = q.representative_point()
                vs = [min(here, key=lambda n_: c_.distance(
                    Point(n_[0], n_[1])))[2]]
            if len({round(v, 3) for v in vs}) > 1 and len(vs) > 1:
                try:                     # each part to its nearest note
                    hq = [(x, y, v) for x, y, v in here
                          if q.buffer(0.05).contains(Point(x, y))]
                    cells = voronoi_diagram(MultiPoint(
                        [(x, y) for x, y, _v in hq]),
                        envelope=q.envelope.buffer(5.0))
                    for cell in cells.geoms:
                        cv = [v for x, y, v in hq if cell.contains(Point(x, y))]
                        if cv:
                            pieces.append((cell.intersection(q), mode(cv)))
                    continue
                except Exception:  # noqa: BLE001
                    pass
            pieces.append((q, mode(vs)))
    new = []
    try:
        on_platform = platform_on(doc) and next(
            (lv_ for lv_ in arch["levels"] if lv_["id"] == lid),
            {}).get("kind") == "ground"
    except Exception:  # noqa: BLE001
        on_platform = False
    for part, lv in pieces:
        for g in getattr(part, "geoms", [part]):
            if g.geom_type != "Polygon" or g.area < 0.5:
                continue
            g = g.buffer(0.0)
            hs = [list(h.exterior.coords)[:-1] for h in holes_all
                  if h.within(g.buffer(0.01))]
            step = max(0.0, lv - base)
            new.append({"type": "slab", "level": lid, "zone": True,
                        "note": True,
                        # on a ground floor standing on its foundation
                        # platform the platform is the floor: the part kept
                        # for its outline and finish, no concrete over the
                        # platform's own top (one face on another)
                        **({"grade": True} if on_platform else {}),
                        "corners": [[round(x, 4), round(y, 4)] for x, y in
                                    list(g.simplify(0.005).exterior.coords)[:-1]],
                        "holes": [[[round(x, 4), round(y, 4)] for x, y in h]
                                  for h in hs],
                        "t": round(t + step, 4),
                        "offset": 0.0 if abs(lv - base) < 0.005
                        else round(lv - base, 4)})
    new = [r_ for r_ in new if S.why_not(r_) is None]
    out = []
    if new:
        arch["structure"] += M.new_elements(arch["structure"], new)
        levels = Counter(r_["offset"] for r_ in new if r_["offset"])
        out += [(f"{n} area(s)", o) for o, n in levels.items()]
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
        out[lid] = [(x, y, ffl_text(e))]
    return out


def ffl_text(e: float) -> str:
    """«+4'-0" F.F.L.» / «±0'-0" F.F.L.» / «-10'-6" F.F.L.»"""
    from .host import len_txt
    sign = "±" if abs(e) < 0.005 else ("+" if e > 0 else "-")
    return f"{sign}{len_txt(abs(e))} F.F.L."


def apply_ground_ffl(doc) -> None:
    """The ground floor's finished level above the natural ground (the
    road / N.G.L. at 0), as the project needs it — 1'-0" to 4'-0": the
    ground floor stands there (the floors above and the basements follow)
    and the plot's ground is 0. 0 = as the CAD's level note set it."""
    v = float(doc["settings"].get("ground_ffl", 0.0) or 0.0)
    if v <= 0.0:
        return
    proj = doc["arch"].setdefault("project", {})
    proj["ground_level"] = round(v, 4)
    doc["settings"]["plinth"] = round(v, 4)



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


def room_size(doc, rec):
    """(width, length) of a room — its smallest bounding rectangle — or
    None when the room is not found."""
    from shapely.geometry import Point
    if not rec:
        return None
    for room in spaces.of_level(doc["arch"], rec["level"]):
        if (room.get("rec") or {}).get("id") == rec["id"] or \
                room["poly"].buffer(0.01).contains(Point(rec["x"], rec["y"])):
            r = room["poly"].minimum_rotated_rectangle
            pts = list(r.exterior.coords)[:4]
            a = math.dist(pts[0], pts[1])
            b = math.dist(pts[1], pts[2])
            return (min(a, b), max(a, b))
    return None


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


def _floor_voids(doc, lid):
    """Every opening in the floor of ``lid`` (shafts, stair and ramp wells,
    lift wells, openings drawn by hand) as one shapely shape, or None."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    hs = []
    for s_ in _floor_slabs(doc, lid):
        for h in s_.get("holes") or []:
            if len(h) >= 3:
                try:
                    p = Polygon([tuple(q[:2]) for q in h]).buffer(0)
                    if not p.is_empty:
                        hs.append(p)
                except Exception:  # noqa: BLE001
                    continue
    for m in doc.get("man_shafts") or []:
        if m.get("through") or m.get("level") == lid:
            try:
                hs.append(Polygon(m["pts"]).buffer(0))
            except Exception:  # noqa: BLE001
                continue
    return unary_union(hs) if hs else None


def _slab_finish_zones(doc, lid):
    """The floor slabs of ``lid`` set apart in their edit dialog: (the
    union of those set «whole» or «off» — the rooms' and edges' finish
    is kept off them —, [(slab, its finish outline)] of those set
    «whole» (the slab less its openings, walls, columns and cores),
    [(slab outline, its own thickness)] of those with a thickness)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    slabs = _floor_slabs(doc, lid)
    zone, whole, thick = [], [], []
    for s_ in slabs:
        try:
            p = Polygon([tuple(q[:2]) for q in s_["corners"]]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if p.is_empty:
            continue
        if float(s_.get("fin_t", 0) or 0) > 0:
            thick.append((p, float(s_["fin_t"])))
        if s_.get("fin") not in ("whole", "off"):
            continue
        zone.append(p)
        if s_["fin"] == "whole":
            q = p
            for h in s_.get("holes") or []:
                if len(h) >= 3:
                    q = q.difference(Polygon([tuple(v[:2]) for v in h])
                                     .buffer(0))
            mine = [w for w in doc["arch"]["walls"] if w["level"] == lid]
            solid = SE.wall_polys(mine) + [
                Polygon(S.column_outline(e, 0.0)).buffer(0)
                if e["type"] == "column" else
                Polygon([tuple(v[:2]) for v in e["corners"]]).buffer(0)
                for e in doc["arch"]["structure"]
                if e["level"] == lid and (e["type"] == "column" or
                                          (e["type"] == "core" and
                                           e.get("corners")))]
            if solid:
                q = q.difference(unary_union(solid))
            whole.append((s_, q))
    return (unary_union(zone) if zone else None), whole, thick


def _poly_of(s_):
    """A slab record's outline (shapely), its openings out."""
    from shapely.geometry import Polygon
    p = Polygon([tuple(q[:2]) for q in s_["corners"]]).buffer(0)
    for h in s_.get("holes") or []:
        if len(h) >= 3:
            p = p.difference(Polygon([tuple(v[:2]) for v in h]).buffer(0))
    return p


def _floor_shape(doc, lid):
    """The floor slabs of ``lid`` as one outline less their openings (a
    little grown, to forgive the wall faces), or None when the level has
    no slab of its own under it (the ground)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    ps = []
    fl = _floor_slabs(doc, lid)
    if slab_on_top(doc) and fl and all(s_["level"] == lid and s_.get("top")
                                       for s_ in fl):
        return None                    # the ground floor: no slab under it
    for s_ in fl:
        try:
            p = Polygon([tuple(q[:2]) for q in s_["corners"]]).buffer(0)
            for h in s_.get("holes") or []:
                if len(h) >= 3:
                    p = p.difference(Polygon([tuple(v[:2]) for v in h])
                                     .buffer(0))
            ps.append(p)
        except Exception:  # noqa: BLE001
            continue
    if not ps:
        return None
    u = unary_union(ps)
    return None if u.is_empty or u.area < 1.0 else u.buffer(0.03,
                                                           join_style=2)


def _finish_t_at(doc, rec, thick, pt):
    """A room's finish: its own, else the slab's own thickness under it,
    else the default."""
    if rec and rec.get("finish") is not None:
        return float(rec["finish"])
    if thick:
        from shapely.geometry import Point
        P_ = Point(pt)
        for p, t in thick:
            if p.contains(P_):
                return t
    return float(doc["settings"].get("finish_t", 0.0508))


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
        voids = _floor_voids(doc, lid)      # the slab's openings: cut too
        try:                                # slabs set apart (whole / off)
            zone, _whole, thick = _slab_finish_zones(doc, lid)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project._slab_finish_zones")
            zone, thick = None, []
        slab_u = _floor_shape(doc, lid)     # the finish follows the slab
        rooms_ = spaces.of_level(arch, lid)
        if slab_u is not None:              # (a slab that is the floor:
            try:                            # not a porch on the ground)
                from shapely.ops import unary_union as _uu
                ru_ = _uu([r["poly"] for r in rooms_])
                if ru_.is_empty or ru_.intersection(slab_u).area < \
                        0.6 * ru_.area:
                    slab_u = None
            except Exception:  # noqa: BLE001
                slab_u = None
        for room in rooms_:
            if room["area"] < 1.0:          # a duct / shaft: no finish
                continue
            f = _finish_t_at(doc, room.get("rec"), thick, room["at"])
            if f < 0.001:
                continue
            z = elev[i] + floor_offset_at(doc, lid, room["at"])
            poly = room["poly"]
            if slab_u is not None:
                try:                         # none out past the slab
                    poly = poly.intersection(slab_u)
                except Exception:  # noqa: BLE001
                    pass
            for cut_ in (voids, zone):
                if cut_ is not None and poly.intersects(cut_):
                    try:
                        poly = poly.difference(cut_)
                    except Exception:  # noqa: BLE001
                        pass
            faces = []
            for pg in getattr(poly, "geoms", [poly]):
                if pg.geom_type != "Polygon" or pg.area < 0.05:
                    continue
                piece = {"outer": S._ccw([tuple(q) for q in
                                          list(pg.exterior.coords)[:-1]]),
                         "holes": [list(reversed(S._ccw(
                             [tuple(q) for q in list(h.coords)[:-1]])))
                             for h in pg.interiors]}
                faces += W.solid(piece, 0.0, f) or []
            if not faces:
                continue
            lf = CP.local_faces(faces, (0.0, 0.0, 0.0, 0.0))
            key = CP.shape_key(lf)
            count[key] = count.get(key, 0) + 1
            prep.append((lv, lid, room, f, z, lf, key))
    edge = []          # the finish carried out to the slab's edge
    if st.get("finish_to_edge", True):
        from . import slabedges as SE
        for i, lv in enumerate(arch["levels"]):
            lid = lv["id"]
            # a parking floor: no finish out to its edges — but the ground
            # floor's car porch, verandah and lobby are finished
            no_edge = (lid in (doc.get("parking") or {})
                       and lv.get("kind") != "ground") or \
                not any(w["level"] == lid for w in arch["walls"])
            try:
                rooms_ = [] if no_edge else spaces.of_level(arch, lid)
                zone, whole, thick = _slab_finish_zones(doc, lid)
                pieces = []
                for p_ in ([] if no_edge else
                           SE.edge_finish_polys(doc, lid, rooms_)):
                    if zone is not None:
                        p_ = p_.difference(zone)
                    pieces += [g for g in getattr(p_, "geoms", [p_])
                               if g.geom_type == "Polygon" and g.area >= 0.3]
                for s_, q in whole:        # «Over the whole slab»
                    pieces += [g for g in getattr(q, "geoms", [q])
                               if g.geom_type == "Polygon" and g.area >= 0.3]
                if lv.get("kind") == "ground" and pieces and \
                        platform_on(doc):
                    # on the foundation platform: the finish only where the
                    # platform is (no finish left floating over the scraps
                    # the platform leaves out)
                    try:
                        from shapely.ops import unary_union as _uu3
                        pu_ = _uu3([q_ for q_, _t in
                                    platform_parts(doc)["pieces"]])
                        if not pu_.is_empty:
                            pieces = [g for p_ in pieces for g in getattr(
                                p_.intersection(pu_), "geoms",
                                [p_.intersection(pu_)])
                                if g.geom_type == "Polygon"
                                and g.area >= 0.3]
                    except Exception:  # noqa: BLE001
                        pass
                drop_ = float(st.get("ext_finish_drop", 0.3048) or 0.0) \
                    if lv.get("kind") == "ground" else 0.0
                ez_ = entrance_zone(doc, lid) if drop_ else None
                if ez_ is not None and not ez_.is_empty:
                    sp_ = []
                    for p_ in pieces:
                        if p_.intersects(ez_):
                            sp_ += [g for q_ in (p_.intersection(ez_),
                                                 p_.difference(ez_))
                                    for g in getattr(q_, "geoms", [q_])
                                    if g.geom_type == "Polygon"
                                    and g.area >= 0.1]
                        else:
                            sp_.append(p_)
                    pieces = sp_
                for k_, p_ in enumerate(pieces, 1):
                    c0 = p_.representative_point()
                    f = _finish_t_at(doc, None, thick, (c0.x, c0.y))
                    c_ = p_.representative_point()
                    d2_ = 0.0 if ez_ is not None and p_.intersection(
                        ez_).area > 0.5 * p_.area else drop_
                    z = elev[i] + floor_offset_at(doc, lid, (c_.x, c_.y)) \
                        - d2_            # outside, a step down (ground)
                    piece = {"outer": S._ccw([tuple(q) for q in
                                              list(p_.exterior.coords)[:-1]]),
                             "holes": [list(reversed(S._ccw(
                                 [tuple(q) for q in list(h.coords)[:-1]])))
                                 for h in p_.interiors]}
                    faces = W.solid(piece, z, z + f)
                    if faces:
                        # on the ground (no slab): the finish-only slab
                        # it belongs to — selected, its handles edit it
                        sid_ = None
                        for s2 in arch["structure"]:
                            if s2["type"] == "slab" and s2.get("grade") \
                                    and s2["level"] == lid:
                                try:
                                    if _poly_of(s2).buffer(0.05).contains(
                                            c0):
                                        sid_ = s2.get("id")
                                        break
                                except Exception:  # noqa: BLE001
                                    pass
                        edge.append((lv, lid, k_, faces, sid_))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project edge finish")
    if st.get("finish_on", True):        # the roof's finish, over its slab
        for e in arch["structure"]:
            if e["type"] != "slab" or not e.get("roof") or e.get("user"):
                continue
            lv = level_by_id(arch, e["level"])
            if lv is None:
                continue
            try:
                i_ = arch["levels"].index(lv)
                z = elev[i_] + float(lv.get("height") or 3.0) + float(
                    e.get("offset", 0.0) or 0.0)
                f = float(st.get("roof_finish_t", st.get("finish_t", 0.0508))
                          or 0.0)
                p_ = _poly_of(e)
                for g_ in getattr(p_, "geoms", [p_]):
                    if g_.geom_type != "Polygon" or g_.area < 0.3 or f <= 0:
                        continue
                    piece = {"outer": S._ccw([tuple(q) for q in list(
                        g_.exterior.coords)[:-1]]),
                             "holes": [list(reversed(S._ccw(
                                 [tuple(q) for q in list(h.coords)[:-1]])))
                                 for h in g_.interiors]}
                    faces = W.solid(piece, z, z + f)
                    if faces:
                        edge.append((lv, e["level"], f"roof{len(edge)}",
                                     faces, e.get("id")))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project roof finish")
    protos, out = {}, []
    for lv, lid, k_, faces, sid_ in edge:
        g = Group(_mesh_of([f_ if isinstance(f_, dict) else
                            {"loop": f_, "holes": []} for f_ in faces]),
                  name=f"Floor finish · slab edge {k_} · {lv['name']}")
        g.component = False
        g.material = {"color": COLOR["room"], "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ext = {KEY: dict({"type": "finish_edge", "id": f"edge-{lid}-{k_}",
                            "level": lid}, **({"slab": sid_} if sid_
                                              else {}))}
        out.append(g)
    for lv, lid, room, f, z, lf, key in prep:
        if key not in protos:
            mesh = Mesh()
            for lp, hs, _c in lf:
                _safe_add(mesh, [QVector3D(*q) for q in lp],
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

_BIKE_MESH = []


def group_by_level(groups, arch) -> list:
    """Every level's 3D elements (on its own layer) put into ONE group per
    level, «Level · Ground Floor» — the floor moved, hidden, copied or
    exported as one thing; double-click it to reach its elements. The 2D
    notes and the site stay as they are."""
    from core.group import Group
    from core.mesh import Mesh
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    buckets, rest = {}, []
    for g in groups:
        t = tag_of(g) or {}
        lid = t.get("level")
        if lid in names and getattr(g, "layer", None) == \
                level_layer(names[lid]):
            buckets.setdefault(lid, []).append(g)
        else:
            rest.append(g)
    out = []
    for lv in arch["levels"]:
        kids = buckets.get(lv["id"])
        if not kids:
            continue
        c = Group(Mesh(), name=f"Level · {lv['name']}")
        c.adopt(kids)
        c.component = False
        c.layer = level_layer(lv["name"])
        c.ext = {KEY: {"type": "levelgroup", "id": f"lvgrp-{lv['id']}",
                       "level": lv["id"]}}
        out.append(c)
    return out + rest


def _walk_groups(groups) -> list:
    out = []

    def walk(gs):
        for g in gs:
            out.append(g)
            kids = getattr(g, "children", None)
            if kids:
                walk(kids)
    walk(groups)
    return out


def all_groups(scene) -> list:
    """The scene's groups and the groups inside them (a level group's
    elements)."""
    out = []

    def walk(gs):
        for g in gs:
            out.append(g)
            kids = getattr(g, "children", None)
            if kids:
                walk(kids)
    walk(getattr(scene, "groups", []) or [])
    return out


def wall_attach(doc, rec, top=None, bot=None, new=None) -> dict:
    """A wall's top and bottom attached to the slabs or not: top «slab» =
    up to the slab over its floor (height «level», following it when the
    storey changes), «free» = its own height (the storey's clear height
    when it was attached); bottom «slab» = standing on its floor slab
    (base 0), «free» = its own base (kept). ``new`` (the values being
    set) comes back changed."""
    new = dict(rec if new is None else new)
    was_top = "slab" if rec.get("height", "level") == "level" else "free"
    was_bot = "slab" if abs(float(rec.get("base", 0.0) or 0.0)) < 1e-4 \
        else "free"
    if top == "slab" and was_top != "slab":
        new["height"] = "level"
    elif top == "free" and new.get("height", "level") == "level":
        try:
            info = S.levels_info(doc["arch"], M.elevations)
            li = info.get(rec["level"]) or {}
            new["height"] = round(max(float(li["under"]) -
                                      float(li["z0"]), 0.1), 4)
        except Exception:  # noqa: BLE001
            lv = level_by_id(doc["arch"], rec["level"]) or {}
            new["height"] = round(float(lv.get("height") or 3.0) - 0.15, 4)
    if bot == "slab" and was_bot != "slab":
        new["base"] = 0.0
    return new


def ramp_solids(doc) -> list:
    """Every car ramp as built, in absolute heights — for the walls and
    beams it crosses to stop under it: [{"sections", "zs", "t"}]."""
    from . import parking as PK
    arch = doc["arch"]
    elev = elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    st = doc["settings"]
    out = []
    for r in doc.get("ramps") or []:
        lid = r.get("level")
        if lid not in z_of or len(r.get("sections") or []) < 2:
            continue
        z = z_of[lid] + open_offset(doc, lid)
        out.append({"sections": r["sections"],
                    "zs": [z + v for v in PK.ramp_z(r)],
                    "t": float(r.get("t", st.get("ramp_t", 0.2)))})
    return out


def _bike_groups(doc, lid, pk, z, lname):
    """A level's motorbike parking: its bay lines painted, a motorbike in
    every space (one shared mesh), M1, M2… and the count —
    (groups, labels, plan lines)."""
    from PySide6.QtGui import QMatrix4x4, QVector3D

    from core.group import Group
    from core.textlabel import TextLabel

    from . import parking as PK
    st = doc["settings"]
    out, labels = [], []
    bl = pk.get("bikelines") or []
    lines = [(tuple(a), tuple(b)) for a, b in bl]
    faces = PK.paint_union(bl, z + 0.004) if bl else []
    if faces:
        g = Group(_mesh_of(faces), name=f"Motorbike parking · {lname}")
        g.component = False
        g.material = {"color": (0.95, 0.95, 0.9), "opacity": 1.0}
        g.layer = level_layer(lname)
        g.ext = {KEY: {"type": "parking", "id": f"bikepark-{lid}",
                       "level": lid}}
        out.append(g)
    bs = pk.get("bike_stalls") or []
    lib_ok = False
    if bs and st.get("cars_lib", True) and st.get("bike_model", "lib") == "lib":
        try:                       # IngeTrazo's library model, as the cars
            from . import cars as CARS
            lg = CARS.bike_groups(
                bs, z, st, level_layer(lname),
                lambda k: {KEY: {"type": "bike", "id": f"bike-{lid}-{k + 1}",
                                 "level": lid}},
                lambda k: f"Motorbike M{k + 1}")
            if lg:
                out += lg
                lib_ok = True
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.bike library")
    if bs and st.get("cars_lib", True) and not lib_ok:
        if not _BIKE_MESH:
            _BIKE_MESH.append(_mesh_of(PK.bike_faces(0.0)))
        for k, sl in enumerate(bs):
            g = Group(_BIKE_MESH[0], name=f"Motorbike M{k + 1}")
            m = QMatrix4x4()
            m.translate(float(sl["c"][0]), float(sl["c"][1]), z)
            m.rotate(float(sl.get("ang", 0.0)), 0.0, 0.0, 1.0)
            g.xform = m
            g.component = True
            g.layer = level_layer(lname)
            g.ext = {KEY: {"type": "bike", "id": f"bike-{lid}-{k + 1}",
                           "level": lid}}
            out.append(g)
    if bs and st.get("park_nums", True):
        for k, sl in enumerate(bs):
            labels.append(TextLabel(
                QVector3D(sl["c"][0], sl["c"][1], z + 0.02),
                QVector3D(0, 0, 0), f"M{k + 1}", layer=text_layer(lname)))
        xs = [sl["c"][0] for sl in bs]
        ys = [sl["c"][1] for sl in bs]
        labels.append(TextLabel(
            QVector3D((min(xs) + max(xs)) / 2, min(ys) - 1.5, z + 0.02),
            QVector3D(0, 0, 0), f"MOTORBIKE PARKING: {len(bs)} BIKES",
            layer=text_layer(lname)))
    return out, labels, lines


def floor_top_at(doc, lid, pt) -> float:
    """The walking surface at ``pt`` on ``lid``: the floor level, its part
    sunk / raised, the finish laid on it (a room's; out past the rooms the
    slab-edge finish — on the ground floor lower by the outside drop; a
    parking floor bare)."""
    from shapely.geometry import Point
    arch = doc["arch"]
    st = doc["settings"]
    lv = level_by_id(arch, lid) or {}
    i = arch["levels"].index(lv) if lv in arch["levels"] else 0
    z = elevations(arch)[i] + floor_offset_at(doc, lid, pt)
    fin = float(st.get("finish_t", 0.0508) or 0.0) \
        if st.get("finish_on", True) else 0.0
    try:
        inside = any(r["poly"].contains(Point(pt))
                     for r in spaces.of_level(arch, lid))
    except Exception:  # noqa: BLE001
        inside = False
    if inside:
        return z + fin
    if not st.get("finish_to_edge", True):
        return z
    if lv.get("kind") == "ground":
        if slab_on_top(doc) or ground_slab_on(doc):
            return z + fin
        if platform_on(doc):          # what the foundation platform makes
            try:                      # there — else the ground itself
                pp_ = platform_parts(doc)
                q_ = Point(pt)
                tops_ = [t_ + fin for pg_, t_ in pp_["pieces"]
                         if pg_.buffer(0.03).contains(q_)]
                for _n, ps_ in pp_["steps"]:      # (finished tops)
                    tops_ += [p_[1] for p_ in ps_
                              if p_[0].buffer(0.01).contains(q_)]
                if tops_:
                    return max(tops_)
                return plot_top(doc)
            except Exception:  # noqa: BLE001
                pass
        ez = entrance_zone(doc, lid)
        if ez is not None and ez.buffer(0.02).contains(Point(pt)):
            return z + fin
        return z - float(st.get("ext_finish_drop", 0.3048) or 0.0) + fin
    if lid in (doc.get("parking") or {}):
        return z
    return z + fin


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
        try:                       # the marks on the finished floor
            mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    for a, b in pk.get("bays") or []] or \
                [(float(sl["c"][0]), float(sl["c"][1]))
                 for sl in pk.get("stalls") or [] if sl.get("c")]
            if mids:
                z = floor_top_at(doc, lid, (
                    sum(m[0] for m in mids) / len(mids),
                    sum(m[1] for m in mids) / len(mids)))
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project parking floor top")
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
        try:
            out_b, lab_b, lines_b = _bike_groups(doc, lid, pk, z,
                                                 names[lid])
            out += out_b
            labels += lab_b
            plan.setdefault(lid, []).extend(lines_b)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.bikes")
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


def _gate_lib(doc, w, h):
    """The IngeTrazo library's gate model for an opening ``w`` × ``h``
    (the one nearest in proportion, the tallest first), or None."""
    if not doc["settings"].get("gate_lib", True):
        return None
    try:
        from . import library as LB
        ents = LB.list_entries()
    except Exception:  # noqa: BLE001
        return None
    best = None
    for e in ents or []:
        nm = str(e.get("name", "")).lower()
        if "gate" not in nm or "fence" in nm:
            continue
        cm = ((e.get("entry") or {}).get("cm")) or e.get("cm") or []
        try:
            ew, _ed, eh = (float(v) / 100.0 for v in cm[:3])
        except Exception:  # noqa: BLE001
            ew = eh = 0.0
        score = (abs((ew / eh if eh else 1.0) - (w / h if h else 1.0))
                 if ew and eh else 9.0) + (0.0 if eh >= 1.5 else 1.0)
        if best is None or score < best[0]:
            best = (score, e)
    if best is None:
        return None
    e = best[1]
    return {"key": e["key"], "entry": e.get("entry"), "fit": "stretch",
            "name": e.get("name")}


PLATFORM_COLOR = (0.66, 0.64, 0.60)
#: round columns: the library's plain round porch column (its shaft 0.209
#: of its 0.332 m width: the model scaled so its shaft is the plan's circle)
ROUND_LIB = "online:katorlegaz-019"
ROUND_LIB_K = 0.332 / 0.2086


def _prism(poly, z0, z1, min_area=0.02):
    """Faces (dicts) of a shapely polygon stood from ``z0`` to ``z1``."""
    out = []
    for pg in getattr(poly, "geoms", [poly]):
        if pg.geom_type != "Polygon" or pg.area < min_area or z1 - z0 < 0.005:
            continue
        piece = {"outer": S._ccw([tuple(q) for q in
                                  list(pg.exterior.coords)[:-1]]),
                 "holes": [list(reversed(S._ccw(
                     [tuple(q) for q in list(h.coords)[:-1]])))
                     for h in pg.interiors]}
        out += [f if isinstance(f, dict) else {"loop": f, "holes": []}
                for f in (W.solid(piece, z0, z1) or [])]
    return out


def _wedge(a, b, d, z_top, z_bot):
    """A ramp: its top edge ``a``-``b`` at ``z_top``, running ``d`` (a
    vector, the run) down to ``z_bot`` — the faces, outward."""
    a2 = (a[0] + d[0], a[1] + d[1])
    b2 = (b[0] + d[0], b[1] + d[1])
    A, B = (a[0], a[1], z_top), (b[0], b[1], z_top)
    A0, B0 = (a[0], a[1], z_bot), (b[0], b[1], z_bot)
    A2, B2 = (a2[0], a2[1], z_bot), (b2[0], b2[1], z_bot)
    faces = [[A, A2, B2, B], [A0, B0, B2, A2], [A, B, B0, A0],
             [A, A0, A2], [B, B2, B0]]
    # outward winding: the top's normal up
    ux, uy = b[0] - a[0], b[1] - a[1]
    if ux * d[1] - uy * d[0] > 0:
        faces = [list(reversed(f)) for f in faces]
    return [{"loop": f, "holes": []} for f in faces]


_STEPS_MEMO: dict = {}


def cad_steps(doc, lid) -> list:
    """The entrance steps the CAD draws on a floor's stair layers, outside
    its rooms (short runs — too few to be a stair): [{"strips": [(polygon,
    rank)], "n": risers, "lines": [LineString], "zone": the landing at
    their top (shapely)}] — rank 0 = the top step's edge (the landing's
    edge), counting down to the ground."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    how = doc["imports"].get(lid)
    if not how or not how.get("file"):
        return []
    key = (lid, str(how.get("file")), str(how.get("region")),
           how.get("bx"), how.get("by"), how.get("ix"), how.get("iy"),
           how.get("rot"), how.get("mtime"), len(doc["arch"]["walls"]))
    if key in _STEPS_MEMO:
        return _STEPS_MEMO[key]
    out = []
    try:
        raw_ = cadread.read(how["file"], how.get("unit"))
    except Exception:  # noqa: BLE001 — the file moved: no steps from it
        _STEPS_MEMO[key] = []
        return []
    try:
        st = doc["settings"]
        drawing = cadread.crop(raw_, how.get("region"))
        base = cadread.base_point(drawing, how.get("base", "origin"),
                                  (how.get("bx", 0.0), how.get("by", 0.0)))
        pl = cadread.place(drawing, base, (how.get("ix", 0.0),
                                           how.get("iy", 0.0)),
                           how.get("rot", 0.0))
        P, _f = layer_patterns(drawing, how, st)
        lay = pl["layers"]
        # the steps' own layer (STEP): steps anywhere on the floor — to a
        # raised hall, a mimber, the verandah; without one, the stair
        # layers' short runs outside the rooms (the entrance steps)
        pat = list(P.get("steps") or []) or ["*STEP*"]
        segs = [((s_[0], s_[1]), (s_[2], s_[3])) for s_ in pl["segs"]
                if _match(lay[s_[4]], pat) and
                0.4 <= math.dist((s_[0], s_[1]), (s_[2], s_[3])) <= 12.0]
        own = bool(segs)
        if not own:
            pat = list(P.get("stairs") or [])
            segs = [((s_[0], s_[1]), (s_[2], s_[3])) for s_ in pl["segs"]
                    if _match(lay[s_[4]], pat) and
                    0.4 <= math.dist((s_[0], s_[1]), (s_[2], s_[3])) <= 12.0]
        arch = doc["arch"]
        rooms_ = spaces.of_level(arch, lid)
        walls = [w for w in arch["walls"] if w["level"] == lid
                 and not w.get("rail") and W.why_not(w) is None]
        bld = unary_union([r["poly"] for r in rooms_] +
                          SE.wall_polys(walls)).buffer(0.05)
        # the traced stairs' own lines are not steps
        used = []
        for ch in stair_trace(doc, lid):
            for f in ch:
                for a, b in f["lines"]:
                    used.append(LineString([a, b]).buffer(0.05))
        usedu = unary_union(used) if used else Polygon()
        lines = []
        for a, b in segs:
            ln = LineString([a, b])
            if not own and bld.contains(ln.interpolate(0.5, normalized=True)):
                continue
            if not usedu.is_empty and usedu.contains(ln):
                continue
            lines.append(ln)
        if own and lines:
            out = _own_steps(lines, bld)
            if len(_STEPS_MEMO) > 16:
                _STEPS_MEMO.clear()
            _STEPS_MEMO[key] = out
            return out
        # sets: lines within 0.8 m of one another
        grp = list(range(len(lines)))

        def root(k):
            while grp[k] != k:
                grp[k] = grp[grp[k]]
                k = grp[k]
            return k
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                if lines[i].distance(lines[j]) < 0.8:
                    grp[root(j)] = root(i)
        sets = {}
        for i, ln in enumerate(lines):
            sets.setdefault(root(i), []).append(ln)
        for ls in sets.values():
            if len(ls) < (1 if own else 2):
                continue
            fams = []                       # by direction
            for ln in ls:
                (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
                ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0
                fam = next((f for f in fams if min(abs(f[0] - ang),
                            180 - abs(f[0] - ang)) < 8.0), None)
                if fam is None:
                    fams.append([ang, [ln]])
                else:
                    fam[1].append(ln)
            # one direction, apart along it (a U of steps: its two ends):
            # each run its own flight
            split = []
            for ang, fl in fams:
                uu = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
                iv = [sorted((c[0] * uu[0] + c[1] * uu[1]) for c in
                             (ln.coords[0], ln.coords[-1])) for ln in fl]
                grp_ = list(range(len(fl)))

                def r_(k):
                    while grp_[k] != k:
                        grp_[k] = grp_[grp_[k]]
                        k = grp_[k]
                    return k
                for i_ in range(len(fl)):
                    for j_ in range(i_ + 1, len(fl)):
                        if min(iv[i_][1], iv[j_][1]) - max(iv[i_][0],
                                                           iv[j_][0]) > 0.05:
                            grp_[r_(j_)] = r_(i_)
                subs = {}
                for i_, ln in enumerate(fl):
                    subs.setdefault(r_(i_), []).append(ln)
                nv_ = (-uu[1], uu[0])
                for v_ in subs.values():         # and apart across it
                    v_.sort(key=lambda ln: ln.interpolate(
                        0.5, normalized=True).x * nv_[0] + ln.interpolate(
                        0.5, normalized=True).y * nv_[1])
                    run = [v_[0]]
                    for ln in v_[1:]:
                        if run[-1].distance(ln) > 0.8:
                            split.append([ang, run])
                            run = []
                        run.append(ln)
                    split.append([ang, run])
            fams = split
            strips, n_, reach, fams_out = [], 0, [], []
            for ang, fl in fams:
                if len(fl) < (1 if own else 2):
                    continue
                u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
                nv = (-u[1], u[0])
                offs = []
                for ln in fl:
                    m = ln.interpolate(0.5, normalized=True)
                    offs.append((m.x * nv[0] + m.y * nv[1], ln))
                offs.sort(key=lambda t: t[0])
                # pieces of one riser line (cut where other lines cross it):
                # one line, end to end
                merged = []
                for o_, ln in offs:
                    if merged and abs(o_ - merged[-1][0]) < 0.06:
                        prev = merged[-1][1]
                        uu = (math.cos(math.radians(ang)),
                              math.sin(math.radians(ang)))
                        ss = [c[0] * uu[0] + c[1] * uu[1] for c in
                              list(prev.coords) + list(ln.coords)]
                        p0 = min(list(prev.coords) + list(ln.coords),
                                 key=lambda c: c[0] * uu[0] + c[1] * uu[1])
                        p1 = max(list(prev.coords) + list(ln.coords),
                                 key=lambda c: c[0] * uu[0] + c[1] * uu[1])
                        merged[-1] = (merged[-1][0], LineString([p0, p1]))
                    else:
                        merged.append((o_, ln))
                offs = merged
                # the spacing (the tread), each line swept toward the
                # building by it: that step's tread
                gaps = [abs(offs[k + 1][0] - offs[k][0])
                        for k in range(len(offs) - 1)]
                tread = sorted(gaps)[len(gaps) // 2] if gaps else 0.3
                tread = min(max(tread, 0.2), 0.6)
                # ordered from the building outwards (rank 0: the top step)
                if offs[0][1].distance(bld) > offs[-1][1].distance(bld):
                    offs.reverse()
                tow = None                  # sweep direction to building
                m0 = offs[0][1].interpolate(0.5, normalized=True)
                for sg in (1, -1):
                    q = Point(m0.x + nv[0] * sg * tread,
                              m0.y + nv[1] * sg * tread)
                    if tow is None or q.distance(bld) < tow[1]:
                        tow = ((nv[0] * sg, nv[1] * sg), q.distance(bld))
                dv = tow[0]
                if len(offs) >= 2:       # several lines: up from the
                    # outermost toward the innermost (the landing's side)
                    o_in, o_out = offs[0][0], offs[-1][0]
                    sg_ = 1.0 if o_in > o_out else -1.0
                    dv = (nv[0] * sg_, nv[1] * sg_)
                for rank, (_o, ln) in enumerate(offs):
                    (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
                    poly = Polygon([(x0, y0), (x1, y1),
                                    (x1 + dv[0] * tread, y1 + dv[1] * tread),
                                    (x0 + dv[0] * tread, y0 + dv[1] * tread)])
                    strips.append((poly, rank))
                    if rank == 0:            # the landing: on from the top
                        R_ = 8.0             # step toward the building
                        reach.append(Polygon([
                            (x0, y0), (x1, y1),
                            (x1 + dv[0] * R_, y1 + dv[1] * R_),
                            (x0 + dv[0] * R_, y0 + dv[1] * R_)]))
                n_ = max(n_, len(offs))
                fams_out.append(([ln for _o, ln in offs], dv, tread))
            if not strips or n_ < (1 if own else 2):
                continue
            top = [p_ for p_, r_ in strips if r_ == 0]   # the landing's edge
            out.append({"strips": strips, "n": n_, "lines": ls,
                        "zone": unary_union(top), "own": own,
                        "fams": fams_out,
                        "reach": unary_union(reach).difference(bld)})
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.cad_steps")
        out = []
    if len(_STEPS_MEMO) > 16:
        _STEPS_MEMO.clear()
    _STEPS_MEMO[key] = out
    return out


#: a floor step's tread when the CAD shows one riser only (12")
STEP_TREAD = 0.3048


def _own_steps(lines, bld) -> list:
    """The STEP layer's risers as whole lines (an L or a U of steps round
    a porch one riser line, its corners joined), in sets of risers one
    behind the other: [{"own", "plines" (top first — as far as the plan
    tells; the levels decide), "tread", "zone", "reach", "strips",
    "n", "lines"}]."""
    from shapely.geometry import LineString, MultiLineString, Point
    from shapely.ops import linemerge, unary_union

    def snap(v):
        return round(v / 0.004) * 0.004
    segs = [LineString([(snap(x), snap(y)) for x, y in ln.coords])
            for ln in lines]
    segs = [g for g in segs if g.length > 0.05]
    if not segs:
        return []
    merged = linemerge(unary_union(MultiLineString(segs)))
    pls = [g for g in getattr(merged, "geoms", [merged])
           if g.geom_type == "LineString" and g.length >= 0.4]
    n = len(pls)
    par = list(range(n))

    def root(k):
        while par[k] != k:
            par[k] = par[par[k]]
            k = par[k]
        return k
    for i in range(n):
        for j in range(i + 1, n):
            if pls[i].distance(pls[j]) < 0.75:
                par[root(j)] = root(i)
    sets: dict = {}
    for i in range(n):
        sets.setdefault(root(i), []).append(pls[i])
    out = []
    for ps in sets.values():
        if len(ps) > 1:
            # risers one behind the other: from an outermost one, by distance
            far = max(ps, key=lambda a: sum(a.distance(b) for b in ps))
            ps.sort(key=lambda a: far.distance(a))
            # the end nearer the building first (rank 0: the top step)
            if bld is not None and not bld.is_empty and \
                    ps[0].distance(bld) > ps[-1].distance(bld) + 0.05:
                ps.reverse()
            gaps = [ps[k].distance(ps[k + 1]) for k in range(len(ps) - 1)]
            tread = sorted(gaps)[len(gaps) // 2] if gaps else STEP_TREAD
        else:
            tread = STEP_TREAD
        tread = min(max(tread, 0.2), 0.6)
        out.append({"own": True, "plines": ps, "tread": tread,
                    "n": len(ps), "lines": ps, "strips": [],
                    "zone": ps[0].buffer(0.05),
                    "reach": ps[0].buffer(0.05)})
    return out


def _samples(poly, n=9):
    """A few points spread inside ``poly``."""
    from shapely.geometry import Point
    out = []
    for g in getattr(poly, "geoms", [poly]):
        if g.is_empty or g.geom_type != "Polygon":
            continue
        out.append(g.representative_point())
        x0, y0, x1, y1 = g.bounds
        k = 3
        for i in range(k):
            for j in range(k):
                q = Point(x0 + (x1 - x0) * (i + 0.5) / k,
                          y0 + (y1 - y0) * (j + 0.5) / k)
                if g.contains(q):
                    out.append(q)
    return out[:max(n, 1) * 3]


def step_strips(ps, tread, up_side_pt=None):
    """Each riser line's tread, swept up-side by ``tread`` (corners
    mitred: an L / U of steps runs on round its corners): [(tread poly,
    side)] — side +1 / −1, shapely's single-sided buffer side of the
    up-side. Up: away from the next riser down (the first: away from the
    second, or toward ``up_side_pt``)."""
    from shapely.geometry import Point
    out = []
    for k, pl_ in enumerate(ps):
        cand = {sg: pl_.buffer(sg * tread, single_sided=True, join_style=2,
                               mitre_limit=4.0) for sg in (1, -1)}
        if k > 0:
            ref = ps[k - 1]                       # the riser above
            sg = min(cand, key=lambda s_: cand[s_].centroid.distance(ref))
        elif len(ps) > 1:
            ref = ps[1]                           # away from the one below
            sg = max(cand, key=lambda s_: cand[s_].centroid.distance(ref))
        elif up_side_pt is not None:
            sg = min(cand, key=lambda s_: cand[s_].centroid.distance(
                Point(up_side_pt)))
        else:
            sg = 1
        out.append((cand[sg].buffer(0), sg))
    return out


def entrance_zone(doc, lid):
    """Where the CAD's entrance steps land: the outside parts of the floor
    (lobby, porch…) their top step touches — at the rooms' floor level,
    not the outside drop. A shapely shape, or None."""
    from shapely.ops import unary_union
    sets = cad_steps(doc, lid)
    if not sets:
        return None
    reach = unary_union([s_["reach"] for s_ in sets])
    tops = unary_union([s_["zone"] for s_ in sets]).buffer(0.35)
    from . import slabedges as SE
    try:
        rooms_ = spaces.of_level(doc["arch"], lid)
        pcs = SE.edge_finish_polys(doc, lid, rooms_)
    except Exception:  # noqa: BLE001
        pcs = []
    # the outside part the top step reaches, as far as the steps run (a
    # porch beside the lobby keeps its own lower level)
    hit = [p_.intersection(reach) for p_ in pcs if p_.intersects(tops)]
    return unary_union(hit + [s_["zone"] for s_ in sets])


def platform_parts(doc) -> dict:
    """The foundation platform under the ground floor (slabs as floors, no
    ground slab, no basement): ``pieces`` [(shapely poly, top z)] from
    N.G.L. up under the floor finishes — the rooms at the floor level, the
    verandah / lobby / porch lower by the outside drop — the ``steps``
    [(name, [(poly, top z)])] at the doors out (main and side entrances)
    down to N.G.L., and the car porch's ``ramps`` [(name, faces)]."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    from .host import len_txt
    out = {"pieces": [], "steps": [], "ramps": []}
    if not platform_on(doc):
        return out
    arch = doc["arch"]
    st = doc["settings"]
    gi = next((i for i, lv in enumerate(arch["levels"])
               if lv.get("kind") == "ground"), None)
    if gi is None:
        return out
    lv = arch["levels"][gi]
    lid = lv["id"]
    walls = [w for w in arch["walls"] if w["level"] == lid
             and not w.get("rail") and W.why_not(w) is None]
    if not walls:
        return out
    elev = elevations(arch)[gi]
    zg = plot_top(doc)
    drop = float(st.get("ext_finish_drop", 0.3048) or 0.0)
    fin = float(st.get("finish_t", 0.0508) or 0.0) \
        if st.get("finish_on", True) else 0.0
    rooms_ = spaces.of_level(arch, lid)
    R = unary_union([r["poly"] for r in rooms_]) if rooms_ else Polygon()
    gs = []
    for s_ in _floor_slabs(doc, lid):
        try:
            gs.append(_poly_of(s_))
        except Exception:  # noqa: BLE001
            continue
    G = unary_union(gs) if gs else R
    WP = unary_union(SE.wall_polys(walls) + [
        SE._poly(e["corners"]) for e in arch["structure"]
        if e["type"] in ("column", "core") and e["level"] == lid
        and e.get("corners")])
    if G.is_empty:
        return out
    inner = G.intersection(R).difference(WP)
    outer = G.difference(R).difference(WP)
    zone = entrance_zone(doc, lid)        # the CAD steps' landing: level
    # the areas the CAD's level notes set (slab_zones): at their noted
    # level — no outside drop there
    try:
        noted = unary_union([_poly_of(s_) for s_ in S.floor_parts(arch, lid)
                             if s_.get("note")])
    except Exception:  # noqa: BLE001
        noted = Polygon()
    if not noted.is_empty:
        zone = noted if zone is None else unary_union([zone, noted])
        # a floor whose levels the CAD notes: what it does not note is at
        # the floor's level (no made-up outside drop)
        drop = 0.0
    # the columns standing outside the rooms (twin columns between the
    # planters, a portico's): each pair on its own square pedestal — not
    # the slab outline's odd scraps round them
    peds = Polygon()
    try:
        co_ = []
        Rin = R.buffer(-0.02)
        for c_ in arch["structure"]:
            if c_["type"] != "column" or c_["level"] != lid:
                continue
            cp_ = Polygon(S.column_outline(c_)).buffer(0)
            if cp_.is_empty or Rin.contains(cp_.centroid):
                continue
            co_.append(cp_)
        if co_:
            grp_ = unary_union([q.buffer(0.3) for q in co_])
            pl_ = []
            for g_ in getattr(grp_, "geoms", [grp_]):
                mine_ = unary_union([q for q in co_ if g_.contains(q)])
                if mine_.is_empty:
                    continue
                pl_.append(mine_.minimum_rotated_rectangle.buffer(
                    0.08, join_style=2))
            peds = unary_union(pl_) if pl_ else Polygon()
    except Exception:  # noqa: BLE001
        peds = Polygon()
    ped_done = False
    for part, dz in ((inner, 0.0), (outer, drop)):
        if dz is drop and part is outer and not peds.is_empty:
            # (a porch the doors open onto is a floor, whatever its shape)
            dpts_ = []
            wd_ = {w_["id"]: w_ for w_ in walls}
            for o_ in arch["openings"]:
                w_ = wd_.get(o_["wall"])
                if w_ is None or o_["kind"] != "door":
                    continue
                L_ = math.dist(w_["a"], w_["b"])
                if L_ < 1e-6:
                    continue
                f_ = float(o_["pos"]) / L_
                dpts_.append(Point(w_["a"][0] + (w_["b"][0] - w_["a"][0])
                                   * f_, w_["a"][1] + (w_["b"][1] -
                                                       w_["a"][1]) * f_))
            small = [g_ for g_ in getattr(part, "geoms", [part])
                     if g_.geom_type == "Polygon" and g_.area < 15.0
                     and g_.intersects(peds)
                     and g_.minimum_rotated_rectangle.area > 1.6 * g_.area
                     and not any(g_.distance(q_) < 0.5 for q_ in dpts_)]
            if small:
                part = part.difference(unary_union(small).buffer(0.001))
            if not ped_done:
                ped_done = True
                for pg_ in getattr(peds, "geoms", [peds]):
                    pg_ = pg_.difference(WP)
                    c_ = pg_.representative_point() if not pg_.is_empty \
                        else None
                    if c_ is None:
                        continue
                    top = elev + floor_offset_at(doc, lid, (c_.x, c_.y)) \
                        - (0.0 if noted.contains(c_) else drop)
                    for q_ in getattr(pg_, "geoms", [pg_]):
                        if q_.geom_type == "Polygon" and q_.area > 0.05 \
                                and top - zg > 0.01:
                            out["pieces"].append((q_, top))
        for pg in getattr(part, "geoms", [part]):
            if pg.geom_type != "Polygon" or pg.area < 0.05:
                continue
            parts_ = [(pg, dz)]
            if dz and zone is not None and pg.intersects(zone):
                parts_ = [(pg.intersection(zone), 0.0),
                          (pg.difference(zone), dz)]
            for q_, dz_ in parts_:
                for qg in getattr(q_, "geoms", [q_]):
                    if qg.geom_type != "Polygon" or qg.area < 0.05:
                        continue
                    c = qg.representative_point()
                    top = elev + floor_offset_at(doc, lid, (c.x, c.y)) - dz_
                    if top - zg > 0.01:
                        out["pieces"].append((qg, top))
    # the entrance steps as the CAD draws them, from the rooms' floor
    # (the landing) down to the ground
    csets = cad_steps(doc, lid)
    rmax_ = max(float(st.get("riser_max", 0.1524) or 0.1524), 0.10)
    Gb = G.buffer(0.01)
    Rb = R.buffer(0.01)

    lplats = []                      # the «line» layer's platforms
    for p_ in ((doc.get("lowparts") or {}).get(lid) or {}).get("plats") or ():
        try:
            pg_ = Polygon(p_["pts"], p_.get("holes") or []).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if p_.get("v") is not None:
            lplats.append((pg_, elev + float(p_["v"])))

    def surf_at(x, y):
        """The finished floor's top at (x, y): the floor (its zone), the
        outside part lower by the drop unless the CAD sets it, a platform
        the CAD's lines close, else the ground."""
        q = Point(x, y)
        if not Gb.contains(q):
            for pg_, top_ in lplats:
                if pg_.buffer(0.02).contains(q):
                    return top_
            return zg
        dz_ = 0.0 if Rb.contains(q) or (zone is not None and
                                        zone.contains(q)) else drop
        return elev + floor_offset_at(doc, lid, (x, y)) - dz_ + fin
    for k_, cs_ in enumerate(csets, 1):
        if not cs_.get("own"):
            c = cs_["zone"].representative_point()
            surf = elev + floor_offset_at(doc, lid, (c.x, c.y)) + fin
            # down to what is at their foot (a porch, a verandah lower by
            # the drop, the ground) — just past the outermost line
            # as many risers as it draws, each the riser set (6"): its
            # foot that much lower — the porch / paving it lands on taken
            # to that level too (no made-up drop beside drawn steps)
            foot_z = max(zg, surf - cs_["n"] * rmax_)
            if surf - foot_z < 0.05:
                foot_z = zg
            try:
                feet_ = []
                for lns_, dv_, tr_ in cs_.get("fams") or []:
                    ln_ = lns_[-1]
                    (x0_, y0_), (x1_, y1_) = ln_.coords[0], ln_.coords[-1]
                    feet_.append(Polygon([
                        (x0_, y0_), (x1_, y1_),
                        (x1_ - dv_[0] * 0.4, y1_ - dv_[1] * 0.4),
                        (x0_ - dv_[0] * 0.4, y0_ - dv_[1] * 0.4)]))
                fu_ = unary_union(feet_) if feet_ else None
                if fu_ is not None and foot_z > zg + 0.01:
                    for k2_, (pg2_, t2_) in enumerate(out["pieces"]):
                        if pg2_.intersects(fu_) and t2_ < surf - 0.05 and \
                                abs(t2_ - foot_z) < 0.6 and \
                                not R.buffer(-0.05).contains(
                                    pg2_.representative_point()):
                            out["pieces"][k2_] = (pg2_, foot_z - fin)
            except Exception:  # noqa: BLE001
                pass
            H = surf - foot_z
            if H < 0.05:
                continue
            r_ = H / cs_["n"]
            out["steps"].append((
                f"Entrance steps (CAD) {k_} ({cs_['n']} risers)",
                [(pc, surf - rank * r_, None, r_) for pc, rank in
                 cs_["strips"] if surf - rank * r_ - foot_z > 0.01]))
            continue
        # the steps' own layer: whole riser lines, from the level at one
        # end of the run to the level at the other (a mimber's: up from
        # the floor, its top at the wall)
        ps = list(cs_["plines"])
        tread = float(cs_["tread"])
        WPc = WP.centroid

        def ends_z(ps_):
            st_ = step_strips(ps_, tread, (WPc.x, WPc.y))
            top_poly = st_[0][0]
            # the level up-side of the top riser: just past its tread
            # (as far as the floor it climbs to: a porch between the top
            # step and the walls is at that floor's level)
            up = ps_[0].buffer(st_[0][1] * (tread + 3.0), single_sided=True,
                               join_style=2).difference(
                ps_[0].buffer(st_[0][1] * (tread + 0.05), single_sided=True,
                              join_style=2))
            dn = ps_[-1].buffer(-st_[-1][1] * 0.6, single_sided=True,
                                join_style=2).difference(
                ps_[-1].buffer(-st_[-1][1] * 0.05, single_sided=True,
                               join_style=2))
            zs_up = [surf_at(q.x, q.y) for q in _samples(up)] or [zg]
            zs_dn = [surf_at(q.x, q.y) for q in _samples(dn)] or [zg]
            return st_, max(zs_up), min(zs_dn), top_poly
        st_, zt, zb, _tp = ends_z(ps)
        if len(ps) > 1:
            st2, zt2, zb2, _ = ends_z(list(reversed(ps)))
            if zt2 - zb2 > zt - zb + 0.02:
                ps, st_, zt, zb = list(reversed(ps)), st2, zt2, zb2
        n = len(ps)
        H = zt - zb
        if H < 0.05:
            # nothing noted: up from the floor, a riser a line, the top at
            # the end nearer the walls
            if len(ps) > 1 and ps[-1].distance(WP) < ps[0].distance(WP) - 0.05:
                ps = list(reversed(ps))
                st_ = step_strips(ps, tread)
            H = n * rmax_
            zt = zb + H
        r_ = H / n
        # the landing between the top step and the floor it climbs to (a
        # porch round the columns): at the top level
        try:
            sg0 = st_[0][1]
            gap = ps[0].distance(G)
            if 0.05 < gap < 3.0:
                land = ps[0].buffer(sg0 * (gap + 0.3), single_sided=True,
                                    join_style=2, mitre_limit=4.0)
                land = land.difference(G).difference(WP).difference(
                    st_[0][0].buffer(-0.001))
                land = unary_union([land, st_[0][0]])
                for lg in getattr(land, "geoms", [land]):
                    if lg.geom_type == "Polygon" and lg.area > 0.1:
                        out["pieces"].append((lg, zt - fin))
            # the top riser running round to the building (a U, an L): the
            # porch it closes against the walls, at the top level too
            cs0 = list(ps[0].coords)
            if len(cs0) >= 3:
                encl = Polygon(cs0).buffer(0)
                porch = encl.difference(G).difference(WP)
                for st0 in st_:
                    porch = porch.difference(st0[0].buffer(0.001))
                for lg in getattr(porch, "geoms", [porch]):
                    if lg.geom_type == "Polygon" and lg.area > 0.3:
                        out["pieces"].append((lg, zt - fin))
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project steps landing")
        pcs = []
        for rank, (pl_, (poly, sg)) in enumerate(zip(ps, st_)):
            ztop = zt - rank * r_
            if ztop - zg <= 0.01:
                continue
            nose = pl_.buffer(-sg * 0.045, single_sided=True, join_style=2,
                              mitre_limit=4.0)
            pcs.append((poly, ztop, {"edge": pl_, "down": -sg,
                                     "nose": nose}, r_))
        if pcs:
            out["steps"].append((f"Steps {k_} ({n} risers)", pcs))
    cad_lines = [ln for cs_ in csets for ln in cs_["lines"]]
    if not st.get("entry_steps", True):
        return out
    # the CAD draws its entrance steps: those only (none made up at the
    # other doors out — the plan followed strictly)
    invent = not (csets and st.get("steps_cad_only", True))
    rmax = max(float(st.get("riser_max", 0.1524) or 0.1524), 0.10)
    tread = max(float(st.get("tread_ext", 0.3048) or 0.3048), 0.22)
    solid = unary_union([G, WP])
    byid = {w["id"]: w for w in walls}
    made = []                                 # (edge point, direction)
    n_ = 0
    for o in (arch["openings"] if invent else []):
        w = byid.get(o.get("wall"))
        if w is None or o.get("kind") != "door" or \
                w.get("kind", "line") != "line":
            continue
        a, b = w["a"], w["b"]
        L = math.dist(a, b)
        if L < 1e-6:
            continue
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        nrm = (-u[1], u[0])
        pos = float(o["pos"])
        c = (a[0] + u[0] * pos, a[1] + u[1] * pos)
        t = float(w["t"])
        sides = []
        for sg in (1, -1):
            q = Point(c[0] + nrm[0] * sg * (t / 2 + 0.25),
                      c[1] + nrm[1] * sg * (t / 2 + 0.25))
            sides.append((sg, R.buffer(-0.02).contains(q)))
        outs = [sg for sg, inside in sides if not inside]
        if len(outs) != 1:
            continue                       # room to room, or nowhere
        sg = outs[0]
        dx, dy = nrm[0] * sg, nrm[1] * sg
        edge = None
        dd = t / 2
        while dd < 30.0:
            q = Point(c[0] + dx * dd, c[1] + dy * dd)
            if not solid.buffer(0.005).contains(q):
                edge = dd
                break
            dd += 0.05
        if edge is None:
            continue
        ep = (c[0] + dx * edge, c[1] + dy * edge)
        if any(math.dist(ep, e_) < 1.0 and d_[0] * dx + d_[1] * dy > 0.9
               for e_, d_ in made):
            continue
        if any(ln.distance(Point(ep)) < 1.5 for ln in cad_lines):
            continue                     # the CAD draws these steps
        made.append((ep, (dx, dy)))
        back = Point(c[0] + dx * (edge - 0.1), c[1] + dy * (edge - 0.1))
        indoor = R.buffer(0.01).contains(back)
        surf = elev + floor_offset_at(doc, lid, (back.x, back.y)) - \
            (0.0 if indoor or (zone is not None and zone.contains(back))
             else drop) + fin
        # down to what is outside: the ground, or a platform the CAD's
        # lines close round (the compound's paving)
        zout = surf_at(c[0] + dx * (edge + 0.4), c[1] + dy * (edge + 0.4))
        H = surf - min(zout, surf)
        if H < 0.05:
            continue
        nr = max(1, math.ceil(H / rmax - 1e-6))
        r_ = H / nr
        wd = min(float(o["w"]) + 0.6, 4.0)
        pieces = []
        for k in range(1, nr):              # the treads (the floor: the top)
            z_top = surf - k * r_
            p0 = (ep[0] + dx * (k - 1) * tread, ep[1] + dy * (k - 1) * tread)
            ln = LineString([p0, (p0[0] + dx * tread, p0[1] + dy * tread)])
            pc = ln.buffer(wd / 2, cap_style=2)
            pieces.append((pc, z_top, (dx, dy), r_))
        if not pieces:                # one riser: the platform's edge is it
            continue
        n_ += 1
        out["steps"].append((f"Entrance steps {n_} ({nr} risers)",
                             [p_ for p_ in pieces if p_[1] - zg > 0.01]))
    # the car porch: a ramp from its open edge (towards the gate / road)
    try:
        words = [t_ for t_ in doc.get("texts") or [] if t_.get("level") == lid
                 and re.search(r"PORCH|GARAGE|PARKING|DRIVE", str(
                     t_.get("text", "")).upper())]
        target = None
        site = doc.get("site") or {}
        plot = arch.get("plot")
        if plot:
            from .engine import plotgeo
            cn = plotgeo.clean(plot["corners"])
            if site.get("wall") and site.get("gates"):
                fr_ = SITE_.gate_frame(cn, site["gates"][0],
                                       float(site.get("t", 0.23)))
                if fr_:
                    target = ((fr_[0][0] + fr_[1][0]) / 2,
                              (fr_[0][1] + fr_[1][1]) / 2)
            if target is None:
                fl = plot.get("sb_front") or []
                k_ = next((i for i, f_ in enumerate(fl) if f_), None)
                if k_ is not None:
                    p_, q_ = cn[k_], cn[(k_ + 1) % len(cn)]
                    target = ((p_[0] + q_[0]) / 2, (p_[1] + q_[1]) / 2)
        for pg in getattr(outer, "geoms", [outer]):
            if pg.geom_type != "Polygon" or pg.area < 8.0:
                continue
            if not any(pg.buffer(0.3).contains(Point(t_["x"], t_["y"]))
                       for t_ in words):
                continue
            cs = list(pg.exterior.coords)
            cands = []
            for p_, q_ in zip(cs, cs[1:]):
                Ls = math.dist(p_, q_)
                if Ls < 2.0:
                    continue
                m_ = Point((p_[0] + q_[0]) / 2, (p_[1] + q_[1]) / 2)
                if m_.distance(WP) < 0.2 or m_.distance(R) < 0.2:
                    continue
                d0 = m_.distance(Point(target)) if target else -Ls
                cands.append((d0, p_, q_))
            if not cands:
                continue
            _d, p_, q_ = min(cands)
            ux, uy = q_[0] - p_[0], q_[1] - p_[1]
            Ls = math.hypot(ux, uy)
            nx, ny = -uy / Ls, ux / Ls
            mx, my = (p_[0] + q_[0]) / 2, (p_[1] + q_[1]) / 2
            if pg.contains(Point(mx + nx * 0.1, my + ny * 0.1)):
                nx, ny = -nx, -ny
            c_ = pg.representative_point()
            top = elev + floor_offset_at(doc, lid, (c_.x, c_.y)) - drop + fin
            H = top - zg
            if H < 0.03:
                continue
            run = max(H * float(st.get("porch_ramp", 6.0) or 6.0), 0.6)
            out["ramps"].append((f"Car porch ramp ({len_txt(H)} over "
                                 f"{len_txt(run)})",
                                 _wedge(p_, q_, (nx * run, ny * run),
                                        top, zg)))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.platform_parts porch")
    return out


def _platform_groups(doc):
    """The foundation platform, its entrance steps and the porch ramp (on
    the ground floor's layer)."""
    from core.group import Group
    parts = platform_parts(doc)
    if not (parts["pieces"] or parts["steps"] or parts["ramps"]):
        return []
    arch = doc["arch"]
    lv = next(lv for lv in arch["levels"] if lv.get("kind") == "ground")
    lid = lv["id"]
    zg = plot_top(doc)
    out = []

    def grp(name, faces, kind, k):
        g = Group(_mesh_of(faces), name=f"{name} · {lv['name']}")
        g.component = False
        g.material = {"color": PLATFORM_COLOR, "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ifc = {"class": "IfcSlab" if kind == "platform" else
                 "IfcStair" if kind == "steps" else "IfcRamp", "name": name}
        g.ext = {KEY: {"type": "platform", "id": f"{kind}-{k}",
                       "level": lid}}
        return g
    faces = []
    for pg, top in parts["pieces"]:
        faces += _prism(pg, zg, top)
    if faces:
        out.append(grp("Foundation platform (fill, PCC)", faces,
                       "platform", 0))
    st = doc["settings"]
    fin_on = st.get("finish_on", True)
    ft = float(st.get("stair_fin_t", 0.02) or 0.0) if fin_on else 0.0
    frt = float(st.get("stair_fin_rt", 0.015) or 0.0) if fin_on else 0.0
    nos = float(st.get("stair_nosing", 0.025) or 0.0)
    if st.get("stair_nose_type") == "flush":
        nos = 0.0
    try:
        from . import stairs as ST_
        fcol = ST_.fin_colour(st.get("stair_fin", "marble"))
    except Exception:  # noqa: BLE001
        fcol = None
    fcol = tuple(fcol) if fcol else (0.92, 0.91, 0.88)
    from shapely import affinity as _aff
    from shapely.geometry import LineString as _LS
    for k, (name, pcs) in enumerate(parts["steps"], 1):
        f_ = []
        for p_ in pcs:
            pc, zt = p_[0], p_[1]
            o = p_[2] if len(p_) > 2 else None
            rr = p_[3] if len(p_) > 3 else 0.15
            if o is None or ft <= 0:
                f_ += _prism(pc, zg, zt)
                continue
            if isinstance(o, dict):
                # a whole riser line (round its corners): the tread's finish
                # out over the riser by the nosing, the riser's finish
                f_ += _prism(pc, zg, zt - ft)
                edge, dn = o["edge"], o["down"]
                tf = pc.union(edge.buffer(dn * (nos + frt), single_sided=True,
                                          join_style=2, mitre_limit=4.0)) \
                    if nos + frt > 1e-4 else pc
                f_ += [dict(fc, color=fcol) for fc in
                       _prism(tf.buffer(0), zt - ft, zt)]
                if frt > 0:
                    rs = edge.buffer(dn * frt, single_sided=True,
                                     join_style=2, mitre_limit=4.0)
                    f_ += [dict(fc, color=fcol) for fc in
                           _prism(rs, max(zg, zt - rr), zt - ft, 0.002)]
                continue
            # the step as the stairs': concrete, the tread's finish with its
            # nosing out over the riser, the riser's finish
            f_ += _prism(pc, zg, zt - ft)
            tread_f = pc.union(_aff.translate(pc, o[0] * (nos + frt),
                                              o[1] * (nos + frt))) \
                if nos + frt > 1e-4 else pc
            f_ += [dict(fc, color=fcol) for fc in _prism(tread_f, zt - ft, zt)]
            if frt > 0:
                # the front edge: the polygon's side farthest along o
                cs = list(pc.exterior.coords)[:-1]
                ds = [x * o[0] + y * o[1] for x, y in cs]
                dm = max(ds)
                fr = [c for c, d in zip(cs, ds) if d > dm - 0.02]
                if len(fr) >= 2:
                    rs2 = _aff.translate(_LS(fr[:2]), o[0] * frt / 2,
                                         o[1] * frt / 2).buffer(
                        frt / 2, cap_style=2)
                    f_ += [dict(fc, color=fcol) for fc in
                           _prism(rs2, max(zg, zt - rr), zt - ft, 0.002)]
        if f_:
            out.append(grp(name, f_, "steps", k))
    for k, (name, f_) in enumerate(parts["ramps"], 1):
        out.append(grp(name, f_, "ramp", k))
    return out


def _site_groups(doc):
    """Boundary wall, pillars and gates (their own layer) and the gates'
    swings (the site plan's notes). Each gate with its two pillars is ONE
    block («Gate n»): moved with the Move tool, it slides along its wall
    (the wall's opening follows); the gate itself the IngeTrazo library's
    gate model where there is one."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh
    from . import components as CP
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
    blocks = {}                               # gate index -> [groups]

    def mesh_of_(faces):
        mesh = Mesh()
        for f in faces:
            if isinstance(f, dict):
                _safe_add(mesh, [QVector3D(*q) for q in f["loop"]],
                          [[QVector3D(*q) for q in hh] for hh in f["holes"]])
            else:
                _safe_add(mesh, [QVector3D(*q) for q in f])
        _soften(mesh)
        return mesh
    lib_done = set()
    for k, part in enumerate(parts):
        name, kind, faces, color = part[:4]
        gi = part[4] if len(part) > 4 else None
        if kind == "gate" and gi is not None and gi not in lib_done:
            gk = doc["site"]["gates"][gi]
            fr_ = SITE_.gate_frame(corners, gk, float(doc["site"]["t"]))
            if fr_ is not None:
                p0, p1, u, nv = fr_
                gh = max(float(doc["site"]["h"]) - 0.15, 0.6)
                wd = math.dist(p0, p1)
                two = gk.get("kind") == "double" or wd > 2.4
                lib = _gate_lib(doc, wd / 2 if two else wd, gh)
                if lib is not None:
                    t_ = float(doc["site"]["t"])
                    mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
                    # each leaf in its own frame — x along the wall, y
                    # across it; the second leaf mirrored (a pair)
                    legs = [(p0, mid, False), (mid, p1, True)] if two \
                        else [(p0, p1, False)]
                    lg = []
                    for li_, (a_, b_, mir) in enumerate(legs):
                        uu = (b_[0] - a_[0], b_[1] - a_[1])
                        ln = math.hypot(*uu) or 1.0
                        uu = (uu[0] / ln, uu[1] / ln)
                        nn = (-uu[1], uu[0])
                        c0 = (a_[0] + nv[0] * (t_ / 2) - nn[0] * 0.06,
                              a_[1] + nv[1] * (t_ / 2) - nn[1] * 0.06)
                        box = [c0, (c0[0] + uu[0] * ln, c0[1] + uu[1] * ln),
                               (c0[0] + uu[0] * ln + nn[0] * 0.12,
                                c0[1] + uu[1] * ln + nn[1] * 0.12),
                               (c0[0] + nn[0] * 0.12, c0[1] + nn[1] * 0.12)]
                        bf = W.solid({"outer": S._ccw(box), "holes": []},
                                     z0 + 0.02, z0 + 0.02 + gh)
                        ang = math.degrees(math.atan2(uu[1], uu[0]))
                        fr = (box[0][0], box[0][1], z0, ang)
                        try:
                            from . import library as LB
                            lf = CP.local_faces([f if isinstance(f, dict) else
                                                 {"loop": f, "holes": []}
                                                 for f in bf], fr)
                            lg += LB.groups_for(
                                lib, fr, lf,
                                f"Gate {gi + 1} · {lib.get('name')}"
                                + (f" ({li_ + 1})" if two else ""),
                                BOUNDARY_LAYER,
                                {KEY: {"type": "gate", "id": f"gate-{gi}",
                                       "level": low}},
                                ifc={"class": "IfcDoor",
                                     "name": f"Gate {gi + 1}"},
                                mirror=(mir, False)) or []
                        except Exception:  # noqa: BLE001
                            from .host import log_error
                            log_error("project gate library")
                            lg = []
                            break
                    if lg:
                        blocks.setdefault(gi, []).extend(lg)
                        lib_done.add(gi)
                        continue
        if kind == "gate" and gi in lib_done:
            continue
        g = Group(mesh_of_(faces), name=name)
        g.component = False
        g.material = {"color": color, "opacity": 1.0}
        g.layer = BOUNDARY_LAYER
        g.ifc = {"class": "IfcWall" if kind == "boundary" else
                 "IfcColumn" if kind in ("pillar", "gatepillar") else
                 "IfcDoor", "name": name}
        if gi is not None:
            g.ext = {KEY: {"type": "gate", "id": f"gate-{gi}", "level": low}}
            blocks.setdefault(gi, []).append(g)
            continue
        g.ext = {KEY: {"type": "site", "id": f"site-{k}", "level": low}}
        out.append(g)
    for gi, kids in sorted(blocks.items()):
        gk = doc["site"]["gates"][gi]
        fr_ = SITE_.gate_frame(corners, gk, float(doc["site"]["t"]))
        at = [round((fr_[0][0] + fr_[1][0]) / 2, 4),
              round((fr_[0][1] + fr_[1][1]) / 2, 4), round(z0, 4)] \
            if fr_ else [0.0, 0.0, z0]
        blk = Group(Mesh(), name=f"Gate {gi + 1} (with its pillars)")
        blk.adopt(kids)
        blk.component = False
        blk.layer = BOUNDARY_LAYER
        blk.ext = {KEY: {"type": "gate", "id": f"gate-{gi}", "level": low,
                         "at": at}}
        out.append(blk)
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


def moved_gates(scene, doc, seen: dict) -> list:
    """Gate blocks moved with the Move tool: [(gate index, new pos)] — the
    move taken along the gate's wall side."""
    from PySide6.QtGui import QVector3D

    from .engine import plotgeo
    plot = doc["arch"].get("plot")
    if not plot:
        return []
    corners = plotgeo.clean(plot["corners"])
    out = []
    for g in list(scene.groups):
        tag = tag_of(g)
        if not tag or tag.get("type") != "gate" or "at" not in tag:
            continue
        xf = getattr(g, "xform", None)
        if xf is None:
            continue
        at = tag["at"]
        q = xf.map(QVector3D(float(at[0]), float(at[1]), float(at[2])))
        dx, dy = q.x() - at[0], q.y() - at[1]
        if math.hypot(dx, dy) < 0.005:
            continue
        key = (getattr(g, "uid", id(g)), round(q.x(), 3), round(q.y(), 3))
        if key in seen:
            continue
        seen[key] = True
        try:
            gi = int(str(tag["id"]).split("-")[1])
            gk = doc["site"]["gates"][gi]
        except Exception:  # noqa: BLE001
            continue
        _a, u, _nv, L = SITE_.side_frame(corners, gk["side"])
        pos = float(gk["pos"]) + dx * u[0] + dy * u[1]
        pos = min(max(pos, gk["w"] / 2 + 0.05), L - gk["w"] / 2 - 0.05)
        out.append((gi, round(pos, 4)))
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
        if ring.geom_type != "Polygon" and not ring.is_empty:
            ring = max(ring.geoms, key=lambda g_: g_.area)   # its main body
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


def _furniture_pose(f, pr, z):
    """The placement of a furniture model: its footprint's middle on
    (x, y), standing on z, turned ``rot`` degrees."""
    from PySide6.QtGui import QMatrix4x4
    x0, y0, z0, x1, y1, z1 = pr["box"]
    m = QMatrix4x4()
    m.translate(float(f["x"]), float(f["y"]), z)
    if abs(float(f.get("rot", 0.0) or 0.0)) > 1e-9:
        m.rotate(float(f["rot"]), 0.0, 0.0, 1.0)
    fit = f.get("fit")
    if fit and len(fit) == 2:            # fitted to the CAD block's sides
        try:
            sx = float(fit[0]) / max(x1 - x0, 1e-6)
            sy = float(fit[1]) / max(y1 - y0, 1e-6)
            if f.get("fit_free"):           # a lift / a wardrobe run
                sz = 1.0
                if f.get("fit_h"):
                    sz = float(f["fit_h"]) / max(z1 - z0, 1e-6)
                    sz = min(max(sz, 0.7), 1.4)
                m.scale(sx, sy, sz)
            elif 0.75 <= sx <= 1.33 and 0.75 <= sy <= 1.33:
                m.scale(sx, sy, 1.0)        # (far off: the model's own size)
        except (TypeError, ValueError):
            pass
    m.translate(-(x0 + x1) / 2, -(y0 + y1) / 2, -z0)
    return m


def _furniture_groups(doc):
    """The furniture placed in rooms: IngeTrazo library models, one
    component each (the same model shares its mesh)."""
    from core.group import Group

    from . import library as LB
    arch = doc["arch"]
    elev = elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    out = []
    _rooms_cache = {}
    for f in doc.get("furniture") or []:
        if f["level"] not in z_of:
            continue
        pr = LB.proto(f["key"], f.get("entry"))
        if pr is None:
            continue
        rec = next((r for r in arch["rooms"] if r["id"] == f.get("room")),
                   None)
        z = z_of[f["level"]] + (room_finish(doc, rec)
                                if doc["settings"].get("finish_on", True)
                                else 0.0)
        if f.get("hang"):              # hung under the false ceiling
            try:
                from . import fitout as FO
                rms = _rooms_cache.get(f["level"])
                if rms is None:
                    rms = _rooms_cache[f["level"]] = FO._rooms(
                        arch, f["level"])
                h_ = FO.ceiling_h(doc, f["level"],
                                  FO._room_at(rms, f["x"], f["y"]),
                                  float(f["hang"]))
            except Exception:  # noqa: BLE001
                h_ = float(f["hang"])
            z = z_of[f["level"]] + h_ - (pr["box"][5] - pr["box"][2])
        base = _furniture_pose(f, pr, z)
        nm = f"{f.get('name', 'Furniture')} · {names[f['level']]}"
        if len(pr["parts"]) == 1:
            mesh, xf = pr["parts"][0]
            g = Group(mesh, name=nm)
            g.xform = base * xf if xf is not None else base
        else:                          # a model in parts: ONE object
            from PySide6.QtGui import QMatrix4x4
            from core.mesh import Mesh
            kids = []
            for mesh, xf in pr["parts"]:
                k = Group(mesh, name=nm)
                k.xform = QMatrix4x4(xf) if xf is not None else QMatrix4x4()
                kids.append(k)
            g = Group(Mesh(), name=nm)
            g.adopt(kids)
            g.xform = base
        g.component = True
        g.layer = level_layer(names[f["level"]])
        g.ifc = {"class": "IfcFurniture", "name": f.get("name", "")}
        g.ext = {KEY: {"type": "furniture", "id": f["id"],
                       "level": f["level"],
                       "at": [float(f["x"]), float(f["y"]),
                              float(f.get("rot", 0.0) or 0.0)]}}
        out.append(g)
    return out


def moved_furniture(scene, doc) -> int:
    """Furniture moved / turned with IngeTrazo's tools: its record follows
    (no rebuild). How many changed."""
    import math as _m
    recs = {f["id"]: f for f in doc.get("furniture") or []}
    n = 0
    for g in getattr(scene, "groups", []):
        t = tag_of(g)
        if not t or t.get("type") != "furniture" or g.xform is None:
            continue
        f = recs.get(t["id"])
        if f is None:
            continue
        m = g.xform
        from . import library as LB0
        pr0 = LB0.proto(f["key"], f.get("entry"))
        if pr0 is not None and len(pr0["parts"]) == 1 and \
                pr0["parts"][0][1] is not None:
            inv, ok = pr0["parts"][0][1].inverted()
            if ok:
                m = m * inv
        # where the model's local origin went, and the turn of its x axis
        c = m.map(__import__("PySide6.QtGui", fromlist=["QVector3D"])
                  .QVector3D(0, 0, 0))
        ax = m.mapVector(__import__("PySide6.QtGui", fromlist=["QVector3D"])
                         .QVector3D(1, 0, 0))
        rot = _m.degrees(_m.atan2(ax.y(), ax.x()))
        at = t.get("at") or [f["x"], f["y"], f.get("rot", 0.0)]
        from . import library as LB
        pr = LB.proto(f["key"], f.get("entry"))
        if pr is None:
            continue
        x0, y0, _z0, x1, y1, _z1 = pr["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = _m.radians(rot)
        # the footprint's middle, back from the origin's place
        nx = c.x() + cx * _m.cos(r) - cy * _m.sin(r)
        ny = c.y() + cx * _m.sin(r) + cy * _m.cos(r)
        if abs(nx - at[0]) > 1e-3 or abs(ny - at[1]) > 1e-3 or \
                abs(((rot - at[2] + 180) % 360) - 180) > 0.05:
            f["x"], f["y"], f["rot"] = round(nx, 4), round(ny, 4), \
                round(rot, 3)
            t["at"] = [f["x"], f["y"], f["rot"]]
            n += 1
    return n


def _ceiling_groups(doc):
    """The false ceilings: one group per room (plan views cut under them),
    on the level's layer, IfcCovering."""
    from PySide6.QtGui import QVector3D

    from core.group import Group
    from core.mesh import Mesh

    from . import ceilings as CE
    if not doc.get("ceilings") and not any(
            r.get("ceiling") in CE.BY for r in doc["arch"]["rooms"]):
        return []                 # no level's ceiling, no room's own
    arch = doc["arch"]
    elev = elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    out = []
    for lid, rname, kind, h, parts, *rk_ in CE.build(doc, z_of, room_key):
        mesh = Mesh()
        for fs, col in parts:
            for f in fs:
                if not isinstance(f, dict):
                    f = {"loop": f, "holes": []}
                face = _safe_add(mesh, [QVector3D(*q) for q in f["loop"]],
                                     [[QVector3D(*q) for q in hh]
                                      for hh in f.get("holes") or []])
                if face is not None:
                    face.attrs["color"] = tuple(col[:3])
        if not mesh.faces:
            continue
        _soften(mesh)
        nm = f"False ceiling · {CE.label(kind)} · {rname} · {names[lid]}"
        g = Group(mesh, name=nm)
        g.component = False
        g.material = {"color": (0.95, 0.95, 0.94), "opacity": 1.0}
        g.layer = level_layer(names[lid])
        g.ifc = {"class": "IfcCovering", "name": nm}
        g.ext = {KEY: {"type": "ceiling",
                       "id": rk_[0] if rk_ else f"{lid}|{rname}",
                       "level": lid}}
        out.append(g)
    return out


def _level_at_fn(doc, i, lid):
    """level_at(q) → (slab top, finished floor) on level ``lid`` (index
    ``i``): the room's own finish over its own (sunk / raised) floor."""
    from shapely.geometry import Point as _Pt
    arch = doc["arch"]
    elev = elevations(arch)
    rooms_ = spaces.of_level(arch, lid)
    ft_ = float(doc["settings"].get("finish_t", 0.0508))

    def level_at(q):
        base = elev[i] + floor_offset_at(doc, lid, q)
        pt = _Pt(q)
        r = next((r for r in rooms_ if r["poly"].contains(pt)), None)
        f = room_finish(doc, r.get("rec")) if r else ft_
        return base, base + f
    return level_at


def door_lifts(doc) -> dict:
    """{door id: how far its threshold's top stands over its level's floor
    line}: the door's frame and leaf stand on the threshold."""
    from . import slabedges as SE
    st = doc["settings"]
    out = {}
    if not (st.get("thresholds", True) and st.get("finish_on", True)):
        return out
    arch = doc["arch"]
    elev = elevations(arch)
    ft_ = float(st.get("finish_t", 0.0508))
    for i, lv in enumerate(arch["levels"]):
        lid = lv["id"]
        tops = {}
        try:
            SE.threshold_faces(doc, lid, elev[i] + open_offset(doc, lid),
                               ft_, _level_at_fn(doc, i, lid), tops)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project door_lifts")
            continue
        for k, zb in tops.items():
            if zb - elev[i] > 0.002:
                out[k] = round(zb - elev[i], 4)
    return out


def _edge_groups(doc):
    """Sun shades over the outer windows (the floors that have them) and
    granite thresholds in the door openings, one group a level each."""
    from core.group import Group

    from . import slabedges as SE
    arch = doc["arch"]
    st = doc["settings"]
    elev = elevations(arch)
    out = []
    for i, lv in enumerate(arch["levels"]):
        lid = lv["id"]
        z0 = elev[i] + open_offset(doc, lid)
        parts = []
        try:
            fs = SE.sunshade_faces(doc, lid, elev[i])
            if fs:
                parts.append(("sunshade", "Sun shades (chajja)", fs,
                              (0.80, 0.80, 0.78), "IfcShadingDevice"))
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project sunshades")
        if st.get("thresholds", True) and st.get("finish_on", True):
            try:
                from shapely.geometry import Point as _Pt
                rooms_ = spaces.of_level(arch, lid)
                ft_ = float(st.get("finish_t", 0.0508))

                def level_at(q, _i=i, _lid=lid, _rooms=rooms_):
                    # the slab top and the finished floor there: the room's
                    # own finish over its own (sunk / raised) floor
                    base = elev[_i] + floor_offset_at(doc, _lid, q)
                    pt = _Pt(q)
                    r = next((r for r in _rooms if r["poly"].contains(pt)),
                             None)
                    f = room_finish(doc, r.get("rec")) if r else ft_
                    return base, base + f
                fs = SE.threshold_faces(doc, lid, z0, ft_, level_at)
                if fs:
                    parts.append(("threshold", "Granite thresholds", fs,
                                  (0.20, 0.20, 0.22), "IfcCovering"))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project thresholds")
        for s_ in arch["structure"]:     # roof terraces over this floor
            if s_["type"] != "slab" or s_["id"] not in set(
                    doc.get("roof_terraces") or []):
                continue
            try:
                from . import slabedges as _SE
                if _SE.floor_level_of(doc, s_) != lid:
                    continue
                fs = roof_terrace_faces(doc, s_, elev[i])
                if fs:
                    parts.append(("terrace_floor", "Roof terrace tiles", fs,
                                  TERRACE_TILE, "IfcCovering"))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project roof terrace")
        if st.get("curtains"):
            try:
                from . import curtains as CT
                fs = CT.faces(doc, lid, elev[i])
                if fs:
                    parts.append(("curtain", "Curtains", fs,
                                  (0.88, 0.83, 0.72), "IfcFurnishingElement"))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("project curtains")
        for kind, label, fs, col, cls in parts:
            nm = f"{label} · {lv['name']}"
            g = Group(_mesh_of(fs), name=nm)
            g.component = False
            g.material = {"color": col, "opacity": 1.0}
            g.layer = level_layer(lv["name"])
            g.ifc = {"class": cls, "name": nm}
            g.ext = {KEY: {"type": kind, "id": f"{kind}-{lid}",
                           "level": lid}}
            out.append(g)
    return out


def _shoring_groups(doc):
    """The shoring along the plot limits (a basement dig): one group per
    plot side, on the lowest basement's layer."""
    from core.group import Group

    from . import shoring as SH
    arch = doc["arch"]
    sides = SH.build(doc, elevations(arch))
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    kind = doc["settings"].get("shoring_type", "piles")
    out = []
    if doc["settings"].get("shoring_on", "plot") == "walls" and sides:
        # round the basement walls: one shoring, all the way round
        tot = sum(L for _k, L, _f, _l in sides)
        sides = [(1, tot, [f for _k, _L, fs, _l in sides for f in fs],
                  sides[0][3])]
    for k, L, fs, lid in sides:
        if not fs:
            continue
        mesh = _mesh_of(fs)
        _soften(mesh)
        nm = f"Shoring · {SH.LABELS.get(kind, kind)} · side {k} ({L:.1f} m)"
        g = Group(mesh, name=nm)
        g.component = False
        g.material = {"color": (0.62, 0.62, 0.60), "opacity": 1.0}
        g.layer = level_layer(names[lid])
        g.ifc = {"class": "IfcPile" if kind != "sheet" else "IfcWall",
                 "name": nm}
        g.ext = {KEY: {"type": "shoring", "id": f"shoring-{k}",
                       "level": lid}}
        out.append(g)
    return out


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
            face = _safe_add(mesh, [QVector3D(*q) for q in f["loop"]],
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
            _safe_add(mesh, [QVector3D(*q) for q in f["loop"]],
                          [[QVector3D(*q) for q in h] for h in f["holes"]])
        else:
            _safe_add(mesh, [QVector3D(*q) for q in f])
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
    try:                    # furniture, fixtures, cars: light unless asked
        from . import library as _LB
        _LB.LOWPOLY[0] = not doc["settings"].get("hi_poly", False)
    except Exception:  # noqa: BLE001
        pass
    arch["levels"] = M.fix_levels(arch["levels"])
    arch["_plaster"] = float(doc["settings"].get("plaster_t", 0.0127) or 0.0)
    arch["_walls_down"] = not slab_on_top(doc)
    arch["_ground_down"] = (float(doc["settings"].get(
        "ext_finish_drop", 0.3048) or 0.0) if not slab_on_top(doc)
        and not ground_slab_on(doc) else 0.0)
    if platform_on(doc):          # on the platform: the walls down to N.G.L.
        arch["_ground_down"] = max(arch["_ground_down"], float(
            doc["settings"].get("plinth", 0.6096) or 0.0))
    apply_ground_ffl(doc)
    apply_slab_pos(doc)
    if doc["settings"].get("hidden_rules", True):   # openings not read yet
        try:
            apply_hidden_lines_new(doc)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.apply_hidden_lines_new")
    try:                       # slabs as floors: the roof over the top floor
        ensure_roof(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.ensure_roof")
    try:
        apply_man_shafts(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.apply_man_shafts")
    try:                       # the roof's and the openings' railings
        opening_parapets(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.opening_parapets")
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
        new_groups += _platform_groups(doc)
    except Exception:  # noqa: BLE001 — the plot never blocks the building
        from .host import log_error
        log_error("project._plot_groups")
    try:
        from . import minarets as MN_
        new_groups += MN_.groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.minarets groups")
    try:
        from . import domes as DM_
        new_groups += DM_.groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.domes groups")
    try:
        from . import lowparts as LP
        new_groups += LP.groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.lowparts groups")
    try:
        new_groups += _furniture_groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._furniture_groups")
    try:
        from . import fitout as FO
        new_groups += FO.groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.fitout groups")
    try:
        new_groups += _edge_groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._edge_groups")
    try:
        new_groups += _shoring_groups(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._shoring_groups")
    try:
        new_groups += _ceiling_groups(doc)
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
    off_ = set(doc.get("off3d") or [])
    if off_:                         # (a wall's doors and windows go too)
        offw = {k.split("|", 1)[1] for k in off_ if k.startswith("wall|")}
        off_ |= {f"opening|{o['id']}" for o in arch["openings"]
                 if o["wall"] in offw}
    if off_:                         # drawn on a floor they are not on
        def _keep(g):
            t_ = tag_of(g) or {}
            return f"{t_.get('type')}|{t_.get('id')}" not in off_ and \
                f"{'stair' if t_.get('type') == 'stairrail' else ''}|" \
                f"{t_.get('id')}" not in off_
        new_groups = [g for g in new_groups if _keep(g)]
    try:                              # the solid parapets' copings
        new_groups += _parapet_groups(doc, new_groups)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project._parapet_groups")
    _apply_materials(new_groups, doc.get("materials") or {})
    try:                             # the rooms' / terraces' materials
        from . import matlib as ML
        ML.apply(new_groups, doc, tag_of,
                 lambda gs: _walk_groups(gs))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project room materials")
    box = doc["settings"].get("section_box")
    if box and len(box) == 6:            # the section box: cut to it
        try:
            from . import secbox as SB
            SB.cut(new_groups, [float(v) for v in box])
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project section box")
    if doc["settings"].get("level_groups"):
        try:
            new_groups = group_by_level(new_groups, arch)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("project.group_by_level")
    arch.pop("_plaster", None)
    arch.pop("_walls_down", None)
    arch.pop("_ground_down", None)
    data = copy.deepcopy(doc)
    arch["_plaster"] = float(doc["settings"].get("plaster_t", 0.0127) or 0.0)
    arch["_walls_down"] = not slab_on_top(doc)
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


PLOT_ITEM = "__plot__"      # «Plot + shoring (site)» in the overlap lists


def plot_centre(doc):
    plot = doc["arch"].get("plot") or {}
    pts = [p for p in plot.get("corners") or [] if _is_pt(p)]
    if len(pts) < 3:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def transform_plot(doc, fn) -> bool:
    """The plot (its corners — the setbacks, boundary wall, gates and
    the shoring along it follow) and the excavations / fills mapped by
    ``fn((x, y)) → (x, y)``. False when there is no plot."""
    arch = doc["arch"]
    plot = arch.get("plot")
    if not plot or len(plot.get("corners") or []) < 3:
        return False
    plot["corners"] = [[round(q[0], 4), round(q[1], 4)] + list(p[2:])
                       for p in plot["corners"] for q in [fn(p)]]
    for d in arch.get("digs") or []:
        d["corners"] = [[round(q[0], 4), round(q[1], 4)] + list(p[2:])
                        for p in d.get("corners") or [] for q in [fn(p)]]
    return True


def move_plot(doc, dx, dy) -> bool:
    return transform_plot(doc, lambda p: (p[0] + dx, p[1] + dy))


def rotate_plot(doc, deg, centre=None) -> bool:
    c = centre or plot_centre(doc)
    if c is None:
        return False
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return transform_plot(doc, lambda p: (
        c[0] + (p[0] - c[0]) * ca - (p[1] - c[1]) * sa,
        c[1] + (p[0] - c[0]) * sa + (p[1] - c[1]) * ca))


def plot_overlap_offset(doc, ref, how="centre"):
    """(dx, dy) that lays the plot over level ``ref``'s building: centres
    together («best» too), or the lower-left corners together."""
    plot = doc["arch"].get("plot") or {}
    pp = [p for p in plot.get("corners") or [] if _is_pt(p)]
    wp = [p for w in doc["arch"]["walls"] if w["level"] == ref
          for p in (w.get("a"), w.get("b")) if _is_pt(p)]
    if len(pp) < 3 or not wp:
        return None
    if how == "ll":
        return (min(p[0] for p in wp) - min(p[0] for p in pp),
                min(p[1] for p in wp) - min(p[1] for p in pp))
    cb = ((min(p[0] for p in wp) + max(p[0] for p in wp)) / 2,
          (min(p[1] for p in wp) + max(p[1] for p in wp)) / 2)
    cp = plot_centre(doc)
    return cb[0] - cp[0], cb[1] - cp[1]


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


def plan_lines_near(doc, lid, boxes, lo=0.3, hi=3.0) -> list:
    """The CAD plan's lines of level ``lid`` (any layer but the walls',
    doors', windows', grid and text) ``lo``–``hi`` m long inside any of
    ``boxes`` [(x0, y0, x1, y1)], in model coordinates: [((x, y), (x, y))]
    — the winder diagonals of a stair's landings."""
    how = doc["imports"].get(lid)
    if not how or not how.get("file") or not boxes:
        return []
    st = doc["settings"]
    try:
        drawing = cadread.crop(cadread.read(how["file"], how.get("unit")),
                               how.get("region"))
    except Exception:  # noqa: BLE001
        return []
    base = cadread.base_point(drawing, how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    pl = cadread.place(drawing, base, (how.get("ix", 0.0), how.get("iy", 0.0)),
                       how.get("rot", 0.0))
    P, _f = layer_patterns(drawing, how, st)
    lay = pl["layers"]
    skip = [P.get(k) for k in ("walls", "doors", "windows", "grid", "text",
                               "columns")]
    out = []
    for s_ in pl["segs"]:
        ln = lay[s_[4]]
        if any(pp and _match(ln, pp) for pp in skip):
            continue
        a, b = (s_[0], s_[1]), (s_[2], s_[3])
        L = math.dist(a, b)
        if not lo <= L <= hi:
            continue
        if any(bx[0] <= min(a[0], b[0]) and max(a[0], b[0]) <= bx[2] and
               bx[1] <= min(a[1], b[1]) and max(a[1], b[1]) <= bx[3]
               for bx in boxes):
            out.append((a, b))
    return out


def stair_cut_lines(segs) -> set:
    """The stair's cut symbol — the break line drawn slantwise across a
    flight where the plan cuts it at eye level (often with a zigzag in
    it): indices of ``segs`` [((x, y), (x, y))] that are not treads. A
    slant line crossing two or more treads, and the short pieces of its
    zigzag touching it."""
    from shapely.geometry import LineString, Point
    if len(segs) < 3:
        return set()
    # the treads' direction: the longest-weighted angle (mod 90)
    hist = {}
    for a, b in segs:
        L = math.dist(a, b)
        if L < 0.3:
            continue
        k = round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                  % 90.0) % 90
        hist[k] = hist.get(k, 0.0) + L
    if not hist:
        return set()
    main = max(hist, key=hist.get)

    def off(a, b):
        g = (math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) - main) % 90.0
        return min(g, 90.0 - g)
    square = [i for i, (a, b) in enumerate(segs) if off(a, b) <= 6.0]
    lines = {i: LineString(segs[i]) for i in range(len(segs))}
    cut = set()
    for i, (a, b) in enumerate(segs):
        if math.dist(a, b) < 0.5 or off(a, b) < 12.0:
            continue
        L_ = lines[i]
        n = 0
        for j in square:
            if j == i:
                continue
            x = L_.intersection(lines[j])
            if x.is_empty or x.geom_type != "Point":
                continue
            # a real crossing: not at either line's end
            if min(Point(p).distance(x) for p in segs[j]) > 0.03 and \
                    min(Point(p).distance(x) for p in (a, b)) > 0.03:
                n += 1
        if n >= 2:
            cut.add(i)
    if cut:                         # its zigzag: short pieces touching it
        zone = [lines[i].buffer(0.06) for i in cut]
        for i, (a, b) in enumerate(segs):
            if i in cut or math.dist(a, b) > 0.4 or off(a, b) <= 6.0 and \
                    math.dist(a, b) > 0.15:
                continue
            if any(z.contains(Point(a)) or z.contains(Point(b))
                   for z in zone):
                cut.add(i)
    return cut


def stair_treads_whole(segs) -> list:
    """The tread lines broken by the plan (a cut symbol, a walking line, a
    note across them) made whole: pieces of one line joined over gaps up
    to 0.6 m, and a line cut short between two whole neighbours of its
    flight run out to theirs. [((x, y), (x, y))]."""
    items = []
    for a, b in segs:
        L = math.dist(a, b)
        if L < 0.02:
            continue
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
        items.append([a, b, ang])
    fams = {}
    for a, b, ang in items:
        k = round(ang) % 180
        fams.setdefault(k, []).append((a, b))
    out = []
    for k, lines in fams.items():
        u = (math.cos(math.radians(k)), math.sin(math.radians(k)))
        n = (-u[1], u[0])
        rows = {}
        for a, b in lines:
            off = a[0] * n[0] + a[1] * n[1]
            t0 = a[0] * u[0] + a[1] * u[1]
            t1 = b[0] * u[0] + b[1] * u[1]
            key = next((q for q in rows if abs(q - off) < 0.02), off)
            rows.setdefault(key, []).append((min(t0, t1), max(t0, t1)))
        merged = {}
        for off, iv in rows.items():
            iv.sort()
            cur = [list(iv[0])]
            for t0, t1 in iv[1:]:
                if t0 - cur[-1][1] <= 0.6:
                    cur[-1][1] = max(cur[-1][1], t1)
                else:
                    cur.append([t0, t1])
            merged[off] = cur
        offs = sorted(merged)
        for i, off in enumerate(offs):
            for iv in merged[off]:
                t0, t1 = iv
                # between two whole neighbours (a tread apart): theirs
                nb = []
                for j in (i - 1, i + 1):
                    if 0 <= j < len(offs) and 0.18 <= abs(offs[j] - off) \
                            <= 0.40:
                        nb += [q for q in merged[offs[j]]
                               if q[0] <= t1 and q[1] >= t0]
                if len(nb) >= 2:
                    lo = max(q[0] for q in nb)
                    hi = min(q[1] for q in nb)
                    if hi - lo > t1 - t0 and (t1 - t0) >= 0.4 * (hi - lo) \
                            and t0 >= lo - 0.05 and t1 <= hi + 0.05:
                        t0, t1 = lo, hi
                out.append(((off * n[0] + t0 * u[0], off * n[1] + t0 * u[1]),
                            (off * n[0] + t1 * u[0], off * n[1] + t1 * u[1])))
    return out


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
    if not segs:
        return []
    try:                         # the cut symbol across a flight: not treads
        cut_ = stair_cut_lines(segs)
        if cut_:
            cut_xy = [segs[i] for i in cut_]
            segs = [sg for i, sg in enumerate(segs) if i not in cut_]
            if not segs:
                return []
        else:
            cut_xy = []
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.stair_cut_lines")
        cut_xy = []

    try:                         # treads broken by the plan: whole again
        segs = stair_treads_whole(segs)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.stair_treads_whole")

    def _is_cut(a_, b_):
        return any(math.dist(a_, c0) < 0.02 and math.dist(b_, c1) < 0.02
                   or math.dist(a_, c1) < 0.02 and math.dist(b_, c0) < 0.02
                   for c0, c1 in cut_xy)
    chains = ST.trace(segs, words)
    # the rest of the stair as drawn on other layers (the upper flight,
    # its landing treads…): tread lines of any layer but the walls', doors'
    # and windows' round the stair found, traced with it
    try:
        boxes = []
        for ch in chains:
            xs = [p[0] for f in ch for ln in f["lines"] for p in ln]
            ys = [p[1] for f in ch for ln in f["lines"] for p in ln]
            if xs:
                boxes.append((min(xs) - 1.6, min(ys) - 1.6,
                              max(xs) + 1.6, max(ys) + 1.6))
        if boxes:
            skip = [P.get(k) for k in ("walls", "doors", "windows", "stairs",
                                       "grid", "text", "columns")]
            extra = []
            for s_ in pl["segs"]:
                ln = lay[s_[4]]
                if any(pp and _match(ln, pp) for pp in skip):
                    continue
                L = math.dist((s_[0], s_[1]), (s_[2], s_[3]))
                if not 0.5 <= L <= 2.6:
                    continue
                mx, my = (s_[0] + s_[2]) / 2, (s_[1] + s_[3]) / 2
                if any(b[0] <= mx <= b[2] and b[1] <= my <= b[3]
                       for b in boxes):
                    extra.append(((s_[0], s_[1]), (s_[2], s_[3])))
            if extra:                # (a cut symbol on another layer: out)
                cx_ = stair_cut_lines(segs + extra)
                extra = [e_ for k_, e_ in enumerate(extra)
                         if k_ + len(segs) not in cx_]
            if extra:
                more = ST.trace(segs + extra, words)
                own = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                       for a, b in segs]

                def mine(f):
                    return any(math.dist(((a[0] + b[0]) / 2,
                                          (a[1] + b[1]) / 2), q) < 0.02
                               for a, b in f["lines"] for q in own)
                # a short run of the other layers' lines (a cupboard's
                # shelves): not a flight
                more = [[f for f in ch if mine(f) or len(f["lines"]) >= 4]
                        for ch in more]
                more = [ch for ch in more if ch]
                n0 = sum(len(f["lines"]) for ch in chains for f in ch)
                n1 = sum(len(f["lines"]) for ch in more for f in ch)
                if len(more) == len(chains) and n1 > n0:
                    chains = more
                    segs = segs + extra
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.stair_trace extra")
    try:                         # a turn onto another stair's treads: cut
        chains = [ST.cut_at_foreign(ch, segs) for ch in chains]
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.stair_trace cut")
    try:                         # the winders' lines: diagonals across the
        for ch in chains:        # turning landings (any layer but walls…)
            if not ch:
                continue
            xs = [p[0] for f in ch for ln in f["lines"] for p in ln]
            ys = [p[1] for f in ch for ln in f["lines"] for p in ln]
            bx = (min(xs) - 2.0, min(ys) - 2.0, max(xs) + 2.0, max(ys) + 2.0)
            skip = [P.get(k) for k in ("walls", "doors", "windows", "grid",
                                       "columns")]
            dg = []
            for s_ in pl["segs"]:
                if any(pp and _match(lay[s_[4]], pp) for pp in skip):
                    continue
                a_, b_ = (s_[0], s_[1]), (s_[2], s_[3])
                L = math.dist(a_, b_)
                if not 0.6 <= L <= 4.0 or abs(a_[0] - b_[0]) < 0.2 or \
                        abs(a_[1] - b_[1]) < 0.2:
                    continue             # level / plumb: not a diagonal
                if all(bx[0] <= q[0] <= bx[2] and bx[1] <= q[1] <= bx[3]
                       for q in (a_, b_)) and not _is_cut(a_, b_):
                    dg.append([list(a_), list(b_)])
            if dg:                   # a slant line across the treads: the
                tl = [tuple(map(tuple, ln)) for f in ch   # cut symbol
                      for ln in f["lines"]]
                cx_ = stair_cut_lines(tl + [tuple(map(tuple, d_))
                                            for d_ in dg])
                dg = [d_ for k_, d_ in enumerate(dg)
                      if k_ + len(tl) not in cx_]
            ch[0]["_diag"] = dg
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("project.stair_trace winders")
    return chains


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


# =====================================================================================
# Arcades and rows of arched openings (as the elevations draw them)
# =====================================================================================
def arcade_over_columns(doc, col_ids, t=0.45, sill=0.0, top_gap=0.9,
                        style="pointed", ring="ablaq") -> str | None:
    """A wall standing on the selected columns (in a row) — its arches
    between them: an arched opening from ``sill`` up to ``top_gap`` under
    the wall's top in each bay, columns paired close together counted as
    one pier. None, or why not."""
    arch = doc["arch"]
    cols = [c for c in arch["structure"] if c["type"] == "column"
            and c["id"] in set(col_ids)]
    if len(cols) < 2:
        return "Select two columns or more, in a row"
    lid = cols[0]["level"]
    pts = [(float(c["x"]), float(c["y"]), max(float(c["w"]), float(c["d"])))
           for c in cols]
    # the row's line: principal direction
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    u = (math.cos(ang), math.sin(ang))
    proj = sorted(((p[0] - mx) * u[0] + (p[1] - my) * u[1], p[2])
                  for p in pts)
    # columns close together: one pier
    piers = []
    for s, d in proj:
        if piers and s - piers[-1][1] < max(d, piers[-1][2]) * 1.6:
            piers[-1] = [piers[-1][0], s, max(d, piers[-1][2])]
        else:
            piers.append([s, s, d])
    if len(piers) < 2:
        return "The columns stand together — select a row of them"
    s0 = piers[0][0] - piers[0][2] / 2
    s1 = piers[-1][1] + piers[-1][2] / 2
    a = [round(mx + u[0] * s0, 4), round(my + u[1] * s0, 4)]
    b = [round(mx + u[0] * s1, 4), round(my + u[1] * s1, 4)]
    rec = {"kind": "line", "a": a, "b": b, "t": round(t * 200) / 200,
           "align": "centre", "side": 1, "height": "level", "base": 0.0,
           "level": lid, "arcade": True}
    w = M.new_walls(arch["walls"], [rec])[0]
    w["name"] = "Arcade " + w["name"].split()[-1]
    arch["walls"].append(w)
    info = S.levels_info(arch, M.elevations)[lid]
    H = info["under"] - info["z0"]
    ops = []
    for (p0, p1, d0), (q0, q1, d1) in zip(piers, piers[1:]):
        ga = p1 + d0 / 2 + 0.05
        gb = q0 - d1 / 2 - 0.05
        wd = gb - ga
        if wd < 0.5:
            continue
        ops.append({"kind": "void", "wall": w["id"],
                    "pos": round((ga + gb) / 2 - s0, 4), "w": round(wd, 3),
                    "h": round(max(H - sill - top_gap, 1.0), 3),
                    "sill": sill, "swing": "left", "face": 1, "style": "",
                    "head": "arch", "arch": style,
                    **({"ring": ring} if ring in ("ablaq", "plain") else {})})
    arch["openings"] += M.new_openings(arch["openings"], ops)
    return None


def openings_along(doc, wall_ids, w=0.46, h=1.4, sill=0.5, pitch=0.75,
                   group=3, gap=1.2, style="semi", grille="cnc",
                   ring=None) -> int:
    """Rows of small arched openings along the selected walls (a
    clerestory, an attic band): groups of ``group`` at ``pitch``, the
    groups ``gap`` apart, centred on each wall. How many made."""
    arch = doc["arch"]
    if grille == "cnc":                  # the jali pattern picked
        grille = doc["settings"].get("jali_style", "cnc") or "cnc"
    n = 0
    for wl in arch["walls"]:
        if wl["id"] not in set(wall_ids) or wl.get("kind", "line") != "line":
            continue
        L = math.dist(wl["a"], wl["b"])
        span = (group - 1) * pitch + w
        unit = span + gap
        k = int((L - 0.6 + gap) // unit)
        if k < 1:
            continue
        tot = k * unit - gap
        start = (L - tot) / 2
        recs = []
        for g in range(k):
            for i in range(group):
                pos = start + g * unit + w / 2 + i * pitch
                recs.append({"kind": "void", "wall": wl["id"],
                             "pos": round(pos, 4), "w": w, "h": h,
                             "sill": sill, "swing": "left", "face": 1,
                             "style": "", "head": "arch", "arch": style,
                             **({"grille": grille} if grille else {}),
                             **({"ring": ring} if ring else {})})
        arch["openings"] += M.new_openings(arch["openings"], recs)
        n += len(recs)
    return n
