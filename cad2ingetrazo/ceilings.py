# SPDX-License-Identifier: GPL-3.0-or-later
"""False ceilings: a ceiling in every room of a level (or the rooms
picked), hung at a height over the floor (8'-0" by default), of a type —
gypsum board, acoustic tiles on a grid, POP, timber, PVC, metal strips.

``doc["ceilings"]`` = {level id: {"type", "h", "rooms": {room key:
{"type", "h"} | {"off": True}}}} — a level's ceiling and the rooms that
differ (another type or height, or none).
"""
from __future__ import annotations

#: key → (label, thickness m, colour rgba, grid m (0 = plain), grid colour)
TYPES = [
    ("gypsum", "Gypsum board (plain)", 0.0125, (0.96, 0.96, 0.95, 1.0), 0.0,
     None),
    ("tiles", "Acoustic tiles 2'×2' on a T-grid", 0.016,
     (0.93, 0.93, 0.91, 1.0), 0.6096, (0.70, 0.71, 0.72, 1.0)),
    ("pop", "Plaster of Paris (POP)", 0.020, (0.98, 0.97, 0.94, 1.0), 0.0,
     None),
    ("wood", "Timber panels", 0.018, (0.62, 0.45, 0.30, 1.0), 0.1524,
     (0.48, 0.34, 0.22, 1.0)),
    ("pvc", "PVC panels", 0.010, (0.95, 0.95, 0.97, 1.0), 0.2032,
     (0.82, 0.83, 0.85, 1.0)),
    ("metal", "Metal linear strips", 0.015, (0.80, 0.81, 0.83, 1.0), 0.1016,
     (0.55, 0.56, 0.58, 1.0)),
]
BY = {t[0]: t for t in TYPES}
DEFAULT_H = 2.4384          # 8'-0" over the floor


def label(kind: str) -> str:
    return BY.get(kind, BY["gypsum"])[1]


def set_level(doc, lid, kind="gypsum", h=DEFAULT_H) -> None:
    doc.setdefault("ceilings", {})[lid] = {
        "type": kind if kind in BY else "gypsum",
        "h": round(min(max(float(h), 2.0), 8.0), 4),
        "rooms": (doc.get("ceilings", {}).get(lid) or {}).get("rooms", {})}


def remove_level(doc, lid) -> None:
    (doc.get("ceilings") or {}).pop(lid, None)


def room_ceiling(doc, lid, rkey) -> dict | None:
    """{"type", "h"} of a room's ceiling, or None (no ceiling there)."""
    c = (doc.get("ceilings") or {}).get(lid)
    r = ((c or {}).get("rooms") or {}).get(rkey)
    if r is not None:
        if r.get("off"):
            return None
        return {"type": r.get("type") or (c or {}).get("type", "gypsum"),
                "h": float(r.get("h") or (c or {}).get("h", DEFAULT_H))}
    if c is None:
        return None
    return {"type": c.get("type", "gypsum"), "h": float(c.get("h",
                                                              DEFAULT_H))}


def faces(poly, z, kind) -> list:
    """[(faces, colour)] of a ceiling of ``kind`` over ``poly`` (shapely),
    its underside at ``z``: the board, and the grid / joints seen under
    it as thin strips."""
    from .engine import walls as W
    _k, _lab, t, col, grid, gcol = BY.get(kind, BY["gypsum"])
    out = []
    g = poly.buffer(-0.005, join_style=2)
    for p in getattr(g, "geoms", [g]):
        if p.is_empty or p.area < 0.2:
            continue
        outer = [tuple(c) for c in list(p.exterior.coords)[:-1]]
        holes = [[tuple(c) for c in list(h.coords)[:-1]]
                 for h in p.interiors]
        out.append((W.solid({"outer": _ccw(outer),
                             "holes": [list(reversed(_ccw(h)))
                                       for h in holes]}, z, z + t), col))
        if grid > 0 and gcol is not None:
            out.append((_grid(p, z, grid), gcol))
    return out


def _grid(p, z, step) -> list:
    """Thin strips under the board along x (and y for tiles): the T-grid,
    the panel joints."""
    from shapely.geometry import box
    x0, y0, x1, y1 = p.bounds
    fs = []
    w = 0.012

    def strip(b):
        g = p.intersection(b)
        for q in getattr(g, "geoms", [g]):
            if q.geom_type != "Polygon" or q.area < 1e-4:
                continue
            pts = [tuple(c) for c in list(q.exterior.coords)[:-1]]
            pts = _ccw(pts)
            fs.append({"loop": [(x, y, z - 0.003) for x, y in
                                reversed(pts)], "holes": []})
    x = x0 + step
    while x < x1:
        strip(box(x - w / 2, y0, x + w / 2, y1))
        x += step
    if step >= 0.5:                       # tiles: both ways
        y = y0 + step
        while y < y1:
            strip(box(x0, y - w / 2, x1, y + w / 2))
            y += step
    return fs


def _ccw(loop):
    a = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                  for p, q in zip(loop, loop[1:] + loop[:1]))
    return list(loop) if a >= 0 else list(reversed(loop))


def build(doc, z_of, room_key) -> list:
    """[(level id, room name, kind, h, [(faces, colour)])] for every room
    with a ceiling."""
    from .engine import spaces
    arch = doc["arch"]
    out = []
    own_lids = {r["level"] for r in arch.get("rooms") or []
                if r.get("ceiling") in BY}
    for lid in list((doc.get("ceilings") or {}).keys()) + \
            sorted(own_lids - set((doc.get("ceilings") or {}).keys())):
        if lid not in z_of:
            continue
        for room in spaces.of_level(arch, lid):
            if room["area"] < 1.0:
                continue
            c = room_ceiling(doc, lid, room_key(lid, room))
            rec = room.get("rec") or {}
            own = rec.get("ceiling")
            if own == "none":
                c = None
            elif own in BY:
                lvc = (doc.get("ceilings") or {}).get(lid) or {}
                c = {"type": own,
                     "h": float(rec.get("ceiling_h") or lvc.get("h",
                                                              DEFAULT_H))}
            elif c is not None and rec.get("ceiling_h"):
                c = dict(c, h=float(rec["ceiling_h"]))
            if c is None:
                continue
            fs = faces(room["poly"], z_of[lid] + c["h"], c["type"])
            if fs:
                out.append((lid, room["name"], c["type"], c["h"], fs))
    return out
