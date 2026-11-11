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
OVEN_WORDS = re.compile(r"\bMV\b|\bOV\b|OVEN|MICRO|M/W|\bMW\b", re.I)
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
SINK_WORDS = ["sink", "kitchen sink", "sink cabinet"]


#: kitchen cabinet styles from IngeTrazo's library: {style: (label,
#: {kind: [name words, best first]})} — a kind left out keeps the
#: standard one
STYLES = {
    "standard": ("Standard (white)", {}),
    "wood": ("Wood", {
        "cabinet": ["wood lower cabinet"],
        "island": ["wood lower cabinet"],
        "wall_cabinet": ["wood upper cabinet"]}),
    "gray": ("Gray", {
        "cabinet": ["gray cabinet"],
        "island": ["gray cabinet"],
        "wall_cabinet": ["gray upper cabinet"]}),
    "red": ("Red", {
        "cabinet": ["red cabinet"],
        "island": ["red cabinet"],
        }),
    "glass": ("Glass-door uppers", {
        "wall_cabinet": ["glass door cabinet", "wood glass door cabinet"]}),
}
KITCHEN_KINDS = ("cabinet", "island", "corner_cabinet", "wall_cabinet",
                 "ksink", "upper_corner")
#: the library's L corner units (3.63): their back corner is the model's
#: (+X, +Y) one, the diagonal door at (−X, −Y) — set with that corner in
#: the room's corner. The lower one a 5-sided box, the upper one an L of
#: 36 cm deep arms.
LOWER_CORNER_KEYS = ("online:blendswap-cc-0-154",)
UPPER_CORNER_KEYS = ("online:blendswap-cc-0-173",)
#: the L units' arms, as fractions of their box: (the arm across the
#: model's X — its depth along the +X wall —, the arm across Y). Scaled
#: so each arm is as deep as the run it meets (no step at the joint)
LOWER_ARMS = (60.4 / 81.0, 48.3 / 82.3)
UPPER_ARMS = (35.0 / 81.0, 36.0 / 81.0)


def corner_fit(arms, own, other, d_own=None, d_other=None) -> dict:
    """An L corner unit in the corner of runs ``own`` (it places it) and
    ``other``: its turn, fit [X, Y] and how much of each run it takes.
    The unit's X side lies along the wall at its back (+Y), Y along the
    +X wall; the run along the back wall meets its −X face (the Y arm's
    depth), the other its −Y face (the X arm's)."""
    d_own = own["d"] if d_own is None else d_own
    d_other = other["d"] if d_other is None else d_other
    rot, swapped = corner_rot(own, other)
    d_y, d_x = (d_other, d_own) if swapped else (d_own, d_other)
    X = min(max(d_x / arms[0], 0.6), 1.3)
    Y = min(max(d_y / arms[1], 0.6), 1.3)
    return {"rot": rot, "fit": [X, Y],
            "own": Y if swapped else X, "other": X if swapped else Y,
            "off": X / 2 if swapped else Y / 2}


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


def _modules(spans, org, L, w=0.6, lo=0.3):
    """The cabinets of a counter's free spans, ``w`` wide on a grid from
    the run's end ``org`` (0 = its start, 1 = its end — the corner), the
    odd piece left at each span's far side shared out when under ``lo``:
    [(t0, t1)]."""
    out = []
    for s0, s1 in spans:
        if s1 - s0 < 0.2:
            continue
        # whole modules from the span's corner side (its start for org 0,
        # its end for org 1): the odd one at the far side
        nk = int((s1 - s0) / w + 1e-6)
        if org == 2:                 # corners at both ends: from each
            kl = nk // 2             # corner in, the odd one mid-run
            kr = nk - kl
            cuts = [s0 + k * w for k in range(0, kl + 1)] + \
                [s1 - k * w for k in range(0, kr + 1)]
        elif org == 0:
            cuts = [s0 + k * w for k in range(0, nk + 1)] + [s1]
        else:
            cuts = [s1 - k * w for k in range(0, nk + 1)] + [s0]
        cuts = sorted({round(c, 6) for c in cuts})
        pcs = [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a > 1e-3]
        # a sliver at an end: joined to its neighbour
        fixed = []
        for a, b in pcs:
            if fixed and (b - a < lo or fixed[-1][1] - fixed[-1][0] < lo):
                fixed[-1] = (fixed[-1][0], b)
            else:
                fixed.append((a, b))
        # a too-wide joined piece (over 0.9 m): split in two
        for a, b in fixed:
            if b - a > 0.9:
                out += [(a, (a + b) / 2), ((a + b) / 2, b)]
            elif b - a >= 0.2:
                out.append((a, b))
    return out


def _curtain_lines(doc, lid):
    """The curtain walls of level ``lid`` as shapely lines."""
    from shapely.geometry import LineString
    out = []
    for w in doc["arch"]["walls"]:
        if w["level"] == lid and w.get("type") == "curtain" and "a" in w:
            try:
                out.append(LineString([w["a"], w["b"]]))
            except Exception:  # noqa: BLE001
                pass
    return out


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
            ds.append((t1 - t0, d))
        if not ivs:
            continue
        d = max(ds)[1]               # the depth of its longest front line
        spans = [(s0, s1) for s0, s1 in _merge(ivs) if s1 - s0 >= 0.6]
        if spans:
            out.append({"a": a, "b": b, "u": u, "n": n, "L": L, "d": d,
                        "spans": spans, "raw": list(spans)})
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


def corner_rot(rn, q) -> tuple:
    """(turn, swapped) of an L corner unit (its back corner the model's
    (+X, +Y)) in the corner of runs ``rn`` and ``q``: +Y to ``rn``'s wall
    and +X to ``q``'s — or, the other hand round, +Y to ``q``'s
    (swapped)."""
    import math as _m
    for k_, (a_, b_) in enumerate(((rn, q), (q, rn))):
        dx, dy = -a_["n"][0], -a_["n"][1]          # +Y: to a_'s wall
        xx, xy = dy, -dx                           # where +X goes then
        if xx * -b_["n"][0] + xy * -b_["n"][1] > 0.5:
            return (_m.degrees(_m.atan2(dy, dx)) - 90.0) % 360.0, bool(k_)
    return (_m.degrees(_m.atan2(-rn["n"][1], -rn["n"][0])) - 90.0) % 360.0, \
        False


def _xy(r, s, off):
    return (r["a"][0] + r["u"][0] * s + r["n"][0] * off,
            r["a"][1] + r["u"][1] * s + r["n"][1] * off)


def serving_boxes(segs, texts, poly):
    """A counter the plan names SERVING / BAR / BREAKFAST / DINING COUNTER
    drawn as two long parallel lines round its text (its ends broken by a
    wall's opening, so no closed box): [rectangle polygon]."""
    from shapely.geometry import Point, Polygon
    out = []
    for t in texts:
        tx = str(t.get("text", ""))
        if not (SERVING_WORDS.search(tx) or re.search(r"DINING\s*COUNTER",
                                                       tx, re.I)):
            continue
        p = (float(t["x"]), float(t["y"]))
        if not poly.buffer(1.5).contains(Point(p)):
            continue
        best = None
        ls = [s_ for s_ in segs if math.hypot(s_[2] - s_[0], s_[3] - s_[1])
              >= 0.8]
        for i, a in enumerate(ls):
            ua = (a[2] - a[0], a[3] - a[1])
            La = math.hypot(*ua)
            ua = (ua[0] / La, ua[1] / La)
            na = (-ua[1], ua[0])
            for b in ls[i + 1:]:
                ub = (b[2] - b[0], b[3] - b[1])
                Lb = math.hypot(*ub)
                if abs(ua[0] * ub[1] - ua[1] * ub[0]) / Lb > 0.03:
                    continue
                gap = (b[0] - a[0]) * na[0] + (b[1] - a[1]) * na[1]
                if not 0.45 <= abs(gap) <= 1.6:
                    continue
                ta = sorted([0.0, La])
                tb = sorted([(b[0] - a[0]) * ua[0] + (b[1] - a[1]) * ua[1],
                             (b[2] - a[0]) * ua[0] + (b[3] - a[1]) * ua[1]])
                lo, hi = max(ta[0], tb[0]), min(ta[1], tb[1])
                if hi - lo < 0.8:
                    continue
                tp = (p[0] - a[0]) * ua[0] + (p[1] - a[1]) * ua[1]
                gp = (p[0] - a[0]) * na[0] + (p[1] - a[1]) * na[1]
                if not (lo - 0.1 <= tp <= hi + 0.1 and
                        min(0.0, gap) - 0.05 <= gp <= max(0.0, gap) + 0.05):
                    continue
                q0 = (a[0] + ua[0] * lo, a[1] + ua[1] * lo)
                q1 = (a[0] + ua[0] * hi, a[1] + ua[1] * hi)
                rect = Polygon([q0, q1, (q1[0] + na[0] * gap,
                                         q1[1] + na[1] * gap),
                                (q0[0] + na[0] * gap, q0[1] + na[1] * gap)])
                if best is None or rect.area < best.area:
                    best = rect
        if best is not None and not any(best.equals(o) for o in out):
            out.append(best)
    return out


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
        # against a wall: a counter run — unless the plan names it a
        # serving counter (one through a wall's opening, the living side)
        if pg.distance(wall) < 0.3 and word != "serving":
            continue
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


KINDS = ("cabinet", "corner_cabinet", "wall_cabinet", "island",
         "upper_corner")


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
    shut = []
    win_segs = []                # the plan's window glazing lines
    for s in pl.get("segs") or ():
        try:
            ly = lay[int(s[4])] if isinstance(s[4], int) else s[4]
        except (IndexError, TypeError, ValueError):
            ly = ""
        if re.search(r"WINDOW|GLAZ|GLASS", str(ly or ""), re.I):
            win_segs.append((float(s[0]), float(s[1]), float(s[2]),
                             float(s[3])))
        if _counter_layer(ly):
            segs.append((float(s[0]), float(s[1]), float(s[2]),
                         float(s[3])))
        elif math.hypot(float(s[2]) - float(s[0]),
                        float(s[3]) - float(s[1])) < 0.4:
            # a short piece on a wall layer: it may close a serving
            # counter that runs through the wall's opening
            shut.append((float(s[0]), float(s[1]), float(s[2]),
                         float(s[3])))
    short_pts = [((x0 + x1) / 2, (y0 + y1) / 2) for x0, y0, x1, y1 in segs
                 if math.hypot(x1 - x0, y1 - y0) < 0.08]
    texts = list(pl.get("texts") or ())
    base_e = _pick(entries, BASE_WORDS, avoid=("corner", "sink"))
    if base_e is None:
        return 0
    # 3.63: the corner takes the library's L corner unit (its diagonal
    # door to the room), CORNER_S each way — set by its known back corner
    # (3.62's plain cabinet in the square had its door behind the other
    # run); a plain cabinet only when the library has none
    corner_e = next((e for k_ in LOWER_CORNER_KEYS for e in entries
                     if e.get("key") == k_), None)
    upper_e = _pick(entries, UPPER_WORDS, avoid=("corner", "smaller",
                                                 "small"))
    upper_corner_e = next((e for k_ in UPPER_CORNER_KEYS for e in entries
                           if e.get("key") == k_), None)
    hood_e = _pick(entries, ["range hood", "hood"])
    ihood_e = _pick(entries, ["hood", "range hood"])   # a chimney hood
    oven_e = _pick(entries, ["microwave cabinet", "double oven", "oven"])
    hob_e = _pick(entries, HOB_WORDS)
    # a hob set into the worktop (on a cabinet), not a free-standing cooker
    top_e = _pick(entries, ["cooktop", "gas hob", "ceramic hob",
                            "induction cooker 4 zones"])
    sink_e = _pick(entries, SINK_WORDS)
    bar_e = _pick(entries, ["bar table", "island extension", "table"])
    stool_e = _pick(entries, ["bar stool", "bar chair", "stool"])
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
        shut_ = [s for s in shut if poly.buffer(0.8).intersects(
            LineString([(s[0], s[1]), (s[2], s[3])]))]
        isl = islands_of(poly, mine + shut_, texts, short_pts, walls)
        try:
            from shapely.ops import polygonize as _pz, unary_union as _uu
            mine_polys = list(_pz(_uu([LineString([(s_[0], s_[1]),
                                                    (s_[2], s_[3])])
                                       for s_ in mine])))
        except Exception:  # noqa: BLE001
            mine_polys = []
        blocks = _blocks(pl, poly, texts)
        serv = serving_boxes(mine, texts, poly)
        isl = [b for b in isl if not any(
            b[0].intersection(sv).area > 0.5 * b[0].area for sv in serv)]
        runs = runs_of(poly, mine, walls, [b[0] for b in isl] + serv)
        # a run the plan names SERVING (COUNTER / BAR): a counter through
        # the wall's opening — cabinets only, no corner unit, no uppers
        for rn in runs:
            st_ = Polygon([rn["a"], rn["b"], _xy(rn, rn["L"], rn["d"]),
                           _xy(rn, 0.0, rn["d"])]).buffer(0.35)
            rn["serving"] = any(
                SERVING_WORDS.search(str(t.get("text", ""))) and
                st_.contains(Point(float(t["x"]), float(t["y"])))
                for t in texts)
        for rn in runs:
            if not rn["serving"]:
                continue
            for end, q in list(rn.get("corners") or []):
                lo, hi = (0.0, q["d"]) if end == 0 else \
                    (rn["L"] - q["d"], rn["L"])
                rn["spans"] = _cut(rn["spans"], lo, hi)
                # the other run: back to where the plan's line stops
                for qe_, p_ in list(q.get("corners") or []):
                    if p_ is not rn or not q.get("raw"):
                        continue
                    if qe_ == 0:
                        q["spans"][0] = (q["raw"][0][0], q["spans"][0][1])
                    else:
                        q["spans"][-1] = (q["spans"][-1][0],
                                          q["raw"][-1][1])
                q["corners"] = [(e_, p_) for e_, p_ in q.get("corners")
                                or [] if p_ is not rn]
            rn["corners"] = []
        # which run owns each corner (the corner cabinets): the longer one
        for rn in runs:
            rn["own"] = {}
            for end, q in rn.get("corners") or []:
                rn["own"][end] = (rn["L"], id(rn)) > (q["L"], id(q))
        # a run on a glass wall (curtain wall / mostly windows) or with the
        # cooker on it takes no upper cabinets (3.59)
        cw_lines = _curtain_lines(doc, lid)
        for rn in runs:
            # the glass along the run: its windows and the curtain walls on
            # its side — no upper cabinet in front of them
            gl = []
            for (ox, oy), ow, kind in openings:
                off = (ox - rn["a"][0]) * rn["n"][0] + \
                    (oy - rn["a"][1]) * rn["n"][1]
                t = (ox - rn["a"][0]) * rn["u"][0] + \
                    (oy - rn["a"][1]) * rn["u"][1]
                if abs(off) < 0.4 and kind == "window":
                    gl.append((t - ow / 2 - 0.05, t + ow / 2 + 0.05))
            for cl in cw_lines:
                cs_ = list(cl.coords)
                offs = [(x - rn["a"][0]) * rn["n"][0] +
                        (y - rn["a"][1]) * rn["n"][1] for x, y in cs_]
                if max(abs(o_) for o_ in offs) > 0.4:
                    continue
                ts = [(x - rn["a"][0]) * rn["u"][0] +
                      (y - rn["a"][1]) * rn["u"][1] for x, y in cs_]
                lo_, hi_ = max(min(ts), 0.0), min(max(ts), rn["L"])
                if hi_ - lo_ > 0.1:
                    gl.append((lo_ - 0.05, hi_ + 0.05))
            # a window the plan draws in the wall behind the run (its
            # glazing lines in the wall's thickness), placed or not
            for x0, y0, x1, y1 in win_segs:
                sl = math.hypot(x1 - x0, y1 - y0)
                if sl < 0.3:
                    continue
                if abs(rn["u"][0] * (y1 - y0) - rn["u"][1] * (x1 - x0)) \
                        / sl > 0.05:
                    continue
                o0 = (x0 - rn["a"][0]) * rn["n"][0] + \
                    (y0 - rn["a"][1]) * rn["n"][1]
                o1 = (x1 - rn["a"][0]) * rn["n"][0] + \
                    (y1 - rn["a"][1]) * rn["n"][1]
                if not (-0.4 <= o0 <= 0.03 and -0.4 <= o1 <= 0.03):
                    continue
                t0 = (x0 - rn["a"][0]) * rn["u"][0] + \
                    (y0 - rn["a"][1]) * rn["u"][1]
                t1 = (x1 - rn["a"][0]) * rn["u"][0] + \
                    (y1 - rn["a"][1]) * rn["u"][1]
                lo_, hi_ = max(min(t0, t1), 0.0), min(max(t0, t1), rn["L"])
                if hi_ - lo_ > 0.3:
                    gl.append((lo_ - 0.05, hi_ + 0.05))
            rn["glass"] = _merge(gl, 0.05)
            cover = sum(min(b, rn["L"]) - max(a, 0.0)
                        for a, b in rn["glass"])
            rn["no_upper"] = "glass" if cover >= 0.6 * rn["L"] else None
            if rn.get("serving"):
                rn["no_upper"] = "serving"
        for rn in runs:
            d = rn["d"]
            strip = Polygon([rn["a"], rn["b"], _xy(rn, rn["L"], d),
                             _xy(rn, 0.0, d)])
            spans = list(rn["spans"])
            for (ox, oy), ow, kind in openings:
                off = (ox - rn["a"][0]) * rn["n"][0] + \
                    (oy - rn["a"][1]) * rn["n"][1]
                t = (ox - rn["a"][0]) * rn["u"][0] + \
                    (oy - rn["a"][1]) * rn["u"][1]
                if abs(off) < 0.4 and kind == "door":
                    spans = _cut(spans, t - ow / 2 - 0.05, t + ow / 2 + 0.05)
            # the sink / hob / fridge the plan sets on the counter
            for bpoly, kind in blocks:
                if bpoly.intersection(strip).area < 0.5 * bpoly.area:
                    continue
                if kind == "stove":
                    rn["no_upper"] = rn["no_upper"] or "cooker"
        # the grid the cabinets keep, from the corner (or from the end
        # against a wall) out to the free end; uppers on the same grid
        for rn in runs:
            d = rn["d"]
            L = rn["L"]
            ends = {e: q for e, q in rn.get("corners") or []}
            org = 2 if (0 in ends and 1 in ends) else \
                1 if 1 in ends else 0
            strip = Polygon([rn["a"], rn["b"], _xy(rn, L, d),
                             _xy(rn, 0.0, d)])
            spans = list(rn["spans"])
            # the corner squares
            for end, q in ends.items():
                if corner_e is not None:     # the L unit, its arms the
                    own_ = bool(rn["own"].get(end))      # runs' depth
                    cf_ = corner_fit(LOWER_ARMS, rn, q) if own_ else \
                        corner_fit(LOWER_ARMS, q, rn)
                    S = cf_["own"] if own_ else cf_["other"]
                    lo, hi = (0.0, S) if end == 0 else (L - S, L)
                    spans = _cut(spans, lo, hi)
                    if own_:
                        cx, cy = _xy(rn, (lo + hi) / 2, cf_["off"])
                        _rec(FO, doc, lid, corner_e, "corner_cabinet", cx,
                             cy, cf_["rot"], r, fit=cf_["fit"],
                             fit_free=True, fit_h=BASE_H)
                        n += 1
                    continue
                lo, hi = (0.0, q["d"]) if end == 0 else (L - q["d"], L)
                spans = _cut(spans, lo, hi)
                if rn["own"].get(end):
                    cx, cy = _xy(rn, (lo + hi) / 2, d / 2)
                    _rec(FO, doc, lid, base_e, "corner_cabinet", cx, cy,
                         FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                         fit=[q["d"], d], fit_free=True, fit_h=BASE_H)
                    n += 1
            for (ox, oy), ow, kind in openings:
                off = (ox - rn["a"][0]) * rn["n"][0] + \
                    (oy - rn["a"][1]) * rn["n"][1]
                t = (ox - rn["a"][0]) * rn["u"][0] + \
                    (oy - rn["a"][1]) * rn["u"][1]
                if abs(off) < 0.4 and kind == "door" and \
                        not rn.get("serving"):   # (a serving counter stands
                    spans = _cut(spans, t - ow / 2 - 0.05,  # in its opening)
                                 t + ow / 2 + 0.05)
            busy, hob_at, fridge_at = [], [], []
            # an oven / microwave tower the plan writes MV / OV on, in the
            # outline drawn round the text
            for t_ in texts:
                if not OVEN_WORDS.search(str(t_.get("text", ""))) or \
                        oven_e is None:
                    continue
                q_ = Point(float(t_["x"]), float(t_["y"]))
                if not strip.buffer(0.1).contains(q_):
                    continue
                box_ = None
                for pg_ in mine_polys:
                    if 0.1 <= pg_.area <= 1.6 and pg_.contains(q_) and (
                            box_ is None or pg_.area < box_.area):
                        box_ = pg_
                tq = (q_.x - rn["a"][0]) * rn["u"][0] + \
                    (q_.y - rn["a"][1]) * rn["u"][1]
                if box_ is not None:
                    ts_ = [(x - rn["a"][0]) * rn["u"][0] +
                           (y - rn["a"][1]) * rn["u"][1]
                           for x, y in box_.exterior.coords]
                    o0, o1 = max(min(ts_), 0.0), min(max(ts_), L)
                else:
                    # its sides: the lines across the counter either side
                    # of the text (the box closes on the wall)
                    tl, tr = [], []
                    for x0, y0, x1, y1 in mine:
                        sl = math.hypot(x1 - x0, y1 - y0)
                        if sl < 0.25:
                            continue
                        if abs(((x1 - x0) * rn["u"][0] + (y1 - y0) *
                                rn["u"][1]) / sl) > 0.1:
                            continue           # not across the run
                        m_ = Point((x0 + x1) / 2, (y0 + y1) / 2)
                        if not strip.buffer(0.05).contains(m_):
                            continue
                        tt = (m_.x - rn["a"][0]) * rn["u"][0] + \
                            (m_.y - rn["a"][1]) * rn["u"][1]
                        (tl if tt < tq else tr).append(tt)
                    tl = [x for x in tl if tq - x <= 1.2]
                    tr = [x for x in tr if x - tq <= 1.2]
                    if not tl or not tr:
                        continue
                    o0, o1 = max(tl), min(tr)
                if o1 - o0 < 0.4:
                    continue
                spans = _cut(spans, o0, o1)
                fridge_at.append((o0, o1))
                px, py = _xy(rn, (o0 + o1) / 2, d / 2)
                _rec(FO, doc, lid, oven_e, "oven", px, py,
                     FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                     fit=[o1 - o0, d], fit_free=True)
                n += 1
            for bpoly, kind in blocks:
                if bpoly.intersection(strip).area < 0.5 * bpoly.area:
                    continue
                c = bpoly.centroid
                t = (c.x - rn["a"][0]) * rn["u"][0] + \
                    (c.y - rn["a"][1]) * rn["u"][1]
                cs = list(bpoly.minimum_rotated_rectangle.exterior.coords)
                w_ = max(math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2]))
                w_ = min(max(w_, 0.6), 1.5 if kind == "ksink" else 1.2)
                e_ = {"ksink": sink_e, "stove": top_e or hob_e,
                      "fridge": fridge_e}.get(kind)
                if e_ is None:
                    continue
                px, py = _xy(rn, t, d / 2)
                if kind == "stove" and top_e is not None:
                    # the hob in the worktop, over the cabinets
                    hw_ = min(w_, 0.75)
                    _rec(FO, doc, lid, top_e, kind, px, py,
                         FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                         fit=[hw_, min(d - 0.08, 0.52)], fit_free=True,
                         zoff=BASE_H)
                    n += 1
                    w_ = hw_
                else:
                    spans = _cut(spans, t - w_ / 2, t + w_ / 2)
                    busy.append((t - w_ / 2, t + w_ / 2))
                    _rec(FO, doc, lid, e_, kind, px, py,
                         FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                         fit=[w_, d], fit_free=kind != "fridge")
                    n += 1
                if kind == "stove":
                    hob_at.append((t - w_ / 2, t + w_ / 2))
                    if hood_e is not None:       # the hood over the hob
                        hx, hy = _xy(rn, t, 0.25)
                        _rec(FO, doc, lid, hood_e, "hood", hx, hy,
                             FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                             fit=[min(w_, 0.9), 0.5], fit_free=True,
                             zoff=UPPER_Z + 0.15)
                        n += 1
                if kind == "fridge":
                    fridge_at.append((t - w_ / 2, t + w_ / 2))
            for t0, t1 in _modules(spans, org, L):
                px, py = _xy(rn, (t0 + t1) / 2, d / 2)
                _rec(FO, doc, lid, base_e, "cabinet", px, py,
                     FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                     fit=[t1 - t0, d], fit_free=True, fit_h=BASE_H)
                n += 1
            # the upper cabinets: on the same grid, from the corner; not on
            # a glass wall nor on the cooker's, clear of windows, doors and
            # the fridge
            if upper_e is None or rn["no_upper"]:
                continue
            up = [(0.0, L)]
            for (ox, oy), ow, kind in openings:
                off = (ox - rn["a"][0]) * rn["n"][0] + \
                    (oy - rn["a"][1]) * rn["n"][1]
                t = (ox - rn["a"][0]) * rn["u"][0] + \
                    (oy - rn["a"][1]) * rn["u"][1]
                if abs(off) < 0.4:
                    up = _cut(up, t - ow / 2 - 0.05, t + ow / 2 + 0.05)
            for lo, hi in hob_at + fridge_at + list(rn.get("glass") or []):
                up = _cut(up, lo, hi)
            # the counter's own extent (no uppers past its ends)
            lo_ = min(s0 for s0, _s1 in rn["spans"])
            hi_ = max(s1 for _s0, s1 in rn["spans"])
            up = [(max(a_, lo_), min(b_, hi_)) for a_, b_ in up
                  if min(b_, hi_) - max(a_, lo_) > 0.2]
            for end, q in ends.items():
                # the corner unit: the L one CORNER_S each way (the lower's
                # grid), else 60 cm
                ucf_ = corner_fit(UPPER_ARMS, rn, q, UPPER_D, UPPER_D) \
                    if rn["own"].get(end) else \
                    corner_fit(UPPER_ARMS, q, rn, UPPER_D, UPPER_D)
                qd = (ucf_["own"] if rn["own"].get(end) else ucf_["other"]) \
                    if upper_corner_e is not None else 0.6
                lo, hi = (0.0, qd) if end == 0 else (L - qd, L)
                if q.get("no_upper"):
                    continue                 # the other run has none
                up = _cut(up, lo, hi)
                qe = next((e_ for e_, p_ in q.get("corners") or []
                           if p_ is rn), 0)
                qlo, qhi = (0.0, qd) if qe == 0 else (q["L"] - qd, q["L"])
                glass_ = any(a_ < qhi and b_ > qlo for a_, b_ in
                             list(q.get("glass") or []))
                if rn["own"].get(end) and upper_corner_e is not None and \
                        not glass_ and not any(
                            a_ < hi and b_ > lo for a_, b_ in
                            list(rn.get("glass") or [])):
                    # the upper corner: an L of upper cabinets, each the
                    # runs' depth — this run's along its wall into the
                    # corner, the other run's filler up to it (3.62: one
                    # 60 × 60 box stood out of both runs)
                    if upper_corner_e is not None:
                        # 3.63: the library's L upper corner unit, its
                        # diagonal door to the room
                        cx, cy = _xy(rn, (lo + hi) / 2, ucf_["off"])
                        _rec(FO, doc, lid, upper_corner_e, "upper_corner",
                             cx, cy, ucf_["rot"], r, fit=ucf_["fit"],
                             fit_free=True, fit_h=UPPER_H, zoff=UPPER_Z,
                             corner=True)
                        n += 1
                        continue
                    cx, cy = _xy(rn, (lo + hi) / 2, UPPER_D / 2)
                    _rec(FO, doc, lid, upper_e, "wall_cabinet", cx,
                         cy, FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                         fit=[qd, UPPER_D], fit_free=True, fit_h=UPPER_H,
                         zoff=UPPER_Z, corner=True)
                    n += 1
                    if qd - UPPER_D > 0.05:
                        t_q = (UPPER_D + qd) / 2 if qe == 0 else \
                            q["L"] - (UPPER_D + qd) / 2
                        fx, fy = _xy(q, t_q, UPPER_D / 2)
                        _rec(FO, doc, lid, upper_e, "wall_cabinet", fx,
                             fy, FU.back_to(-q["n"][0], -q["n"][1]), r,
                             fit=[qd - UPPER_D, UPPER_D], fit_free=True,
                             fit_h=UPPER_H, zoff=UPPER_Z, corner=True)
                        n += 1
            for t0, t1 in _modules(up, org, L, lo=0.25):
                px, py = _xy(rn, (t0 + t1) / 2, UPPER_D / 2)
                _rec(FO, doc, lid, upper_e, "wall_cabinet", px, py,
                     FU.back_to(-rn["n"][0], -rn["n"][1]), r,
                     fit=[t1 - t0, UPPER_D], fit_free=True,
                     fit_h=UPPER_H, zoff=UPPER_Z)
                n += 1
        # the serving / dining counter the plan draws (through the wall's
        # opening): the library's bar counter on it, its chairs bar stools
        for sv in serv:
            cs = list(sv.exterior.coords)[:-1]
            e1, e2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
            if e1 >= e2:
                ax_ = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
            else:
                ax_ = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
            Ls, Ds = max(e1, e2), min(e1, e2)
            c = sv.centroid
            rot_ = (math.degrees(math.atan2(ax_[1], ax_[0]))) % 180.0
            if bar_e is not None:
                _rec(FO, doc, lid, bar_e, "serving", c.x, c.y, rot_, r,
                     fit=[Ls, Ds], fit_free=True, fit_h=1.05)
                n += 1
            if stool_e is not None:
                for f in doc.get("furniture") or []:
                    if f.get("level") != lid or f.get("kind") not in (
                            "chair", "stool") or f.get("kc"):
                        continue
                    if sv.distance(Point(f["x"], f["y"])) > 0.9:
                        continue
                    q_ = sv.exterior.interpolate(sv.exterior.project(
                        Point(f["x"], f["y"])))
                    f.update(key=stool_e["key"], name=stool_e["name"],
                             kind="stool", rot=round(FU.back_to(
                                 f["x"] - q_.x, f["y"] - q_.y), 3))
                    f.pop("fit", None)
                    f.pop("lib", None)
                    if stool_e.get("entry"):
                        f["entry"] = stool_e["entry"]
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
            # the hobs: the burners drawn on it, in groups along it (a hob
            # at each end, as the plan draws them)
            hobs = []
            if hob is not None and (top_e or hob_e) is not None:
                bts = sorted((p[0] - p0[0]) * u[0] + (p[1] - p0[1]) * u[1]
                             for p in short_pts if pg.contains(Point(p)))
                grp = []
                for t_ in bts:
                    if grp and t_ - grp[-1][-1] > 0.3:
                        grp.append([t_])
                    elif grp:
                        grp[-1].append(t_)
                    else:
                        grp.append([t_])
                grp = [g_ for g_ in grp if len(g_) >= 8] or \
                    [[(hob[0] - p0[0]) * u[0] + (hob[1] - p0[1]) * u[1]]]
                for g_ in grp:
                    hw = min(max(g_[-1] - g_[0] + 0.2, 0.45),
                             0.75 if top_e is not None else 0.9, L)
                    hobs.append(((g_[0] + g_[-1]) / 2, hw))
            for hob_t, hw in hobs:
                hob_t = min(max(hob_t, hw / 2), L - hw / 2)
                hx = c.x + u[0] * (hob_t - L / 2)
                hy = c.y + u[1] * (hob_t - L / 2)
                if top_e is not None:     # the hob in the island's top
                    _rec(FO, doc, lid, top_e, "stove", hx, hy,
                         FU.back_to(-nv[0], -nv[1]), r,
                         fit=[hw, min(D - 0.1, 0.52)], fit_free=True,
                         island=True, zoff=BASE_H)
                else:
                    spans = _cut(spans, hob_t - hw / 2, hob_t + hw / 2)
                    _rec(FO, doc, lid, hob_e, "stove", hx, hy,
                         FU.back_to(-nv[0], -nv[1]), r,
                         fit=[hw, D], fit_free=True, island=True)
                n += 1
                if ihood_e is not None:   # the island hood over the hob,
                    _rec(FO, doc, lid, ihood_e, "hood", hx, hy,  # hung
                         FU.back_to(-nv[0], -nv[1]), r,
                         fit=[min(max(hw, 0.6), 0.9), 0.55],
                         fit_free=True, island=True, zoff=1.65)
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
