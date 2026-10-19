# SPDX-License-Identifier: GPL-3.0-or-later
"""Staircases from the plans, floor to floor, with their wells cut in the
slabs — and terraces and balconies on any floor.

Where a stair is: a closed outline (or the lines) on a stair layer of the
CAD plan, else a room named STAIR… on the level, else the stair of the
floor below (a stair core goes up the building). A long, narrow well
gets one straight flight; a squarer one a dog-leg — two flights side by
side and a half landing. Risers about 175 mm, goings up to 300 mm.

``doc["stairs"]`` = [{"id", "level" (from), "to", "corners" [4 pts],
                       "kind": "straight" | "dogleg", "risers", "rise",
                       "going", "flip": bool}]
"""
from __future__ import annotations

import math
import uuid

RISER = 0.175
GOING_MAX = 0.30
GOING_MIN = 0.22
STAIR_COLOR = (0.74, 0.73, 0.70)


# ---- where -----------------------------------------------------------------------------
def rect_of(pts):
    """(centre, u (long axis), w (across), L (along)) of the smallest
    rectangle round ``pts``."""
    from shapely.geometry import MultiPoint
    r = MultiPoint([tuple(p[:2]) for p in pts]).minimum_rotated_rectangle
    c = list(r.exterior.coords)[:4]
    e0 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e1 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l0, l1 = math.hypot(*e0), math.hypot(*e1)
    if l0 >= l1:
        u, L, w = (e0[0] / l0, e0[1] / l0), l0, l1
    else:
        u, L, w = (e1[0] / l1, e1[1] / l1), l1, l0
    if u[0] < -1e-9 or (abs(u[0]) < 1e-9 and u[1] < 0):
        u = (-u[0], -u[1])                    # one way round, always
    cx = sum(p[0] for p in c) / 4
    cy = sum(p[1] for p in c) / 4
    return (cx, cy), u, w, L


def corners_of(centre, u, w, L):
    v = (-u[1], u[0])
    cx, cy = centre
    return [[round(cx + a * u[0] * L / 2 + b * v[0] * w / 2, 4),
             round(cy + a * u[1] * L / 2 + b * v[1] * w / 2, 4)]
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def from_cad(pl, match_stairs) -> list:
    """Stair wells in a placed drawing: closed outlines on the stair
    layers (2–40 m²), else the box round the stair layers' lines."""
    out = []
    for lp in pl["loops"]:
        if match_stairs(lp["layer"]):
            a = _area(lp["pts"])
            if 2.0 <= a <= 40.0:
                out.append(lp["pts"])
    if not out:
        lay = pl["layers"]
        segs = [s for s in pl["segs"] if match_stairs(lay[s[4]])]
        if len(segs) >= 6:
            pts = [(s[0], s[1]) for s in segs] + [(s[2], s[3]) for s in segs]
            _c, _u, w, L = rect_of(pts)
            if 2.0 <= w * L <= 40.0:
                out.append(pts)
    return [corners_of(*rect_of(p)) for p in out]


def from_rooms(arch, lid) -> list:
    """Rooms named STAIR… (STAIRCASE, STAIRS, ESCALERA…) on the level."""
    from .engine import spaces
    out = []
    try:
        rooms = spaces.of_level(arch, lid)
    except Exception:  # noqa: BLE001
        return out
    for r in rooms:
        n = str(r.get("name", "")).upper()
        if any(k in n for k in ("STAIR", "ESCAL", "ESCADA", "TREPP",
                                "SCALA")) and 2.0 <= r["area"] <= 60.0:
            poly = r.get("poly")
            pts = list(poly.exterior.coords)[:-1] if poly is not None else None
            if pts:
                out.append(corners_of(*rect_of(pts)))
    return out


def _area(pts):
    return abs(0.5 * sum(a[0] * b[1] - b[0] * a[1]
                         for a, b in zip(pts, list(pts[1:]) + [pts[0]])))


# ---- how --------------------------------------------------------------------------------
def n_risers(H, riser=RISER) -> int:
    """The number of risers for a storey H with risers no higher than
    ``riser`` (7" by default)."""
    return max(int(math.ceil(H / max(float(riser), 0.10) - 1e-6)), 2)


def design(corners, H, flip=False, riser=RISER, going=None,
           n=None) -> dict:
    """Risers, going and kind for a well and a storey height H: risers no
    higher than ``riser``, treads ``going`` deep (11" by default) unless the
    well is too short for them (then as deep as it allows); ``n`` risers
    when given."""
    _c, _u, w, L = rect_of(corners)
    n = int(n) if n else n_risers(H, riser)
    rise = H / n
    want = float(going) if going else None
    straight_run = (n - 1) * (want or GOING_MIN)
    if L >= straight_run + 0.9 or w < 1.6:
        g = (L - 0.9) / (n - 1)
        g = min(want, g) if want else min(GOING_MAX, g)
        return {"kind": "straight", "risers": n, "rise": round(rise, 4),
                "going": round(max(g, 0.15), 4), "flip": flip}
    dl = w / 2                                   # half landing, square
    n1 = int(math.ceil(n / 2))
    g = (L - dl) / max(n1 - 1, 1)
    g = min(want, g) if want else min(GOING_MAX, g)
    return {"kind": "dogleg", "risers": n, "rise": round(rise, 4),
            "going": round(max(g, 0.15), 4), "flip": flip}


def redesign(st, new) -> dict:
    """A stair's new riser / tread / number of risers, as typed in its
    edit dialog: the storey height stays; a new number of risers sets the
    riser height, a new riser height sets the number (risers no higher);
    a designed stair re-lays its flights with the new tread in its well. A
    traced stair (drawn in the CAD) keeps its tread lines."""
    H = float(st.get("rise", 0.175)) * int(st.get("risers", 18))
    out = dict(new)
    n0, n1 = int(st.get("risers", 0)), int(new.get("risers", 0) or 0)
    r0, r1 = float(st.get("rise", 0)), float(new.get("rise", 0) or 0)
    if n1 and n1 != n0:
        n = n1
    elif r1 and abs(r1 - r0) > 1e-4:
        n = n_risers(H, r1)
    else:
        n = n0
    n = max(n, 2)
    out["risers"] = n
    out["rise"] = round(H / n, 4)
    if not st.get("traced") and st.get("corners"):
        d = design(st["corners"], H, st.get("flip", False),
                   going=float(new.get("going") or st.get("going", 0.2794)),
                   n=n)
        out.update(kind=d["kind"], going=d["going"])
    else:
        out["going"] = st.get("going")
    return out


def steps(st, z0) -> list:
    """[(name, footprint [4 pts], z bottom, z top)] — the stair as blocks:
    each step from the floor up to its tread (a solid stair), and the
    landing."""
    (cx, cy), u, w, L = rect_of(st["corners"])
    v = (-u[1], u[0])
    if st.get("flip"):
        v = (-v[0], -v[1])
    o = (cx - u[0] * L / 2 - v[0] * w / 2, cy - u[1] * L / 2 - v[1] * w / 2)

    def P(a, b):                     # a along u from the start, b across
        return (o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b)

    def quad(a0, a1, b0, b1):
        return [P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b1)]
    n, rise, g = st["risers"], st["rise"], st["going"]
    out = []
    if st["kind"] == "straight":
        start = max((L - (n - 1) * g) / 2, 0.0)  # centred in the well
        for k in range(1, n):
            out.append((f"Step {k}", quad(start + (k - 1) * g,
                                          start + k * g, 0.0, w),
                        z0, z0 + k * rise))
        return out
    dl = w / 2
    n1 = int(math.ceil(n / 2))
    n2 = n - n1
    for k in range(1, n1):                       # first flight, side 0…w/2
        out.append((f"Step {k}", quad((k - 1) * g, k * g, 0.0, w / 2 - 0.01),
                    z0, z0 + k * rise))
    out.append(("Landing", quad(L - dl, L, 0.0, w), z0, z0 + n1 * rise))
    for k in range(1, n2):                       # second flight, back
        a1 = L - dl - (k - 1) * g
        out.append((f"Step {n1 + k}", quad(a1 - g, a1, w / 2 + 0.01, w),
                    z0, z0 + (n1 + k) * rise))
    return out


# ---- doing it ---------------------------------------------------------------------------
def auto(doc, cad=None, flip=False) -> dict:
    """Stairs on every floor, as the plans draw them: the tread lines of
    each level's stair layer give the flights (their width, risers, turn
    and landings — completed with a return flight when the plan shows the
    lower flight only); where the plan has no stair lines, a stair well
    (an outline on the stair layer, a room named STAIR…) gets a standard
    stair; a level with neither takes the floor below's. Each stair goes
    up to the next level and cuts its well in that level's slab. Replaces
    the stairs before (and the wells they cut)."""
    from shapely.geometry import Point

    from . import project as PJ
    from .engine import model as M
    from .engine import spaces
    from .engine import structure as S
    arch = doc["arch"]
    stt0 = doc.get("settings") or {}
    _uncut(doc)
    # what each stair set for itself survives a re-make (by where it is)
    kept = {}
    for s0 in doc.get("stairs") or []:
        cs0 = s0.get("corners") or []
        if cs0 and any(s0.get(k) for k in OWN):
            kept[(s0["level"], round(sum(p[0] for p in cs0) / len(cs0), 1),
                  round(sum(p[1] for p in cs0) / len(cs0), 1))] = \
                {k: s0[k] for k in OWN if s0.get(k)}
    relaid = []                 # flights turned by hand: by the stair's foot
    for s0 in doc.get("stairs") or []:
        if s0.get("foot0") and (s0.get("turns") is not None or
                                s0.get("rot")):
            relaid.append((s0["level"], tuple(s0["foot0"]),
                           s0.get("turns"), s0.get("rot", 0.0),
                           s0.get("counts")))
    doc["stairs"] = []
    levels = arch["levels"]
    info = S.levels_info(arch, M.elevations)
    cad = cad if cad is not None else doc.get("stair_cad") or {}
    made, cut, traced_n = 0, 0, 0
    carried = []
    for i, lv in enumerate(levels):
        up = levels[i + 1] if i + 1 < len(levels) else None
        if up is not None and not any(
                w["level"] == up["id"] for w in arch["walls"]) and \
                not any(e["level"] == up["id"] for e in arch["structure"]):
            up = None                       # nothing built up there yet
        if up is None:
            # the top floor (or nothing above yet): its stairs as the plan
            # draws them, one storey high — no well to cut up there
            if str(lv.get("name", "")).strip().lower() == "roof" or \
                    not any(w["level"] == lv["id"] for w in arch["walls"]):
                continue
            H = float(lv.get("height") or 3.0)
        else:
            H = info[up["id"]]["z0"] - info[lv["id"]]["z0"]
        n_need = n_risers(H, float(stt0.get("stair_riser", 0.1778)))
        recs = []
        try:
            chains = PJ.stair_trace(doc, lv["id"])
        except Exception:  # noqa: BLE001
            chains = []
        try:
            rooms = spaces.of_level(arch, lv["id"])
        except Exception:  # noqa: BLE001
            rooms = []
        dn_only = 0
        for flights in chains:
            if sum(len(f["lines"]) for f in flights) < 3:
                continue
            if flights and flights[0].get("_dn_only") and i > 0 and \
                    stt0.get("stair_dn_skip", True):
                dn_only += 1          # the stair from below, going DN
                continue
            m = _mid(flights[0]["lines"][0])
            room = next((r["poly"] for r in rooms
                         if r["poly"].buffer(0.3).contains(Point(m))), None)
            # the plan's own risers when they climb the storey at a
            # riser of 8" at most: no return flight invented beside them
            have = sum(len(f["lines"]) for f in flights)
            n_use = have if have and H / have <= 0.2032 else n_need
            diag = flights[0].get("_diag") if flights else None
            fl, lands = complete(flights, n_use, room)
            if diag:
                try:                 # winders drawn on a turning landing
                    fl, lands = winders(fl, lands, diag)
                except Exception:  # noqa: BLE001
                    from .host import log_error
                    log_error("stairs.winders")
            n = sum(len(f["lines"]) for f in fl)
            st = {"traced": True, "flights": [
                dict({"lines": [[list(a), list(b)] for a, b in f["lines"]],
                      "d": list(f["d"]), "w": f["w"], "g": f["g"]},
                     **({"winder": True} if f.get("winder") else {}))
                for f in fl],
                "landings": lands, "risers": n, "rise": round(H / n, 4),
                "going": round(fl[0]["g"], 4), "kind": "traced"}
            st["corners"] = outline_of(st)
            recs.append(st)
            traced_n += 1
        if not recs and dn_only:      # only the stair from below: none
            carried = []              # climbs on from this floor
            continue
        if not recs:
            wells = list(cad.get(lv["id"]) or []) or \
                from_rooms(arch, lv["id"])
            for corners in wells:
                recs.append(dict(design(
                    corners, H, flip,
                    float(stt0.get("stair_riser", 0.1778)),
                    float(stt0.get("stair_going", 0.2794))),
                    corners=corners))
        if not recs and carried:                  # the floor below's stair
            recs = [dict(r) for r in carried]
            for r in recs:
                if r.get("traced"):
                    n = r["risers"]
                    r["rise"] = round(H / n, 4)
        if recs:
            carried = recs
        for r in recs:
            r = dict(r, id=uuid.uuid4().hex[:8], level=lv["id"],
                     to=up["id"] if up is not None else None)
            cs1 = r.get("corners") or []
            if cs1 and kept:
                r.update(kept.get((lv["id"], round(sum(
                    p[0] for p in cs1) / len(cs1), 1), round(sum(
                        p[1] for p in cs1) / len(cs1), 1)), {}))
            if relaid:
                ft = foot_of(r)
                hit = next((x for x in relaid if x[0] == lv["id"] and ft
                            and math.dist(ft, x[1]) < 0.6), None)
                if hit is not None:
                    try:
                        drop_holes_over(doc, r)   # the CAD's hole there
                        r = relay(r, hit[2], hit[3], hit[4])
                        r["foot0"] = list(hit[1])
                    except Exception:  # noqa: BLE001
                        pass
            doc["stairs"].append(r)
            made += 1
            # the well: only over the steps that need it — 7'-0" clear
            # over every step (the lower steps stay under the slab)
            well = r["corners"]
            wm = stt0.get("stair_well", "railing")
            if wm != "outline" and stt0.get("stair_headroom_cut", True):
                hc = headroom_cut(r, H, float(stt0.get("slab_t", 0.15)),
                                  float(stt0.get("stair_head", HEADROOM)),
                                  wm)
                if hc:
                    well = hc
            if PJ.slab_on_top(doc):
                # the slab over this floor is its own: the well in it
                cut += _cut(arch, lv["id"], well)
            elif up is not None:
                cut += _cut(arch, up["id"], well)
    return {"stairs": made, "cuts": cut, "traced": traced_n}


def _cut(arch, lid, corners) -> int:
    """The well cut in the level's slab(s) that hold it."""
    from shapely.geometry import Polygon
    hole = Polygon(corners)
    n = 0
    for s in arch["structure"]:
        if s["type"] != "slab" or s["level"] != lid:
            continue
        outer = Polygon(s["corners"])
        if not outer.is_valid:
            outer = outer.buffer(0)
        part = outer.buffer(-0.02).intersection(hole)
        if part.is_empty or part.area < 0.5:
            continue
        holes = s.setdefault("holes", [])
        if any(Polygon(h).intersects(part) for h in holes):
            # an opening drawn there already (the CAD's stair hole):
            # widened to the whole well
            from shapely.ops import unary_union as _uu
            merged = _uu([part])
            keep = []
            for h in holes:
                if Polygon(h).intersects(merged):
                    merged = merged.union(Polygon(h))
                else:
                    keep.append(h)
            merged = merged.convex_hull.intersection(outer.buffer(-0.02))
            holes[:] = keep
            part = merged
        geom = getattr(part, "geoms", [part])
        for gpart in geom:
            if gpart.geom_type == "Polygon" and gpart.area >= 0.5:
                holes.append([[round(x, 4), round(y, 4)]
                              for x, y in list(gpart.exterior.coords)[:-1]])
                n += 1
    return n


HEADROOM = 2.1336            # 7'-0" clear over every step


def refit_heights(doc) -> int:
    """Every stair's risers re-spaced to its storey's height now (the
    floors and levels changed): the same steps, the risers taller or
    shorter so the stair still lands on the floor above. How many."""
    from .engine import model as M
    from .engine import structure as S
    arch = doc["arch"]
    info = S.levels_info(arch, M.elevations)
    n = 0
    for st in doc.get("stairs") or []:
        lv = info.get(st.get("level"))
        if lv is None:
            continue
        up = info.get(st.get("to")) if st.get("to") else None
        H = (up["z0"] - lv["z0"]) if up else float(lv["height"])
        k = int(st.get("risers") or 0)
        if k <= 0 or H <= 0:
            continue
        r = round(H / k, 4)
        if abs(r - float(st.get("rise") or 0)) > 1e-4:
            st["rise"] = r
            n += 1
    return n


def cut_well(doc, r) -> int:
    """The well of stair ``r`` cut in the slab over it (as «Stairs» does)."""
    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    arch = doc["arch"]
    stt0 = doc.get("settings") or {}
    info = S.levels_info(arch, M.elevations)
    lv = next((x for x in arch["levels"] if x["id"] == r["level"]), None)
    if lv is None:
        return 0
    up = next((x for x in arch["levels"] if x["id"] == r.get("to")), None)
    if up is not None:
        H = info[up["id"]]["z0"] - info[lv["id"]]["z0"]
    else:
        H = float(lv.get("height") or 3.0)
    well = r["corners"]
    wm = stt0.get("stair_well", "railing")
    if wm != "outline" and stt0.get("stair_headroom_cut", True):
        hc = headroom_cut(r, H, float(stt0.get("slab_t", 0.15)),
                          float(stt0.get("stair_head", HEADROOM)), wm)
        if hc:
            well = hc
    if PJ.slab_on_top(doc):
        return _cut(arch, lv["id"], well)
    if up is not None:
        return _cut(arch, up["id"], well)
    return 0


def drop_holes_over(doc, st) -> int:
    """The slab openings over stair ``st``'s outline (its well, a stair hole
    drawn in the CAD merged with it) closed — on its level and the next —
    before the stair is laid out again somewhere else."""
    from shapely.geometry import Polygon
    cs = st.get("corners") or []
    if len(cs) < 3:
        return 0
    o = Polygon(cs).buffer(0.05)
    if not o.is_valid:
        o = o.buffer(0)
    lids = {st.get("level"), st.get("to")}
    n = 0
    for s in doc["arch"]["structure"]:
        if s["type"] != "slab" or s["level"] not in lids:
            continue
        keep = []
        for h in s.get("holes") or []:
            try:
                hp = Polygon(h)
                if not hp.is_valid:
                    hp = hp.buffer(0)
                share = hp.intersection(o).area
            except Exception:  # noqa: BLE001
                keep.append(h)
                continue
            if hp.area >= 0.3 and share >= 0.3 * hp.area:
                n += 1
                continue
            keep.append(h)
        s["holes"] = keep
    return n


def restair(doc, sid, turns, rot, counts) -> dict:
    """Stair ``sid`` laid again by hand: ``counts`` risers in each flight
    (their number the number of flights), ``turns`` how each flight leaves
    the landing before it, the whole stair turned to ``rot`` degrees round
    its foot. The landings follow the turns; the slab's well is cut again.
    Kept through «Stairs» (made again from the CAD) by the stair's foot."""
    st = next((x for x in doc.get("stairs") or [] if x.get("id") == sid),
              None)
    if st is None:
        raise ValueError("stair not found")
    foot0 = st.get("foot0") or foot_of(st)
    d_rot = float(rot or 0.0) - float(st.get("rot") or 0.0)
    new = relay(st, turns, d_rot, counts)
    new["rot"] = float(rot or 0.0)
    new["foot0"] = [round(foot0[0], 4), round(foot0[1], 4)]
    _uncut(doc, [st])
    drop_holes_over(doc, st)               # its old opening, upstairs too
    i = doc["stairs"].index(st)
    doc["stairs"][i] = new
    cut_well(doc, new)
    return new


def unstair(doc, sid) -> bool:
    """The hand turns of stair ``sid`` forgotten (back to the CAD's)."""
    st = next((x for x in doc.get("stairs") or [] if x.get("id") == sid),
              None)
    if st is None:
        return False
    for k in ("turns", "rot", "counts", "foot0"):
        st.pop(k, None)
    return True


WELL_MODES = [("railing", "Following the railing (whole flights that "
                         "need headroom, their landings)"),
              ("headroom", "Only over the steps short of 7'-0\" headroom"),
              ("outline", "The whole stair outline")]


def headroom_cut(st, H, slab_t, head=HEADROOM, mode="headroom"):
    """The part of the stair's outline the slab above must leave open so
    every step and landing keeps ``head`` clear under the slab's soffit:
    the treads (and landings) higher than (H − slab − head) — the lower
    steps, with headroom to spare, stay under the slab. Corners [[x, y]]
    or None (cut the whole outline)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    try:
        flights, lands = as_flights(st)
        n = int(st.get("risers") or sum(len(f["lines"]) for f in flights))
        rise = float(st.get("rise") or (H / max(n, 1)))
        cut_z = H - float(slab_t) - float(head)
        parts, k = [], 0
        for f in flights:
            d = f["d"]
            g = float(f.get("g") or st.get("going") or 0.28)
            k0 = k
            need = any((k0 + j + 1) * rise >= cut_z - 1e-6
                       for j in range(len(f["lines"])))
            for a, b in f["lines"]:
                k += 1
                ztop = k * rise                  # the tread over riser k
                # «railing»: a flight that needs headroom opened its whole
                # length, so the opening's edge runs along its railing
                if ztop >= cut_z - 1e-6 or (mode == "railing" and need):
                    q = [tuple(a), tuple(b),
                         (b[0] + d[0] * g, b[1] + d[1] * g),
                         (a[0] + d[0] * g, a[1] + d[1] * g)]
                    pg = Polygon(q).buffer(0)
                    if not pg.is_empty:
                        parts.append(pg)
        for ld in lands:
            z = float(ld.get("after", 0)) * rise
            if z >= cut_z - 1e-6 and len(ld.get("corners") or []) >= 3:
                parts.append(Polygon(ld["corners"]).buffer(0))
        if not parts:
            return None
        outline = Polygon(st["corners"]).buffer(0.02)
        u = unary_union([p.buffer(0.03, join_style=2) for p in parts])
        u = u.buffer(0.15, join_style=2).buffer(-0.15, join_style=2)
        u = u.intersection(outline)
        g_ = max(getattr(u, "geoms", [u]), key=lambda x: x.area)
        if g_.geom_type != "Polygon" or g_.area < 0.5:
            return None
        if g_.area > 0.97 * Polygon(st["corners"]).area:
            return None                          # all of it anyway
        return [[round(x, 4), round(y, 4)]
                for x, y in list(g_.simplify(0.01).exterior.coords)[:-1]]
    except Exception:  # noqa: BLE001
        return None


def _uncut(doc, only=None) -> None:
    """The wells the stairs before cut (``only`` those), closed again."""
    from shapely.geometry import Polygon
    arch = doc["arch"]
    olds = [Polygon(st["corners"]) for st in (
        only if only is not None else doc.get("stairs") or [])
        if len(st.get("corners") or []) >= 3]
    for s in arch["structure"]:
        if s["type"] != "slab" or not olds:
            continue
        keep = []
        for h in s.get("holes") or []:
            hp = Polygon(h)
            if any(hp.is_valid and o.is_valid and
                   hp.intersection(o).area >= 0.9 * hp.area and
                   hp.area >= 0.5 for o in olds):
                continue
            keep.append(h)
        s["holes"] = keep


#: what one stair may set for itself (else the panel's defaults)
OWN = ("stype", "rail", "rail_h", "rail_sides", "rail_off", "rail_gap",
       "rail_ext", "fin", "nose_type")
SIDES = ("inner", "outer", "both", "none")


def _own(st, k, stt, sk, dv):
    v = st.get(k)
    return stt.get(sk, dv) if v is None or v == "" else v


def eff(st, stt) -> dict:
    """The stair's own type and railing, or the defaults."""
    return {"stype": st.get("stype") or stt.get("stair_type", "monolithic"),
            "rail": st.get("rail") or stt.get("stair_rail", "ss_bars"),
            "rail_h": float(st.get("rail_h") or stt.get("stair_rail_h",
                                                       0.9144)),
            "rail_sides": st.get("rail_sides")
            or stt.get("stair_rail_sides", "inner"),
            "rail_off": float(_own(st, "rail_off", stt, "stair_rail_off",
                                   0.05)),
            "rail_gap": float(_own(st, "rail_gap", stt, "stair_rail_gap",
                                   0.0)),
            "rail_ext": float(_own(st, "rail_ext", stt, "stair_rail_ext",
                                   0.0)),
            "fin": st.get("fin") or stt.get("stair_fin", "marble"),
            "nose_type": st.get("nose_type") or stt.get("stair_nose_type",
                                                        "square")}


def groups(doc, z_of, layer_of):
    """[(name, stair id, level id, [(faces, colour)…], layer,
    [(faces, colour)…] of its railing)]."""
    stt = doc.get("settings") or {}
    out = []
    for st in doc.get("stairs") or []:
        z0 = z_of.get(st["level"])
        if z0 is None:
            continue
        e = eff(st, stt)
        fin_t = float(stt.get("stair_fin_t", 0.02))
        try:                  # finished floor to finished floor: the floor
            lo, hi = floor_finishes(doc, st)    # finish under its foot and
        except Exception:  # noqa: BLE001      # on the slab it arrives at
            from .host import log_error
            log_error("stairs.floor_finishes")
            lo = hi = 0.0
        if lo or hi:
            n_ = int(st.get("risers") or 1) or 1
            H_ = float(st["rise"]) * n_ + hi - lo
            st = dict(st, rise=H_ / n_)
            z0 += lo
            if hi > 0.001:
                fin_t = hi            # treads / landings: the slab's finish
        parts = build(st, z0, e["stype"], float(stt.get("stair_waist", 0.15)),
                      float(stt.get("stair_nosing", 0.025)),
                      float(stt.get("stair_tread", 0.05)), None,
                      fin=fin_colour(e["fin"]),
                      fin_t=fin_t,
                      fin_rt=float(stt.get("stair_fin_rt", 0.015)),
                      nose_type=e["nose_type"])
        rails = build_rail(st, z0, e["rail"], e["rail_h"], e["rail_sides"],
                           e["rail_off"], e["rail_gap"], e["rail_ext"],
                           _floor_of(parts), _walls_of(doc, st["level"]))
        if e["rail"] and e["rail"] != "none" and e["rail_sides"] != "none":
            try:                         # round the opening, upstairs
                guard = _well_guard(doc, st, z0, e["rail"], e["rail_h"],
                                    e["rail_gap"])
            except Exception:  # noqa: BLE001
                guard = []
            skip = {int(k) for k in st.get("rail_skip") or []
                    if str(k).lstrip("-").isdigit()}
            n0 = len(rails)
            rails = rails + [(fs, c) if (n0 + k) not in skip else ([], c)
                             for k, (fs, c) in enumerate(guard)]
        out.append((f"Stair {len(out) + 1}", st["id"], st["level"], parts,
                    layer_of(st["level"]), rails))
    return out


def floor_finishes(doc, st) -> tuple:
    """(below, above): the floor finish's thickness (m) under the stair's
    first step, on its own level, and where it arrives, on the slab above —
    each the finish of that room / slab zone (its own, the slab's, else the
    default); 0 with floor finishes off or «Stair finish follows the floor
    finish» unticked. The stair climbs from finished floor to finished
    floor and its treads and landings take the slab's finish."""
    stt = doc.get("settings") or {}
    if not stt.get("finish_on", True) or not stt.get("stair_fin_follow",
                                                      True):
        return 0.0, 0.0
    from . import project as PJ
    from .engine import spaces
    from shapely.geometry import Point
    flights, _l = as_flights(st)
    if not flights or not flights[0]["lines"]:
        return 0.0, 0.0
    foot = _mid(flights[0]["lines"][0])
    d0 = _nrm(flights[0]["d"])
    foot = (foot[0] - d0[0] * 0.3, foot[1] - d0[1] * 0.3)   # before it
    top_l = flights[-1]["lines"][-1]
    dt = _nrm(flights[-1]["d"])
    g = float(flights[-1].get("g") or 0.28)
    top = _mid(top_l)
    top = (top[0] + dt[0] * (g + 0.3), top[1] + dt[1] * (g + 0.3))

    def at(lid, pt):
        if not lid:
            return None
        rec = None
        try:
            for room in spaces.of_level(doc["arch"], lid):
                if room["poly"].contains(Point(pt)):
                    rec = room.get("rec")
                    break
        except Exception:  # noqa: BLE001
            pass
        try:
            _z, _w, thick = PJ._slab_finish_zones(doc, lid)
        except Exception:  # noqa: BLE001
            thick = []
        return float(PJ._finish_t_at(doc, rec, thick, pt) or 0.0)
    lo = at(st.get("level"), foot) or 0.0
    hi = at(st.get("to"), top)
    if hi is None:
        hi = lo
    return max(lo, 0.0), max(hi, 0.0)


def _well_guard(doc, st, z0, kind, h, gap) -> list:
    """[(faces, None)] — a railing round the stair's opening in the floor
    above: along each edge of the slab's hole over the stair, on the slab
    beside it, but where a wall stands and where the stair arrives (its
    last nosing) — each straight edge one piece."""
    from shapely.geometry import LineString, Polygon

    from .engine import railings as RL
    if not st.get("to"):
        return []
    arch = doc["arch"]
    ztop = z0 + int(st["risers"]) * float(st["rise"])
    foot = Polygon([tuple(p[:2]) for p in st["corners"]])
    holes = []
    for e in arch["structure"]:
        if e["type"] != "slab":
            continue
        from . import slabedges as SE
        if SE.floor_level_of({"arch": arch, "settings": doc["settings"]},
                             e) != st["to"]:
            continue
        for hl in e.get("holes") or []:
            try:
                hp = Polygon([tuple(p[:2]) for p in hl])
            except Exception:  # noqa: BLE001
                continue
            if hp.is_valid and hp.intersection(foot).area > 0.3 * min(
                    hp.area, foot.area):
                holes.append(hp)
    if not holes:
        return []
    walls = _walls_of(doc, st["to"])
    flights, _l = as_flights(st)
    arr = None
    if flights and flights[-1]["lines"]:
        ln = flights[-1]["lines"][-1]
        arr = LineString([tuple(ln[0][:2]), tuple(ln[1][:2])])
    out = []
    for hp in holes:
        pts = list(hp.exterior.coords)[:-1]
        ccw = hp.exterior.is_ccw
        for a, b in zip(pts, pts[1:] + pts[:1]):
            L = math.dist(a, b)
            if L < 0.3:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            out_n = (u[1], -u[0]) if ccw else (-u[1], u[0])  # onto the slab
            o_ = 0.04
            pa = (a[0] + out_n[0] * o_, a[1] + out_n[1] * o_)
            pb = (b[0] + out_n[0] * o_, b[1] + out_n[1] * o_)
            seg = LineString([pa, pb])
            if walls is not None:
                seg = seg.difference(walls.buffer(0.12))
            if arr is not None:
                seg = seg.difference(arr.buffer(0.35))
            for g in getattr(seg, "geoms", [seg]):
                if g.geom_type != "LineString" or g.length < 0.3:
                    continue
                c = list(g.coords)
                out.append((RL.faces([(c[0][0], c[0][1], ztop),
                                      (c[-1][0], c[-1][1], ztop)], h, kind,
                                     gap=gap), None))
    return out


def _runs(st, z0, off=0.05):
    """Each flight's two side lines over the nosings, ``off`` in from its
    edges: [(flight, is-left, (x, y, z) foot, (x, y, z) head)]."""
    flights, _landings = as_flights(st)
    rise = st["rise"]
    runs, count = [], 0
    for f in flights:
        lines = [((ln[0][0], ln[0][1]), (ln[1][0], ln[1][1]))
                 for ln in f["lines"]]
        m = len(lines)
        if m < 2:
            count += m
            continue
        a0, b0 = lines[0]
        d = tuple(f["d"])
        wv = math.dist(a0, b0) or float(f["w"])
        r = ((b0[0] - a0[0]) / wv, (b0[1] - a0[1]) / wv)
        ss = [((ln[0][0] + ln[1][0]) / 2 - (a0[0] + b0[0]) / 2) * d[0] +
              ((ln[0][1] + ln[1][1]) / 2 - (a0[1] + b0[1]) / 2) * d[1]
              for ln in lines]
        zb = z0 + count * rise
        o_ = min(max(float(off), 0.0), wv / 2 - 0.05)
        for tside in (o_, wv - o_):
            p_ = _at(a0, d, r, ss[0], tside)
            q_ = _at(a0, d, r, ss[m - 1], tside)
            runs.append((len(runs) // 2, tside < wv / 2,
                         (p_[0], p_[1], zb + rise), (q_[0], q_[1],
                                                     zb + m * rise)))
        count += m
    return runs


def _floor_of(parts):
    """floor(x, y) → the top of the tread / landing under a point (the
    stair's level faces looking up), or None off the stair."""
    from shapely.geometry import Point, Polygon
    tops = []
    for fs, _c in parts or []:
        for f in fs:
            lp = f["loop"] if isinstance(f, dict) else f
            if len(lp) < 3:
                continue
            zs = [q[2] for q in lp]
            if max(zs) - min(zs) > 1e-4:
                continue
            a = sum(p[0] * q[1] - q[0] * p[1]
                    for p, q in zip(lp, lp[1:] + lp[:1]))
            if a <= 0:                       # looking down: a soffit
                continue
            try:
                tops.append((Polygon([(q[0], q[1]) for q in lp]), zs[0]))
            except Exception:  # noqa: BLE001
                continue

    def floor(x, y):
        pt = Point(x, y)
        hit = [z for pg, z in tops if pg.buffer(0.01).contains(pt)]
        return max(hit) if hit else None
    return floor


def _walls_of(doc, lid):
    """The level's walls on plan (shapely, one union) — a flight's side
    along one needs no railing."""
    try:
        from shapely.ops import unary_union

        from . import slabedges as SE
        ws = [w for w in doc["arch"]["walls"] if w["level"] == lid
              and not w.get("rail")]
        ps = SE.wall_polys(ws)
        return unary_union(ps) if ps else None
    except Exception:  # noqa: BLE001
        return None


def build_rail(st, z0, rail, h=0.9, sides="inner", off=0.05, gap=0.0,
               ext=0.0, floor=None, walls=None) -> list:
    """[(faces, colour)] of the stair's railing alone: its type, height,
    sides (inner / outer / both / none), inset from the flight's edge,
    baluster spacing (0 = the type's) and run-on past the first and the
    last nosing."""
    if not rail or rail == "none" or sides == "none":
        return []
    runs = _runs(st, z0, off)
    out = railing(st, runs, rail, h, sides, gap, ext, off, floor, walls) \
        if runs else []
    # the pieces deleted by hand (right-click ▸ Delete on one): not made
    skip = {int(k) for k in st.get("rail_skip") or []
            if str(k).lstrip("-").isdigit()}
    return [(fs, c) if k not in skip else ([], c)
            for k, (fs, c) in enumerate(out)]

def _ccw(loop):
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(loop, loop[1:] + loop[:1]))
    return list(loop) if a >= 0 else list(reversed(loop))


# ---- terraces and balconies ----------------------------------------------------------------
def terrace(doc, lid, h=1.0, t=0.15) -> dict:
    """The roof of the floor below that this floor does not cover becomes
    its terrace: this level's slab grows over it, and a parapet runs on
    its open edges (not where this floor's walls stand)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    arch = doc["arch"]
    ids = [lv["id"] for lv in arch["levels"]]
    i = ids.index(lid)
    if i == 0:
        return {"why": "No floor below this one"}
    below = ids[i - 1]
    bw = [w for w in arch["walls"] if w["level"] == below]
    tw = [w for w in arch["walls"] if w["level"] == lid]
    if not bw or not tw:
        return {"why": "This floor and the one below need walls"}
    bo = S.inside_walls(bw, PJ._outer_loop)
    to = S.inside_walls(tw, PJ._outer_loop)
    if not bo or not to:
        return {"why": "No outline"}
    bp, tp = Polygon(bo), Polygon(to)
    region = bp.difference(tp.buffer(0.01, join_style=2))
    parts = [p for p in getattr(region, "geoms", [region])
             if p.geom_type == "Polygon" and p.area >= 1.0]
    if not parts:
        return {"why": "This floor covers the whole floor below — no terrace"}
    slabs = [e for e in arch["structure"]
             if e["type"] == "slab" and e["level"] == lid
             and not (e.get("zone") or e.get("user") or e.get("roof"))]
    if PJ.slab_on_top(doc):
        # the terrace stands on the slab over the floor below — nothing
        # more over it: this level's own slab (over this floor) kept off
        # the terrace
        open_u = unary_union(parts).buffer(0.005, join_style=2)
        for sl in slabs:
            poly = Polygon(sl["corners"]).buffer(0)
            if not poly.intersects(open_u):
                continue
            rest = poly.difference(open_u)
            g = max(getattr(rest, "geoms", [rest]), key=lambda q: q.area,
                    default=None)
            if g is None or g.is_empty or g.geom_type != "Polygon" or \
                    g.area < 1.0:
                continue
            sl["corners"] = [[round(x, 4), round(y, 4)]
                             for x, y in list(g.simplify(0.005)
                                              .exterior.coords)[:-1]]
            sl["holes"] = [h for h in sl.get("holes") or []
                           if g.contains(Polygon(h).buffer(-0.01))]
    else:
        # the slab of this level (at its floor): over both
        full = unary_union([bp, tp]).buffer(0.001, join_style=2)
        if full.geom_type != "Polygon":
            full = max(full.geoms, key=lambda g: g.area)
        holes = [h for s_ in slabs for h in s_.get("holes") or []]
        arch["structure"] = [e for e in arch["structure"] if e not in slabs]
        t_slab = float(slabs[0]["t"]) if slabs else 0.15
        rec = {"type": "slab", "level": lid,
               "corners": [[round(x, 4), round(y, 4)]
                           for x, y in list(full.exterior.coords)[:-1]],
               "holes": holes, "t": t_slab, "offset": 0.0,
               "shafts": [h for s_ in slabs for h in s_.get("shafts") or []]}
        if S.why_not(rec) is None:
            arch["structure"] += M.new_elements(arch["structure"], [rec])
    # the terrace made before on this level: its parapets go
    arch["walls"] = [w for w in arch["walls"] if not (
        w["level"] == lid and str(w.get("name", "")).startswith("Terrace"))]
    recs = parapet_runs(parts, tp, t, h, lid)
    made = M.new_walls(arch["walls"], recs)
    rk = doc["settings"].get("parapet_rail", "solid")
    for k, w in enumerate(made, 1):
        w["name"] = f"Terrace parapet {k}"
        if rk and rk != "solid":
            w["rail"] = rk
    arch["walls"] += made
    area = sum(p.area for p in parts)
    arch["rooms"] = [r for r in arch["rooms"]
                     if not (r["level"] == lid and r["name"] == "Terrace")]
    arch["rooms"] = M._rooms(arch["rooms"] + [{
        "id": "", "level": lid, "name": "Terrace",
        "x": parts[0].representative_point().x,
        "y": parts[0].representative_point().y}], set(ids))
    return {"area": area, "parapets": len(recs)}


def parapet_runs(parts, tp, t, h, lid) -> list:
    """The parapet walls round the terrace ``parts`` on their open edges:
    each run ONE chain of walls sharing their end points (so the corners
    close clean), set in by half its width from the slab's edge, and
    carried up to the face of this floor's walls where it meets them."""
    from shapely.geometry import LineString, Point
    from shapely.ops import linemerge
    out = []
    near = t / 2 + 0.03                       # the run along this floor
    edge = tp.buffer(near, join_style=2)
    for p in parts:
        inset = p.buffer(-t / 2, join_style=2)
        for g in getattr(inset, "geoms", [inset]):
            if g.geom_type != "Polygon" or g.area < 0.05:
                continue
            ring = LineString(list(g.exterior.simplify(0.01).coords))
            rest = ring.difference(edge)
            if rest.is_empty:
                continue
            if rest.geom_type == "MultiLineString":
                rest = linemerge(rest)
            for run in getattr(rest, "geoms", [rest]):
                if run.geom_type != "LineString" or run.length < 0.2:
                    continue
                pts = [tuple(q) for q in run.coords]
                closed = math.dist(pts[0], pts[-1]) < 1e-6
                if not closed:
                    # an end at this floor's walls: on to their face
                    for k, k2 in ((0, 1), (-1, -2)):
                        a_, b_ = pts[k], pts[k2]
                        if tp.distance(Point(a_)) > near + 0.05:
                            continue
                        L = math.dist(a_, b_) or 1.0
                        ux, uy = (a_[0] - b_[0]) / L, (a_[1] - b_[1]) / L
                        d = tp.exterior.distance(Point(a_)) + 0.01
                        pts[k] = (a_[0] + ux * d, a_[1] + uy * d)
                for a_, b_ in zip(pts, pts[1:]):
                    if math.dist(a_, b_) < 0.05:
                        continue
                    out.append({"kind": "line",
                                "a": [round(a_[0], 4), round(a_[1], 4)],
                                "b": [round(b_[0], 4), round(b_[1], 4)],
                                "t": t, "align": "centre", "side": 1,
                                "height": h, "base": 0.0, "level": lid})
    return out


def balcony(doc, wall_id, depth=1.2, width=0.0, pos=None, h=1.0, t=0.10,
            slab_t=0.15) -> dict:
    """A balcony out of a wall: a slab ``depth`` deep, ``width`` long
    (0 = the wall's length; ``pos`` its centre along the wall, else the
    middle), on the wall's outer side, with a railing round it."""
    from shapely.geometry import Point, Polygon

    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    from .engine import walls as W
    arch = doc["arch"]
    w = next((x for x in arch["walls"] if x["id"] == wall_id), None)
    if w is None or w.get("kind", "line") != "line":
        return {"why": "Select a straight wall"}
    lid = w["level"]
    cl = W.centre(w)
    a, b = cl.at(0.0), cl.at(1.0)
    L = math.dist(a, b)
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    nrm = (-u[1], u[0])
    mine = [x for x in arch["walls"] if x["level"] == lid]
    out = S.inside_walls(mine, PJ._outer_loop)
    poly = Polygon(out) if out else None
    if next((lv["kind"] for lv in arch["levels"] if lv["id"] == lid),
            "floor") != "floor":
        return {"why": "a balcony hangs from an upper floor — select a wall "
                       "of Level 2 or above (its plan: Level list ▸ Plan)"}
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    side_out = []
    for sgn in (1, -1):                     # just past each face
        q = (mid[0] + nrm[0] * sgn * (float(w["t"]) / 2 + 0.06),
             mid[1] + nrm[1] * sgn * (float(w["t"]) / 2 + 0.06))
        side_out.append(poly is None or not poly.buffer(-0.01).contains(
            Point(q)))
    if side_out == [False, False]:
        return {"why": "this wall has rooms on both sides — select an "
                       "outside wall"}
    if not side_out[0]:
        nrm = (-nrm[0], -nrm[1])
    width = L if width <= 0 else min(width, L + 2.0)
    c = L / 2 if pos is None else min(max(pos, 0.0), L)
    face = float(w["t"]) / 2                     # the wall's outer face
    s0, s1 = c - width / 2, c + width / 2
    p = lambda s, d: (a[0] + u[0] * s + nrm[0] * d,  # noqa: E731
                      a[1] + u[1] * s + nrm[1] * d)
    quad = [p(s0, face), p(s1, face), p(s1, face + depth), p(s0, face + depth)]
    rec = {"type": "slab", "level": lid,
           "corners": [[round(x, 4), round(y, 4)] for x, y in quad],
           "holes": [], "t": slab_t, "offset": 0.0}
    why = S.why_not(rec)
    if why:
        return {"why": why}
    arch["structure"] += M.new_elements(arch["structure"], [rec])
    rails = []
    d = depth - t / 2 + face
    for (sa, da), (sb, db) in (((s0 + t / 2, face), (s0 + t / 2, d)),
                               ((s0 + t / 2, d), (s1 - t / 2, d)),
                               ((s1 - t / 2, d), (s1 - t / 2, face))):
        A, B = p(sa, da), p(sb, db)
        rails.append({"kind": "line", "a": [round(A[0], 4), round(A[1], 4)],
                      "b": [round(B[0], 4), round(B[1], 4)], "t": t,
                      "align": "centre", "side": 1, "height": h,
                      "base": 0.0, "level": lid})
    made = M.new_walls(arch["walls"], rails)
    for k, w_ in enumerate(made, 1):
        w_["name"] = f"Balcony railing {k}"
        rk_ = doc["settings"].get("parapet_rail", "solid")
        if rk_ and rk_ != "solid":
            w_["rail"] = rk_
    arch["walls"] += made
    mid = p((s0 + s1) / 2, face + depth / 2)
    arch["rooms"] = M._rooms(arch["rooms"] + [{
        "id": "", "level": lid, "name": "Balcony", "x": mid[0], "y": mid[1]}],
        {lv["id"] for lv in arch["levels"]})
    return {"area": width * depth, "level": lid}


# ---- stairs traced from the plan's tread lines -------------------------------------------
def _unit(a, b):
    L = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def trace(segs, words=()):
    """Flights from the tread lines of a stair layer (model m):
    [[flight, …] per stair], a flight = {"lines": [(a, b)…] in climbing
    order (a on the left), "d": climbing direction, "w", "g"}. ``words``:
    [(x, y, text)] — UP marks a stair's foot, DN its head."""
    cand = []
    for (a, b) in segs:
        L = math.dist(a, b)
        if 0.5 <= L <= 2.6:
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
            cand.append((round(ang) % 180, round(L / 0.05), a, b))
    groups = {}
    for ang, lk, a, b in cand:
        groups.setdefault((ang, lk), []).append((a, b))
    flights = []
    split = []
    for (ang, lk), lines in groups.items():
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        n = (-u[1], u[0])
        # the same tread line drawn twice: once
        uniq = []
        for a, b in lines:
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if not any(math.dist(m, q) < 0.01 for q, _l in uniq):
                uniq.append((m, (a, b)))
        # flights side by side (a U-stair's two arms: same length, same
        # direction) apart: by where they sit along the treads
        al = sorted(uniq, key=lambda t: t[0][0] * u[0] + t[0][1] * u[1])
        part = [al[0]]
        for t in al[1:]:
            pa = part[-1][0][0] * u[0] + part[-1][0][1] * u[1]
            if t[0][0] * u[0] + t[0][1] * u[1] - pa > 0.10:
                split.append((ang, lk, [l for _m, l in part]))
                part = []
            part.append(t)
        split.append((ang, lk, [l for _m, l in part]))
    for ang, _lk, lines in split:
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        n = (-u[1], u[0])
        rows = sorted(((((a[0] + b[0]) / 2) * n[0] + ((a[1] + b[1]) / 2) * n[1],
                        ((a[0] + b[0]) / 2) * u[0] + ((a[1] + b[1]) / 2) * u[1],
                        a, b) for a, b in lines))
        run = [rows[0]]
        for r in rows[1:] + [None]:
            ok = False
            if r is not None:
                s = r[0] - run[-1][0]
                prev = run[-1][0] - run[-2][0] if len(run) > 1 else s
                ok = 0.18 <= s <= 0.40 and abs(s - prev) < 0.04 and \
                    abs(r[1] - run[-1][1]) < 0.10
            if ok:
                run.append(r)
                continue
            if len(run) >= 2:
                gs = [run[k + 1][0] - run[k][0] for k in range(len(run) - 1)]
                ls = []
                for _o, _t, a, b in run:
                    if (b[0] - a[0]) * u[0] + (b[1] - a[1]) * u[1] < 0:
                        a, b = b, a
                    ls.append((tuple(a), tuple(b)))
                flights.append({"lines": ls, "d": n,
                                "w": math.dist(*ls[0]),
                                "g": sum(gs) / len(gs)})
            if r is not None:
                run = [r]
    # stairs: flights near each other
    # (every flight within 1.2 m of another one of the stair, whatever
    # order they come in: merged)
    boxes = [_fbox(f) for f in flights]
    root = list(range(len(flights)))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for i in range(len(flights)):
        for j in range(i + 1, len(flights)):
            if _boxdist(boxes[i], boxes[j]) < 1.2:
                root[find(i)] = find(j)
    by = {}
    for i, f in enumerate(flights):
        by.setdefault(find(i), []).append(f)
    return [_chain(st, words) for st in by.values()]


def _fbox(f):
    xs = [p[0] for ln in f["lines"] for p in ln]
    ys = [p[1] for ln in f["lines"] for p in ln]
    return min(xs), min(ys), max(xs), max(ys)


def _boxdist(a, b):
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def _mid(ln):
    return ((ln[0][0] + ln[1][0]) / 2, (ln[0][1] + ln[1][1]) / 2)


def _flip(f):
    lines = [(b, a) for a, b in reversed(f["lines"])]
    return dict(f, lines=lines, d=(-f["d"][0], -f["d"][1]))


def _chain(fl, words):
    """The flights in climbing order, each pointing up."""
    ups = [(x, y) for x, y, t in words if t.strip().upper() == "UP"]
    dns = [(x, y) for x, y, t in words if t.strip().upper() in ("DN", "DOWN")]

    def near(p, pts):
        return min((math.dist(p, q) for q in pts), default=1e9)
    # the foot: the flight end nearest an UP (else farthest from a DN)
    best = None
    for i, f in enumerate(fl):
        for end, ln in ((0, f["lines"][0]), (1, f["lines"][-1])):
            m = _mid(ln)
            score = near(m, ups) if ups else (-near(m, dns) if dns else
                                               (end, i))
            if best is None or score < best[0]:
                best = (score, i, end)
    _s, i, end = best
    first = fl[i] if end == 0 else _flip(fl[i])
    order = [first]
    rest = [f for k, f in enumerate(fl) if k != i]
    while rest:
        top = _mid(order[-1]["lines"][-1])
        k, e = min(((k, e) for k in range(len(rest)) for e in (0, 1)),
                   key=lambda ke: math.dist(top, _mid(
                       rest[ke[0]]["lines"][0 if ke[1] == 0 else -1])))
        f = rest.pop(k)
        order.append(f if e == 0 else _flip(f))
    # a flight marked DN (the one going down to the floor below, drawn
    # on this plan beside the up flights) is not part of this stair
    if dns and ups and len(order) > 1:
        def mid_of(f):
            return _mid(f["lines"][len(f["lines"]) // 2])
        keep = [order[0]]
        for f in order[1:]:
            m = mid_of(f)
            if near(m, dns) < near(m, ups) and near(m, dns) < 2.5:
                continue
            keep.append(f)
        order = keep
    for f in order:                    # every line: a on the climber's left
        d = f["d"]
        f["lines"] = [(a, b) if (b[0] - a[0]) * d[1] - (b[1] - a[1]) * d[0]
                      > 0 else (b, a) for a, b in f["lines"]]
    # marked DN only (no UP by it): the stair from the floor below, seen
    # going down on this plan — not a stair climbing from this floor
    mids = [_mid(ln) for f in fl for ln in f["lines"]]

    def by(pts):
        return [p for p in pts if mids and
                min(math.dist(p, m) for m in mids) < 3.0]
    if order and by(dns) and not by(ups):
        order[0]["_dn_only"] = True
    return order


def complete(flights, n_needed, room=None):
    """The flights drawn, and — when they hold fewer risers than the
    storey needs (a plan shows the lower flight only) — a half landing and
    a return flight beside the last one, on the side the stair room
    leaves free. Returns (flights, landings) with landings as
    {"corners", "after"} (risers climbed before it)."""
    from shapely.geometry import Polygon
    flights = [dict(f) for f in flights]
    landings = []
    count = 0
    for i, f in enumerate(flights[:-1]):
        count += len(f["lines"])
        nx = flights[i + 1]
        la, lb = f["lines"][-1]
        fa, fb = nx["lines"][0]
        d = f["d"]
        depth = f["w"] if d[0] * nx["d"][0] + d[1] * nx["d"][1] < -0.5 else 0.0
        pts = [la, lb, fa, fb]
        pts += [(p[0] + d[0] * depth, p[1] + d[1] * depth) for p in pts]
        # the landing: square to the flight it ends (its last tread line
        # and the next flight's first one, boxed along the flight) — the
        # corner square of an L, the full width of a U's half landing
        landings.append({"corners": _box_along(pts, d), "after": count})
    have = sum(len(f["lines"]) for f in flights)
    if n_needed > have and len(flights) >= 2 and abs(
            flights[-2]["d"][0] * flights[-1]["d"][0] +
            flights[-2]["d"][1] * flights[-1]["d"][1]) < 0.3:
        # an L drawn (the plan cut above it): the stair turns the same way
        # again — a corner landing past the last flight, then the third
        # flight on, as a three-flight U goes
        f, pf = flights[-1], flights[-2]
        d, w, g = f["d"], float(f["w"]), float(f["g"])
        turn = pf["d"][0] * d[1] - pf["d"][1] * d[0]
        nd = (-d[1], d[0]) if turn > 0 else (d[1], -d[0])
        a, b = f["lines"][-1]
        dw = (d[0] * w, d[1] * w)
        land = [a, b, (a[0] + dw[0], a[1] + dw[1]),
                (b[0] + dw[0], b[1] + dw[1])]
        landings.append({"corners": _box_along(land, d), "after": have})
        left = (-d[1], d[0])
        # the landing's side the new flight leaves from
        sa = (a[0] - b[0]) * left[0] + (a[1] - b[1]) * left[1]
        e0 = a if (sa > 0) == (turn > 0) else b
        e1 = (e0[0] + dw[0], e0[1] + dw[1])
        nl = (-nd[1], nd[0])
        if (e1[0] - e0[0]) * nl[0] + (e1[1] - e0[1]) * nl[1] < 0:
            e0, e1 = e1, e0
        k = n_needed - have
        lines = [((e0[0] + nd[0] * g * j, e0[1] + nd[1] * g * j),
                  (e1[0] + nd[0] * g * j, e1[1] + nd[1] * g * j))
                 for j in range(k)]
        flights.append({"lines": lines, "d": nd, "w": w, "g": g})
        have = n_needed
    if n_needed > have and flights:
        f = flights[-1]
        d, w, g = f["d"], f["w"], f["g"]
        a, b = f["lines"][-1]
        left = (-d[1], d[0])           # a is on the left of the climber
        best = None
        for side in (1, -1):
            off = (left[0] * side * (w + 0.10), left[1] * side * (w + 0.10))
            land = [a, b, (a[0] + off[0], a[1] + off[1]),
                    (b[0] + off[0], b[1] + off[1])]
            land += [(p[0] + d[0] * w, p[1] + d[1] * w) for p in land]
            c, u, lw, L = rect_of(land)
            box = corners_of(c, u, lw, L)
            score = Polygon(box).intersection(room).area if room is not None \
                else side
            if best is None or score > best[0]:
                best = (score, side, off, box)
        _s, side, off, box = best
        landings.append({"corners": box, "after": have})
        k = n_needed - have
        # the return flight: beside, coming back down the well
        a2 = (a[0] + off[0], a[1] + off[1])
        b2 = (b[0] + off[0], b[1] + off[1])
        back = (-d[0], -d[1])
        lines = []
        for j in range(k):
            s = g * j
            lines.append(((b2[0] + back[0] * s, b2[1] + back[1] * s),
                          (a2[0] + back[0] * s, a2[1] + back[1] * s)))
        flights.append({"lines": lines, "d": back, "w": w, "g": g})
    # the arrival: a landing at the floor above, the width of the last
    # flight, square past its last riser (the stair never ends on a hole)
    if flights:
        f = flights[-1]
        d, w = f["d"], float(f["w"])
        la, lb = f["lines"][-1]
        pts = [la, lb, (la[0] + d[0] * w, la[1] + d[1] * w),
               (lb[0] + d[0] * w, lb[1] + d[1] * w)]
        landings.append({"corners": _box_along(pts, d),
                         "after": sum(len(x["lines"]) for x in flights),
                         "arrival": True})
    return flights, landings


def winders(flights, lands, diags, tol=0.2):
    """A turning landing the plan splits with a diagonal from corner to
    corner: two winder treads, one riser apart — the landing made two
    triangles (the first by the flight arriving, the second by the one
    leaving, a riser up) and a one-line «flight» on the diagonal between
    them (its riser), the landings and risers after it one higher."""
    from shapely.geometry import Point, Polygon
    out_f, out_l = list(flights), []
    shift = 0
    for lg in sorted(lands, key=lambda g: int(g.get("after", 0))):
        lg = dict(lg, after=int(lg.get("after", 0)) + shift)
        cs = [tuple(p[:2]) for p in lg.get("corners") or []]
        if lg.get("arrival") or len(cs) != 4:
            out_l.append(lg)
            continue
        hit = None
        for a, b in diags:
            ia = min(range(4), key=lambda i: math.dist(cs[i], a))
            ib = min(range(4), key=lambda i: math.dist(cs[i], b))
            if (ia - ib) % 4 == 2 and math.dist(cs[ia], a) < tol and \
                    math.dist(cs[ib], b) < tol:
                hit = (ia, ib)
                break
        if hit is None:
            out_l.append(lg)
            continue
        ia, ib = hit
        t1 = [cs[ia], cs[(ia + 1) % 4], cs[ib]]
        t2 = [cs[ib], cs[(ib + 1) % 4], cs[ia]]
        # the flight arriving here: its last riser on an edge of t1 or t2
        k_in, acc = None, 0
        for i, f in enumerate(out_f):
            acc += len(f["lines"])
            if acc == lg["after"]:
                k_in = i
                break
        if k_in is None:
            out_l.append(lg)
            continue
        m_in = Point(_mid(out_f[k_in]["lines"][-1]))
        if Polygon(t2).distance(m_in) < Polygon(t1).distance(m_in) - 1e-6:
            t1, t2 = t2, t1
        c1 = Polygon(t1).centroid
        c2 = Polygon(t2).centroid
        dd = _nrm((c2.x - c1.x, c2.y - c1.y))
        diag = [list(cs[ia]), list(cs[ib])]
        out_f.insert(k_in + 1, {"lines": [diag], "d": [dd[0], dd[1]],
                                "w": math.dist(cs[ia], cs[ib]),
                                "g": 0.0, "winder": True})
        out_l.append({"corners": [list(p) for p in t1], "after": lg["after"]})
        out_l.append({"corners": [list(p) for p in t2],
                      "after": lg["after"] + 1, "winder_line": diag,
                      "winder_d": [dd[0], dd[1]]})
        shift += 1
    return out_f, out_l


def real_flights(st) -> list:
    """The stair's flights without its winders' one-line «flights»."""
    flights, _l = as_flights(st)
    return [f for f in flights if not f.get("winder")]


def cut_at_foreign(flights, segs):
    """The flights of a traced stair up to the first turn whose landing
    the plan fills with other tread lines (the flight beyond belongs to
    another stair — the one going down to the basement drawn beside it)."""
    from shapely.geometry import Point, Polygon
    if len(flights) < 2:
        return flights
    mine = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            for f in flights for a, b in f["lines"]]
    other = []
    for a, b in segs:
        L = math.dist(a, b)
        if not 0.5 <= L <= 2.6:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if any(math.dist(m, q) < 0.03 for q in mine):
            continue
        other.append(m)
    if not other:
        return flights
    for i, f in enumerate(flights[:-1]):
        nx = flights[i + 1]
        la, lb = f["lines"][-1]
        fa, fb = nx["lines"][0]
        d = f["d"]
        depth = f["w"] if d[0] * nx["d"][0] + d[1] * nx["d"][1] < -0.5 \
            else 0.0
        pts = [la, lb, fa, fb]
        pts += [(p[0] + d[0] * depth, p[1] + d[1] * depth) for p in pts]
        try:
            box = Polygon(_box_along(pts, d)).buffer(-0.08)
        except Exception:  # noqa: BLE001
            continue
        if box.is_empty:
            continue
        if sum(1 for m in other if box.contains(Point(m))) >= 2:
            return flights[:i + 1]
        # two flights side by side climbing the same way: not one stair
        if d[0] * nx["d"][0] + d[1] * nx["d"][1] > 0.5 and i > 0:
            return flights[:i + 1]
    return flights


def _box_along(pts, d):
    """The box round points, its sides along d and across it."""
    L = math.hypot(d[0], d[1]) or 1.0
    u = (d[0] / L, d[1] / L)
    v = (-u[1], u[0])
    su = [p[0] * u[0] + p[1] * u[1] for p in pts]
    sv = [p[0] * v[0] + p[1] * v[1] for p in pts]
    a0, a1, b0, b1 = min(su), max(su), min(sv), max(sv)

    def P(a, b):
        return [round(u[0] * a + v[0] * b, 4), round(u[1] * a + v[1] * b, 4)]
    return [P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b1)]


def traced_steps(st, z0):
    """Blocks of a traced stair: between each two lines of a flight, and
    the landings, each from the floor up to its level."""
    rise = st["rise"]
    out = []
    count = 0
    for f in st["flights"]:
        lines = f["lines"]
        for j in range(len(lines) - 1):
            (a0, b0), (a1, b1) = lines[j], lines[j + 1]
            out.append((f"Step {count + j + 1}", [a0, b0, b1, a1], z0,
                        z0 + (count + j + 1) * rise))
        count += len(lines)
    for lg in st.get("landings") or []:
        out.append(("Landing", [tuple(p) for p in lg["corners"]], z0,
                    z0 + lg["after"] * rise))
    return out


def outline_of(st):
    """The stair's well: its flights and landings — not its arrival
    landing, which is the floor above's own slab."""
    pts = [p for f in st["flights"] for ln in f["lines"] for p in ln]
    pts += [tuple(p) for lg in st.get("landings") or []
            if not lg.get("arrival") for p in lg["corners"]]
    return corners_of(*rect_of(pts))


def terraces_all(doc, h=1.0, t=0.15) -> list:
    """A terrace on every floor that leaves part of the floor below open:
    [(level name, area)]."""
    out = []
    for lv in doc["arch"]["levels"]:
        if lv["kind"] != "floor" or lv["name"] == "Roof":
            continue
        r = terrace(doc, lv["id"], h, t)
        if not r.get("why"):
            out.append((lv["name"], r["area"]))
    return out


# ---- stair types: how a flight is made ----------------------------------------------------
TYPES = [("monolithic", "Monolithic RCC (waist slab)"),
         ("solid", "Solid / masonry (filled)"),
         ("open", "Open riser — steel / timber on stringers"),
         ("cantilever", "Cantilever (floating treads)")]
CONCRETE = (0.74, 0.73, 0.70, 1.0)
TIMBER = (0.62, 0.45, 0.30, 1.0)
STEEL = (0.25, 0.27, 0.30, 1.0)


def as_flights(st):
    """A standard (designed) stair in the traced form: flights of riser
    lines and landings."""
    if st.get("traced"):
        return st["flights"], st.get("landings") or []
    (cx, cy), u, w, L = rect_of(st["corners"])
    v = (-u[1], u[0])
    if st.get("flip"):
        v = (-v[0], -v[1])
    o = (cx - u[0] * L / 2 - v[0] * w / 2, cy - u[1] * L / 2 - v[1] * w / 2)

    def P(a, b):
        return [o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b]
    n, g = st["risers"], st["going"]
    if st["kind"] == "straight":
        start = max((L - (n - 1) * g) / 2, 0.0)
        lines = [[P(start + k * g, w), P(start + k * g, 0.0)] for k in range(n)]
        return [{"lines": lines, "d": list(u), "w": w, "g": g}], []
    dl = w / 2
    n1 = int(math.ceil(n / 2))
    n2 = n - n1
    # the first flight's last riser is the half landing's edge (the spare
    # length stays at its foot, on the floor)
    s1 = max(L - dl - (n1 - 1) * g, 0.0)
    f1 = [[P(s1 + k * g, w / 2 - 0.01), P(s1 + k * g, 0.0)]
          for k in range(n1)]
    f2 = [[P(L - dl - k * g, w / 2 + 0.01), P(L - dl - k * g, w)]
          for k in range(n2)]
    land = {"corners": [P(L - dl, 0), P(L, 0), P(L, w), P(L - dl, w)],
            "after": n1}
    return ([{"lines": f1, "d": list(u), "w": w / 2, "g": g},
             {"lines": f2, "d": [-u[0], -u[1]], "w": w / 2, "g": g}],
            [land])


def _prism(profile, o, d, r, t0, t1):
    """A solid from a profile [(s, z)] in the vertical plane along ``d``
    (from ``o``), run across ``r`` from t0 to t1: side faces and the
    faces round its edges."""
    def P(s, t, z):
        return (o[0] + d[0] * s + r[0] * t, o[1] + d[1] * s + r[1] * t, z)
    faces = [[P(s, t0, z) for s, z in profile],
             [P(s, t1, z) for s, z in reversed(profile)]]
    n = len(profile)
    for i in range(n):
        (s0, z0), (s1, z1) = profile[i], profile[(i + 1) % n]
        if abs(s0 - s1) < 1e-9 and abs(z0 - z1) < 1e-9:
            continue
        faces.append([P(s0, t0, z0), P(s0, t1, z0), P(s1, t1, z1),
                      P(s1, t0, z1)])
    # outward, however ``d``, ``r`` and the profile turn: the end face at
    # t0 must look away from the t1 end (else every face turned round)
    area = sum(profile[i][0] * profile[(i + 1) % n][1] -
               profile[(i + 1) % n][0] * profile[i][1] for i in range(n))
    look = (d[1] * r[0] - d[0] * r[1]) * area * (t1 - t0)
    if look > 0:
        faces = [list(reversed(f)) for f in faces]
    return faces


def _clean(profile):
    out = []
    for p in profile:
        if not out or abs(p[0] - out[-1][0]) > 1e-6 or \
                abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-6 and \
            abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


FINISHES = [("marble", "White marble", (0.92, 0.91, 0.88)),
            ("granite", "Black granite", (0.22, 0.22, 0.23)),
            ("terrazzo", "Terrazzo", (0.84, 0.80, 0.74)),
            ("porcelain", "Porcelain tile (grey)", (0.72, 0.72, 0.70)),
            ("wood", "Timber", (0.62, 0.45, 0.30)),
            ("bare", "No finish (bare concrete)", None)]
NOSINGS = [("square", "Square (projecting)"),
           ("bullnose", "Bullnose (fully rounded)"),
           ("pencil", "Pencil round (small radius)"),
           ("chamfer", "Chamfered"),
           ("flush", "Flush (no projection)"),
           ("strip", "Square with anti-slip metal strip")]
STRIP = (0.70, 0.71, 0.73)


def fin_colour(key):
    return next((c for k, _l, c in FINISHES if k == key), None)


def _box(s0, s1, z0, z1):
    """A rectangle in the (s, z) plane, in the profiles' turning sense."""
    return [(s0, z0), (s0, z1), (s1, z1), (s1, z0)]


def _nose_profile(s_front, s_back, z_top, ft, kind):
    """A tread finish's section: its front edge shaped as the nosing."""
    zb = z_top - ft
    if kind == "bullnose" and ft > 0.004:
        r = ft / 2.0
        cx, cz = s_front + r, z_top - r
        arc = [(cx + r * math.cos(math.radians(a)),
                cz + r * math.sin(math.radians(a)))
               for a in range(270, 89, -20)]
        return arc + [(s_back, z_top), (s_back, zb)]
    if kind == "pencil" and ft > 0.004:
        rr = min(0.006, ft / 2.0)
        cx, cz = s_front + rr, z_top - rr
        arc = [(cx + rr * math.cos(math.radians(a)),
                cz + rr * math.sin(math.radians(a)))
               for a in range(180, 89, -15)]
        return [(s_front, zb)] + arc + [(s_back, z_top), (s_back, zb)]
    if kind == "chamfer":
        c = min(0.01, ft * 0.6)
        return [(s_front, zb), (s_front, z_top - c), (s_front + c, z_top),
                (s_back, z_top), (s_back, zb)]
    return _box(s_front, s_back, zb, z_top)


def build(st, z0, kind="monolithic", waist=0.15, nosing=0.025,
          tread_t=0.05, rail=None, rail_h=0.9, rail_sides="inner",
          rail_off=0.05, rail_gap=0.0, rail_ext=0.0, fin=None, fin_t=0.02,
          fin_rt=0.015, nose_type="square"):
    """[(faces, colour)] of a stair of the chosen type — with its railing
    (``rail``: a railings type; None / "none" = no railing). ``fin`` (a
    colour): a finish on the treads (``fin_t`` thick, its front edge the
    ``nose_type`` nosing, ``nosing`` past the riser), on the risers
    (``fin_rt``) and on the landings — the concrete set down / back by it,
    so the finished risers and goings stay as drawn."""
    from shapely.geometry import Polygon as _Pg
    has_fin = fin is not None and kind in ("monolithic", "solid")
    ft = max(float(fin_t), 0.0) if has_fin else 0.0
    rt = max(float(fin_rt), 0.0) if has_fin else 0.0
    nos_p = 0.0 if nose_type == "flush" else float(nosing)
    land_ext = {}                     # landing «after» → finish run-ons
    from .engine import walls as W
    flights, landings = as_flights(st)
    rise = st["rise"]
    out = []
    count = 0
    runs = []                         # each flight's two side lines, sloped
    for f in flights:
        lines = [((ln[0][0], ln[0][1]), (ln[1][0], ln[1][1]))
                 for ln in f["lines"]]
        m = len(lines)
        if m < 2:
            count += m
            continue
        a0, b0 = lines[0]
        d = tuple(f["d"])
        o = a0
        wv = math.dist(a0, b0) or float(f["w"])
        r = ((b0[0] - a0[0]) / wv, (b0[1] - a0[1]) / wv)
        ss = [((ln[0][0] + ln[1][0]) / 2 - (a0[0] + b0[0]) / 2) * d[0] +
              ((ln[0][1] + ln[1][1]) / 2 - (a0[1] + b0[1]) / 2) * d[1]
              for ln in lines]
        g = (ss[-1] - ss[0]) / (m - 1) if m > 1 else float(f["g"])
        zb = z0 + count * rise
        zk = [zb + k * rise for k in range(m + 1)]
        # the railing's line: over the nosings, from the first to the top
        for tside in (0.05, wv - 0.05):
            p_ = _at(o, d, r, ss[0], tside)
            q_ = _at(o, d, r, ss[m - 1], tside)
            runs.append((len(runs) // 2, tside < wv / 2,
                         (p_[0], p_[1], zb + rise), (q_[0], q_[1], zk[m])))
        tan = rise / g if g > 1e-6 else 1.0
        cos = 1.0 / math.sqrt(1.0 + tan * tan)
        nos = nosing if kind in ("monolithic", "solid") else 0.0
        if has_fin:
            nos = 0.0                   # the finish makes the nosing
        ends_on_ = any(int(lg.get("after", -1)) == count + m
                       for lg in landings)
        if has_fin:
            for j in range(m):          # the risers' finish
                ztop = zk[j + 1] - ft if (j < m - 1 or ends_on_) \
                    else zk[j + 1]
                if rt > 0 and ztop > zk[j] + 1e-4:
                    out.append((_prism(_box(ss[j] - rt, ss[j], zk[j], ztop),
                                       o, d, r, 0.0, wv), fin))
            for k in range(1, m):       # the treads' finish, nosing front
                if ft <= 0:
                    break
                sf = ss[k - 1] - rt - nos_p
                out.append((_prism(_clean(_nose_profile(
                    sf, ss[k], zk[k], ft, nose_type)), o, d, r, 0.0, wv),
                    fin))
                if nose_type == "strip" and wv > 0.2:
                    out.append((_prism(_box(sf + 0.012, sf + 0.052, zk[k],
                                            zk[k] + 0.003), o, d, r, 0.05,
                                       wv - 0.05), STRIP))
            if ends_on_:                # the landing's finish over the
                s_l = ss[m - 1] - rt    # last riser (flush with its finish)
                q = [_at(o, d, r, s_l, 0),
                     _at(o, d, r, ss[m - 1] + 0.01, 0),
                     _at(o, d, r, ss[m - 1] + 0.01, wv),
                     _at(o, d, r, s_l, wv)]
                land_ext.setdefault(count + m, []).append(
                    [(p_[0], p_[1]) for p_ in q])
                # the landing's front edge: a step like the others — the
                # same nosing (and anti-slip strip) over the last riser
                sf = s_l - nos_p
                if ft > 0 and nos_p > 1e-4:
                    out.append((_prism(_clean(_nose_profile(
                        sf, s_l, zk[m], ft, nose_type)), o, d, r, 0.0, wv),
                        fin))
                if ft > 0 and nose_type == "strip" and wv > 0.2:
                    out.append((_prism(_box(sf + 0.012, sf + 0.052, zk[m],
                                            zk[m] + 0.003), o, d, r, 0.05,
                                       wv - 0.05), STRIP))
        if kind == "solid":
            for k in range(1, m):
                q = [_at(o, d, r, ss[k - 1] - nos, 0), _at(o, d, r, ss[k], 0),
                     _at(o, d, r, ss[k], wv), _at(o, d, r, ss[k - 1] - nos, wv)]
                out.append((W.solid({"outer": _ccw(q), "holes": []},
                                    zb, zk[k] - ft), CONCRETE))
        elif kind == "monolithic":
            prof = []

            def root(s):
                return zb + (s - ss[0]) * tan
            off = waist / cos
            T = waist                           # the landing's thickness
            if count and any(lg.get("winder_line") and
                             int(lg.get("after", -1)) == count
                             for lg in landings):
                T = waist + rise      # off winders: their one flat soffit
            if count == 0:                      # from the floor
                s_x = ss[0] + off / tan
                prof.append((ss[0], zb))
            else:                               # from a landing: the soffit
                s_x = None                      # kinks into the landing's
                s_k = ss[0] + max(off - T, 0.0) / tan
                if s_k > ss[0] + 1e-6:
                    prof.append((s_k, zb - T))
                prof.append((ss[0], zb - T))
                prof.append((ss[0], zb))
            for k in range(1, m):
                if has_fin:             # set down under the finish
                    prof += [(ss[k - 1], zk[k] - ft), (ss[k], zk[k] - ft)]
                    continue
                tn = min(0.03, rise / 3)
                prof += [(ss[k - 1], zk[k] - tn), (ss[k - 1] - nos, zk[k] - tn),
                         (ss[k - 1] - nos, zk[k]), (ss[k], zk[k])]
            ends_on = any(int(lg.get("after", -1)) == count + m
                          for lg in landings)
            if not ends_on:                     # no landing: the flight's
                prof.append((ss[m - 1], zk[m]))  # top runs on to the slab
            # into the landing (or the floor) above: the waist runs on
            # under it until its soffit meets the landing's — one clean
            # kink line, no step under the landing's edge
            s_e = ss[m - 1] + (zk[m] - T - (root(ss[m - 1]) - off)) / tan
            if ends_on:
                prof.append((ss[m - 1], zk[m] - T))
            else:
                prof.append((s_e, zk[m]))
            if s_e > ss[m - 1] + 1e-6:
                prof.append((s_e, zk[m] - T))
            if s_x is not None and s_x < s_e:
                prof.append((s_x, zb))
            out.append((_prism(_clean(prof), o, d, r, 0.0, wv), CONCRETE))
        else:                                   # open / cantilever treads
            sw = 0.05 if kind == "open" else 0.0
            for k in range(1, m):
                q = [_at(o, d, r, ss[k - 1] - nosing, sw),
                     _at(o, d, r, ss[k], sw),
                     _at(o, d, r, ss[k], wv - sw),
                     _at(o, d, r, ss[k - 1] - nosing, wv - sw)]
                out.append((W.solid({"outer": _ccw(q), "holes": []},
                                    zk[k] - tread_t, zk[k]), TIMBER))
            if kind == "open":                  # two steel stringers
                D = 0.25

                def top(s):
                    return zb + (s - ss[0]) * tan + rise + 0.05
                s0, s1 = ss[0] - nosing, ss[m - 1]
                prof = [(s0, top(s0)), (s1, top(s1)),
                        (s1, top(s1) - D / cos), (s0, top(s0) - D / cos)]
                if count == 0:
                    prof = [(x, max(z, zb)) for x, z in prof]
                for t0, t1 in ((0.0, sw), (wv - sw, wv)):
                    out.append((_prism(_clean(prof), o, d, r, t0, t1), STEEL))
        count += m
    if rail and rail != "none" and rail_sides != "none" and runs:
        out += build_rail(st, z0, rail, rail_h, rail_sides, rail_off,
                          rail_gap, rail_ext)
    for lg in landings:
        zl = z0 + lg["after"] * rise
        wl = lg.get("winder_line")
        if wl and kind in ("monolithic", "solid"):
            try:                         # the winder's riser and nosing
                a_w, b_w = tuple(wl[0][:2]), tuple(wl[1][:2])
                Lw = math.dist(a_w, b_w)
                rw = ((b_w[0] - a_w[0]) / Lw, (b_w[1] - a_w[1]) / Lw)
                dw = _nrm(lg.get("winder_d") or (-rw[1], rw[0]))
                if has_fin and rt > 0:
                    out.append((_prism(_box(-rt, 0.0, zl - rise, zl - ft),
                                       a_w, dw, rw, 0.0, Lw), fin))
                if has_fin and ft > 0 and nos_p > 1e-4:
                    out.append((_prism(_clean(_nose_profile(
                        -rt - nos_p, 0.0, zl, ft, nose_type)), a_w, dw, rw,
                        0.0, Lw), fin))
                if has_fin and ft > 0 and nose_type == "strip" and Lw > 0.2:
                    sf = -rt - nos_p
                    out.append((_prism(_box(sf + 0.012, sf + 0.052, zl,
                                            zl + 0.003), a_w, dw, rw, 0.05,
                                       Lw - 0.05), STRIP))
            except Exception:  # noqa: BLE001
                pass
        th = {"monolithic": waist, "solid": zl - z0, "open": 0.10,
              "cantilever": 0.15}[kind]
        if wl and kind == "monolithic":
            th = waist + rise         # the winders' soffit: one flat plane
        out.append((W.solid({"outer": _ccw([tuple(p) for p in lg["corners"]]),
                             "holes": []}, zl - max(th, 0.05), zl - ft),
                    CONCRETE if kind in ("monolithic", "solid") else TIMBER))
        if has_fin and ft > 0:          # the landing's finish
            try:
                from shapely.ops import unary_union as _uu
                pg = _Pg([tuple(p[:2]) for p in lg["corners"]]).buffer(0)
                ext = [_Pg(q).buffer(0) for q in
                       land_ext.get(int(lg.get("after", -1)), [])]
                u = _uu([pg] + ext).buffer(1e-4, join_style=2).buffer(
                    -1e-4, join_style=2)
                for g_ in getattr(u, "geoms", [u]):
                    if g_.geom_type == "Polygon" and g_.area > 1e-3:
                        out.append((W.solid({"outer": _ccw(list(
                            g_.exterior.coords)[:-1]), "holes": []},
                            zl - ft, zl), fin))
            except Exception:  # noqa: BLE001
                pass
    return out


def _ext(path, ext, at_end):
    """The path run on ``ext`` past its first (or last) point, level."""
    if ext <= 0 or len(path) < 2:
        return path
    if at_end:
        p, q = path[-2], path[-1]
    else:
        p, q = path[1], path[0]
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    if L < 1e-6:
        return path
    e = (q[0] + (q[0] - p[0]) / L * ext, q[1] + (q[1] - p[1]) / L * ext, q[2])
    return path + [e] if at_end else [e] + path


def railing(st, runs, kind, h=0.9, sides="inner", gap=0.0, ext=0.0,
            inset=0.05, floor=None, walls=None) -> list:
    """[(faces, colour)] of the stair's railing: on the inner side of its
    flights (the side by the well, joined across each landing), the outer
    (the wall side), or both. A single straight flight has no well: both
    sides, unless «inner» / «outer» picks one."""
    from .engine import railings as RL
    if sides == "none":
        return []
    nfl = max(r[0] for r in runs) + 1
    cs = st.get("corners") or []
    cx = sum(p[0] for p in cs) / len(cs) if cs else 0.0
    cy = sum(p[1] for p in cs) / len(cs) if cs else 0.0

    def far(r):
        mx, my = (r[2][0] + r[3][0]) / 2, (r[2][1] + r[3][1]) / 2
        return math.hypot(mx - cx, my - cy)
    both = sides == "both" or (nfl == 1 and sides not in ("outer",)
                               and not st.get("rail_sides"))
    out = []
    if both and nfl > 1:
        # both sides of a stair with landings: the well side joined across
        # each landing, and the wall side turning round the landings — the
        # landing's open edges railed too
        return railing(st, runs, kind, h, "inner", gap, ext, inset,
                       floor, walls) + \
            railing(st, runs, kind, h, "outer", gap, ext, inset, floor,
                    walls)
    if both:
        for i in range(nfl):
            for r in (r for r in runs if r[0] == i):
                path = [r[2], r[3]]
                if i == 0:
                    path = _ext(path, ext, False)
                if i == nfl - 1:
                    path = _ext(path, ext, True)
                out += _pieces(path, h, kind, gap, floor)
        return out
    picked = []
    want = _inner_sides(st)            # the well side of each flight, by
    hand = st.get("turns") is not None  # its turns (left / right of climb)
    for i in range(nfl):
        two = [r for r in runs if r[0] == i]
        w_ = want[i] if want and i < len(want) else None
        if nfl > 1 and w_ is not None and len(two) == 2 and not (
                walls is not None and not hand and _walled_one(
                    two, walls, inset)):
            inner = next((r for r in two if r[1] == w_), two[0])
            outer = next((r for r in two if r is not inner), two[-1])
            picked.append(outer if sides == "outer" else inner)
            continue
        if nfl == 1:                   # one flight: inner = its left side
            picked.append(next((r for r in two
                                if r[1] == (sides != "outer")), two[0]))
            continue
        # the inner side: the one towards the flights before and after
        # (the well of a dog-leg, the inside corner of an L) — not the one
        # nearest the stair's middle, which an L's long flight gets wrong
        nb = [_fmid(runs, j) for j in (i - 1, i + 1) if 0 <= j < nfl]
        tx = sum(q[0] for q in nb) / len(nb)
        ty = sum(q[1] for q in nb) / len(nb)

        def near(r, _t=(tx, ty)):
            mx, my = (r[2][0] + r[3][0]) / 2, (r[2][1] + r[3][1]) / 2
            return math.hypot(mx - _t[0], my - _t[1])
        # a side running along a wall needs no railing: the open side
        if walls is not None and len(two) == 2:
            from shapely.geometry import LineString
            walled = [walls.distance(LineString([r[2][:2], r[3][:2]]))
                      < inset + 0.15 for r in two]
            if walled[0] != walled[1]:
                op_ = two[1] if walled[0] else two[0]
                wl_ = two[0] if walled[0] else two[1]
                picked.append(wl_ if sides == "outer" else op_)
                continue
        picked.append(max(two, key=near) if sides == "outer"
                      else min(two, key=near))
    lands = [lg for lg in (as_flights(st)[1] or []) if not lg.get("arrival")]
    # one railing from the bottom to the top, across the landings (the
    # outer one turns round the landing's far corners)
    paths, path = [], []
    for r in picked:
        p, q = r[2], r[3]
        if path and math.hypot(p[0] - path[-1][0], p[1] - path[-1][1]) > \
                (3.0 if sides != "outer" else 8.0):
            paths.append(path)
            path = []
        if path:                      # across the landing, at its level
            last = path[-1]
            if sides == "outer" and lands:
                # round the landing: on along the last flight to its far
                # edge, across it, and back to the next flight
                pl = path[-2]
                L = math.hypot(last[0] - pl[0], last[1] - pl[1]) or 1.0
                u = ((last[0] - pl[0]) / L, (last[1] - pl[1]) / L)
                mid = ((last[0] + p[0]) / 2, (last[1] + p[1]) / 2)
                lg = min(lands, key=lambda g: min(
                    math.hypot(c[0] - mid[0], c[1] - mid[1])
                    for c in g["corners"]))
                k = max((c[0] - last[0]) * u[0] + (c[1] - last[1]) * u[1]
                        for c in lg["corners"]) - inset
                kp = (p[0] - last[0]) * u[0] + (p[1] - last[1]) * u[1]
                if k > 0.05:
                    path.append((last[0] + u[0] * k, last[1] + u[1] * k,
                                 last[2]))
                    if k - kp > 0.05:
                        path.append((p[0] + u[0] * (k - kp),
                                     p[1] + u[1] * (k - kp), last[2]))
            path.append((p[0], p[1], path[-1][2]))
        path += [p, q]
    if len(path) >= 2:
        paths.append(path)
    if paths:
        paths[0] = _ext(paths[0], ext, False)
        paths[-1] = _ext(paths[-1], ext, True)
    paths = [_smooth(pth) for pth in paths]
    out = []
    for pth in paths:
        if len(pth) >= 2:
            out += _pieces(pth, h, kind, gap, floor)
    return out


def _walled_one(two, walls, inset) -> bool:
    """One side of the flight runs along a wall, the other is open."""
    from shapely.geometry import LineString
    w = [walls.distance(LineString([r[2][:2], r[3][:2]])) < inset + 0.15
         for r in two]
    return w[0] != w[1]


def _inner_sides(st) -> list:
    """For each flight (of two risers or more, as ``_runs`` counts them):
    the «is-left» flag of ``_runs`` of its well side — the side it turns
    to at its landing (a left turn or U-turn left: its left), else the
    side the turn before it came from, else the flight before's side. None
    where a stair runs straight all the way."""
    flights, _l = as_flights(st)
    keep = [f for f in flights if len(f["lines"]) >= 2]
    if len(keep) < 2:
        return []
    turns = flight_turns({"traced": True, "flights": keep, "landings": []})

    def side(t):
        return "L" if t in ("left", "uleft") else \
            "R" if t in ("right", "uright") else None
    climb = []
    for i in range(len(keep)):
        s_ = side(turns[i]) if i < len(turns) else None
        if s_ is None and i > 0:
            s_ = side(turns[i - 1])
        climb.append(s_)
    for i in range(1, len(climb)):          # straight on: the side before
        if climb[i] is None:
            climb[i] = climb[i - 1]
    for i in range(len(climb) - 2, -1, -1):
        if climb[i] is None:
            climb[i] = climb[i + 1]
    if all(c is None for c in climb):        # straight all the way: one
        climb = ["L"] * len(climb)           # side, not crossing over
    out = []
    for f, s_ in zip(keep, climb):
        if s_ is None:
            out.append(None)
            continue
        (a, b) = f["lines"][0]
        d = _nrm(f["d"])
        lf = (-d[1], d[0])
        r = (b[0] - a[0], b[1] - a[1])
        a_left = (r[0] * lf[0] + r[1] * lf[1]) < 0   # going a→b goes right
        out.append(a_left if s_ == "L" else not a_left)
    return out


def _pieces(path, h, kind, gap, floor) -> list:
    """[(faces, None)] — the railing along ``path`` in straight pieces
    (each run between two turns, level or sloping, its own piece: one
    component in the model to edit or delete)."""
    from .engine import railings as RL
    pts = [tuple(p) for p in path]
    runs, cur = [], [pts[0]]
    for q in pts[1:]:
        if len(cur) >= 2:
            a, b = cur[-2], cur[-1]
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (q[0] - b[0], q[1] - b[1], q[2] - b[2])
            Lu = math.sqrt(sum(c * c for c in u)) or 1.0
            Lv = math.sqrt(sum(c * c for c in v)) or 1.0
            cos = sum(x * y for x, y in zip(u, v)) / (Lu * Lv)
            if cos < 0.999:                      # a turn: a new piece
                runs.append(cur)
                cur = [b]
        cur.append(q)
    runs.append(cur)
    out = []
    for r in runs:
        if len(r) >= 2 and math.hypot(r[-1][0] - r[0][0],
                                      r[-1][1] - r[0][1]) > 0.05:
            out.append((RL.faces([r[0], r[-1]], h, kind, gap=gap,
                                 floor=floor), None))
    return out


def _fmid(runs, i):
    """The middle of flight ``i`` on plan (between its two side runs)."""
    rs = [r for r in runs if r[0] == i]
    xs = [p[0] for r in rs for p in (r[2], r[3])]
    ys = [p[1] for r in rs for p in (r[2], r[3])]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _smooth(path):
    """A railing path without its jumps: two points on the same spot (the
    landing's level, then the next flight's first nosing) made one — the
    rail runs on into the next flight instead of a step straight up;
    two inner lines meeting at an L landing turned at their corner."""
    out = []
    for p in path:
        if out and math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) < 0.01:
            out[-1] = (out[-1][0], out[-1][1], max(out[-1][2], p[2]))
            continue
        out.append(tuple(p))
    # an L: the two lines' corner, not a diagonal cut across it
    res = out[:1]
    for k in range(1, len(out)):
        a, b = res[-1], out[k]
        if k >= 2 and k + 1 < len(out):
            pa, nb = res[-2], out[k + 1]
            u = (a[0] - pa[0], a[1] - pa[1])
            v = (nb[0] - b[0], nb[1] - b[1])
            Lu, Lv = math.hypot(*u), math.hypot(*v)
            if Lu > 0.05 and Lv > 0.05:
                u = (u[0] / Lu, u[1] / Lu)
                v = (v[0] / Lv, v[1] / Lv)
                cr = u[0] * v[1] - u[1] * v[0]
                if abs(cr) > 0.7:                # square turn
                    t_ = ((b[0] - a[0]) * v[1] - (b[1] - a[1]) * v[0]) / cr
                    c = (a[0] + u[0] * t_, a[1] + u[1] * t_)
                    if 0 <= t_ <= 1.5 and math.hypot(c[0] - b[0],
                                                    c[1] - b[1]) < 1.5:
                        res.append((c[0], c[1], a[2]))
        res.append(b)
    fin = []
    for p in res:
        if fin and math.dist(p, fin[-1]) < 0.005:
            continue
        fin.append(p)
    return fin


def _at(o, d, r, s, t):
    return (o[0] + d[0] * s + r[0] * t, o[1] + d[1] * s + r[1] * t)


# ---- flights turned by hand: the landings follow ---------------------------------------
TURNS = [("straight", "Straight on"), ("left", "Turn left 90°"),
         ("right", "Turn right 90°"), ("uleft", "U-turn left (180°)"),
         ("uright", "U-turn right (180°)")]
U_GAP = 0.10                 # m between the two flights of a U


def _nrm(v):
    n = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / n, v[1] / n)


def _frame(f):
    """A flight's first riser line as (a, r across, w width, d up, g)."""
    (a, b) = f["lines"][0]
    a, b = (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
    w = math.dist(a, b) or float(f.get("w") or 1.0)
    r = ((b[0] - a[0]) / w, (b[1] - a[1]) / w)
    d = _nrm(f["d"])
    return a, r, w, d, float(f.get("g") or GOING_MIN)


def _left_of(d):
    return (-d[1], d[0])


def flight_turns(st) -> list:
    """How each flight after the first leaves the landing before it:
    "straight", "left", "right", "uleft", "uright" (seen climbing)."""
    flights = real_flights(st)
    out = []
    for f0, f1 in zip(flights, flights[1:]):
        d0, d1 = _nrm(f0["d"]), _nrm(f1["d"])
        dot = d0[0] * d1[0] + d0[1] * d1[1]
        cr = d0[0] * d1[1] - d0[1] * d1[0]
        if dot > 0.7:
            out.append("straight")
        elif dot < -0.7:
            m0 = _mid(f0["lines"][-1])
            m1 = _mid(f1["lines"][0])
            lf = _left_of(d0)
            side = (m1[0] - m0[0]) * lf[0] + (m1[1] - m0[1]) * lf[1]
            out.append("uleft" if side > 0 else "uright")
        else:
            out.append("left" if cr > 0 else "right")
    return out


def relay(st, turns=None, rot=0.0, counts=None, gap=U_GAP) -> dict:
    """The stair laid again flight by flight: each flight keeps its width
    and tread, ``counts`` its risers, ``turns`` how it leaves the landing
    before it, the whole stair turned ``rot`` degrees round its foot (the
    first riser's middle). Every landing is made again to fit its turn —
    a square for a 90° turn, both flights' width for a U, a flight's width
    on a straight run — and the arrival landing past the last riser. The
    storey height stays (the riser height follows the risers' number)."""
    flights = real_flights(st)
    if not flights:
        return dict(st)
    turns0 = list(turns or flight_turns(st))
    if counts:                     # flights added (like the last) / dropped
        flights = list(flights[:len(counts)])
        while len(flights) < len(counts):
            flights.append(dict(flights[-1]))
    nf = len(flights)
    turns = turns0[:nf - 1]
    turns += ["right"] * (nf - 1 - len(turns))
    cnt = [len(f["lines"]) for f in flights]
    if counts and len(counts) == nf:
        cnt = [max(2, int(c)) for c in counts]
    a, r, w, d, g = _frame(flights[0])
    foot = (a[0] + r[0] * w / 2, a[1] + r[1] * w / 2)
    if rot:
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))

        def R(v):
            return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)
        r, d = R(r), R(d)
        a = (foot[0] - r[0] * w / 2, foot[1] - r[1] * w / 2)

    def P(o, v, k):
        return (o[0] + v[0] * k, o[1] + v[1] * k)

    def L(p):
        return [round(p[0], 4), round(p[1], 4)]
    new_f, new_l = [], []
    climbed = 0
    for k in range(nf):
        m = cnt[k]
        lines = []
        for j in range(m):
            p = P(a, d, j * g)
            lines.append([L(p), L(P(p, r, w))])
        new_f.append({"lines": lines, "d": [round(d[0], 6), round(d[1], 6)],
                      "w": round(w, 4), "g": round(g, 4)})
        climbed += m
        A = P(a, d, (m - 1) * g)          # the last riser's a end
        if k == nf - 1:
            pts = [A, P(A, r, w), P(P(A, r, w), d, w), P(A, d, w)]
            new_l.append({"corners": [L(p) for p in pts],
                          "after": climbed, "arrival": True})
            break
        _a2, _r2, w2, _d2, g2 = _frame(flights[k + 1])
        t = turns[k]
        lf = _left_of(d)
        r_left = (r[0] * lf[0] + r[1] * lf[1]) > 0   # r points left
        if t in ("left", "right"):
            to_r = (t == "left") == r_left           # leaves on r's side
            pts = [A, P(A, r, w), P(P(A, r, w), d, w2), P(A, d, w2)]
            if to_r:
                na = P(P(A, r, w), d, w2)
                nr, nd = (-d[0], -d[1]), r
            else:
                na = A
                nr, nd = d, (-r[0], -r[1])
        elif t in ("uleft", "uright"):
            to_r = (t == "uleft") == r_left
            D = max(w, w2)
            if to_r:
                lo, hi = 0.0, w + gap + w2
                na = P(A, r, w + gap + w2)
            else:
                lo, hi = -(gap + w2), w
                na = P(A, r, -gap)
            nr, nd = (-r[0], -r[1]), (-d[0], -d[1])
            p0, p1 = P(A, r, lo), P(A, r, hi)
            pts = [p0, p1, P(p1, d, D), P(p0, d, D)]
        else:                                        # straight on
            D = max(w, 0.9)
            pts = [A, P(A, r, w), P(P(A, r, w), d, D), P(A, d, D)]
            na, nr, nd = P(A, d, D), r, d
            if abs(w2 - w) > 1e-3:                   # centred on the run
                na = P(na, r, (w - w2) / 2)
        new_l.append({"corners": [L(p) for p in pts], "after": climbed})
        a, r, w, d, g = na, nr, w2, nd, g2
    H = float(st.get("rise", RISER)) * int(st.get("risers", sum(
        len(f["lines"]) for f in flights)) or 1)
    n = sum(len(f["lines"]) for f in new_f)
    out = dict(st, traced=True, kind="traced", flights=new_f,
               landings=new_l, risers=n, rise=round(H / n, 4),
               going=new_f[0]["g"], turns=turns, rot=float(rot or 0.0),
               counts=[len(f["lines"]) for f in new_f])
    out.pop("flip", None)
    out["corners"] = outline_of(out)
    return out


def foot_of(st):
    """The middle of a stair's first riser line."""
    flights, _l = as_flights(st)
    if not flights:
        return None
    return _mid(flights[0]["lines"][0])


def well_of(doc, st):
    """The well a stair cuts (as the import cuts it)."""
    stt = doc.get("settings") or {}
    H = float(st.get("rise", RISER)) * int(st.get("risers", 18))
    well = st["corners"]
    wm = stt.get("stair_well", "railing")
    if wm != "outline" and stt.get("stair_headroom_cut", True):
        hc = headroom_cut(st, H, float(stt.get("slab_t", 0.15)),
                          float(stt.get("stair_head", HEADROOM)), wm)
        if hc:
            well = hc
    return well


def recut(doc, old, new) -> int:
    """The well of stair ``old`` closed, ``new``'s cut instead."""
    from shapely.geometry import Polygon

    from . import project as PJ
    arch = doc["arch"]
    o = Polygon(old.get("corners") or [])
    if o.is_valid and o.area > 0:
        for s in arch["structure"]:
            if s["type"] != "slab":
                continue
            keep = []
            for h in s.get("holes") or []:
                hp = Polygon(h)
                if hp.is_valid and hp.area >= 0.5 and \
                        hp.intersection(o).area >= 0.9 * hp.area:
                    continue
                keep.append(h)
            s["holes"] = keep
    well = well_of(doc, new)
    if PJ.slab_on_top(doc):
        return _cut(arch, new["level"], well)
    if new.get("to"):
        return _cut(arch, new["to"], well)
    return 0
