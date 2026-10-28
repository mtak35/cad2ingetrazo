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
    ("gypsum", "Gypsum false ceiling (plain board)", 0.0125,
     (0.96, 0.96, 0.95, 1.0), 0.0, None),
    ("pop", "POP false ceiling (tray, cornice, cove light)", 0.020,
     (0.98, 0.97, 0.94, 1.0), 0.0, None),
    ("wood", "Wooden false ceiling (planks)", 0.018, (0.62, 0.45, 0.30, 1.0),
     0.1524, (0.48, 0.34, 0.22, 1.0)),
    ("pvc", "PVC false ceiling (panels)", 0.010, (0.95, 0.95, 0.97, 1.0),
     0.2032, (0.82, 0.83, 0.85, 1.0)),
    ("metal", "Metal false ceiling (600×600 tiles)", 0.012,
     (0.84, 0.85, 0.86, 1.0), 0.6, (0.62, 0.63, 0.65, 1.0)),
    ("glass", "Glass false ceiling (back-lit panels)", 0.010,
     (0.93, 0.96, 1.0, 1.0), 0.6, (0.40, 0.42, 0.45, 1.0)),
    ("fabric", "Fabric / cloth false ceiling (draped)", 0.004,
     (0.86, 0.70, 0.48, 1.0), 0.3, (0.78, 0.62, 0.40, 1.0)),
    ("mineral", "Mineral fibre false ceiling (600×600, light panels)", 0.016,
     (0.97, 0.97, 0.96, 1.0), 0.6, (0.80, 0.80, 0.80, 1.0)),
    ("combo", "Combination ceiling (gypsum border, wooden centre)", 0.0125,
     (0.97, 0.97, 0.96, 1.0), 0.1524, (0.62, 0.45, 0.30, 1.0)),
    ("tiles", "Acoustic tiles 2'×2' on a T-grid", 0.016,
     (0.93, 0.93, 0.91, 1.0), 0.6096, (0.70, 0.71, 0.72, 1.0)),
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
    ("metal_linear", "Metal linear strips", 0.015, (0.80, 0.81, 0.83, 1.0),
     0.1016, (0.55, 0.56, 0.58, 1.0)),
    ("cove_track", "Luxury cove ceiling: LED cove, magnetic track lights, "
     "downlights", 0.0125, (0.96, 0.95, 0.93, 1.0), 0.0, None),
    ("cove_slot", "Luxury cove ceiling: LED cove, linear slot lights, "
     "downlights", 0.0125, (0.96, 0.95, 0.93, 1.0), 0.0, None),
]
TRACK = (0.08, 0.08, 0.09, 1.0)       # black magnetic track, spot heads
WARM = (1.0, 0.84, 0.55, 1.0)         # warm-white LED cove
LIGHT = (1.0, 0.93, 0.72, 1.0)        # the cove's glow, a lit panel
WOOD = (0.62, 0.45, 0.30, 1.0)
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
        if kind in ("cove_track", "cove_slot"):
            out += _luxury(p, z, t, col, tracks=(kind == "cove_track"))
            continue
        if kind in ("pop", "combo", "glass"):
            # a tray: a band round the room, the middle raised (POP: its
            # cornice and the cove light; glass: lit panels in a frame;
            # combination: wooden planks in the middle)
            bw = 0.6 if kind != "glass" else 0.5
            mid = p.buffer(-bw, join_style=2)
            band = p.difference(mid) if not mid.is_empty else p
            for q in getattr(band, "geoms", [band]):
                if q.geom_type == "Polygon" and q.area > 0.01:
                    out.append((_slab(q, z, z + t), BY["gypsum"][3]))
            up = 0.10 if kind != "glass" else 0.06
            for q in getattr(mid, "geoms", [mid]):
                if q.geom_type != "Polygon" or q.area < 0.05:
                    continue
                cc = WOOD if kind == "combo" else col
                out.append((_slab(q, z + up, z + up + t), cc))
                ring = q.buffer(0.02, join_style=2).difference(q)  # fascia
                out.append((_slab(ring, z, z + up), BY["gypsum"][3]))
                if kind == "pop":
                    glow = q.difference(q.buffer(-0.05, join_style=2))
                    out.append((_slab(glow, z + up - 0.012, z + up - 0.002),
                                LIGHT))
                    corn = p.difference(p.buffer(-0.06, join_style=2))
                    out.append((_slab(corn, z - 0.05, z), col))   # cornice
                if kind == "combo":
                    out.append((_grid(q, z + up, grid), gcol))
                if kind == "glass":
                    out.append((_grid(q, z + up, grid), gcol))
            continue
        if kind == "fabric":
            # cloth drawn into folds: strips hanging low and high by turns
            # in the middle, a plain band round it
            mid = p.buffer(-0.45, join_style=2)
            band = p.difference(mid) if not mid.is_empty else p
            for q in getattr(band, "geoms", [band]):
                if q.geom_type == "Polygon" and q.area > 0.01:
                    out.append((_slab(q, z, z + 0.0125), BY["gypsum"][3]))
            from shapely.geometry import box as _bx
            for q in getattr(mid, "geoms", [mid]):
                if q.geom_type != "Polygon" or q.area < 0.05:
                    continue
                x0, y0, x1, y1 = q.bounds
                x, k = x0, 0
                while x < x1:
                    st = q.intersection(_bx(x, y0, x + 0.15, y1))
                    sag = 0.07 if k % 2 == 0 else 0.03
                    for s_ in getattr(st, "geoms", [st]):
                        if s_.geom_type == "Polygon" and s_.area > 1e-4:
                            out.append((_slab(s_, z + 0.08 - sag,
                                              z + 0.08 - sag + t),
                                        col if k % 2 == 0 else gcol))
                    x += 0.15
                    k += 1
                out.append((_slab(q, z + 0.09, z + 0.10), gcol))  # behind
            continue
        if kind == "mineral":          # tiles on a grid, some lit panels
            out.append((_slab(p, z, z + t), col))
            out.append((_grid(p, z, grid), gcol))
            from shapely.geometry import box as _bx
            x0, y0, x1, y1 = p.bounds
            yy = y0 + 1.2
            while yy < y1 - 0.6:
                xx = x0 + 1.2
                while xx < x1 - 0.6:
                    lp = _bx(xx + 0.02, yy + 0.02, xx + 0.58, yy + 0.58)
                    if p.buffer(-0.05).contains(lp):
                        out.append((_slab(lp, z - 0.006, z - 0.001), LIGHT))
                    xx += 1.8
                yy += 1.8
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


def _luxury(p, z, t, col, tracks=True) -> list:
    """The designer bedroom ceiling: a gypsum bulkhead round the room
    (15 cm lower, 60 cm wide) with recessed downlights, a warm LED cove
    washing the raised middle from its inner edge, and in the middle black
    magnetic tracks along the room with spot heads and linear lights
    (``tracks``) or recessed linear slot lights."""
    import math as _m

    from shapely import affinity
    from shapely.geometry import LineString, Point
    out = []
    drop, bw, up = 0.15, 0.60, 0.05
    mid = p.buffer(-bw, join_style=2)
    if mid.is_empty or mid.area < 1.0:          # small room: plain cove
        mid = p.buffer(-0.30, join_style=2)
        bw = 0.30
    band = p.difference(mid) if not mid.is_empty else p
    for q in getattr(band, "geoms", [band]):
        if q.geom_type == "Polygon" and q.area > 0.01:
            out.append((_slabs(q, z - drop, z + t), col))
    if mid.is_empty:
        return out
    for q in getattr(mid, "geoms", [mid]):
        if q.geom_type != "Polygon" or q.area < 0.3:
            continue
        out.append((_slabs(q, z + up, z + up + t), col))
        # the cove: the fascia's inner face lit, a glow on the soffit
        lip = q.buffer(0.012, join_style=2).difference(q)
        out.append((_slabs(lip, z - drop + 0.02, z + up - 0.005), WARM))
        glow = q.difference(q.buffer(-0.10, join_style=2))
        out.append((_slabs(glow, z + up - 0.003, z + up - 0.001), WARM))
        # the room's long direction (its tracks run along it)
        mrr = q.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)[:4]
        e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        ax = e1 if _m.hypot(*e1) >= _m.hypot(*e2) else e2
        ang = _m.degrees(_m.atan2(ax[1], ax[0]))
        c = q.centroid
        qr = affinity.rotate(q, -ang, origin=c)
        x0, y0, x1, y1 = qr.bounds
        inner = qr.buffer(-0.25, join_style=2)
        if inner.is_empty:
            continue
        W_ = y1 - y0
        nlines = 2 if W_ > 2.4 else 1
        for k in range(nlines):
            yy = y0 + W_ * (k + 1) / (nlines + 1)
            ln = LineString([(x0, yy), (x1, yy)]).intersection(inner)
            for seg in getattr(ln, "geoms", [ln]):
                if seg.geom_type != "LineString" or seg.length < 0.6:
                    continue
                (sx0, _y), (sx1, _y2) = list(seg.coords)[0], \
                    list(seg.coords)[-1]
                sx0, sx1 = min(sx0, sx1), max(sx0, sx1)

                def rect(a_, b_, w_):
                    r = LineString([(a_, yy), (b_, yy)]).buffer(
                        w_ / 2, cap_style=2, join_style=2)
                    return affinity.rotate(r, ang, origin=c)
                if tracks:
                    out.append((_slabs(rect(sx0, sx1, 0.035), z + up - 0.035,
                                      z + up), TRACK))
                    xx = sx0 + 0.25
                    k_ = 0
                    while xx < sx1 - 0.2:          # spots and linear lights
                        if k_ % 2 == 0:
                            out.append((_slabs(rect(xx - 0.035, xx + 0.035,
                                                   0.07), z + up - 0.15,
                                              z + up - 0.035), TRACK))
                            out.append((_slabs(rect(xx - 0.025, xx + 0.025,
                                                   0.05), z + up - 0.152,
                                              z + up - 0.15), WARM))
                            xx += 0.35
                        else:
                            e_ = min(xx + 0.6, sx1 - 0.2)
                            out.append((_slabs(rect(xx, e_, 0.02),
                                              z + up - 0.037,
                                              z + up - 0.035), LIGHT))
                            xx = e_ + 0.35
                        k_ += 1
                else:                               # recessed slots
                    out.append((_slabs(rect(sx0, sx1, 0.06), z + up - 0.004,
                                      z + up - 0.001), TRACK))
                    out.append((_slabs(rect(sx0 + 0.01, sx1 - 0.01, 0.03),
                                      z + up - 0.006, z + up - 0.004),
                                LIGHT))
    # recessed downlights along the bulkhead
    rp = p.buffer(-bw / 2, join_style=2)
    for rq in getattr(rp, "geoms", [rp]):
        if rq.is_empty or rq.geom_type != "Polygon":
            continue
        ring = rq.exterior
        if ring.length < 1.0:
            continue
        n_ = max(int(ring.length / 1.2), 1)
        for i in range(n_):
            pt = ring.interpolate(i * ring.length / n_)
            out.append((_slabs(Point(pt.x, pt.y).buffer(0.045, 8),
                               z - drop - 0.003, z - drop - 0.001), WARM))
    return out


def _slabs(g, z0, z1) -> list:
    """_slab of every polygon in ``g`` (a polygon or several)."""
    out = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type == "Polygon" and not q.is_empty and q.area > 1e-6:
            out += _slab(q, z0, z1)
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
        stair_feet = []
        for s_ in doc.get("stairs") or []:     # a stair hall the CAD calls
            if s_.get("level") != lid:           # «VOID» / «STAIR»: ceiled
                continue
            try:
                from shapely.geometry import Polygon as _Pg
                stair_feet.append(_Pg([tuple(p[:2]) for p in
                                       s_["corners"]]).buffer(0))
            except Exception:  # noqa: BLE001
                continue
        for room in spaces.of_level(arch, lid):
            if room["area"] < 1.0:
                continue
            rec_ = room.get("rec") or {}
            hall = bool(re.search(r"VOID|STAIR|LOBBY|HALL",
                                  str(room.get("name", "")), re.I)) and \
                any(room["poly"].intersects(f_) for f_ in stair_feet)
            if rec_.get("ceiling") not in BY and not hall and \
                    _open_air(room, rails):
                if rec_.get("ceiling") != "none" and \
                        doc["settings"].get("balcony_ceiling", True) and \
                        re.search(BALCONY, str(room.get("name", "")), re.I) \
                        or (rec_.get("ceiling") != "none" and
                            doc["settings"].get("balcony_ceiling", True) and
                            not re.search(NO_CEILING,
                                          str(room.get("name", "")), re.I)):
                    try:          # a balcony: its ceiling and edge beam
                        b_ = _balcony(doc, lid, room, order, z_of, rails)
                        if b_:
                            out.append(b_ + (room_key(lid, room),))
                    except Exception:  # noqa: BLE001
                        from .host import log_error
                        log_error("ceilings._balcony")
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
            fs = paint(faces(poly, z_of[lid] + c["h"], c["type"]), rec)
            if fs:
                out.append((lid, room["name"], c["type"], c["h"], fs,
                            room_key(lid, room)))
                done_.append(poly)
        try:                 # the beams round the stair well over it
            out += _well_beams(doc, lid, order, z_of, wells)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("ceilings._well_beams")
        try:                 # the rest inside the outside walls (a hall,
            out += _rest(doc, lid, z_of, wells, done_)   # a corridor, a
        except Exception:  # noqa: BLE001                  # lobby…)
            from .host import log_error
            log_error("ceilings._rest")
    return out


#: the false ceiling's face colour (Edit ▸ Ceiling colour) and its LED
COLOURS = [("fc_auto", "As the type", None),
           ("fc_white", "White", (0.97, 0.97, 0.97, 1.0)),
           ("fc_offwhite", "Off-white", (0.95, 0.94, 0.90, 1.0)),
           ("fc_ivory", "Ivory", (0.96, 0.92, 0.82, 1.0)),
           ("fc_beige", "Warm beige", (0.88, 0.82, 0.72, 1.0)),
           ("fc_grey", "Light grey", (0.82, 0.83, 0.84, 1.0)),
           ("fc_charcoal", "Charcoal", (0.25, 0.26, 0.28, 1.0)),
           ("fc_walnut", "Walnut wood", (0.42, 0.25, 0.13, 1.0)),
           ("fc_oak", "Light oak", (0.74, 0.60, 0.42, 1.0))]
LEDS = [("led_auto", "As the type", None), ("led_warm", "Warm white", WARM),
        ("led_cool", "Cool white", (0.88, 0.94, 1.0, 1.0)),
        ("led_gold", "Golden", (1.0, 0.75, 0.35, 1.0)),
        ("led_off", "Off (no glow)", None)]
_LIT = {LIGHT, WARM}


def paint(fs, rec) -> list:
    """The ceiling's faces in the room's own colours: its boards
    (``ceil_color``) and its cove / panel light (``ceil_led``); the
    tracks, spots and edge beams as they are."""
    cc = dict((k, c) for k, _l, c in COLOURS).get((rec or {}).get(
        "ceil_color") or "fc_auto")
    led_k = (rec or {}).get("ceil_led") or "led_auto"
    lc = dict((k, c) for k, _l, c in LEDS).get(led_k)
    if cc is None and led_k == "led_auto":
        return fs
    out = []
    for f_, col in fs:
        col4 = tuple(col) if col is not None else None
        if col4 in _LIT:
            if led_k == "led_off":
                col4 = cc or BY["gypsum"][3]
            elif lc is not None:
                col4 = lc
        elif cc is not None and col4 not in (TRACK, BEAM_COLOR):
            col4 = cc
        out.append((f_, col4))
    return out


#: rooms out in the open that still get a false ceiling (under the floor
#: above): balconies, sit-outs, verandahs
BALCONY = r"BALCON|SIT\s*OUT|VERANDA|PORCH|LOGGIA"
#: the beam round a balcony's open sides: 9" wide, hung from the slab
#: above down to the false ceiling
BEAM_W = 0.2286
BEAM_COLOR = (0.93, 0.92, 0.89, 1.0)


def _balcony(doc, lid, room, order, z_of, rails):
    """(level, name, kind, h, [(faces, colour)]) of a balcony's false
    ceiling with the periphery beam along its open sides (its railings,
    the edges no wall closes), the beam from the soffit of the slab above
    down to the ceiling — or None when no floor / roof is over it."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from . import project as PJ
    from . import slabedges as SE
    from .engine import walls as W
    arch = doc["arch"]
    i = order.index(lid) if lid in order else -1
    if i < 0:
        return None
    up = order[i + 1] if i + 1 < len(order) else None
    poly = room["poly"]
    over = []
    roof_slabs = [s_ for s_ in arch["structure"] if s_["type"] == "slab"
                  and s_["level"] == lid and s_.get("roof")]
    for s_ in (PJ._floor_slabs(doc, up) if up else []) + roof_slabs:
        try:
            over.append(Polygon(s_["corners"]).buffer(0))
        except Exception:  # noqa: BLE001
            continue
    if not over and up is None:
        # the top floor with no roof slab drawn yet: under the floor's
        # own outline, as the roof will be cast over it
        for s_ in PJ._floor_slabs(doc, lid):
            try:
                over.append(Polygon(s_["corners"]).buffer(0))
            except Exception:  # noqa: BLE001
                continue
    if not over:
        return None
    cover = poly.intersection(unary_union(over))
    if cover.area < 0.5 * poly.area:
        return None                       # open to the sky
    lvc = (doc.get("ceilings") or {}).get(lid) or {}
    rec = room.get("rec") or {}
    kind = rec.get("ceiling") if rec.get("ceiling") in BY else \
        doc["settings"].get("balcony_ceiling_type") or \
        lvc.get("type", "gypsum")
    if kind not in BY:
        kind = "gypsum"
    h = float(rec.get("ceiling_h") or lvc.get("h", DEFAULT_H))
    z0 = z_of[lid]
    zc = z0 + h
    t_up = 0.15
    try:
        t_up = max(float(s_.get("t", 0.15)) for s_ in (
            PJ._floor_slabs(doc, up) if up else roof_slabs) or
            PJ._floor_slabs(doc, lid))
    except Exception:  # noqa: BLE001
        pass
    if up is not None:
        zs = z_of[up] - t_up              # the soffit of the slab above
    else:
        lv_ = next((v for v in arch["levels"] if v["id"] == lid), {})
        zs = z_of[lid] + float(lv_.get("height") or 3.0) - t_up
    if zs <= zc + 0.02:
        zs = zc + 0.02
    ws = [w for w in arch["walls"] if w["level"] == lid
          and not w.get("rail") and W.why_not(w) is None]
    WU = unary_union(SE.wall_polys(ws)) if ws else None
    cover = cover.buffer(-0.005)
    edge = cover.exterior if cover.geom_type == "Polygon" else \
        unary_union([g.exterior for g in cover.geoms])
    open_ = edge.difference(WU.buffer(0.12)) if WU is not None else edge
    band = None
    if not open_.is_empty:
        band = open_.buffer(BEAM_W, cap_style=2, join_style=2) \
            .intersection(cover)
    fs = []
    ceil = cover.difference(band) if band is not None and \
        not band.is_empty else cover
    for g in getattr(ceil, "geoms", [ceil]):
        if g.geom_type == "Polygon" and g.area > 0.1:
            fs += faces(g, zc, kind)
    if band is not None:
        bf = []
        for g in getattr(band, "geoms", [band]):
            if g.geom_type == "Polygon" and g.area > 0.01:
                bf += _slab(g, zc - 0.0125, zs)
        if bf:
            fs.append((bf, BEAM_COLOR))
    if not fs:
        return None
    return (lid, room["name"], kind, h, paint(fs, rec))


def _well_beams(doc, lid, order, z_of, wells) -> list:
    """The edge beams round the stair well in the floor above (as round a
    balcony): 9" wide, hung from the slab's soffit down to the false
    ceiling, along the well's sides no wall closes."""
    if wells is None or wells.is_empty:
        return []
    from shapely.ops import unary_union

    from . import project as PJ
    from . import slabedges as SE
    from .engine import walls as W
    arch = doc["arch"]
    i = order.index(lid) if lid in order else -1
    if i < 0 or i + 1 >= len(order):
        return []
    up = order[i + 1]
    lvc = (doc.get("ceilings") or {}).get(lid) or {}
    h = float(lvc.get("h", DEFAULT_H))
    zc = z_of[lid] + h
    t_up = 0.15
    try:
        t_up = max(float(s_.get("t", 0.15)) for s_ in
                   PJ._floor_slabs(doc, up))
    except Exception:  # noqa: BLE001
        pass
    zs = z_of[up] - t_up
    if zs <= zc + 0.05:
        zc = zs - 0.30                    # no room for a ceiling: a 1' beam
    ws = [w for w in arch["walls"] if w["level"] in (lid, up)
          and not w.get("rail") and W.why_not(w) is None]
    WU = unary_union(SE.wall_polys(ws)) if ws else None
    out = []
    k = 0
    for g in getattr(wells, "geoms", [wells]):
        if g.geom_type != "Polygon" or g.area < 4.0:
            continue                      # a duct / a shaft: no beam
        edge = g.exterior
        open_ = edge.difference(WU.buffer(0.12)) if WU is not None else edge
        if open_.is_empty or open_.length < 0.5:
            continue
        band = open_.buffer(BEAM_W, cap_style=2, join_style=2).difference(g)
        fs = []
        for q in getattr(band, "geoms", [band]):
            if q.geom_type == "Polygon" and q.area > 0.01:
                fs += _slab(q, zc - 0.0125, zs)
        if fs:
            k += 1
            out.append((lid, f"Stair well beam {k}", "beam", h,
                        [(fs, BEAM_COLOR)], f"{lid}|wellbeam{k}"))
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
