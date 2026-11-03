# SPDX-License-Identifier: GPL-3.0-or-later
# From ArchXQ IT Lite (c) Orlando Souza / XQ, GPL-3.0-or-later
# https://github.com/equipexq/archxq-it-lite  — used unchanged by CAD2IngeTrazo.
"""ArchXQ ROOMS — found from the walls, named by the architect.

A room is a space ENCLOSED by walls: a hole in the union of a level's
joined wall plans (the walls engine closes every corner, T and crossing,
and doors don't cut the plans — so a room behind a door is still closed).
Nothing to draw: they are found again on every change of the walls.

What the architect gives them is kept in ``doc["rooms"]``: {"id",
"level", "x", "y" (a point inside), "name"}. A room found takes the name
of the record whose point lies in it; a record whose room is gone (the
walls moved over its point) is dropped when names are saved.
"""
from __future__ import annotations

from . import walls as W

MIN_AREA = 0.5          # m² — less is a gap between walls, not a room
_cache: dict = {}


#: CAD2IngeTrazo: walls stopping short of one another (a column, a pier,
#: a window band between them) still close a room — gaps up to twice this
CLOSE = 0.38


def found(walls: list[dict], solids=()) -> list[dict]:
    """The rooms the walls enclose: [{"poly": shapely Polygon, "area",
    "perimeter", "at": (x, y) label point}], largest first. ``solids``:
    plan outlines that close rooms too (the level's columns)."""
    key = repr(sorted((w["id"], w.get("a"), w.get("b"), w.get("m"),
                       w.get("c"), w.get("r"), w.get("t"), w.get("align"),
                       w.get("side"), w.get("kind")) for w in walls)) + \
        repr([tuple(map(tuple, s_)) for s_ in solids])
    if key in _cache:
        return _cache[key]
    from shapely.geometry import Polygon
    from shapely.ops import polylabel, unary_union
    polys = []
    for pcs in W.plan(walls).values():
        for pc in pcs:
            p = Polygon(pc["outer"], pc["holes"])
            polys.append(p if p.is_valid else p.buffer(0))
    for s_ in solids:
        try:
            p = Polygon(s_)
            polys.append(p if p.is_valid else p.buffer(0))
        except Exception:  # noqa: BLE001
            continue
    out = []
    if polys:
        # close the hairline seams between joined pieces — and the small
        # gaps the plan leaves between walls, piers and columns
        g_ = CLOSE if solids is not None else 1e-4
        u = unary_union(polys).buffer(g_, join_style=2).buffer(
            -g_, join_style=2)
        comps = list(getattr(u, "geoms", [u]))
        filled = [Polygon(g.exterior) for g in comps]
        for g in comps:
            for ring in g.interiors:
                hole = Polygon(ring)
                # less the walls standing loose inside it (a core in a
                # garage) — FILLED: their own rooms are counted on their own
                inner = [f for f in filled if f.area < hole.area - 1e-6
                         and hole.contains(f.representative_point())]
                room = hole.difference(unary_union(inner)) if inner \
                    else hole
                for r in getattr(room, "geoms", [room]):
                    if r.geom_type != "Polygon" or r.area < MIN_AREA:
                        continue
                    try:
                        at = polylabel(r, tolerance=0.05)
                    except Exception:  # noqa: BLE001 — any inside point
                        at = r.representative_point()
                    out.append({"poly": r, "area": r.area,
                                "perimeter": r.exterior.length,
                                "at": (at.x, at.y)})
    if polys and solids is not None:
        try:
            out += _open_rooms(polys, out)
        except Exception:  # noqa: BLE001
            pass
    out.sort(key=lambda r: -r["area"])
    if len(_cache) > 64:
        _cache.clear()
    _cache[key] = out
    return out


#: CAD2IngeTrazo: a room left open by a wide gap (an archway, a duct
#: between two walls, a window band no wall holds) closed at this reach;
#: what is still open inside the building's outline (a hall, a lobby, a
#: corridor) a room of its own
CLOSE_WIDE = 0.7
OUTLINE_GAP = 1.25


def _open_rooms(polys, found_) -> list:
    from shapely.geometry import Polygon
    from shapely.ops import polylabel, unary_union
    U = unary_union(polys)
    u1 = U.buffer(CLOSE, join_style=2).buffer(-CLOSE, join_style=2)
    big = U.buffer(OUTLINE_GAP, join_style=2).buffer(-OUTLINE_GAP,
                                                    join_style=2)
    outline = unary_union([Polygon(g.exterior) for g in getattr(
        big, "geoms", [big]) if g.geom_type == "Polygon" and
        Polygon(g.exterior).area >= 20.0])
    if outline.is_empty:
        return []
    have = unary_union([r["poly"] for r in found_]) if found_ else Polygon()
    rest = outline.difference(u1).difference(have.buffer(0.01))
    if rest.is_empty or rest.area < 2.0:
        return []
    out = []

    def add(r):
        try:
            at = polylabel(r, tolerance=0.05)
        except Exception:  # noqa: BLE001
            at = r.representative_point()
        out.append({"poly": r, "area": r.area,
                    "perimeter": r.exterior.length, "at": (at.x, at.y),
                    "open": True})
    # rooms closed at the wider reach
    u2 = U.buffer(CLOSE_WIDE, join_style=2).buffer(-CLOSE_WIDE,
                                                   join_style=2)
    for g in getattr(u2, "geoms", [u2]):
        if g.geom_type != "Polygon":
            continue
        for ring in g.interiors:
            piece = Polygon(ring).intersection(rest)
            for r in getattr(piece, "geoms", [piece]):
                if r.geom_type == "Polygon" and r.area >= 2.0 and \
                        not r.buffer(-0.3).is_empty:
                    add(r)
    if out:
        rest = rest.difference(unary_union([r["poly"] for r in out])
                               .buffer(0.01))
    # what is left inside the outline: a hall, a corridor, a lobby
    for r in getattr(rest, "geoms", [rest]):
        if r.geom_type == "Polygon" and r.area >= 2.0 and \
                not r.buffer(-0.35).is_empty:
            add(r)
    return out


def gross(walls: list[dict]) -> float:
    """The level's gross area: inside the walls' outer faces."""
    key = ("gross",) + tuple(sorted(repr((w["id"], w.get("a"), w.get("b"),
                       w.get("m"), w.get("c"), w.get("r"), w.get("t"),
                       w.get("align"), w.get("side"), w.get("kind")))
                       for w in walls))
    if key in _gross:
        return _gross[key]
    if len(_gross) > 64:
        _gross.clear()
    _gross[key] = v = _gross_of(walls)
    return v


_gross: dict = {}


def _gross_of(walls: list[dict]) -> float:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = [Polygon(pc["outer"], pc["holes"]).buffer(0)
             for pcs in W.plan(walls).values() for pc in pcs]
    if not polys:
        return 0.0
    u = unary_union(polys).buffer(1e-4, join_style=2).buffer(
        -1e-4, join_style=2)
    return sum(Polygon(g.exterior).area for g in getattr(u, "geoms", [u]))


def of_level(doc: dict, level_id: str) -> list[dict]:
    """The level's rooms with their names: [{"name", "area", "perimeter",
    "at", "poly", "rec" (the record, or None)}]. Unnamed: «Room N»."""
    from shapely.geometry import Point
    walls = [w for w in doc.get("walls") or [] if w["level"] == level_id]
    recs = [r for r in doc.get("rooms") or [] if r["level"] == level_id]
    sol = []
    try:                          # the columns close rooms with the walls
        from . import structure as S_
        for c in doc.get("structure") or []:
            if c.get("type") == "column" and c.get("level") == level_id:
                sol.append([tuple(q) for q in S_.column_outline(c)])
    except Exception:  # noqa: BLE001
        sol = []
    out, n = [], 0
    for room in found(walls, sol):
        rec = next((r for r in recs
                    if room["poly"].contains(Point(r["x"], r["y"]))), None)
        if rec is None:
            n += 1
        out.append(dict(room, rec=rec,
                        name=rec["name"] if rec else f"Room {n}"))
    return out


def label(room: dict) -> str:
    return f"{room['name']}\n{room['area']:.2f} m²"
