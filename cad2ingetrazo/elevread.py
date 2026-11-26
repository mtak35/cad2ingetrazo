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


def dirs_of(arch):
    """The sides' directions: the compass ones — or those of a rotated
    block's own axes (3.64.153: ``arch["_dirs"]``)."""
    return arch.get("_dirs") or DIRS


#: 3.64.156: a level mark with its name before it: «GR.LEV.+4'-0"»,
#: «ROOF LEV.+36'-0"», «R.LEV.±0'-0"», «1ST.FL.LEV.+24'-0"»
LEVEL_NAMED_RX = re.compile(
    r"^[A-Za-z0-9 .\-/&]*?(?:LEV|LEVEL|FL|FLOOR|ROOF|SLAB|GL|NGL|TOP)"
    r"[A-Za-z. ]*?([+±\-]\s*\d+(?:\.\d+)?\s*(?:'|’)\s*-?\s*"
    r"(?:\d+(?:\.\d+)?)?\s*(?:\"|''|”)?)\s*$", re.I)


def _level_value(txt):
    """A level mark's value in metres, or None."""
    t = txt.replace("%%p", "±").replace("%%P", "±").strip()
    m = LEVEL_RX.match(t)
    if not m:
        n_ = LEVEL_NAMED_RX.match(t)
        if n_:
            m = LEVEL_RX.match(n_.group(1))
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
    f, r = dirs_of(arch)[D]
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
    f, rv = dirs_of(arch)[D]
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
    if st.get("tall"):
        rep["tall windows"] = rep.get("tall windows", 0) + st["tall"]
    if st.get("arches"):
        rep["arcade arches"] = rep.get("arcade arches", 0) + st["arches"]


def _add_opening(arch, rec) -> None:
    """3.64.157: a new opening in the block's view and in the model's own
    list (a block's view holds copies of the lists)."""
    arch["openings"].append(rec)
    allo = arch.get("_all_openings")
    if allo is not None and allo is not arch["openings"]:
        allo.append(rec)


def _new_upper(arch, seen, lid, z0, z1, u0, u1, dep, D):
    """An opening over a tall window where the plan has none: on the wall
    of that storey standing at its place. (opening, wall, z0, z1) or None."""
    import uuid
    for w2, a0, a1, d2 in seen:
        if w2["level"] != lid or w2.get("rail") or abs(d2 - dep) > 1.5:
            continue
        if not (a0 - 0.05 <= u0 and u1 <= a1 + 0.05):
            continue
        ax, ay = w2["a"]
        bx, by = w2["b"]
        f_, r_ = dirs_of(arch)[D]
        ua = ax * r_[0] + ay * r_[1]
        ub = bx * r_[0] + by * r_[1]
        if abs(ub - ua) < 0.5:
            continue
        L = math.hypot(bx - ax, by - ay)
        uc = (u0 + u1) / 2
        pos = (uc - ua) / (ub - ua) * L
        sample = next((q for q in arch["openings"]
                       if q["wall"] == w2["id"]), None) or next(
            (q for q in arch["openings"]
             if q["kind"] == "void" and
             next((x for x in arch["walls"] if x["id"] == q["wall"]),
                  {}).get("level") == lid), None)
        rec = dict(sample) if sample else {
            "kind": "void", "swing": "left", "style": "", "leaves": 1,
            "face": 1, "frame": "auto", "hl": 1}
        rec.update({"id": uuid.uuid4().hex[:8], "wall": w2["id"],
                    "pos": round(pos, 4), "w": round(u1 - u0, 3),
                    "sill": 0.0, "h": 1.0, "head": "flat",
                    "name": "Window (elevation)", "elev_cad": 1})
        rec.pop("arch", None)
        _add_opening(arch, rec)
        return rec, w2, z0, z1
    return None


def _arch_bays(arcs):
    """3.64.157: the big pointed arches an elevation draws (an arcade's
    bays): two arcs that meet at the apex, each taller than wide. Each as
    (u0, u1, spring, apex), the innermost ring of a nest only."""
    cand = [a for a in arcs if a[1] - a[0] > 0.2 and
            (a[3] - a[2]) > 1.2 * (a[1] - a[0])]
    bays = []
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            l, r = (a, b) if a[0] < b[0] else (b, a)
            if abs(l[1] - r[0]) < 0.12 and abs(l[3] - r[3]) < 0.12 and \
                    abs(l[2] - r[2]) < 0.15 and l[1] - l[0] > 0.2 and \
                    r[1] - r[0] > 0.2:
                bays.append((l[0], r[1], min(l[2], r[2]), l[3]))
    bays = [b for b in bays if 0.45 <= b[1] - b[0] <= 4.2 and
            b[3] - b[2] > 0.5]
    out = []
    for b in sorted(bays, key=lambda q: q[1] - q[0]):
        c = (b[0] + b[1]) / 2
        if not any(abs((o[0] + o[1]) / 2 - c) < 0.2 for o in out):
            out.append(b)
    return sorted(out)


def _add_wall(arch, rec) -> None:
    """3.64.161: a new wall in the block's view and in the model's own
    list."""
    arch["walls"].append(rec)
    allw = arch.get("_all_walls")
    if allw is not None and allw is not arch["walls"]:
        allw.append(rec)


def _bay_columns(arch, lid, f_, r_, u0, u1, d_near=None):
    """3.64.161: the two columns of storey ``lid`` that stand either side
    of an arcade bay (clear span u0..u1): (depth of their centres, their
    depth) or None."""
    left, right = [], []
    for e in arch["structure"]:
        if e.get("type") != "column" or e.get("level") != lid or \
                e.get("x") is None:
            continue
        a_ = math.radians(float(e.get("angle", 0.0) or 0.0))
        w_, d_ = float(e.get("w", 0.5)), float(e.get("d", e.get("w", 0.5)))
        e1 = (math.cos(a_), math.sin(a_))
        e2 = (-math.sin(a_), math.cos(a_))
        hu = (abs(e1[0] * r_[0] + e1[1] * r_[1]) * w_ +
              abs(e2[0] * r_[0] + e2[1] * r_[1]) * d_) / 2
        hd = (abs(e1[0] * f_[0] + e1[1] * f_[1]) * w_ +
              abs(e2[0] * f_[0] + e2[1] * f_[1]) * d_) / 2
        cu = e["x"] * r_[0] + e["y"] * r_[1]
        cd = e["x"] * f_[0] + e["y"] * f_[1]
        if abs(cu + hu - u0) < 0.3:
            left.append((cd, hd))
        if abs(cu - hu - u1) < 0.3:
            right.append((cd, hd))
    best = None
    for cl, hl in left:
        for cr, hr in right:
            if abs(cl - cr) < 0.8:
                dc = (cl + cr) / 2
                key = abs(dc - d_near) if d_near is not None else 0.0
                if best is None or key < best[0]:
                    best = (key, dc, 2 * max(hl, hr))
    return None if best is None else (best[1], best[2])


def _bay_foot(vert, u0, u1, sp) -> float:
    """3.64.161: where an arcade bay's recess starts below its arch: the
    lowest foot of the vertical lines drawn at both its sides that reach up
    to the arch's spring (None when the drawing has none)."""
    feet = []
    for edge in (u0, u1):
        zs = [za for (u, za, zb) in vert
              if abs(u - edge) < 0.08 and zb >= sp - 0.15 and
              za < sp - 0.3 and zb - za > 0.6]
        if not zs:
            return None
        feet.append(min(zs))
    return max(feet)


def _drop_opening(arch, rec) -> None:
    for lst in (arch["openings"], arch.get("_all_openings")):
        if lst is not None and rec in lst:
            lst.remove(rec)


def _niche_arches(arch, seen, bands, arcs, ops, D, st, vert=None) -> None:
    """3.64.157: the arcade's arches an elevation draws over the wall
    where no opening is — a pointed niche (the arch's recess) in the
    outer wall of the storey they spring from.
    3.64.161: the whole bay — the recess from the foot of its drawn sides
    (through the storeys below it, as a window over the window there) up to
    the apex; the small windows the plan has inside it give way."""
    import uuid
    f_, r_ = dirs_of(arch)[D]
    n_new = 0
    order = sorted(bands.items(), key=lambda kv: kv[1][0])
    for (u0, u1, sp, ap) in _arch_bays(arcs):
        lid = next((l for l, (a, b) in bands.items()
                    if a - 0.1 <= sp < b - 0.3 and ap <= b + 0.15), None)
        if lid is None:
            continue
        z0, z1 = bands[lid]
        cand = [(d2, w2, a0, a1) for w2, a0, a1, d2 in seen
                if w2["level"] == lid and not w2.get("rail")
                and a0 - 0.05 <= u0 and u1 <= a1 + 0.05]
        if not cand:
            continue
        d2, w2, a0, a1 = min(cand, key=lambda q: q[0])
        ax, ay = w2["a"]
        bx, by = w2["b"]
        ua = ax * r_[0] + ay * r_[1]
        ub = bx * r_[0] + by * r_[1]
        L = math.hypot(bx - ax, by - ay)
        if abs(ub - ua) < 0.5 or L < 0.5:
            continue
        foot = _bay_foot(vert or [], u0, u1, sp)
        if vert and foot is None:
            continue                 # no recess drawn down its sides: no bay
        start = max(foot, z0) if foot is not None else sp
        k_ = abs(ub - ua) / L
        sgn = 1.0 if ub > ua else -1.0

        def span(q, w=w2):
            qa = ua + (float(q["pos"]) - float(q["w"]) / 2) * sgn * k_
            qb = ua + (float(q["pos"]) + float(q["w"]) / 2) * sgn * k_
            return sorted((qa, qb))
        busy = False
        small = []
        for q in list(arch["openings"]):
            if q["wall"] != w2["id"]:
                continue
            qa, qb = span(q)
            qz0 = float(q.get("sill", 0)) + z0
            qz1 = qz0 + float(q["h"])
            if min(qb, u1) - max(qa, u0) <= 0.2 or qz0 >= ap or qz1 <= start:
                continue
            if q["kind"] != "door" and float(q["h"]) < 2.2 and \
                    qz0 >= start - 0.05 and qa >= u0 - 0.3 and qb <= u1 + 0.3:
                small.append(q)           # a small plan window: gives way
            else:
                busy = True
                break
        if busy:
            continue
        for q in small:
            _drop_opening(arch, q)
        uc = (u0 + u1) / 2
        cb = _bay_columns(arch, lid, f_, r_, u0, u1, d2)
        if cb is not None and not any(
                x.get("elev_cad") and x.get("name") == "Arcade (elevation)"
                and abs((x["a"][0] + x["b"][0]) / 2 * r_[0] +
                        (x["a"][1] + x["b"][1]) / 2 * r_[1] - uc) < 0.3 and
                x.get("level") == lid for x in arch["walls"]):
            dc, thick = cb
            sw = dict(w2)
            for kx in ("a", "b", "id", "rail", "curve", "arc", "bulge"):
                sw.pop(kx, None)
            wid = uuid.uuid4().hex[:8]
            pa = ((u0 - 0.1) * r_[0] + dc * f_[0],
                  (u0 - 0.1) * r_[1] + dc * f_[1])
            pb = ((u1 + 0.1) * r_[0] + dc * f_[0],
                  (u1 + 0.1) * r_[1] + dc * f_[1])
            sw.update({"kind": "line", "a": [round(pa[0], 4), round(pa[1], 4)],
                       "b": [round(pb[0], 4), round(pb[1], 4)],
                       "t": round(thick, 3), "id": wid, "level": lid,
                       "name": "Arcade (elevation)", "elev_cad": 1,
                       "align": "centre", "height": "level", "base": 0.0})
            _add_wall(arch, sw)
            _add_opening(arch, {
                "id": uuid.uuid4().hex[:8], "kind": "void", "wall": wid,
                "pos": round((u1 - u0 + 0.2) / 2, 4),
                "w": round(u1 - u0, 3), "sill": 0.0,
                "h": round(ap - z0, 3), "head": "arch", "arch": "pointed",
                "ring": "plain", "swing": "left", "style": "", "leaves": 1,
                "face": 1, "frame": "auto", "hl": 1,
                "name": "Arch (elevation)", "elev_cad": 1})
            n_new += 1
            cb = True
        else:
            cb = None
        pos = (uc - ua) / (ub - ua) * L
        dx, dy = (bx - ax) / L, (by - ay) / L
        nrm = (-dy, dx)                  # the face a niche's face=+1 opens to
        face = 1 if (nrm[0] * -f_[0] + nrm[1] * -f_[1]) > 0 else -1
        if cb is None:
            _add_opening(arch, {
                "id": uuid.uuid4().hex[:8], "kind": "void",
                "wall": w2["id"],
                "pos": round(pos, 4), "w": round(u1 - u0 - 0.1, 3),
                "sill": round(max(start - z0, 0.0), 3),
                "h": round(ap - start - 0.05, 3), "head": "arch",
                "arch": "pointed", "ring": "plain",
                "niche": {"d": 0.12, "face": face}, "swing": "left",
                "style": "", "leaves": 1, "face": 1, "frame": "auto",
                "hl": 1, "name": "Arch (elevation)", "elev_cad": 1})
            n_new += 1
        # the storeys below it: the recess goes on down to its foot
        if foot is not None and foot < z0 - 0.05:
            for lid2, (b0, b1) in order:
                if b1 > z0 + 0.01 or b1 <= foot + 1.0 or b0 < -0.1:
                    continue
                c2 = [(dd, w3, x0, x1) for w3, x0, x1, dd in seen
                      if w3["level"] == lid2 and not w3.get("rail")
                      and x0 - 0.05 <= u0 and u1 <= x1 + 0.05
                      and abs(dd - d2) < 1.0]
                if not c2:
                    continue
                dd, w3, x0, x1 = min(c2, key=lambda q: abs(q[0] - d2))
                ex0, ey0 = w3["a"]
                ex1, ey1 = w3["b"]
                va = ex0 * r_[0] + ey0 * r_[1]
                vb = ex1 * r_[0] + ey1 * r_[1]
                L3 = math.hypot(ex1 - ex0, ey1 - ey0)
                if abs(vb - va) < 0.5 or L3 < 0.5:
                    continue
                k3 = abs(vb - va) / L3
                lo = max(foot, b0)
                over = False
                for q in arch["openings"]:
                    if q["wall"] != w3["id"]:
                        continue
                    sg3 = 1.0 if vb > va else -1.0
                    qa = va + (float(q["pos"]) - float(q["w"]) / 2) * sg3 * k3
                    qb = va + (float(q["pos"]) + float(q["w"]) / 2) * sg3 * k3
                    qa, qb = sorted((qa, qb))
                    qz0 = float(q.get("sill", 0)) + b0
                    qz1 = qz0 + float(q["h"])
                    if min(qb, u1) - max(qa, u0) > 0.2 and qz1 > lo + 0.1 \
                            and qz0 < b1 - 0.1:
                        over = True
                        if q["kind"] != "door" and qz1 < b1 - 0.3 and \
                                qz0 <= lo + 0.3:      # the drawn frame goes on up
                            q["h"] = round(b1 - 0.12 - qz0, 3)
                        break
                if over:
                    continue
                sample = next((q for q in arch["openings"]
                               if q["kind"] == "void" and q["wall"] == w3["id"]),
                              None)
                rec = dict(sample) if sample else {
                    "kind": "void", "swing": "left", "style": "",
                    "leaves": 1, "face": 1, "frame": "auto", "hl": 1}
                rec.pop("niche", None)
                rec.pop("arch", None)
                rec.update({"id": uuid.uuid4().hex[:8], "wall": w3["id"],
                            "pos": round((uc - va) / (vb - va) * L3, 4),
                            "w": round(u1 - u0 - 0.1, 3),
                            "sill": round(lo - b0, 3),
                            "h": round(b1 - lo - 0.05, 3), "head": "flat",
                            "name": "Window (elevation)", "elev_cad": 1})
                _add_opening(arch, rec)
                n_new += 1
    if n_new:
        st["arches"] = st.get("arches", 0) + n_new


def _pointed_arcs(arcs, lo, hi, za_min, spring) -> bool:
    """3.64.157: the arcs over an opening (u from lo to hi) are the halves
    of a pointed head — each taller than it is wide (a round head's arc is
    half as high as it is wide)."""
    hit = [(ua, ub, za, zb) for (ua, ub, za, zb) in arcs
           if ua >= lo - 0.05 and ub <= hi + 0.05 and za > za_min - 0.3
           and ub - ua > 0.05]
    return bool(hit) and \
        sum(1 for (ua, ub, za, zb) in hit if (zb - za) > 1.2 * (ub - ua)) \
        >= max(1, len(hit) // 2)


def _tall_frames(ops, vert, arcs, bands, st, know_arcs=True, arch=None,
                 seen=None, D=None) -> set:
    """3.64.156: the windows an elevation draws over more than one storey
    (the prayer hall's tall arched windows, ground floor to the roof): each
    one's lower opening from its sill to its ceiling, the openings over it
    (the same place, next storeys) from the floor up, the last one to the
    frame's top (its arch). Returns the ids of the openings set."""
    done = set()
    order = sorted(bands.items(), key=lambda kv: kv[1][0])
    lvl_pos = {lid: n for n, (lid, _b) in enumerate(order)}
    for o, w, u0, u1, dep, behind_rail in ops:
        if behind_rail or id(o) in done:
            continue
        z0, z1 = bands.get(w["level"], (None, None))
        if z0 is None or u1 - u0 < 0.3:
            continue
        left = [(za, zb) for (u, za, zb) in vert
                if abs(u - u0) < 0.1 and z0 - 0.6 < za < z1 - 0.3 and
                zb > z1 + 0.3 and zb - za > 2.5]
        right = [(za, zb) for (u, za, zb) in vert
                 if abs(u - u1) < 0.1 and z0 - 0.6 < za < z1 - 0.3 and
                 zb > z1 + 0.3 and zb - za > 2.5]
        if not left or not right:
            continue
        bot = min(min(a for a, _b in left), min(a for a, _b in right))
        if o["kind"] == "door":
            # a door the plan draws where the elevation draws a window
            # (its frame stands off the floor): a window
            if bot < z0 + 0.5:
                continue
        spring = min(max(b for _a, b in left), max(b for _a, b in right))
        apex = max((zb for (ua, ub, za, zb) in arcs
                    if ua >= u0 - 0.15 and ub <= u1 + 0.15 and
                    za > bot + 0.5 and abs(za - spring) < 1.2), default=None)
        arched = know_arcs and apex is not None and apex > spring + 0.1
        pointed = arched and _pointed_arcs(arcs, u0 - 0.15, u1 + 0.15,
                                           bot + 0.5, spring)
        top = apex if arched else spring
        chain = [(o, w, z0, z1)]
        n = lvl_pos.get(w["level"])
        if n is None:
            continue
        zt = z1
        k = n + 1
        while top > zt + 0.25 and k < len(order):
            lid, (a, b) = order[k]
            nxt = None
            for o2, w2, v0, v1, dep2, br2 in ops:
                if w2["level"] != lid or o2["kind"] == "door" or br2:
                    continue
                ov = min(u1, v1) - max(u0, v0)
                if ov > 0.6 * min(u1 - u0, v1 - v0) and abs(dep2 - dep) < 1.5:
                    nxt = (o2, w2, a, b)
                    break
            if nxt is None and arch is not None and seen:
                nxt = _new_upper(arch, seen, lid, a, b, u0, u1, dep, D)
            if nxt is None:
                break
            chain.append(nxt)
            zt = b
            k += 1
        if len(chain) < 2:
            continue
        if o["kind"] == "door":
            o["kind"] = "window"
            o["elev_cad"] = 1
        for j, (o_, w_, a_, b_) in enumerate(chain):
            last = j == len(chain) - 1
            s_new = round(max(bot - a_, 0.0), 3) if j == 0 else 0.0
            if s_new < 0.08:
                s_new = 0.0
            head = min(top, b_ - 0.05) if last else b_ - 0.05
            h_new = round(head - a_ - s_new, 3)
            if h_new < 0.5:
                continue
            if abs(h_new - float(o_["h"])) > 0.03 or \
                    abs(s_new - float(o_.get("sill", 0.0) or 0.0)) > 0.03:
                o_["sill"], o_["h"] = s_new, h_new
                o_["elev_cad"] = 1
                st["openings"] += 1
            if last and arched and o_.get("head") != "arch":
                o_["head"] = "arch"
                o_["arch"] = "pointed" if pointed else \
                    o_.get("arch") or "semi"
                o_["elev_cad"] = 1
            elif last and arched and pointed and o_.get("arch") != "pointed":
                o_["arch"] = "pointed"           # 3.64.157: as drawn
                o_["elev_cad"] = 1
                st["openings"] += 1
            elif not last and (o_.get("head") == "arch" or o_.get("arch")):
                o_["head"] = "flat"
                o_.pop("arch", None)
            done.add(id(o_))
        st.setdefault("tall", 0)
        st["tall"] += 1
    return done


def _apply_view(doc, arch, D, ops, seen, vert, horiz, arcs, circ, marks,
                bands, st, know_arcs=True, careful=False) -> None:
    """What one elevation seen from side D says, set in the model: the
    openings' sills and heads (and arched / flat heads when the drawing's
    arcs are known), a gable's round window, glass railings, the parapets
    and void railings it does not draw. ``vert`` / ``horiz`` / … in model
    metres (u along the view, z absolute). ``st`` gathers the counts."""
    glass_names = {}
    hit_circ = set()
    tall_done = _tall_frames(ops, vert, arcs, bands, st, know_arcs, arch,
                             seen, D)
    if know_arcs and arch is not None and seen:
        try:
            _niche_arches(arch, seen, bands, arcs, ops, D, st, vert)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("elevread arches")
    for o, w, u0, u1, dep, behind_rail in ops:
        if id(o) in tall_done:
            continue
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
            o["arch"] = "pointed" if _pointed_arcs(arcs, lo, hi, sill, sill) \
                else o.get("arch") or "semi"
            ch = True
        elif arched and o["kind"] != "door" and \
                o.get("arch") in (None, "", "semi", "segmental") and \
                _pointed_arcs(arcs, lo, hi, sill, sill):
            o["arch"] = "pointed"       # 3.64.157: the head drawn pointed
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
    f_, r_ = dirs_of(arch)[D]
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


# =====================================================================
# 3.64.156: the towers an elevation draws — its minarets and its dome
# =====================================================================
def _skyline(segs, zmin, step=0.05):
    """(u0, step, tops): the highest line over each ``step`` of u, from
    the lines [(u0, z0, u1, z1)] that reach over ``zmin``."""
    import numpy as np
    S = [s for s in segs if max(s[1], s[3]) > zmin]
    if not S:
        return None
    ulo = min(min(s[0], s[2]) for s in S)
    uhi = max(max(s[0], s[2]) for s in S)
    top = np.full(int((uhi - ulo) / step) + 2, -1e9)
    for a, b, c, d in S:
        i0 = int((min(a, c) - ulo) / step)
        i1 = int((max(a, c) - ulo) / step)
        top[i0:i1 + 1] = np.maximum(top[i0:i1 + 1], max(b, d))
    return ulo, step, top


def _widths(seg, z0, z1, step):
    """[(z, width of the part of ``seg`` standing at least that high)]."""
    import numpy as np
    out = []
    for z in np.arange(z0, z1, 0.05):
        ii = np.nonzero(seg >= z)[0]
        out.append((float(z), (ii[-1] - ii[0] + 1) * step if len(ii) else 0.0))
    return out


def towers(segs, z_top, step=0.05) -> dict:
    """What stands over the roof line in an elevation: {"roof": z,
    "minarets": [{"u", "top", "tops": [balcony tops], "b"}], "domes":
    [{"u", "d", "w0", "z_a", "tiers": [...], "z_d", "z_s", "z_t", "top"}]}.
    ``segs``: the building's lines [(u0, z0, u1, z1)] in metres (z over
    the model's zero), ``z_top``: the model's own roof top."""
    import numpy as np
    sk = _skyline(segs, z_top - 0.9, step)
    if sk is None:
        return {}
    ulo, step, top = sk
    near = top[(top > z_top - 0.7) & (top < z_top + 1.0)]
    zp = float(np.median(near)) if len(near) > 20 else float(z_top)
    idx = np.nonzero(top > zp + 0.8)[0]
    if not len(idx):
        return {"roof": zp, "minarets": [], "domes": []}
    groups, st, pv = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - pv > 6:
            groups.append((st, pv))
            st = i
        pv = i
    groups.append((st, pv))
    out = {"roof": zp, "minarets": [], "domes": []}
    for a, b in groups:
        seg = top[a:b + 1]
        peak = float(seg.max())
        ws = _widths(seg, zp + 0.9, peak, step)
        if not ws:
            continue
        w_low = ws[0][1]
        pk = np.nonzero(seg >= peak - 0.1)[0]
        u_c = ulo + (a + float(pk.mean()) + 0.5) * step
        if peak - zp >= 6.0 and w_low < 5.0:
            # the balconies: where the width falls by 0.25 m or more
            tops, run, last = [], 0.0, None
            for i in range(1, len(ws)):
                dw = ws[i - 1][1] - ws[i][1]
                if dw > 0.01:
                    if last is None or i - last > 10:
                        run = 0.0
                    run += dw
                    last = i
                    if run >= 0.25 and ws[i][0] < peak - 1.4 and \
                            (not tops or ws[i][0] - tops[-1] > 1.0):
                        tops.append(ws[i][0])
                        run = 0.0
            out["minarets"].append({"u": u_c, "top": peak, "tops": tops,
                                    "w": w_low, "z0": float(zp)})
        elif 0.8 <= peak - zp < 3.5 and 1.2 <= w_low < 3.2 and \
                (b - a) * step < 3.4:
            out.setdefault("kiosks", []).append(
                {"u": u_c, "w": w_low, "top": peak, "z0": float(zp)})
        elif 1.0 <= peak - zp < 12.0 and w_low >= 3.0:
            w0 = ws[0][1]
            z_a = next((z for z, w in ws if w < 0.97 * w0), None)
            if z_a is None:
                continue
            # the drum: the longest run of one width after the tiers
            runs, cur = [], [ws[0][0], ws[0][1], ws[0][0]]
            for z, w in ws[1:]:
                if abs(w - cur[1]) < 0.06:
                    cur[2] = z
                else:
                    runs.append(cur)
                    cur = [z, w, z]
            runs.append(cur)
            ru = [r for r in runs if r[0] >= z_a - 0.01 and r[1] < 0.97 * w0
                  and r[1] > 1.5]
            drum = max(ru, key=lambda r: r[2] - r[0]) if ru else None
            tiers_z = [r for r in ru if drum and r[0] < drum[0]
                       and r[1] > drum[1] + 0.1]
            z_s = z_t = None
            if drum:
                z_d = drum[0]
                z_s = drum[2]
                # the shell: from the drum's top until the width falls to
                # a rod (under 1 m)
                z_t = next((z for z, w in ws if z > z_s and w < 1.0), peak)
            else:
                z_d = z_a
            if z_s is None:
                continue
            out["domes"].append({
                "u": u_c, "w0": w0, "z_a": z_a, "z_d": z_d, "z_s": z_s,
                "z_t": z_t, "top": peak, "tiers": len(tiers_z),
                "d": drum[1] if drum else w0, "z0": float(zp)})
    return out


def _shaft_width(segs, u_c, zp, half=3.0):
    """The square shaft's side at the roof line: the outermost verticals
    near ``u_c`` that rise from the roof line."""
    us = []
    for a, b, c, d in segs:
        if abs(a - c) < 0.01 and abs(a - u_c) < half and \
                min(b, d) < zp + 1.0 and max(b, d) > zp + 3.0 and \
                abs(b - d) > 2.0:
            us.append(a)
    return (max(us) - min(us)) if len(us) >= 2 else None


def store_towers(doc, tw, segs, el_lvl=None, pri=0, r_vec=None,
                 f_vec=None, side=None) -> dict:
    """Keeps what the elevation says of the minarets and the dome in
    ``doc["elev_towers"]`` (in the model's metres over its zero) and sets
    them on the minarets / dome that stand."""
    spec = doc.setdefault("elev_towers", {})
    zp = float(tw.get("roof") or 0.0)
    if zp and 8.0 < zp < 80.0:
        spec["parapet_top"] = round(zp, 3)
    ks = tw.get("kiosks") or []
    if len(ks) >= 2:
        k0 = ks[0]
        hk = max(float(k["top"]) - float(k["z0"]) for k in ks)
        w_ = float(sorted(k["w"] for k in ks)[len(ks) // 2])
        d_ = round(max(0.8 * w_, 0.8), 3)
        fh = 0.4
        spec["kiosk"] = {"d": d_, "base_w": round(w_ / d_, 3),
                         "base_h": round(max(hk - d_ / 2 - fh, 0.2), 3),
                         "finial_h": fh, "n": len(ks), "_pri": pri} \
            if not spec.get("kiosk") or (pri, len(ks)) >= (
                spec["kiosk"].get("_pri", 0), spec["kiosk"].get("n", 0)) \
            else spec["kiosk"]
        _ = k0
    ms = [m for m in tw.get("minarets") or [] if len(m["tops"]) >= 2]
    if ms and r_vec and f_vec and side:     # 3.64.162: where each elevation
        spec.setdefault("minaret_views", {})[side] = {   # sees them
            "us": sorted(round(float(q["u"]), 3) for q in ms),
            "r": [round(float(r_vec[0]), 6), round(float(r_vec[1]), 6)]}
    if ms:
        m = max(ms, key=lambda r: (len(r["tops"]), r["top"]))
        b = _shaft_width(segs, m["u"], zp)
        new = {"top": round(float(m["top"]), 3),
               "stops": [round(float(t) - 1.2, 3) for t in m["tops"]],
               "b": round(float(b), 3) if b and 1.0 <= b <= 4.0 else None,
               "_pri": pri, "us": sorted(round(float(q["u"]), 3)
                                         for q in ms)}
        if r_vec:
            new["r"] = [round(float(r_vec[0]), 6), round(float(r_vec[1]), 6)]
        old = spec.get("minaret")
        # (one elevation sees more of it than another: the fuller kept;
        # the front's before the sides')
        if not old or (pri, len(new["stops"]), new["top"]) >= \
                (old.get("_pri", 0), len(old["stops"]), old["top"]):
            spec["minaret"] = new
    dm = [d for d in tw.get("domes") or [] if d["d"] >= 2.0]
    if dm:
        d = max(dm, key=lambda r: r["z_s"] - r["z0"])
        R = float(d["d"]) / 2
        new = {
            "d": round(float(d["d"]), 3),
            "base_h": round(max(float(d["z_a"] - d["z0"]), 0.0), 3),
            "base_w": round(float(d["w0"] / d["d"]), 3),
            "steps": int(min(max(d["tiers"], 0), 6)),
            "step_h": round(float((d["z_d"] - d["z_a"]) / d["tiers"]), 3)
            if d["tiers"] else 0.45,
            "drum": round(max(float(d["z_s"] - d["z_d"]), 0.0), 3),
            "rise": round(min(max(float((d["z_t"] - d["z_s"]) / (2 * R)),
                                  0.2), 1.2), 3),
            "finial_h": round(max(float(d["top"] - d["z_t"]), 0.3), 3),
            "_up": round(float(d["z_s"] - d["z0"]), 3), "_pri": pri}
        old = spec.get("dome")
        if not old or (pri, new["_up"]) >= (old.get("_pri", 0),
                                            old.get("_up", 0.0)):
            spec["dome"] = new
    return spec


def _minaret_depth(doc, spec) -> int:
    """3.64.162: the minarets' place front to back from the side
    elevations (their u runs along the front's depth): all the minarets
    set to the depth the sides draw them at (one depth drawn: both; as many
    depths as minarets: in the order they stand). How many moved."""
    from . import refelev as RE
    fv = RE.front_vec(doc)
    if not fv:
        return 0
    fv = (float(fv[0]), float(fv[1]))
    ds = []
    for _side, v in (spec.get("minaret_views") or {}).items():
        r_ = v["r"]
        c = r_[0] * fv[0] + r_[1] * fv[1]
        if abs(c) < 0.95:                    # not a side seen along the depth
            continue
        ds.append(sorted(c * float(u) for u in v["us"]))
    if not ds:
        return 0
    depths = ds[0]
    ms = [m for m in doc.get("minarets") or []
          if str(m.get("id", "")).startswith("auto-")]
    if not ms:
        return 0
    cur = sorted(ms, key=lambda m: m["x"] * fv[0] + m["y"] * fv[1])
    if len(depths) == 1:
        tgt = [depths[0]] * len(cur)
    elif len(depths) == len(cur):
        tgt = depths
    else:
        return 0
    n = 0
    for m, dt in zip(cur, tgt):
        d0 = float(m["x"]) * fv[0] + float(m["y"]) * fv[1]
        if abs(dt - d0) > 0.3:
            m["x"] = round(float(m["x"]) + (dt - d0) * fv[0], 4)
            m["y"] = round(float(m["y"]) + (dt - d0) * fv[1], 4)
            n += 1
    return n


def spec_all(doc) -> dict:
    """The elevations' minarets and dome set on the model's (the minarets
    the plans / the look made, the roof plan's biggest dome)."""
    from . import project as PJ
    spec = doc.get("elev_towers") or {}
    rep = {}
    arch = doc["arch"]
    el = dict(zip([lv["id"] for lv in arch["levels"]], PJ.elevations(arch)))
    ms = spec.get("minaret")
    if ms:
        n = 0
        for m in doc.get("minarets") or []:
            if not str(m.get("id", "")).startswith("auto-"):
                continue
            z0 = el.get(m.get("level"))
            if z0 is None:
                continue
            h = float(ms["top"]) - z0
            if h < 6.0:
                continue
            m["h"] = round(h, 3)
            st = [round(s - z0, 3) for s in ms["stops"]]
            if st and st[0] >= 1.0 and all(b > a for a, b in
                                           zip(st, st[1:])):
                m["stops"] = st
                m["base_h"] = st[0]
                m["galleries"] = min(max(len(st) - 1, 1), 3)
            if ms.get("b"):
                m["b"] = float(ms["b"])
            us_, r_ = ms.get("us") or [], ms.get("r")
            if us_ and r_ and ms.get("_pri"):      # where the front puts it
                u_m = float(m["x"]) * r_[0] + float(m["y"]) * r_[1]
                tgt = min(us_, key=lambda q: abs(q - u_m))
                if 0.3 < abs(tgt - u_m) <= 4.5:
                    m["x"] = round(float(m["x"]) + (tgt - u_m) * r_[0], 4)
                    m["y"] = round(float(m["y"]) + (tgt - u_m) * r_[1], 4)
            n += 1
        if n:
            rep["minarets"] = n
        mv = _minaret_depth(doc, spec)
        if mv:
            rep["minarets_depth"] = mv
    kd = spec.get("kiosk")
    if kd:
        cands = [d for d in doc.get("domes") or []
                 if str(d.get("id", "")).startswith("cad-")]
        if cands:
            big = max(float(d["d"]) for d in cands)
            n = 0
            for d in cands:
                if float(d["d"]) >= 0.75 * big and float(d["d"]) >= 4.0:
                    continue
                d.update({"d": kd["d"], "base_w": kd["base_w"],
                          "base_h": kd["base_h"], "finial_h": kd["finial_h"],
                          "stand": "walls", "steps": 0, "drum": 0.0,
                          "kind": "hemi", "rise": 0.0})
                d.pop("base_poly", None)
                n += 1
            if n:
                rep["kiosk_domes"] = n
    pt = spec.get("parapet_top")
    if pt:
        n = 0
        for w in arch["walls"]:
            if not str(w.get("name", "")).lower().startswith("roof parapet") \
                    or w.get("kind", "line") != "line" or w.get("rail"):
                continue
            z0 = el.get(w.get("level"))
            if z0 is None or z0 > pt - 0.8:
                continue
            try:
                h0 = float(w.get("height", 1.0))
            except (TypeError, ValueError):
                continue
            h1 = round(pt - 0.1 - z0 - float(w.get("base", 0.0) or 0.0), 3)
            if h0 + 0.2 < h1 <= 4.5:
                w["height"] = h1
                n += 1
        if n:
            rep["parapets_raised"] = n
    dm = spec.get("dome")
    if dm:
        cands = [d for d in doc.get("domes") or []
                 if str(d.get("id", "")).startswith("cad-")]
        if cands:
            big = max(float(d["d"]) for d in cands)
            for d in cands:
                if float(d["d"]) < 0.75 * big or float(d["d"]) < 4.0:
                    continue
                d.update({k: dm[k] for k in ("d", "base_h", "base_w", "steps",
                                             "step_h", "drum", "rise",
                                             "finial_h") if k in dm})
                d["kind"] = "hemi"
                d.pop("base_poly", None)
                rep["dome"] = d["id"]
    return rep
