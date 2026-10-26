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
            [("Bedroom", ["bed"])]),
    "wc": (r"\bWC\b|W\.C|TOILET|COMMODE|WATER.?CLOSET|\bEWC\b|\bIWC\b|"
           r"INODORO|\bPAN\b",
           [("Bathroom", ["toilet unit", "hanged toilet", "toilet"])]),
    "basin": (r"BASIN|\bWHB\b|\bWB\b|WASH|\bLAV|LAVABO|VANITY",
              [("Bathroom", ["vanity", "washbasin with cabinet",
                             "washbasin", "basin", "small lavatory"])]),
    "shower": (r"SHOWER|DUCHA", [("Bathroom", ["shower cabin", "shower stall",
                                               "shower cubicle"])]),
    "bathtub": (r"\bTUB|BATHTUB|BAÑERA|BANERA|JACUZZI",
                [("Bathroom", ["bath", "bathtub"])]),
    "sofa": (r"SOFA|COUCH|SETTEE|LOVESEAT", [("Living room",
                                              ["sofa", "couch"])]),
    "armchair": (r"ARM.?CHAIR|LOUNGE.?CHAIR|SILLON",
                 [("Living room", ["armchair"])]),
    "chair": (r"CHAIR|\bSTOL|SILLA|STOOL",
              [("Living room", ["chair"]), ("Kitchen", ["chair"]),
               ("Office", ["chair"])]),
    "dining": (r"DINING|DIN.?TABLE|TABLE|MESA|\bBORD",
               [("Living room", ["table", "rectangular table",
                                 "glass table"]),
                ("Kitchen", ["table"])]),
    "coffee": (r"COFFEE|CENTRE.?TABLE|CENTER.?TABLE",
               [("Living room", ["coffee table"])]),
    "desk": (r"DESK|WORK.?STATION|STUDY|ESCRITORIO",
             [("Office", ["desk"])]),
    "sidetable": (r"BEDSIDE|BED.?SIDE|SIDE.?TABLE|NIGHT.?STAND|^B[-. ]?S$|"
                  r"NIGHT.?TABLE|MESILLA",
                  [("Bedroom", ["bedside table"])]),
    "wardrobe": (r"WARD|\bROBE|CLOSET|CUPBOARD|ALMIRAH|ARMARIO",
                 [("Bedroom", ["wardrobe"])]),
    "ksink": (r"K.?SINK|KITCHEN.?SINK|\bSINK|FREGADERO",
              [("Kitchen", ["sink"])]),
    "stove": (r"STOVE|\bHOB\b|COOKER|COOK|BURNER|COCINA|\bRANGE|OVEN",
              [("Kitchen", ["cooker", "stove"])]),
    "fridge": (r"FRIDGE|REFRIG|FRIGO|NEVERA|^REF\b|^REF\.",
               [("Kitchen", ["fridge", "refrigerator"])]),
    "cabinet": (r"\bCABINET|COUNTER|\bBASE.?UNIT",
                [("Kitchen", ["lower cabinet", "wood lower cabinet"])]),
    "tv": (r"\bTV\b|TELEVISION|\bLED\b", [("Living room",
                                             ["tv", "wall flat tv"])]),
    "plant": (r"PLANT|PLTS|\bPOT\b|FLOWER|MACETA",
              [("Living room", ["plant", "decorative plant"]),
               ("Exterior", ["plant"])]),
    "tree": (r"TREE|ARBOL|PALM", [("Exterior", ["tree", "palm"])]),
}
#: words that make a library model the wrong one for a kind
NOT_WORDS = {
    "bed": ("baby", "child", "bunk", "loft", "hospital", "sofa", "air",
            "crib", "mezzanine", "captain", "trundle", "day", "side",
            "bedside", "iron", "futon"),
    "wc": ("turkish", "japanese", "brush", "paper", "potty", "grab",
           "urinal"),
    "basin": ("corner", "stone", "ergonomic", "mixer", "double", "hand"),
    "shower": ("door", "curtain", "head", "chair", "armchair", "mixer",
               "tap"),
    "bathtub": ("mat", "mixer", "towel", "island", "jet", "l shape"),
    "sofa": ("bed", "corner", "winchester", "futon"),
    "armchair": ("ottoman", "shower", "winchester"),
    "chair": ("arm", "child", "bar", "high", "shower", "rocking", "folding",
              "cushion", "office", "ryokan", "lattice", "oak"),
    "dining": ("coffee", "bar", "child", "small", "half", "drop", "folding",
               "waitress", "wheels", "trestle", "gnome", "couch", "round",
               "marble", "technical", "planters"),
    "coffee": ("square",),
    "wardrobe": ("angle", "corner", "blue"),
    "sidetable": ("blue",),
    "ksink": ("cabinet",),
    "stove": ("propane", "large", "induction", "deep fryer"),
    "fridge": ("chest",),
    "cabinet": ("corner", "upper", "small", "glass", "microwave"),
    "plant": ("bonsai", "christmas"),
}
#: names that are not furniture (handled elsewhere)
SKIP = r"DOOR|WINDOW|WIN\b|CAR\b|CAR\d|VEHIC|BIKE|MOTOR|NORTH|ARROW|GRID|" \
       r"COL\b|COL-|COLUMN|LIFT|STAIR|LEVEL|LEV\b|SECTION|SEC-|TITLE|LOGO|" \
       r"SCALE|PIPE|STACK|AC.?INT|AC.?OUTER|SPLIT"
#: the layers furniture and fixtures stand on (a block on another layer
#: is read only when its NAME says what it is)
FURN_LAYER = r"FURN|FIX|SANIT|PLUMB|TOILET|BATH|KITCH|KITC|SYMB|GREEN|TREE|" \
             r"PLANT|LANDSC|INTERIOR|EQUIP|^0$|MOBIL|MUEBLE"

#: room words → the room's use
ROOMS = (("bath", r"BATH|TOILET|W\.?C|WASH|LAV|POWDER|P\.?\s?ROOM"),
         ("bed", r"BED|MASTER|GUEST|CHILD|KID|SERVANT|MAID"),
         ("kitchen", r"KITCHEN|PANTRY|COOK|KITCHENETTE"),
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
    if re.search(SKIP, str(name).upper()) or W < 0.2 or \
            re.search(SKIP, str(layer).upper()):
        return None
    named = any(re.search(pat, str(name).upper())
                for pat, _l in KINDS.values())
    if not named and not re.search(FURN_LAYER, str(layer).upper()):
        return None                   # a window's, a column's… block
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
        if _in(L, 0.55, 1.0) and _in(W, 0.33, 0.6) and L / W >= 1.35:
            return "wc"               # (with its cistern / its mat)
        if _in(L, 1.35, 1.95) and _in(W, 0.6, 0.98):
            return "bathtub"
        if _in(L, 0.75, 1.25) and _in(W, 0.75, 1.25) and L / W < 1.4:
            return "shower"
        if _in(L, 0.35, 0.95) and _in(W, 0.28, 0.75):
            return "basin"
    if use in ("bed", "dress"):
        if _in(L, 1.85, 3.3) and _in(W, 0.85, 2.6):   # (with side tables)
            return "bed"
        if use == "bed" and _in(L, 0.3, 0.7) and _in(W, 0.3, 0.7) and \
                L / W < 1.45:
            return "sidetable"        # a small square by the bed
        if _in(L, 0.9, 3.2) and _in(W, 0.45, 0.75):
            return "wardrobe"
    if use not in ("bath", "kitchen", "dining", "living", "office") and \
            _in(L, 1.9, 3.0) and _in(W, 1.35, 2.6) and L / W < 1.6:
        return "bed"                  # a double bed, whatever the room's name
    if use == "living":
        if _in(L, 1.4, 3.4) and _in(W, 0.7, 1.15):
            return "sofa"
        if _in(L, 0.6, 1.15) and _in(W, 0.6, 1.15):
            return "armchair"
    if use in ("dining", "living", "kitchen"):
        if _in(L, 1.0, 3.2) and _in(W, 0.7, 1.4):
            return "dining"
    if use == "kitchen":
        if _in(L, 0.7, 1.4) and _in(W, 0.4, 0.66) and L / W >= 1.4:
            return "ksink"
    if use == "office" and _in(L, 1.0, 2.2) and _in(W, 0.5, 1.0):
        return "desk"
    if _in(L, 0.38, 0.66) and _in(W, 0.36, 0.66):
        return "chair"
    del s
    return None


def _fits(kind, L, W) -> bool:
    lim = {"bed": (1.6, 2.5, 0.8, 2.2), "wc": (0.45, 1.0, 0.3, 0.6),
           "basin": (0.3, 1.2, 0.25, 0.7), "shower": (0.7, 1.5, 0.7, 1.5),
           "bathtub": (1.2, 2.0, 0.55, 1.0), "sofa": (1.2, 3.6, 0.6, 2.2),
           "armchair": (0.5, 1.2, 0.5, 1.2), "chair": (0.3, 0.8, 0.3, 0.8),
           "dining": (0.6, 3.5, 0.6, 1.6), "desk": (0.8, 2.4, 0.4, 1.2),
           "wardrobe": (0.6, 3.5, 0.4, 0.9), "sidetable": (0.3, 0.75, 0.3, 0.75), "ksink": (0.4, 1.4, 0.35, 0.7),
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
            if any(x in nm for x in NOT_WORDS.get(kind, ())):
                continue
            rank = next((i for i, w in enumerate(words) if w in nm), None)
            if rank is None:
                continue
            if nm.strip() == words[rank]:     # the plain name: best
                rank -= 0.5
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


def cad_plan(doc, lid):
    """The level's CAD plan placed in the model (``cadread.place``), or
    None."""
    from . import cadread
    how = (doc.get("imports") or {}).get(lid)
    if not isinstance(how, dict) or not how.get("file"):
        return None
    raw = cadread.read(how["file"], how.get("unit"))
    drawing = cadread.crop(raw, how.get("region"))
    base = cadread.base_point(drawing, how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    return cadread.place(drawing, base, (how.get("ix", 0.0),
                                         how.get("iy", 0.0)),
                         how.get("rot", 0.0))


def oval_basins(pl, rooms) -> list:
    """Washbasins drawn loose (not a block): an oval / round closed line
    on a fixture layer inside a bathroom, 14"–30" across — [(x, y, L, W,
    room)], the outer ring of each."""
    from shapely.geometry import Polygon
    out = []
    if pl is None:
        return out
    for lp in pl.get("loops") or ():
        if not re.search(FURN_LAYER, str(lp["layer"]).upper()) or \
                len(lp["pts"]) < 12:
            continue
        try:
            g = Polygon(lp["pts"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if g.is_empty or g.geom_type != "Polygon":
            continue
        m = g.minimum_rotated_rectangle
        cs = list(m.exterior.coords)[:-1]
        a_, b_ = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        L, W = max(a_, b_), min(a_, b_)
        if not (_in(L, 0.35, 0.8) and _in(W, 0.22, 0.65)):
            continue
        if not 0.68 <= g.area / max(m.area, 1e-9) <= 0.84:
            continue                       # an ellipse fills π/4 of its box
        c = g.centroid
        room = next((r for r in rooms if r["poly"].contains(c)), None)
        if room is None or _use(room["name"]) != "bath":
            continue
        out.append((c.x, c.y, L, W, room))
    out.sort(key=lambda q: -q[2])
    keep = []
    for q in out:                          # the rings of one basin: one
        if all(math.dist(q[:2], k[:2]) > 0.2 for k in keep):
            keep.append(q)
    return keep


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


#: kinds that stand with their back to a wall (the library's models face
#: −Y: their back is their +Y side)
WALL_KINDS = {"bed", "sidetable", "wc", "basin", "sofa", "armchair", "wardrobe", "tv",
              "cabinet", "fridge", "stove", "ksink", "desk", "shower",
              "bathtub"}


def back_to(dx, dy):
    """The turn (°) that puts a model's back (+Y) toward the world
    direction (dx, dy)."""
    return (math.degrees(math.atan2(dy, dx)) - 90.0) % 360.0


def face_wall(poly, cx, cy, ex, ey, reach=0.75):
    """For an item centred (cx, cy), ``ex`` × ``ey`` across in the world, in
    the room ``poly``: (turn °, fit [along the wall, across it]) with its
    back to the nearest wall — or None when no wall is near."""
    from shapely.geometry import LineString, Point, box
    foot = box(cx - ex / 2, cy - ey / 2, cx + ex / 2, cy + ey / 2)
    pts = list(poly.exterior.coords)
    best = None
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        if L < 0.3:
            continue
        d = LineString([a, b]).distance(foot)
        if d > reach:
            continue
        if best is None or d < best[0]:
            best = (d, a, b, L)
    if best is None:
        return None
    _d, a, b, L = best
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])
    # n toward the wall: from the item to the edge
    q = LineString([a, b]).interpolate(LineString([a, b]).project(
        Point(cx, cy)))
    if (q.x - cx) * n[0] + (q.y - cy) * n[1] < 0:
        n = (-n[0], -n[1])
    along = abs(u[0]) * ex + abs(u[1]) * ey
    across = abs(u[1]) * ex + abs(u[0]) * ey
    return back_to(*n), [along, across]


#: the bathroom's fixtures (placed even with the CAD furniture off)
BATH_KINDS = ("wc", "basin", "shower", "bathtub")


def furnish(doc, lids=None, entries=None, only=None) -> dict:
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
                            if not (f.get("cad") and f["level"] == lid
                                    and f.get("src") != "fitout"
                                    and (only is None
                                         or f.get("kind") in only))]
        got = {}
        seen = []
        near = None                      # the floor's reach (its walls)
        try:
            from shapely.geometry import MultiPoint
            wp_ = [tuple(p_) for w_ in arch["walls"] if w_["level"] == lid
                   and "a" in w_ for p_ in (w_["a"], w_["b"])]
            if len(wp_) >= 3:
                near = MultiPoint(wp_).convex_hull.buffer(3.0)
        except Exception:  # noqa: BLE001
            near = None
        fix_rooms = set()                # rooms holding a sanitary block
        for ins in blocks:
            if re.search(r"FIX|SANIT|PLUMB|TOILET|\bWC\b|\bWB\b|BASIN",
                         f"{ins.get('name', '')} {ins.get('layer', '')}",
                         re.I):
                cs_ = ins.get("corners") or []
                if len(cs_) < 4:
                    continue
                pc_ = Point(sum(c[0] for c in cs_) / 4,
                            sum(c[1] for c in cs_) / 4)
                for r in rooms:
                    if r["poly"].contains(pc_):
                        fix_rooms.add(id(r))
                        break
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
            if near is not None and not near.contains(Point(cx, cy)):
                continue                 # far from the floor's walls
            rot = float(ins.get("rot", 0.0) or 0.0)
            # the block's own sides (its box is the world box): a block
            # turned a quarter shows them swapped
            q = round((rot % 180.0) / 90.0) % 2
            lx, ly = (dy, dx) if q == 1 else (dx, dy)
            if ins.get("ldim"):          # read in the block's own axes
                lx, ly = float(ins["ldim"][0]), float(ins["ldim"][1])
                if ins.get("lc"):
                    cx, cy = float(ins["lc"][0]), float(ins["lc"][1])
                a_ = math.radians(rot)   # its footprint in the world
                dx = abs(math.cos(a_)) * lx + abs(math.sin(a_)) * ly
                dy = abs(math.sin(a_)) * lx + abs(math.cos(a_)) * ly
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
            if room is not None and not use and \
                    str(room["name"]).startswith("Room ") and \
                    id(room) in fix_rooms:
                use = "bath"             # an unnamed room with its fixtures
            kind = classify(str(ins.get("name", "")),
                            str(ins.get("layer", "")), L, W, use)
            if kind is None or (kind == "tree" and room is not None):
                continue
            if only is not None and kind not in only:
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
            if kind in WALL_KINDS and room is not None:
                fw = face_wall(room["poly"], cx, cy, dx, dy)
                if fw is not None:       # its back to the wall, facing in
                    turn, fit = fw
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
        try:                 # a small square by a bed: its bedside table
            beds = [f for f in doc["furniture"] if f["level"] == lid
                    and f.get("kind") == "bed" and f.get("cad")]
            st_e = pick("sidetable", 0.45, 0.45, entries, cache)
            for f in doc["furniture"]:
                if f["level"] != lid or f.get("kind") != "chair" or \
                        not f.get("cad") or st_e is None:
                    continue
                if any(math.dist((f["x"], f["y"]), (b["x"], b["y"])) < 1.6
                       for b in beds):
                    f.update(kind="sidetable", key=st_e["key"],
                             name=st_e["name"])
                    if st_e.get("entry"):
                        f["entry"] = st_e["entry"]
                    got["chair"] = got.get("chair", 1) - 1
                    got["sidetable"] = got.get("sidetable", 0) + 1
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("furnish.bedside")
        if only is None or "basin" in only:
            try:             # basins drawn as an oval, not a block
                pl_ = cad_plan(doc, lid)
                for bx, by, bl, bw, room in oval_basins(pl_, rooms):
                    if any(math.dist((bx, by), s_) < 0.35 for s_ in seen):
                        continue
                    e = pick("basin", bl, bw, entries, cache)
                    if e is None:
                        continue
                    fw = face_wall(room["poly"], bx, by, bl, bw, reach=0.6)
                    rot = fw[0] if fw else 0.0
                    rec = _rec(doc, lid, e, "basin", bx, by, rot, room)
                    rec["oval"] = True
                    seen.append((bx, by))
                    got["basin"] = got.get("basin", 0) + 1
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("furnish.oval_basins")
        if only is not None:
            out[lid] = got
            continue
        try:                 # kitchen counters along the sink and hob
            for k_, n_ in kitchen_runs(doc, lid, rooms, entries,
                                       cache).items():
                got[k_] = got.get(k_, 0) + n_
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("furnish.kitchen_runs")
        if doc["settings"].get("room_furniture", True):
            try:             # rooms the plan leaves empty: furnished
                for k_, n_ in room_sets(doc, lid, rooms, entries,
                                        cache).items():
                    got[k_] = got.get(k_, 0) + n_
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("furnish.room_sets")
        out[lid] = got
    return out


def _rec(doc, lid, e, kind, x, y, rot, room=None, fit=None, auto=False):
    import uuid
    r = {"id": uuid.uuid4().hex[:8], "level": lid, "key": e["key"],
         "name": e["name"], "x": round(x, 4), "y": round(y, 4),
         "rot": round(rot % 360.0, 3), "cad": True, "kind": kind}
    if auto:
        r["auto"] = True
    if room and room.get("rec"):
        r["room"] = room["rec"]["id"]
    if e.get("entry"):
        r["entry"] = e["entry"]
    if fit:
        r["fit"] = [round(fit[0], 4), round(fit[1], 4)]
    doc["furniture"].append(r)
    return r


def _sides(poly):
    """The room's straight sides, long ones first: [(a, b)]."""
    pts = list(poly.exterior.coords)[:-1]
    out = []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        if math.dist(a, b) >= 0.6:
            out.append((a, b))
    out.sort(key=lambda s: -math.dist(*s))
    return out


def _doors(doc, lid):
    """The middles of the level's doors and openings (x, y)."""
    from .engine import walls as W
    arch = doc["arch"]
    byid = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    out = []
    for o in arch["openings"]:
        w = byid.get(o.get("wall"))
        if w is None or w.get("kind", "line") != "line" or "a" not in w:
            continue
        if o.get("kind") not in ("door", "void") and \
                float(o.get("sill", 0.0) or 0.0) > 0.3:
            continue
        try:
            sg = W.centre(w)
            out.append((sg.p0[0] + sg.u[0] * o["pos"],
                        sg.p0[1] + sg.u[1] * o["pos"], float(o["w"])))
        except Exception:  # noqa: BLE001
            continue
    return out


def _against(poly, length, depth, doors, taken=(), along=True):
    """A place for an item ``length`` × ``depth`` with its back to a side
    of the room no door opens on: (centre, angle of the side °, inward
    normal) or None. ``along``: its length along the side (else across
    it, a bed)."""
    from shapely.geometry import Point
    from shapely.geometry import Polygon as _P
    c = poly.centroid
    best = None
    for a, b in _sides(poly):
        L = math.dist(a, b)
        need = length if along else depth
        if L < need + 0.2:
            continue
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-u[1], u[0])
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if (c.x - m[0]) * n[0] + (c.y - m[1]) * n[1] < 0:
            n = (-n[0], -n[1])
        # a door on this side, near where the item goes: not here
        blocked = 0.0
        for dx, dy, dw in doors:
            t = (dx - a[0]) * u[0] + (dy - a[1]) * u[1]
            off = abs((dx - a[0]) * n[0] + (dy - a[1]) * n[1])
            if -0.2 <= t <= L + 0.2 and off < 0.45:
                blocked += dw
        if any(abs(math.dist(m, q)) < 0.4 for q in taken):
            continue
        dep = depth if along else length
        cen = (m[0] + n[0] * (dep / 2 + 0.03), m[1] + n[1] * (dep / 2 + 0.03))
        hl, hd = (length / 2, dep / 2) if along else (depth / 2, dep / 2)
        foot = _P([(cen[0] + u[0] * sa * hl + n[0] * sb * hd,
                    cen[1] + u[1] * sa * hl + n[1] * sb * hd)
                   for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        if not poly.buffer(0.05).contains(foot):
            continue
        # clear of the doors' swing
        if any(Point(dx, dy).buffer(dw * 0.9).intersects(foot)
               for dx, dy, dw in doors):
            continue
        score = (blocked > 0, -L)
        if best is None or score < best[0]:
            best = (score, (cen, math.degrees(math.atan2(u[1], u[0])), n, m))
    return best[1] if best else None


def _model_turn(e, along_len_is_x=True):
    """0 when the model's long side runs along its x (else 90)."""
    d = _dims(e)
    if not d:
        return 0.0
    return 0.0 if (d[0] >= d[1]) == along_len_is_x else 90.0


def room_sets(doc, lid, rooms, entries, cache) -> dict:
    """The rooms the plan leaves without their furniture: a bedroom its
    bed (and a wardrobe), a living / drawing room its sofa and coffee
    table, a dining room its table and chairs — set against the walls no
    door opens on, clear of the doors."""
    from shapely.geometry import Point
    got = {}
    doors = _doors(doc, lid)
    mine = [f for f in doc.get("furniture") or [] if f["level"] == lid]
    for r in rooms:
        use = _use(r["name"])
        poly = r["poly"]
        if use not in ("bed", "living", "dining") or r["area"] < 5.0:
            continue
        here = [f for f in mine if poly.contains(Point(f["x"], f["y"]))]
        kinds = {f.get("kind") for f in here}
        taken = [(f["x"], f["y"]) for f in here]
        mrr = poly.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)[:-1]
        short = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
        if use == "bed" and "bed" not in kinds:
            W = 1.6 if short >= 3.0 else 1.0
            e = pick("bed", 2.0, W, entries, cache)
            if e is not None:
                d = _dims(e) or (W, 2.0)
                bw, bl = min(d), max(d)
                spot = _against(poly, bl, bw, doors, taken, along=False)
                if spot is not None:
                    cen, ang, n, _m = spot
                    # its head (back) to the wall: facing the room
                    rot = back_to(-n[0], -n[1])
                    _rec(doc, lid, e, "bed", cen[0], cen[1], rot, r,
                         auto=True)
                    taken.append(cen)
                    got["bed"] = got.get("bed", 0) + 1
            if "wardrobe" not in kinds and r["area"] >= 9.0:
                e = pick("wardrobe", 1.8, 0.6, entries, cache)
                if e is not None:
                    d = _dims(e) or (1.8, 0.6)
                    spot = _against(poly, max(d), min(d), doors, taken)
                    if spot is not None:
                        cen, ang, n, _m = spot
                        _rec(doc, lid, e, "wardrobe", cen[0], cen[1],
                             back_to(-n[0], -n[1]), r, auto=True)
                        taken.append(cen)
                        got["wardrobe"] = got.get("wardrobe", 0) + 1
        if use == "living" and "sofa" not in kinds:
            e = pick("sofa", 2.2, 0.85, entries, cache)
            if e is not None:
                d = _dims(e) or (2.2, 0.85)
                spot = _against(poly, max(d), min(d), doors, taken)
                if spot is not None:
                    cen, ang, n, _m = spot
                    _rec(doc, lid, e, "sofa", cen[0], cen[1],
                         back_to(-n[0], -n[1]), r, auto=True)
                    taken.append(cen)
                    got["sofa"] = got.get("sofa", 0) + 1
                    t = pick("coffee", 1.1, 0.6, entries, cache)
                    if t is not None:
                        dt = _dims(t) or (1.1, 0.6)
                        off = min(d) / 2 + 0.45 + min(dt) / 2
                        q = (cen[0] + n[0] * off, cen[1] + n[1] * off)
                        if poly.contains(Point(q)):
                            _rec(doc, lid, t, "coffee", q[0], q[1],
                                 ang + _model_turn(t), r, auto=True)
                            got["coffee"] = got.get("coffee", 0) + 1
        if use == "dining" and "dining" not in kinds:
            e = pick("dining", 1.6, 0.9, entries, cache)
            if e is not None:
                d = _dims(e) or (1.6, 0.9)
                c = poly.representative_point()
                a, b = cs[0], cs[1]
                if math.dist(cs[1], cs[2]) > math.dist(a, b):
                    a, b = cs[1], cs[2]
                ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                _rec(doc, lid, e, "dining", c.x, c.y,
                     ang + _model_turn(e), r, auto=True)
                got["dining"] = got.get("dining", 0) + 1
                ch = pick("chair", 0.5, 0.5, entries, cache)
                if ch is not None and "chair" not in kinds:
                    u = (math.cos(math.radians(ang)),
                         math.sin(math.radians(ang)))
                    n = (-u[1], u[0])
                    L, Wd = max(d), min(d)
                    for side in (1, -1):
                        for t in (-L / 4, L / 4):
                            q = (c.x + u[0] * t + n[0] * side * (Wd / 2 + 0.3),
                                 c.y + u[1] * t + n[1] * side * (Wd / 2 + 0.3))
                            if poly.contains(Point(q)):
                                _rec(doc, lid, ch, "chair", q[0], q[1],
                                     ang + (0 if side > 0 else 180), r,
                                     auto=True)
                                got["chair"] = got.get("chair", 0) + 1
    return got


def kitchen_runs(doc, lid, rooms, entries, cache) -> dict:
    """Base cabinets along the kitchen walls the sink and the hob stand
    on: the run along that wall inside the room, a cabinet every ~60 cm
    where nothing else stands, the counter's depth."""
    from shapely.geometry import Point
    got = {}
    mine = [f for f in doc.get("furniture") or [] if f["level"] == lid]
    cab = pick("cabinet", 0.6, 0.6, entries, cache)
    if cab is None:
        return got
    for r in rooms:
        if _use(r["name"]) != "kitchen":
            continue
        poly = r["poly"]
        here = [f for f in mine if poly.contains(Point(f["x"], f["y"]))
                and f.get("kind") in ("ksink", "stove", "fridge",
                                      "cabinet")]
        if not here or any(f.get("kind") == "cabinet" for f in here):
            continue
        anchors = [f for f in here if f.get("kind") in ("ksink", "stove")]
        sides = _sides(poly)
        used = set()
        for f in anchors:
            # the side the sink / hob backs onto
            best = None
            for i, (a, b) in enumerate(sides):
                L = math.dist(a, b)
                u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                t = (f["x"] - a[0]) * u[0] + (f["y"] - a[1]) * u[1]
                off = abs((f["x"] - a[0]) * u[1] - (f["y"] - a[1]) * u[0])
                if -0.1 <= t <= L + 0.1 and off < 0.7 and \
                        (best is None or off < best[0]):
                    best = (off, i)
            if best is None or best[1] in used:
                continue
            used.add(best[1])
            a, b = sides[best[1]]
            L = math.dist(a, b)
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            n = (-u[1], u[0])
            c = poly.centroid
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if (c.x - m[0]) * n[0] + (c.y - m[1]) * n[1] < 0:
                n = (-n[0], -n[1])
            depth = 0.6
            k = max(int(round(L / 0.6)), 1)
            w = L / k
            for j in range(k):
                t = w * (j + 0.5)
                q = (a[0] + u[0] * t + n[0] * (depth / 2 + 0.01),
                     a[1] + u[1] * t + n[1] * (depth / 2 + 0.01))
                if not poly.contains(Point(q)):
                    continue
                if any(math.dist(q, (g["x"], g["y"])) < 0.45
                       for g in here):
                    continue                 # the sink / hob stands here
                # back to the wall (the model's +Y), its width along it
                _rec(doc, lid, cab, "cabinet", q[0], q[1],
                     back_to(-n[0], -n[1]), r, fit=[w, depth])
                got["cabinet"] = got.get("cabinet", 0) + 1
    return got


__all__ = ["furnish", "classify", "pick", "cad_blocks", "KINDS"]
