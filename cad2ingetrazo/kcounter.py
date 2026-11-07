# SPDX-License-Identifier: GPL-3.0-or-later
"""Kitchen counters read from the CAD plan — IngeTrazo library cabinets.

In a room named KITCHEN (COOKING, PANTRY…) the plan draws its worktop as a
line ~2'-0" in from the walls (on whatever layer). That line, parallel to
a wall side of the room 0.45–0.80 m in from it, is the counter's front:

* the strip between it and the wall gets the library's lower cabinets
  (fitted to the run, the counter's depth), the sink / hob / fridge blocks
  the plan sets on it kept as theirs (sink, cooker, fridge models);
* two runs meeting at a corner (an L, a U) get a lower corner cabinet in
  the corner square;
* over each run, upper (wall) cabinets 0.35 m deep from 1.45 m up, clear
  of the windows, of the door openings and over the hob and fridge;
* a box standing free in the kitchen (a closed rectangle 0.5–1.6 m wide,
  not against a wall) named ISLAND / COOKING by a text in it, or with the
  burners of a hob drawn on it, is a cooking island: lower cabinets on
  both of its long sides' depth and the library's cooker set where the
  burners are; a box named SERVING / BAR / BREAKFAST is a counter
  (cabinets, no cooker).

The pieces go in ``doc["furniture"]`` (``src: "fitout"``, kinds
``cabinet``, ``corner_cabinet``, ``wall_cabinet``, ``island``, ``ksink``,
``stove``, ``fridge``) — each replaced from the library like any fixture
(right-click ▸ Replace every …).

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

import math
import re

KITCHEN_ROOM = re.compile(r"KITCHEN|KICHEN|COOKING|COCKING|PANTRY|"
                          r"KITCHENETTE|\bK\.?\s?T\.?\s?N\b", re.I)
ISLAND_WORDS = re.compile(r"ISLAND|COOKING|COCKING|\bHOB\b|COOK", re.I)
SERVING_WORDS = re.compile(r"SERVING|\bBAR\b|BREAKFAST|COUNTER", re.I)
NOT_COUNTER_LAYER = re.compile(r"WALL|COLUMN|\bCOL\b|S-COL|DIM|HATCH|"
                               r"TEXT|GRID|AXIS|TREE|GREEN|LANDSC", re.I)
BASE_H = 0.86                 # the worktop's top less its own thickness
UPPER_Z, UPPER_D, UPPER_H = 1.45, 0.35, 0.70
BASE_WORDS = ["lower cabinet", "base cabinet", "wood lower cabinet",
              "kitchen cabinet"]
CORNER_WORDS = ["lower corner cabinet", "corner lower cabinet",
                "corner cabinet"]
UPPER_WORDS = ["upper cabinet", "wall cabinet", "hanging cabinet",
               "upper kitchen cabinet", "kitchen wall cabinet"]
HOB_WORDS = ["cooker", "cooktop", "hob", "gas hob", "induction hob",
             "stove", "kitchen stove"]
SINK_WORDS = ["kitchen sink", "sink cabinet", "sink"]


#: kitchen cabinet styles from IngeTrazo's library: {style: (label,
#: {kind: [name words, best first]})} — a kind left out keeps the
#: standard one
STYLES = {
    "standard": ("Standard (white)", {}),
    "wood": ("Wood", {
        "cabinet": ["wood lower cabinet"],
        "island": ["wood lower cabinet"],
        "corner_cabinet": ["wood corner cabinet"],
        "wall_cabinet": ["wood upper cabinet"],
        "ksink": ["wood cabinet with sink"]}),
    "gray": ("Gray", {
        "cabinet": ["gray cabinet"],
        "island": ["gray cabinet"],
        "wall_cabinet": ["gray upper cabinet"],
        "ksink": ["gray cabinet with basin"]}),
    "red": ("Red", {
        "cabinet": ["red cabinet"],
        "island": ["red cabinet"],
        "ksink": ["red cabinet with basin"]}),
    "glass": ("Glass-door uppers", {
        "wall_cabinet": ["glass door cabinet", "wood glass door cabinet"]}),
}
KITCHEN_KINDS = ("cabinet", "island", "corner_cabinet", "wall_cabinet",
                 "ksink")


def style_entries(entries, style) -> dict:
    """{kind: library entry} for the kitchen ``style`` (only the kinds the
    style changes, and that the library has)."""
    out = {}
    for kind, words in (STYLES.get(style) or ("", {}))[1].items():
        e = _pick(entries, words, avoid=("corner",) if kind not in (
            "corner_cabinet",) else ())
        if e is not None:
            out[kind] = e
    return out


def _pick(entries, words, cat="Kitchen", avoid=()):
    for w in words:
        for e in entries:
            if cat and e.get("cat") != cat:
                continue
            nm = str(e.get("name", "")).strip().lower()
            if nm == w and not any(a in nm for a in avoid):
                return e
    for w in words:
        for e in entries:
            if cat and e.get("cat") != cat:
                continue
            nm = str(e.get("name", "")).lower()
            if w in nm and not any(a in nm for a in avoid):
                return e
    if cat:
        return _pick(entries, words, None, avoid)
    return None


def _counter_layer(name) -> bool:
    return not NOT_COUNTER_LAYER.search(str(name or ""))


def _merge(ivs, gap=0.15):
    out = []
    for a, b in sorted(ivs):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _cut(spans, lo, hi):
    out = []
    for s0, s1 in spans:
        if hi <= s0 or lo >= s1:
            out.append((s0, s1))
            continue
        if lo > s0:
            out.append((s0, lo))
        if hi < s1:
            out.append((hi, s1))
    return out


def _fill(run, target=0.6, lo=0.3):
    """Widths filling ``run`` (m): ~60 cm cabinets, the rest shared."""
    if run < lo:
        return []
    k = max(int(round(run / target)), 1)
    return [run / k] * k


def runs_of(poly, segs, walls=None, boxes=()):
    """The counter runs along the room's sides: [{"a", "b", "u", "n",
    "L", "d" depth, "spans": [(s0, s1)]}] — n into the room. ``walls``
    (shapely): only the sides a wall stands on; ``boxes``: the islands /
    blocks whose own lines are no counter's front."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.geometry.polygon import orient
    from . import furnish as FU
    P = orient(Polygon(poly.exterior).simplify(0.03), 1.0)
    inside = P.buffer(0.03)
    out = []
    for a, b in FU._sides(P):
        L = math.dist(a, b)
        if L < 0.6:
            continue
        if walls is not None and not walls.is_empty:
            side_ = LineString([a, b])
            if side_.intersection(walls.buffer(0.15)).length < 0.5 * L:
                continue                       # an open side: no wall
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-u[1], u[0])                      # CCW: the room on the left
        ivs, ds = [], []
        for x0, y0, x1, y1 in segs:
            sl = math.hypot(x1 - x0, y1 - y0)
            if sl < 0.3:
                continue
            v = ((x1 - x0) / sl, (y1 - y0) / sl)
            if abs(u[0] * v[1] - u[1] * v[0]) > 0.05:
                continue
            if not (inside.contains(Point(x0, y0)) and
                    inside.contains(Point(x1, y1))):
                continue
            if any(bx.buffer(0.03).contains(Point((x0 + x1) / 2,
                                                  (y0 + y1) / 2))
                   and bx.exterior.distance(Point((x0 + x1) / 2,
                                                  (y0 + y1) / 2)) < 0.03
                   for bx in boxes):
                continue                       # an island's own side
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            d = (mx - a[0]) * n[0] + (my - a[1]) * n[1]
            if not 0.45 <= d <= 0.80:
                continue
            t0 = (x0 - a[0]) * u[0] + (y0 - a[1]) * u[1]
            t1 = (x1 - a[0]) * u[0] + (y1 - a[1]) * u[1]
            t0, t1 = max(min(t0, t1), 0.0), min(max(t0, t1), L)
            if t1 - t0 < 0.3:
                continue
            ivs.append((t0, t1))
            ds.append(d)
        if not ivs:
            continue
        ds.sort()
        d = ds[len(ds) // 2]
        spans = [(s0, s1) for s0, s1 in _merge(ivs) if s1 - s0 >= 0.6]
        if spans:
            out.append({"a": a, "b": b, "u": u, "n": n, "L": L, "d": d,
                        "spans": spans})
    # a run's end at a corner where another run starts: the counter goes
    # into the corner (the line drawn stops at the other run's front)
    for r in out:
        for q in out:
            if q is r:
                continue
            for end, pt in ((0, r["a"]), (1, r["b"])):
                for qpt in (q["a"], q["b"]):
                    if math.dist(pt, qpt) > 0.05:
                        continue
                    if abs(r["u"][0] * q["u"][0] + r["u"][1] * q["u"][1]) \
                            > 0.2:
                        continue
                    qs = q["spans"]
                    q_at = qs[0][0] <= r["d"] + 0.25 if math.dist(
                        qpt, q["a"]) < 0.05 else \
                        qs[-1][1] >= q["L"] - r["d"] - 0.25
                    if not q_at:
                        continue           # the other run stops short of it
                    sp = r["spans"]
                    if end == 0 and sp[0][0] <= q["d"] + 0.25:
                        sp[0] = (0.0, sp[0][1])
                        r.setdefault("corners", []).append((0, q))
                    if end == 1 and sp[-1][1] >= r["L"] - q["d"] - 0.25:
                        sp[-1] = (sp[-1][0], r["L"])
                        r.setdefault("corners", []).append((1, q))
    return out


def _xy(r, s, off):
    return (r["a"][0] + r["u"][0] * s + r["n"][0] * off,
            r["a"][1] + r["u"][1] * s + r["n"][1] * off)


def islands_of(poly, segs, texts, short_segs, walls=None):
    """Free-standing boxes in the kitchen: [(rect polygon, "island" /
    "serving", hob centre or None)]."""
    from shapely.geometry import LineString, Point
    from shapely.ops import polygonize, unary_union
    lines = [LineString([(x0, y0), (x1, y1)]) for x0, y0, x1, y1 in segs
             if math.hypot(x1 - x0, y1 - y0) >= 0.2]
    if not lines:
        return []
    try:
        polys = list(polygonize(unary_union(lines)))
    except Exception:  # noqa: BLE001
        return []
    wall = walls if walls is not None and not walls.is_empty \
        else poly.exterior
    out = []
    for pg in sorted(polys, key=lambda g: -g.area):
        if not 0.4 <= pg.area <= 9.0:
            continue
        mrr = pg.minimum_rotated_rectangle
        if pg.area < 0.88 * mrr.area:
            continue
        cs = list(mrr.exterior.coords)[:-1]
        e1, e2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        sh, lg = min(e1, e2), max(e1, e2)
        if not (0.45 <= sh <= 1.6 and 0.8 <= lg <= 5.0):
            continue
        c = pg.centroid
        if not poly.buffer(0.6).contains(c):
            continue
        if pg.distance(wall) < 0.3:
            continue                         # against a wall: a counter run
        if any(o[0].buffer(0.05).contains(c) or pg.buffer(0.05).contains(
                o[0].centroid) for o in out):
            continue                         # a box in a box already taken
        word = None
        for t in texts:
            q = Point(float(t["x"]), float(t["y"]))
            if pg.buffer(0.3).contains(q):
                tx = str(t.get("text", ""))
                if ISLAND_WORDS.search(tx):
                    word = "island"
                    break
                if SERVING_WORDS.search(tx):
                    word = "serving"
        burners = [p for p in short_segs if pg.contains(Point(p))]
        hob = None
        if len(burners) >= 16:
            hob = (sum(p[0] for p in burners) / len(burners),
                   sum(p[1] for p in burners) / len(burners))
            word = word or "island"
        if word is None:
            continue
        out.append((pg, word, hob if word == "island" else None))
    return out


KINDS = ("cabinet", "corner_cabinet", "wall_cabinet", "island")


def clear(doc, lid) -> int:
    """The kitchen pieces made before on level ``lid``: gone (their
    number)."""
    fs = doc.get("furniture") or []
    keep = [f for f in fs if not (f.get("level") == lid and f.get("src")
                                  == "fitout" and f.get("kc"))]
    doc["furniture"] = keep
    return len(fs) - len(keep)


def fit(doc, lid, pl, rooms, entries) -> int:
    """The kitchens of level ``lid`` fitted from the plan ``pl``. The
    number of pieces placed."""
    from shapely.geometry import LineString, Point, Polygon
    from . import fitout as FO
    from . import furnish as FU
    lay = pl.get("layers") or []
    segs = []
    for s in pl.get("segs") or ():
        try:
            ly = lay[int(s[4])] if isinstance(s[4], int) else s[4]
        except (IndexError, TypeError, ValueError):
            ly = ""
        if _counter_layer(ly):
            segs.append((float(s[0]), float(s[1]), float(s[2]),
                         float(s[3])))
    short_pts = [((x0 + x1) / 2, (y0 + y1) / 2) for x0, y0, x1, y1 in segs
                 if math.hypot(x1 - x0, y1 - y0) < 0.08]
    texts = list(pl.get("texts") or ())
    base_e = _pick(entries, BASE_WORDS, avoid=("corner", "sink"))
    if base_e is None:
        return 0
    corner_e = _pick(entries, CORNER_WORDS) or base_e
    upper_e = _pick(entries, UPPER_WORDS, avoid=("corner",))
    hob_e = _pick(entries, HOB_WORDS)
    sink_e = _pick(entries, SINK_WORDS)
    fridge_e = FU.pick("fridge", 0.7, 0.7, entries, {})
    openings = _openings(doc, lid)
    try:
        walls = FO._wall_union(doc, lid)
    except Exception:  # noqa: BLE001
        walls = None
    # the ones placed by hand (not the CAD blocks read as furniture)
    have = [f for f in doc.get("furniture") or [] if f["level"] == lid
            and f.get("src") != "fitout" and not f.get("cad")]
    KINDS_ = ("cabinet", "corner_cabinet", "wall_cabinet", "island",
              "ksink", "stove", "fridge")
    n = 0
    for r in rooms:
        if not KITCHEN_ROOM.search(str(r.get("name", ""))):
            continue
        poly = r["poly"]
        if poly.geom_type != "Polygon":
            poly = max(getattr(poly, "geoms", [poly]), key=lambda g: g.area)
        if any(poly.contains(Point(f["x"], f["y"])) and f.get("kind") in (
                "cabinet", "corner_cabinet", "island") for f in have):
            continue                       # the user's own cabinets stay
        # the CAD's kitchen blocks read as furniture: this fit-out's own
        # cabinets, sink, cooker and fridge take their place
        doc["furniture"] = [f for f in doc.get("furniture") or [] if not (
            f.get("level") == lid and f.get("cad") and f.get("src") !=
            "fitout" and f.get("kind") in KINDS_ and
            poly.buffer(0.3).contains(Point(f["x"], f["y"])))]
        mine = [s for s in segs if poly.buffer(0.8).intersects(
            LineString([(s[0], s[1]), (s[2], s[3])]))]
        isl = islands_of(poly, mine, texts, short_pts, walls)
        blocks = _blocks(pl, poly, texts)
        runs = runs_of(poly, mine, walls, [b[0] for b in isl])
        for k_r, rn in enumerate(runs):
            d = rn["d"]
            strip = Polygon([rn["a"], rn["b"], _xy(rn, rn["L"], d),
                             _xy(rn, 0.0, d)])
            spans = list(rn["spans"])
            corner_ends = [e for e, _q in rn.get("corners") or []]
            # the corner square: one run's (the first of the pair) — a
            # corner cabinet; the other run stops at its side
            for end, q in rn.get("corners") or []:
                mine_corner = id(rn) < id(q)
                lo, hi = (0.0, q["d"]) if end == 0 else \
                    (rn["L"] - q["d"], rn["L"])
                spans = _cut(spans, lo, hi)
                if mine_corner:
                    cx, cy = _xy(rn, (lo + hi) / 2, d / 2)
                    # square with the runs: its back to this run's wall
                    bx, by = -rn["n"][0], -rn["n"][1]
                    _rec(FO, doc, lid, corner_e, "corner_cabinet", cx,
                                 cy, FU.back_to(bx, by), r,
                                 fit=[q["d"], d], fit_free=True,
                                 fit_h=BASE_H)
                    n += 1
            # the doors in this wall: no cabinet in front of them
            for (ox, oy), ow, kind in openings:
                off = (ox - rn["a"][0]) * rn["n"][0] + \
                    (oy - rn["a"][1]) * rn["n"][1]
                t = (ox - rn["a"][0]) * rn["u"][0] + \
                    (oy - rn["a"][1]) * rn["u"][1]
                if abs(off) < 0.4 and kind == "door":
                    spans = _cut(spans, t - ow / 2 - 0.05, t + ow / 2 + 0.05)
            # the sink / hob / fridge the plan sets on the counter
            busy, hob_at, fridge_at = [], [], []
            for bpoly, kind in blocks:
                if bpoly.intersection(strip).area < 0.5 * bpoly.area:
                    continue
                c = bpoly.centroid
                t = (c.x - rn["a"][0]) * rn["u"][0] + \
                    (c.y - rn["a"][1]) * rn["u"][1]
                cs = list(bpoly.minimum_rotated_rectangle.exterior.coords)
                w_ = max(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
                w_ = min(max(w_, 0.6), 1.2)
                e_ = {"ksink": sink_e, "stove": hob_e,
                      "fridge": fridge_e}.get(kind)
                if e_ is None:
                    continue
                spans = _cut(spans, t - w_ / 2, t + w_ / 2)
                busy.append((t - w_ / 2, t + w_ / 2))
                px, py = _xy(rn, t, d / 2)
                _rec(FO, doc, lid, e_, kind, px, py,
                             FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                             fit=[w_, d], fit_free=kind != "fridge")
                n += 1
                if kind == "stove":
                    hob_at.append((t - w_ / 2, t + w_ / 2))
                if kind == "fridge":
                    fridge_at.append((t - w_ / 2, t + w_ / 2))
            for s0, s1 in spans:
                ws = _fill(s1 - s0)
                s = s0
                for w_ in ws:
                    px, py = _xy(rn, s + w_ / 2, d / 2)
                    _rec(FO, doc, lid, base_e, "cabinet", px, py,
                                 FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                                 fit=[w_, d], fit_free=True,
                                 fit_h=BASE_H)
                    n += 1
                    s += w_
            # the upper cabinets: over the run, clear of the windows, the
            # doors, the hob and the fridge
            if upper_e is None:
                continue
            up = list(_merge(rn["spans"]))
            for (ox, oy), ow, kind in openings:
                off = (ox - rn["a"][0]) * rn["n"][0] + \
                    (oy - rn["a"][1]) * rn["n"][1]
                t = (ox - rn["a"][0]) * rn["u"][0] + \
                    (oy - rn["a"][1]) * rn["u"][1]
                if abs(off) < 0.4:
                    up = _cut(up, t - ow / 2 - 0.05, t + ow / 2 + 0.05)
            for lo, hi in hob_at + fridge_at:
                up = _cut(up, lo, hi)
            for end in corner_ends:          # the corner: the other run's
                q = next(q_ for e_, q_ in rn["corners"] if e_ == end)
                if id(rn) > id(q):
                    up = _cut(up, 0.0, UPPER_D) if end == 0 else \
                        _cut(up, rn["L"] - UPPER_D, rn["L"])
            for s0, s1 in up:
                s = s0
                for w_ in _fill(s1 - s0, 0.6, 0.3):
                    px, py = _xy(rn, s + w_ / 2, UPPER_D / 2)
                    _rec(FO, doc, lid, upper_e, "wall_cabinet", px, py,
                                 FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                                 fit=[w_, UPPER_D], fit_free=True,
                                 fit_h=UPPER_H, zoff=UPPER_Z)
                    n += 1
                    s += w_
        # the island / serving counter
        for pg, word, hob in isl:
            mrr = pg.minimum_rotated_rectangle
            cs = list(mrr.exterior.coords)[:-1]
            if math.dist(cs[0], cs[1]) >= math.dist(cs[1], cs[2]):
                p0, p1, p2 = cs[0], cs[1], cs[2]
            else:
                p0, p1, p2 = cs[1], cs[2], cs[3]
            L = math.dist(p0, p1)
            D = math.dist(p1, p2)
            u = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
            nv = ((p2[0] - p1[0]) / D, (p2[1] - p1[1]) / D)
            c = pg.centroid
            # its front (the cabinet doors) toward the kitchen's counter —
            # the cook's side; else toward the room's middle
            tgt = None
            for rn in runs:
                m_ = _xy(rn, rn["L"] / 2, rn["d"])
                dd = Point(m_).distance(c)
                if tgt is None or dd < tgt[0]:
                    tgt = (dd, m_)
            if tgt is None:
                rc = poly.centroid
                tgt = (0.0, (rc.x, rc.y))
            fx, fy = tgt[1][0] - c.x, tgt[1][1] - c.y
            if fx * nv[0] + fy * nv[1] < 0:
                nv = (-nv[0], -nv[1])         # nv: toward the front
            spans = [(0.0, L)]
            hob_t = None
            if hob is not None and hob_e is not None:
                hob_t = (hob[0] - p0[0]) * u[0] + (hob[1] - p0[1]) * u[1]
                hw = min(0.9, L)
                hob_t = min(max(hob_t, hw / 2), L - hw / 2)
                spans = _cut(spans, hob_t - hw / 2, hob_t + hw / 2)
                hx = c.x + u[0] * (hob_t - L / 2)
                hy = c.y + u[1] * (hob_t - L / 2)
                _rec(FO, doc, lid, hob_e, "stove", hx, hy,
                             FU.back_to(-nv[0], -nv[1]), r,
                             fit=[hw, D], fit_free=True, island=True)
                n += 1
            for s0, s1 in spans:
                s = s0
                for w_ in _fill(s1 - s0, 0.6, 0.25):
                    t = s + w_ / 2
                    px = c.x + u[0] * (t - L / 2)
                    py = c.y + u[1] * (t - L / 2)
                    _rec(FO, doc, lid, base_e, "island", px, py,
                                 FU.back_to(-nv[0], -nv[1]), r,
                                 fit=[w_, D], fit_free=True, fit_h=BASE_H,
                                 word=word)
                    n += 1
                    s += w_
    return n


def _rec(FO, *a, **kw):
    kw["kc"] = True
    return FO._furn_rec(*a, **kw)


def _openings(doc, lid):
    """The level's doors and windows: [((x, y) middle, width, kind)]."""
    from .engine import walls as W
    arch = doc["arch"]
    byid = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    out = []
    for o in arch["openings"]:
        w = byid.get(o.get("wall"))
        if w is None or w.get("kind", "line") != "line" or "a" not in w:
            continue
        c = W.centre(w)
        p0, p1 = tuple(c.p0), tuple(c.p1)
        L = math.dist(p0, p1)
        if L < 1e-6:
            continue
        t = float(o["pos"])
        kind = "door" if o.get("kind") in ("door", "void") or float(
            o.get("sill", 0.0) or 0.0) < 0.3 else "window"
        out.append(((p0[0] + (p1[0] - p0[0]) * t / L,
                     p0[1] + (p1[1] - p0[1]) * t / L), float(o["w"]), kind))
    return out


def _blocks(pl, poly, texts):
    """The plan's blocks in the kitchen with what they are: [(polygon,
    "ksink" / "stove" / "fridge")]."""
    from shapely.geometry import Point, Polygon
    from . import furnish as FU
    out = []
    for ins in pl.get("inserts") or ():
        cs = ins.get("corners")
        if not cs or len(cs) < 3:
            continue
        try:
            bp = Polygon(cs).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if bp.area < 0.05 or not poly.buffer(0.3).contains(bp.centroid):
            continue
        lx, ly = (ins.get("ldim") or [0, 0])[:2]
        L_, W_ = max(lx, ly), min(lx, ly)
        kind = None
        try:
            kind = FU.classify(str(ins.get("name", "")),
                               str(ins.get("layer", "")), L_, W_, "kitchen")
        except Exception:  # noqa: BLE001
            kind = None
        if kind not in ("ksink", "stove", "fridge"):
            kind = None
            for t in texts:
                if bp.buffer(0.25).contains(Point(float(t["x"]),
                                                  float(t["y"]))):
                    tx = str(t.get("text", "")).upper()
                    if re.search(r"\bFR\b|FRIDGE|REF", tx):
                        kind = "fridge"
                    elif re.search(r"SINK", tx):
                        kind = "ksink"
                    elif re.search(r"HOB|STOVE|COOK|BURNER", tx):
                        kind = "stove"
            nm = str(ins.get("name", "")).upper()
            if kind is None and re.search(r"\bREF|FRIDGE|FRIG", nm):
                kind = "fridge"
            if kind is None and 0.6 <= L_ <= 1.4 and 0.4 <= W_ <= 0.7:
                kind = "ksink"            # a bowl block on the counter
        if kind:
            out.append((bp, kind))
    sinks = [o for o in out if o[1] == "ksink"]
    if len(sinks) > 1:                    # one sink: the biggest bowl block
        big = max(sinks, key=lambda o: o[0].area)
        out = [o for o in out if o[1] != "ksink" or o is big]
    return out
