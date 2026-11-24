# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo's own material library (resources/textures/library.json — the
swatches of its Materials tray) for the rooms: a floor, wall and ceiling
material per room, and one for the terraces' floors — painted on the
model's faces the way IngeTrazo's Paint tool paints them (``attrs
["texture"]`` and the material's name in ``attrs["mat"]``).

A material key is «category/file» (e.g. «floor/floor_ceramic_white.png»).
"""
from __future__ import annotations

import json
import math

#: which library categories each surface offers
FOR = {"floor": ("finish", "floor", "wood", "stone", "misc", "concrete",
                 "rug", "ground"),
       "wall": ("finish", "wall", "wallpaper", "misc", "concrete", "brick",
                "stone", "wood"),
       "ceiling": ("finish", "wall", "wood", "concrete", "misc"),
       "terrace": ("finish", "floor", "stone", "concrete", "ground", "wood")}
_CACHE = {}


def _root():
    try:
        from core.paths import app_root
        return app_root() / "resources" / "textures"
    except Exception:  # noqa: BLE001
        return None


def items() -> dict:
    """{key: {"name", "path", "sw", "sh", "cat"}} — the library's swatches
    (none when IngeTrazo's library is not there)."""
    if "items" in _CACHE:
        return _CACHE["items"]
    out = {}
    root = _root()
    try:
        data = json.loads((root / "library.json").read_text(encoding="utf-8"))
        for cat in data.get("categories", []):
            for it in cat.get("items", []):
                key = f"{cat['id']}/{it['file'].split('/')[-1]}"
                nm = str(it.get("name", key)).replace("_", " ")
                out[key] = {"name": nm[:1].upper() + nm[1:],
                            "path": str(root / "library" / it["file"]),
                            "sw": float(it.get("sw") or 1.0),
                            "sh": float(it.get("sh") or it.get("sw") or 1.0),
                            "cat": cat["id"]}
    except Exception:  # noqa: BLE001
        out = {}
    try:                 # CAD2IngeTrazo's own finishes: marble, porcelain,
        from pathlib import Path         # ceramic, wood, stone, paint
        here = Path(__file__).resolve().parent / "textures"
        for it in json.loads((here / "finishes.json").read_text(
                encoding="utf-8")):
            key = f"finish/{it['file']}"
            out[key] = {"name": it["name"], "path": str(here / it["file"]),
                        "sw": float(it["sw"]), "sh": float(it["sh"]),
                        "cat": "finish", "group": it.get("cat", "")}
    except Exception:  # noqa: BLE001
        pass
    _CACHE["items"] = out
    return out


def keys_for(surface) -> tuple:
    """The material keys a surface («floor», «wall», «ceiling», «terrace»)
    offers, «none» (as built) first."""
    cats = FOR.get(surface, ())
    its = items()
    return ("none",) + tuple(k for c in cats for k in its
                             if its[k]["cat"] == c)


def labels() -> dict:
    out = {k: (f"{v['name']} — CAD2IngeTrazo" if v["cat"] == "finish"
               else f"{v['name']} ({v['cat']})") for k, v in items().items()}
    out["none"] = "As built (no material)"
    return out


def attrs_of(key):
    """The attrs IngeTrazo's Paint tool stamps for that swatch, or None."""
    it = items().get(key or "")
    if not it:
        return None
    return {"texture": {"path": it["path"], "sw": it["sw"], "sh": it["sh"],
                        "rot": 0.0},
            "mat": it["name"]}


def _newell(lp):
    nx = ny = nz = 0.0
    for i, a in enumerate(lp):
        b = lp[(i + 1) % len(lp)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    L = math.sqrt(nx * nx + ny * ny + nz * nz)
    return None if L < 1e-12 else (nx / L, ny / L, nz / L)


def _split_to_rooms(lp, hs, nn, rms, key="mat_wall", probe=0.15):
    """3.64.133: a wall's face painted only where it looks into the room —
    the face (one polygon along the whole wall, holes for the doors and
    windows) cut at the room's corners. ``rms``: [(room polygon, attrs)].
    Returns [(loop, holes, attrs or None)] when the face is cut or
    painted, else None (the face stays as it is)."""
    from shapely.geometry import LineString, Polygon, box as sbox
    from shapely.ops import unary_union
    h = math.hypot(nn[0], nn[1])
    if h < 0.9 or abs(nn[2]) > 0.1:
        return None
    nx, ny = nn[0] / h, nn[1] / h
    ux, uy = -ny, nx
    d = sum(q[0] * nx + q[1] * ny for q in lp) / len(lp)

    def sz(q):
        return (q[0] * ux + q[1] * uy, q[2])
    S = Polygon([sz(q) for q in lp], [[sz(q) for q in hh] for hh in hs])
    if not S.is_valid:
        S = S.buffer(0)
    if S.is_empty or S.area < 1e-6:
        return None
    s0, z0, s1, z1 = S.bounds
    strips = []                     # [(s_a, s_b, attrs)]
    for poly, m in rms:
        at = m.get(key)
        if not at:
            continue
        p0 = (ux * s0 + nx * (d + probe), uy * s0 + ny * (d + probe))
        p1 = (ux * s1 + nx * (d + probe), uy * s1 + ny * (d + probe))
        if p0 == p1:
            continue
        g = LineString([p0, p1]).intersection(poly)
        for part in getattr(g, "geoms", [g]):
            if part.is_empty or part.geom_type != "LineString" or \
                    part.length < 0.05:
                continue
            ss = [(x - p0[0]) * ux + (y - p0[1]) * uy + s0
                  for x, y in part.coords]
            strips.append((min(ss), max(ss), at))
    if not strips:
        return None
    pieces, rest = [], S
    for a, b, at in strips:
        box_ = sbox(a, z0 - 1.0, b, z1 + 1.0)
        inn = S.intersection(box_)
        if not inn.is_empty and inn.area > 1e-4:
            pieces.append((inn, at))
        rest = rest.difference(box_)
    if not pieces:
        return None
    if rest.is_empty or rest.area < 1e-4:
        pieces_ = pieces                           # all of it inside
    else:
        pieces_ = pieces + [(rest, None)]
    out = []
    for g, at in pieces_:
        for pg in getattr(g, "geoms", [g]):
            if pg.geom_type != "Polygon" or pg.area < 1e-4:
                continue

            def back(co):
                return [(ux * s_ + nx * d, uy * s_ + ny * d, z_)
                        for s_, z_ in co]
            lo = back(list(pg.exterior.coords)[:-1])
            nw = _newell(lo)
            rev = nw is not None and (nw[0] * nn[0] + nw[1] * nn[1]) < 0
            if rev:
                lo = lo[::-1]
            ho = []
            for hh in pg.interiors:
                hl = back(list(hh.coords)[:-1])
                if rev:
                    hl = hl[::-1]
                ho.append(hl)
            out.append((lo, ho, at))
    return out or None


def _repaint(g, pick, split=None) -> int:
    """Faces of group ``g`` given the attrs ``pick(loop, normal)`` returns
    (None = as they are): a shared component made its own mesh first (in
    world coordinates) so its other copies keep theirs. ``split(loop,
    holes, normal)`` (3.64.133) may cut a face in pieces first, each with
    its own attrs. The number painted."""
    from PySide6.QtGui import QVector3D

    from core.mesh import Mesh
    mesh = getattr(g, "mesh", None)
    if mesh is None or not getattr(mesh, "faces", None):
        return 0
    M = getattr(g, "xform", None)

    def W(v):
        q = M.map(v) if M is not None else v
        return (q.x(), q.y(), q.z())
    plan = []                  # (face, loop, holes | None, attrs)
    n = 0
    cut = False
    for f in list(mesh.faces):
        try:
            lp = [W(v) for v in f.vertices]
        except Exception:  # noqa: BLE001
            plan.append((f, None, None, None))
            continue
        nn = _newell(lp)
        if split is not None and nn is not None:
            try:
                hs0 = [[W(v) for v in h] for h in (f.holes or [])]
                pcs = split(lp, hs0, nn)
            except Exception:  # noqa: BLE001
                pcs = None
            if pcs:
                cut = True
                for plp, phs, at in pcs:
                    plan.append((f, plp, phs, at))
                    if at:
                        n += 1
                continue
        at = pick(lp, nn) if nn is not None else None
        plan.append((f, lp, None, at))
        if at:
            n += 1
    if not n:
        return 0
    if M is None and not getattr(g, "component", False) and not cut:
        for f, _lp, _hs, at in plan:
            if at:
                f.attrs.pop("color", None)
                f.attrs.update(at)
        return n
    new = Mesh()                     # its own mesh, world coordinates
    for f, lp, hs, at in plan:
        if lp is None:
            continue
        if hs is None:
            hs = [[W(v) for v in h] for h in (f.holes or [])]
        nf = new.add_face([QVector3D(*q) for q in lp],
                          [[QVector3D(*q) for q in h] for h in hs])
        if nf is None:
            continue
        a = dict(getattr(f, "attrs", {}) or {})
        if at:
            a.pop("color", None)
            a.update(at)
        nf.attrs.update(a)
    g.mesh = new
    g.xform = None
    try:
        g.component = False
    except Exception:  # noqa: BLE001
        pass
    return n


def apply(groups, doc, tag_of, all_groups) -> int:
    """The rooms' floor / wall / ceiling materials and the terraces' floor
    material painted on the model's faces. The number of faces painted."""
    from shapely.geometry import Point

    from .engine import spaces
    arch = doc["arch"]
    st = doc["settings"]
    ter = attrs_of(st.get("terrace_mat"))
    ter_f = attrs_of(st.get("fin_terrace"))      # 3.64.98: the finish by area
    lvk = {lv["id"]: lv.get("kind") for lv in arch["levels"]}
    from . import areas as AR_
    rooms = {}
    for lv in arch["levels"]:
        rs = []
        for r in spaces.of_level(arch, lv["id"]):
            rec = r.get("rec") or {}
            m = {k: attrs_of(rec.get(k)) for k in
                 ("mat_floor", "mat_wall", "mat_ceil")}
            if ter_f and not m["mat_floor"] and (AR_.kind_of(
                    r.get("name") or rec.get("name")) or ("",))[0] == "terrace":
                m["mat_floor"] = ter_f
            if any(m.values()):
                rs.append((r["poly"], m))
        if rs:
            rooms[lv["id"]] = rs
    if not rooms and not ter and not ter_f:
        return 0

    def room_at(lid, x, y):
        pt = Point(x, y)
        for poly, m in rooms.get(lid, ()):
            if poly.contains(pt):
                return m
        return None
    n = 0
    for g in all_groups(groups):
        t = tag_of(g) or {}
        kind, lid = t.get("type"), t.get("level")
        if kind in ("terrace_floor", "finish_edge") and (
                ter or (ter_f and (kind == "terrace_floor"
                                   or lvk.get(lid) != "ground"))):
            tt_ = ter or ter_f
            n += _repaint(g, lambda lp, nn, _t=tt_: _t if nn[2] > 0.9
                          else None)
            continue
        if lid not in rooms:
            continue
        if kind == "room":               # its floor finish: the top
            def pf(lp, nn, _l=lid):
                if nn[2] < 0.9:
                    return None
                c = (sum(q[0] for q in lp) / len(lp),
                     sum(q[1] for q in lp) / len(lp))
                m = room_at(_l, *c)
                return m and m["mat_floor"]
            n += _repaint(g, pf)
        elif kind == "ceiling":          # its underside
            def pc(lp, nn, _l=lid):
                if nn[2] > -0.9:
                    return None
                c = (sum(q[0] for q in lp) / len(lp),
                     sum(q[1] for q in lp) / len(lp))
                m = room_at(_l, *c)
                return m and m["mat_ceil"]
            n += _repaint(g, pc)
        elif kind == "wall":             # its faces looking into a room,
            rms = rooms.get(lid) or []      # the room's own stretch only

            def pw(lp, nn):
                return None

            def sp(lp, hs, nn, _r=rms):
                return _split_to_rooms(lp, hs, nn, _r)
            n += _repaint(g, pw, sp)
    return n
