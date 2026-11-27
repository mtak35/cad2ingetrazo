"""3.64.101: the roof as the reference elevations draw it.

The elevations the drawing holds (and the pictures added in «Elevations /
perspectives to follow…») show the roof's silhouette on each side. Here
that silhouette is read: for every side, the highest line over each
position along the side (the roof's profile, the walls' own height taken
off). A roof block of the plan is then given the form the profiles say:

- how high its ridge stands over the walls (both views must show it: the
  lower of the two peaks);
- its slope, from that height over the half of its narrower side;
- a hip roof when both views taper to the ridge, a gable when one view
  runs flat along it (the ridge runs along that view's side);
- no pitched roof (the flat roof and its parapets stay) when the
  silhouette stays under half a metre over the walls.

Nothing is read from a photograph's perspective: it gives the look (the
colours, the style), the elevations give the form.
"""
from __future__ import annotations

import math

STEP = 0.1                 # m: the profile's sampling along a side
MIN_RISE = 0.5             # m: less over the walls: a flat roof
EAVE_DEFAULT = 0.6

#: side → the view's right vector: u = x·r[0] + y·r[1]
_R = {"west": (0.0, -1.0), "east": (0.0, 1.0),
      "north": (-1.0, 0.0), "south": (1.0, 0.0)}


# ---- the silhouettes -----------------------------------------------------------
def _segments(doc) -> dict:
    """{side: [(u0, z0, u1, z1)]} in model metres: the CAD's elevations
    (read again on a copy of the document) and the added pictures that
    were followed (their stored fit)."""
    import copy

    from . import elevread as EV
    out = {}
    try:
        files = [h.get("file") for h in doc["imports"].values()
                 if h.get("file")]
        if files:
            EV.apply(copy.deepcopy(doc))
            for D, segs in EV.PROFILES.items():
                out[D] = list(segs)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("roofref CAD elevations")
    from . import refelev as RE
    for i_, ref in enumerate(doc.get("ref_elev") or []):
        if RE.effective_side(ref) == "perspective" or \
                not ref.get("follow", True):
            continue
        fit = ref.get("fit")
        if not fit:                       # not followed yet: on a copy
            try:
                cp_ = copy.deepcopy(doc)
                RE.follow(cp_, cp_["ref_elev"][i_])
                fit = cp_["ref_elev"][i_].get("fit")
            except Exception:  # noqa: BLE001
                fit = None
        if not fit or fit.get("side") not in _R:
            continue
        if fit["side"] in out:
            continue
        try:
            src = RE.source(ref["file"], int(ref.get("page", 1) or 1))
        except Exception:  # noqa: BLE001
            continue
        s_, t_, y0, z0 = (float(fit[k]) for k in ("s", "t", "y0", "z0"))
        out[fit["side"]] = [(s_ * a + t_, z0 + s_ * (b - y0),
                             s_ * c + t_, z0 + s_ * (d - y0))
                            for a, b, c, d in src["segs"]]
    return out


def envelope(segs, u0, u1, z_lo, z_hi, step=STEP):
    """The upper outline of the lines over [u0, u1]: [(u, z)] — the
    highest line crossing each position (a vertical line alone makes no
    roof: a flag pole, a post; a line longer than the span: a ground or
    dimension line). Positions with no line: None."""
    span = max(u1 - u0, 1.0)
    use = []
    for a, b, c, d in segs:
        if abs(c - a) < 0.25 or abs(c - a) > 1.4 * span:
            continue
        if max(b, d) < z_lo or min(b, d) > z_hi:
            continue
        if a > c:
            a, b, c, d = c, d, a, b
        use.append((a, b, c, d))
    n = int((u1 - u0) / step) + 1
    top = [None] * n
    for a, b, c, d in use:
        i0 = max(int(math.ceil((a - u0) / step)), 0)
        i1 = min(int(math.floor((c - u0) / step)), n - 1)
        for i in range(i0, i1 + 1):
            u = u0 + i * step
            z = b + (d - b) * (u - a) / (c - a)
            if z > z_hi:
                continue
            if top[i] is None or z > top[i]:
                top[i] = z
    return [(u0 + i * step, top[i]) for i in range(n)]


def _fill(prof):
    """Gaps in a profile bridged (a window of the drawing's edge): the
    value of the nearest known neighbour."""
    zs = [z for _u, z in prof]
    last = None
    for i, z in enumerate(zs):
        if z is None:
            zs[i] = last
        else:
            last = z
    nxt = None
    for i in range(len(zs) - 1, -1, -1):
        if zs[i] is None:
            zs[i] = nxt
        else:
            nxt = zs[i]
    return [(u, z) for (u, _z), z in zip(prof, zs)]


# ---- the blocks ------------------------------------------------------------------
def _near(prof, u0, tol=0.6):
    """The profile's height at (or nearest to) position u0."""
    best = None
    for u, z in prof:
        if z is None or abs(u - u0) > tol:
            continue
        if best is None or abs(u - u0) < best[0]:
            best = (abs(u - u0), z)
    return best[1] if best else None


def _slice(prof, a, b):
    return [z for u, z in prof if a <= u <= b and z is not None]


def _fit_block(cs, profs, z_wall):
    """The roof a block's corners ``cs`` take from the profiles: a dict
    (kind, slope, eave, ridge) or None for a flat roof."""
    xs = [p[0] for p in cs]
    ys = [p[1] for p in cs]
    e1 = math.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = math.hypot(cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    long_x = abs(cs[1][0] - cs[0][0]) >= abs(cs[1][1] - cs[0][1])
    if e2 > e1:
        long_x = not long_x
    peaks, flats, eaves = {}, {}, []
    for D, prof in profs.items():
        r = _R[D]
        us = [x * r[0] + y * r[1] for x, y in cs]
        ua, ub = min(us), max(us)
        zs = _slice(prof, ua, ub)
        if not zs:
            continue
        # the eave: where the silhouette stands at the block's two edges
        # (the roof's own base in the drawing: a drawing's levels may sit
        # a little off the model's)
        ze = [_near(prof, ua), _near(prof, ub)]
        ze = [z for z in ze if z is not None]
        z_e = min(ze) if ze else z_wall
        z_e = min(z_e, z_wall + 0.3)
        rise = [z - z_e for z in zs]
        pk = max(rise)
        peaks[D] = pk
        # how much of the block's span the silhouette holds near its peak
        if pk > MIN_RISE:
            flats[D] = sum(1 for v in rise if v >= 0.88 * pk) / len(rise)
        # the eave: how far the roof's edge reaches out past the walls at
        # the walls' top
        low = [(u, z) for u, z in prof
               if z is not None and ua - 2.5 <= u <= ub + 2.5]
        out = [u for u, z in low if z >= z_e - 0.45 and (
            u < ua or u > ub)]
        if out:
            eaves.append(max(max(ua - min(out), 0.0),
                             max(max(out) - ub, 0.0)))
    if not peaks:
        return None
    H = min(peaks.values())
    if H < MIN_RISE:
        return None
    short = min(e1, e2)
    eave = min(max(sum(eaves) / len(eaves), 0.25), 1.0) if eaves \
        else EAVE_DEFAULT
    slope = math.degrees(math.atan2(H, short / 2.0 + eave))
    slope = min(max(slope, 8.0), 62.0)
    kind, ridge = "hip", "long"
    flat_axes = [D for D, f in flats.items() if f >= 0.8]
    if len(flats) == 2 and len(flat_axes) == 1:
        D = flat_axes[0]                 # the ridge runs along this view
        along_x = D in ("north", "south")
        kind = "gable"
        ridge = "long" if along_x == long_x else "short"
    elif len(flats) == 2 and len(flat_axes) == 2:
        return None                      # a box over the walls: no roof
    return {"kind": kind, "slope": round(slope, 1), "eave": round(eave, 2),
            "ridge": ridge, "rise": round(H, 2)}


def apply(doc, color=None) -> dict:
    """Roofs of the reference elevations over the top blocks (and the
    annexes) — the look's roofs made again from the silhouettes. A
    report: {"roofs": n, "sources": [sides], "flat": n} or {"note": why
    nothing was done}."""
    from . import lookstyle as LS
    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    arch = doc["arch"]
    levels = arch["levels"]
    segs = _segments(doc)
    if not segs:
        return {"note": "no elevation drawing to follow (add elevations in "
                        "«Elevations / perspectives to follow…» or read "
                        "them from the CAD)"}
    el = PJ.elevations(arch)
    order = sorted(range(len(levels)), key=lambda i: el[i])
    top = order[-1]
    roof_lv = levels[top]["id"] if str(levels[top].get("name", "")).strip(
        ).lower() == "roof" or all(
        str(w.get("name", "")).lower().startswith(
            ("roof parapet", "roof edge")) or w.get("rail")
        for w in arch["walls"] if w["level"] == levels[top]["id"]) else None
    under = levels[order[-2]]["id"] if roof_lv and len(order) >= 2 \
        else levels[top]["id"]
    ui = next(i for i, lv in enumerate(levels) if lv["id"] == under)
    slab_t = float(doc["settings"].get("slab_t", 0.1016) or 0.1016)
    z_wall = el[ui] + float(levels[ui]["height"]) + slab_t
    poly, ws = LS._outline(arch, under, roof=True)
    if poly is None:
        return {"note": "the top floor has no outline"}
    b = poly.bounds
    z_hi = z_wall + 9.0
    profs = {}
    for D, sg in segs.items():
        r = _R[D]
        us = [x * r[0] + y * r[1] for x, y in
              ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]))]
        pr = envelope(sg, min(us) - 3.0, max(us) + 3.0, z_wall - 1.2, z_hi)
        got = sum(1 for u_, z in pr if z is not None
                  and min(us) <= u_ <= max(us))
        if got >= 0.25 * max((max(us) - min(us)) / STEP, 1.0):
            profs[D] = _fill(pr)
    if not profs:
        return {"note": "the elevations show no roof outline over the "
                        "building"}
    from shapely import affinity
    ang = LS._frame_angle(ws)
    c = poly.centroid
    p0 = affinity.rotate(poly, -ang, origin=c, use_radians=True).simplify(0.05)
    if p0.geom_type != "Polygon":
        p0 = max(p0.geoms, key=lambda g: g.area)
    # 3.64.164: a mosque's roof is where the elevations hatch it (the
    # porch's tiles): its parapet rows, domes and minarets are no pitched
    # roofs over the top blocks
    from . import elevread as EV_
    only_hatch = bool((doc.get("look") or {}).get("mosque")) and EV_.HATCH \
        and not any(z1 >= z_wall - 0.5 for hv in EV_.HATCH.values()
                    for _a, _b, _z0, z1 in hv["roofs"])
    old = [e for e in arch["structure"] if LS.is_look_roof(e)]
    arch["structure"] = [e for e in arch["structure"]
                         if not LS.is_look_roof(e)]
    recs, flat, pitched = [], 0, []
    terr_ = LS.terrace_union(arch, under)
    for x0, y0, x1, y1 in LS.rectangles(p0):
        cs = []
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            dx, dy = x - c.x, y - c.y
            cs.append([round(c.x + dx * math.cos(ang) - dy * math.sin(ang), 4),
                       round(c.y + dx * math.sin(ang) + dy * math.cos(ang), 4)])
        fit = None if only_hatch else _fit_block(cs, profs, z_wall)
        if fit is None:
            flat += 1
            continue
        rec = {"type": "roof", "level": under, "kind": fit["kind"],
               "corners": cs, "slope": fit["slope"],
               "overhang": LS.eave_clear(cs, fit["eave"], terr_),
               "t": 0.15, "ridge": fit["ridge"],
               "parapet": 0.0, "pt": 0.15, "tiles": True, "look": True}
        if S.why_not(rec):
            continue
        recs.append(rec)
        pitched.append(cs)
    if recs:
        arch["structure"] += M.new_elements(arch["structure"], recs)
    n = len(recs)
    # the roof's parapets go under the pitched roofs only
    if pitched and roof_lv:
        from shapely.geometry import Point, Polygon
        zone = [Polygon(cs).buffer(0.6) for cs in pitched]
        n0 = len(arch["walls"])
        arch["walls"] = [w for w in arch["walls"] if not (
            w["level"] == roof_lv and (str(w.get("name", "")).lower()
                                       .startswith(("roof parapet",
                                                    "roof edge"))
                                       or w.get("rail")) and any(
            z_.contains(Point((w["a"][0] + w["b"][0]) / 2,
                              (w["a"][1] + w["b"][1]) / 2))
            for z_ in zone))]
        parapets = n0 - len(arch["walls"])
    else:
        parapets = 0
    # a single-storey annex under the main roof: the slope the walls' roof
    # took (its own silhouette is hidden behind the main one)
    if recs:
        sl = sum(r["slope"] for r in recs) / len(recs)
        ev = sum(r["overhang"] for r in recs) / len(recs)
        n += LS.annex_roofs(doc, sl, ev * 0.75, kind=recs[0]["kind"])
        if color:
            doc.setdefault("materials", {})["roof"] = {
                "name": "Roof tiles, as designed", "color": list(color)}
    elif old:
        pass
    if pitched:
        doc["settings"]["roof_parapet"] = bool(flat)
    try:                               # 3.64.164: the porch's hatched roof
        n_h = EV_.hatch_roofs(doc)
        n += n_h
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("roofref hatch roofs")
    rep = {"roofs": n, "sources": sorted(profs), "flat": flat}
    if parapets:
        rep["parapets_off"] = parapets
    if recs:
        rep["forms"] = ", ".join(sorted({
            f"{r['kind']} {r['slope']:.0f}°" for r in recs}))
    return rep
