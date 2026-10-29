# SPDX-License-Identifier: GPL-3.0-or-later
# From ArchXQ IT Lite (c) Orlando Souza / XQ, GPL-3.0-or-later
# https://github.com/equipexq/archxq-it-lite  — used unchanged by CAD2IngeTrazo.
"""ArchXQ structure — the ENGINE. Pure: no IngeTrazo, no Qt.

Columns, beams, slabs and footings, and how they sit with the walls,
level by level. ``build(doc, union)`` gives every element of the
building (walls too) with its faces, at its true heights:

- a level's SLAB has its top at the level's floor (+ its offset); the
  walls, columns and beams of the level BELOW stop at its underside —
  nothing passes through a slab;
- COLUMNS and BEAMS are 1 mm smaller on every face: inside a wall of the
  same width they hide (no two faces in one plane, nothing flickers);
  wider, they read as pilasters / downstand beams;
- a FOOTING hangs under its level's slab (its top at the slab's
  underside, or at the floor without a slab).

Records (``doc["structure"]``): {"id", "name", "type", "level", …}
    column  x, y, shape "rect"|"round", w, d (rect; round: w = Ø),
            angle (°), anchor "centre"|"corner", height "level"|m
    beam    a, b, w (width), h (height)
    slab    corners [[x, y]…], t, offset
    footing kind "pad": x, y, w, d (depth), angle
            kind "strip": a, b (or an arc's "m"), w, d
            kind "raft" | "combined": corners (+ holes), d
    roof    kind "gable"|"hip"|"flat", corners, slope, overhang, t,
            ridge "long"|"short", parapet, pt — on its level's wall tops
"""
from __future__ import annotations

import math

from . import walls as W

SHRINK = 0.001          # m off every face of columns and beams
#: …and of the ones FITTED inside a wall: the host draws edges with a
#: small depth offset, and 1 mm behind a wall's face their lines showed
#: through it (seen on the demo, 2026-10-03) — 1 cm hides them, and a
#: hidden structure 2 cm slimmer is never seen
FIT_SHRINK = 0.01
ROUND_SEGS = 24         # a round column's sides
TYPES = ("column", "beam", "slab", "footing", "roof", "core")
LABEL = {"column": "Column", "beam": "Beam", "slab": "Slab",
         "footing": "Footing", "wall": "Wall", "roof": "Roof",
         "core": "Lift core"}


# ---- levels ------------------------------------------------------------------------
def PLASTER(doc) -> float:
    """The plaster on each face of the walls (m), 0 = none."""
    try:                        # ½" both faces unless set (0 = none)
        return max(float(doc.get("_plaster", 0.0127) or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _down(doc, w, li) -> float:
    """How far a wall standing on its floor reaches down — to the bottom
    of the floor slab under it (slabs as floors: the slab between the
    walls, the walls down over its edge, so the outer face runs on in one
    plane). 0 otherwise, or for a wall set on its own base / a railing."""
    if not doc.get("_walls_down"):
        return 0.0
    if w.get("rail") or abs(float(w.get("base", 0.0) or 0.0)) > 1e-6:
        return 0.0
    gd = float(doc.get("_ground_down", 0.0) or 0.0)
    if gd > 0 and li.get("ground"):       # on the ground: down to the
        return gd                         # outside finish's level
    return max(float(li.get("slab", 0.0) or 0.0), 0.0)


def _plastered(w, p):
    """The wall as built with its plaster: a coat ``p`` thick on both
    faces (its centre line kept) and, standing up to the slab over it, on
    up to the slab's top — the slab's edge in the plaster, as built (no
    slab line on the elevations)."""
    if p <= 0 or w.get("rail") or w.get("type") == "curtain":
        return w
    # the plaster is IN the wall's total thickness (as drawn): the wall
    # keeps its width; the coats are its outer ``p`` on each face
    out = dict(w, _pl=True)
    if w.get("kind", "line") == "line" and w.get("align", "centre") != \
            "centre":
        c = W.centre(w)
        out.update(a=[c.p0[0], c.p0[1]], b=[c.p1[0], c.p1[1]],
                   align="centre")
    elif w.get("kind", "line") != "line" and w.get("align", "centre") != \
            "centre":
        out = dict(w, _pl=True)          # an off-centre arc: as drawn
    return out


def _plaster_skin(w, pieces, p, z_a, z_b) -> list:
    """The plaster coats of a (plastered) wall carried on from its top
    ``z_a`` up to ``z_b`` (over the slab's edge): a ``p`` thick skin on
    each face, flush with the wall's plastered faces."""
    seg = W.centre(w)
    p0, u = seg.p0, seg.u
    n = (-u[1], u[0])
    T2 = float(w["t"]) / 2
    out = []
    for sg in (1.0, -1.0):
        # this face's own ends (a mitred corner makes the two faces differ)
        # — the skin's edges on the wall face's, the seam drawn smooth
        ss = []
        for pc in pieces or []:
            for q in pc["outer"]:
                c = (q[0] - p0[0]) * n[0] + (q[1] - p0[1]) * n[1]
                if abs(c - sg * T2) < 1e-4:
                    ss.append((q[0] - p0[0]) * u[0] + (q[1] - p0[1]) * u[1])
        if len(ss) < 2:
            ss = [0.0, seg.L]
        s0, s1 = min(ss), max(ss)
        if s1 - s0 < 0.01:
            continue
        ca, cb = (T2 - p, T2) if sg > 0 else (-T2, -T2 + p)
        out += _box(p0, u, n, s0, s1, ca, cb, z_a, z_b, None)
    return out


def _shp_pieces(g) -> list:
    """Shapely (multi)polygon -> solid pieces (outer ccw, holes cw)."""
    out = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type != "Polygon" or q.is_empty or q.area < 1e-6:
            continue
        out.append({"outer": _ccw(list(q.exterior.coords)[:-1]),
                    "holes": [list(reversed(_ccw(list(r.coords)[:-1])))
                              for r in q.interiors]})
    return out


def _slab_plaster(s, parts, p):
    """The slab with its edges plastered all round — its outline AND its
    openings (stair wells, shafts): the concrete core inset ``p`` and a
    ``p`` plaster band in its place, flush with the wall faces under it,
    so no slab line shows on any elevation.  -> (core pieces, band
    pieces)."""
    from shapely.geometry import Polygon
    sp = Polygon([tuple(q) for q in s["corners"]],
                 [[tuple(q) for q in h] for h in s.get("holes") or []
                  if len(h) >= 3])
    if not sp.is_valid:
        sp = sp.buffer(0)
    core = sp.buffer(-p, join_style=2)
    if core.is_empty:
        return parts, []
    band = sp.difference(core)
    new = []
    for pc in parts:
        try:
            P = Polygon(pc["outer"], pc.get("holes") or [])
            if not P.is_valid:
                P = P.buffer(0)
            new += _shp_pieces(P.intersection(core))
        except Exception:  # noqa: BLE001
            new.append(pc)
    return new or parts, _shp_pieces(band)


PLASTER_COLOR = (0.88, 0.86, 0.82, 1.0)     # plastered and painted


def _newell(loop):
    nx = ny = nz = 0.0
    n = len(loop)
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return nx, ny, nz


def _facing(loop, want):
    """``loop`` wound so its normal points along ``want``."""
    nn = _newell(loop)
    if nn[0] * want[0] + nn[1] * want[1] + nn[2] * want[2] < 0:
        return list(reversed(loop))
    return list(loop)


def round_infill(w, seg, o, z0, n=32) -> list:
    """A round opening: the wall filled back between its square cut and
    the circle (both faces), and the circle's reveal through the wall."""
    T2 = float(w["t"]) / 2
    u = seg.u
    nv = (-u[1], u[0])
    sc = float(o["pos"])
    hw, hh = float(o["w"]) / 2, float(o["h"]) / 2
    zc = z0 + float(o.get("sill", 0.0)) + hh
    r = max(min(hw, hh) - 0.002, 0.02)

    def P(s_, z, c):
        return (seg.p0[0] + u[0] * s_ + nv[0] * c,
                seg.p0[1] + u[1] * s_ + nv[1] * c, z)
    out = []
    for side in (1.0, -1.0):
        c = side * T2
        want = (nv[0] * side, nv[1] * side, 0.0)
        rect = [P(sc - hw, zc - hh, c), P(sc + hw, zc - hh, c),
                P(sc + hw, zc + hh, c), P(sc - hw, zc + hh, c)]
        circ = [P(sc + r * math.cos(2 * math.pi * k / n),
                  zc + r * math.sin(2 * math.pi * k / n), c)
                for k in range(n)]
        outer = _facing(rect, want)
        hole = list(reversed(_facing(circ, want)))
        out.append({"loop": outer, "holes": [hole], "color": None})
    for k in range(n):                       # the reveal, facing the hole
        a0 = 2 * math.pi * k / n
        a1 = 2 * math.pi * (k + 1) / n
        q = [P(sc + r * math.cos(a0), zc + r * math.sin(a0), T2),
             P(sc + r * math.cos(a1), zc + r * math.sin(a1), T2),
             P(sc + r * math.cos(a1), zc + r * math.sin(a1), -T2),
             P(sc + r * math.cos(a0), zc + r * math.sin(a0), -T2)]
        am = (a0 + a1) / 2
        want = (-u[0] * math.cos(am), -u[1] * math.cos(am),
                -math.sin(am))
        out.append({"loop": _facing(q, want), "holes": [], "color": None})
    return out


def levels_info(doc: dict, elevations) -> dict:
    """Per level id: z0 (floor), height, the slab thickness ON it, and
    ``under`` = where things of this level stop (the next level's slab
    underside; the level's top without one)."""
    levels = doc["levels"]
    ground = doc["project"]["ground_level"] if doc.get("project") else 0.0
    elev = elevations(levels, ground)
    slab_t, roof_t, main_a = {}, {}, {}
    off_next = next_floor_offsets(doc)
    for s in doc.get("structure") or []:
        if s["type"] != "slab" or s.get("skip") or s.get("user") \
                or s.get("zone") or s.get("grade"):
            continue
        if s.get("top"):        # the slab over the floor: on its walls
            roof_t[s["level"]] = max(roof_t.get(s["level"], 0.0),
                                     float(s["t"])
                                     - off_next.get(s["level"], 0.0))
            continue
        if s.get("roof"):
            roof_t[s["level"]] = max(roof_t.get(s["level"], 0.0),
                                     float(s["t"]) - float(s.get("offset", 0)))
            continue
        # the floor's depth: its MAIN slab's (the largest) — a small piece
        # sunk / raised (a toilet, a drawn slab) does not set the depth the
        # walls of the floor below stop at, or this floor's walls reach to
        a_ = _area(s.get("corners") or [])
        if a_ > main_a.get(s["level"], -1.0):
            main_a[s["level"]] = a_
            slab_t[s["level"]] = float(s["t"]) - float(s.get("offset", 0))
    out = {}
    for i, lv in enumerate(levels):
        top = elev[i] + float(lv["height"])
        above = levels[i + 1]["id"] if i + 1 < len(levels) else None
        below_top = slab_t.get(above, 0.0) if above else 0.0
        out[lv["id"]] = {"z0": elev[i], "height": float(lv["height"]),
                         "ground": lv.get("kind") == "ground",
                         "slab": slab_t.get(lv["id"], 0.0),
                         "under": top - max(below_top,
                                            roof_t.get(lv["id"], 0.0))}
    return out


def main_slab_offset(doc: dict, lid) -> float:
    """The level's open floor against its floor level (its main slab's
    offset) — 0 without one."""
    best = None
    for s in doc.get("structure") or []:
        if s["type"] == "slab" and s["level"] == lid and not (
                s.get("zone") or s.get("user") or s.get("roof")
                or s.get("grade")):
            a_ = _area(s.get("corners") or [])
            if best is None or a_ > best[0]:
                best = (a_, float(s.get("offset", 0.0) or 0.0))
    return best[1] if best else 0.0


def next_floor_offsets(doc: dict) -> dict:
    """Per level id: the open-floor offset of the floor ABOVE it — where
    a slab over the level (``top``) stands: under the next floor."""
    levels = doc["levels"]
    out = {}
    for i, lv in enumerate(levels):
        out[lv["id"]] = main_slab_offset(doc, levels[i + 1]["id"]) \
            if i + 1 < len(levels) else 0.0
    return out


def floor_parts(doc: dict, lid) -> list:
    """The level's floor pieces at their own heights: CAD level zones and
    the parts sunk / raised by hand."""
    return [s for s in doc.get("structure") or []
            if s["type"] == "slab" and s["level"] == lid
            and (s.get("zone") or s.get("user")) and not s.get("skip")]


def _minus(s, cuts) -> list:
    """The slab ``s`` without the outlines ``cuts``: plan pieces
    ({"outer", "holes"}), or [] when shapely cannot."""
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
    except ImportError:
        return []
    try:
        g = Polygon(s["corners"], [h for h in s.get("holes") or []
                                   if len(h) >= 3]).buffer(0)
        g = g.difference(unary_union([Polygon(c["corners"]).buffer(0)
                                      for c in cuts]))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for p in getattr(g, "geoms", [g]):
        if p.geom_type != "Polygon" or p.area < 0.01:
            continue
        out.append({"outer": _ccw([tuple(q) for q in
                                   list(p.exterior.coords)[:-1]]),
                    "holes": [list(reversed(_ccw([tuple(q) for q in
                                                  list(h.coords)[:-1]])))
                              for h in p.interiors]})
    return out


# ---- plans ---------------------------------------------------------------------------
def _rot(p, c, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * ca - y * sa, c[1] + x * sa + y * ca)


def column_outline(c: dict, shrink: float = SHRINK) -> list:
    """The column's section in plan, counter-clockwise."""
    x, y = float(c["x"]), float(c["y"])
    w = float(c["w"]) - 2 * shrink
    if c.get("shape") == "poly" and c.get("pts"):
        # an L / T / C section (a shear wall turning a corner, a core
        # wall drawn as a column): its own corners from (x, y), turned
        ang = math.radians(float(c.get("angle", 0.0)))
        pts = [(x + p[0], y + p[1]) for p in c["pts"]]
        if shrink:
            try:
                from shapely.geometry import Polygon
                g = Polygon(pts).buffer(-shrink, join_style=2)
                if g.geom_type == "Polygon" and not g.is_empty:
                    pts = list(g.exterior.coords)[:-1]
            except Exception:  # noqa: BLE001
                pass
        out = [_rot(p, (x, y), ang) for p in pts]
        return out if _area(out) > 0 else list(reversed(out))
    if c.get("shape") == "round":
        r = w / 2.0
        return [(x + r * math.cos(2 * math.pi * k / ROUND_SEGS),
                 y + r * math.sin(2 * math.pi * k / ROUND_SEGS))
                for k in range(ROUND_SEGS)]
    d = float(c["d"]) - 2 * shrink
    ang = math.radians(float(c.get("angle", 0.0)))
    # (x, y) is the column's insertion point: its centre, a corner or a
    # side's middle (``anchor``) — the section's middle sits off it
    ax, ay = ANCHORS.get(c.get("anchor", "centre"), (0, 0))
    W, D = float(c["w"]), float(c["d"])
    mx, my = x - ax * W / 2, y - ay * D / 2
    pts = [(mx - w / 2, my - d / 2), (mx + w / 2, my - d / 2),
           (mx + w / 2, my + d / 2), (mx - w / 2, my + d / 2)]
    return [_rot(p, (x, y), ang) for p in pts]


#: the insertion points of a rectangular column: (−1|0|1 across, along)
#: — «corner» (older files) is the lower left one
ANCHORS = {"centre": (0, 0), "sw": (-1, -1), "corner": (-1, -1),
           "s": (0, -1), "se": (1, -1), "e": (1, 0), "ne": (1, 1),
           "n": (0, 1), "nw": (-1, 1), "w": (-1, 0)}


def column_centre(c: dict):
    """Where the column's axis is (off-centre insertion: the section's
    middle)."""
    if c.get("anchor", "centre") == "centre" or c.get("shape") == "round":
        return (float(c["x"]), float(c["y"]))
    pts = column_outline(c, 0.0)
    return (sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4)


def pad_outline(f: dict) -> list:
    x, y, w = float(f["x"]), float(f["y"]), float(f["w"])
    ang = math.radians(float(f.get("angle", 0.0)))
    pts = [(x - w / 2, y - w / 2), (x + w / 2, y - w / 2),
           (x + w / 2, y + w / 2), (x - w / 2, y + w / 2)]
    return [_rot(p, (x, y), ang) for p in pts]


def _ccw(loop):
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(loop, loop[1:] + loop[:1]))
    return list(loop) if a >= 0 else list(reversed(loop))


def as_wall(e: dict, width_key: str = "w", shrink: float = SHRINK) -> dict:
    """A beam or a strip footing, as a centre-aligned «wall» — the walls
    engine joins them (L, T, X) exactly as it joins walls."""
    rec = {"id": e["id"], "name": e.get("name", ""),
           "kind": "arc" if e.get("m") else "line",
           "a": list(e["a"]), "b": list(e["b"]),
           "t": float(e[width_key]) - 2 * shrink, "align": "centre",
           "side": 1}
    if e.get("m"):
        rec["m"] = list(e["m"])
    return rec


def why_not(e: dict) -> str | None:
    """Why an element can't be built (None = it can)."""
    t = e.get("type")
    try:
        if t == "column":
            if float(e["w"]) < 0.05 or (e.get("shape") != "round"
                                        and float(e["d"]) < 0.05):
                return "A column needs a section of 5 cm at least"
        elif t == "beam":
            if float(e["w"]) < 0.05 or float(e["h"]) < 0.05:
                return "A beam needs a width and a height"
            if math.dist(e["a"], e["b"]) < max(float(e["w"]), 0.1):
                return "Too short for a beam"
        elif t == "slab":
            if len(e["corners"]) < 3 or float(e["t"]) < 0.02:
                return "A slab needs three corners and a thickness"
            if abs(_area(e["corners"])) < 0.05:
                return "Too small for a slab"
        elif t == "footing":
            if e.get("kind") in ("raft", "combined"):
                if len(e.get("corners") or []) < 3 or \
                        abs(_area(e["corners"])) < 0.2:
                    return "Too small for a raft / combined footing"
                if float(e["d"]) < 0.05:
                    return "A footing needs a depth"
                return None
            if float(e["w"]) < 0.1 or float(e["d"]) < 0.05:
                return "A footing needs a width and a depth"
            if e.get("kind") == "strip" and math.dist(e["a"], e["b"]) < 0.1:
                return "Too short for a footing"
        elif t == "core":
            if len(e["corners"]) < 3 or abs(_area(e["corners"])) < 0.02:
                return "Too small for a lift core"
        elif t == "roof":
            if len(e["corners"]) < 3 or abs(_area(e["corners"])) < 1.0:
                return "Too small for a roof"
            if e.get("kind") in ("gable", "hip") and not \
                    5.0 <= float(e["slope"]) <= 75.0:
                return "A pitched roof needs a slope of 5° to 75°"
        else:
            return "Unknown element"
    except (KeyError, TypeError, ValueError):
        return "Incomplete element"
    return None


def _area(pts) -> float:
    return 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                     for p, q in zip(pts, list(pts[1:]) + [pts[0]]))


# ---- structure INSIDE the walls (the usual case — his rule, 2026-10-03) ---------------
FIT_TOL = 0.02          # m past a wall's face that still counts as on it


def _walls_at(p, walls: list[dict]) -> list[tuple]:
    """[(wall, centre seg, fraction)] of the walls whose body holds p."""
    out = []
    for w in walls:
        if W.why_not(w) is not None:
            continue
        s = W.centre(w)
        f, off = s.project(p)
        if (W.is_closed(w) or -1e-6 <= f <= 1 + 1e-6) \
                and abs(off) <= float(w["t"]) / 2 + FIT_TOL:
            out.append((w, s, f % 1.0 if W.is_closed(w) else f))
    return out


def fit_column(c: dict, walls: list[dict]) -> dict:
    """A column standing on a wall goes INSIDE it: as thick as the wall,
    turned with it, on its centre line (its length along the wall kept).
    Where walls meet (a corner, a T): a square as thick as the thinnest.
    Off the walls: as it was drawn."""
    p = column_centre(c)
    here = _walls_at(p, walls)
    if not here:
        return dict(c, fit=False)
    # from here on its insertion point is its middle (an off-centre one —
    # a corner — moved there: it kept the corner's place before)
    c = dict(c, anchor="centre", fit=True, x=round(p[0], 4),
             y=round(p[1], 4))
    dirs = []
    for w, s, f in here:
        u = s.tangent(f)
        if not any(abs(u[0] * v[1] - u[1] * v[0]) < 0.05 for v in dirs):
            dirs.append(u)
    t = min(float(w["t"]) for w, _s, _f in here)
    w0, s0, f0 = here[0]
    if len(dirs) >= 2:                          # walls meeting: a square
        c.update(w=t, d=t)
    else:                                       # on one wall: in its line
        q = s0.at(min(max(f0, 0.0), 1.0))
        c.update(x=round(q[0], 4), y=round(q[1], 4),
                 w=max(float(c["w"]), float(c.get("d", c["w"]))), d=t)
        if c.get("shape") == "round":
            c.update(w=t, d=t)
    u = s0.tangent(f0)
    c["angle"] = round(math.degrees(math.atan2(u[1], u[0])), 3)
    if c.get("shape") == "round":
        c["w"] = c["d"] = t
    return c


def fit_beam(b: dict, walls: list[dict]) -> dict:
    """A beam on the line of a wall (along all of it, or running past it
    into the next room) takes the wall's thickness — where the wall is,
    it hides in it; past it, it reads as a downstand beam of the same
    width."""
    ax, ay = b["a"]
    bx, by = b["b"]
    L = math.hypot(bx - ax, by - ay)
    if L < 1e-9:
        return dict(b, fit=False)
    u = ((bx - ax) / L, (by - ay) / L)
    best = None
    for w in walls:
        if W.why_not(w) is not None or w.get("kind", "line") != "line":
            continue
        s = W.centre(w)
        if abs(u[0] * s.u[1] - u[1] * s.u[0]) > 0.01:
            continue                             # not the same way
        f0, off0 = s.project(b["a"])
        f1, off1 = s.project(b["b"])
        tol = float(w["t"]) / 2 + FIT_TOL
        if abs(off0) > tol or abs(off1) > tol:
            continue                             # not on its line
        if max(f0, f1) < 0.0 or min(f0, f1) > 1.0:
            continue                             # beside it, not along it
        t = float(w["t"])
        best = t if best is None else min(best, t)
    if best is None:
        return dict(b, fit=False)
    return dict(b, w=best, fit=True)


# ---- derived from the walls ----------------------------------------------------------
def wall_corners(walls: list[dict]) -> list:
    """Where the level's walls MEET (corners, T, X) — on their centre
    lines, so a column there sits in the middle of the walls (an outside-
    aligned wall's drawn corner is its outer corner: a column there would
    hang half out)."""
    good = [w for w in walls if W.why_not(w) is None and not W.is_closed(w)]
    centres = [W.centre(w) for w in good]
    ends = []                                  # (drawn point, wall index)
    for i, w in enumerate(good):
        d = W.drawn(w)
        ends += [(d.at(0.0), i), (d.at(1.0), i)]
    groups: list = []
    for p, i in ends:
        for g in groups:
            if math.dist(g[0], p) <= W.JOIN_TOL:
                g[1].add(i)
                break
        else:
            groups.append([p, {i}])
    # an end on another wall's body is a corner too (a T)
    for g in groups:
        if len(g[1]) == 1:
            for j, s in enumerate(centres):
                if j in g[1]:
                    continue
                f, off = s.project(g[0])
                if 0.0 < f < 1.0 and abs(off) <= good[j]["t"] / 2 + W.BODY_TOL:
                    g[1].add(j)
    out = []
    for p, ids in groups:
        if len(ids) < 2:
            continue
        ids = sorted(ids)
        pt = None
        for a in ids:
            for b in ids:
                if b <= a or centres[a].kind != "line" \
                        or centres[b].kind != "line":
                    continue
                got = W._meet(("line", centres[a].p0, centres[a].u),
                              ("line", centres[b].p0, centres[b].u))
                if got and math.dist(got[0], p) <= max(
                        good[a]["t"], good[b]["t"]) + W.JOIN_TOL:
                    pt = got[0]
                    break
            if pt:
                break
        out.append(tuple(pt) if pt else tuple(p))
    return out


def inside_walls(walls: list[dict], union) -> list | None:
    """A slab's outline from the level's walls: the outer contour of all
    of them together (``union(polygons) → outer loop`` is the host's
    shapely, handed in). None without walls."""
    plans = W.plan([w for w in walls if W.why_not(w) is None])
    polys = [pc for pieces in plans.values() for pc in pieces]
    if not polys:
        return None
    loop = union(polys)
    if not loop or len(loop) < 3:
        return None
    return [[round(p[0], 4), round(p[1], 4)] for p in _ccw(loop)]


def along_walls(walls: list[dict]) -> list[tuple]:
    """Beams over the level's straight walls: on each wall's centre line,
    end to end (curved / round walls are left out)."""
    out = []
    for w in walls:
        if W.why_not(w) is not None or w.get("kind", "line") != "line":
            continue
        s = W.centre(w)
        out.append(([round(s.p0[0], 4), round(s.p0[1], 4)],
                    [round(s.p1[0], 4), round(s.p1[1], 4)]))
    return out


def strips_under(walls: list[dict]) -> list[dict]:
    """Strip footings under the walls: on each wall's centre line (a
    curved wall's too)."""
    out = []
    for w in walls:
        if W.why_not(w) is not None or W.is_closed(w):
            continue
        s = W.centre(w)
        rec = {"a": [round(s.at(0.0)[0], 4), round(s.at(0.0)[1], 4)],
               "b": [round(s.at(1.0)[0], 4), round(s.at(1.0)[1], 4)]}
        if s.kind == "arc":
            m = s.at(0.5)
            rec["m"] = [round(m[0], 4), round(m[1], 4)]
        out.append(rec)
    return out


# ---- openings: doors, windows, voids in the walls -----------------------------------
#: an opening: {"id", "name", "kind": "door" | "window" | "void",
#:   "wall": wall id, "pos": its centre along the wall's line (m from the
#:   wall's start), "w", "h", "sill" (from the level's floor),
#:   "swing": "left" | "right" (a door's hinge, seen from inside)}
OPENING_LABEL = {"door": "Door", "window": "Window", "void": "Opening"}
FRAME = 0.05            # m, a frame's face width
FRAME_DEPTH = 0.07      # m, a frame's depth through the wall
LEAF = 0.04             # m, a door leaf
FRAME_COLOR = (0.94, 0.94, 0.92, 1.0)
GLASS_COLOR = (0.62, 0.80, 0.90, 0.35)
#: glass types: key → (label, rgba) — windows, glazed doors, curtain walls
GLASS_TYPES = [
    ("clear", "Clear float", GLASS_COLOR),
    ("double", "Double glazed (clear)", (0.60, 0.78, 0.86, 0.45)),
    ("lowe", "Low-E (neutral)", (0.56, 0.74, 0.78, 0.42)),
    ("grey", "Tinted grey", (0.33, 0.37, 0.40, 0.58)),
    ("bronze", "Tinted bronze", (0.52, 0.40, 0.28, 0.58)),
    ("green", "Tinted green", (0.42, 0.62, 0.52, 0.52)),
    ("blue_ref", "Reflective blue", (0.28, 0.45, 0.62, 0.78)),
    ("silver_ref", "Reflective silver (mirror)", (0.74, 0.77, 0.80, 0.86)),
    ("frosted", "Frosted / obscure (toilets)", (0.88, 0.90, 0.92, 0.82)),
]
GLASS_BY = {k: c for k, _l, c in GLASS_TYPES}


def glass_color(o) -> tuple:
    return GLASS_BY.get((o or {}).get("glass") or "clear", GLASS_COLOR)
LEAF_COLOR = (0.58, 0.42, 0.28, 1.0)
END_GAP = 0.10          # m kept between an opening and its wall's end
PANEL_W = 4 * 0.3048    # a sliding panel: 4' wide at most
PANEL_H = 7 * 0.3048    # …and a sliding door's panel 7' high


def opening_room(o: dict, wall: dict, others: list[dict],
                 wall_height: float) -> str | None:
    """Why an opening can't go there (None = it can): it must sit on a
    straight wall, wholly, clear of the wall's ends and of the wall's
    other openings, under the wall's top."""
    if wall.get("kind", "line") != "line":
        return "Openings go in straight walls (curved: not yet)"
    L = W.drawn(wall).L
    half = float(o["w"]) / 2
    if float(o["w"]) < 0.2 or float(o["h"]) < 0.2:
        return "Too small for an opening"
    if o["pos"] - half < END_GAP or o["pos"] + half > L - END_GAP:
        return "It doesn't fit in that wall"
    if float(o.get("sill", 0)) + float(o["h"]) > wall_height - 0.05:
        return "Too tall for that wall"
    for p in others:
        if p.get("id") == o.get("id") or p["wall"] != o["wall"]:
            continue
        if abs(p["pos"] - o["pos"]) < (float(p["w"]) + float(o["w"])) / 2 \
                + 0.05:
            return "It runs into another opening of that wall"
    return None


def _clip(poly, p0, u, s, keep_more: bool) -> list:
    """The part of a plan polygon on one side of the line across the
    wall's axis at distance s (Sutherland–Hodgman, one half-plane)."""
    def d(p):
        return ((p[0] - p0[0]) * u[0] + (p[1] - p0[1]) * u[1] - s) * \
            (1 if keep_more else -1)
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        da, db = d(a), d(b)
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out if len(out) >= 3 and abs(_area(out)) > 1e-9 else []


def wall_with_openings(piece: dict, seg, ops: list[dict], z0: float,
                       b: float, top: float) -> list:
    """A straight wall's solid with its openings, made as a plan draws
    it: each long face is ONE face with the openings cut out of it (a
    window: a hole; a door: a notch from the floor) — no seams running
    floor to ceiling past the jambs; then the openings' own faces (jambs,
    head, sill); the top and bottom faces lose what the openings take."""
    from shapely.geometry import Polygon, box
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union

    p0, u = seg.p0, seg.u
    poly = _ccw(list(piece["outer"]))
    eps = 1e-4
    spans = []                       # (s0, s1, zs, zt) — clipped to the wall
    rises = {}                       # an arch-top opening's rise, by span
    arch_of = {}                     # … and its shape
    for o in ops:
        zs = max(b, z0 + float(o.get("sill", 0.0)))
        zt = min(top, z0 + float(o.get("sill", 0.0)) + float(o["h"]))
        if zt - zs > 0.01:
            sp = (o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2, zs, zt)
            spans.append(sp)
            if (o.get("head") or "flat") == "arch" and zt < top - 0.02:
                r = min(head_size(o), zt - zs - 0.05)
                if r > 0.02:
                    rises[sp] = r
                    arch_of[sp] = o.get("arch")

    def S(p):
        return (p[0] - p0[0]) * u[0] + (p[1] - p0[1]) * u[1]

    faces = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        L = math.dist(p, q)
        if L < 1e-9:
            continue
        d = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
        along = abs(d[0] * u[1] - d[1] * u[0]) < 0.01   # (±0.6°: a
        #                    face a join turned a hair off the wall line)
        if not along:                # an end (square, mitred): whole
            faces.append([(p[0], p[1], b), (q[0], q[1], b),
                          (q[0], q[1], top), (p[0], p[1], top)])
            continue
        # this long face in its own (t along p→q, z) plane
        sp, sign = S(p), 1.0 if (d[0] * u[0] + d[1] * u[1]) > 0 else -1.0
        cut = []
        for spn in spans:
            s0, s1, zs, zt = spn
            t0, t1 = sorted(((s0 - sp) * sign, (s1 - sp) * sign))
            if t1 > eps and t0 < L - eps:
                zb_ = zs - (eps if zs <= b + eps else 0)
                if spn in rises:             # rectangle, then the arch
                    zsp = zt - rises[spn]
                    curve = arch_pts(t0, t1, zsp, zt, 20, arch_of.get(spn))
                    cut.append(Polygon([(t0, zb_), (t1, zb_)] + curve))
                else:
                    cut.append(box(t0, zb_, t1,
                                   zt + (eps if zt >= top - eps else 0)))
        region = box(0, b, L, top)
        if cut:
            region = region.difference(unary_union(cut))
        for g in getattr(region, "geoms", [region]):
            if g.is_empty or g.area < 1e-8:
                continue
            g = orient(g, 1.0)

            def P3(tz):
                t, z = tz
                return (p[0] + d[0] * t, p[1] + d[1] * t, z)
            faces.append({"loop": [P3(c) for c in list(g.exterior.coords)
                                   [:-1]],
                          "holes": [[P3(c) for c in list(r.coords)[:-1]]
                                    for r in g.interiors]})
    # the openings' own faces: jambs, head, sill (across the wall)
    nrm = (-u[1], u[0])
    for spn in spans:
        s0, s1, zs, zt = spn
        rise = rises.get(spn, 0.0)
        zj = zt - rise                   # the jambs stop at the spring
        # where the two long faces are at s (the faces' across offsets)
        offs = sorted({round((pt[0] - p0[0]) * nrm[0]
                             + (pt[1] - p0[1]) * nrm[1], 6) for pt in poly})
        c_lo, c_hi = offs[0], offs[-1]

        def P(s, c, z):
            return (p0[0] + u[0] * s + nrm[0] * c,
                    p0[1] + u[1] * s + nrm[1] * c, z)
        # jambs: at s0 facing +u, at s1 facing −u (into the opening);
        # (u, n, z) is right-handed: n × z = u
        faces.append([P(s0, c_lo, zs), P(s0, c_hi, zs), P(s0, c_hi, zj),
                      P(s0, c_lo, zj)])
        faces.append([P(s1, c_lo, zs), P(s1, c_lo, zj), P(s1, c_hi, zj),
                      P(s1, c_hi, zs)])
        if rise > 0:                             # the arch's soffit
            curve = arch_pts(s0, s1, zj, zt, 20,
                             arch_of.get(spn))     # s1 → crown → s0
            for (sa, za), (sb, zb2) in zip(curve, curve[1:]):
                # as the flat head: the smaller s first (faces inward)
                faces.append([P(sb, c_lo, zb2), P(sb, c_hi, zb2),
                              P(sa, c_hi, za), P(sa, c_lo, za)])
        elif zt < top - eps:                     # the head, facing down
            faces.append([P(s0, c_lo, zt), P(s0, c_hi, zt), P(s1, c_hi, zt),
                          P(s1, c_lo, zt)])
        if zs > b + eps:                         # the sill, facing up
            faces.append([P(s0, c_lo, zs), P(s1, c_lo, zs), P(s1, c_hi, zs),
                          P(s0, c_hi, zs)])
    # top and bottom: the plan, less what reaches them
    for z, up in ((top, True), (b, False)):
        plan = Polygon(poly)
        bands = [box(min(s0, s1), -1e3, max(s0, s1), 1e3)
                 for s0, s1, zs, zt in spans
                 if (zt >= top - eps if up else zs <= b + eps)]
        if bands:
            from shapely import affinity
            ang = math.degrees(math.atan2(u[1], u[0]))
            band = affinity.rotate(unary_union(bands), ang, origin=(0, 0))
            band = affinity.translate(band, p0[0], p0[1])
            plan = plan.difference(band)
        for g in getattr(plan, "geoms", [plan]):
            if g.is_empty or g.area < 1e-8:
                continue
            g = orient(g, 1.0)
            loop = [(c[0], c[1], z) for c in list(g.exterior.coords)[:-1]]
            holes = [[(c[0], c[1], z) for c in list(r.coords)[:-1]]
                     for r in g.interiors]
            if not up:                           # the bottom faces down
                loop = list(reversed(loop))
                holes = [list(reversed(h)) for h in holes]
            faces.append({"loop": loop, "holes": holes})
    return faces


def _box(p0, u, n, sa, sb, ca, cb, za, zb, color) -> list:
    """A box along a wall: axial sa..sb, across ca..cb (n side), height
    za..zb — six faces, outward, each with its colour."""
    def P(s, c, z):
        return (p0[0] + u[0] * s + n[0] * c, p0[1] + u[1] * s + n[1] * c, z)
    c = [P(sa, ca, za), P(sb, ca, za), P(sb, cb, za), P(sa, cb, za),
         P(sa, ca, zb), P(sb, ca, zb), P(sb, cb, zb), P(sa, cb, zb)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    # (u, n, z) is right-handed: these loops face outward
    return [{"loop": [c[i] for i in q], "holes": [], "color": color}
            for q in quads]


HANDLE_COLOR = (0.78, 0.79, 0.80, 1.0)    # brushed steel ironmongery
#: frame materials: key → (label, colour, face width m, depth m)
FRAMES = {"wood": ("Wood (chowkat)", (0.47, 0.31, 0.18, 1.0), 0.075, 0.10),
          "aluminium": ("Aluminium", (0.80, 0.81, 0.83, 1.0), 0.045, 0.07),
          "steel": ("Steel", (0.32, 0.34, 0.37, 1.0), 0.05, 0.06),
          "upvc": ("uPVC (white)", (0.96, 0.96, 0.95, 1.0), 0.06, 0.07)}
WOOD_DOORS = ("hinged", "main", "double", "french", "glazed", "pocket",
              "folding")
#: door types hung on hinges: one leaf or two («leaves»)
HINGED_TYPES = ("hinged", "main", "louvre", "glass", "glazed", "alu_glass")
ALU_COLOR = (0.80, 0.81, 0.83, 1.0)        # an aluminium leaf / panel
LEAVES = [(1, "Single leaf"), (2, "Double leaf")]


def leaves_of(o: dict) -> int:
    if o.get("style") in ("double", "french"):
        return 2
    return 2 if str(o.get("leaves", 1)) == "2" else 1


def frame_size(o: dict):
    """(label, colour, face width, depth) of the opening's frame: its
    material's, with the width / depth set on the opening (Edit ▸ Frame
    width, Frame depth) over them."""
    lab, col, f, dep = FRAMES[frame_of(o)]
    if frame_of(o) == "wood" and str(o.get("panel") or "").startswith(
            "veneer"):
        col = WALNUT_FRAME                  # a walnut door: walnut chowkat
    try:
        if float(o.get("frame_w") or 0) > 0:
            f = float(o["frame_w"])
        if float(o.get("frame_d") or 0) > 0:
            dep = float(o["frame_d"])
    except (TypeError, ValueError):
        pass
    return lab, col, f, dep


def frame_of(o: dict) -> str:
    """The opening's frame material: as set, else wood for hinged-type
    doors, steel for shutters, aluminium for sliding doors and windows."""
    fr = o.get("frame") or "auto"
    if fr in FRAMES:
        return fr
    sty = o.get("style") or ("hinged" if o.get("kind") == "door" else "")
    if o.get("kind") == "door":
        if sty in ("rolling", "garage"):
            return "steel"
        if sty in ("louvre", "alu_glass"):
            return "aluminium"
        if sty in WOOD_DOORS:
            return "wood"
    return "aluminium"
HEADS = [("flat", "Flat head"), ("transom", "Transom (fixed light over)"),
         ("arch", "Arch top")]


CW_FRAME = (0.80, 0.81, 0.83, 1.0)        # curtain wall mullions
CW_SPANDREL = (0.36, 0.40, 0.45, 1.0)     # an opaque (spandrel) panel
CW_GLASS = (0.55, 0.74, 0.86, 0.38)


def curtain_wall(w: dict, seg, ops: list, z0: float, b: float,
                 top: float) -> list:
    """A curtain wall on the wall's centre line: aluminium mullions on an
    even grid (``grid`` m, about), transoms every ``tgrid`` m and at its
    foot and head, glass between — the openings (doors in it) left to
    their own frames."""
    L = float(seg.L)
    if L < 0.2 or top - b < 0.2:
        return []
    gv = max(float(w.get("grid", 1.5) or 1.5), 0.3)
    gh = max(float(w.get("tgrid", 1.5) or 1.5), 0.3)
    H = top - b
    # the mullion lines: on each door's jambs, the rest of the wall shared
    # out evenly (about ``grid`` apart) between them — the grid meets the
    # doors, as a curtain wall's door is set in it
    marks = [0.0, L]
    mw_ = 0.06                                # (the mullion's face)
    if w.get("kind", "line") == "line":
        for o in ops:
            # a mullion each side of the door, its face on the door's
            # frame (the door between two mullions, as Revit sets it)
            for s_ in (float(o["pos"]) - float(o["w"]) / 2 - mw_ / 2,
                       float(o["pos"]) + float(o["w"]) / 2 + mw_ / 2):
                if 0.05 < s_ < L - 0.05:
                    marks.append(s_)
    marks = sorted(marks)
    grid_s = [marks[0]]
    for a_, b_ in zip(marks, marks[1:]):
        if b_ - a_ < 0.05:
            continue
        k_ = max(1, int(round((b_ - a_) / gv)))
        grid_s += [a_ + (b_ - a_) * i / k_ for i in range(1, k_ + 1)]
    nv = len(grid_s) - 1
    # a lower and an upper panel (their heights), the vision glass between
    # on the transom grid
    low = min(max(float(w.get("cw_low", 0.0) or 0.0), 0.0), H * 0.6)
    up = min(max(float(w.get("cw_up", 0.0) or 0.0), 0.0), H - low - 0.3)
    up = max(up, 0.0)
    mid0, mid1 = b + low, top - up
    nm = max(1, int(round((mid1 - mid0) / gh)))
    zs = [b] + ([mid0] if low > 0.02 else []) + \
        [mid0 + (mid1 - mid0) * j / nm for j in range(1, nm)] + \
        ([mid1] if up > 0.02 else []) + [top]
    # a transom at its doors' heads, the bays beside them too (the door's
    # head carried along the wall — the grid set out from the door)
    for o in ops:
        if o.get("kind") != "door":
            continue
        zh_ = z0 + float(o.get("sill", 0.0)) + float(o["h"])
        if b + 0.3 < zh_ < top - 0.2:
            zs = [z for z in zs if abs(z - zh_) > 0.25 or z in (b, top)]
            zs.append(zh_)
    zs = sorted(set(round(z, 5) for z in zs))
    nh = len(zs) - 1
    spandrel = (w.get("cw_fill") or "glass") == "spandrel"
    mw, md = 0.06, 0.15                       # mullion face, depth
    tw = 0.06                                 # transom height
    out = []
    pts = [seg.at(sg / L) for sg in grid_s]
    spans = [(float(o["pos"]) - float(o["w"]) / 2,
              float(o["pos"]) + float(o["w"]) / 2,
              z0 + float(o.get("sill", 0.0)),
              z0 + float(o.get("sill", 0.0)) + float(o["h"])) for o in ops]

    def free(sa, sb, za, zb):
        """The parts of the box sa..sb × za..zb outside the openings (a
        door cuts the grid: mullions, transoms and glass stop round it)."""
        parts = [(sa, sb, za, zb)]
        for s0, s1, q0, q1 in spans:
            nxt = []
            for a_, b_, c_, d_ in parts:
                if b_ <= s0 or a_ >= s1 or d_ <= q0 or c_ >= q1:
                    nxt.append((a_, b_, c_, d_))
                    continue
                if a_ < s0:
                    nxt.append((a_, s0, c_, d_))
                if b_ > s1:
                    nxt.append((s1, b_, c_, d_))
                m0, m1 = max(a_, s0), min(b_, s1)
                if d_ > q1:
                    nxt.append((m0, m1, max(c_, q1), d_))
                if c_ < q0:
                    nxt.append((m0, m1, c_, min(d_, q0)))
            parts = nxt
        return [q for q in parts if q[1] - q[0] > 0.01 and q[3] - q[2] > 0.01]
    straight = w.get("kind", "line") == "line"
    for k in range(nv + 1):                   # mullions
        f = grid_s[k] / L
        p = seg.at(f)
        t = seg.tangent(f)
        n = (-t[1], t[0])
        sk = L * f
        for a_, b_, c_, d_ in (free(sk - mw / 2, sk + mw / 2, b, top)
                               if straight else [(sk - mw / 2, sk + mw / 2,
                                                  b, top)]):
            out += _box(p, t, n, a_ - sk, b_ - sk, -md / 2, md / 2, c_, d_,
                        CW_FRAME)
    for k in range(nv):                       # transoms and glass, bay by bay
        a, c = pts[k], pts[k + 1]
        Lc = math.dist(a, c)
        if Lc < 1e-6:
            continue
        u = ((c[0] - a[0]) / Lc, (c[1] - a[1]) / Lc)
        n = (-u[1], u[0])
        sa = grid_s[k]

        def cut(za, zb):
            box_ = (sa + mw / 2, sa + Lc - mw / 2, za, zb)
            return free(*box_) if straight else [box_]
        for j, z in enumerate(zs):
            za = z if j == 0 else (z - tw if j == nh else z - tw / 2)
            zb = z + tw if j == 0 else (z if j == nh else z + tw / 2)
            for a_, b_, c_, d_ in cut(za, zb):
                out += _box(a, u, n, a_ - sa, b_ - sa, -md / 2 + 0.02,
                            md / 2 - 0.02, c_, d_, CW_FRAME)
        for j in range(nh):
            za = zs[j] + (tw if j == 0 else tw / 2)
            zb = zs[j + 1] - (tw if j + 1 == nh else tw / 2)
            if zb - za < 0.02:
                continue
            panel = (low > 0.02 and j == 0) or (up > 0.02 and j == nh - 1)
            for a_, b_, c_, d_ in cut(za, zb):
                out += _box(a, u, n, a_ - sa, b_ - sa, -0.006, 0.006, c_, d_,
                            CW_SPANDREL if (panel and spandrel)
                            else (GLASS_BY.get(w.get("glass"), CW_GLASS)
                                  if w.get("glass") else CW_GLASS))
    if straight:                              # a door's head: a transom
        p0, u0 = seg.at(0.0), seg.tangent(0.0)
        n0 = (-u0[1], u0[0])
        for s0, s1, q0, q1 in spans:
            if q1 < top - tw:
                out += _box(p0, u0, n0, s0, s1, -md / 2 + 0.02,
                            md / 2 - 0.02, q1, q1 + tw, CW_FRAME)
    return out


#: the arched heads' shapes: (key, label, rise over the opening's width)
ARCHES = [("semi", "Semicircular (Roman)", 0.50),
          ("segmental", "Segmental (shallow)", 0.20),
          ("elliptical", "Elliptical (basket)", 0.30),
          ("pointed", "Pointed (Islamic / Gothic, two-centred)", 0.80),
          ("ogee", "Ogee (Mughal, S-curved to a point)", 0.85),
          ("horseshoe", "Horseshoe (Moorish)", 0.65),
          ("multifoil", "Multifoil (cusped, five lobes)", 0.50),
          ("trefoil", "Trefoil (three lobes)", 0.50),
          ("tudor", "Tudor / four-centred (Persian, flat point)", 0.32)]
_RISE = {k: r for k, _l, r in ARCHES}


def head_size(o: dict) -> float:
    """How much of the opening's height its head takes (0: a flat head):
    a transom light, or an arch's rise (as its shape wants it — a
    semicircle half the width, a pointed arch more — capped by the
    opening's height)."""
    head = o.get("head") or "flat"
    h, w = float(o["h"]), float(o["w"])
    if head == "transom":
        return 0.45 if o["kind"] == "door" else min(0.45, 0.30 * h)
    if head == "arch":
        sty = o.get("arch") or "semi"
        if sty == "semi":
            cap = 0.60 if o["kind"] == "door" else 0.40 * h
            return min(w / 2, cap)
        cap = 1.20 if o["kind"] == "door" else 0.50 * h
        return min(_RISE.get(sty, 0.5) * w, cap)
    return 0.0


def _half(hw, r, sty, k):
    """The arch's right half in (dx, dz) from its spring (hw, 0) to the
    crown (0, r), never outside the jamb (dx ≤ hw)."""
    if sty == "pointed" and r > hw * 1.01:
        e = (r * r - hw * hw) / (2 * hw)        # centres on the spring line
        R = hw + e
        a1 = math.atan2(r, e)                   # from the centre (−e, 0)
        return [(-e + R * math.cos(a1 * i / k), R * math.sin(a1 * i / k))
                for i in range(k + 1)]
    if sty == "elliptical" or (sty == "pointed" and r <= hw * 1.01):
        return [(hw * math.cos(math.pi / 2 * i / k),
                 r * math.sin(math.pi / 2 * i / k)) for i in range(k + 1)]
    if sty == "ogee":
        m = max(k // 2, 3)
        lo = [(hw / 2 + hw / 2 * math.cos(math.pi / 2 * i / m),
               r / 2 * math.sin(math.pi / 2 * i / m)) for i in range(m + 1)]
        up = [(hw / 2 - hw / 2 * math.sin(math.pi / 2 * i / m),
               r - r / 2 * math.cos(math.pi / 2 * i / m))
              for i in range(1, m + 1)]
        return lo + up
    if sty == "horseshoe":
        # a circle wider than its spring: its centre over the spring line,
        # the jambs' line its widest; the arch steps in at the spring
        R = r / 1.3
        R = min(R, hw)
        zc = r - R
        x0 = math.sqrt(max(R * R - zc * zc, 0.0))
        out = [(hw, 0.0)]
        a0 = math.atan2(-zc, x0)
        for i in range(k + 1):
            a = a0 + (math.pi / 2 - a0) * i / k
            out.append((R * math.cos(a), zc + R * math.sin(a)))
        return out
    if sty in ("multifoil", "trefoil"):
        n = 5 if sty == "multifoil" else 3
        kk = max(k * 2, 24)
        out = []
        for i in range(kk + 1):
            th = math.pi / 2 * i / kk           # 0 at the spring
            # lobes: cusps pointing in, between them the full circle
            f = 1.0 - 0.14 * (1.0 - abs(math.sin(n * th)))
            out.append((hw * f * math.cos(th), r * f * math.sin(th)))
        out[0] = (hw, 0.0)
        return out
    if sty == "tudor":
        a = 0.35 * hw                           # the small arcs at the
        al = math.radians(60.0)                 # springs, then straight
        m = max(k // 2, 3)                      # to the flat point
        lo = [(hw - a + a * math.cos(al * i / m), a * math.sin(al * i / m))
              for i in range(m + 1)]
        px, pz = lo[-1]
        if r < pz + 0.01:
            r = pz + 0.01
        up = [(px * (1 - t), pz + (r - pz) * (t ** 0.85)) for t in
              (j / m for j in range(1, m + 1))]
        return lo + up
    return None


def arch_pts(s0, s1, zsp, zt, k=16, style=None) -> list:
    """The arch's curve in the wall's (along, z) plane, from (s1, zsp) over
    the crown (mid, zt) to (s0, zsp): of the shape ``style`` (ARCHES; a
    circle through spring and crown when none)."""
    hw, r = (s1 - s0) / 2, zt - zsp
    if r < 1e-4 or hw < 1e-4:
        return [(s1, zsp), (s0, zsp)]
    mid = (s0 + s1) / 2
    half = _half(abs(hw), r, style, k) if style and style not in (
        "semi", "segmental") else None
    if half:
        sg = 1.0 if hw > 0 else -1.0
        right = [(mid + sg * dx, zsp + dz) for dx, dz in half]
        left = [(mid - sg * dx, zsp + dz) for dx, dz in reversed(half[:-1])]
        return right + left
    R = (hw * hw + r * r) / (2 * r)
    zc = zt - R
    a1 = math.atan2(zsp - zc, hw)
    out = []
    for i in range(k + 1):
        a = a1 + (math.pi - 2 * a1) * i / k
        out.append((mid + R * math.cos(a), zc + R * math.sin(a)))
    return out


def _sz_prism(p0, u, n, pts, c0, c1, color) -> list:
    """A polygon in the wall's (along, z) plane, extruded across it from
    c0 to c1 (an arch's frame ring, its glass)."""
    def P(s_, z_, c_):
        return (p0[0] + u[0] * s_ + n[0] * c_, p0[1] + u[1] * s_ + n[1] * c_,
                z_)
    a2 = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1]))
    if a2 < 0:
        pts = pts[::-1]
    # (u, z) is CCW seen from −n: that face looks to −n
    out = [{"loop": [P(a, z, c0) for a, z in reversed(pts)], "holes": [],
            "color": color},
           {"loop": [P(a, z, c1) for a, z in pts], "holes": [],
            "color": color}]
    for (a, z), (b, y) in zip(pts, pts[1:] + pts[:1]):
        out.append({"loop": [P(a, z, c0), P(b, y, c0), P(b, y, c1),
                             P(a, z, c1)], "holes": [], "color": color})
    return out


def _lifted(o: dict, lifts: dict) -> dict:
    """A door standing on its threshold: its frame and leaf start at the
    threshold's top (the finished floor), the hole in the wall does not."""
    d = lifts.get(o.get("id"))
    if not d or o.get("kind") != "door" or float(o.get("sill", 0)) > 0.05:
        return o
    d = min(float(d), float(o["h"]) - 0.3)
    if d <= 0.002:
        return o
    return dict(o, sill=float(o.get("sill", 0)) + d, h=float(o["h"]) - d)


CW_POST = 0.08                 # m: the aluminium corner post (square)


def corner_window_faces(legs) -> list:
    """One aluminium window turning the corner(s) of its walls: [(wall,
    sill z, head z)] → frame (jambs at its two free ends, sill and head
    running round), the corner post where two legs meet, fixed glass
    panes (mullions at most 1.2 m apart) — no wall between the panes."""
    _lab, FC, f, dep = FRAMES["aluminium"]
    hd = dep / 2
    ph = CW_POST / 2
    segs = []
    for w, zs, zt in legs:
        sg = W.centre(w)
        segs.append((sg.p0, sg.p1, sg.u, zs, zt))
    ends = [p for p0, p1, *_r in segs for p in (p0, p1)]

    def shared(p):
        return sum(1 for q in ends if math.dist(p, q) < 0.02) > 1
    out = []
    posts = []
    for p0, p1, u, zs, zt in segs:
        if zt - zs < 0.2:
            continue
        n = (-u[1], u[0])
        L = math.dist(p0, p1)
        ca, cb = shared(p0), shared(p1)
        sa = ph if ca else 0.0
        sb = L - ph if cb else L
        parts = []
        if not ca:                                   # jambs at free ends
            parts.append(_box(p0, u, n, 0.0, f, -hd, hd, zs, zt, FC))
            sa = f
        if not cb:
            parts.append(_box(p0, u, n, L - f, L, -hd, hd, zs, zt, FC))
            sb = L - f
        if sb - sa < 0.05:
            continue
        parts.append(_box(p0, u, n, sa, sb, -hd, hd, zs, zs + f, FC))
        parts.append(_box(p0, u, n, sa, sb, -hd, hd, zt - f, zt, FC))
        k = max(1, int(math.ceil((sb - sa) / 1.2 - 1e-6)))
        for i in range(1, k):                        # mullions
            sm = sa + (sb - sa) * i / k
            parts.append(_box(p0, u, n, sm - f / 2, sm + f / 2, -hd, hd,
                              zs + f, zt - f, FC))
        parts.append(_box(p0, u, n, sa, sb, -0.005, 0.005, zs + f, zt - f,
                          GLASS_COLOR))
        for c, on in ((p0, ca), (p1, cb)):
            if on and not any(math.dist(c, q) < 0.02 for q in posts):
                posts.append(c)
                parts.append(_box(c, u, n, -ph, ph, -ph, ph, zs, zt, FC))
        out += [face for pt in parts for face in pt]
    return out


def opening_parts(o: dict, seg, z0: float) -> list:
    """The frame, glass (of its glass type), leaves and ironmongery of an
    opening — with its head."""
    faces = _opening_parts_head(o, seg, z0)
    gc = glass_color(o)
    if gc == GLASS_COLOR:
        return faces
    out = []
    for f in faces:
        if isinstance(f, dict) and tuple(f.get("color") or ()) == GLASS_COLOR:
            f = dict(f, color=gc)
        out.append(f)
    return out


def _opening_parts_head(o: dict, seg, z0: float) -> list:
    """The frame (and glass / leaves / ironmongery) of an opening — with
    its head: flat, a transom light over it, or an arch top."""
    hs = head_size(o) if o["kind"] != "void" else 0.0
    if hs <= 0.01:
        return _opening_parts(o, seg, z0)
    low = dict(o, h=float(o["h"]) - hs, head="flat")
    faces = _opening_parts(low, seg, z0)
    p0, u = seg.p0, seg.u
    n = (-u[1], u[0])
    s0, s1 = o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2
    zsp = z0 + float(o.get("sill", 0.0)) + float(low["h"])
    zt = z0 + float(o.get("sill", 0.0)) + float(o["h"])
    _lab, FRAME_COLOR, f, dep = frame_size(o)
    hd = dep / 2
    parts = []
    if (o.get("head") or "flat") == "transom":
        parts += [_box(p0, u, n, s0, s0 + f, -hd, hd, zsp, zt, FRAME_COLOR),
                  _box(p0, u, n, s1 - f, s1, -hd, hd, zsp, zt, FRAME_COLOR),
                  _box(p0, u, n, s0 + f, s1 - f, -hd, hd, zt - f, zt,
                       FRAME_COLOR),
                  _box(p0, u, n, s0 + f, s1 - f, -0.005, 0.005, zsp,
                       zt - f, GLASS_COLOR)]
        if o["w"] > 1.6:                         # mullions in a wide light
            k = int(math.ceil(o["w"] / 1.2))
            for i in range(1, k):
                sm = s0 + (s1 - s0) * i / k
                parts.append(_box(p0, u, n, sm - f / 2, sm + f / 2, -hd, hd,
                                  zsp, zt - f, FRAME_COLOR))
    else:                                        # arch: frame ring, glass
        sty = o.get("arch")
        outer = arch_pts(s0, s1, zsp, zt, 16, sty)
        inner = arch_pts(s0 + f, s1 - f, zsp, zt - f, 16, sty)
        ring = outer + list(reversed(inner))
        parts.append(_sz_prism(p0, u, n, ring, -hd, hd, FRAME_COLOR))
        parts.append(_sz_prism(p0, u, n, list(reversed(inner)), -0.005,
                               0.005, GLASS_COLOR))
    return faces + [face for pt in parts for face in pt]


HANDLE_TYPES = [("auto", "As the door type"),
                ("lever_rose", "Lever on a round rose"),
                ("lever_plate", "Lever on a back plate (with lock)"),
                ("knob", "Round knob"),
                ("pull_bar", "Pull bar (long, vertical)"),
                ("long_pull", "Tall pull bar, dark bronze (1.2 m)"),
                ("d_pull", "D pull handle"),
                ("flush", "Flush pull (recessed)"),
                ("none", "No handle")]
KEY_COLOR = (0.12, 0.12, 0.13, 1.0)
BRONZE_COLOR = (0.20, 0.16, 0.12, 1.0)     # dark bronze pull
WALNUT_LEAF = (0.40, 0.22, 0.11, 1.0)      # walnut veneer leaf
WALNUT_GROOVE = (0.22, 0.12, 0.06, 1.0)
WALNUT_FRAME = (0.33, 0.18, 0.09, 1.0)


def _handle(p0, u, n, ua, ub, c_h, toward, z, kind="lever") -> list:
    """Ironmongery on both faces of a leaf standing across the wall (its
    faces at ua and ub along the wall), at ``c_h`` across, ``z`` high:
    the lever / knob / pull of ``kind`` — its lever pointing ``toward``
    (±1 across, to the hinge side)."""
    kind = {"lever": "lever_rose", "pull": "pull_bar"}.get(kind, kind)
    if kind == "none":
        return []
    H = HANDLE_COLOR
    out = []

    def B(s_a, s_b, c_a, c_b, z_a, z_b, col=H):
        out.append(_box(p0, u, n, min(s_a, s_b), max(s_a, s_b),
                        min(c_a, c_b), max(c_a, c_b), z_a, z_b, col))

    def oct_disc(f, sg, r, th, cc, zc, col=H):
        """A round rose / knob as an octagon prism standing off the face
        ``f`` (outward ``sg``) — made of three boxes."""
        k = r * 0.414
        B(f, f + sg * th, cc - k, cc + k, zc - r, zc + r, col)
        B(f, f + sg * th, cc - r, cc + r, zc - k, zc + k, col)
        B(f, f + sg * th, cc - r * 0.71, cc + r * 0.71, zc - r * 0.71,
          zc + r * 0.71, col)
    for f, sg in ((ub, 1.0), (ua, -1.0)):           # each face of the leaf
        if kind == "lever_rose":
            oct_disc(f, sg, 0.026, 0.010, c_h, z)           # rose
            B(f + sg * 0.010, f + sg * 0.050, c_h - 0.009, c_h + 0.009,
              z - 0.009, z + 0.009)                         # spindle neck
            B(f + sg * 0.040, f + sg * 0.060, c_h, c_h + toward * 0.13,
              z - 0.010, z + 0.010)                         # the lever
            B(f + sg * 0.040, f + sg * 0.060, c_h + toward * 0.115,
              c_h + toward * 0.13, z - 0.010, z + 0.004)    # its turned end
        elif kind == "lever_plate":
            B(f, f + sg * 0.008, c_h - 0.023, c_h + 0.023, z - 0.13,
              z + 0.05)                                     # back plate
            B(f + sg * 0.008, f + sg * 0.050, c_h - 0.009, c_h + 0.009,
              z - 0.009, z + 0.009)
            B(f + sg * 0.040, f + sg * 0.060, c_h, c_h + toward * 0.13,
              z - 0.010, z + 0.010)
            B(f + sg * 0.008, f + sg * 0.010, c_h - 0.004, c_h + 0.004,
              z - 0.095, z - 0.075, KEY_COLOR)              # keyhole
        elif kind == "knob":
            oct_disc(f, sg, 0.027, 0.008, c_h, z)
            B(f + sg * 0.008, f + sg * 0.035, c_h - 0.010, c_h + 0.010,
              z - 0.010, z + 0.010)
            oct_disc(f + sg * 0.035, sg, 0.030, 0.030, c_h, z)
        elif kind == "pull_bar":
            L2 = 0.30
            B(f + sg * 0.055, f + sg * 0.080, c_h - 0.0125, c_h + 0.0125,
              z - L2, z + L2)                               # the bar
            for zz in (z - L2 + 0.05, z + L2 - 0.05):       # standoffs
                B(f, f + sg * 0.055, c_h - 0.008, c_h + 0.008, zz - 0.008,
                  zz + 0.008)
        elif kind == "long_pull":
            L2 = 0.60
            zc = max(z, L2 + 0.25)
            B(f + sg * 0.045, f + sg * 0.070, c_h - 0.011, c_h + 0.011,
              zc - L2, zc + L2, BRONZE_COLOR)               # the bar
            for zz in (zc - L2 + 0.08, zc + L2 - 0.08):     # standoffs
                B(f, f + sg * 0.045, c_h - 0.007, c_h + 0.007, zz - 0.007,
                  zz + 0.007, BRONZE_COLOR)
        elif kind == "d_pull":
            L2 = 0.11
            B(f + sg * 0.050, f + sg * 0.065, c_h - 0.008, c_h + 0.008,
              z - L2, z + L2)
            for zz in (z - L2, z + L2 - 0.014):
                B(f, f + sg * 0.065, c_h - 0.008, c_h + 0.008, zz,
                  zz + 0.014)
        elif kind == "flush":
            B(f - sg * 0.001, f + sg * 0.002, c_h - 0.022, c_h + 0.022,
              z - 0.07, z + 0.07)
            B(f + sg * 0.002, f + sg * 0.003, c_h - 0.015, c_h + 0.015,
              z - 0.055, z + 0.055, KEY_COLOR)
    return out

def _opening_parts(o: dict, seg, z0: float) -> list:
    """The frame (and glass / leaf) of an opening, on the wall's centre
    line: faces with their colours. A void has none."""
    if o["kind"] == "void":
        return []
    p0, u = seg.p0, seg.u
    n = (-u[1], u[0])
    s0, s1 = o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2
    zs = z0 + float(o.get("sill", 0.0))
    zt = zs + float(o["h"])
    _lab, FC, f, dep = frame_size(o)
    hd = dep / 2
    parts = [_box(p0, u, n, s0, s0 + f, -hd, hd, zs, zt, FC),
             _box(p0, u, n, s1 - f, s1, -hd, hd, zs, zt, FC),
             _box(p0, u, n, s0 + f, s1 - f, -hd, hd, zt - f, zt, FC)]
    style = o.get("style") or ""
    G, F = GLASS_COLOR, FC
    if o["kind"] == "window" or style == "sliding":
        if o["kind"] == "window":                    # the sill's frame
            parts.append(_box(p0, u, n, s0 + f, s1 - f, -hd, hd, zs, zs + f,
                              F))
            zb = zs + f
        else:
            zb = zs
        x0, x1, zt2 = s0 + f, s1 - f, zt - f
        mid = (x0 + x1) / 2
        if style == "sliding":
            # panels at most 4' wide, on two tracks, overlapping; a door's
            # panels at most 7' high — a fixed glass light above them
            W = x1 - x0
            npan = max(2, int(math.ceil(W / PANEL_W - 1e-6)))
            pw = W / npan
            ph = zt2 - zb
            if o["kind"] == "door" and ph > PANEL_H + 0.05:
                ph = PANEL_H
                parts.append(_box(p0, u, n, x0, x1, -hd, hd, zb + ph,
                                  zb + ph + f, F))           # transom bar
                parts.append(_box(p0, u, n, x0, x1, -0.005, 0.005,
                                  zb + ph + f, zt2, G))      # fixed light
            ztop = zb + ph
            for k in range(npan):
                a0 = x0 + k * pw - (0.02 if k else 0.0)
                a1 = x0 + (k + 1) * pw + (0.02 if k < npan - 1 else 0.0)
                c = -0.018 if k % 2 == 0 else 0.018
                parts += [_box(p0, u, n, a0, a1, c - 0.012, c + 0.012, zb,
                               zb + 0.04, F),
                          _box(p0, u, n, a0, a1, c - 0.012, c + 0.012,
                               ztop - 0.04, ztop, F),
                          _box(p0, u, n, a0, a0 + 0.04, c - 0.012, c + 0.012,
                               zb, ztop, F),
                          _box(p0, u, n, a1 - 0.04, a1, c - 0.012, c + 0.012,
                               zb, ztop, F),
                          _box(p0, u, n, a0 + 0.04, a1 - 0.04, c - 0.004,
                               c + 0.004, zb + 0.04, ztop - 0.04, G)]
                # the pull on the jamb side of the end panels, both faces —
                # never on the edges where the panels meet (the inner
                # panels of a 3- or 4-panel set have none)
                if o["kind"] != "door":     # windows: no pulls (3.14.1)
                    continue
                if k == 0:
                    sh = a0 + 0.05
                elif k == npan - 1:
                    sh = a1 - 0.07
                else:
                    continue
                zh = zb + (1.05 if o["kind"] == "door" else
                           min(0.5 * (ztop - zb), 0.35))
                hl = 0.30 if o["kind"] == "door" else 0.08
                for cc in (-1, 1):
                    parts.append(_box(p0, u, n, sh, sh + 0.02,
                                      c + cc * 0.012, c + cc * 0.03,
                                      zh - hl, zh + hl, HANDLE_COLOR))
        elif style == "fixed":
            parts.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zb, zt2, G))
        elif style == "louvre":      # glass slats across
            k = max(int((zt2 - zb) / 0.10), 1)
            for i in range(k):
                z = zb + (i + 0.5) * (zt2 - zb) / k
                parts.append(_box(p0, u, n, x0, x1, -0.03, 0.03, z - 0.004,
                                  z + 0.004, G))
        elif style in ("top-hung", "awning"):
            parts.append(_box(p0, u, n, x0, x1, -0.01, 0.01, zt2 - 0.04,
                              zt2, F))
            parts.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zb, zt2 - 0.04,
                              G))
        else:                        # casement: two hinged sashes
            for a0, a1 in ((x0, mid), (mid, x1)):
                parts += [_box(p0, u, n, a0, a0 + 0.035, -0.01, 0.01, zb,
                               zt2, F),
                          _box(p0, u, n, a1 - 0.035, a1, -0.01, 0.01, zb,
                               zt2, F),
                          _box(p0, u, n, a0 + 0.035, a1 - 0.035, -0.005,
                               0.005, zb, zt2, G)]
    else:
        parts += door_parts(o, style, p0, u, n, s0, s1, zs, zt, hd, f)
        if style not in NO_TRIM and o.get("_t"):
            parts += door_trim(o, p0, u, n, s0, s1, zs, zt, FC)
    return [face for p in parts for face in p]


NO_TRIM = ("sliding", "rolling", "garage", "pocket")
LINING_T = 0.018           # m: the jamb lining board over the reveal
ARCH_W, ARCH_T = 0.075, 0.018    # m: the architrave's face width, depth


def door_trim(o, p0, u, n, s0, s1, zs, zt, col) -> list:
    """A door's joinery round its frame: the jamb lining (boards over the
    reveal, the wall's full thickness, both jambs and the head) and an
    architrave on both faces of the wall (two legs and a head)."""
    t2 = float(o["_t"]) / 2
    L, D = LINING_T, ARCH_T
    try:                          # its own architrave width (0: none)
        A = float(o["arch_w"]) if o.get("arch_w") is not None else ARCH_W
    except (TypeError, ValueError):
        A = ARCH_W
    out = [_box(p0, u, n, s0, s0 + L, -t2, t2, zs, zt, col),       # linings
           _box(p0, u, n, s1 - L, s1, -t2, t2, zs, zt, col),
           _box(p0, u, n, s0, s1, -t2, t2, zt - L, zt, col)]
    if A <= 0.001:
        return out
    for c0, c1 in ((t2, t2 + D), (-t2 - D, -t2)):                 # architraves
        out += [_box(p0, u, n, s0 - A, s0 + L, c0, c1, zs, zt + A, col),
                _box(p0, u, n, s1 - L, s1 + A, c0, c1, zs, zt + A, col),
                _box(p0, u, n, s0 + L, s1 - L, c0, c1, zt - L, zt + A, col)]
    return out


STEEL_COLOR = (0.62, 0.64, 0.67, 1.0)      # a lift's landing door

#: the door types (as the window types): key → label
DOOR_STYLES = [("hinged", "Hinged, flush"),
               ("main", "Main entrance (panelled)"),
               ("louvre", "Louvred aluminium (ventilation)"),
               ("glass", "Frameless glass"),
               ("alu_glass", "Hinged glass (aluminium frame)"),
               ("glazed", "Glazed (French)"),
               ("sliding", "Sliding glass"),
               ("pocket", "Pocket (slides into the wall)"),
               ("folding", "Folding (bi-fold)"),
               ("rolling", "Rolling shutter"),
               ("garage", "Garage (sectional)")]
WINDOW_STYLES = [("casement", "Casement (hinged)"), ("sliding", "Sliding"),
                 ("fixed", "Fixed glass"), ("top-hung", "Top-hung"),
                 ("louvre", "Louvre")]
PANEL_COLOR = (0.50, 0.36, 0.24, 1.0)      # a panelled leaf's mouldings
SHUTTER_COLOR = (0.70, 0.72, 0.74, 1.0)    # rolling shutter / garage door


PANEL_TYPES = [("auto", "As the door type"), ("flush", "Flush"),
               ("panel2", "2 panels"), ("panel4", "4 panels"),
               ("panel6", "6 panels"), ("glazed_half", "Half glazed"),
               ("glazed_full", "Fully glazed"), ("louvred", "Louvred"),
               ("ledged", "Ledged (vertical boards)"),
               ("veneer_walnut", "Walnut veneer, flush (luxury)"),
               ("veneer_grooved", "Walnut veneer with grooves (luxury)")]


def leaf_face(pk, p0, u, n, ua, ub, ca, cb, z0, z1) -> list:
    """A wooden leaf standing open (thickness ua..ub along the wall, width
    ca..cb across, z0..z1 high) with its face: flush, panelled (2 / 4 / 6
    raised panels, both faces), half / fully glazed, louvred or ledged."""
    P = []
    W = cb - ca
    if pk in ("glazed_half", "glazed_full", "louvred"):
        st_, top_ = 0.10, 0.12
        mid = z0 + (z1 - z0) * 0.45
        P += [_box(p0, u, n, ua, ub, ca, ca + st_, z0, z1, LEAF_COLOR),
              _box(p0, u, n, ua, ub, cb - st_, cb, z0, z1, LEAF_COLOR),
              _box(p0, u, n, ua, ub, ca + st_, cb - st_, z1 - top_, z1,
                   LEAF_COLOR),
              _box(p0, u, n, ua, ub, ca + st_, cb - st_, z0, z0 + 0.20,
                   LEAF_COLOR)]
        lo = z0 + 0.20
        if pk == "glazed_half":                 # solid below the mid rail
            P.append(_box(p0, u, n, ua, ub, ca + st_, cb - st_, lo, mid,
                          LEAF_COLOR))
            P.append(_box(p0, u, n, ua, ub, ca + st_, cb - st_, mid,
                          mid + 0.10, LEAF_COLOR))
            for z_a, z_b in ((lo + 0.08, mid - 0.08),):
                P.append(_box(p0, u, n, ua - 0.008, ub + 0.008,
                              ca + st_ + 0.06, cb - st_ - 0.06, z_a, z_b,
                              PANEL_COLOR))
            lo = mid + 0.10
        if pk == "louvred":
            k = max(int((z1 - top_ - lo) / 0.06), 1)
            for j in range(k):
                zz = lo + (z1 - top_ - lo) * (j + 0.15) / k
                slat = [(ua, zz), (ub, zz + 0.035), (ub, zz + 0.045),
                        (ua, zz + 0.010)]
                P.append(_sz_prism(p0, u, n, slat, ca + st_, cb - st_,
                                   LEAF_COLOR))
        else:
            P.append(_box(p0, u, n, ua + 0.012, ub - 0.012, ca + st_,
                          cb - st_, lo, z1 - top_, GLASS_COLOR))
        return P
    if pk in ("veneer_walnut", "veneer_grooved"):     # walnut veneer
        P.append(_box(p0, u, n, ua, ub, ca, cb, z0, z1, WALNUT_LEAF))
        if pk == "veneer_grooved":
            # V-grooves across both faces, and one down the lock side
            H = z1 - z0
            for j in (0.22, 0.42, 0.62, 0.82):
                zz = z0 + H * j
                for a_, b_ in ((ua - 0.003, ua), (ub, ub + 0.003)):
                    P.append(_box(p0, u, n, a_, b_, ca + 0.06, cb - 0.06,
                                  zz - 0.003, zz + 0.003, WALNUT_GROOVE))
        return P
    P.append(_box(p0, u, n, ua, ub, ca, cb, z0, z1, LEAF_COLOR))
    if pk == "ledged":                          # board joints, both faces
        k = max(int(W / 0.10), 2)
        for j in range(1, k):
            c_ = ca + W * j / k
            for a_, b_ in ((ua - 0.004, ua), (ub, ub + 0.004)):
                P.append(_box(p0, u, n, a_, b_, c_ - 0.004, c_ + 0.004,
                              z0 + 0.02, z1 - 0.02, PANEL_COLOR))
        return P
    grid = {"panel2": (1, 2), "panel4": (2, 2), "panel6": (2, 3)}.get(pk)
    if not grid:
        return P                                # flush
    cols, rows = grid
    m, g = 0.11, 0.10                           # margin, gap between
    pw = (W - 2 * m - (cols - 1) * g) / cols
    ph = (z1 - z0 - 2 * 0.14 - (rows - 1) * g) / rows
    if pw < 0.05 or ph < 0.05:
        return P
    for i in range(cols):
        c_a = ca + m + i * (pw + g)
        for j in range(rows):
            z_a = z0 + 0.14 + j * (ph + g)
            P.append(_box(p0, u, n, ua - 0.008, ub + 0.008, c_a, c_a + pw,
                          z_a, z_a + ph, PANEL_COLOR))
    return P


def _hk(o, default):
    """The door's handle type: as set (Edit ▸ Door handle), else its
    type's."""
    h = o.get("handle") or "auto"
    return default if h == "auto" else h


def door_parts(o, style, p0, u, n, s0, s1, zs, zt, hd, f) -> list:
    """A door's leaves (its frame is made already), by its type. Hinged
    leaves stand OPEN 90° into the room they open to, so the plans show
    them as leaves, not as a thin wall."""
    side = 1.0 if float(o.get("face", 1) or 1) >= 0 else -1.0
    z0, z1 = zs + 0.01, zt - f
    W = s1 - s0 - 2 * f
    parts = []

    def hinged(hs, away, lw, kind):
        ua, ub = sorted((hs, hs + away * LEAF))
        ca, cb = sorted((side * hd, side * (hd + lw)))
        c_free = side * (hd + lw)               # the leaf's free edge
        c_h = c_free - side * 0.07              # where its handle is
        zh = zs + 1.0                           # handle height, 1 m
        if kind == "glass":                     # 12 mm toughened glass
            ua, ub = sorted((hs, hs + away * 0.012))
            parts.append(_box(p0, u, n, ua, ub, ca, cb, z0, z1, GLASS_COLOR))
            fa, fb = (ca, ca + 0.15) if side > 0 else (cb - 0.15, cb)
            for zz in (z0 + 0.1, z1 - 0.15):    # patch fittings (hinges)
                parts.append(_box(p0, u, n, ua - 0.01, ub + 0.01, fa, fb,
                                  zz, zz + 0.05, STEEL_COLOR))
            parts.extend(_handle(p0, u, n, ua, ub, c_h - side * 0.03,
                                 -side, zh, _hk(o, "pull_bar")))
            return
        parts.extend(_handle(p0, u, n, ua, ub, c_h, -side, zh,
                             _hk(o, "lever_plate" if kind == "main"
                                 else "lever_rose")))
        if kind == "alu_glass":            # aluminium leaf, glazed
            st_ = 0.07
            for c_a, c_b in ((ca, ca + st_), (cb - st_, cb)):
                parts.append(_box(p0, u, n, ua, ub, c_a, c_b, z0, z1,
                                  ALU_COLOR))
            for z_a, z_b in ((z0, z0 + 0.12), (z1 - 0.07, z1)):
                parts.append(_box(p0, u, n, ua, ub, ca + st_, cb - st_, z_a,
                                  z_b, ALU_COLOR))
            parts.append(_box(p0, u, n, ua + 0.012, ub - 0.012, ca + st_,
                              cb - st_, z0 + 0.12, z1 - 0.07, GLASS_COLOR))
        if kind == "louvre":               # aluminium: stiles, rails, slats
            st_ = 0.09
            for c_a, c_b in ((ca, ca + st_), (cb - st_, cb)):
                parts.append(_box(p0, u, n, ua, ub, c_a, c_b, z0, z1,
                                  ALU_COLOR))
            for z_a, z_b in ((z0, z0 + 0.18), ((z0 + z1) / 2 - 0.06,
                                               (z0 + z1) / 2 + 0.06),
                             (z1 - 0.10, z1)):
                parts.append(_box(p0, u, n, ua, ub, ca + st_, cb - st_, z_a,
                                  z_b, ALU_COLOR))
            for z_a, z_b in ((z0 + 0.18, (z0 + z1) / 2 - 0.06),
                             ((z0 + z1) / 2 + 0.06, z1 - 0.10)):
                k = max(int((z_b - z_a) / 0.055), 1)
                for j in range(k):
                    zz = z_a + (z_b - z_a) * (j + 0.15) / k
                    slat = [(ua, zz), (ub, zz + 0.035), (ub, zz + 0.047),
                            (ua, zz + 0.012)]
                    parts.append(_sz_prism(p0, u, n, slat, ca + st_,
                                           cb - st_, ALU_COLOR))
        if kind == "french":                    # glazed leaf: stiles, rails
            st_ = 0.08
            for c_a, c_b in ((ca, ca + st_), (cb - st_, cb)):
                parts.append(_box(p0, u, n, ua, ub, c_a, c_b, z0, z1,
                                  LEAF_COLOR))
            for z_a, z_b in ((z0, z0 + 0.20), (z1 - 0.10, z1)):
                parts.append(_box(p0, u, n, ua, ub, ca + st_, cb - st_, z_a,
                                  z_b, LEAF_COLOR))
            parts.append(_box(p0, u, n, ua + 0.01, ub - 0.01, ca + st_,
                              cb - st_, z0 + 0.20, z1 - 0.10, GLASS_COLOR))
            return
        if kind in ("hinged", "main"):         # a wooden leaf: its face
            pk = o.get("panel") or ("panel4" if kind == "main" else "flush")
            parts.extend(leaf_face(pk, p0, u, n, ua, ub, ca, cb, z0, z1))
            return
        if kind not in ("louvre", "alu_glass"):
            parts.append(_box(p0, u, n, ua, ub, ca, cb, z0, z1, LEAF_COLOR))

    style = {"double": "hinged", "french": "glazed"}.get(style, style)
    two = leaves_of(o) == 2
    if style in HINGED_TYPES and two:           # two leaves, one each side
        kind = {"glazed": "french"}.get(style, style)
        lw = W / 2
        hinged(s0 + f, 1.0, lw, kind)
        hinged(s1 - f, -1.0, lw, kind)
    elif style == "pocket" and two:             # bi-parting, both pockets
        for sgn, edge in ((1, s0 + f), (-1, s1 - f)):
            a_ = edge - sgn * (W / 2 - 0.10)
            parts.append(_box(p0, u, n, min(a_, edge + sgn * 0.10),
                              max(a_, edge + sgn * 0.10), -LEAF / 2,
                              LEAF / 2, z0, z1, LEAF_COLOR))
    elif style == "pocket":
        # the leaf slid into the wall, a hand's width left out
        parts.append(_box(p0, u, n, s0 + f - W + 0.10, s0 + f + 0.10,
                          -LEAF / 2, LEAF / 2, z0, z1, LEAF_COLOR))
        for cc in (-1, 1):                      # flush pulls, both faces
            parts.append(_box(p0, u, n, s0 + f + 0.03, s0 + f + 0.07,
                              cc * LEAF / 2 - 0.004, cc * LEAF / 2 + 0.004,
                              zs + 0.95, zs + 1.10, HANDLE_COLOR))
    elif style == "folding":
        # bi-fold leaves, folded zig-zag to one side
        k = max(2, int(math.ceil(W / 0.5)))
        k += k % 2
        lw = W / k
        ang = math.radians(60.0)
        x = s0 + f
        for i in range(k):
            sgn = 1 if i % 2 == 0 else -1
            xa = x
            xb = x + lw * math.cos(ang)
            ca = 0.0 if sgn > 0 else side * lw * math.sin(ang)
            cb = side * lw * math.sin(ang) if sgn > 0 else 0.0
            # a leaf: a thin box along the fold (as a prism from 4 corners)
            q = [(xa, ca), (xb, cb)]
            dx, dc = q[1][0] - q[0][0], q[1][1] - q[0][1]
            L = math.hypot(dx, dc) or 1.0
            ox, oc = -dc / L * 0.02, dx / L * 0.02
            pts = [(q[0][0] - ox, q[0][1] - oc), (q[1][0] - ox, q[1][1] - oc),
                   (q[1][0] + ox, q[1][1] + oc), (q[0][0] + ox, q[0][1] + oc)]
            parts.append(_prism_uv(p0, u, n, pts, z0, z1, LEAF_COLOR))
            if i == k - 1:                      # the knob on the last leaf
                parts.append(_box(p0, u, n, xb - 0.06, xb - 0.03,
                                  cb - 0.03, cb + 0.03, zs + 0.98,
                                  zs + 1.04, HANDLE_COLOR))
            x = xb
    elif style in ("rolling", "garage"):
        # closed: slats (rolling, with its box over the opening) or four
        # sectional panels
        if style == "rolling":
            parts.append(_box(p0, u, n, s0, s1, -hd - 0.12, -hd, zt - 0.30,
                              zt, SHUTTER_COLOR))
            k = max(int((z1 - z0) / 0.08), 1)
            for i in range(k):
                za = z0 + i * (z1 - z0) / k
                parts.append(_box(p0, u, n, s0 + f, s1 - f, -0.012, 0.012,
                                  za + 0.004, za + (z1 - z0) / k, SHUTTER_COLOR))
        else:
            k = 4
            for i in range(k):
                za = z0 + i * (z1 - z0) / k
                parts.append(_box(p0, u, n, s0 + f, s1 - f, -0.02, 0.02,
                                  za + 0.006, za + (z1 - z0) / k,
                                  SHUTTER_COLOR))
        mid = (s0 + s1) / 2                     # the lift handle, low
        for cc in (-1, 1):
            parts.append(_box(p0, u, n, mid - 0.15, mid + 0.15,
                              cc * 0.03 - 0.01, cc * 0.03 + 0.01,
                              z0 + 0.25, z0 + 0.29, HANDLE_COLOR))
    else:                                       # one hinged leaf
        kind = {"glazed": "french"}.get(style, style)
        kind = kind if kind in ("main", "glass", "louvre", "french",
                                "alu_glass") else "hinged"
        if o.get("swing", "left") == "left":
            hinged(s0 + f, 1.0, W, kind)
        else:
            hinged(s1 - f, -1.0, W, kind)
    return parts


def _prism_uv(p0, u, n, pts, z0, z1, color) -> list:
    """A vertical prism over a 2D outline given in the wall's (along,
    across) frame."""
    def P(s_, c_, z):
        return (p0[0] + u[0] * s_ + n[0] * c_, p0[1] + u[1] * s_ + n[1] * c_, z)
    a2 = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1]))
    if a2 < 0:
        pts = pts[::-1]
    # (along, across) is a right-handed frame when n is u turned left
    out = [{"loop": [P(a, c, z1) for a, c in pts], "holes": [],
            "color": color},
           {"loop": [P(a, c, z0) for a, c in reversed(pts)], "holes": [],
            "color": color}]
    for (a, c), (b, d) in zip(pts, pts[1:] + pts[:1]):
        out.append({"loop": [P(a, c, z0), P(b, d, z0), P(b, d, z1),
                             P(a, c, z1)], "holes": [], "color": color})
    return out


def lift_door(dr: dict, z0: float, top: float) -> list:
    """A lift's landing door in its gap through the core: the RCC lintel
    over it, a steel frame, and two steel panels meeting in the middle
    (centre-opening), closed."""
    a, b = dr["a"], dr["b"]
    L = math.dist(a, b)
    if L < 0.3:
        return []
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])
    t = float(dr.get("t", 0.2)) / 2
    h = min(float(dr.get("h", 2.1)), top - z0 - 0.05)
    out = []
    if top - (z0 + h) > 0.02:                       # the lintel
        out += _box(a, u, n, 0.0, L, -t, t, z0 + h, top, None)
    f, S_ = 0.05, STEEL_COLOR
    out += _box(a, u, n, 0.0, f, -0.04, 0.04, z0, z0 + h, S_)
    out += _box(a, u, n, L - f, L, -0.04, 0.04, z0, z0 + h, S_)
    out += _box(a, u, n, f, L - f, -0.04, 0.04, z0 + h - f, z0 + h, S_)
    mid = L / 2
    out += _box(a, u, n, f, mid - 0.003, -0.015, 0.015, z0 + 0.01,
                z0 + h - f, S_)
    out += _box(a, u, n, mid + 0.003, L - f, -0.015, 0.015, z0 + 0.01,
                z0 + h - f, S_)
    return out


# ---- roofs ---------------------------------------------------------------------------
#: a roof: {"type": "roof", "kind": "gable" | "hip" | "flat",
#:   "corners": its outline (a pitched roof: a rectangle, 4 corners),
#:   "slope" (°), "overhang", "t" (thickness), "ridge": "long" | "short"
#:   (a gable's), "parapet" (m over a flat roof, 0 = none), "pt" (its
#:   thickness)} — it rests on the top of its level's walls.
ROOF_COLOR = (0.66, 0.36, 0.27, 1.0)       # tiles
FLAT_COLOR = (0.72, 0.73, 0.74, 1.0)       # a flat roof (concrete)
GABLE_COLOR = (0.88, 0.86, 0.82, 1.0)      # the gable walls (as walls)


def rect_frame(corners):
    """(centre, unit along the first side, half-length, unit across,
    half-width) of a 4-corner rectangle outline."""
    c = [tuple(p) for p in corners]
    cx = sum(p[0] for p in c) / 4
    cy = sum(p[1] for p in c) / 4
    e0 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e1 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    a, b = math.hypot(*e0), math.hypot(*e1)
    u0 = (e0[0] / a, e0[1] / a) if a > 1e-9 else (1.0, 0.0)
    return (cx, cy), u0, a / 2, (-u0[1], u0[0]), b / 2


def _sweep(section, x0, x1, P, color) -> list:
    """A section (y, z), counter-clockwise, swept along x from x0 to x1:
    its two caps and its sides, outward."""
    faces = [{"loop": [P(x1, y, z) for y, z in section], "holes": [],
              "color": color},
             {"loop": [P(x0, y, z) for y, z in reversed(section)],
              "holes": [], "color": color}]
    n = len(section)
    for i in range(n):
        (py, pz), (qy, qz) = section[i], section[(i + 1) % n]
        faces.append({"loop": [P(x0, py, pz), P(x0, qy, qz), P(x1, qy, qz),
                               P(x1, py, pz)], "holes": [], "color": color})
    return faces


def _faces(raw, color) -> list:
    return [dict(f, color=color) if isinstance(f, dict) else
            {"loop": f, "holes": [], "color": color} for f in raw]


def roof_faces(r: dict, base: float, wall_t: float = 0.20) -> list:
    """A roof's faces, resting on ``base`` (its level's wall tops): a
    pitched roof's underside passes through the walls' outer top edge."""
    kind = r.get("kind", "flat")
    t = float(r.get("t", 0.20))
    o = float(r.get("overhang", 0.0))
    if kind == "flat":
        from shapely.geometry import Polygon
        from shapely.geometry.polygon import orient
        poly = Polygon(r["corners"])
        if o > 1e-6:
            poly = poly.buffer(o, join_style=2)
        poly = orient(poly, 1.0)
        outer = list(poly.exterior.coords)[:-1]
        faces = _faces(W.solid({"outer": outer, "holes": []}, base,
                               base + t), FLAT_COLOR)
        ph, pt = float(r.get("parapet", 0.0)), float(r.get("pt", 0.15))
        inner = poly.buffer(-pt, join_style=2) if ph > 1e-6 else None
        if inner is not None and inner.geom_type == "Polygon" \
                and inner.area > 0.1:                # the parapet: a ring
            hole = list(orient(inner, 1.0).exterior.coords)[:-1]
            ring = {"outer": outer, "holes": [list(reversed(hole))]}
            faces += _faces(W.solid(ring, base + t, base + t + ph),
                            GABLE_COLOR)
        return faces
    (cx, cy), u0, ha, v0, hb = rect_frame(r["corners"])
    # x along the ridge (the longer side; a gable may be asked the other
    # way), y across, z up — a right-handed frame
    along = ha >= hb
    if kind == "gable" and r.get("ridge", "long") == "short":
        along = not along
    ux, A, B = (u0, ha, hb) if along else (v0, hb, ha)
    uy = (-ux[1], ux[0])
    ang = math.radians(float(r.get("slope", 30.0)))
    tan, dz = math.tan(ang), t / math.cos(ang)

    def P(x, y, z):
        return (cx + ux[0] * x + uy[0] * y, cy + ux[1] * x + uy[1] * y, z)
    if kind == "gable":
        Y, X = B + o, A + o

        def zb(y):
            return base + (B - abs(y)) * tan
        # counter-clockwise in (y, z): along the underside, up the eave,
        # back along the top
        section = [(-Y, zb(-Y)), (0, zb(0)), (Y, zb(Y)), (Y, zb(Y) + dz),
                   (0, zb(0) + dz), (-Y, zb(-Y) + dz)]
        faces = _sweep(section, -X, X, P, ROOF_COLOR)
        # the gable walls: a triangle on each end wall, as thick as it —
        # 2 mm under the roof and 1 mm off the wall's faces (no coplanar
        # faces), its foot 1 mm down into the wall
        d = 0.002
        b2 = B - d / tan
        tri = [(-b2, base - 0.001), (b2, base - 0.001), (0, zb(0) - d)]
        faces += _sweep(tri, A - wall_t + 0.001, A - 0.001, P, GABLE_COLOR)
        faces += _sweep(tri, -A + 0.001, -A + wall_t - 0.001, P,
                        GABLE_COLOR)
        return faces
    # a hip roof: four planes of one slope, the ridge along x
    Ao, Bo = A + o, B + o
    ze, zr = base - o * tan, base + B * tan
    r1, r2 = (-(A - B), 0.0), ((A - B), 0.0)
    sw, se, ne, nw = (-Ao, -Bo), (Ao, -Bo), (Ao, Bo), (-Ao, Bo)
    eaves = (sw, se, ne, nw)
    faces = []
    for loop in ([sw, se, r2, r1], [se, ne, r2], [ne, nw, r1, r2],
                 [nw, sw, r1]):
        pts = []
        for q in loop:
            if all(math.dist(q, p) > 1e-9 for p in pts):
                pts.append(q)
        zt = [ze if q in eaves else zr for q in pts]
        faces.append({"loop": [P(q[0], q[1], z + dz)
                               for q, z in zip(pts, zt)], "holes": [],
                      "color": ROOF_COLOR})
        faces.append({"loop": [P(q[0], q[1], z) for q, z in
                               reversed(list(zip(pts, zt)))], "holes": [],
                      "color": ROOF_COLOR})
    for i in range(4):                           # the eaves' fascias
        p, q = eaves[i], eaves[(i + 1) % 4]
        faces.append({"loop": [P(p[0], p[1], ze), P(q[0], q[1], ze),
                               P(q[0], q[1], ze + dz), P(p[0], p[1], ze + dz)],
                      "holes": [], "color": ROOF_COLOR})
    return faces


def roof_outline(walls: list[dict], union, kind: str):
    """A roof's outline from its level's walls: their outer contour; a
    pitched roof's, the rectangle round it (turned with the building)."""
    loop = inside_walls(walls, union)
    return roof_corners(loop, kind) if loop else loop


def roof_corners(corners, kind: str) -> list:
    """A roof's corners as stored: a flat roof's as drawn; a pitched
    roof's, the rectangle round them (turned with them)."""
    pts = _ccw([tuple(p) for p in corners])
    if kind != "flat":
        from shapely.geometry import Polygon
        rect = Polygon(pts).minimum_rotated_rectangle
        pts = _ccw(list(rect.exterior.coords)[:-1])
    return [[round(p[0], 4), round(p[1], 4)] for p in pts]


# ---- car ramps: walls and beams stop at the ramp's slab -----------------------------
class _Ramp:
    """A built ramp in absolute heights: ``doc["_ramps"]`` items are
    {"sections": [[a, b]…], "zs": [z of each section's top], "t"}."""

    def __init__(self, r):
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        self.secs = [(tuple(a), tuple(b)) for a, b in r["sections"]]
        self.zs = [float(z) for z in r["zs"]]
        self.t = float(r.get("t", 0.2))
        self.quads = [Polygon([a, b, d, c]).buffer(0)
                      for (a, b), (c, d) in zip(self.secs, self.secs[1:])]
        self.poly = unary_union(self.quads) if self.quads else None
        self.mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                     for a, b in self.secs]

    def top_at(self, p):
        """The ramp's driving surface over ``p`` (None: not over it)."""
        from shapely.geometry import Point
        pt = Point(p)
        for i, q in enumerate(self.quads):
            if q.buffer(0.02).contains(pt):
                m0, m1 = self.mids[i], self.mids[i + 1]
                dx, dy = m1[0] - m0[0], m1[1] - m0[1]
                L2 = dx * dx + dy * dy or 1e-9
                f = ((p[0] - m0[0]) * dx + (p[1] - m0[1]) * dy) / L2
                f = min(max(f, 0.0), 1.0)
                return self.zs[i] + (self.zs[i + 1] - self.zs[i]) * f
        return None


def _ramps(doc):
    out = []
    for r in doc.get("_ramps") or []:
        try:
            rr = _Ramp(r)
            if rr.poly is not None and not rr.poly.is_empty:
                out.append(rr)
        except Exception:  # noqa: BLE001
            continue
    return out


def _wall_under_ramps(w, ramps, bot, top, step=0.4):
    """A straight wall under / over a car ramp in pieces along it, each
    with its own bottom and top: stopping under the ramp's soffit (or
    standing on its driving surface) — [(s0, s1, bot, top)] along the
    wall's line, or None when no ramp crosses it."""
    from shapely.geometry import LineString
    if w.get("kind", "line") != "line" or w.get("rail"):
        return None
    a, b = tuple(w["a"]), tuple(w["b"])
    L = math.dist(a, b)
    if L < 0.05:
        return None
    line = LineString([a, b]).buffer(float(w["t"]) / 2, cap_style=2)
    hit = [r for r in ramps if r.poly.intersects(line)]
    if not hit:
        return None
    n = max(1, int(math.ceil(L / step)))
    segs = []
    changed = False
    for k in range(n):
        s0, s1 = L * k / n, L * (k + 1) / n
        lo, hi = bot, top
        for sm in (s0, (s0 + s1) / 2, s1):
            p = (a[0] + (b[0] - a[0]) * sm / L, a[1] + (b[1] - a[1]) * sm / L)
            for r in hit:
                zt = r.top_at(p)
                if zt is None:
                    continue
                soff = zt - r.t
                if bot + 0.05 < soff < top:           # the ramp over it
                    hi = min(hi, soff)
                    changed = True
                elif bot - 6.0 < zt <= bot + 0.05 and zt < bot - 0.02:
                    lo = min(lo, zt)                  # on the ramp below
                    changed = True
        segs.append([s0, s1, lo, hi])
    if not changed:
        return None
    merged = []                                       # equal runs joined
    for sg in segs:
        if merged and abs(merged[-1][2] - sg[2]) < 1e-3 and \
                abs(merged[-1][3] - sg[3]) < 1e-3:
            merged[-1][1] = sg[1]
        else:
            merged.append(sg)
    return [tuple(m) for m in merged]


# ---- everything, with its faces ----------------------------------------------------
def build(doc: dict, elevations) -> list[dict]:
    """[{"kind", "id", "name", "level", "faces"}] for every wall and
    structural element of the building, at its true heights."""
    info = levels_info(doc, elevations)
    out = []
    walls = doc.get("walls") or []
    struct = doc.get("structure") or []
    openings = doc.get("openings") or []
    for lid, li in info.items():
        z0, under = li["z0"], li["under"]
        # walls — cut by their openings
        mine = [_plastered(w, PLASTER(doc)) for w in walls
                if w["level"] == lid]
        ramps = _ramps(doc)
        # a wall a car ramp crosses: in pieces, each stopping under the
        # ramp's soffit (its doors / windows go with the piece they are in)
        if ramps:
            mine2, ops_extra = [], []
            for w in mine:
                b_ = z0 + float(w.get("base", 0.0)) - _down(doc, w, li)
                t_ = under if w.get("height", "level") == "level" \
                    else z0 + float(w["height"])
                try:
                    runs = _wall_under_ramps(w, ramps, b_, t_)
                except Exception:  # noqa: BLE001
                    runs = None
                if not runs:
                    mine2.append(w)
                    continue
                a, b = w["a"], w["b"]
                L = math.dist(a, b)
                # a door / window keeps one piece round it (the lowest top)
                for o in openings:
                    if o["wall"] != w["id"]:
                        continue
                    o0 = float(o["pos"]) - float(o["w"]) / 2 - 0.1
                    o1 = float(o["pos"]) + float(o["w"]) / 2 + 0.1
                    hit_ = [r_ for r_ in runs if r_[1] > o0 and r_[0] < o1]
                    if len(hit_) > 1:
                        j = (min(r_[0] for r_ in hit_),
                             max(r_[1] for r_ in hit_),
                             min(r_[2] for r_ in hit_),
                             min(r_[3] for r_ in hit_))
                        runs = sorted([r_ for r_ in runs if r_ not in hit_] +
                                      [j])
                for k, (s0, s1, lo, hi) in enumerate(runs):
                    if hi - lo < 0.05:
                        continue
                    pa = [a[0] + (b[0] - a[0]) * s0 / L,
                          a[1] + (b[1] - a[1]) * s0 / L]
                    pb = [a[0] + (b[0] - a[0]) * s1 / L,
                          a[1] + (b[1] - a[1]) * s1 / L]
                    pid = f"{w['id']}~{k}"
                    mine2.append(dict(w, id=pid, _orig=w["id"], a=pa, b=pb,
                                      base=lo - z0, height=hi - z0))
                    for o in openings:
                        if o["wall"] == w["id"] and \
                                s0 <= float(o["pos"]) < s1:
                            ops_extra.append(dict(o, wall=pid,
                                                  pos=float(o["pos"]) - s0))
            mine = mine2
            openings = [o for o in openings] + ops_extra
        plans = W.plan(mine)
        cwins: dict = {}
        lifts = doc.get("_door_lift") or {}
        for w in mine:
            pieces = plans.get(w["id"])
            if not pieces:
                continue
            b = z0 + float(w.get("base", 0.0)) - _down(doc, w, li)
            top = under if w.get("height", "level") == "level" \
                else z0 + float(w["height"])
            if top - b < 0.01:
                continue
            # an RCC wall (a hatched shear wall, a lift core) keeps its
            # doors and its lift landing openings; its windows closed
            ops = [o for o in openings if o["wall"] == w["id"]
                   and opening_room(o, w, openings, top - z0) is None
                   and (not w.get("rcc") or o.get("lift")
                        or o.get("kind") in ("door", "void"))]
            if w.get("rail"):                    # a railing, not a wall
                from . import railings as RL
                seg = W.centre(w)
                n_ = 1 if w.get("kind", "line") == "line" else 12
                path = [(*seg.at(k / n_), b) for k in range(n_ + 1)]
                ch = float(w.get("curb_h") or 0.0)
                if ch > 0.01:                    # on its upstand (curb)
                    pl_ = PLASTER(doc)
                    ct = float(w.get("curb_t") or 0.0762) + 2 * pl_
                    cd = float(w.get("curb_d") or 0.0) if pl_ > 0 else 0.0
                    faces = []                   # down over the slab's edge
                    ra = bool(w.get("cj_a"))     # a corner: run on to meet
                    rb = bool(w.get("cj_b"))     # the other upstand full
                    cp = RL._run_on(path, ra and ct / 2, rb and ct / 2)
                    for p_, q_ in zip(cp, cp[1:]):
                        faces += RL._panel(p_, q_, -cd, ch, ct, RL.MASONRY)
                    path = [(x, y, z + ch) for x, y, z in path]
                    faces += RL.faces(path, max(top - b - ch, 0.3), w["rail"],
                                      float(w["t"]),
                                      no_post=(bool(w.get("np_a")),
                                               bool(w.get("np_b"))),
                                      run_on=(ra, rb))
                else:
                    faces = RL.faces(path, top - b, w["rail"], float(w["t"]),
                                     no_post=(bool(w.get("np_a")),
                                              bool(w.get("np_b"))),
                                     run_on=(bool(w.get("cj_a")),
                                             bool(w.get("cj_b"))))
            elif w.get("type") == "curtain":       # glass on a grid
                seg = W.centre(w)
                # standing on the finished floor (its doors on their
                # thresholds), not on the slab under the finish
                lft_ = [_lifted(o, lifts) for o in ops]
                fin_ = float(doc.get("_fin_t", 0.0) or 0.0)
                # its doors' thresholds set the finished floor it stands on
                for o in ops:
                    if o.get("id") in lifts:
                        fin_ = max(fin_, float(lifts[o["id"]]))
                bcw = max(b, z0 + fin_)
                faces = curtain_wall(w, seg, lft_, z0, bcw, top)
                if bcw - b > 0.01:       # the wall under it (a plinth down
                    for pc in pieces:    # through the platform, the slab's
                        faces += W.solid(pc, b, bcw)       # edge) — solid
                for o in ops:
                    parts = opening_parts(_lifted(o, lifts), seg, z0)
                    if parts:
                        out.append({"kind": "opening", "id": o["id"],
                                    "name": o["name"], "level": lid,
                                    "okind": o["kind"], "faces": parts})
            elif w.get("cwin") and w.get("kind", "line") == "line":
                # a leg of a corner window: the wall under its sill and
                # over its head; the window (one, round the corner) below
                zs = min(max(z0 + float(w.get("cw_low", 0.9)), b), top)
                zt = min(max(zs + float(w.get("cwin_h", 1.2)), zs), top)
                faces = []
                for pc in pieces:
                    if zs - b > 0.01:
                        faces += W.solid(pc, b, zs)
                    if top - zt > 0.01:
                        faces += W.solid(pc, zt, top)
                cwins.setdefault(w["cwin"], []).append((w, zs, zt))
            elif ops:
                seg = W.centre(w)
                faces = [f for pc in pieces
                         for f in wall_with_openings(pc, seg, ops, z0, b,
                                                     top)]
                for o in ops:                # a round hole: the wall back
                    if o.get("shape") == "round":    # round it
                        try:
                            faces += round_infill(w, seg, o, z0)
                        except Exception:  # noqa: BLE001
                            pass
                for o in ops:
                    parts = opening_parts(
                        dict(_lifted(o, lifts), _t=float(w["t"])), seg, z0)
                    if parts:
                        out.append({"kind": "opening", "id": o["id"],
                                    "name": o["name"], "level": lid,
                                    "okind": o["kind"], "faces": parts})
            else:
                faces = [f for pc in pieces for f in W.solid(pc, b, top)]
            # the plaster carried on up over the slab's edge (the wall
            # itself stops under the slab, attached to it)
            if False and w.get("_pl"):          # (the slab's band does it)
                faces = faces + _plaster_skin(w, pieces, PLASTER(doc), top,
                                              z0 + li["height"] - 0.001)
            out.append({"kind": "wall", "id": w.get("_orig", w["id"]),
                        "name": w["name"], "level": lid, "faces": faces})
        if doc.get("_merge_walls"):     # the floor's walls as ONE solid
            try:
                _merge_level(doc, lid, li, mine, plans, openings, out, z0,
                             under)
            except Exception:  # noqa: BLE001
                import traceback
                traceback.print_exc()
        for cid, legs in cwins.items():
            try:
                fs = corner_window_faces(legs)
            except Exception:  # noqa: BLE001
                fs = []
            if fs:
                nm = next((str(w.get("name", "")) for w, _a, _b in legs),
                          "Corner window")
                out.append({"kind": "opening", "id": "cw-" + cid,
                            "name": nm.rsplit(" ·", 1)[0], "level": lid,
                            "okind": "window", "faces": fs})
        els = [e for e in struct if e["level"] == lid and why_not(e) is None]
        # the columns run on through the floor slab they stand on (and
        # the slab cast over them), the slab cut round them: no slab edge
        # drawn across a column in the elevations
        thru = bool(doc.get("_col_thru", True))
        col_cut = []
        floor_s, top_s = [], []
        if thru:
            try:
                from shapely.geometry import Polygon as _Pg, Point as _Pt
                for s_ in els:
                    if s_["type"] != "slab" or s_.get("grade") or \
                            s_.get("zone") or s_.get("user") or \
                            s_.get("skip"):
                        continue
                    pg_ = _Pg([tuple(p) for p in s_["corners"]]).buffer(0)
                    if s_.get("top"):
                        top_s.append((pg_, float(s_["t"])))
                    elif not s_.get("roof"):
                        floor_s.append((pg_, float(s_["t"])))
            except Exception:  # noqa: BLE001
                floor_s, top_s = [], []
        # columns
        for c in (e for e in els if e["type"] == "column"):
            top = (under if c.get("height", "level") == "level"
                   else z0 + float(c["height"])) - SHRINK
            if thru and abs(float(c.get("base", 0.0) or 0.0)) < 1e-6:
                try:
                    pt_ = _Pt(*column_outline(c, 0.0)[0])
                    ctr_ = _Pg(column_outline(c, 0.0)).centroid
                    for pg_, t_ in floor_s:
                        if pg_.buffer(0.05).contains(ctr_):
                            col_cut.append({"corners": [list(q) for q in
                                                        column_outline(c,
                                                                       0.0)],
                                            "_floor": True})
                            c = dict(c, _bot=-t_)
                            break
                    if c.get("height", "level") == "level":
                        for pg_, t_ in top_s:
                            if pg_.buffer(0.05).contains(ctr_):
                                col_cut.append({"corners": [
                                    list(q) for q in column_outline(c, 0.0)],
                                    "_top": True})
                                top = under + t_ - SHRINK
                                break
                except Exception:  # noqa: BLE001
                    pass
            sh = FIT_SHRINK if c.get("fit") else SHRINK
            piece = {"outer": _ccw(column_outline(c, sh)), "holes": []}
            bot = z0 + float(c.get("base", 0.0)) + SHRINK   # its base
            if abs(float(c.get("base", 0.0) or 0.0)) < 1e-6:
                # down as the walls go (on the ground: to the outside
                # floor / the ground — a porch column stands on it)
                bot -= _down(doc, {"base": 0.0}, li)
            if c.get("_bot"):          # on down through its floor slab
                bot = min(bot, z0 + float(c["_bot"]) + SHRINK)
            if top - bot < 0.05:
                continue
            out.append(dict(_el(c, lid, W.solid(piece, bot, top)),
                            inwall=in_one_wall(c, mine)))
        # lift cores: RCC walls round the shafts, full height, as columns
        for c in (e for e in els if e["type"] == "core"):
            top = (under if c.get("height", "level") == "level"
                   else z0 + float(c["height"])) - SHRINK
            bot = z0 + float(c.get("base", 0.0)) + SHRINK
            if top - bot < 0.05:
                continue
            piece = {"outer": _ccw([tuple(p) for p in c["corners"]]),
                     "holes": [list(reversed(_ccw([tuple(p) for p in h])))
                               for h in c.get("holes") or []]}
            faces = W.solid(piece, bot, top)
            for dr in c.get("doors") or []:
                faces += lift_door(dr, bot, top)
            out.append(_el(c, lid, faces))
        # beams: joined among themselves like walls
        beams = [e for e in els if e["type"] == "beam"]
        if ramps and beams:     # no beam through a car ramp: cut round it
            from shapely.geometry import LineString
            btop = under - SHRINK
            nb = []
            for e in beams:
                bbot = btop - float(e["h"])
                L_ = LineString([tuple(e["a"]), tuple(e["b"])])
                cut_ = None
                for r in ramps:
                    zlo, zhi = min(r.zs) - r.t, max(r.zs)
                    if zhi > bbot and zlo < btop and r.poly.intersects(
                            L_.buffer(float(e["w"]) / 2)):
                        g_ = r.poly.buffer(0.05)
                        cut_ = g_ if cut_ is None else cut_.union(g_)
                if cut_ is None:
                    nb.append(e)
                    continue
                rest = L_.difference(cut_)
                for k, g in enumerate(getattr(rest, "geoms", [rest])):
                    if g.geom_type == "LineString" and g.length > 0.3:
                        c_ = list(g.coords)
                        nb.append(dict(e, id=f"{e['id']}~{k}", _orig=e["id"],
                                       a=list(c_[0]), b=list(c_[-1])))
            beams = nb
        bplans = W.plan([as_wall(e, shrink=FIT_SHRINK if e.get("fit")
                                 else SHRINK) for e in beams])
        for e in beams:
            top = under - SHRINK
            bot = top - float(e["h"]) + 2 * SHRINK
            el_ = _el(e, lid, [f for pc in bplans.get(e["id"], ())
                               for f in W.solid(pc, bot, top)])
            if e.get("_orig"):
                el_["id"] = e["_orig"]
            out.append(dict(el_, inwall=in_one_wall(e, mine)))
        # slabs
        slabs_ = [e for e in els if e["type"] == "slab" and not e.get("skip")]
        ids_ = [lv["id"] for lv in doc["levels"]]
        k_ = ids_.index(lid) if lid in ids_ else -1
        nxt = ids_[k_ + 1] if 0 <= k_ < len(ids_) - 1 else None
        down_cut = []
        if doc.get("_walls_down"):         # the walls standing on the slab
            try:
                wp_ = W.plan([w for w in mine if not w.get("rail") and abs(
                    float(w.get("base", 0.0) or 0.0)) < 1e-6
                    and W.why_not(w) is None])
                down_cut = [{"corners": [list(q) for q in pc["outer"]]}
                            for pcs in wp_.values() for pc in pcs]
            except Exception:  # noqa: BLE001
                down_cut = []
        for s in slabs_:
            if s.get("grade"):
                continue          # on the ground: its finish only
            if s.get("top"):
                # the slab OVER the floor (as cast on site): on its walls,
                # under the next floor's open floor; the next floor's
                # sunk / raised parts and level zones cut out of it
                top = z0 + li["height"] + (main_slab_offset(doc, nxt)
                                           if nxt else 0.0)
                bot = top - float(s["t"])
                cut = floor_parts(doc, nxt) if nxt else []
            else:
                # the floor slab: its top at the level's floor; the roof
                # slab (on top of the top floor): its top at the level's top
                base_top = z0 + (li["height"] if s.get("roof") else 0.0)
                top = base_top + float(s.get("offset", 0.0))
                bot = top - float(s["t"])
                if s.get("user") and float(s.get("offset", 0.0)) > 0:
                    bot = base_top - float(s["t"])  # raised: filled down
                # the parts sunk / raised by hand: out of the slab round them
                cut = [] if s.get("user") or s.get("zone") else \
                    [u for u in slabs_ if u.get("user")
                     and bool(u.get("roof")) == bool(s.get("roof"))]
            parts_ = [{"outer": _ccw([tuple(p) for p in s["corners"]]),
                       # openings wound the other way round
                       "holes": [list(reversed(_ccw([tuple(p) for p in h])))
                                 for h in s.get("holes") or []]}]
            if down_cut and not s.get("top") and not s.get("roof") and \
                    not s.get("zone"):
                cut = list(cut) + down_cut
            if col_cut and not s.get("zone") and not s.get("user") and \
                    not s.get("roof"):
                cc_ = [x for x in col_cut
                       if x.get("_top" if s.get("top") else "_floor")]
                if cc_:
                    cut = list(cut) + cc_
            if cut:
                parts_ = _minus(s, cut) or parts_
            band_ = []
            if PLASTER(doc) > 0:
                try:                     # plaster on all its edges
                    parts_, band_ = _slab_plaster(s, parts_, PLASTER(doc))
                except Exception:  # noqa: BLE001
                    band_ = []
            faces_ = []
            for piece in parts_:
                faces_ += W.solid(piece, bot, top)
            for piece in band_:
                for f in W.solid(piece, bot, top):
                    lp = f["loop"] if isinstance(f, dict) else f
                    hs = f.get("holes", []) if isinstance(f, dict) else []
                    faces_.append({"loop": lp, "holes": hs,
                                   "color": PLASTER_COLOR})
            out.append(_el(s, lid, faces_))
        # footings: under the slab of their level
        ftop = z0 - li["slab"]
        pads = [e for e in els if e["type"] == "footing"
                and e.get("kind") == "pad"]
        for f in pads:
            piece = {"outer": _ccw(pad_outline(f)), "holes": []}
            out.append(_el(f, lid, W.solid(piece, ftop - float(f["d"]),
                                           ftop)))
        for f in (e for e in els if e["type"] == "footing"
                  and e.get("kind") in ("raft", "combined")):
            piece = {"outer": _ccw([tuple(p) for p in f["corners"]]),
                     "holes": [list(reversed(_ccw([tuple(p) for p in h])))
                               for h in f.get("holes") or []]}
            # a raft 2 mm under the pads' top plane (no flicker where both)
            top_ = ftop - (2 * SHRINK if f["kind"] == "raft" else 0.0)
            out.append(_el(f, lid, W.solid(piece, top_ - float(f["d"]),
                                           top_)))
        strips = [e for e in els if e["type"] == "footing"
                  and e.get("kind") == "strip"]
        splans = W.plan([as_wall(e, shrink=0.0) for e in strips])
        for f in strips:
            # 1 mm under the pads' top: where a strip runs into a pad the
            # two tops would share one plane (and flicker)
            out.append(_el(f, lid, [pc_f for pc in splans.get(f["id"], ())
                                    for pc_f in W.solid(
                                        pc, ftop - float(f["d"]),
                                        ftop - SHRINK)]))
        # roofs: on the top of the level's walls
        wall_t = max((float(w["t"]) for w in mine), default=0.20)
        for r in (e for e in els if e["type"] == "roof"):
            out.append(_el(r, lid, roof_faces(r, under, wall_t)))
    return [e for e in out if e["faces"]]


def hole_place(slabs: list[dict], hole) -> tuple:
    """(slab, reason): the slab an opening drawn at ``hole`` goes
    through — the one that holds it all, clear of its other openings."""
    from shapely.geometry import Polygon
    h = Polygon(hole)
    if not h.is_valid or h.area < 0.01:
        return None, "Too small for an opening"
    for s in slabs:
        outer = Polygon(s["corners"])
        if not outer.is_valid:
            outer = outer.buffer(0)
        if not outer.buffer(1e-6).contains(h):
            continue
        if any(Polygon(o).intersects(h) for o in s.get("holes") or []):
            return None, "It runs into another opening of that slab"
        return s, None
    return None, "Draw the opening inside a slab of this level"


def in_one_wall(e: dict, walls: list[dict]) -> bool:
    """A fitted column, or a beam lying wholly within one wall: it is
    INSIDE the wall — hidden while the walls are shown (its lines showed
    through them in a raking view; nothing of it is to be seen anyway)."""
    if not e.get("fit"):
        return False
    if e["type"] == "column":
        return True                     # fitted = inside by construction
    for w in walls:
        if W.why_not(w) is not None or w.get("kind", "line") != "line":
            continue
        s = W.centre(w)
        if all((-1e-6 <= f <= 1 + 1e-6) and
               abs(off) <= float(w["t"]) / 2 + FIT_TOL
               for f, off in (s.project(e["a"]), s.project(e["b"]))):
            return True
    return False


def _el(e: dict, lid: str, faces) -> dict:
    return {"kind": e["type"], "id": e["id"], "name": e["name"],
            "level": lid, "faces": faces}


def _merge_level(doc, lid, li, mine, plans, openings, out, z0, under):
    """The plain walls of a floor (solid, straight or curved, their doors
    and windows square-headed) put into one solid per height — on the
    CAD's own wall outline where it has one: no joints between walls."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from . import wallmerge as WM
    groups = {}
    for w in mine:
        if w.get("rail") or w.get("type") == "curtain" or w.get("cwin") \
                or w.get("_orig"):
            continue
        pieces = plans.get(w["id"])
        if not pieces:
            continue
        b = z0 + float(w.get("base", 0.0)) - _down(doc, w, li)
        top = under if w.get("height", "level") == "level" \
            else z0 + float(w["height"])
        if top - b < 0.05:
            continue
        ops = [o for o in openings if o["wall"] == w["id"]
               and opening_room(o, w, openings, top - z0) is None
               and (not w.get("rcc") or o.get("lift")
                    or o.get("kind") in ("door", "void"))]
        if any(str(o.get("head") or "flat").startswith("arch") or
               o.get("shape") == "round" for o in ops):
            continue
        if ops and w.get("kind", "line") != "line":
            continue
        try:
            poly = unary_union([Polygon(pc["outer"], pc.get("holes") or [])
                                .buffer(0) for pc in pieces])
        except Exception:  # noqa: BLE001
            continue
        key = (round(b, 3), round(top, 3))
        groups.setdefault(key, []).append((w, poly, ops))
    if not groups:
        return
    cad = WM.region_of((doc.get("_wall_outline") or {}).get(lid))
    merged_ids = set()
    k = 0
    for (b, top), items in groups.items():
        if len(items) < 2:
            continue
        model = unary_union([pl for _w, pl, _o in items])
        fps = []
        for w, _pl, ops in items:
            if not ops:
                continue
            seg = W.centre(w)
            for o in ops:
                zs = z0 + float(o.get("sill", 0.0))
                zt = zs + float(o["h"])
                fps.append((WM.footprint(w, o, seg), zs, zt))
        U = model
        if cad is not None and not cad.is_empty:
            try:
                near = cad.intersection(model.buffer(0.3, join_style=2))
                cb = cad.buffer(0.35, join_style=2)
                # a wall the CAD draws (a band along most of it): its band
                # only, as drawn; a wall the CAD closes no band for: the
                # wall read (less where a band is)
                rest = [pl.difference(cad.buffer(0.02, join_style=2))
                        for _w, pl, _o in items
                        if pl.intersection(cb).area < 0.6 * pl.area]
                over = []                # over / under the openings: the
                for w, _pl, ops in items:    # CAD's band carried across
                    if not ops:
                        continue
                    seg = W.centre(w)
                    for o in ops:
                        span = WM.footprint(w, o, seg, extra=0.5)
                        wide = WM.footprint(dict(w), dict(
                            o, w=float(o["w"]) + 0.6), seg, extra=0.5)
                        side = cad.intersection(wide)
                        if not side.is_empty and side.area > 0.01:
                            over.append(side.convex_hull.intersection(span))
                        else:
                            over.append(WM.footprint(w, o, seg)
                                        .intersection(model))
                U = unary_union([near] + rest + over)
                # the slits under 0.2 m between two bands closed
                U = U.buffer(0.1, join_style=2).buffer(-0.1, join_style=2)
            except Exception:  # noqa: BLE001
                U = model
        faces = WM.merged_faces(U, fps, b, top)
        if not faces:
            continue
        ids = [w["id"] for w, _pl, _o in items]
        merged_ids.update(ids)
        out.append({"kind": "wall", "id": f"merged|{lid}|{k}",
                    "name": "Walls", "level": lid, "faces": faces,
                    "merged": ids})
        k += 1
    if merged_ids:
        out[:] = [e for e in out if not (e.get("kind") == "wall" and
                                         e.get("id") in merged_ids)]
