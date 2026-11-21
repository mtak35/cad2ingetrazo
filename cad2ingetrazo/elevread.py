"""3.64.42: the CAD's elevations read back into the model.

A drawing that holds its elevations («ELEVATION-01», «FRONT ELEVATION»)
says what the plans cannot: how high each window and door stands (its
sill and head), whether its head is arched or flat, the storey heights
(the level marks «±0'-0" GR.FLOOR», «+12'-0" 1ST FLOOR»), whether a
railing is glass, and whether a roof parapet stands at all.

Each elevation is matched to a side of the model by the openings it
draws: the plan's openings on that side, seen from outside, are slid
along the elevation until their jambs fall on the elevation's frame
lines. The side and the slide that line up the most jambs win. Then
every opening seen there takes its sill and head from the frame drawn
over it.
"""
from __future__ import annotations

import bisect
import math
import re

#: a level mark's value: «+12'-0"», «±0'-0"», «-3'-6"» (a sign is needed:
#: a dimension's «10'-0"» is no level)
LEVEL_RX = re.compile(
    r"^\s*([+±\-])\s*(\d+(?:\.\d+)?)\s*(?:'|’)\s*-?\s*(\d+(?:\.\d+)?)?\s*"
    r"(?:\"|''|”)?\s*$")
#: a level mark in metres: «+3.65», «± 0.00», «FFL +3.600»
LEVEL_M_RX = re.compile(r"^\s*(?:F\.?F\.?L\.?\s*)?([+±\-])\s*(\d+\.\d{2,3})\s*$",
                        re.I)
TITLE_RX = re.compile(r"\bELEVATIONS?\b|\bELEV\b\.?", re.I)
VIEW_RX = re.compile(r"\bELEVATIONS?\b|\bSECTION\b|\bELEV\b", re.I)
#: layers that never hold the building's lines in an elevation
NOTE_LAYERS = re.compile(
    r"DIM|TEXT|ANNO|LEVEL|DEFPOINT|HATCH|GRID|TITLE|NOTE|LEADER|BORDER",
    re.I)

FT = 0.3048
JAMB_TOL = 0.05          # m: a jamb and an elevation frame line «coincide»
DIRS = {                 # the side → (looking direction f, the view's right r)
    "west": ((1.0, 0.0), (0.0, -1.0)),
    "east": ((-1.0, 0.0), (0.0, 1.0)),
    "north": ((0.0, -1.0), (-1.0, 0.0)),
    "south": ((0.0, 1.0), (1.0, 0.0)),
}


def _level_value(txt):
    """A level mark's value in metres, or None."""
    t = txt.replace("%%p", "±").replace("%%P", "±").strip()
    m = LEVEL_RX.match(t)
    if m:
        v = float(m.group(2)) * FT + float(m.group(3) or 0.0) * FT / 12.0
        return -v if m.group(1) == "-" else v
    m = LEVEL_M_RX.match(t)
    if m:
        v = float(m.group(2))
        return -v if m.group(1) == "-" else v
    return None


def _is_horiz(s, k, tol=0.01):
    return abs(s[3] - s[1]) * k < tol and abs(s[2] - s[0]) * k > 0.0


def _is_vert(s, k, tol=0.01):
    return abs(s[2] - s[0]) * k < tol and abs(s[3] - s[1]) * k > 0.0


def find_views(raw) -> list:
    """The drawing's elevations: [{"title", "x0", "x1", "datums":
    [(y, metres)], "b"}] — ``b`` puts a drawing y at its height:
    z = y·k − b (metres over the ground floor's ±0)."""
    k = float(raw.get("unit") or 1.0)
    ft = FT / k
    titles = [t for t in raw["texts"] if VIEW_RX.search(t["text"] or "")
              and len(t["text"]) < 60]
    marks = []
    for t in raw["texts"]:
        v = _level_value(t["text"] or "")
        if v is not None:
            marks.append((t, v))
    if not titles or len(marks) < 2:
        return []
    hsegs = [s for s in raw["segs"] if _is_horiz(s, k)
             and abs(s[2] - s[0]) > 1.5 * ft]
    views = []
    for ti in titles:
        # the level marks just above the title, the nearest cluster
        near = [(t, v) for t, v in marks
                if ti["y"] < t["y"] < ti["y"] + 80 * ft
                and abs(t["x"] - ti["x"]) < 40 * ft]
        if len(near) < 2:
            continue
        near.sort(key=lambda tv: abs(tv[0]["x"] - ti["x"]))
        cx = near[0][0]["x"]
        clus = [(t, v) for t, v in near if abs(t["x"] - cx) < 8 * ft]
        if len(clus) < 2:
            continue
        datums = []
        for t, v in clus:
            # the datum line: the nearest long level line under the mark
            # (longer than the mark's own underline)
            best = None
            for s in hsegs:
                if abs(s[2] - s[0]) < 5 * ft:
                    continue
                y = s[1]
                if t["y"] - 3 * ft <= y <= t["y"] + 0.2 * ft and \
                        min(s[0], s[2]) - 2 * ft <= t["x"] <= \
                        max(s[0], s[2]) + 2 * ft:
                    if best is None or y > best:
                        best = y
            datums.append((best if best is not None else t["y"], v))
        # one line puts them all: z = y·k − b (the marks that disagree out)
        bs = sorted(y * k - v for y, v in datums)
        b = bs[len(bs) // 2]
        datums = sorted({round(v, 3): (y, v) for y, v in datums
                         if abs(y * k - v - b) < 0.15}.values(),
                        key=lambda yv: yv[1])
        if len(datums) < 2:
            continue
        views.append({"title": ti["text"].strip(), "tx": ti["x"],
                      "ty": ti["y"], "mx": min(t["x"] for t, _ in clus),
                      "datums": datums, "b": b,
                      "elev": bool(TITLE_RX.search(ti["text"]))})
    # one view per title position (a title read twice: once)
    uniq = []
    for v in views:
        if not any(abs(v["tx"] - u["tx"]) < 2 * ft and
                   abs(v["ty"] - u["ty"]) < 2 * ft for u in uniq):
            uniq.append(v)
    views = uniq
    # each view's sideways reach: from its level marks to the next view's
    for v in views:
        row = sorted((u for u in views if abs(u["ty"] - v["ty"]) < 6 * ft),
                     key=lambda u: u["mx"])
        i = row.index(v)
        v["x0"] = v["mx"] - 2 * ft
        v["x1"] = row[i + 1]["mx"] - 2 * ft if i + 1 < len(row) \
            else v["mx"] + 90 * ft
        lo = min(y for y, _ in v["datums"])
        hi = max(y for y, _ in v["datums"])
        v["y0"] = lo - 4 * ft
        v["y1"] = hi + 4 * ft
    return [v for v in views if v["elev"]]


def _view_geom(raw, v):
    """The view's own lines, in metres: vertical [(u, z0, z1)], horizontal
    [(u0, u1, z)], arcs [(u0, u1, z0, z1)], circles [(u, z, r)], glass
    marks {insert name: [(u, z)]}."""
    k = float(raw.get("unit") or 1.0)
    b = v["b"]
    x0, x1, y0, y1 = v["x0"], v["x1"], v["y0"], v["y1"]

    def inside(x, y):
        return x0 <= x <= x1 and y0 <= y <= y1

    vert, horiz = [], []
    for s in raw["segs"]:
        if NOTE_LAYERS.search(s[4] or ""):
            continue
        if not (inside(s[0], s[1]) and inside(s[2], s[3])):
            continue
        if _is_vert(s, k):
            za, zb = sorted((s[1] * k - b, s[3] * k - b))
            vert.append((s[0] * k, za, zb))
        elif _is_horiz(s, k):
            ua, ub = sorted((s[0] * k, s[2] * k))
            horiz.append((ua, ub, s[1] * k - b))
    arcs = []
    for a in raw.get("arcs", []):
        if NOTE_LAYERS.search(a["layer"] or ""):
            continue
        pts = (a["p0"], a["p1"], a["pm"])
        if not all(inside(*p) for p in pts):
            continue
        us = [p[0] * k for p in pts]
        zs = [p[1] * k - b for p in pts]
        if float(a["r"]) * k < 0.15:        # a knob, a hinge mark
            continue
        arcs.append((min(us), max(us), min(zs), max(zs)))
    circles = []
    for c in raw.get("circles", []):
        if NOTE_LAYERS.search(c["layer"] or ""):
            continue
        if inside(*c["c"]) and float(c["r"]) * k > 0.2:
            circles.append((c["c"][0] * k, c["c"][1] * k - b,
                            float(c["r"]) * k))
    marks = {}
    for ins in raw.get("inserts", []):
        bx = ins.get("box") or [ins["x"], ins["y"], ins["x"], ins["y"]]
        cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
        if inside(cx, cy) and (bx[2] - bx[0]) * k < 0.3 and \
                (bx[3] - bx[1]) * k < 0.3:
            marks.setdefault(ins["name"], []).append((cx * k, cy * k - b))
    return vert, horiz, arcs, circles, marks


#: layers that hold the surroundings, not the building (trees, people, cars)
ENTOURAGE = re.compile(r"TREE|PLANT|LAND|FURN|PEOPLE|PERSON|HUMAN|\bCAR|"
                       r"VEHICLE|ENTOUR|SHRUB|GRASS|SKY|CLOUD|BIRD|SHADE|"
                       r"SHADOW|SCALE", re.I)
#: 3.64.101: the last read's silhouettes: {side: [(u0, z0, u1, z1)]} in the
#: model's metres (all the view's lines, diagonals too) — for the roof
PROFILES: dict = {}


def _view_all(raw, v):
    """Every line of the view that belongs to the building, in metres
    over the view's datum: [(u0, z0, u1, z1)] (a sloped roof edge is one)."""
    k = float(raw.get("unit") or 1.0)
    b = v["b"]
    x0, x1, y0, y1 = v["x0"], v["x1"], v["y0"], v["y1"]
    out = []
    for s in raw["segs"]:
        lay = s[4] or ""
        if NOTE_LAYERS.search(lay) or ENTOURAGE.search(lay):
            continue
        if not (x0 <= s[0] <= x1 and x0 <= s[2] <= x1 and
                y0 - 60 * FT / k <= s[1] <= y1 + 60 * FT / k and
                y0 - 60 * FT / k <= s[3] <= y1 + 60 * FT / k):
            continue
        out.append((s[0] * k, s[1] * k - b, s[2] * k, s[3] * k - b))
    return out


def _bands(arch, datums, el):
    """{level id: (z0, z1)} — each level from its floor to the next (the
    elevation's own levels; above the last noted floor, its height)."""
    levels = arch["levels"]
    order = sorted(range(len(levels)), key=lambda i: el[i])
    out = {}
    for n, i in enumerate(order):
        z0 = el[i]
        z1 = el[order[n + 1]] if n + 1 < len(order) else \
            z0 + float(levels[i].get("height", 3.0))
        out[levels[i]["id"]] = (z0, z1)
    return out


def _visible(arch, D):
    """The openings seen from side D: [(opening, wall, u0, u1, depth)]
    and the walls seen there (for the parapets and railings): the nearest
    wall of its level covering it is no other one."""
    f, r = DIRS[D]
    walls = [w for w in arch["walls"] if w.get("kind", "line") == "line"]
    par = []
    for w in walls:
        ax, ay = w["a"]
        bx, by = w["b"]
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            continue
        dx, dy = (bx - ax) / L, (by - ay) / L
        if abs(dx * f[0] + dy * f[1]) > 0.15:
            continue
        ua = ax * r[0] + ay * r[1]
        ub = bx * r[0] + by * r[1]
        dep = ((ax + bx) / 2) * f[0] + ((ay + by) / 2) * f[1]
        par.append((w, min(ua, ub), max(ua, ub), dep, L, (dx, dy)))
    solid = [p for p in par if not p[0].get("rail")]

    def hidden(w, lvl, u, dep):
        for q in solid:
            if q[0] is w or q[0]["level"] != lvl:
                continue
            if q[1] + 0.05 < u < q[2] - 0.05 and q[3] < dep - 0.3:
                return True
        return False

    byw = {p[0]["id"]: p for p in par}
    ops = []
    for o in arch["openings"]:
        p = byw.get(o["wall"])
        if not p:
            continue
        w, _, _, dep, L, (dx, dy) = p
        c = float(o["pos"])
        cx = w["a"][0] + dx * c
        cy = w["a"][1] + dy * c
        cu = cx * r[0] + cy * r[1]
        hw = float(o["w"]) / 2
        if hidden(w, w["level"], cu, dep):
            continue
        behind_rail = any(
            q[0].get("rail") and q[0]["level"] == w["level"] and
            q[1] - 0.05 < cu < q[2] + 0.05 and q[3] < dep - 0.3
            for q in par)
        ops.append((o, w, cu - hw, cu + hw, dep, behind_rail))
    seen = [(w, u0, u1, dep) for (w, u0, u1, dep, _L, _d) in par
            if not hidden(w, w["level"], (u0 + u1) / 2, dep)]
    return ops, seen


def _fit(ops, vert, bands):
    """The slide s (model u = drawing u + s) that lines up the most jambs
    with the elevation's vertical lines: (matched, s)."""
    if not ops or not vert:
        return 0, 0.0
    by_band = {}
    for lid, (z0, z1) in bands.items():
        us = sorted(u for (u, za, zb) in vert
                    if zb - za > 0.25 and min(zb, z1) - max(za, z0) > 0.25)
        by_band[lid] = us
    edges = []
    for o, w, u0, u1, *_ in ops:
        us = by_band.get(w["level"])
        if us:
            edges.append((us, u0))
            edges.append((us, u1))
    if not edges:
        return 0, 0.0
    cands = set()
    for us, e in edges:
        for u in us:
            cands.add(round(e - u, 2))
    best = (0, 0.0)
    for s in cands:
        n = 0
        for us, e in edges:
            t = e - s
            j = bisect.bisect_left(us, t - JAMB_TOL)
            if j < len(us) and us[j] <= t + JAMB_TOL:
                n += 1
        if n > best[0]:
            best = (n, s)
    # refine: the mean offset of the matched jambs
    n, s = best
    offs = []
    for us, e in edges:
        t = e - s
        j = bisect.bisect_left(us, t - JAMB_TOL)
        if j < len(us) and us[j] <= t + JAMB_TOL:
            offs.append(e - us[j])
    if offs:
        s = sum(offs) / len(offs)
    return n, s, len(edges)


def _oculus(arch, D, u, z, r) -> bool:
    """A round window (u, z, radius r seen from side D) set in the gable
    end of a pitched roof seen there: True when one takes it."""
    f, rv = DIRS[D]
    best = None
    for e in arch["structure"]:
        if e.get("type") != "roof" or e.get("kind") != "gable":
            continue
        cs = e.get("corners") or []
        if len(cs) != 4:
            continue
        edges = [(cs[i], cs[(i + 1) % 4]) for i in range(4)]
        lens = [math.dist(a, b) for a, b in edges]
        long_ = max(lens)
        for (a, b), L in zip(edges, lens):
            if L < 1e-6:
                continue
            dx, dy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            if abs(dx * f[0] + dy * f[1]) > 0.15:
                continue
            # a gable's end: across the ridge
            is_end = (L < long_ - 1e-6) == (e.get("ridge", "long") != "short")
            if not is_end and abs(lens[0] - lens[1]) > 1e-3:
                continue
            ua, ub = a[0] * rv[0] + a[1] * rv[1], b[0] * rv[0] + b[1] * rv[1]
            if not (min(ua, ub) + r < u < max(ua, ub) - r):
                continue
            dep = ((a[0] + b[0]) / 2) * f[0] + ((a[1] + b[1]) / 2) * f[1]
            if best is None or dep < best[0]:
                t_ = (u - ua) / (ub - ua)
                best = (dep, e, (a[0] + (b[0] - a[0]) * t_,
                                 a[1] + (b[1] - a[1]) * t_))
    if best is None:
        return False
    _d, e, (x, y) = best
    ocs = [o for o in e.get("oculus") or []
           if math.hypot(o["x"] - x, o["y"] - y) > 0.3
           or abs(o["z"] - z) > 0.3]
    ocs.append({"x": round(x, 4), "y": round(y, 4), "z": round(z, 4),
                "d": round(2 * r, 3)})
    e["oculus"] = ocs
    return True


def apply(doc, raw=None, file=None) -> dict:
    """The elevations the drawing holds, read back into the model. Returns
    a report: {"views": {title: side}, "openings": n, "levels": [...],
    "rails": n, "parapets": n, "round": [...]}."""
    from . import cadread
    from . import project as PJ
    rep = {}
    if raw is None:
        if not file:
            files = [h.get("file") for h in doc["imports"].values()
                     if h.get("file")]
            if not files:
                return rep
            file = files[0]
        how = next((h for h in doc["imports"].values()
                    if h.get("file") == file), {})
        raw = cadread.read(file, how.get("unit"))
    views = find_views(raw)
    PROFILES.clear()
    if not views:
        return rep
    arch = doc["arch"]
    levels = arch["levels"]
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)

    # ---- storey heights from the level marks (the view with the most) ----
    best_v = max(views, key=lambda v: len(v["datums"]))
    vals = sorted({round(v, 3) for _, v in best_v["datums"] if v >= -0.01})
    lv_set = []
    up = [i for i in sorted(range(len(levels)),
                            key=lambda i: PJ.elevations(arch)[i])
          if i >= g or PJ.elevations(arch)[i] >= PJ.elevations(arch)[g]]
    if len(vals) >= 2 and abs(vals[0]) < 0.05:
        for n, i in enumerate(up[:-1]):
            if n + 1 >= len(vals):
                break
            h = vals[n + 1] - vals[n]
            if 2.2 <= h <= 8.0 and abs(h - float(levels[i]["height"])) > 0.03:
                old = float(levels[i]["height"])
                levels[i]["height"] = round(h, 4)
                lv_set.append((levels[i]["name"], round(old, 3), round(h, 3)))
    if lv_set:
        rep["levels"] = lv_set
    el = PJ.elevations(arch)
    zg = el[g]
    bands = _bands(arch, best_v["datums"], el)

    # ---- each elevation: its side, then what it says ----------------------
    used = set()
    rep["views"] = {}
    st = new_stats()
    geoms = []
    for v in views:
        geo = _view_geom(raw, v)
        vert = [(u, za + zg, zb + zg) for (u, za, zb) in geo[0]]
        fits = []
        for D in DIRS:
            ops, seen = _visible(arch, D)
            res = _fit(ops, vert, bands)
            if len(res) == 3 and res[0] >= max(4, 0.45 * res[2]):
                fits.append((res[0] / max(res[2], 1), res[0], D, res[1],
                             ops, seen))
        fits.sort(key=lambda t: (-t[0], -t[1]))
        geoms.append((v, geo, fits))
    # the best matches first: one view per side
    order = sorted(geoms, key=lambda gv: -(gv[2][0][0] if gv[2] else 0))
    for v, geo, fits in order:
        fit = next((f_ for f_ in fits if f_[2] not in used), None)
        if not fit:
            continue
        _r, _n, D, s, ops, seen = fit
        used.add(D)
        rep["views"][v["title"]] = D
        vert0, horiz0, arcs0, circ0, marks0 = geo
        vert = [(u + s, za + zg, zb + zg) for (u, za, zb) in vert0]
        horiz = [(ua + s, ub + s, z + zg) for (ua, ub, z) in horiz0]
        arcs = [(ua + s, ub + s, za + zg, zb + zg)
                for (ua, ub, za, zb) in arcs0]
        circ = [(u + s, z + zg, rr) for (u, z, rr) in circ0]
        marks = {nm: [(u + s, z + zg) for (u, z) in pts]
                 for nm, pts in marks0.items()}
        try:
            PROFILES[D] = [(a_ + s, b_ + zg, c_ + s, d_ + zg)
                           for a_, b_, c_, d_ in _view_all(raw, v)]
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("elevread profile")
        _apply_view(doc, arch, D, ops, seen, vert, horiz, arcs, circ, marks,
                    bands, st)
    finish_stats(arch, st, rep)
    return rep


def new_stats() -> dict:
    return {"openings": 0, "rails": 0, "round": [], "drop": set()}


def finish_stats(arch, st, rep) -> None:
    """The parapets marked to go, gone; the counts into the report."""
    n_par = 0
    if st["drop"]:
        # a jog between two dropped parapets goes with them
        arch["walls"] = [w for w in arch["walls"]
                         if w["id"] not in st["drop"]]
        n_par = len(st["drop"])
        left = [w for w in arch["walls"]
                if str(w.get("name", "")).lower().startswith("roof parapet")
                and w.get("jog")]
        for w in left:
            arch["walls"].remove(w)
            n_par += 1
    rep["openings"] = rep.get("openings", 0) + st["openings"]
    if st["rails"]:
        rep["rails"] = rep.get("rails", 0) + st["rails"]
    if n_par:
        rep["parapets"] = rep.get("parapets", 0) + n_par
    if st["round"]:
        rep.setdefault("round", []).extend(st["round"])

def _apply_view(doc, arch, D, ops, seen, vert, horiz, arcs, circ, marks,
                bands, st, know_arcs=True, careful=False) -> None:
    """What one elevation seen from side D says, set in the model: the
    openings' sills and heads (and arched / flat heads when the drawing's
    arcs are known), a gable's round window, glass railings, the parapets
    and void railings it does not draw. ``vert`` / ``horiz`` / … in model
    metres (u along the view, z absolute). ``st`` gathers the counts."""
    glass_names = {}
    hit_circ = set()
    for o, w, u0, u1, dep, behind_rail in ops:
        z0, z1 = bands.get(w["level"], (None, None))
        if z0 is None:
            continue
        lo, hi = u0 - 0.06, u1 + 0.06
        zs = [z for (u, za, zb) in vert
              if lo <= u <= hi and zb - za > 0.2
              and za > z0 - 0.1 and zb < z1 + 0.05
              for z in (za, zb)]
        zs += [z for (ua, ub, z) in horiz
               if ua >= lo and ub <= hi and ub - ua > 0.6 * (u1 - u0)
               and z0 - 0.1 < z < z1 - 0.05]
        for i_, (cu, cz, rr) in enumerate(circ):
            if lo <= cu <= hi and z0 < cz < z1:
                hit_circ.add(i_)
        if len(zs) < 2:
            continue
        sill, head = min(zs), max(zs)
        if head - sill < 0.3:
            continue
        sill = max(sill, z0)
        head_raw = head
        head = min(head, z1 - 0.15)      # (the slab / lintel over it)
        arched = any(ua < hi and ub > lo and head - 1.0 < zb <= head + 0.1
                     and za > sill for (ua, ub, za, zb) in arcs)
        ch = False
        if o["kind"] == "door" or behind_rail:
            h_new = round(head - z0 - float(o.get("sill", 0.0) or 0.0), 3)
            if o["kind"] != "door":
                h_new = round(head - z0 - float(o.get("sill", 0.0)), 3)
            if h_new > 1.5 and abs(h_new - float(o["h"])) > 0.03:
                o["h"] = h_new
                ch = True
        else:
            s_new = round(sill - z0, 3)
            if s_new < 0.08:
                s_new = 0.0
            h_new = round(head - z0 - s_new, 3)
            if abs(s_new - float(o.get("sill", 0.0) or 0.0)) > 0.03 or \
                    abs(h_new - float(o["h"])) > 0.03:
                o["sill"], o["h"] = s_new, h_new
                ch = True
        if not know_arcs:
            # a picture: no arcs known — a straight top drawn over it says
            # «flat»; else the head is left as it is
            flat_ = any(abs(z - head_raw) < 0.08 and min(ub, hi) - max(ua, lo)
                        > 0.7 * (u1 - u0) for (ua, ub, z) in horiz)
            if flat_ and (o.get("head") == "arch" or o.get("arch")):
                o["head"] = "flat"
                o.pop("arch", None)
                ch = True
        elif not arched and (o.get("head") == "arch" or o.get("arch")):
            o["head"] = "flat"
            o.pop("arch", None)
            ch = True
        elif arched and o.get("head") != "arch":
            o["head"] = "arch"
            o.setdefault("arch", "semi")
            ch = True
        if ch:
            o["elev_cad"] = 1
            st["openings"] += 1
        # the glass marks the windows hold (to know the railings' glass)
        if o["kind"] == "window":
            for nm, pts in marks.items():
                if any(lo <= u <= hi and sill <= z <= head
                       for u, z in pts):
                    glass_names[nm] = glass_names.get(nm, 0) + 1
    # a round window the plans could not draw (a gable's oculus):
    # the outer of concentric circles, set in the gable end seen there
    cs_ = sorted((c_ for i_, c_ in enumerate(circ)
                  if i_ not in hit_circ and c_[2] > 0.25),
                 key=lambda c_: -c_[2])
    kept = []
    for cu, cz, rr in cs_:
        if any(math.hypot(cu - k_[0], cz - k_[1]) < k_[2] for k_ in kept):
            continue
        kept.append((cu, cz, rr))
        put = _oculus(arch, D, cu, cz, rr)
        st["round"].append({"side": D, "u": round(cu, 2), "z": round(cz, 2),
                       "d": round(2 * rr, 2), "built": put})
    # railings: glass when the glass marks stand in them
    for w, u0, u1, dep in seen:
        if not w.get("rail"):
            continue
        z0, z1 = bands.get(w["level"], (None, None))
        if z0 is None:
            continue
        n_g = sum(1 for nm in glass_names for (u, z) in marks.get(nm, [])
                  if u0 - 0.05 <= u <= u1 + 0.05 and
                  z0 < z < z0 + float(w.get("height", 1.1) or 1.1) + 0.2)
        if n_g and w.get("rail") not in ("glass", "glass_post"):
            w["rail"] = "glass_post"
            st["rails"] += 1
    if careful:                  # a picture: openings only
        return
    # roof parapets the elevation does not draw
    umin = min((u for u, _a, _b in vert), default=0.0)
    umax = max((u for u, _a, _b in vert), default=0.0)
    for w, u0, u1, dep in seen:
        nm = str(w.get("name", ""))
        if not nm.lower().startswith("roof parapet"):
            continue
        z0, z1 = bands.get(w["level"], (None, None))
        if z0 is None or u1 < umin - 3.0 or u0 > umax + 3.0:
            continue
        hp = float(w.get("height", 1.0) or 1.0)
        cov = 0.0
        for ua, ub, z in horiz:
            if z0 + 0.25 <= z <= z0 + hp + 0.05:
                cov += max(0.0, min(ub, u1) - max(ua, u0))
        span = max(u1 - u0, 0.05)
        if cov < 0.4 * span and u1 - u0 > 0.0:
            st["drop"].add(w["id"])
    # a void's railing the elevation does not draw (a roof open over
    # a terrace: no railing round it up there)
    f_, r_ = DIRS[D]
    for m in doc.get("man_shafts") or []:
        z0, z1 = bands.get(m.get("level"), (None, None))
        if z0 is not None and m.get("above"):    # «VOID ABOVE»: the
            z0, z1 = next(((a_, b_) for a_, b_ in   # floor over it
                           sorted(bands.values()) if a_ > z0 + 0.5),
                          (None, None))
        if z0 is None or not m.get("pts") or m.get("auto") == "lift":
            continue
        us = [p_[0] * r_[0] + p_[1] * r_[1] for p_ in m["pts"]]
        u0, u1 = min(us), max(us)
        if u1 - u0 < 0.5 or u1 < umin - 0.5 or u0 > umax + 0.5:
            continue
        # seen from outside only: no wall of its level in front of it
        dmin = min(p_[0] * f_[0] + p_[1] * f_[1] for p_ in m["pts"])
        uc = (u0 + u1) / 2
        lv_ = next((lid_ for lid_, b_ in bands.items()
                    if abs(b_[0] - z0) < 1e-6), m.get("level"))
        if any(w["level"] == lv_ and not w.get("rail") and
               wu0 + 0.05 < uc < wu1 - 0.05 and wd < dmin - 0.3
               for w, wu0, wu1, wd in seen):
            continue
        cov = 0.0
        for ua, ub, z in horiz:
            if z0 + 0.3 <= z <= z0 + 1.15:
                cov += max(0.0, min(ub, u1) - max(ua, u0))
        if cov < 0.25 * (u1 - u0):
            m["no_rail"] = True
