# SPDX-License-Identifier: GPL-3.0-or-later
"""False ceilings: a ceiling in every room of a level (or the rooms
picked), hung at a height over the floor (8'-0" by default), of a type —
gypsum board, acoustic tiles on a grid, POP, timber, PVC, metal strips.

``doc["ceilings"]`` = {level id: {"type", "h", "rooms": {room key:
{"type", "h"} | {"off": True}}}} — a level's ceiling and the rooms that
differ (another type or height, or none).
"""
from __future__ import annotations

import re

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
    ("mineral", "Mineral fibre tiles 600×600 (Armstrong)", 0.016,
     (0.97, 0.97, 0.96, 1.0), 0.6, (0.88, 0.88, 0.88, 1.0)),
    ("grid24", "Lay-in tiles 2'×4' on a T-grid", 0.016,
     (0.95, 0.95, 0.94, 1.0), 0.6096, (0.72, 0.73, 0.74, 1.0)),
    ("cove", "Gypsum with cove / bulkhead (hidden light)", 0.0125,
     (0.97, 0.97, 0.96, 1.0), 0.0, None),
    ("coffered", "Coffered gypsum", 0.0125, (0.97, 0.96, 0.94, 1.0), 1.2,
     (0.93, 0.92, 0.90, 1.0)),
    ("baffle", "Aluminium baffles", 0.0, (0.82, 0.83, 0.85, 1.0), 0.15,
     (0.78, 0.79, 0.81, 1.0)),
    ("slats", "Timber slats (open)", 0.0, (0.66, 0.48, 0.31, 1.0), 0.1,
     (0.60, 0.43, 0.27, 1.0)),
    ("opencell", "Open-cell metal grid", 0.0, (0.75, 0.76, 0.78, 1.0), 0.1,
     (0.70, 0.71, 0.73, 1.0)),
    ("stretch", "Stretch ceiling (glossy)", 0.005, (0.99, 0.99, 1.0, 1.0),
     0.0, None),
    ("acp", "Aluminium composite panels", 0.006, (0.86, 0.87, 0.88, 1.0),
     1.2192, (0.60, 0.61, 0.63, 1.0)),
]
#: types with no board: strips hung in rows (depth m, width m)
OPEN_KINDS = {"baffle": (0.10, 0.02), "slats": (0.05, 0.04),
              "opencell": (0.05, 0.012)}
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
    if kind in OPEN_KINDS:
        dep, wid = OPEN_KINDS[kind]
        for p in getattr(g, "geoms", [g]):
            if p.is_empty or p.area < 0.2:
                continue
            out.append((_strips(p, z, grid, wid, dep,
                                both=(kind == "opencell")), col))
        return out
    for p in getattr(g, "geoms", [g]):
        if p.is_empty or p.area < 0.2:
            continue
        if kind == "cove":             # a bulkhead band round the room,
            band = p.difference(p.buffer(-0.45, join_style=2))  # lower
            mid = p.buffer(-0.45, join_style=2)
            for q in getattr(band, "geoms", [band]):
                if q.geom_type == "Polygon" and q.area > 0.01:
                    out.append((_slab(q, z - 0.15, z + t), col))
            for q in getattr(mid, "geoms", [mid]):
                if q.geom_type == "Polygon" and q.area > 0.05:
                    out.append((_slab(q, z, z + t), col))
            continue
        if kind == "coffered":         # a board with ribs hung under it
            out.append((_slab(p, z, z + t), col))
            out.append((_strips(p, z, grid, 0.10, 0.12, both=True), gcol))
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


def _slab(p, z0, z1) -> list:
    from .engine import walls as W
    outer = [tuple(c) for c in list(p.exterior.coords)[:-1]]
    holes = [[tuple(c) for c in list(h.coords)[:-1]] for h in p.interiors]
    return W.solid({"outer": _ccw(outer),
                    "holes": [list(reversed(_ccw(h))) for h in holes]},
                   z0, z1)


def _strips(p, z, step, wid, dep, both=False) -> list:
    """Strips ``wid`` wide, ``dep`` deep, every ``step``, hung from z down
    (along x; and along y too with ``both``): baffles, slats, ribs."""
    from shapely.geometry import box
    x0, y0, x1, y1 = p.bounds
    fs = []

    def put(b):
        g = p.intersection(b)
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon" and q.area > 1e-4:
                fs.extend(_slab(q, z - dep, z))
    x = x0 + step / 2
    while x < x1:
        put(box(x - wid / 2, y0, x + wid / 2, y1))
        x += step
    if both:
        y = y0 + step / 2
        while y < y1:
            put(box(x0, y - wid / 2, x1, y + wid / 2))
            y += step
    return fs


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


NO_CEILING = r"BALCON|TERRACE|TERACE|SIT\s*OUT|OPEN|SKY|DUCT|SHAFT|LIFT|" \
    r"ELEV|P\d+\.?CO|VOID|O\.?T\.?S|STAIR"


def _open_air(room, rails) -> bool:
    """A room out in the open (a balcony, a sit-out) or a shaft: no false
    ceiling — by its name, or railed round more than a quarter of it."""
    import re
    if re.search(NO_CEILING, str(room.get("name", "")), re.I):
        return True
    if rails is None or rails.is_empty:
        return False
    try:
        edge = room["poly"].exterior
        return edge.intersection(rails).length > 0.25 * edge.length
    except Exception:  # noqa: BLE001
        return False


def build(doc, z_of, room_key) -> list:
    """[(level id, room name, kind, h, [(faces, colour)])] for every room
    with a ceiling."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    from .engine import spaces
    arch = doc["arch"]
    out = []
    order = sorted(z_of, key=lambda k: z_of[k])

    def wells_over(lid):
        """The openings in the floor over ``lid`` (a stair well, a void):
        no ceiling under them."""
        try:
            from . import project as PJ
            i = order.index(lid)
            if i + 1 >= len(order):
                return None
            up = order[i + 1]
            hs = []
            for s_ in PJ._floor_slabs(doc, up):
                for h in s_.get("holes") or []:
                    try:
                        from shapely.geometry import Polygon as _P
                        hs.append(_P(h).buffer(0))
                    except Exception:  # noqa: BLE001
                        continue
            return unary_union(hs) if hs else None
        except Exception:  # noqa: BLE001
            return None
    own_lids = {r["level"] for r in arch.get("rooms") or []
                if r.get("ceiling") in BY}
    for lid in list((doc.get("ceilings") or {}).keys()) + \
            sorted(own_lids - set((doc.get("ceilings") or {}).keys())):
        if lid not in z_of:
            continue
        wells = wells_over(lid)
        try:
            rails = unary_union([LineString([w["a"], w["b"]]).buffer(0.25)
                                 for w in arch["walls"] if w["level"] == lid
                                 and w.get("rail") and "a" in w]) or None
        except Exception:  # noqa: BLE001
            rails = None
        done_ = []
        for room in spaces.of_level(arch, lid):
            if room["area"] < 1.0:
                continue
            rec_ = room.get("rec") or {}
            if rec_.get("ceiling") not in BY and _open_air(room, rails):
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
            poly = room["poly"]
            if wells is not None and poly.intersects(wells):
                try:
                    poly = poly.difference(wells.buffer(0.05))
                except Exception:  # noqa: BLE001
                    pass
            if poly.is_empty:
                continue
            fs = faces(poly, z_of[lid] + c["h"], c["type"])
            if fs:
                out.append((lid, room["name"], c["type"], c["h"], fs,
                            room_key(lid, room)))
                done_.append(poly)
        try:                 # the rest inside the outside walls (a hall,
            out += _rest(doc, lid, z_of, wells, done_)   # a corridor, a
        except Exception:  # noqa: BLE001                  # lobby…)
            from .host import log_error
            log_error("ceilings._rest")
    return out


def _rest(doc, lid, z_of, wells, done) -> list:
    """The level's ceiling over what its rooms leave inside the outside
    walls (halls and corridors open to one another, a lobby): not over
    the walls, the shafts and wells, nor out on the balconies."""
    lvc = (doc.get("ceilings") or {}).get(lid)
    if not lvc:
        return []
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from . import slabedges as SE
    from .engine import walls as W
    arch = doc["arch"]
    ws = [w for w in arch["walls"] if w["level"] == lid
          and not w.get("rail") and W.why_not(w) is None]
    if not ws:
        return []
    WU = unary_union(SE.wall_polys(ws))
    # (a corridor open at its end to a balcony, up to 4 m: inside)
    close = WU.buffer(2.0, join_style=2).buffer(-2.0, join_style=2)
    inside = unary_union([Polygon(g.exterior) for g in getattr(
        close, "geoms", [close]) if g.geom_type == "Polygon"
        and Polygon(g.exterior).area >= 20.0])
    if inside.is_empty:
        return []
    try:                     # never past the floor's own slab
        fl = unary_union([Polygon(s_["corners"]).buffer(0)
                          for s_ in arch["structure"] if s_["type"] == "slab"
                          and s_["level"] == lid and not s_.get("roof")
                          and not s_.get("zone")])
        if not fl.is_empty:
            inside = inside.intersection(fl)
    except Exception:  # noqa: BLE001
        pass
    cut = [WU.buffer(0.005)]
    if done:
        cut.append(unary_union(done).buffer(0.02))
    if wells is not None:
        cut.append(wells.buffer(0.05))
    for s_ in arch["structure"]:          # the shafts through this floor
        if s_["type"] == "slab" and s_["level"] == lid:
            for h in s_.get("shafts") or []:
                try:
                    cut.append(Polygon(h).buffer(0.02))
                except Exception:  # noqa: BLE001
                    continue
        if s_.get("type") == "column" and s_.get("level") == lid:
            try:
                from .engine import structure as S_
                cut.append(Polygon(S_.column_outline(s_, 0.0)).buffer(0.01))
            except Exception:  # noqa: BLE001
                continue
    for m in doc.get("man_shafts") or []:
        if m.get("level") == lid and (m.get("auto") in ("lift",) or re.search(
                r"DUCT|SHAFT|LIFT", str(m.get("note", "")), re.I)):
            cut.append(Polygon(m["pts"]).buffer(0.05))
    rest = inside.difference(unary_union(cut))
    out = []
    k = 0
    for g in getattr(rest, "geoms", [rest]):
        if g.geom_type != "Polygon" or g.area < 1.0 or \
                g.buffer(-0.25).is_empty:
            continue
        k += 1
        fs = faces(g, z_of[lid] + float(lvc.get("h", DEFAULT_H)),
                   lvc.get("type", "gypsum"))
        if fs:
            out.append((lid, f"Open area {k}", lvc.get("type", "gypsum"),
                        float(lvc.get("h", DEFAULT_H)), fs,
                        f"{lid}|open{k}"))
    return out
