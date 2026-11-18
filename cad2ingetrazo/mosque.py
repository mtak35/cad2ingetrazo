# SPDX-License-Identifier: GPL-3.0-or-later
"""A mosque as its perspectives show it (3.64.66).

The «Modern mosque» look (lookstyle preset «mosque», picked by itself
when a perspective is followed on a mosque's drawing — its rooms named
MAIN HALL / PRAYER HALL / MIMBER / ABLUTION…):

* the domes the plans draw — circles on a DOME layer — made at their
  size: the big one a hemisphere on a low drum, the small ones round it;
* four slim modern minarets (square shafts, screened slots, an open
  lantern) at the prayer hall's corners;
* every outside door, window and opening arched (round heads);
* the prayer hall's storey 18'-0" (a hall, not a room), when it was the
  default height;
* white walls; the boundary wall white, its front in lattice (jali)
  panels between piers.

``doc["cad_domes"]`` = {level id: [[x, y, diameter]…]} — the circles
read at the import; the domes made from them have ids «cad-…».
"""
from __future__ import annotations

import math
import re

MOSQUE_RX = re.compile(r"\bMASJID\b|\bMOSQUE\b|PRAYER\s+HALL|\bMIMBE?R\b|"
                       r"\bMIMBAR\b|\bMEHRAB\b|\bMIHRAB\b|\bMUAZZIN\b|"
                       r"\bIMAM\b|\bABLUTION\b|\bWUZU\b|\bWUDU\b|\bSEHEN\b|"
                       r"\bSAHN\b|\bMAYYAT\b", re.I)
HALL_RX = re.compile(r"MAIN\s+HALL|PRAYER\s+HALL|\bHALL\b", re.I)
DOME_LAYER = re.compile(r"DOME|GUMBAD|GUMBAZ|QUBBA|CUPOLA", re.I)
HALL_H = 5.4864                     # 18'-0"
DEFAULT_H = 3.048


def is_mosque(doc) -> bool:
    n = sum(1 for t in doc.get("texts") or []
            if MOSQUE_RX.search(str(t.get("text", ""))))
    return n >= 2 or bool(doc.get("cad_domes"))


# ---- the domes the plans draw -----------------------------------------------------
def read_domes(doc, lid, pl) -> int:
    """At the import: the circles on a dome layer (a dome drawn in plan)
    kept for the level; the cad domes made again from them."""
    cs = [[round(c["c"][0], 4), round(c["c"][1], 4), round(2 * c["r"], 3)]
          for c in pl.get("circles") or []
          if DOME_LAYER.search(str(c.get("layer", ""))) and
          0.8 <= 2 * c["r"] <= 60.0]
    keep = {}
    for c in cs:                         # (concentric circles: the biggest)
        k = (round(c[0], 1), round(c[1], 1))
        if k not in keep or c[2] > keep[k][2]:
            keep[k] = c
    cs = list(keep.values())
    cd = doc.setdefault("cad_domes", {})
    if cs:
        cd[lid] = cs
    else:
        cd.pop(lid, None)
    if cs or any(str(d.get("id", "")).startswith("cad-")
                 and d.get("level") == lid for d in doc.get("domes") or []):
        sync_domes(doc)
    return len(cs)


def sync_domes(doc) -> int:
    """The cad domes as the plans draw them (the domes made by hand
    kept): the biggest of a level a hemisphere on a drum, the others
    plain hemispheres."""
    ids = {lv["id"] for lv in doc["arch"]["levels"]}
    keep = [d for d in doc.get("domes") or []
            if not str(d.get("id", "")).startswith("cad-")]
    old = {d["id"]: d for d in doc.get("domes") or []
           if str(d.get("id", "")).startswith("cad-")}
    made = []
    for lid, cs in (doc.get("cad_domes") or {}).items():
        if lid not in ids or not cs:
            continue
        big = max(c[2] for c in cs)
        for c in cs:
            x, y, d = c
            did = f"cad-{lid}-{round(x, 1)}-{round(y, 1)}"
            main = d >= 0.75 * big and d >= 4.0
            rec = {"id": did, "level": lid, "x": x, "y": y, "d": d,
                   "kind": "hemi", "rise": 0.0,
                   "drum": round(0.12 * d, 3) if main else 0.0,
                   "finial": True, "color": "white"}
            o = old.get(did)
            if o:                         # (its finish / kind set by hand)
                rec.update({k: o[k] for k in ("kind", "rise", "drum",
                                              "finial", "color") if k in o})
            made.append(rec)
    doc["domes"] = keep + made
    return len(made)


# ---- the minarets ----------------------------------------------------------------
def hall(doc):
    """(level id, polygon) of the prayer hall: the ground floor's room
    named MAIN HALL / PRAYER HALL (else its biggest room)."""
    from shapely.geometry import Point
    from .engine import spaces
    arch = doc["arch"]
    g = next((lv for lv in arch["levels"] if lv["kind"] == "ground"), None)
    if g is None:
        return None, None
    rooms = spaces.of_level(arch, g["id"])
    if not rooms:
        return g["id"], None
    named = []
    for t in doc.get("texts") or []:
        if t.get("level") != g["id"] or not HALL_RX.search(
                str(t.get("text", ""))):
            continue
        for r in rooms:
            if r["poly"].contains(Point(t["x"], t["y"])):
                named.append(r)
    pick = max(named or rooms, key=lambda r: r["area"])
    return g["id"], pick["poly"]


def minarets(doc, b=1.5) -> int:
    """Four modern minarets at the prayer hall's corners (none made by
    hand yet): their height about 2.6 times the building's."""
    if doc.get("minarets"):
        return 0
    from . import minarets as MN
    from . import project as PJ
    lid, poly = hall(doc)
    if poly is None:
        return 0
    arch = doc["arch"]
    el = PJ.elevations(arch)
    gi = next(i for i, lv in enumerate(arch["levels"]) if lv["id"] == lid)
    top = max(el[i] + float(lv["height"]) for i, lv in
              enumerate(arch["levels"]))
    H = round(min(max(2.6 * (top - el[gi]), 24.0), 60.0), 2)
    rr = poly.minimum_rotated_rectangle
    cs = list(rr.exterior.coords)[:4]
    ang = math.degrees(math.atan2(cs[1][1] - cs[0][1], cs[1][0] - cs[0][0]))
    cx, cy = rr.centroid.x, rr.centroid.y
    for x, y in cs:                    # just outside the hall's corner
        d = math.hypot(x - cx, y - cy)
        k = (d + b * 0.35) / max(d, 1e-6)
        MN.new_minaret(doc, lid, cx + (x - cx) * k, cy + (y - cy) * k,
                       b=b, h=H, galleries=1, cupola="modern",
                       rot=ang % 90.0, color="white")
    return 4


# ---- arches, storey, boundary wall ------------------------------------------------
def arches(doc) -> int:
    """Every outside door, window and opening (0.6 m wide or more) with a
    round head."""
    from . import project as PJ
    from .lookstyle import _outer_walls
    arch = doc["arch"]
    outer = _outer_walls(arch)
    ws = {w["id"]: w for w in arch["walls"]}
    n = 0
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or w["id"] not in outer or float(o["w"]) < 0.6:
            continue
        if o.get("head") == "arch":
            continue
        o["head"] = "arch"
        o["arch"] = "semi"
        o.pop("grille", None) if o.get("grille") == "ms" else None
        try:
            PJ.fit_head(o)
        except Exception:  # noqa: BLE001
            pass
        n += 1
    return n


def hall_storey(doc) -> bool:
    lid, _p = hall(doc)
    lv = next((x for x in doc["arch"]["levels"] if x["id"] == lid), None)
    if lv is None or abs(float(lv["height"]) - DEFAULT_H) > 0.01:
        return False
    lv["height"] = HALL_H
    return True


def boundary(doc) -> None:
    st = doc["site"]
    st["wall"] = True
    st["finish"] = "white"
    st["front_finish"] = "white"
    if not st.get("front_style"):
        st["front_style"] = "cement_lattice"
    st["gate_color"] = st.get("gate_color") or "charcoal"


def apply(doc) -> dict:
    """The mosque's own elements (the look's colours and fascias are the
    kit's)."""
    rep = {}
    try:
        rep["domes"] = sync_domes(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("mosque.sync_domes")
    rep["hall_18ft"] = hall_storey(doc)
    rep["minarets"] = minarets(doc)
    rep["arched"] = arches(doc)
    boundary(doc)
    return rep
