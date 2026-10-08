# SPDX-License-Identifier: GPL-3.0-or-later
"""Which layer of a CAD plan holds what — found from the names (AIA /
ISO 13567 / Revit and AutoCAD exports, English, Spanish, Portuguese,
French, German, Italian, Urdu-English office habits) and, when the names
say nothing, from the drawing itself (the layer whose lines pair up at a
wall's thickness holds the walls). Blocks tell doors and windows by their
names.

``roles(drawing, tmin, tmax)`` → {role: [layer names]};
``block_kind(name, layer)`` → "door" | "window" | None.
"""
from __future__ import annotations

import re

ROLES = ("walls", "doors", "windows", "columns", "beams", "slab", "holes",
         "text", "plot", "footings", "stairs", "grid", "lift", "parking",
         "cars", "ramps")

_W = r"(^|[^A-Z])"            # a word's start: not inside another word
KEYS = {
    "walls": [r"WALL", r"MURO", r"\bMUR\b", r"^MUR", r"WAND", r"PARED",
              r"PAREDE", r"PARETE", r"A-WALL", r"BRICK", r"BLOCKWORK",
              r"MASONRY", r"PARTITION", r"TABIQUE"],
    "doors": [r"DOOR", r"PUERTA", r"PORTA", r"PORTE", r"(^|[^A-Z])T[UÜ]R($|[^A-Z])", r"A-DOOR",
              _W + r"DR[S_ -]?($|[^A-Z])", r"SHUTTER"],
    "windows": [r"WIND", r"WINDOW", r"GLAZ", r"VENTANA", r"JANELA",
                r"FENETRE", r"FENSTER", r"FINESTRA", r"A-GLAZ", r"WDW",
                _W + r"WIN($|[^A-Z])", r"GLASS", r"VENT"],
    "columns": [r"COL", r"COLUMN", r"PILAR", r"COLUMNA", r"PILASTRA",
                r"S-COLS", r"PILLAR", r"STUT"],
    "beams": [r"BEAM", r"VIGA", r"POUTRE", r"TRAVE", r"S-BEAM", r"LINTEL"],
    "slab": [r"SLAB", r"LOSA", r"LAJE", r"DALLE", r"S-SLAB",
             r"FLOOR.?OUTLINE", r"FLOOR.?EDGE"],
    "holes": [r"STAIR", r"SHAFT", r"LIFT", r"VOID", r"HOLE", r"ESCALERA",
              r"ELEVATOR", r"DUCT", r"S-OPEN", r"OPENING"],
    "text": [r"TEXT", r"TXT", r"ANNO", r"ROOM", r"NAME", r"LABEL", r"TAG",
             r"A-AREA", r"TEXTO", r"NOTE"],
    "plot": [r"PLOT", r"SITE", r"BOUNDARY", r"PROPERTY", r"\bLOT\b",
             r"PARCEL", r"TERRENO", r"LOTE", r"L-PROP", r"C-PROP",
             r"PROP.?LINE", r"LIMIT"],
    "grid": [r"GRID", r"GIRD", r"AXIS", r"AXES", r"EJE", r"S-GRID", r"CENT.?LINE",
             r"C-L\b"],
    "stairs": [r"STAIR", r"ESCAL", r"ESCADA", r"TREPP", r"SCALA",
               r"STEP", r"A-FLOR-STRS", r"RISER", r"TREAD"],
    "lift": [r"LIFT", r"ELEVATOR", r"(^|[^A-Z])CORE", r"SHEAR"],
    "parking": [r"PARK", r"PRKG", r"ESTACION", r"STALL", r"\bBAY"],
    "cars": [r"(^|[^A-Z])CARS?($|[^A-Z])", r"VEHIC", r"AUTOMOB"],
    "ramps": [r"RAMP", r"RAMPA"],
    "footings": [r"FOOT", r"FOUND", r"FNDN", r"ZAPATA", r"SAPATA",
                 r"S-FNDN", r"S-FOOT", r"PILE", r"RAFT", r"PAD"],
}
#: never a building element, whatever else the name says
NOT = [r"DIM", r"COTA", r"HATCH", r"FURN",
       r"MOBIL", r"SANIT", r"PLUMB", r"ELEC", r"TITLE", r"FRAME", r"DEFPOINTS",
       r"VIEWPORT", r"XREF", r"TREE", r"HVAC", r"LANDSC"]

_rx = {k: [re.compile(p) for p in v] for k, v in KEYS.items()}
_not = [re.compile(p) for p in NOT]


def _upper(name: str) -> str:
    return str(name or "").upper()


def by_name(name: str) -> list:
    """The roles a layer's (or block's) name points to."""
    n = _upper(name)
    if any(r.search(n) for r in _not):
        return []
    out = [k for k, rs in _rx.items() if any(r.search(n) for r in rs)]
    # a layer of notes is never an element: «COLUMN TEXT», «GRID-TEXT»…
    if any(w in n for w in ("TEXT", "TXT", "ANNO", "TAG", "LABEL", "DIM")):
        out = [k for k in out if k in ("text",)] or (["text"] if "TEXT" in n
                                                     else [])
    # a structural layer that names a run of floors («S-CONC-4 FOUNDATION
    # TO 6TH», «COL 6TH TO ROOF»): the columns that run up through them,
    # not footings
    if re.search(r"(^|[^A-Z])TO($|[^A-Z])", n) and re.search(
            r"CONC|RCC|STR|COL|FOUND|S-", n) and \
            re.search(r"FOUND|BASE|GRD|GROUND|ROOF|\d(ST|ND|RD|TH)", n):
        out = [k for k in out if k not in ("footings", "slab", "walls")]
        if "columns" not in out:
            out.append("columns")
    # the boundary wall is the plot's, not the building's
    if any(w in n for w in ("BOUNDARY", "COMPOUND", "OTHER PROP")) and \
            "walls" in out:
        out.remove("walls")
    # «WINDOW» says window, not wall; «DOOR FRAME» door; «COLUMN» not «COL»
    if "windows" in out and "walls" in out and "WALL" not in n:
        out.remove("walls")
    return out


def block_style(name: str, kind: str) -> str:
    """The opening type a block's name tells: SD / SLIDING → sliding,
    DOUBLE / DD → double door, FIXED / FG → fixed glass, LOUVRE…"""
    n = _upper(name)
    if re.search(r"SLID|(^|[^A-Z])S\.?D($|[^A-Z])|SDG|SLD", n):
        return "sliding"
    if kind == "door" and re.search(r"DOUBLE|(^|[^A-Z])DD($|[^A-Z])|2 ?LEAF",
                                    n):
        return "double"
    if kind == "window":
        if re.search(r"FIX|(^|[^A-Z])FG($|[^A-Z])", n):
            return "fixed"
        if re.search(r"LOUV|VENT", n):
            return "louvre"
        if re.search(r"TOP|AWN", n):
            return "top-hung"
    return "hinged" if kind == "door" else ""


def block_kind(name: str, layer: str = "") -> str | None:
    """A block's opening kind, from its name first, then its layer."""
    for src in (name, layer):
        r = by_name(src)
        if "doors" in r:
            return "door"
        if "windows" in r:
            return "window"
    return None


def roles(drawing: dict, tmin: float = 0.08, tmax: float = 0.40) -> dict:
    """{role: [layer names]} — every layer of ``drawing`` (as read, in its
    own units) given the roles its name holds; walls from the geometry
    when no name says «wall»."""
    count: dict = {}
    for s in drawing["segs"]:
        count[s[4]] = count.get(s[4], 0) + 1
    names = set(count) | {t["layer"] for t in drawing["texts"]} | \
        {lp["layer"] for lp in drawing["loops"]}
    out = {k: [] for k in ROLES}
    for n in sorted(names):
        for r in by_name(n):
            out[r].append(n)
    # blocks named DOOR / WINDOW: their layer holds them
    for i in drawing.get("inserts", ()):
        k = block_kind(i["name"])
        if k and i["layer"] not in out[k + "s"]:
            out[k + "s"].append(i["layer"])
    # texts: every layer that holds words, when none is named for them
    if not out["text"]:
        out["text"] = sorted({t["layer"] for t in drawing["texts"]})
    if not out["walls"]:
        out["walls"] = _walls_by_geometry(drawing, count, tmin, tmax)
    return out


def _walls_by_geometry(drawing, count, tmin, tmax) -> list:
    """The layer(s) whose lines pair up as walls (most wall length)."""
    from .engine import walldetect
    k = drawing["unit"]
    best = []
    for name in sorted(count, key=count.get, reverse=True)[:8]:
        if by_name(name) and set(by_name(name)) & {"doors", "windows",
                                                    "text", "plot"}:
            continue
        segs = [[s[0] * k, s[1] * k, s[2] * k, s[3] * k, 0]
                for s in drawing["segs"] if s[4] == name][:6000]
        if len(segs) < 4:
            continue
        try:
            found, _ops = walldetect.walls_from(segs, tmin, tmax)
        except Exception:  # noqa: BLE001
            continue
        import math
        length = sum(math.dist(a, b) for a, b, _t in found)
        if length > 2.0:
            best.append((length, name))
    best.sort(reverse=True)
    if not best:
        return []
    top = best[0][0]
    return [n for L, n in best if L >= 0.35 * top]


def as_patterns(names: list) -> str:
    """Layer names as the panel's comma list (exact names)."""
    return ", ".join(n.replace(",", "?").replace("[", "[[]")
                     .replace("*", "?").replace("?", "?") for n in names)
