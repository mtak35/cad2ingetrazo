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
    remove(doc)                 # (the look's own: made again, as now)
    if doc.get("minarets"):     # (made by hand: left as they are)
        return 0
    from . import minarets as MN
    from . import project as PJ
    lid, poly = hall(doc)
    if poly is None:
        return 0
    try:                        # 3.64.68: at the highest tier's corners,
        from shapely.ops import unary_union    # as the perspectives show
        for tl in (doc.get("tiers") or {}):
            plan = tier_plan(doc, tl)
            if plan:
                poly = unary_union(plan[-1][1])
                break
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("mosque.minarets tiers")
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
    # 3.64.71: on the stair cores the plans draw (the stairs up to the roof
    # and the minarets' own): one minaret on each, as the plans place them
    for tl in (doc.get("tiers") or {}):        # 3.64.72: where the roof
        mp = marks_plan(doc, tl)               # plan writes «MINARET»
        if mp and mp.get("minarets"):
            pts = [(x, y, side, a_) for x, y, side, a_ in mp["minarets"]]
            if len(pts) == 2 and doc["settings"].get("rear_minarets", True):
                # 3.64.74: the perspectives show four — the pair the plan
                # marks at the front's ends, its twin at the back's ends
                # (the building's centre through)
                from shapely.ops import unary_union
                from shapely.geometry import Point as _Pt
                mass_ = unary_union([unary_union(ps_) for _z, ps_, _o in
                                     mp["masses"]])
                c_ = mass_.centroid
                near_ = mass_.buffer(0.4)
                for x, y, side, a_ in list(pts):
                    qx, qy = 2 * c_.x - x, 2 * c_.y - y
                    d_ = math.hypot(qx - c_.x, qy - c_.y) or 1.0
                    ux, uy = (qx - c_.x) / d_, (qy - c_.y) / d_
                    for _ in range(40):      # out of the building's mass
                        if not near_.contains(_Pt(qx, qy)):
                            break
                        qx, qy = qx + ux * 0.3, qy + uy * 0.3
                    pts.append((qx, qy, side, a_))
            for x, y, side, a_ in pts:
                rec = MN.new_minaret(doc, lid, x, y, b=min(max(side, 1.2),
                                                           3.0),
                                     h=H, galleries=1, cupola="modern",
                                     rot=a_ % 90.0, color="white")
                rec["id"] = "auto-" + rec["id"]
            return len(pts)
    cores = stair_cores(doc, lid, poly)
    if len(cores) >= 2:
        for x, y, a_ in cores:
            rec = MN.new_minaret(doc, lid, x, y, b=b, h=H, galleries=1,
                                 cupola="modern", rot=a_ % 90.0,
                                 color="white")
            rec["id"] = "auto-" + rec["id"]
        return len(cores)
    for x, y in cs:                    # just outside the hall's corner
        d = math.hypot(x - cx, y - cy)
        k = (d + b * 0.35) / max(d, 1e-6)
        rec = MN.new_minaret(doc, lid, cx + (x - cx) * k,
                             cy + (y - cy) * k, b=b, h=H, galleries=1,
                             cupola="modern", rot=ang % 90.0, color="white")
        rec["id"] = "auto-" + rec["id"]     # (the look's: gone with it)
    return 4


def stair_cores(doc, lid, poly) -> list:
    """The stair cores near the prayer hall that climb to the roof (its
    level's and the next one's stairs, one per place): [(x, y, angle)]."""
    from shapely.geometry import Polygon
    arch = doc["arch"]
    ids = [lv["id"] for lv in arch["levels"]]
    i = ids.index(lid)
    ups = set(ids[i:i + 2])
    zone = poly.minimum_rotated_rectangle.buffer(30.0)
    out = []
    for st in doc.get("stairs") or []:
        if st.get("level") not in ups or len(st.get("corners") or []) < 3:
            continue
        try:
            g = Polygon(st["corners"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        c = g.centroid
        if not zone.contains(c):
            continue
        if any(math.hypot(c.x - x, c.y - y) < 5.0 for x, y, _a in out):
            continue
        r = g.minimum_rotated_rectangle
        q = list(r.exterior.coords)
        a = math.degrees(math.atan2(q[1][1] - q[0][1], q[1][0] - q[0][0]))
        out.append((c.x, c.y, a))
    return out


# ---- arches, storey, boundary wall ------------------------------------------------
def arches(doc) -> int:
    """Every outside door, window and opening (0.6 m wide or more) with a
    round head."""
    from . import project as PJ
    from .lookstyle import _outer_walls
    arch = doc["arch"]
    outer = _outer_walls(arch)
    ws = {w["id"]: w for w in arch["walls"]}
    jali = doc["settings"].get("jali_style", "cnc") or "cnc"
    n = 0
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or w["id"] not in outer or float(o["w"]) < 0.6:
            continue
        if o["kind"] != "door" and float(o["w"]) >= 0.6 and \
                o.get("grille") in (None, "", "ms"):
            o["grille"] = jali        # 3.64.67: the jali in the arches
        if o.get("head") == "arch":
            continue
        o["head"] = "arch"
        o["arch"] = "semi"
        try:
            PJ.fit_head(o)
        except Exception:  # noqa: BLE001
            pass
        n += 1
    return n


def crown(doc) -> int:
    """The hall's upper tiers as the perspectives show them (3.64.69):
    each tier wall over the prayer hall a row of tall arched jali
    openings, side by side, as high as the wall lets (up to its curved
    cornice) — on walls that have no openings yet."""
    from shapely.geometry import Point
    lid, poly = hall(doc)
    if poly is None:
        return 0
    arch = doc["arch"]
    levels = arch["levels"]
    i = next(k for k, lv in enumerate(levels) if lv["id"] == lid)
    if i + 1 >= len(levels):
        return 0
    up = levels[i + 1]
    zone = poly.minimum_rotated_rectangle.buffer(9.0)
    from .engine import model as M
    jali = doc["settings"].get("jali_style", "cnc") or "cnc"
    upw = {w["id"] for w in arch["walls"] if w["level"] == up["id"] or
           str(w["id"]).startswith("courtw-")}
    # (the arches made at an earlier look: made again as now)
    arch["openings"] = [o for o in arch["openings"] if not (
        o["wall"] in upw and o["kind"] == "void" and o.get("head") == "arch"
        and o.get("grille") and float(o.get("sill", 0) or 0) == 0.3)]
    busy = {o["wall"] for o in arch["openings"]}
    named = [Point(t["x"], t["y"]) for t in doc.get("texts") or []
             if t.get("level") == up["id"] and re.search(
                 r"BED|BATH|KITCHEN|LOUNGE|RESIDENCE|DRAWING|DINING|TOILET",
                 str(t.get("text", "")), re.I)]
    n = 0
    for w in arch["walls"]:
        court_ = str(w["id"]).startswith("courtw-")
        if (w["level"] != up["id"] and not court_) or w["id"] in busy or \
                w.get("kind", "line") != "line" or "a" not in w:
            continue
        m = Point((w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2)
        if not zone.contains(m) or math.dist(w["a"], w["b"]) < 2.0 or \
                any(p.distance(m) < 4.0 for p in named):
            continue
        hw = w.get("height", "level")
        hw = float(up["height"]) if hw == "level" else float(hw)
        h = hw - 0.3 - (0.3 if court_ else 0.55)   # (the cornice over it)
        if h < 1.2:
            continue
        # 3.64.71: arches side by side the wall's whole length, slim piers
        # between them and at the corners (the arches meet round the
        # corner), each in a deep wall with its arched frame
        L = math.dist(w["a"], w["b"])
        pier = 0.35
        w0 = 1.5 if hw < 5.0 else 1.9
        k = max(int(round((L - pier) / (w0 + pier))), 1)
        wd = (L - pier * (k + 1)) / k
        while k > 1 and wd < 0.8:
            k -= 1
            wd = (L - pier * (k + 1)) / k
        if wd < 0.6:
            continue
        w["t"] = max(float(w.get("t", 0.2)), 0.45)
        recs = [{"kind": "void", "wall": w["id"],
                 "pos": round(pier + wd / 2 + j * (wd + pier), 4),
                 "w": round(wd, 3), "h": round(h, 3), "sill": 0.3,
                 "swing": "left", "face": 1, "style": "", "head": "arch",
                 "arch": "semi", "grille": jali, "ring": "plain"}
                for j in range(k)]
        arch["openings"] += M.new_openings(arch["openings"], recs)
        n += k
    return n


def tall_arches(doc) -> int:
    """The prayer hall's own outside windows as tall as its storey lets
    (3.64.69): the arches rise to the curved cornice, tier over tier."""
    from shapely.geometry import Point
    lid, poly = hall(doc)
    if poly is None:
        return 0
    arch = doc["arch"]
    lv = next(x for x in arch["levels"] if x["id"] == lid)
    H = float(lv["height"])
    zone = poly.minimum_rotated_rectangle.buffer(6.0)
    ws = {w["id"]: w for w in arch["walls"] if w["level"] == lid
          and "a" in w}
    n = 0
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or o["kind"] not in ("window", "void") or \
                float(o["w"]) < 0.9:
            continue
        m = Point((w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2)
        if not zone.contains(m):
            continue
        sill = 0.0 if o["kind"] == "void" else \
            min(float(o.get("sill", 0.9) or 0.9), 0.6)
        h = round(H - sill - 0.75, 3)
        if o.get("head") == "arch":
            o["ring"] = "plain"          # 3.64.71: the arch's frame
        if h > float(o["h"]) + 0.1:
            o["sill"] = sill
            o["h"] = h
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
    try:                               # 3.64.68: the roof plan's tiers
        rep["tiers"] = apply_tiers(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("mosque.apply_tiers")
    rep["arched"] = arches(doc)
    try:
        rep["tall"] = tall_arches(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("mosque.tall_arches")
    try:
        rep["crown"] = crown(doc)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("mosque.crown")
    boundary(doc)
    return rep


def _migrate(doc) -> None:
    """3.64.66 made the look's minarets without the «auto-» mark (its
    modern ones): marked now."""
    for m in doc.get("minarets") or []:
        if m.get("cupola") == "modern" and \
                not str(m.get("id", "")).startswith("auto-"):
            m["id"] = "auto-" + str(m.get("id", ""))


def remove(doc) -> int:
    """The look's own minarets taken away (another kind of building)."""
    _migrate(doc)
    old = doc.get("minarets") or []
    doc["minarets"] = [m for m in old
                       if not str(m.get("id", "")).startswith("auto-")]
    return len(old) - len(doc["minarets"])


# ---- 3.64.68: the roof plan's tiers (stepped roofs, deep projecting slabs) ---------
TIER_STEP = 3.048                   # 10'-0" a tier over the one below
FASCIA = 0.45                       # the projecting slabs' depth


def _fill(lines, grow=0.35):
    """Closed shapes of a family of lines (double wall lines, a gap at a
    door): thickened, their insides filled, thinned back."""
    from shapely.geometry import MultiLineString, Polygon
    if not lines:
        return []
    g = MultiLineString(lines).buffer(grow, join_style=2)
    out = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type != "Polygon":
            continue
        f = Polygon(q.exterior).buffer(-grow, join_style=2)
        for r in getattr(f, "geoms", [f]):
            if r.geom_type == "Polygon" and r.area >= 6.0:
                out.append(r.simplify(0.03))
    return out


def _rings(lines, snap=0.03) -> list:
    """The closed rings the lines make end to end (an outline drawn as its
    sides, overlapping other outlines): [[(x, y)…]] of 6 m² and more."""
    from shapely.geometry import Polygon
    key = (lambda p: (round(p[0] / snap), round(p[1] / snap)))
    adj, pos = {}, {}
    for a, b in lines:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        pos.setdefault(ka, a)
        pos.setdefault(kb, b)
        adj.setdefault(ka, []).append(kb)
        adj.setdefault(kb, []).append(ka)
    seen, out = set(), []
    for k0 in adj:
        if k0 in seen or len(adj[k0]) != 2:
            continue
        ring, prev, cur, ok = [k0], None, k0, False
        while True:
            nx = [n for n in adj[cur] if n != prev]
            if len(adj[cur]) != 2 or not nx:
                break
            prev, cur = cur, nx[0]
            if cur == k0:
                ok = True
                break
            if cur in ring:
                break
            ring.append(cur)
        seen.update(ring)
        if ok and len(ring) >= 3:
            g = Polygon([pos[k] for k in ring]).buffer(0)
            if g.geom_type == "Polygon" and g.area >= 6.0:
                out.append(list(g.simplify(0.03).exterior.coords)[:-1])
    return out


def read_tiers(doc, lid, pl, wall_match) -> int:
    """At the import: a roof plan whose walls are drawn in several colours
    (each colour a tier — the plan's convention; the walls in the layer's
    own colour are the ordinary ones) and its dashed outlines (the
    projecting roof slabs): their lines kept as ``doc["tiers"][lid]``."""
    cols = pl.get("colors") or []
    dsh = pl.get("dashed") or []
    lay = pl["layers"]
    t = doc.setdefault("tiers", {})
    if not isinstance(t, dict):
        t = doc["tiers"] = {}
    t.pop(lid, None)
    n = _read_tiers_colours(doc, lid, pl, wall_match, cols, dsh, lay, t)
    if not n:
        try:
            n = _read_tiers_marks(doc, lid, pl, wall_match, t)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("mosque.read_tiers marks")
            n = 0
    return n


PARAPET_RX = re.compile(r"PARAPET|PARAPIT|ROOF\s*EDGE|FASCIA", re.I)
OTHER_ROOM_RX = re.compile(r"BED|BATH|KITCHEN|LOUNGE|TERRACE|TOILET|"
                           r"STORE|LOBBY|DRAWING|DINING|RESIDENCE|ROOM", re.I)


def _read_tiers_marks(doc, lid, pl, wall_match, t) -> int:
    """3.64.72: a roof plan drawn in one colour, each roof's level written
    in it («LEV.+45'-0"», the levels over the datum the floors' notes use):
    its wall / parapet lines, its level notes and its «MINARET» notes kept
    as ``doc["tiers"][lid]`` = {"mode": "marks", …} (two levels or more
    over the floor)."""
    from . import project as PJ
    lay = pl["layers"]
    marks, mins, others = [], [], []
    for tx in pl.get("texts") or []:
        s_ = str(tx.get("text", ""))
        v = PJ._feet_level(s_)
        if v is not None:
            marks.append([round(tx["x"], 4), round(tx["y"], 4),
                          round(v * 0.3048, 4)])
        elif re.search(r"MINAR", s_, re.I):
            mins.append([round(tx["x"], 4), round(tx["y"], 4)])
        elif OTHER_ROOM_RX.search(s_):
            others.append([round(tx["x"], 4), round(tx["y"], 4)])
    zs_ = sorted({m[2] for m in marks})
    if len(zs_) < 3 or zs_[-1] - zs_[0] < 5.0:   # (roofs a storey and more
        return 0                                  # apart: not a floor's)
    if sum(1 for z in zs_ if z >= zs_[0] + 2.5) < 2:
        return 0
    from shapely.geometry import MultiPoint, Point
    zone = MultiPoint([(m[0], m[1]) for m in marks] +
                      [tuple(m) for m in mins]).convex_hull.buffer(7.0)
    lines = []
    for s in pl["segs"]:
        name = str(lay[s[4]])
        if not (wall_match(name) or PARAPET_RX.search(name)):
            continue
        if not (zone.contains(Point(s[0], s[1])) or
                zone.contains(Point(s[2], s[3]))):
            continue
        lines.append([[round(s[0], 3), round(s[1], 3)],
                      [round(s[2], 3), round(s[3], 3)]])
    if len(lines) < 8:
        return 0
    t[lid] = {"mode": "marks", "lines": lines, "marks": marks,
              "minarets": mins, "others": others}
    return len({m[2] for m in marks})


_MP_CACHE = {}


def marks_plan(doc, lid):
    """3.64.72: the roof plan's masses from its level notes — the faces its
    lines close, each the level noted in it (a face noted twice over:
    shared out by the nearer note); a face with no note: a thin one (the
    projecting slab round a roof) the higher roof's beside it, a wide one
    the roof it shares the most edge with. {"masses": [(z, core polygons,
    overhang m)] low → high, "holes": [polygons] (the voids noted at the
    floor below), "minarets": [(x, y, side, angle)]} or None."""
    rec = (doc.get("tiers") or {}).get(lid)
    if not rec or rec.get("mode") != "marks":
        return None
    key = (lid, len(rec["lines"]), round(sum(m[2] for m in rec["marks"]), 3),
           round(sum(a[0] + b[1] for a, b in rec["lines"]), 2))
    hit = _MP_CACHE.get(key)
    if hit is not None:
        return hit
    from shapely.geometry import LineString, Point, MultiPoint
    from shapely.ops import polygonize, unary_union, voronoi_diagram
    ext = 0.8
    ls = []
    for a, b in rec["lines"]:
        L = math.dist(a, b)
        if L < 0.05:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        ls.append(LineString([(a[0] - ux * ext, a[1] - uy * ext),
                              (b[0] + ux * ext, b[1] + uy * ext)]))
    faces = [f for f in polygonize(unary_union(ls)) if f.area >= 0.3]
    zone = MultiPoint([(m[0], m[1]) for m in rec["marks"]]).convex_hull \
        .buffer(7.0)
    faces = [f for f in faces if zone.contains(f.representative_point())]
    others = [Point(*p) for p in rec.get("others") or []]
    faces = [f for f in faces if not any(f.contains(p) for p in others)]
    minp = [Point(*p) for p in rec.get("minarets") or []]
    mins, cells = [], []                      # cells: [poly, z or None]
    for f in faces:
        if any(f.contains(p) for p in minp) and f.area < 30.0:
            r = f.minimum_rotated_rectangle
            q = list(r.exterior.coords)
            e0, e1 = math.dist(q[0], q[1]), math.dist(q[1], q[2])
            a_ = math.degrees(math.atan2(q[1][1] - q[0][1], q[1][0] - q[0][0]))
            mins.append((r.centroid.x, r.centroid.y,
                         round(min(max((e0 + e1) / 2, 1.0), 4.0), 3), a_))
            continue
        ms = [m for m in rec["marks"] if f.contains(Point(m[0], m[1]))]
        zs = sorted({m[2] for m in ms})
        if len(zs) <= 1:
            cells.append([f, zs[0] if zs else None])
            continue
        vd = voronoi_diagram(MultiPoint([(m[0], m[1]) for m in ms]),
                             envelope=f.envelope.buffer(5.0))
        for c in getattr(vd, "geoms", [vd]):
            part = c.intersection(f)
            m_ = next((m for m in ms if c.contains(Point(m[0], m[1]))), None)
            for q in getattr(part, "geoms", [part]):
                if q.geom_type == "Polygon" and q.area >= 0.3 and m_:
                    cells.append([q, m_[2]])
    if not any(c[1] is not None for c in cells):
        return None

    def width(g):
        return 2.0 * g.area / max(g.length, 1e-6)
    for _ in range(12):                    # the faces with no note
        changed = False
        for c in cells:
            if c[1] is not None:
                continue
            nb = []
            for o in cells:
                if o is c or o[1] is None:
                    continue
                sh = c[0].boundary.intersection(o[0].buffer(0.05)).length
                if sh > 0.3:
                    nb.append((sh, o[1]))
            if not nb:
                continue
            c[1] = max(z for _s, z in nb) if width(c[0]) < 1.4 else \
                max(nb)[1]
            c.append("thin" if width(c[0]) < 1.4 else "wide")
            changed = True
        if not changed:
            break
    zs = sorted({c[1] for c in cells if c[1] is not None})
    if len(zs) < 2:
        return None
    lo = zs[0]
    holes, masses = [], []
    roofs = [z for z in zs if z > lo + 2.0] or zs
    floor_z = min(roofs)
    for z in zs:
        mine = [c for c in cells if c[1] == z]
        if z < floor_z - 2.0:              # a void down to the floor below
            holes += [c[0] for c in mine]
            continue
        core = [c[0] for c in mine if not (len(c) > 2 and c[2] == "thin")]
        thin = [c[0] for c in mine if len(c) > 2 and c[2] == "thin"]
        ws = sorted(width(g) for g in thin)
        ov = ws[len(ws) // 2] if ws else 0.6
        g = unary_union(core or thin)
        ps = [q for q in getattr(g, "geoms", [g])
              if q.geom_type == "Polygon" and q.area >= 1.0]
        if ps:
            masses.append((z, ps, round(min(max(ov, 0.3), 2.5), 3)))
    out = {"masses": masses, "holes": holes, "minarets": mins}
    _MP_CACHE.clear()
    _MP_CACHE[key] = out
    return out


def _read_tiers_colours(doc, lid, pl, wall_match, cols, dsh, lay, t) -> int:
    if len(cols) != len(pl["segs"]):
        return 0
    by = {}
    proj = []
    for s, c, d in zip(pl["segs"], cols, dsh or [False] * len(cols)):
        name = str(lay[s[4]])
        ln = [[round(s[0], 3), round(s[1], 3)], [round(s[2], 3),
                                                  round(s[3], 3)]]
        if d and re.search(r"PROJ|SLAB|CANTI|OVERHANG|ROOF", name, re.I):
            proj.append(ln)
        elif wall_match(name) and c is not None and not d:
            by.setdefault(tuple(c), []).append(ln)
    if len(by) < 3:                 # (the ordinary walls and 2+ tiers)
        return 0
    main = max(by, key=lambda c: len(by[c]))
    groups = [{"color": list(c), "lines": ls} for c, ls in by.items()
              if c != main and len(ls) >= 4]
    if len(groups) < 2:
        return 0
    t[lid] = {"groups": groups, "proj": proj}
    return len(groups)


def tier_plan(doc, lid):
    """[(rank, [polygons], top z, overhang m)] of the level's tiers — the
    colour nearest the middle the highest; each tier the area its lines
    close with the tiers inside it — or []."""
    from shapely.geometry import MultiLineString, Point
    from shapely.ops import unary_union
    from . import project as PJ
    rec = (doc.get("tiers") or {}).get(lid)
    arch = doc["arch"]
    i = next((k for k, lv in enumerate(arch["levels"]) if lv["id"] == lid),
             None)
    if rec and rec.get("mode") == "marks":
        mp = marks_plan(doc, lid)
        if not mp:
            return []
        return [(r, ps, z, ov) for r, (z, ps, ov) in enumerate(mp["masses"])]
    if not rec or i is None or "groups" not in rec or \
            "lines" not in (rec["groups"] or [{}])[0]:
        return []
    gl = [[tuple(map(tuple, ln)) for ln in g["lines"]] for g in rec["groups"]]
    mids = [[Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in ls]
            for ls in gl]
    allm = [p for ms in mids for p in ms]
    cx = sum(p.x for p in allm) / len(allm)
    cy = sum(p.y for p in allm) / len(allm)
    c = Point(cx, cy)
    order = sorted(range(len(gl)), key=lambda k: sum(
        p.distance(c) for p in mids[k]) / len(mids[k]))   # inner first
    regions = []
    acc_lines, prev = [], None
    for k in order:
        acc_lines += gl[k]
        f = unary_union(_fill(acc_lines)) if _fill(acc_lines) else None
        if f is None:
            continue
        reg = f if prev is None else f.difference(prev.buffer(0.02))
        prev = f if prev is None else unary_union([prev, f])
        ps = [q for q in getattr(reg, "geoms", [reg])
              if q.geom_type == "Polygon" and q.area >= 3.0]
        if ps:
            regions.append(ps)
    if len(regions) < 2:
        return []
    regions.reverse()                   # outer (lowest) first
    E = PJ.elevations(arch)[i]
    h = float(arch["levels"][i]["height"])
    # the projecting slabs: how far the dashed outlines stand off each tier
    pl_ = rec.get("proj") or []
    dm = [Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in pl_]
    out = []
    for r, ps in enumerate(regions):
        top = E if r == 0 else E + h + (r - 1) * TIER_STEP
        u = unary_union(ps)
        ds = sorted(u.exterior.distance(p) if u.geom_type == "Polygon"
                    else u.boundary.distance(p)
                    for p in dm if not u.buffer(-0.05).contains(p))
        ds = [d_ for d_ in ds if 0.15 <= d_ <= 3.0]
        ov = ds[len(ds) // 2] if ds else 0.6
        out.append((r, ps, top, round(min(max(ov, 0.3), 2.5), 3)))
    _ = MultiLineString
    return out


def apply_tiers(doc) -> dict:
    """The tiers made: the lowest tier's walls on the roof plan's level
    taken away (it is the roof of the floor under it), the higher tiers'
    walls raised a step each, that level's roofs cut off the lowest tier,
    the domes on the highest tier set on its top."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    from .engine import model as M
    arch = doc["arch"]
    rep = {"removed": 0, "raised": 0}
    arch["walls"] = [w for w in arch["walls"]
                     if not str(w.get("id", "")).startswith(
                         ("tierw-", "courtw-"))]
    for lid in list((doc.get("tiers") or {}).keys()):
        if (doc["tiers"][lid] or {}).get("mode") == "marks":
            try:
                rep.update(_apply_tiers_marks(doc, lid))
            except Exception:  # noqa: BLE001
                from .host import log_error
                log_error("mosque.apply_tiers marks")
            continue
        plan = tier_plan(doc, lid)
        if not plan:
            continue
        i = next(k for k, lv in enumerate(arch["levels"]) if lv["id"] == lid)
        h = float(arch["levels"][i]["height"])
        bounds = [(r, unary_union(ps).boundary) for r, ps, _z, _o in plan]
        gone = set()
        for w in arch["walls"]:
            if w["level"] != lid or "a" not in w:
                continue
            m = Point((w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2)
            best = min(bounds, key=lambda q: q[1].distance(m))
            if best[1].distance(m) > float(w.get("t", 0.2)) / 2 + 0.25:
                continue
            if best[0] == 0:
                gone.add(w["id"])
            elif best[0] >= 2:
                w["height"] = round(h + (best[0] - 1) * TIER_STEP, 3)
                rep["raised"] += 1
        if gone:
            arch["walls"] = [w for w in arch["walls"] if w["id"] not in gone]
            arch["openings"] = [o for o in arch["openings"]
                                if o["wall"] not in gone]
            rep["removed"] += len(gone)
        # this level's roofs off the lowest tier
        low = unary_union(plan[0][1]).buffer(0.05)
        keep, add = [], []
        for s in arch["structure"]:
            if s.get("type") == "slab" and s.get("level") == lid and \
                    s.get("roof"):
                try:
                    g = Polygon(s["corners"]).buffer(0).difference(low)
                except Exception:  # noqa: BLE001
                    keep.append(s)
                    continue
                pcs = [q for q in getattr(g, "geoms", [g])
                       if q.geom_type == "Polygon" and q.area > 0.5]
                for k, q in enumerate(pcs):
                    rec = dict(s, corners=[[round(x, 4), round(y, 4)] for
                                           x, y in list(q.exterior.coords)[:-1]],
                               holes=[])
                    if k == 0:
                        keep.append(rec)
                    else:
                        rec.pop("id", None)
                        add.append(rec)
                continue
            keep.append(s)
        arch["structure"] = keep
        if add:
            arch["structure"] += M.new_elements(arch["structure"], add)
        # the domes on the highest tier
        r_top, ps_top, _z, _o = plan[-1]
        top_u = unary_union(ps_top).buffer(0.3)
        for d in doc.get("domes") or []:
            if d.get("level") == lid and top_u.contains(Point(d["x"], d["y"])):
                d["z_off"] = round((r_top - 1) * TIER_STEP, 3)
    return rep


TIER_T = 0.23                       # the tiers' walls (9")


def _apply_tiers_marks(doc, lid) -> dict:
    """3.64.72: the tiers of a roof plan whose roofs' levels are written:
    the floor under it raised / lowered to the lowest roof's level (the
    prayer hall's height as drawn), each higher roof's walls made on its
    outline (where no higher roof stands) up to its level, the level's
    own roofs off the tiers, the voids noted at the floor below cut from
    its floor, the domes set on the roof under them."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    from .engine import model as M
    from . import project as PJ
    mp = marks_plan(doc, lid)
    rep = {"tiers_marks": 0}
    if not mp or not mp["masses"]:
        return rep
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    i = next(k for k, lv in enumerate(levels) if lv["id"] == lid)
    lo_z = mp["masses"][0][0]
    j = next((k for k in range(len(levels)) if k != i and
              abs(el[k] + float(levels[k]["height"]) - el[i]) < 0.02), None)
    if j is not None and 0.02 < abs(lo_z - el[i]) < 1.6:
        levels[j]["height"] = round(lo_z - el[j], 4)    # (as the roofs say)
        rep["hall_h"] = levels[j]["height"]
        el = PJ.elevations(arch)
    E = el[i]
    h = float(levels[i]["height"])
    tmpl = next((w for w in arch["walls"] if w.get("level") == lid), {})
    n = 0
    for k, (z, ps, _ov) in enumerate(mp["masses"]):
        if z <= E + 0.3:
            continue
        g = unary_union(ps)
        hi = [unary_union(p2) for z2, p2, _o in mp["masses"] if z2 > z + 0.1]
        higher = unary_union(hi).buffer(TIER_T) if hi else None
        inner = g.buffer(-TIER_T / 2, join_style=2)
        rings = []
        for q in getattr(inner, "geoms", [inner]):
            if q.geom_type != "Polygon":
                continue
            rings.append(q.exterior)
            rings += list(q.interiors)
        for r_ in rings:
            ln = r_ if higher is None else r_.difference(higher)
            for piece in getattr(ln, "geoms", [ln]):
                if piece.geom_type not in ("LineString", "LinearRing"):
                    continue
                cs = list(piece.simplify(0.05).coords)
                for a, b in zip(cs, cs[1:]):
                    if math.dist(a, b) < 0.4:
                        continue
                    n += 1
                    arch["walls"].append({
                        "kind": "line", "a": [round(a[0], 4), round(a[1], 4)],
                        "b": [round(b[0], 4), round(b[1], 4)], "t": TIER_T,
                        "type": "solid",
                        "cw_low": tmpl.get("cw_low", 0.9),
                        "cw_up": tmpl.get("cw_up", 0.6),
                        "cw_fill": tmpl.get("cw_fill", "glass"),
                        "grid": tmpl.get("grid", 1.5),
                        "tgrid": tmpl.get("tgrid", 1.5),
                        "height": round(z - E, 4), "base": 0.0,
                        "align": "centre", "side": 1, "level": lid,
                        "id": f"tierw-{lid}-{n}", "name": f"Tier wall {n}"})
    rep["tiers_marks"] = n
    # the level's own roofs off the tiers (each tier has its own roof)
    allu = unary_union([unary_union(ps) for _z, ps, _o in mp["masses"]] +
                       list(mp["holes"])).buffer(0.05)
    keep, add = [], []
    for s in arch["structure"]:
        if s.get("type") == "slab" and s.get("level") == lid and \
                s.get("roof"):
            try:
                g = Polygon(s["corners"]).buffer(0).difference(allu)
            except Exception:  # noqa: BLE001
                keep.append(s)
                continue
            pcs = [q for q in getattr(g, "geoms", [g])
                   if q.geom_type == "Polygon" and q.area > 0.5]
            for k, q in enumerate(pcs):
                rec = dict(s, corners=[[round(x, 4), round(y, 4)] for
                                       x, y in list(q.exterior.coords)[:-1]],
                           holes=[[[round(x, 4), round(y, 4)] for x, y in
                                   list(r_.coords)[:-1]]
                                  for r_ in q.interiors])
                if k == 0:
                    keep.append(rec)
                else:
                    rec.pop("id", None)
                    add.append(rec)
            continue
        keep.append(s)
    arch["structure"] = keep
    if add:
        arch["structure"] += M.new_elements(arch["structure"], add)
    # 3.64.74: the voids (the court) open down to the hall's floor: cut
    # from every slab over that floor — the hall's roof, this level's
    # floor, the roofs between — and walled all the way down (the court's
    # arcade runs from the hall's floor to the top roof)
    hi_ = j if j is not None else max(i - 1, 0)
    z_floor = el[hi_]
    for hp in mp["holes"]:
        for s in list(arch["structure"]):
            if s.get("type") != "slab" or not s.get("corners"):
                continue
            idx = next((k for k, lv_ in enumerate(levels)
                        if lv_["id"] == s.get("level")), None)
            if idx is None:
                continue
            ztop = el[idx] + (float(levels[idx]["height"])
                              if s.get("roof") else 0.0)
            if ztop <= z_floor + 0.3:
                continue
            try:
                P_ = Polygon(s["corners"]).buffer(0)
                holes_ = [Polygon(x).buffer(0) for x in s.get("holes") or []
                          if len(x) >= 3]
                if P_.is_empty or not P_.intersects(hp):
                    continue
                g = P_.difference(unary_union(holes_ + [hp]) if holes_
                                  else hp)
            except Exception:  # noqa: BLE001
                continue
            if g.is_empty:
                arch["structure"].remove(s)
                continue
            pcs_ = [q for q in getattr(g, "geoms", [g])
                    if q.geom_type == "Polygon" and q.area > 0.3]
            for k, q in enumerate(pcs_):
                rr = dict(s, corners=[[round(x, 4), round(y, 4)] for x, y in
                                      list(q.exterior.coords)[:-1]],
                          holes=[[[round(x, 4), round(y, 4)] for x, y in
                                  list(r_.coords)[:-1]]
                                 for r_ in q.interiors])
                if k == 0:
                    s.clear()
                    s.update(rr)
                else:
                    rr.pop("id", None)
                    add2 = arch.setdefault("_add2", [])
                    add2.append(rr)
            rep["voids"] = rep.get("voids", 0) + 1
        ring = hp.buffer(TIER_T / 2, join_style=2).exterior
        cs = list(ring.simplify(0.05).coords)
        hall_h = el[i] - el[hi_]
        for a_, b_ in zip(cs, cs[1:]):
            if math.dist(a_, b_) < 0.4 or hall_h < 1.0:
                continue
            n += 1
            arch["walls"].append({
                "kind": "line", "a": [round(a_[0], 4), round(a_[1], 4)],
                "b": [round(b_[0], 4), round(b_[1], 4)], "t": TIER_T,
                "type": "solid", "cw_low": 0.9, "cw_up": 0.6,
                "cw_fill": "glass", "grid": 1.5, "tgrid": 1.5,
                "height": round(hall_h, 4), "base": 0.0, "align": "centre",
                "side": 1, "level": levels[hi_]["id"],
                "id": f"courtw-{lid}-{n}", "name": f"Court wall {n}"})
    add2 = arch.pop("_add2", [])
    if add2:
        arch["structure"] += M.new_elements(arch["structure"], add2)
    # the domes on the roof under them
    for d in doc.get("domes") or []:
        if d.get("level") != lid:
            continue
        p = Point(d["x"], d["y"])
        zs = [z for z, ps, _o in mp["masses"]
              if unary_union(ps).buffer(0.3).contains(p)]
        if zs:
            d["z_off"] = round(max(zs) - (E + h), 3)
    return rep


def _court_holes(doc, lid):
    """The open courts the level's floor leaves (X-marked shafts ≥ 4 m²)."""
    from shapely.geometry import Polygon
    out = []
    for s in doc["arch"]["structure"]:
        if s.get("type") == "slab" and s.get("level") == lid and \
                not s.get("roof"):
            for h in s.get("shafts") or []:
                try:
                    g = Polygon(h).buffer(0)
                    if g.area >= 4.0:
                        out.append(g)
                except Exception:  # noqa: BLE001
                    pass
    return out


def groups(doc):
    """The tiers' roofs (the higher tiers', over their raised walls) and
    the deep projecting slabs round each tier."""
    if not (doc.get("look") or {}).get("mosque") or not doc.get("tiers"):
        return []
    from PySide6.QtGui import QVector3D
    from shapely.ops import unary_union
    from core.group import Group
    from core.mesh import Mesh
    from . import project as PJ
    from .engine import structure as S
    from .engine import walls as W
    from .host import KEY, level_layer
    out = []
    col = tuple((doc.get("look") or {}).get("trim") or (0.97, 0.96, 0.93))
    for lid, rec in (doc.get("tiers") or {}).items():
        plan = tier_plan(doc, lid)
        if not plan:
            continue
        lv = next(x for x in doc["arch"]["levels"] if x["id"] == lid)
        ch_ = list(_court_holes(doc, lid))
        mk_ = rec.get("mode") == "marks" if isinstance(rec, dict) else False
        if mk_:                          # 3.64.72: the voids noted
            ch_ += list((marks_plan(doc, lid) or {}).get("holes") or [])
        courts = unary_union(ch_) if ch_ else None
        E_ = PJ.elevations(doc["arch"])[[x["id"] for x in
                                         doc["arch"]["levels"]].index(lid)]
        mesh = Mesh()

        def solid(g, z0, z1):
            for q in getattr(g, "geoms", [g]):
                if q.geom_type != "Polygon" or q.area < 0.05:
                    continue
                outer = S._ccw([tuple(c) for c in
                                list(q.exterior.coords)[:-1]])
                holes = [list(reversed(S._ccw([tuple(c) for c in
                                               list(r.coords)[:-1]])))
                         for r in q.interiors]
                for f in W.solid({"outer": outer, "holes": holes}, z0, z1):
                    if isinstance(f, dict):
                        PJ._safe_add(mesh, [QVector3D(*c) for c in
                                            f["loop"]],
                                     [[QVector3D(*c) for c in hh]
                                      for hh in f["holes"]])
                    else:
                        PJ._safe_add(mesh, [QVector3D(*c) for c in f])
        # the higher tiers' own roofs (over the level's roof)
        higher = None
        for r, ps, top, ov in reversed(plan):
            g = unary_union(ps)
            if r >= 2 if not mk_ else top > E_ + 0.3:
                gg = g if courts is None else g.difference(courts)
                solid(gg, top - 0.15, top)
            # 3.64.69: the tier's edge a curved flare — the cornice sweeps
            # out from the wall face up to the projecting lip (as the
            # perspectives show), in slices; never over the tiers above
            rise = max(1.2 * ov, 0.9)
            N = 12              # 3.64.71: a cove (quarter ellipse) — up
            inner_ = g.buffer(-0.25, join_style=2)     # the wall's face,
            for k_ in range(N):                        # out to the lip
                th0 = (math.pi / 2) * k_ / N
                th1 = (math.pi / 2) * (k_ + 1) / N
                za = top - rise * (1 - math.sin(th0))
                zb = top - rise * (1 - math.sin(th1)) + \
                    (0.05 if k_ == N - 1 else 0.0)
                if zb - za < 0.01:
                    zb = za + 0.01
                off = ov * (1 - math.cos(th1))
                sl = g.buffer(max(off, 0.02), join_style=2).difference(inner_)
                if higher is not None:
                    sl = sl.difference(higher)
                if courts is not None:
                    sl = sl.difference(courts)
                solid(sl, za, zb)
            higher = g if higher is None else unary_union([higher, g])
        PJ._soften(mesh)
        g_ = Group(mesh, name=f"Tiers — roofs and projecting slabs · "
                   f"{lv['name']}")
        g_.component = False
        g_.material = {"color": col, "opacity": 1.0}
        g_.layer = level_layer(lv["name"])
        g_.ifc = {"class": "IfcSlab", "name": "Tier roofs"}
        g_.ext = {KEY: {"type": "tiers", "id": "tiers-" + lid,
                        "level": lid}}
        out.append(g_)
    try:
        out += frame_groups(doc, col)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("mosque.frame_groups")
    return out


def frame_groups(doc, col) -> list:
    """3.64.71: each arched opening of the prayer hall and its tiers
    framed as the perspectives show it — a deep plain arched surround
    standing proud of the wall's outside face (jambs and the arch)."""
    from PySide6.QtGui import QVector3D
    from shapely.geometry import Point
    from core.group import Group
    from core.mesh import Mesh
    from . import project as PJ
    from .engine import structure as S
    from .host import KEY
    lid, poly = hall(doc)
    if poly is None:
        return []
    arch = doc["arch"]
    ids = [lv["id"] for lv in arch["levels"]]
    i = ids.index(lid)
    lvls = set(ids[i:i + 2])
    el = PJ.elevations(arch)
    zone = poly.minimum_rotated_rectangle.buffer(9.0)
    cen = poly.centroid
    ws = {w["id"]: w for w in arch["walls"] if w["level"] in lvls
          and "a" in w and zone.contains(Point(
              (w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2))}
    mesh = Mesh()
    n = 0
    F, D = 0.16, 0.20                       # frame width, its depth
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or o.get("head") != "arch" or float(o["w"]) < 0.6:
            continue
        a, b = w["a"], w["b"]
        L = math.dist(a, b)
        if L < 0.1:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if (mx + nx - cen.x) ** 2 + (my + ny - cen.y) ** 2 < \
                (mx - nx - cen.x) ** 2 + (my - ny - cen.y) ** 2:
            nx, ny = -nx, -ny               # (the face away from the hall)
        t = float(w.get("t", 0.2))
        z0 = el[ids.index(w["level"])] + float(w.get("base", 0.0) or 0.0)
        wd, h = float(o["w"]), float(o["h"])
        s0, s1 = float(o["pos"]) - wd / 2, float(o["pos"]) + wd / 2
        zs = z0 + float(o.get("sill", 0.0) or 0.0)
        zt = zs + h
        zsp = max(zs + 0.05, zt - wd / 2)
        inner = S.arch_pts(s0, s1, zsp, zt, 14, "semi")      # s1 → s0
        outer = S.arch_pts(s0 - F, s1 + F, zsp, zt + F, 14, "semi")
        prof = [(s1 + F, zs)] + outer + [(s0 - F, zs), (s0, zs)] + \
            list(reversed(inner)) + [(s1, zs)]

        def P(sz, off):
            return QVector3D(a[0] + ux * sz[0] + nx * off,
                             a[1] + uy * sz[0] + ny * off, sz[1])
        f0, f1 = t / 2, t / 2 + D
        PJ._safe_add(mesh, [P(q, f1) for q in prof])
        PJ._safe_add(mesh, [P(q, f0) for q in reversed(prof)])
        for q0, q1 in zip(prof, prof[1:] + prof[:1]):
            PJ._safe_add(mesh, [P(q0, f0), P(q1, f0), P(q1, f1),
                                P(q0, f1)])
        n += 1
    if not n:
        return []
    PJ._soften(mesh)
    g = Group(mesh, name=f"Arch surrounds ({n})")
    g.component = False
    g.material = {"color": col, "opacity": 1.0}
    g.ext = {KEY: {"type": "arch_frames", "id": "arch-frames",
                   "level": lid}}
    return [g]
