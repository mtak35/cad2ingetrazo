# SPDX-License-Identifier: GPL-3.0-or-later
"""Excavations and fills in the plot — ArchXQ's terrain cuts, for the
CAD2IngeTrazo model: a pit dug for the basement (or the footings), a
ramp's cutting, a raised platform.

A record in ``doc["arch"]["digs"]`` (ArchXQ's own format, so a file goes
both ways):
    {"id", "name", "kind": "cut" | "fill", "corners": [[x, y]…] (CCW),
     "bottom": {"mode": "depth", "d": 3.0}            (under the ground)
             | {"mode": "height", "h": 1.0}           (a fill: over it)
             | {"mode": "level", "level": id, "offset": -0.30}
             | {"mode": "elev", "z": -3.0},
     "angles": [side angle ° per side] (90 = vertical / shored)}

The ground is the plot's (``ground`` z, the plinth under the ground
floor). A cut opens the ground plate and goes down to its bottom with
sides at their angle (the bottom smaller); a fill stands on the ground,
its sides sloping out. Pure: faces as the engine makes them.
"""
from __future__ import annotations

import math

EARTH = (0.55, 0.42, 0.30, 1.0)            # the pit's sides
EARTH_FLOOR = (0.62, 0.50, 0.37, 1.0)      # its floor
FILL = (0.58, 0.66, 0.45, 1.0)             # a fill's top (grassed)
FILL_SIDE = (0.60, 0.50, 0.36, 1.0)
BELOW_FLOOR = -0.30                        # a basement's pit: under its slab

SHAPES = [("footprint", "Building footprint + working space"),
          ("buildable", "Buildable area (setback line)"),
          ("plot", "Whole plot (inset by the margin)"),
          ("rect", "Rectangle W × D at X, Y (the plot's fields)"),
          ("selected", "Selected slab / room / ramp outline")]
BOTTOMS = [("level", "Under the lowest level (its slab − margin)"),
           ("depth", "Depth below the ground"),
           ("elev", "Elevation (absolute)")]


def _area(pts) -> float:
    return 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                     for p, q in zip(pts, pts[1:] + pts[:1]))


def ccw(pts) -> list:
    pts = [(float(p[0]), float(p[1])) for p in pts]
    return pts if _area(pts) >= 0 else pts[::-1]


def offset(pts, s) -> list | None:
    """The outline moved ``s`` inward (s < 0: outward), each side kept
    parallel — a corner where its two moved sides meet. None when the
    outline turns over (the pit too deep for its slopes)."""
    pts = ccw(pts)
    n = len(pts)
    if abs(s) < 1e-9:
        return pts
    lines = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        L = math.dist(a, b) or 1e-9
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        nrm = (-u[1], u[0])                  # inward for a CCW outline
        lines.append(((a[0] + nrm[0] * s, a[1] + nrm[1] * s), u))
    out = []
    for i in range(n):
        (p, d), (q, e) = lines[i - 1], lines[i]
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-6:                   # straight on: the point moved
            out.append(q)
            continue
        t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
        out.append((p[0] + d[0] * t, p[1] + d[1] * t))
    try:
        from shapely.geometry import Polygon
        pg = Polygon(out)
        if not pg.is_valid or pg.area < 0.05 or \
                (_area(out) > 0) != (_area(pts) > 0):
            return None
        if s > 0 and pg.area > Polygon(pts).area:
            return None
    except Exception:  # noqa: BLE001
        pass
    return out


def lowest_level(arch) -> tuple:
    """(id, elevation) of the lowest level."""
    el = _elev(arch)
    i = min(range(len(arch["levels"])), key=lambda k: el[k])
    return arch["levels"][i]["id"], el[i]


def _elev(arch):
    from . import project as PJ
    return PJ.elevations(arch)


def bottom_z(dig, doc, ground: float) -> float:
    """The dig's bottom (a cut) or top (a fill) elevation."""
    b = dig.get("bottom") or {}
    mode = b.get("mode", "depth")
    if mode == "depth":
        return ground - float(b.get("d", 3.0))
    if mode == "height":
        return ground + float(b.get("h", 1.0))
    if mode == "level":
        arch = doc["arch"]
        el = _elev(arch)
        ids = [lv["id"] for lv in arch["levels"]]
        lid = b.get("level")
        if lid in ids:
            return el[ids.index(lid)] + float(b.get("offset", BELOW_FLOOR))
        return ground - 3.0
    return float(b.get("z", ground - 3.0))


def _run(depth, ang) -> float:
    """How far a side at ``ang`` ° runs in plan over ``depth``."""
    ang = min(max(float(ang), 5.0), 90.0)
    return 0.0 if ang >= 89.99 else abs(depth) / math.tan(math.radians(ang))


def _foot(dig, doc, ground):
    """(top outline, foot outline, z top, z foot): for a cut the ground
    outline and the smaller floor; for a fill its top and its wider foot
    on the ground."""
    top = ccw(dig["corners"])
    zb = bottom_z(dig, doc, ground)
    ang = min((dig.get("angles") or [90.0]) or [90.0])
    run = _run(zb - ground, ang)
    if dig.get("kind") == "fill":
        foot = offset(top, -run) if run else top
        return top, foot or top, zb, ground
    low = offset(top, run) if run else top
    if low is None:                          # too deep for its slopes
        low = offset(top, 0.0)
    return top, low, ground, zb


def faces(dig, doc, ground: float) -> list:
    """[(face, colour)] of a cut (floor + sides, seen from the pit) or a
    fill (top + sides)."""
    top, low, za, zb = _foot(dig, doc, ground)
    out = []
    fill = dig.get("kind") == "fill"
    if fill:
        # the top (up), the sides sloping down and out to the ground
        out.append(({"loop": [(x, y, za) for x, y in top], "holes": []},
                    FILL))
        n = len(top)
        for i in range(n):
            a, b = top[i], top[(i + 1) % n]
            c, d = low[(i + 1) % n], low[i]
            out.append(({"loop": [(a[0], a[1], za), (d[0], d[1], zb),
                                  (c[0], c[1], zb), (b[0], b[1], za)],
                         "holes": []}, FILL_SIDE))
        return out
    if zb >= za - 0.01:
        return []
    # the floor, facing up; the sides from the ground's edge down to it,
    # facing into the pit
    out.append(({"loop": [(x, y, zb) for x, y in low], "holes": []},
                EARTH_FLOOR))
    n = len(top)
    for i in range(n):
        a, b = top[i], top[(i + 1) % n]
        c, d = low[(i + 1) % n], low[i]
        out.append(({"loop": [(a[0], a[1], za), (b[0], b[1], za),
                              (c[0], c[1], zb), (d[0], d[1], zb)],
                     "holes": []}, EARTH))
    return out


def volume(dig, doc, ground: float) -> float:
    """m³ dug (a cut) or brought in (a fill): the prismoid's rule."""
    from shapely.geometry import Polygon
    top, low, za, zb = _foot(dig, doc, ground)
    h = abs(za - zb)
    if h < 1e-6:
        return 0.0
    a0, a1 = Polygon(top).area, Polygon(low).area
    ang = min((dig.get("angles") or [90.0]) or [90.0])
    run = _run(h, ang)
    mid = offset(top, (run / 2) * (-1 if dig.get("kind") == "fill" else 1)) \
        if run else top
    am = Polygon(mid).area if mid else (a0 + a1) / 2
    return h / 6.0 * (a0 + 4 * am + a1)


def ground_holes(doc) -> list:
    """The cuts' outlines at the ground (to open the plot's plate)."""
    return [ccw(d["corners"]) for d in doc["arch"].get("digs") or []
            if d.get("kind") != "fill" and len(d.get("corners") or []) >= 3]


def new(doc, corners, kind="cut", bottom=None, angle=90.0) -> dict:
    """A new dig in ``doc`` (its next «Excavation N» / «Fill N»)."""
    from .engine import model as M
    arch = doc["arch"]
    arch.setdefault("digs", [])
    base = "Fill" if kind == "fill" else "Excavation"
    d = M.new_dig(arch["digs"], [list(p) for p in ccw(corners)],
                  bottom or {"mode": "depth", "d": 3.0}, base, kind)
    d["angles"] = [float(angle)] * len(d["corners"])
    arch["digs"].append(d)
    return d


def outline_of(doc, shape, margin=1.0, rect=None, selected=None):
    """The outline a new dig takes: [(x, y)…] or (None, why)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    arch = doc["arch"]
    plot = arch.get("plot")
    if shape == "rect":
        if not rect:
            return None, "give the rectangle's size and corner"
        x, y, w, dd, rot = rect
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        pts = [(0, 0), (w, 0), (w, dd), (0, dd)]
        return [(x + px * c - py * s, y + px * s + py * c)
                for px, py in pts], None
    if shape == "selected":
        if not selected or len(selected) < 3:
            return None, "select a slab, a room or a ramp in the model first"
        g = Polygon(selected).buffer(margin, join_style=2)
        return [p for p in list(g.exterior.coords)[:-1]], None
    if shape in ("plot", "buildable"):
        if not plot:
            return None, "make the plot first"
        if shape == "buildable":
            from .engine import plotgeo
            _r, _d, area = plotgeo.setbacks_of(plot)
            if not area:
                return None, "apply the setbacks first"
            return [tuple(p) for p in area], None
        g = Polygon(plot["corners"]).buffer(-max(margin, 0.05),
                                            join_style=2)
        if g.is_empty or g.geom_type != "Polygon":
            return None, "the margin leaves nothing of the plot"
        return [p for p in list(g.exterior.coords)[:-1]], None
    # the building's footprint: the lowest level's walls, closed, and the
    # working space round them
    from .engine import walls as W
    lid, _z = lowest_level(arch)
    walls = [w for w in arch["walls"] if w["level"] == lid
             and W.why_not(w) is None]
    if not walls:
        return None, "the lowest level has no walls yet"
    pcs = [pc for ps in W.plan(walls).values() for pc in ps]
    u = unary_union([Polygon(pc["outer"], pc["holes"]).buffer(0)
                     for pc in pcs])
    u = u.buffer(1.5, join_style=2).buffer(-1.5, join_style=2)
    g = max(getattr(u, "geoms", [u]), key=lambda q: q.area)
    g = Polygon(g.exterior).buffer(margin, join_style=2).simplify(0.02)
    if plot:                                  # never past the plot's edge
        gp = g.intersection(Polygon(plot["corners"]).buffer(0))
        if not gp.is_empty:
            g = max(getattr(gp, "geoms", [gp]), key=lambda q: q.area)
    return [p for p in list(g.exterior.coords)[:-1]], None


def default_bottom(doc) -> dict:
    """Under the lowest level when it is under the ground, else 1.5 m (the
    footings' trenches)."""
    from . import project as PJ
    arch = doc["arch"]
    lid, z = lowest_level(arch)
    ground = PJ.plot_top(doc)
    if z < ground - 0.5:
        return {"mode": "level", "level": lid, "offset": BELOW_FLOOR}
    return {"mode": "depth", "d": 1.5}


def describe(dig, doc, ground) -> str:
    from .host import len_txt
    z = bottom_z(dig, doc, ground)
    v = volume(dig, doc, ground)
    what = "top" if dig.get("kind") == "fill" else "bottom"
    ang = min((dig.get("angles") or [90.0]) or [90.0])
    side = "vertical sides" if ang >= 89.99 else f"sides at {ang:.0f}°"
    return f"{dig['name']} · {what} {len_txt(z - ground)} from the ground " \
        f"· {side} · {v:,.0f} m³"
