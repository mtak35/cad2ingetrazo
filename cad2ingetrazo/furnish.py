"""Furniture and fixtures from the CAD plan — IngeTrazo library models.

Every block the plan inserts on a floor that is not a door, window, car,
column… is read for what it is — by its name (BED, WC, SOFA, CHAIR, STOVE…
in English, Spanish and the usual CAD shorthands), else by its size and
the room it stands in (a 0.4 × 0.7 m block in a bathroom is a WC, a
2.0 × 1.8 m block in a bedroom a bed) — and the IngeTrazo library model of
that kind whose size is nearest is set in its place: the block's middle,
its rotation, fitted to its footprint. They are kept as the floor's
furniture («CAD» ones made again each time; the ones placed by hand stay).

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

import math
import re

#: kind: (name pattern, [(library category, [name words, best first])])
KINDS = {
    "bed": (r"BED|CAMA|\bKING\b|QUEEN|DIVAN",
            [("Bedroom", ["double bed", "bed"])]),
    "wc": (r"\bWC\b|W\.C|TOILET|COMMODE|WATER.?CLOSET|\bEWC\b|\bIWC\b|"
           r"INODORO|\bPAN\b",
           [("Bathroom", ["toilet", "wc"])]),
    "basin": (r"BASIN|\bWHB\b|WASH|\bLAV|LAVABO|VANITY",
              [("Bathroom", ["washbasin", "basin", "sink", "vanity"])]),
    "shower": (r"SHOWER|DUCHA", [("Bathroom", ["shower"])]),
    "bathtub": (r"\bTUB|BATHTUB|BAÑERA|BANERA|JACUZZI",
                [("Bathroom", ["bathtub", "bath"])]),
    "sofa": (r"SOFA|COUCH|SETTEE|LOVESEAT", [("Living room",
                                              ["sofa", "couch"])]),
    "armchair": (r"ARM.?CHAIR|LOUNGE.?CHAIR|SILLON",
                 [("Living room", ["armchair", "chair"])]),
    "chair": (r"CHAIR|\bSTOL|SILLA|STOOL",
              [("Living room", ["dining chair", "chair"]),
               ("Kitchen", ["chair"]), ("Office", ["chair"])]),
    "dining": (r"DINING|DIN.?TABLE|TABLE|MESA|\bBORD",
               [("Living room", ["dining table", "table"]),
                ("Kitchen", ["table"])]),
    "desk": (r"DESK|WORK.?STATION|STUDY|ESCRITORIO",
             [("Office", ["desk", "table"])]),
    "wardrobe": (r"WARD|\bROBE|CLOSET|CUPBOARD|ALMIRAH|ARMARIO",
                 [("Bedroom", ["wardrobe", "closet", "cabinet"])]),
    "ksink": (r"K.?SINK|KITCHEN.?SINK|\bSINK|FREGADERO",
              [("Kitchen", ["sink"])]),
    "stove": (r"STOVE|\bHOB\b|COOKER|COOK|BURNER|COCINA|\bRANGE",
              [("Kitchen", ["stove", "cooker", "hob", "oven"])]),
    "fridge": (r"FRIDGE|REFRIG|FRIGO|NEVERA|^REF\b|^REF\.",
               [("Kitchen", ["fridge", "refrigerator"])]),
    "tv": (r"\bTV\b|TELEVISION|\bLED\b", [("Living room",
                                          ["tv", "television"])]),
    "plant": (r"PLANT|PLTS|\bPOT\b|FLOWER|MACETA",
              [("Living room", ["plant"]), ("Exterior", ["plant"])]),
    "tree": (r"TREE|ARBOL|PALM", [("Exterior", ["tree", "palm"])]),
}
#: names that are not furniture (handled elsewhere)
SKIP = r"DOOR|WINDOW|WIN\b|CAR\b|CAR\d|VEHIC|BIKE|MOTOR|NORTH|ARROW|GRID|" \
       r"COL\b|COLUMN|LIFT|STAIR|LEVEL|LEV\b|SECTION|TITLE|LOGO|SCALE"

#: room words → the room's use
ROOMS = (("bath", r"BATH|TOILET|W\.?C|WASH|LAV|POWDER"),
         ("bed", r"BED|MASTER|GUEST|CHILD|KID|SERVANT"),
         ("kitchen", r"KITCHEN|PANTRY|COOK"),
         ("dining", r"DINING"),
         ("living", r"LIVING|LOUNGE|DRAWING|SITTING|FAMILY|T\.?V"),
         ("office", r"OFFICE|STUDY|LIBRARY"),
         ("dress", r"DRESS|WARDROBE|CLOSET"))


def _use(room_name: str) -> str:
    nm = str(room_name or "").upper()
    for k, pat in ROOMS:
        if re.search(pat, nm):
            return k
    return ""


def _in(v, lo, hi) -> bool:
    return lo <= v <= hi


def classify(name: str, layer: str, L: float, W: float, use: str):
    """The kind of furniture a block is, or None. ``L`` ≥ ``W`` its sides
    (m), ``use`` the room's use."""
    s = f"{name} {layer}".upper()
    if re.search(SKIP, str(name).upper()) or W < 0.2:
        return None
    if re.search(r"SEAT", str(name).upper()):      # a WC seat / a seat
        return "wc" if use == "bath" else "armchair"
    for k, (pat, _lib) in KINDS.items():
        if re.search(pat, str(name).upper()):
            return k
    for k, (pat, _lib) in KINDS.items():         # the layer's name next
        if k not in ("tv", "plant") and re.search(pat, str(layer).upper()):
            if _fits(k, L, W):
                return k
    if re.search(r"GREEN|PLANT|LANDSC|GARDEN", str(layer).upper()) and \
            _in(L, 0.3, 3.0):
        return "plant"
    # by its size and the room it stands in
    if use == "bath":
        if _in(L, 0.55, 0.9) and _in(W, 0.33, 0.58):
            return "wc"
        if _in(L, 1.35, 1.95) and _in(W, 0.6, 0.98):
            return "bathtub"
        if _in(L, 0.75, 1.25) and _in(W, 0.75, 1.25) and L / W < 1.4:
            return "shower"
        if _in(L, 0.35, 0.8) and _in(W, 0.28, 0.62):
            return "basin"
    if use in ("bed", "dress"):
        if _in(L, 1.85, 3.3) and _in(W, 0.85, 2.6):   # (with side tables)
            return "bed"
        if _in(L, 0.9, 3.2) and _in(W, 0.45, 0.75):
            return "wardrobe"
    if use == "living":
        if _in(L, 1.4, 3.4) and _in(W, 0.7, 1.15):
            return "sofa"
        if _in(L, 0.6, 1.15) and _in(W, 0.6, 1.15):
            return "armchair"
    if use in ("dining", "living", "kitchen"):
        if _in(L, 1.0, 3.2) and _in(W, 0.7, 1.4):
            return "dining"
    if use == "kitchen":
        if _in(L, 0.6, 1.25) and _in(W, 0.4, 0.62):
            return "ksink"
        if _in(L, 0.55, 0.95) and _in(W, 0.55, 0.95):
            return "fridge"
    if use == "office" and _in(L, 1.0, 2.2) and _in(W, 0.5, 1.0):
        return "desk"
    if _in(L, 0.38, 0.66) and _in(W, 0.36, 0.66):
        return "chair"
    del s
    return None


def _fits(kind, L, W) -> bool:
    lim = {"bed": (1.6, 2.5, 0.8, 2.2), "wc": (0.45, 0.95, 0.3, 0.6),
           "basin": (0.3, 1.2, 0.25, 0.7), "shower": (0.7, 1.5, 0.7, 1.5),
           "bathtub": (1.2, 2.0, 0.55, 1.0), "sofa": (1.2, 3.6, 0.6, 2.2),
           "armchair": (0.5, 1.2, 0.5, 1.2), "chair": (0.3, 0.8, 0.3, 0.8),
           "dining": (0.6, 3.5, 0.6, 1.6), "desk": (0.8, 2.4, 0.4, 1.2),
           "wardrobe": (0.6, 3.5, 0.4, 0.9), "ksink": (0.4, 1.4, 0.35, 0.7),
           "stove": (0.4, 1.0, 0.4, 0.8), "fridge": (0.5, 1.0, 0.5, 1.0),
           "tree": (0.3, 12.0, 0.3, 12.0)}.get(kind)
    return lim is None or (_in(L, lim[0], lim[1]) and _in(W, lim[2], lim[3]))


def _dims(e):
    """(along x, along y) of a library entry, m — or None."""
    cm = ((e.get("entry") or {}).get("cm")) or ()
    try:
        if len(cm) >= 2:
            return float(cm[0]) / 100.0, float(cm[1]) / 100.0
    except (TypeError, ValueError):
        pass
    return None


def pick(kind, L, W, entries, cache=None):
    """The library entry for ``kind`` sized nearest to L × W."""
    key = (kind, round(L, 1), round(W, 1))
    if cache is not None and key in cache:
        return cache[key]
    best = None
    for cat, words in KINDS[kind][1]:
        for e in entries:
            if e.get("cat") != cat:
                continue
            nm = str(e.get("name", "")).lower()
            rank = next((i for i, w in enumerate(words) if w in nm), None)
            if rank is None:
                continue
            d = _dims(e)
            if kind == "bed" and d:           # a double bed for a wide one
                wide = min(d) > 1.2
                if wide != (W > 1.2):
                    rank += 1
            if d:
                a, b = max(d), min(d)
                err = abs(a - L) + abs(b - W)
            else:
                err = 2.0
            score = (rank, err)
            if best is None or score < best[0]:
                best = (score, e)
    hit = best[1] if best else None
    if cache is not None:
        cache[key] = hit
    return hit


def cad_blocks(doc, lid) -> list:
    """The level's CAD blocks, placed in the model (``cadread.place``)."""
    from . import cadread
    how = (doc.get("imports") or {}).get(lid)
    if not isinstance(how, dict) or not how.get("file"):
        return []
    raw = cadread.read(how["file"], how.get("unit"))
    drawing = cadread.crop(raw, how.get("region"))
    base = cadread.base_point(drawing, how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    pl = cadread.place(drawing, base, (how.get("ix", 0.0),
                                       how.get("iy", 0.0)),
                       how.get("rot", 0.0))
    return list(pl.get("inserts", ()))


def furnish(doc, lids=None, entries=None) -> dict:
    """The furniture / fixtures of the CAD blocks on levels ``lids`` (all
    imported) set as library models: the CAD-made ones of those levels
    made again, the hand-placed kept. {level: {kind: n}}."""
    from shapely.geometry import Point

    from . import detect
    from .engine import spaces
    if entries is None:
        from . import library as LB
        entries = LB.list_entries()
    arch = doc["arch"]
    out = {}
    cache = {}
    names = {lv["id"] for lv in arch["levels"]}
    for lid in (lids or list((doc.get("imports") or {}).keys())):
        if lid not in names:
            continue
        try:
            blocks = cad_blocks(doc, lid)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("furnish.cad_blocks")
            continue
        rooms = []
        try:
            rooms = spaces.of_level(arch, lid)
        except Exception:  # noqa: BLE001
            pass
        doc["furniture"] = [f for f in doc.get("furniture") or []
                            if not (f.get("cad") and f["level"] == lid)]
        got = {}
        seen = []
        for ins in blocks:
            if detect.block_kind(str(ins.get("name", "")),
                                 str(ins.get("layer", ""))):
                continue                         # a door / window
            cs = ins.get("corners") or []
            if len(cs) < 4:
                continue
            xs = [c[0] for c in cs]
            ys = [c[1] for c in cs]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            dx, dy = max(xs) - min(xs), max(ys) - min(ys)
            if max(dx, dy) < 0.25 or max(dx, dy) > 14.0:
                continue
            rot = float(ins.get("rot", 0.0) or 0.0)
            # the block's own sides (its box is the world box): a block
            # turned a quarter shows them swapped
            q = round((rot % 180.0) / 90.0) % 2
            lx, ly = (dy, dx) if q == 1 else (dx, dy)
            L, W = max(lx, ly), min(lx, ly)
            room = None
            P_ = Point(cx, cy)
            for r in rooms:
                try:
                    if r["poly"].contains(P_):
                        room = r
                        break
                except Exception:  # noqa: BLE001
                    continue
            use = _use(room["name"]) if room else ""
            kind = classify(str(ins.get("name", "")),
                            str(ins.get("layer", "")), L, W, use)
            if kind is None or (kind == "tree" and room is not None):
                continue
            if any(math.dist((cx, cy), s) < 0.15 for s in seen):
                continue                       # the same block twice
            e = pick(kind, L, W, entries, cache)
            if e is None:
                continue
            seen.append((cx, cy))
            d = _dims(e)
            turn = rot
            fit = None
            if d:                   # the model's long side along the block's
                mx, my = d
                if (mx >= my) != (lx >= ly):
                    turn += 90.0
                    fit = [ly, lx]
                else:
                    fit = [lx, ly]
            rec = {"id": __import__("uuid").uuid4().hex[:8], "level": lid,
                   "key": e["key"], "name": e["name"], "x": round(cx, 4),
                   "y": round(cy, 4), "rot": round(turn % 360.0, 3),
                   "cad": True, "kind": kind,
                   **({"room": room["rec"]["id"]}
                      if room and room.get("rec") else {}),
                   **({"entry": e["entry"]} if e.get("entry") else {}),
                   **({"fit": [round(fit[0], 4), round(fit[1], 4)]}
                      if fit and kind not in ("tree", "plant", "chair")
                      else {})}
            doc["furniture"].append(rec)
            got[kind] = got.get(kind, 0) + 1
        out[lid] = got
    return out


__all__ = ["furnish", "classify", "pick", "cad_blocks", "KINDS"]
