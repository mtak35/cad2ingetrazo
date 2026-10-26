# SPDX-License-Identifier: GPL-3.0-or-later
"""Fit-out read from the CAD plan, on every import of a floor:

* slab cuts named by a text — «VOID», «CUT OUT» (this floor's slab) and
  «DUCT», «SHAFT», «O.T.S» / «OPEN TO SKY», «LIGHT WELL» (this floor and
  every floor over it, the roof too): the room / outline round the text
  cut as a slab opening (``doc["man_shafts"]`` records with ``auto``);
* the GLASS layer inside a bathroom — a frameless glass shower partition
  with its glass door (``doc["fitout"]``, kind "glass");
* the CLADDING layer (CLAD, ACP, ALUCOBOND…) along a wall — aluminium
  composite panels on that wall's face (kind "clad");
* a LIFT / ELEVATOR room — the library's «Elevator» fitted in the well and
  its «Elevator door» in the opening on the lobby side; the well cut
  through the floor slab;
* the lighting layers (LIGHT, LIGHTING, ELE / ELEC with light blocks) —
  library ceiling lamps hung under the false ceiling (made for the floor
  when it has none);
* the AC layers (AC, HVAC, DIFFUSER…) — square / round / linear ceiling
  diffusers set in the false ceiling (kind "diffuser");
* the DRESS layer / a room named DRESS — library wardrobes along its
  walls (or in the outlines drawn).

The library pieces go in ``doc["furniture"]`` with ``src: "fitout"`` (the
CAD furniture's own pass leaves them alone); made again on each import.

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

import math
import re

#: texts that cut the slab: own floor / own floor and every one over it
CUT_OWN = re.compile(r"\bVOID\b|\bVOIDS\b|CUT[\s\-]*OUT|DOUBLE\s*HEIGHT|"
                     r"\bD\.?\s?H\.?\b", re.I)
CUT_UP = re.compile(r"\bDUCTS?\b|\bSHAFTS?\b|\bO\s?\.?\s?T\s?\.?\s?S\b|"
                    r"OPEN\s*TO\s*SKY|LIGHT\s*WELL|SKY\s*WELL|"
                    r"\bP\.?\s?D\b\.?|PLUMBING\s*DUCT|SERVICE\s*DUCT", re.I)
GLASS_LAYER = re.compile(r"GLASS|GLAZ|SHOWER|SCREEN|PARTITION.?GL", re.I)
CLAD_LAYER = re.compile(r"CLAD|\bACP\b|ALUCO|ALU.?COMP|ALUMIN|FACADE.?PAN|"
                        r"A\.C\.P", re.I)
LIFT_ROOM = re.compile(r"\bLIFT|ELEVAT|\bELEV\b|\bELV\b", re.I)
LIGHT_LAYER = re.compile(r"LIGHT|LIGHTING|LAMP|LUMIN", re.I)
ELEC_LAYER = re.compile(r"^ELE\b|^ELE[\s_\-]|\bELE\b|ELEC|ELECT|E[\-_]L", re.I)
LIGHT_NAME = re.compile(r"LIGHT|LAMP|SPOT|DOWN|\bLED\b|BULB|FIXT|CFL|TUBE|"
                        r"PANEL|CHANDEL|PENDANT|\bDL\b|LUMIN", re.I)
NOT_LIGHT = re.compile(r"SWITCH|SOCKET|S\.?/?B\b|\bDB\b|BOARD|PLUG|FAN|"
                       r"\bAC\b|\bTV\b|TEL|DATA|CCTV|BELL|WALL|BRACKET|"
                       r"EXHAUST|SMOKE|SPEAKER|CAMERA|METER", re.I)
AC_LAYER = re.compile(r"(^|[^A-Z])A\.?C(\.|[^A-Z]|$)|HVAC|DIFF|AIR.?COND|"
                      r"SUPPLY.?AIR|RETURN.?AIR|S\.?A\.?D|R\.?A\.?G|"
                      r"\bMECH|GRILLE|DUCTING", re.I)
NOT_AC = re.compile(r"OUTDOOR|OUTER|CONDENS|SPLIT|COMPRESS|\bODU\b", re.I)
DRESS_LAYER = re.compile(r"DRESS|WARD|W\.?/\s?ROBE|CLOSET|ALMIRAH|CUPBOARD",
                         re.I)
DRESS_WORDS = re.compile(r"DRESS|WARD.?ROBE|W\.?/\s?ROBE|WALK.?IN|CLOSET",
                         re.I)
BATH_ROOM = re.compile(r"BATH|TOILET|W\.?C\b|WASH|LAV|POWDER|SHOWER", re.I)

GLASS_H = 2.0            # the shower glass, over the finished floor
GLASS_T = 0.010
CLAD_T = 0.025           # 4 mm ACP on its rails
CLAD_W = 1.2192          # panels 4' wide…
CLAD_HP = 0.6096         # …and 2' high
WARD_D = 0.6


def _seg_dir(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 1e-9 else (1.0, 0.0)


def _rooms(arch, lid):
    from .engine import spaces
    try:
        return spaces.of_level(arch, lid)
    except Exception:  # noqa: BLE001
        return []


def _room_at(rooms, x, y, shrink=0.0):
    from shapely.geometry import Point
    p = Point(x, y)
    best = None
    for r in rooms:
        g = r["poly"].buffer(-shrink) if shrink else r["poly"]
        try:
            if g.contains(p) and (best is None or
                                  r["area"] < best["area"]):
                best = r
        except Exception:  # noqa: BLE001
            continue
    return best


def _box_c(ins):
    cs = ins.get("corners") or []
    if len(cs) < 4:
        return float(ins["x"]), float(ins["y"]), 0.0, 0.0
    xs = [c[0] for c in cs]
    ys = [c[1] for c in cs]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
            max(xs) - min(xs), max(ys) - min(ys))


def _dedupe(pts, d=0.08):
    out = []
    for p in pts:
        if all(math.dist(p[:2], q[:2]) >= d for q in out):
            out.append(p)
    return out


# ---- what the plan holds ----------------------------------------------------
def analyze(doc, lid, pl, entries=None) -> dict:
    """Read the level's fit-out from its placed plan ``pl``
    (``cadread.place``). The report {kind: n}."""
    from . import project as PJ
    arch = doc["arch"]
    st = doc["settings"]
    rep = {}
    if not st.get("fitout_on", True):
        clear(doc, lid)
        return rep
    clear(doc, lid)
    rooms = _rooms(arch, lid)
    if entries is None:
        try:
            from . import library as LB
            entries = LB.list_entries()
        except Exception:  # noqa: BLE001
            entries = []
    steps = (("slab cuts", _text_cuts), ("shower glass", _shower_glass),
             ("cladding", _cladding), ("lift", _lift),
             ("lights", _lights), ("AC diffusers", _diffusers),
             ("wardrobes", _wardrobes))
    for name, fn in steps:
        try:
            n = fn(doc, lid, pl, rooms, entries)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error(f"fitout.{fn.__name__}")
            n = 0
        if n:
            rep[name] = n
    del PJ
    return rep


def clear(doc, lid) -> None:
    """The fit-out an earlier import of the level made: gone."""
    doc["fitout"] = [f for f in doc.get("fitout") or []
                     if f.get("level") != lid]
    doc["furniture"] = [f for f in doc.get("furniture") or []
                        if not (f.get("src") == "fitout"
                                and f.get("level") == lid)]
    doc["man_shafts"] = [m for m in doc.get("man_shafts") or []
                         if not (m.get("auto") and m.get("level") == lid)]


def _new_id():
    import uuid
    return uuid.uuid4().hex[:8]


# ---- slab cuts --------------------------------------------------------------
def _outline_at(pl, rooms, x, y, wall_like=None):
    """The smallest closed outline round (x, y): its room, a closed
    polyline, or the plan's lines closed round it. Shapely or None."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union
    p = Point(x, y)
    r = _room_at(rooms, x, y)
    best = r["poly"] if r is not None and r["area"] <= 80.0 else None
    for lp in pl.get("loops") or ():
        try:
            g = Polygon(lp["pts"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if 0.1 <= g.area <= 80.0 and g.contains(p) and (
                best is None or g.area < best.area):
            best = g
    near = []
    for s in pl["segs"]:
        a, b = (s[0], s[1]), (s[2], s[3])
        if min(a[0], b[0]) > x + 8 or max(a[0], b[0]) < x - 8 or \
                min(a[1], b[1]) > y + 8 or max(a[1], b[1]) < y - 8:
            continue
        if math.dist(a, b) > 0.05:
            near.append(LineString([a, b]))
    if not near:
        return best
    try:
        for g in polygonize(unary_union(near)):
            if 0.1 <= g.area <= 80.0 and g.contains(p) and (
                    best is None or g.area < best.area - 0.05):
                best = g
    except Exception:  # noqa: BLE001
        return best
    return best


def _text_cuts(doc, lid, pl, rooms, entries) -> int:
    n = 0
    for t in pl.get("texts") or ():
        s = str(t.get("text", ""))
        up = bool(CUT_UP.search(s))
        own = bool(CUT_OWN.search(s))
        if not (up or own):
            continue
        g = _outline_at(pl, rooms, float(t["x"]), float(t["y"]))
        if g is None or g.is_empty:
            continue
        if g.geom_type != "Polygon":
            g = max(g.geoms, key=lambda q: q.area)
        pts = [[round(x, 4), round(y, 4)]
               for x, y in list(g.exterior.coords)[:-1]]
        doc.setdefault("man_shafts", []).append(
            {"id": _new_id(), "level": lid, "through": False, "pts": pts,
             "auto": "text", "up": up, "own": True,
             "note": s.strip()[:30]})
        n += 1
    return n


def cut_targets(doc, m, slabs) -> list:
    """The slabs an automatic cut opens: its own floor (never the lowest
    floor's, on the ground) and, «up», every floor over it and the
    roof."""
    from . import project as PJ
    arch = doc["arch"]
    el = PJ.elevations(arch)
    zl = {lv["id"]: el[i] for i, lv in enumerate(arch["levels"])}
    lid = m.get("level")
    if lid not in zl:
        return []
    z0 = zl[lid]
    lowest = min(zl.values())
    out, seen = [], set()

    def add(ss):
        for s in ss:
            if id(s) not in seen and not s.get("grade") and \
                    not s.get("zone"):
                seen.add(id(s))
                out.append(s)
    if m.get("own", True) and z0 > lowest + 1e-6:
        add(PJ._floor_slabs(doc, lid))
    if m.get("up"):
        for k, z in zl.items():
            if z > z0 + 1e-6:
                add(PJ._floor_slabs(doc, k))
        add([s for s in slabs if s.get("roof") and zl.get(s["level"],
                                                          -1e9) >= z0 - 1e-6])
    return out


# ---- shower glass -----------------------------------------------------------
def _runs(segs, gap=0.3, min_len=0.25):
    """Parallel lines drawn as a pair (the glass' faces) as one run each:
    [(a, b)]."""
    from . import cornerwin as CW
    out = []
    for a, b, _sp, _n in CW._clusters(segs, gap=gap):
        if math.dist(a, b) >= min_len:
            out.append((tuple(a), tuple(b)))
    return out


def _shower_glass(doc, lid, pl, rooms, entries) -> int:
    from shapely.geometry import Point
    lay = pl["layers"]
    baths = [r for r in rooms if BATH_ROOM.search(str(r["name"]))]
    if not baths:
        return 0
    n = 0
    for r in baths:
        inner = r["poly"].buffer(-0.06)
        if inner.is_empty:
            continue
        segs = []
        for s in pl["segs"]:
            if not GLASS_LAYER.search(lay[s[4]]):
                continue
            m = Point((s[0] + s[2]) / 2, (s[1] + s[3]) / 2)
            if inner.contains(m):
                segs.append(s)
        if not segs:
            continue
        runs = _runs(segs)
        if not runs:
            continue
        edge = r["poly"].exterior
        # the run's free end (away from the walls) takes the door
        longest = max(runs, key=lambda ab: math.dist(*ab))
        for a, b in runs:
            # carried to the walls they nearly touch
            u = _seg_dir(a, b)
            a2, b2 = list(a), list(b)
            for end, sgn in ((a2, -1), (b2, 1)):
                d = edge.distance(Point(end))
                if d < 0.25:
                    end[0] += u[0] * sgn * d
                    end[1] += u[1] * sgn * d
            L = math.dist(a2, b2)
            door = None
            if (a, b) == longest and L >= 0.9:
                da = edge.distance(Point(a2))
                db = edge.distance(Point(b2))
                dw = min(0.6, L * 0.5)
                door = [L - dw, L] if da <= db else [0.0, dw]
            doc.setdefault("fitout", []).append(
                {"id": _new_id(), "level": lid, "kind": "glass",
                 "a": [round(a2[0], 4), round(a2[1], 4)],
                 "b": [round(b2[0], 4), round(b2[1], 4)],
                 "h": GLASS_H, **({"door": [round(door[0], 4),
                                            round(door[1], 4)]}
                                  if door else {})})
            n += 1
    return n


# ---- aluminium cladding -----------------------------------------------------
def _cladding(doc, lid, pl, rooms, entries) -> int:
    from shapely.geometry import LineString, Point

    from .engine import walls as W
    lay = pl["layers"]
    segs = [s for s in pl["segs"] if CLAD_LAYER.search(lay[s[4]])]
    if not segs:
        return 0
    arch = doc["arch"]
    walls = [w for w in arch["walls"] if w["level"] == lid
             and w.get("kind", "line") == "line" and "a" in w
             and not w.get("rail")]
    n = 0
    for a, b in _runs(segs, gap=0.2, min_len=0.3):
        u = _seg_dir(a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        best = None
        for w in walls:
            try:
                c = W.centre(w)
            except Exception:  # noqa: BLE001
                continue
            p0, p1 = tuple(c.p0), tuple(c.p1)
            v = _seg_dir(p0, p1)
            if abs(u[0] * v[1] - u[1] * v[0]) > 0.09:
                continue
            d = LineString([p0, p1]).distance(Point(mid))
            if d > float(w["t"]) / 2 + 0.6:
                continue
            if best is None or d < best[0]:
                best = (d, w, p0, v)
        if best is None:
            continue
        _d, w, p0, v = best
        nrm = (-v[1], v[0])
        side = (mid[0] - p0[0]) * nrm[0] + (mid[1] - p0[1]) * nrm[1]
        if side < 0:
            nrm = (-nrm[0], -nrm[1])
        off = float(w["t"]) / 2 + 0.003

        def onto(q):
            t = (q[0] - p0[0]) * v[0] + (q[1] - p0[1]) * v[1]
            return [round(p0[0] + v[0] * t + nrm[0] * off, 4),
                    round(p0[1] + v[1] * t + nrm[1] * off, 4)]
        doc.setdefault("fitout", []).append(
            {"id": _new_id(), "level": lid, "kind": "clad",
             "a": onto(a), "b": onto(b),
             "n": [round(nrm[0], 4), round(nrm[1], 4)],
             "z0": round(float(w.get("base", 0.0) or 0.0), 4),
             "z1": ("level" if w.get("height", "level") == "level"
                    else round(float(w.get("height") or 3.0), 4)),
             "wall": w["id"]})
        n += 1
    return n


# ---- the lift ---------------------------------------------------------------
def _pick_named(entries, words, cat=None):
    for w in words:
        for e in entries:
            if cat and e.get("cat") != cat:
                continue
            if str(e.get("name", "")).strip().lower() == w:
                return e
    for w in words:
        for e in entries:
            if (not cat or e.get("cat") == cat) and \
                    w in str(e.get("name", "")).lower():
                return e
    return None


def _openings_xy(doc, lid):
    from .engine import walls as W
    arch = doc["arch"]
    byid = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    out = []
    for o in arch["openings"]:
        w = byid.get(o.get("wall"))
        if w is None or w.get("kind", "line") != "line" or "a" not in w:
            continue
        try:
            c = W.centre(w)
        except Exception:  # noqa: BLE001
            continue
        u = _seg_dir(tuple(c.p0), tuple(c.p1))
        out.append(((c.p0[0] + u[0] * o["pos"], c.p0[1] + u[1] * o["pos"]),
                    float(o["w"]), u, o, w))
    return out


def _furn_rec(doc, lid, e, kind, x, y, rot, room=None, fit=None, **kw):
    r = {"id": _new_id(), "level": lid, "key": e["key"],
         "name": e["name"], "x": round(x, 4), "y": round(y, 4),
         "rot": round(rot % 360.0, 3), "cad": True, "kind": kind,
         "src": "fitout"}
    if room and room.get("rec"):
        r["room"] = room["rec"]["id"]
    if e.get("entry"):
        r["entry"] = e["entry"]
    if fit:
        r["fit"] = [round(fit[0], 4), round(fit[1], 4)]
    r.update(kw)
    doc.setdefault("furniture", []).append(r)
    return r


def _lift(doc, lid, pl, rooms, entries) -> int:
    from shapely.geometry import Point

    from .furnish import back_to
    lifts = [r for r in rooms if LIFT_ROOM.search(str(r["name"]))
             and 1.2 <= r["area"] <= 12.0]
    # a «LIFT» text in a room the walls close
    for t in pl.get("texts") or ():
        if LIFT_ROOM.search(str(t.get("text", ""))):
            r = _room_at(rooms, float(t["x"]), float(t["y"]))
            if r is not None and 1.2 <= r["area"] <= 12.0 and \
                    all(r is not q for q in lifts):
                lifts.append(r)
    if not lifts:
        return 0
    car = _pick_named(entries, ["elevator"])
    door = _pick_named(entries, ["elevator door"])
    ops = _openings_xy(doc, lid)
    n = 0
    for r in lifts:
        poly = r["poly"]
        mrr = poly.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)[:-1]
        e0 = (cs[0], cs[1])
        e1 = (cs[1], cs[2])
        c = poly.centroid
        # the opening on its edge: the lobby's side
        edge = poly.exterior
        op = None
        for q, w_, u, o, w in ops:
            if edge.distance(Point(q)) <= float(w["t"]) / 2 + 0.12 and (
                    op is None or w_ > op[1]):
                op = (q, w_, u, o, w)
        if op is not None:
            q = op[0]
            nd = (q[0] - c.x, q[1] - c.y)
            L_ = math.hypot(*nd) or 1.0
            nd = (nd[0] / L_, nd[1] / L_)
            # square to the wall: its normal toward the opening
            u = op[2]
            nn = (-u[1], u[0])
            if nn[0] * nd[0] + nn[1] * nd[1] < 0:
                nn = (-nn[0], -nn[1])
            nd = nn
        else:
            ux = _seg_dir(*e0)
            nd = (-ux[1], ux[0])
        # the well's sides across / along the door's facing
        a_ = math.dist(*e0)
        b_ = math.dist(*e1)
        ue0 = _seg_dir(*e0)
        along_e0 = abs(ue0[0] * nd[1] - ue0[1] * nd[0]) > 0.7
        width, depth = (a_, b_) if along_e0 else (b_, a_)
        if car is not None:
            _furn_rec(doc, lid, car, "lift", c.x, c.y,
                      back_to(-nd[0], -nd[1]), r,
                      fit=[max(width - 0.1, 0.8), max(depth - 0.1, 0.8)],
                      fit_free=True)
            n += 1
        if door is not None and op is not None:
            q, w_, u, o, w = op
            ow = max(min(w_, width), 0.8)
            off = float(w["t"]) / 2 - 0.11
            # its back toward the car, its face to the lobby (−Y front)
            _furn_rec(doc, lid, door, "liftdoor",
                      q[0] - nd[0] * max(off, 0.0),
                      q[1] - nd[1] * max(off, 0.0),
                      back_to(-nd[0], -nd[1]), r, fit=[ow + 0.15, 0.215],
                      fit_free=True, fit_h=float(o.get("h", 2.1) or 2.1))
            n += 1
        # the well: through this floor's slab
        pts = [[round(x, 4), round(y, 4)]
               for x, y in list(poly.buffer(-0.01).exterior.coords)[:-1]]
        doc.setdefault("man_shafts", []).append(
            {"id": _new_id(), "level": lid, "through": False, "pts": pts,
             "auto": "lift", "up": False, "own": True, "note": "LIFT"})
    return n


# ---- the ceiling's lights and AC diffusers ----------------------------------
def _need_ceiling(doc, lid):
    from . import ceilings as CE
    if lid not in (doc.get("ceilings") or {}):
        CE.set_level(doc, lid)


def ceiling_h(doc, lid, room, fallback=None):
    """The false ceiling's height over the floor in ``room`` (a
    spaces.of_level room) — or the level's, or ``fallback``."""
    from . import ceilings as CE
    from . import project as PJ
    c = None
    if room is not None:
        try:
            c = CE.room_ceiling(doc, lid, PJ.room_key(lid, room))
            rec = room.get("rec") or {}
            if rec.get("ceiling_h"):
                c = dict(c or {}, h=float(rec["ceiling_h"]))
        except Exception:  # noqa: BLE001
            c = None
    if c is None:
        lv = (doc.get("ceilings") or {}).get(lid)
        if lv:
            return float(lv.get("h", CE.DEFAULT_H))
        return fallback
    return float(c["h"])


def _lights(doc, lid, pl, rooms, entries) -> int:
    lay_ok = lambda L: bool(LIGHT_LAYER.search(L))  # noqa: E731
    pts = []
    for ins in pl.get("inserts") or ():
        L = str(ins.get("layer", ""))
        nm = str(ins.get("name", ""))
        if NOT_LIGHT.search(nm):
            continue
        if not (lay_ok(L) or (ELEC_LAYER.search(L) and LIGHT_NAME.search(nm))
                or LIGHT_NAME.search(nm) and not re.search(
                    r"WALL|BRACKET|GARDEN|STREET|BOLLARD", nm, re.I)):
            continue
        if NOT_LIGHT.search(L) and not lay_ok(L):
            continue
        x, y, dx, dy = _box_c(ins)
        if max(dx, dy) > 1.8:
            continue
        pts.append((x, y, max(dx, dy), min(dx, dy), float(ins.get("rot",
                                                                  0.0))))
    for ci in pl.get("circles") or ():
        if lay_ok(str(ci["layer"])) and 0.03 <= float(ci["r"]) <= 0.35:
            pts.append((ci["c"][0], ci["c"][1], 2 * ci["r"], 2 * ci["r"],
                        0.0))
    pts.sort(key=lambda p: -p[2])            # the outer ring of a symbol
    pts = _dedupe(pts, 0.12)
    if not pts:
        return 0
    lamp = _pick_named(entries, ["ceiling lamp"], "Lights")
    strip = _pick_named(entries, ["fluorescent strip",
                                  "fluorescent light"], "Lights") or lamp
    if lamp is None:
        return 0
    n = 0
    placed = False
    for x, y, L, W_, rot in pts:
        r = _room_at(rooms, x, y)
        if r is None:
            continue
        if not placed:
            _need_ceiling(doc, lid)
            placed = True
        h = ceiling_h(doc, lid, r, 2.4384)
        e = strip if (W_ > 0 and L / max(W_, 1e-6) > 2.5 and L >= 0.5) \
            else lamp
        _furn_rec(doc, lid, e, "lamp", x, y, rot, r, hang=round(h, 4))
        n += 1
    return n


def _diffusers(doc, lid, pl, rooms, entries) -> int:
    from shapely.geometry import Polygon
    items = []
    for ins in pl.get("inserts") or ():
        L = str(ins.get("layer", ""))
        nm = str(ins.get("name", ""))
        if not (AC_LAYER.search(L) or re.search(r"DIFFUS|GRILLE|\bSAD\b|"
                                                r"\bRAG\b|CASSETTE", nm,
                                                re.I)):
            continue
        if NOT_AC.search(nm):
            continue
        x, y, dx, dy = _box_c(ins)
        if not (0.12 <= max(dx, dy) <= 2.4) or min(dx, dy) < 0.08:
            continue
        rot = float(ins.get("rot", 0.0) or 0.0)
        q = round((rot % 180.0) / 90.0) % 2
        lx, ly = (dy, dx) if q == 1 else (dx, dy)
        items.append((x, y, lx, ly, rot % 90.0 if abs(rot % 90.0) > 1 else
                      0.0, False))
    for lp in pl.get("loops") or ():
        if not AC_LAYER.search(str(lp["layer"])):
            continue
        try:
            g = Polygon(lp["pts"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if g.is_empty:
            continue
        m = g.minimum_rotated_rectangle
        cs = list(m.exterior.coords)[:-1]
        a_, b_ = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        if not (0.12 <= max(a_, b_) <= 2.4) or min(a_, b_) < 0.08:
            continue
        ang = math.degrees(math.atan2(cs[1][1] - cs[0][1],
                                      cs[1][0] - cs[0][0])) % 90.0
        if ang > 45:
            ang -= 90
        c = g.centroid
        swap = abs(ang) > 1e-6 and False
        del swap
        items.append((c.x, c.y, a_, b_, ang, False))
    for ci in pl.get("circles") or ():
        if AC_LAYER.search(str(ci["layer"])) and \
                0.08 <= float(ci["r"]) <= 0.4:
            items.append((ci["c"][0], ci["c"][1], 2 * ci["r"], 2 * ci["r"],
                          0.0, True))
    items.sort(key=lambda p: -max(p[2], p[3]))
    items = _dedupe(items, 0.15)
    n = 0
    placed = False
    for x, y, lx, ly, rot, rnd in items:
        r = _room_at(rooms, x, y)
        if r is None:
            continue
        if not placed:
            _need_ceiling(doc, lid)
            placed = True
        doc.setdefault("fitout", []).append(
            {"id": _new_id(), "level": lid, "kind": "diffuser",
             "x": round(x, 4), "y": round(y, 4),
             "lx": round(min(max(lx, 0.15), 2.4), 4),
             "ly": round(min(max(ly, 0.15), 2.4), 4),
             "rot": round(rot, 3), "round": bool(rnd),
             "room": (r.get("rec") or {}).get("id"),
             "hang": round(ceiling_h(doc, lid, r, 2.4384), 4)})
        n += 1
    return n


# ---- wardrobes --------------------------------------------------------------
def _wardrobes(doc, lid, pl, rooms, entries) -> int:
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union

    from . import furnish as FU
    lay = pl["layers"]
    ward = FU.pick("wardrobe", 1.0, 0.6, entries, {})
    if ward is None:
        return 0
    have = [f for f in doc.get("furniture") or [] if f["level"] == lid
            and f.get("kind") == "wardrobe" and not f.get("auto")]
    n = 0
    taken_rooms = set()
    # the outlines drawn on the DRESS layer
    lines = [LineString([(s[0], s[1]), (s[2], s[3])]) for s in pl["segs"]
             if DRESS_LAYER.search(lay[s[4]])]
    polys = [Polygon(lp["pts"]).buffer(0) for lp in pl.get("loops") or ()
             if DRESS_LAYER.search(str(lp["layer"])) and len(lp["pts"]) >= 3]
    if lines:
        try:
            polys += list(polygonize(unary_union(lines)))
        except Exception:  # noqa: BLE001
            pass
    for g in polys:
        if g.is_empty:
            continue
        m = g.minimum_rotated_rectangle
        cs = list(m.exterior.coords)[:-1]
        a_, b_ = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        L, Wd = max(a_, b_), min(a_, b_)
        if not (0.6 <= L <= 6.0 and 0.35 <= Wd <= 1.0):
            continue
        c = g.centroid
        if any(math.dist((c.x, c.y), (f["x"], f["y"])) < 0.3 for f in have):
            continue
        e = (cs[0], cs[1]) if a_ >= b_ else (cs[1], cs[2])
        u = _seg_dir(*e)
        r = _room_at(rooms, c.x, c.y)
        nrm = (-u[1], u[0])
        if r is not None:          # its back to the nearer wall
            fw = FU.face_wall(r["poly"], c.x, c.y, abs(u[0]) * L + abs(
                u[1]) * Wd, abs(u[1]) * L + abs(u[0]) * Wd, reach=0.4)
            if fw is not None:
                rot = fw[0]
            else:
                rot = FU.back_to(*nrm)
        else:
            rot = FU.back_to(*nrm)
        k = max(int(round(L / 1.0)), 1)
        for j in range(k):
            t = -L / 2 + L / k * (j + 0.5)
            _furn_rec(doc, lid, ward, "wardrobe", c.x + u[0] * t,
                      c.y + u[1] * t, rot, r, fit=[L / k, Wd],
                      fit_free=True)
            n += 1
        if r is not None:
            taken_rooms.add(id(r))
    # a room named DRESS (or a DRESS text in it): wardrobes along its walls
    named = [r for r in rooms if DRESS_WORDS.search(str(r["name"]))]
    for t in pl.get("texts") or ():
        if DRESS_WORDS.search(str(t.get("text", ""))):
            r = _room_at(rooms, float(t["x"]), float(t["y"]))
            if r is not None and all(r is not q for q in named):
                named.append(r)
    doors = FU._doors(doc, lid)
    for r in named:
        if id(r) in taken_rooms or r["area"] < 1.5 or r["area"] > 30.0:
            continue
        poly = r["poly"]
        if any(poly.contains(Point(f["x"], f["y"])) for f in have):
            continue
        mrr = poly.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)[:-1]
        short = min(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
        sides_max = 2 if short >= 2.1 else 1
        c = poly.centroid
        done = 0
        used = []
        used_ab = []
        for a, b in FU._sides(poly):
            if done >= sides_max:
                break
            L = math.dist(a, b)
            if L < 0.9:
                continue
            u = _seg_dir(a, b)
            if any(abs(u[0] * v[1] - u[1] * v[0]) < 0.2 and
                   abs((a[0] - q[0]) * v[1] - (a[1] - q[1]) * v[0]) < 0.5
                   for q, v in used):
                continue                   # the side across the passage
            nrm = (-u[1], u[0])
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if (c.x - m[0]) * nrm[0] + (c.y - m[1]) * nrm[1] < 0:
                nrm = (-nrm[0], -nrm[1])
            # the run clear of the doors' swing (and of the run already
            # set on the side it meets at a corner)
            s0_, s1_ = 0.0, L
            for (qa, qb), _v in used_ab:
                seg_ = LineString([qa, qb])
                if seg_.distance(Point(a)) < 0.1:
                    s0_ += WARD_D + 0.02
                if seg_.distance(Point(b)) < 0.1:
                    s1_ -= WARD_D + 0.02
            spans = [(s0_, s1_)] if s1_ - s0_ > 0.5 else []
            for dx, dy, dw in doors:
                tq = (dx - a[0]) * u[0] + (dy - a[1]) * u[1]
                off = abs((dx - a[0]) * nrm[0] + (dy - a[1]) * nrm[1])
                if off < dw + 0.35 and -dw <= tq <= L + dw:
                    lo_, hi_ = tq - dw / 2 - 0.1, tq + dw / 2 + 0.1
                    if off < 0.45:          # a door in this very wall
                        pass
                    else:                   # a door in the wall across
                        lo_, hi_ = tq - dw, tq + dw
                    ns = []
                    for s0, s1 in spans:
                        if hi_ <= s0 or lo_ >= s1:
                            ns.append((s0, s1))
                            continue
                        if lo_ > s0:
                            ns.append((s0, lo_))
                        if hi_ < s1:
                            ns.append((hi_, s1))
                    spans = ns
            got = 0
            for s0, s1 in spans:
                run = s1 - s0
                if run < 0.6:
                    continue
                k = max(int(round(run / 1.0)), 1)
                wk = run / k
                for j in range(k):
                    t = s0 + wk * (j + 0.5)
                    q = (a[0] + u[0] * t + nrm[0] * (WARD_D / 2 + 0.01),
                         a[1] + u[1] * t + nrm[1] * (WARD_D / 2 + 0.01))
                    if not poly.contains(Point(q)):
                        continue
                    _furn_rec(doc, lid, ward, "wardrobe", q[0], q[1],
                              FU.back_to(-nrm[0], -nrm[1]), r,
                              fit=[wk, WARD_D], fit_free=True)
                    n += 1
                    got += 1
            if got:
                done += 1
                used.append((a, u))
                used_ab.append(((a, b), u))
    return n


# ---- building them ------------------------------------------------------------
GLASS_COL = (0.72, 0.86, 0.90)
CHROME = (0.78, 0.79, 0.81)
ACP_COL = (0.74, 0.76, 0.78)
DIFF_COL = (0.93, 0.93, 0.93)
DIFF_DARK = (0.35, 0.36, 0.38)


def _box_faces(cx, cy, ux, uy, l, d, z0, z1):
    from .engine import walls as W
    nx, ny = -uy, ux
    hl, hd = l / 2, d / 2
    pts = [(cx - ux * hl - nx * hd, cy - uy * hl - ny * hd),
           (cx + ux * hl - nx * hd, cy + uy * hl - ny * hd),
           (cx + ux * hl + nx * hd, cy + uy * hl + ny * hd),
           (cx - ux * hl + nx * hd, cy - uy * hl + ny * hd)]
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(pts, pts[1:] + pts[:1]))
    if a < 0:
        pts.reverse()
    return W.solid({"outer": pts, "holes": []}, z0, z1)


def _poly_faces(poly, z0, z1):
    from .engine import walls as W
    pts = [tuple(c) for c in list(poly.exterior.coords)[:-1]]
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(pts, pts[1:] + pts[:1]))
    if a < 0:
        pts.reverse()
    holes = []
    for h in poly.interiors:
        hp = [tuple(c) for c in list(h.coords)[:-1]]
        ah = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                       for p, q in zip(hp, hp[1:] + hp[:1]))
        holes.append(hp if ah < 0 else list(reversed(hp)))
    return W.solid({"outer": pts, "holes": holes}, z0, z1)


def groups(doc):
    """The shower glass, the cladding and the diffusers of every level."""
    from core.group import Group

    from . import project as PJ
    from .host import KEY, level_layer
    recs = doc.get("fitout") or []
    if not recs:
        return []
    arch = doc["arch"]
    st = doc["settings"]
    elev = PJ.elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    fin = float(st.get("finish_t", 0.0508) or 0.0) \
        if st.get("finish_on", True) else 0.0
    rooms_of = {}
    out = []

    def grp(f, name, faces, color, opacity=1.0, ifc="IfcCovering"):
        if not faces:
            return
        faces = [q if isinstance(q, dict) else {"loop": q, "holes": []}
                 for q in faces]
        g = Group(PJ._mesh_of(faces), name=f"{name} · {names[f['level']]}")
        g.component = False
        g.material = {"color": color, "opacity": opacity}
        g.layer = level_layer(names[f["level"]])
        g.ifc = {"class": ifc, "name": name}
        g.ext = {KEY: {"type": "fitout", "id": f["id"],
                       "level": f["level"], "kind": f["kind"]}}
        out.append(g)
    for f in recs:
        lid = f.get("level")
        if lid not in z_of:
            continue
        z = z_of[lid]
        k = f.get("kind")
        try:
            if k == "glass":
                a, b = f["a"], f["b"]
                L = math.dist(a, b)
                if L < 0.1:
                    continue
                u = _seg_dir(a, b)
                z0 = z + fin
                h = float(f.get("h", GLASS_H))
                dr = f.get("door")
                glass, metal = [], []
                parts = [(0.0, L)]
                if dr:
                    parts = [(s0, s1) for s0, s1 in
                             ((0.0, dr[0]), (dr[1], L)) if s1 - s0 > 0.02]
                for s0, s1 in parts:
                    cx = a[0] + u[0] * (s0 + s1) / 2
                    cy = a[1] + u[1] * (s0 + s1) / 2
                    glass += _box_faces(cx, cy, u[0], u[1], s1 - s0 - 0.004,
                                        GLASS_T, z0 + 0.01, z0 + h)
                    metal += _box_faces(cx, cy, u[0], u[1], s1 - s0, 0.02,
                                        z0, z0 + 0.012)       # the channel
                if dr:
                    nx, ny = -u[1], u[0]
                    t0, t1 = dr
                    cx = a[0] + u[0] * (t0 + t1) / 2 + nx * 0.016
                    cy = a[1] + u[1] * (t0 + t1) / 2 + ny * 0.016
                    glass += _box_faces(cx, cy, u[0], u[1], t1 - t0 - 0.006,
                                        GLASS_T, z0 + 0.012, z0 + h - 0.01)
                    # its pull handle and two hinges
                    hx = a[0] + u[0] * (t0 + 0.06 if dr[0] > 0.01 else
                                        t1 - 0.06) + nx * 0.016
                    hy = a[1] + u[1] * (t0 + 0.06 if dr[0] > 0.01 else
                                        t1 - 0.06) + ny * 0.016
                    metal += _box_faces(hx, hy, u[0], u[1], 0.02, 0.07,
                                        z0 + 0.85, z0 + 1.25)
                    jt = t1 - 0.005 if dr[0] > 0.01 else t0 + 0.005
                    jx = a[0] + u[0] * jt
                    jy = a[1] + u[1] * jt
                    for zh in (0.25, h - 0.3):
                        metal += _box_faces(jx, jy, u[0], u[1], 0.06, 0.04,
                                            z0 + zh, z0 + zh + 0.08)
                grp(f, "Shower glass partition", glass, GLASS_COL, 0.35,
                    "IfcPlate")
                grp(dict(f, id=f["id"] + "m"), "Shower glass fittings",
                    metal, CHROME, 1.0, "IfcMember")
            elif k == "clad":
                a, b = f["a"], f["b"]
                L = math.dist(a, b)
                if L < 0.1:
                    continue
                u = _seg_dir(a, b)
                nx, ny = f.get("n") or (-u[1], u[0])
                z0 = z + float(f.get("z0", 0.0))
                if f.get("z1", "level") == "level":     # the storey's height
                    ups = sorted(v for v in z_of.values() if v > z + 0.5)
                    lv_ = next(lv for lv in arch["levels"]
                               if lv["id"] == lid)
                    z1 = ups[0] if ups else z + float(
                        lv_.get("height", 3.0) or 3.0)
                else:
                    z1 = z + float(f["z1"])
                fs = []
                nW = max(int(math.ceil(L / CLAD_W)), 1)
                wp = L / nW
                nH = max(int(math.ceil((z1 - z0) / CLAD_HP)), 1)
                hp = (z1 - z0) / nH
                gap = 0.008
                for i in range(nW):
                    t = wp * (i + 0.5)
                    cx = a[0] + u[0] * t + nx * CLAD_T / 2
                    cy = a[1] + u[1] * t + ny * CLAD_T / 2
                    for j in range(nH):
                        fs += _box_faces(cx, cy, u[0], u[1], wp - gap,
                                         CLAD_T, z0 + hp * j + gap / 2,
                                         z0 + hp * (j + 1) - gap / 2)
                grp(f, "Aluminium cladding (ACP)", fs, ACP_COL, 1.0,
                    "IfcCovering")
            elif k == "diffuser":
                rooms = rooms_of.get(lid)
                if rooms is None:
                    rooms = rooms_of[lid] = _rooms(arch, lid)
                r = _room_at(rooms, f["x"], f["y"])
                h = ceiling_h(doc, lid, r, float(f.get("hang", 2.4384)))
                zc = z + h
                lx, ly = float(f["lx"]), float(f["ly"])
                ang = math.radians(float(f.get("rot", 0.0)))
                u = (math.cos(ang), math.sin(ang))
                from shapely.geometry import Point
                from shapely import affinity
                fs, dk = [], []
                if f.get("round"):
                    rr = lx / 2
                    fs += _poly_faces(Point(f["x"], f["y"]).buffer(rr, 24),
                                      zc - 0.012, zc - 0.001)
                    for k_ in (0.75, 0.5, 0.25):
                        ring = Point(f["x"], f["y"]).buffer(rr * k_, 24) \
                            .difference(Point(f["x"], f["y"])
                                        .buffer(rr * k_ - 0.012, 24))
                        dk += _poly_faces(ring, zc - 0.016, zc - 0.012)
                else:
                    fs += _box_faces(f["x"], f["y"], u[0], u[1], lx, ly,
                                     zc - 0.012, zc - 0.001)
                    from shapely.geometry import box as _bx
                    for k_ in (0.8, 0.6, 0.4):
                        ring = _bx(-lx * k_ / 2, -ly * k_ / 2, lx * k_ / 2,
                                   ly * k_ / 2).difference(
                            _bx(-lx * k_ / 2 + 0.012, -ly * k_ / 2 + 0.012,
                                lx * k_ / 2 - 0.012, ly * k_ / 2 - 0.012))
                        ring = affinity.rotate(ring, math.degrees(ang),
                                               origin=(0, 0))
                        ring = affinity.translate(ring, f["x"], f["y"])
                        dk += _poly_faces(ring, zc - 0.016, zc - 0.012)
                grp(f, "AC diffuser", fs, DIFF_COL, 1.0, "IfcAirTerminal")
                grp(dict(f, id=f["id"] + "s"), "AC diffuser slots", dk,
                    DIFF_DARK, 1.0, "IfcAirTerminal")
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("fitout.groups")
    return out


__all__ = ["analyze", "clear", "groups", "cut_targets", "ceiling_h"]
