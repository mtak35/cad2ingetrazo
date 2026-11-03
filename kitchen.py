# SPDX-License-Identifier: GPL-3.0-or-later
"""Kitchens fitted with the «IngeTrazo Kitchen Maker» extension's
parametric cabinets: in every room named KITCHEN (a level's or all
levels'), the longest free wall — and, room allowing, the wall turning off
it (an L) — gets a run of base cabinets with their worktop, the sink under
a window, the hob unit apart from it, a tall fridge unit at the end of a
long run, and wall cabinets over the worktop where there is no window.
The fronts face the room, the backs against the walls; doors and their
swings, and the windows (for the wall cabinets) are kept clear.

The cabinets are Kitchen Maker's own — select one and its Edit, Add next,
Finishes… work on it. Made again, a kitchen's cabinets are replaced."""
from __future__ import annotations

import math
import re
import sys

TAG = "cad2ingetrazo_kitchen"
KM_ID = "ingetrazo_kitchen_maker"
KITCHEN_RX = re.compile(r"KITCHEN|KICHEN|COOKING|COCKING", re.I)
BASE_D, WALL_D = 0.60, 0.35
WALL_Z = 1.45                        # wall cabinets' bottom over the floor
WIDTHS = (900.0, 600.0, 450.0, 300.0)


def maker():
    """The Kitchen Maker extension's module when it is installed, or None."""
    for name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        if KM_ID in name and hasattr(mod, "make_group") and \
                hasattr(mod, "preset"):
            return mod
    return None


def kitchens(doc, lid=None) -> list:
    """[(level id, room)] of the rooms named as kitchens."""
    from .engine import spaces
    arch = doc["arch"]
    out = []
    for lv in arch["levels"]:
        if lid is not None and lv["id"] != lid:
            continue
        try:
            rooms = spaces.of_level(arch, lv["id"])
        except Exception:  # noqa: BLE001
            continue
        for r in rooms:
            if KITCHEN_RX.search(str(r.get("name", ""))) and r["area"] >= 3.0:
                out.append((lv["id"], r))
    return out


def _spans(doc, lid):
    """The level's doors and windows: [(kind, a, b, wall thickness)]."""
    from .engine import walls as W
    arch = doc["arch"]
    walls = {w["id"]: w for w in arch["walls"] if w["level"] == lid}
    out = []
    for o in arch["openings"]:
        w = walls.get(o.get("wall"))
        if w is None or w.get("kind", "line") != "line":
            continue
        c = W.centre(w)
        p0, p1 = tuple(c.p0), tuple(c.p1)
        L = math.dist(p0, p1)
        if L < 1e-6:
            continue
        u = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
        s0 = float(o["pos"]) - float(o["w"]) / 2
        s1 = float(o["pos"]) + float(o["w"]) / 2
        out.append((o.get("kind"), (p0[0] + u[0] * s0, p0[1] + u[1] * s0),
                    (p0[0] + u[0] * s1, p0[1] + u[1] * s1), float(w["t"])))
    return out


def _free(intervals, L):
    """[0, L] less the blocked ``intervals``: the free stretches."""
    cur = [(0.0, L)]
    for a, b in intervals:
        nxt = []
        for x, y in cur:
            if b <= x or a >= y:
                nxt.append((x, y))
                continue
            if a > x:
                nxt.append((x, a))
            if b < y:
                nxt.append((b, y))
        cur = nxt
    return [(x, y) for x, y in cur if y - x > 0.05]


def plan_room(doc, lid, room) -> list:
    """The cabinets of one kitchen: [(params family/style/width/name, origin
    (x, y), x axis (ux, uy), height)] — origin the cabinet's front-left
    bottom corner, x along its run, its back towards the wall."""
    from shapely.geometry import LineString, Polygon
    from shapely.geometry.polygon import orient
    poly = room["poly"]
    if poly.geom_type != "Polygon":
        poly = max(getattr(poly, "geoms", [poly]), key=lambda g: g.area)
    poly = orient(Polygon(poly.exterior), 1.0)          # CCW: room on left
    cs = list(poly.exterior.coords)[:-1]
    n_ = len(cs)
    spans = _spans(doc, lid)
    near = [s for s in spans if poly.buffer(0.5).intersects(
        LineString([s[1], s[2]]))]
    # what blocks the cabinets: the doors with their swings (a square of
    # the door's width into the room), and — for the wall cabinets — the
    # windows' spans
    door_block, win_block = [], []
    for kind, a, b, t in near:
        seg = LineString([a, b])
        if kind == "door":
            wd = max(seg.length, 0.7)
            door_block.append(seg.buffer(wd + t, cap_style=2).buffer(0.05))
        else:
            win_block.append(seg.buffer(t / 2 + 0.25, cap_style=2))
    edges = []
    for i in range(n_):
        P, Q = cs[i], cs[(i + 1) % n_]
        L = math.dist(P, Q)
        if L < 0.9:
            continue
        u = ((Q[0] - P[0]) / L, (Q[1] - P[1]) / L)
        nv = (-u[1], u[0])                       # into the room
        # the run goes from Q back to P (x = −u, y = −n: right-handed)

        def strip(d, P=P, Q=Q, nv=nv):
            return Polygon([P, Q, (Q[0] + nv[0] * d, Q[1] + nv[1] * d),
                            (P[0] + nv[0] * d, P[1] + nv[1] * d)])

        def interval(geom, P=P, Q=Q, u=u, L=L):
            if geom.is_empty:
                return None
            xs = [(Q[0] - x) * -u[0] + (Q[1] - y) * -u[1]
                  for x, y in _coords(geom)]
            return (max(min(xs), 0.0), min(max(xs), L))
        base_bl = [iv for iv in (interval(strip(BASE_D).intersection(g))
                                 for g in door_block) if iv]
        wall_bl = base_bl + [iv for iv in (interval(strip(0.3).intersection(g))
                                           for g in win_block) if iv]
        wins = [iv for iv in (interval(strip(0.3).intersection(g))
                              for g in win_block) if iv]
        edges.append({"i": i, "P": P, "Q": Q, "L": L, "u": u, "n": nv,
                      "base": _free(base_bl, L), "wall_bl": wall_bl,
                      "wins": wins})
    if not edges:
        return []

    def free_len(e):
        return sum(y - x for x, y in e["base"])
    edges.sort(key=free_len, reverse=True)
    main = edges[0]
    if free_len(main) < 1.2:
        return []
    runs = [main]
    # an L: the neighbour sharing a corner, when it has room
    nbrs = [e for e in edges[1:] if (e["i"] - main["i"]) % n_ in (1, n_ - 1)
            and free_len(e) >= 1.2]
    if nbrs:
        sec = max(nbrs, key=free_len)
        # its end at the shared corner: kept clear of the main run's depth
        if math.dist(sec["Q"], main["P"]) < 0.05 or \
                math.dist(sec["Q"], main["Q"]) < 0.05:
            sec["base"] = _free([(0.0, BASE_D)] + [
                (x, y) for x, y in _gaps(sec["base"], sec["L"])], sec["L"])
        else:
            sec["base"] = _free([(sec["L"] - BASE_D, sec["L"])] + [
                (x, y) for x, y in _gaps(sec["base"], sec["L"])], sec["L"])
        runs.append(sec)
    out = []
    sink_done = hob_done = fridge_done = False
    for e in runs:
        for x0, x1 in e["base"]:
            fridge = not fridge_done and x1 - x0 >= 3.0
            mods = ([600.0] + _fill(x1 - x0 - 0.6)) if fridge \
                else _fill(x1 - x0)
            if not mods:
                continue
            used = sum(mods) / 1000.0
            s = x0 + (x1 - x0 - used) / 2
            for k, wmm in enumerate(mods):
                w = wmm / 1000.0
                c = s + w / 2
                fam, style, name = "Base", "Double doors" if wmm >= 600 \
                    else "Single door", f"Base cabinet {int(wmm)}"
                if fridge and k == 0:
                    fam, style, name = "Tall", "Appliance niche", \
                        "Tall fridge unit 600"
                    fridge_done = True
                    e["wall_bl"].append((s, s + w))   # none over it
                elif not sink_done and wmm >= 600 and any(
                        a - 0.3 <= c <= b + 0.3 for a, b in e["wins"]):
                    style, name = "Double doors", f"Sink base {int(wmm)}"
                    sink_done = True
                out.append(({"family": fam, "style": style, "width": wmm,
                             "name": name}, e, s, 0.0))
                s += w
        # the wall cabinets: over the base run, clear of windows / doors
        wfree = _free(e["wall_bl"], e["L"])
        bases = [(x0, x1) for x0, x1 in e["base"]]
        for x0, x1 in wfree:
            for b0, b1 in bases:
                a, b = max(x0, b0), min(x1, b1)
                if b - a < 0.3:
                    continue
                mods = _fill(b - a)
                used = sum(mods) / 1000.0
                s = a + (b - a - used) / 2
                for wmm in mods:
                    out.append(({"family": "Wall", "style": "Double doors"
                                 if wmm >= 600 else "Single door",
                                 "width": wmm,
                                 "name": f"Wall cabinet {int(wmm)}"},
                                e, s, WALL_Z))
                    s += wmm / 1000.0
    if not sink_done:              # no window: the sink mid main run
        mains = [o for o in out if o[1] is main and o[0]["family"] == "Base"
                 and o[0]["width"] >= 600]
        if mains:
            sk = mains[len(mains) // 2]
            sk[0].update(style="Double doors",
                         name=f"Sink base {int(sk[0]['width'])}")
    # the hob: the base cabinet farthest from the sink, 600 wide or more
    if not hob_done:
        sink = next((o for o in out if o[0]["name"].startswith("Sink")),
                    None)
        cands = [o for o in out if o[0]["family"] == "Base" and
                 o[0]["width"] >= 600 and not o[0]["name"].startswith("Sink")]
        if cands:
            if sink is not None:
                sp = _origin(sink)
                hob = max(cands, key=lambda o: math.dist(_origin(o), sp))
            else:
                hob = cands[len(cands) // 2]
            hob[0].update(style="Drawers", name=f"Hob base {int(hob[0]['width'])}")
    res = []
    for p, e, s, z in out:
        d = BASE_D if p["family"] in ("Base", "Tall") else WALL_D
        ox = e["Q"][0] - e["u"][0] * s + e["n"][0] * d
        oy = e["Q"][1] - e["u"][1] * s + e["n"][1] * d
        res.append((p, (ox, oy), (-e["u"][0], -e["u"][1]), z))
    return res


def _origin(o):
    p, e, s, _z = o
    return (e["Q"][0] - e["u"][0] * s, e["Q"][1] - e["u"][1] * s)


def _gaps(free, L):
    """The blocked stretches of [0, L] between the free ones."""
    out, x = [], 0.0
    for a, b in sorted(free):
        if a > x:
            out.append((x, a))
        x = max(x, b)
    if x < L:
        out.append((x, L))
    return out


def _coords(geom):
    for g in getattr(geom, "geoms", [geom]):
        if hasattr(g, "exterior"):
            yield from g.exterior.coords
        else:
            yield from g.coords


def _fill(length):
    """Cabinet widths (mm) filling ``length`` (m), the widest first."""
    left = int(round(length * 1000.0))
    out = []
    for w in WIDTHS:
        while left >= w:
            out.append(w)
            left -= int(w)
    return out


def groups_for(doc, lid, room, km):
    """Kitchen Maker groups for one kitchen, placed (on its floor)."""
    from PySide6.QtGui import QMatrix4x4

    from . import project as PJ
    at = room.get("at") or (room["poly"].representative_point().x,
                            room["poly"].representative_point().y)
    z0 = PJ.floor_top_at(doc, lid, tuple(at))
    out = []
    rk = PJ.room_key(lid, room)
    for k, (p_, (ox, oy), (ux, uy), dz) in enumerate(plan_room(doc, lid,
                                                              room)):
        p = km.preset(p_["family"], p_["style"], p_["width"])
        p.update(style=p_["style"], width=float(p_["width"]),
                 name=p_["name"])
        try:
            g = km.make_group(p)
        except Exception:  # noqa: BLE001 — a size its validation refuses
            continue
        # x along the run, y (the cabinet's back) towards the wall, z up
        m = QMatrix4x4(ux, -uy, 0.0, ox,
                       uy, ux, 0.0, oy,
                       0.0, 0.0, 1.0, z0 + dz,
                       0.0, 0.0, 0.0, 1.0)
        g.xform = m
        g.layer = PJ.level_layer(PJ.level_by_id(doc["arch"], lid)["name"])
        ext = dict(getattr(g, "ext", None) or {})
        # NOT the project's own tag: «commit» makes again only what carries
        # it — these stay the user's (and Kitchen Maker's) to edit
        ext[TAG] = {"id": f"{rk}-{k}", "level": lid, "room": rk}
        g.ext = ext
        out.append(g)
    return out


def fit(viewport, doc, lid=None) -> tuple:
    """Every kitchen (of ``lid``, None = all levels) fitted — the cabinets
    made before in it replaced — ONE Ctrl+Z. (kitchens, cabinets) or raises
    ValueError (no Kitchen Maker, no kitchen)."""
    from core.history import Command
    km = maker()
    if km is None:
        raise ValueError("The «IngeTrazo Kitchen Maker» extension is not "
                         "installed — add it from Extensions, then try again")
    ks = kitchens(doc, lid)
    if not ks:
        raise ValueError("No room named KITCHEN on " +
                         ("this level" if lid else "any level"))
    new, rooms = [], set()
    from . import project as PJ
    for lid_, room in ks:
        gs = groups_for(doc, lid_, room, km)
        rooms.add(PJ.room_key(lid_, room))
        new += gs

    class _Fit(Command):
        def do(self, sc):
            self.old = [g for g in sc.groups if ((getattr(g, "ext", None)
                        or {}).get(TAG) or {}).get("room") in rooms]
            sc.groups[:] = [g for g in sc.groups if g not in self.old] + new
            sc.version += 1

        def undo(self, sc):
            sc.groups[:] = [g for g in sc.groups if g not in new] + self.old
            sc.version += 1
    viewport.history.execute(_Fit())
    try:
        viewport.notify_scene_changed()
    except Exception:  # noqa: BLE001
        pass
    viewport.update()
    return len(ks), len(new)
