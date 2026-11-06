# SPDX-License-Identifier: GPL-3.0-or-later
"""BIM coordination: the consultants' drawings — structure, HVAC, water
supply, drainage, fire fighting, electrical, low current, gas — each its own
DWG / DXF, laid over the architectural floor it belongs to.

* **Superimposed**: every line of the discipline's part of its drawing, on
  the floor, at the height that discipline runs at (ducts under the slab
  over the floor, drainage below them, …), in its colour — in the plan view
  of the floor and in 3D. Placed by the same reference point picked on the
  architectural floor (the grid point both drawings share), moved / turned
  by hand, or lined up with the architecture automatically.
* **3D runs**: ducts and cable trays from their pairs of lines (their size
  from the WxH written by them), pipes from single lines (their Ø written
  by them) — as boxes and round-ish pipes in the model.
* **Clashes**: the runs against the beams, columns, walls and slabs, and
  against each other (one discipline's against another's) — hard clashes
  (a duct through a beam), soft ones (a pipe through a wall: a sleeve) —
  listed, marked in the model, written to a CSV.
* **Structure to the model**: the structural drawing's columns and beams
  in place of the architect's.

``doc["coord"]`` = [{id, level, disc, file, unit, region, bx, by, dx, dy,
drot, z, on, runs_on, off}] and ``doc["clashes"]`` = [{...}]."""
from __future__ import annotations

import math
import os
import re
import uuid

#: the disciplines: key → (label, colour, the layers that are its own,
#: what its single lines are (pipe / line), the default Ø / size)
DISC = {
    "structure": ("Structural", (120, 120, 128),
                  r"COL|BEAM|SLAB|STR|S-|FOOT|PILE|SHEAR|RCC|GRID|AXIS", None),
    "hvac": ("HVAC (ducts)", (0, 150, 220),
             r"DUCT|HVAC|M-|MECH|SUPPLY|RETURN|EXHAUST|FRESH|\bSA\b|\bRA\b|"
             r"\bEA\b|\bFA\b|DIFF|GRILL|FCU|AHU|VRF|VRV|AC\b|A\.C|DRAIN.*AC",
             "pipe"),
    "plumbing": ("Water supply", (30, 90, 255),
                 r"PLUMB|WATER|\bCW\b|\bHW\b|P-|PIPE|SUPPLY|W\.S|WS\b",
                 "pipe"),
    "drainage": ("Drainage", (150, 90, 30),
                 r"DRAIN|SOIL|WASTE|SEW|VENT|RWP|R\.W|STORM|D-|SW\b|FD\b",
                 "pipe"),
    "fire": ("Fire fighting", (225, 30, 30),
             r"FIRE|SPRINK|\bFF\b|HYDR|F-|FHC|LANDING", "pipe"),
    "electrical": ("Electrical", (235, 170, 0),
                   r"ELEC|LIGHT|POWER|TRAY|TRUNK|CABLE|E-|\bLV\b|\bDB\b|"
                   r"LUM|SOCKET|BUS", "line"),
    "elv": ("Low current (ELV)", (150, 60, 200),
            r"ELV|CCTV|DATA|TEL|FA\b|FIRE ALARM|BMS|PA\b|SECUR", "line"),
    "gas": ("Gas", (240, 120, 20), r"GAS|LPG|SNG", "pipe"),
}
ORDER = list(DISC)

#: the height a discipline runs at, from the top (under the slab over the
#: floor) down: its runs' top (m below the slab's underside); structure on
#: the floor
DROP = {"hvac": 0.05, "electrical": 0.05, "elv": 0.08, "fire": 0.10,
        "plumbing": 0.45, "gas": 0.55, "drainage": 0.65}
#: default pipe Ø (m) per discipline when none is written by the line
PIPE_D = {"plumbing": 0.032, "drainage": 0.10, "fire": 0.10, "gas": 0.025,
          "hvac": 0.032}
DUCT_H = 0.30                  # a duct's depth when none is written
TRAY_H = 0.10

#: the architect's background in a consultant's drawing (its x-ref): drawn
#: faint, never made a run
BACKGROUND = re.compile(r"\bWALL|^A-|DOOR|WIN|\bCOL|STAIR|FURN|DIM|HATCH|"
                        r"TEXT|TITLE|BORDER|FRAME|VIEWPORT|DEFPOINTS|X-?REF|"
                        r"\$0\$|ARCH|PARTITION|FLOOR|ROOM|TOILET|SANIT|"
                        r"FIXTURE|LIFT|RAMP|PARK|CAR\b", re.I)

_cache: dict = {}
_doc_memo = None


# ---- the records ------------------------------------------------------------
def load(doc, raw, ids) -> None:
    """``doc["coord"]`` / ``doc["clashes"]`` / ``doc["mep_runs"]`` kept from
    the stored document (their levels still there)."""
    out = []
    for o in raw.get("coord") or []:
        if not isinstance(o, dict) or o.get("level") not in ids or \
                o.get("disc") not in DISC or not o.get("file"):
            continue
        out.append(dict(o))
    doc["coord"] = out
    keep = {o["id"] for o in out}
    doc["mep_runs"] = {k: v for k, v in (raw.get("mep_runs") or {}).items()
                       if k in keep and isinstance(v, list)}
    doc["clashes"] = [c for c in raw.get("clashes") or []
                      if isinstance(c, dict) and c.get("level") in ids]


def new(doc, lid, disc, path, unit=None) -> dict:
    """A drawing laid over the floor ``lid``: placed as the floor's
    architectural drawing is (the same reference point, when both are
    drawn to the same coordinates) — move it, or pick its part, after."""
    how = (doc.get("imports") or {}).get(lid) or {}
    o = {"id": uuid.uuid4().hex[:8], "level": lid, "disc": disc,
         "file": path, "unit": unit or how.get("unit"),
         "region": None, "bx": None, "by": None,
         "dx": 0.0, "dy": 0.0, "drot": 0.0, "z": None, "on": True,
         "runs_on": True, "off": [],
         "name": os.path.basename(path)}
    try:                       # the architect's reference point, in the
        from . import cadread  # consultant's units (same coordinates)
        if how.get("file"):
            ra = cadread.read(how["file"], how.get("unit"))
            da = cadread.crop(ra, how.get("region"))
            ba = cadread.base_point(da, how.get("base", "origin"),
                                    (how.get("bx", 0.0), how.get("by", 0.0)))
            ro = cadread.read(path, o["unit"])
            k = float(ra["unit"]) / float(ro["unit"] or 1.0)
            o["bx"], o["by"] = ba[0] * k, ba[1] * k
            if how.get("region"):
                x0, y0, x1, y1 = (float(v) * k for v in how["region"])
                o["region"] = [x0, y0, x1, y1]
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("coord.new placement")
    doc.setdefault("coord", []).append(o)
    return o


def of_level(doc, lid) -> list:
    return [o for o in doc.get("coord") or [] if o["level"] == lid]


def find(doc, oid):
    return next((o for o in doc.get("coord") or [] if o["id"] == oid), None)


def remove(doc, oid) -> None:
    doc["coord"] = [o for o in doc.get("coord") or [] if o["id"] != oid]
    (doc.get("mep_runs") or {}).pop(oid, None)
    doc["clashes"] = [c for c in doc.get("clashes") or []
                      if oid not in (c.get("oa"), c.get("ob"))]


# ---- placing a drawing ---------------------------------------------------------
def _key(o):
    try:
        mt = os.path.getmtime(o["file"])
    except OSError:
        mt = 0
    return (o["file"], mt, str(o.get("unit")), str(o.get("region")),
            o.get("bx"), o.get("by"), o.get("dx"), o.get("dy"),
            o.get("drot"), tuple(sorted(o.get("off") or ())))


def placed(doc, o) -> dict:
    """The drawing's part on the floor, in metres (cadread.place's plan):
    ``model = R(rot + drot)·(p − ref)·k + insert + (dx, dy)``."""
    from . import cadread
    k_ = ("pl",) + _key(o) + (str((doc.get("imports") or {}).get(
        o["level"], {}).get("rot")),)
    if k_ in _cache:
        return _cache[k_]
    how = (doc.get("imports") or {}).get(o["level"]) or {}
    raw = cadread.read(o["file"], o.get("unit"))
    d = cadread.crop(raw, o.get("region"))
    if o.get("off"):
        d = cadread.without_layers(d, set(o["off"]))
    if o.get("bx") is None:
        base = cadread.base_point(d, "origin", (0.0, 0.0))
    else:
        base = (float(o["bx"]), float(o["by"]))
    ins = (float(how.get("ix", 0.0)) + float(o.get("dx") or 0.0),
           float(how.get("iy", 0.0)) + float(o.get("dy") or 0.0))
    rot = float(how.get("rot", 0.0)) + float(o.get("drot") or 0.0)
    pl = cadread.place(d, base, ins, rot)
    pl["_layers_all"] = list(raw.get("layers") or ())
    if len(_cache) > 16:
        _cache.clear()
    _cache[k_] = pl
    return pl


def is_own(disc, layer) -> bool:
    """A layer of the discipline itself (not the architect's background)."""
    pat = DISC[disc][2]
    if re.search(pat, str(layer), re.I):
        return True
    return False


def own_layers(o, pl) -> set:
    """The layers of the discipline's own lines: those named for it, else
    every layer that is not the architect's background."""
    lay = pl["layers"]
    own = {n for n in lay if is_own(o["disc"], n)
           and not (o["disc"] != "structure" and BACKGROUND.search(n)
                    and not re.search(DISC[o["disc"]][2], n, re.I))}
    if not own:
        own = {n for n in lay if not BACKGROUND.search(n)}
    return own


def heights(doc, lid) -> dict:
    """The floor's z0, its height and the underside of the slab over it."""
    from .engine import model as M
    from .engine import structure as S
    info = S.levels_info(doc["arch"], M.elevations)
    li = info.get(lid) or {"z0": 0.0, "height": 3.0, "under": 3.0}
    return li


def run_top(doc, o) -> float:
    """The top of the discipline's runs (absolute): its own height above
    the floor when set, else under the slab over the floor less its
    drop (structure: on the floor)."""
    li = heights(doc, o["level"])
    if o.get("z") is not None:
        return li["z0"] + float(o["z"])
    if o["disc"] == "structure":
        return li["z0"] + 0.02
    return li["under"] - DROP.get(o["disc"], 0.1)


def line_sets(doc, o):
    """[(own?, N×4 array)] of the drawing's lines on the floor: the
    discipline's own and the background — circles and arcs as short
    chords."""
    import numpy as np
    k_ = ("ls",) + _key(o)
    if k_ in _cache:
        return _cache[k_]
    pl = placed(doc, o)
    own = own_layers(o, pl)
    lay = pl["layers"]
    a, b = [], []
    for s in pl["segs"]:
        (a if lay[s[4]] in own else b).append(s[:4])
    for arc in pl.get("arcs") or ():
        (a if arc.get("layer") in own else b).extend(
            [(arc["p0"][0], arc["p0"][1], arc["pm"][0], arc["pm"][1]),
             (arc["pm"][0], arc["pm"][1], arc["p1"][0], arc["p1"][1])])
    for c in pl.get("circles") or ():
        cx, cy = c["c"][0], c["c"][1]
        r = float(c.get("r", 0.0))
        if r <= 0:
            continue
        n = 12 if r > 0.05 else 6
        pts = [(cx + r * math.cos(2 * math.pi * i / n),
                cy + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
        dst = a if c.get("layer") in own else b
        for i in range(n):
            dst.append((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]))
    out = [(True, np.array(a, dtype=float).reshape(-1, 4)),
           (False, np.array(b, dtype=float).reshape(-1, 4))]
    _cache[k_] = out
    return out


# ---- lining it up with the architecture ------------------------------------
def auto_align(doc, o) -> tuple:
    """(dx, dy, drot, score) moving the drawing onto the architectural
    floor: the turn that lines their lines' directions up (to 0.1°), then
    the move most of their line ends agree on (to 2 cm). Applied to ``o``
    (added to its dx / dy / drot) when the match is clear."""
    import numpy as np
    from . import furnish as FU
    try:
        pa = FU.cad_plan(doc, o["level"]) or {}
    except Exception:  # noqa: BLE001
        pa = {}
    if not pa.get("segs"):
        return (0.0, 0.0, 0.0, 0.0)
    pb = placed(doc, o)

    def ends_angles(pl, nmax=3000):
        segs = [s for s in pl["segs"]
                if math.hypot(s[2] - s[0], s[3] - s[1]) > 0.5]
        if len(segs) > nmax:
            step = len(segs) / nmax
            segs = [segs[int(i * step)] for i in range(nmax)]
        A = np.array([s[:4] for s in segs], dtype=float).reshape(-1, 4)
        L = np.hypot(A[:, 2] - A[:, 0], A[:, 3] - A[:, 1])
        ang = np.degrees(np.arctan2(A[:, 3] - A[:, 1], A[:, 2] - A[:, 0]))
        return A, L, ang % 90.0
    A, LA, aA = ends_angles(pa)
    B, LB, aB = ends_angles(pb)
    if not len(A) or not len(B):
        return (0.0, 0.0, 0.0, 0.0)

    def dominant(ang, w):
        h, e = np.histogram(ang, bins=900, range=(0, 90), weights=w)
        i = int(np.argmax(h))
        return (e[i] + e[i + 1]) / 2
    da = dominant(aA, LA) - dominant(aB, LB)
    if da > 45:
        da -= 90
    if da < -45:
        da += 90
    drot = round(da, 2) if abs(da) > 0.05 else 0.0
    # turn B's lines round the floor's insert point by drot
    how = (doc.get("imports") or {}).get(o["level"]) or {}
    cx = float(how.get("ix", 0.0)) + float(o.get("dx") or 0.0)
    cy = float(how.get("iy", 0.0)) + float(o.get("dy") or 0.0)
    c, s = math.cos(math.radians(drot)), math.sin(math.radians(drot))

    def turn(xy):
        x, y = xy[:, 0] - cx, xy[:, 1] - cy
        return np.stack([c * x - s * y + cx, s * x + c * y + cy], axis=1)
    PA = np.concatenate([A[:, :2], A[:, 2:]])
    PB = turn(np.concatenate([B[:, :2], B[:, 2:]]))
    rng = np.random.default_rng(7)
    ia = rng.choice(len(PA), min(500, len(PA)), replace=False)
    ib = rng.choice(len(PB), min(900, len(PB)), replace=False)
    D = (PA[ia][:, None, :] - PB[ib][None, :, :]).reshape(-1, 2)
    D = D[(np.abs(D[:, 0]) < 60) & (np.abs(D[:, 1]) < 60)]
    if not len(D):
        return (0.0, 0.0, drot, 0.0)
    H, xe, ye = np.histogram2d(D[:, 0], D[:, 1], bins=600,
                               range=[[-60, 60], [-60, 60]])
    i, j = np.unravel_index(int(np.argmax(H)), H.shape)
    gx, gy = (xe[i] + xe[i + 1]) / 2, (ye[j] + ye[j + 1]) / 2
    near = D[(np.abs(D[:, 0] - gx) < 0.2) & (np.abs(D[:, 1] - gy) < 0.2)]
    if len(near):
        gx, gy = float(np.median(near[:, 0])), float(np.median(near[:, 1]))
    score = float(H[i, j]) / max(1.0, float(len(ia)))
    # the check: line ends of the drawing landing on line ends of the
    # floor, after the move against before (a drawing with no background
    # of the architecture lines up with nothing: left where it is)
    try:
        from scipy.spatial import cKDTree as _KD
        kd = _KD(PA)
        before = float(np.mean(kd.query(PB, distance_upper_bound=0.05)[0]
                               < 0.05))
        after = float(np.mean(kd.query(PB + np.array([gx, gy]),
                                       distance_upper_bound=0.05)[0] < 0.05))
    except Exception:  # noqa: BLE001
        sub = PB[:400]
        dd = np.min(np.hypot(sub[:, None, 0] - PA[None, :2000, 0],
                             sub[:, None, 1] - PA[None, :2000, 1]), axis=1)
        before = float(np.mean(dd < 0.05))
        dd = np.min(np.hypot(sub[:, None, 0] + gx - PA[None, :2000, 0],
                             sub[:, None, 1] + gy - PA[None, :2000, 1]),
                    axis=1)
        after = float(np.mean(dd < 0.05))
    if after < 0.25 or after <= before + 0.05 or len(PB) < 12:
        return (gx, gy, drot, 0.0)            # no clear match: unchanged
    score = after
    o["dx"] = round(float(o.get("dx") or 0.0) + gx, 4)
    o["dy"] = round(float(o.get("dy") or 0.0) + gy, 4)
    o["drot"] = round(float(o.get("drot") or 0.0) + drot, 3)
    return (gx, gy, drot, score)


# ---- the runs ------------------------------------------------------------------
_NUM = r"(\d+(?:\.\d+)?)"
SIZE_RX = re.compile(_NUM + r"\s*(?:MM|\"|''|IN)?\s*[xX×*]\s*" + _NUM
                     + r"\s*(MM|\"|''|IN)?", re.I)
DIA_RX = re.compile(r"(?:Ø|ø|⌀|%%C|DIA\.?|D\s*=)\s*" + _NUM + r"\s*(MM|\"|IN)?|"
                    + _NUM + r"\s*(MM)\s*(?:Ø|ø|DIA|PIPE)?|"
                    r"(\d+(?:\s+\d)?(?:/\d+)?)\s*(\"|''|IN\b)", re.I)


def _metres(v, unit, ref=None):
    """A written size in metres: mm / inches as marked, else guessed (above
    60: mm; else inches)."""
    try:
        if isinstance(v, str) and "/" in v:
            parts = v.split()
            tot = 0.0
            for p_ in parts:
                if "/" in p_:
                    n_, d_ = p_.split("/")
                    tot += float(n_) / float(d_)
                else:
                    tot += float(p_)
            v = tot
        v = float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    u = str(unit or "").upper()
    if u == "MM":
        return v / 1000.0
    if u in ('"', "''", "IN"):
        return v * 0.0254
    return v / 1000.0 if v > 60 else v * 0.0254


def _texts_near(pl, x, y, r=2.0, seg=None):
    """The texts by a point — or by a run (``seg`` = (a, b): within ``r``
    of the line, anywhere along it) — nearest first."""
    out = []
    for t in pl.get("texts") or ():
        tx, ty = float(t["x"]), float(t["y"])
        if seg is not None:
            (ax, ay), (bx, by) = seg
            L2 = (bx - ax) ** 2 + (by - ay) ** 2
            u = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, (
                (tx - ax) * (bx - ax) + (ty - ay) * (by - ay)) / L2))
            d = math.hypot(tx - (ax + u * (bx - ax)), ty - (ay + u * (by - ay)))
        else:
            d = math.hypot(tx - x, ty - y)
        if d <= r:
            out.append((d, str(t.get("text", ""))))
    out.sort()
    return [s for _d, s in out]


def duct_size(pl, mid, width, seg=None):
    """(width, depth) of a duct / tray from the WxH written by it: the
    number nearest its drawn width is the width, the other its depth."""
    for txt in _texts_near(pl, mid[0], mid[1], 1.2 if seg else 2.5, seg):
        m = SIZE_RX.search(txt)
        if not m:
            continue
        u = m.group(3)
        a_ = _metres(m.group(1), u)
        b_ = _metres(m.group(2), u)
        if not a_ or not b_:
            continue
        if abs(a_ - width) <= abs(b_ - width):
            return a_, b_
        return b_, a_
    return None


def pipe_dia(pl, mid, seg=None):
    for txt in _texts_near(pl, mid[0], mid[1], 0.8 if seg else 1.8, seg):
        m = DIA_RX.search(txt)
        if not m:
            continue
        if m.group(1):
            v = _metres(m.group(1), m.group(2) or "MM")
        elif m.group(3):
            v = _metres(m.group(3), "MM")
        else:
            v = _metres(m.group(5), m.group(6))
        if v and 0.008 <= v <= 0.9:
            return v
    return None


def build_runs(doc, o) -> list:
    """The drawing's runs: ducts / trays from its pairs of lines (10 cm to
    2 m apart), pipes from its other single lines — [{kind, a, b, w, h,
    top}], absolute heights. Kept in ``doc["mep_runs"][o.id]``."""
    from shapely.geometry import LineString
    from shapely.ops import linemerge, unary_union

    from .engine import walldetect
    disc = o["disc"]
    if disc == "structure":
        return []
    pl = placed(doc, o)
    own = own_layers(o, pl)
    lay = pl["layers"]
    segs = [s for s in pl["segs"] if lay[s[4]] in own
            and math.hypot(s[2] - s[0], s[3] - s[1]) > 0.05]
    top = run_top(doc, o)
    runs = []
    paired = []
    if disc in ("hvac", "electrical", "elv"):
        try:
            prs, _ops = walldetect.walls_from(segs, 0.10, 2.0)
        except Exception:  # noqa: BLE001
            prs = []
        for a, b, t in prs:
            L = math.dist(a, b)
            if L < 0.4:
                continue
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            sz = duct_size(pl, mid, t, (a, b))
            tray = disc != "hvac"
            if sz:
                w_, h_ = sz
                if abs(w_ - t) > 0.35 * t:
                    w_ = t
            else:
                w_, h_ = t, (TRAY_H if tray else min(DUCT_H, max(0.15, t)))
            runs.append({"kind": "tray" if tray else "duct",
                         "a": [round(a[0], 4), round(a[1], 4)],
                         "b": [round(b[0], 4), round(b[1], 4)],
                         "w": round(w_, 3), "h": round(h_, 3),
                         "top": round(top, 4)})
            paired.append(LineString([a, b]).buffer(t / 2 + 0.05,
                                                    cap_style=2))
    if DISC[disc][3] == "pipe":
        PU = unary_union(paired) if paired else None
        lines = []
        for s in segs:
            ln = LineString([(s[0], s[1]), (s[2], s[3])])
            if PU is not None and PU.contains(ln):
                continue
            lines.append(ln)
        if lines:
            try:
                mg = linemerge(unary_union(lines))
            except Exception:  # noqa: BLE001
                mg = None
            for ch in getattr(mg, "geoms", [mg]) if mg is not None else []:
                if ch is None or ch.geom_type != "LineString" or \
                        ch.length < 0.3:
                    continue
                cs = list(ch.coords)
                for p0, p1 in zip(cs, cs[1:]):
                    if math.dist(p0, p1) < 0.05:
                        continue
                    dd = pipe_dia(pl, p0, (p0, p1))
                    d_ = dd or PIPE_D.get(disc, 0.05)
                    runs.append({"kind": "pipe",
                                 "a": [round(p0[0], 4), round(p0[1], 4)],
                                 "b": [round(p1[0], 4), round(p1[1], 4)],
                                 "w": round(d_, 3), "h": round(d_, 3),
                                 "top": round(top, 4)})
    if len(runs) > 6000:              # a drawing far too busy: its longest
        runs.sort(key=lambda r: -math.dist(r["a"], r["b"]))
        runs = runs[:6000]
    doc.setdefault("mep_runs", {})[o["id"]] = runs
    return runs


def _run_poly(r):
    from shapely.geometry import LineString
    return LineString([r["a"], r["b"]]).buffer(float(r["w"]) / 2,
                                               cap_style=2, join_style=2)


def _pipe_faces(r, sides=8):
    """An n-sided pipe along the run (its axis at top − Ø/2)."""
    a, b = r["a"], r["b"]
    L = math.dist(a, b)
    if L < 1e-4:
        return []
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])
    rad = float(r["w"]) / 2
    zc = float(r["top"]) - rad
    ring = [(math.cos(2 * math.pi * i / sides) * rad,
             math.sin(2 * math.pi * i / sides) * rad) for i in range(sides)]

    def P(end, q):
        return (end[0] + n[0] * q[0], end[1] + n[1] * q[0], zc + q[1])
    faces = []
    for i in range(sides):
        q0, q1 = ring[i], ring[(i + 1) % sides]
        faces.append({"loop": [P(a, q0), P(b, q0), P(b, q1), P(a, q1)],
                      "holes": []})
    faces.append({"loop": [P(a, q) for q in reversed(ring)], "holes": []})
    faces.append({"loop": [P(b, q) for q in ring], "holes": []})
    return faces


# ---- the clashes ------------------------------------------------------------------
def _structure_boxes(doc, lid):
    """[(label, kind, plan polygon, z0, z1)] of the floor's beams, columns,
    walls, slab over it."""
    from shapely.geometry import LineString, Polygon

    from .engine import structure as S
    from .engine import walls as W
    li = heights(doc, lid)
    z0, top, under = li["z0"], li["z0"] + li["height"], li["under"]
    out = []
    arch = doc["arch"]
    for e in arch["structure"]:
        if e.get("level") != lid:
            continue
        try:
            if e["type"] == "beam":
                h = float(e.get("h", 0.6) or 0.6)
                pg = LineString([e["a"], e["b"]]).buffer(
                    float(e.get("w", 0.23)) / 2, cap_style=2)
                out.append((e.get("name") or "Beam", "beam", pg,
                            under - h, under))
            elif e["type"] == "column":
                pg = Polygon(S.column_outline(e, 0.0)).buffer(0)
                out.append((e.get("name") or "Column", "column", pg,
                            z0, under))
        except Exception:  # noqa: BLE001
            continue
    try:
        pcs = W.plan([w for w in arch["walls"] if w["level"] == lid
                      and not w.get("rail") and W.why_not(w) is None])
        for wid, ps in pcs.items():
            w_ = next((w for w in arch["walls"] if w["id"] == wid), None)
            nm = (w_ or {}).get("name") or "Wall"
            for pc in ps:
                pg = Polygon(pc["outer"], pc["holes"]).buffer(0)
                out.append((nm, "wall", pg, z0, under))
    except Exception:  # noqa: BLE001
        pass
    # the slab over the floor: the next level's floor slab (its underside
    # at «under»)
    levels = arch["levels"]
    ids = [lv["id"] for lv in levels]
    if lid in ids and ids.index(lid) + 1 < len(ids):
        nxt = ids[ids.index(lid) + 1]
        for s in arch["structure"]:
            if s["type"] == "slab" and s["level"] == nxt and not (
                    s.get("zone") or s.get("grade")):
                try:
                    pg = Polygon(s["corners"], [h for h in s.get("holes")
                                                or [] if len(h) >= 3]
                                 ).buffer(0)
                except Exception:  # noqa: BLE001
                    continue
                out.append((s.get("name") or "Slab", "slab", pg, under,
                            top))
    return out


def check(doc, lids=None) -> list:
    """Every clash on the floors ``lids`` (all by default): each run
    against the structure and the walls, and against the other drawings'
    runs. ``doc["clashes"]`` set; the list returned."""
    from shapely.strtree import STRtree
    found = []
    levels = [lv["id"] for lv in doc["arch"]["levels"]]
    for lid in levels:
        if lids is not None and lid not in lids:
            continue
        runs = []                          # (o, run, polygon, z0, z1)
        for o in of_level(doc, lid):
            if not o.get("on", True):
                continue
            for r in (doc.get("mep_runs") or {}).get(o["id"]) or []:
                try:
                    pg = _run_poly(r)
                except Exception:  # noqa: BLE001
                    continue
                runs.append((o, r, pg, float(r["top"]) - float(r["h"]),
                             float(r["top"])))
        if not runs:
            continue
        sb = _structure_boxes(doc, lid)
        geoms = [b[2] for b in sb]
        tree = STRtree(geoms) if geoms else None
        for o, r, pg, z0, z1 in runs:
            if tree is None:
                break
            for i in tree.query(pg):
                lab, kind, g, b0, b1 = sb[int(i)]
                if min(z1, b1) - max(z0, b0) <= 0.005:
                    continue               # above / below it
                x = pg.intersection(g)
                if x.is_empty or x.area < 1e-4:
                    continue
                c = x.centroid
                hard = kind in ("beam", "column", "slab")
                found.append({"level": lid, "hard": hard,
                              "a": f"{DISC[o['disc']][0]} {r['kind']} "
                                   f"{_size(r)}",
                              "b": f"{kind} {lab}", "kind": kind,
                              "oa": o["id"], "ob": None,
                              "x": round(c.x, 3), "y": round(c.y, 3),
                              "z": round((max(z0, b0) + min(z1, b1)) / 2, 3),
                              "len": round(math.sqrt(x.area), 3)})
        # the drawings against each other
        rp = [t_[2] for t_ in runs]
        rt = STRtree(rp)
        for k, (o, r, pg, z0, z1) in enumerate(runs):
            for i in rt.query(pg):
                i = int(i)
                if i <= k:
                    continue
                o2, r2, pg2, y0, y1 = runs[i]
                if o2["id"] == o["id"]:
                    continue
                if min(z1, y1) - max(z0, y0) <= 0.005:
                    continue
                x = pg.intersection(pg2)
                if x.is_empty or x.area < 1e-4:
                    continue
                c = x.centroid
                found.append({"level": lid, "hard": True,
                              "a": f"{DISC[o['disc']][0]} {r['kind']} "
                                   f"{_size(r)}",
                              "b": f"{DISC[o2['disc']][0]} {r2['kind']} "
                                   f"{_size(r2)}",
                              "kind": "mep", "oa": o["id"], "ob": o2["id"],
                              "x": round(c.x, 3), "y": round(c.y, 3),
                              "z": round((max(z0, y0) + min(z1, y1)) / 2, 3),
                              "len": round(math.sqrt(x.area), 3)})
    # one per place: the same pair crossing at one spot (a run split in
    # pieces) once
    seen, out = set(), []
    found.sort(key=lambda c: not c["hard"])    # a beam over a wall: the beam
    for c in found:
        k_ = (c["level"], c["oa"], c["a"], round(c["x"] / 0.5),
              round(c["y"] / 0.5)) if not c["hard"] or c["kind"] in (
                  "beam", "column", "slab") else \
            (c["level"], c["a"], c["b"], round(c["x"] / 0.5),
             round(c["y"] / 0.5))
        if not c["hard"]:
            k_h = (c["level"], c["oa"], c["a"], round(c["x"] / 0.5),
                   round(c["y"] / 0.5))
            if k_h in seen:
                continue
        if k_ in seen:
            continue
        seen.add(k_)
        out.append(c)
    for i, c in enumerate(out, 1):
        c["no"] = i
    doc["clashes"] = [c for c in doc.get("clashes") or []
                      if lids is not None and c["level"] not in lids] + out
    return out


def _size(r):
    if r["kind"] == "pipe":
        return f"Ø{round(float(r['w']) * 1000)}"
    return f"{round(float(r['w']) * 1000)}×{round(float(r['h']) * 1000)}"


def write_csv(doc, path) -> int:
    import csv
    names = {lv["id"]: lv["name"] for lv in doc["arch"]["levels"]}
    rows = doc.get("clashes") or []
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["No", "Floor", "Type", "Element A", "Element B",
                    "X (m)", "Y (m)", "Z (m)", "Size (m)"])
        for c in rows:
            w.writerow([c.get("no"), names.get(c["level"], c["level"]),
                        "Hard" if c.get("hard") else "Soft (sleeve)",
                        c["a"], c["b"], c["x"], c["y"], c["z"], c["len"]])
    return len(rows)


# ---- the structural drawing into the model ------------------------------------------
def structure_to_model(doc, o, beam_h=None) -> tuple:
    """The floor's columns and beams read from the structural drawing in
    place of the architect's: (columns, beams)."""
    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    from .engine import walldetect
    pl = placed(doc, o)
    lay = pl["layers"]
    lid = o["level"]
    st = doc["settings"]
    how = (doc.get("imports") or {}).get(lid) or {}
    pats_c = [p.strip() for p in str(how.get("columns") or "").split(",")
              if p.strip()] + ["*COL*", "S-COL*", "*COLUMN*", "*PIER*"]
    pats_b = [p.strip() for p in str(how.get("beams") or "").split(",")
              if p.strip()] + ["*BEAM*", "S-BEAM*", "*BM*", "*GIRDER*"]
    cols = PJ.columns_from(pl, pats_c, lay)
    old = [e for e in doc["arch"]["structure"]
           if e["type"] == "column" and e["level"] == lid]
    keep = {k: old[0][k] for k in ("base", "height") if old and k in old[0]}
    seen, crecs = set(), []
    for c in cols:
        key = (round(c["x"], 2), round(c["y"], 2))
        if key in seen:
            continue
        seen.add(key)
        crecs.append(dict(c, type="column", level=lid, anchor="centre",
                          base=keep.get("base", 0.0),
                          height=keep.get("height", "level"), fit=False,
                          src="structure"))
    crecs = [r for r in crecs if S.why_not(r) is None]
    bsegs = [s for s in pl["segs"] if PJ._match(lay[s[4]], pats_b)]
    brecs = []
    if bsegs:
        try:
            bw, _bo = walldetect.walls_from(bsegs, 0.12, 1.2)
        except Exception:  # noqa: BLE001
            bw = []
        dh = float(beam_h or st.get("beam_h", 0.6096) or 0.6096)
        for a, b, t in bw:
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            sz = duct_size(pl, mid, t, (a, b))   # «B1 230×600», «9"×24"»
            h_ = max(sz) if sz and max(sz) > t * 1.2 else dh
            brecs.append({"type": "beam", "level": lid,
                          "a": [round(a[0], 4), round(a[1], 4)],
                          "b": [round(b[0], 4), round(b[1], 4)],
                          "w": round(t, 3), "h": round(h_, 3), "fit": False,
                          "src": "structure"})
    arch = doc["arch"]
    if crecs:
        arch["structure"] = [e for e in arch["structure"]
                             if not (e["type"] == "column"
                                     and e["level"] == lid)]
        arch["structure"] += M.new_elements(arch["structure"], crecs)
    if brecs:
        arch["structure"] = [e for e in arch["structure"]
                             if not (e["type"] == "beam"
                                     and e["level"] == lid)]
        arch["structure"] += M.new_elements(arch["structure"], brecs)
    return len(crecs), len(brecs)


# ---- the model's groups -------------------------------------------------------------
def groups(doc) -> list:
    """The runs (one group a drawing) and the clash marks (one a floor)."""
    from core.group import Group

    from . import project as PJ
    from .host import KEY, level_layer
    out = []
    names = {lv["id"]: lv["name"] for lv in doc["arch"]["levels"]}
    for o in doc.get("coord") or []:
        if not o.get("on", True) or not o.get("runs_on", True):
            continue
        runs = (doc.get("mep_runs") or {}).get(o["id"]) or []
        if not runs:
            continue
        faces = []
        for r in runs:
            try:
                if r["kind"] == "pipe":
                    faces += _pipe_faces(r)
                else:
                    faces += PJ._prism(_run_poly(r), float(r["top"]) -
                                       float(r["h"]), float(r["top"]), 0.0005)
            except Exception:  # noqa: BLE001
                continue
        if not faces:
            continue
        lab = DISC[o["disc"]][0]
        g = Group(PJ._mesh_of(faces),
                  name=f"{lab} · {o.get('name', '')} · "
                       f"{names.get(o['level'], '')}")
        g.component = False
        g.material = {"color": tuple(v / 255.0 for v in DISC[o["disc"]][1]),
                      "opacity": 1.0}
        g.layer = level_layer(names.get(o["level"], ""))
        g.ifc = {"class": "IfcDuctSegment" if o["disc"] == "hvac" else
                 "IfcCableCarrierSegment" if o["disc"] in
                 ("electrical", "elv") else "IfcPipeSegment",
                 "name": lab}
        g.ext = {KEY: {"type": "mep", "id": o["id"], "level": o["level"]}}
        out.append(g)
    by_lv = {}
    for c in doc.get("clashes") or []:
        by_lv.setdefault(c["level"], []).append(c)
    for lid, cs in by_lv.items():
        faces = []
        from shapely.geometry import box
        for c in cs:
            r = 0.15
            faces += PJ._prism(box(c["x"] - r, c["y"] - r, c["x"] + r,
                                   c["y"] + r), c["z"] - r, c["z"] + r,
                               0.0001)
        if not faces:
            continue
        g = Group(PJ._mesh_of(faces),
                  name=f"Clashes ({len(cs)}) · {names.get(lid, '')}")
        g.component = False
        g.material = {"color": (1.0, 0.0, 0.25), "opacity": 0.85}
        g.layer = level_layer(names.get(lid, ""))
        g.ifc = {"class": "IfcAnnotation", "name": "Clash"}
        g.ext = {KEY: {"type": "clash", "id": f"clash-{lid}", "level": lid}}
        out.append(g)
    return out


# ---- the lines, drawn over the views ----------------------------------------------
def draw(viewport, painter) -> None:
    """Every shown drawing's lines: in a floor's plan view those of that
    floor, at its floor; in 3D all of them, each at its discipline's
    height — the discipline's own lines in its colour, the background
    faint."""
    from .host import KEY, PREFIX_PLAN_CUT
    scene = viewport.scene
    raw = (getattr(scene, "plugin_data", {}) or {}).get(KEY)
    if not raw or not raw.get("coord"):
        return
    from . import project as PJ
    global _doc_memo
    if _doc_memo is not None and _doc_memo[0] is raw:
        doc = _doc_memo[1]
    else:
        doc = PJ.load(raw)
        _doc_memo = (raw, doc)
    if not doc["settings"].get("coord_lines", True):
        return
    sp = scene.active_section() if hasattr(scene, "active_section") else None
    name = str(getattr(sp, "name", "") or "")
    plan_lv = None
    if name.startswith(PREFIX_PLAN_CUT):
        nm = name[len(PREFIX_PLAN_CUT):]
        plan_lv = next((lv["id"] for lv in doc["arch"]["levels"]
                        if lv["name"] == nm), None)
        if plan_lv is None:
            return
    elif not doc["settings"].get("coord_3d", True):
        return
    import numpy as np
    from PySide6.QtCore import QLineF, Qt
    from PySide6.QtGui import QColor, QPen
    W_, H_ = viewport.width(), viewport.height()
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    for o in doc.get("coord") or []:
        if not o.get("on", True):
            continue
        if plan_lv is not None and o["level"] != plan_lv:
            continue
        try:
            sets = line_sets(doc, o)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("coord.line_sets")
            continue
        if plan_lv is not None:
            z = heights(doc, o["level"])["z0"] + 0.05
        else:
            z = run_top(doc, o)
        col = DISC[o["disc"]][1]
        for own, arr in sets:
            if not len(arr):
                continue
            if not own and plan_lv is None:
                continue                 # in 3D: the discipline alone
            n = len(arr)
            P = np.empty((2 * n, 3))
            P[0::2, 0], P[0::2, 1] = arr[:, 0], arr[:, 1]
            P[1::2, 0], P[1::2, 1] = arr[:, 2], arr[:, 3]
            P[:, 2] = z
            X, Y, OK = viewport._project_px(P)
            X, Y, OK = X.reshape(-1, 2), Y.reshape(-1, 2), OK.reshape(-1, 2)
            vis = OK.all(axis=1) & ~(((X < 0).all(axis=1)) |
                                     ((X > W_).all(axis=1)) |
                                     ((Y < 0).all(axis=1)) |
                                     ((Y > H_).all(axis=1)))
            if not vis.any():
                continue
            qc = QColor(*col) if own else QColor(160, 160, 170, 110)
            pen = QPen(qc, 1.6 if own else 0.8)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            Xv, Yv = X[vis], Y[vis]
            painter.drawLines([QLineF(float(a), float(b), float(c_),
                                      float(d))
                               for a, b, c_, d in zip(Xv[:, 0], Yv[:, 0],
                                                      Xv[:, 1], Yv[:, 1])])
    painter.restore()
