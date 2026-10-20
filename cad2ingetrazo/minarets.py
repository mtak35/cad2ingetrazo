# SPDX-License-Identifier: GPL-3.0-or-later
"""Minarets and chhatris (domed kiosks) — a mosque's skyline.

``doc["minarets"]``: [{"id", "level" (it rises from that level's floor),
"x", "y", "b" (its square base's side, m), "h" (its height to the tip of
the crescent, m), "base_h" (the square shaft's height, m), "galleries"
(1–3 balconies), "cupola" ("onion" | "bulbous" | "conical"), "rot" (°),
"color"}].

``doc["chhatris"]``: [{"id", "level" (on top of its parapet / roof),
"x", "y", "w" (its side, m), "rot", "z" (its base over the level's top;
None = on the parapet)}].

``groups(doc)`` builds them.
"""
from __future__ import annotations

import math
import uuid

from . import domes as DM

STONE = (0.95, 0.94, 0.90)
TRIM = (0.86, 0.84, 0.78)
ACCENT = (0.70, 0.22, 0.18)          # the galleries' red band
CUPOLA = (0.93, 0.92, 0.88)
GOLD = (0.86, 0.69, 0.25)
CUPOLAS = [("onion", "Onion"), ("bulbous", "Bulbous (fluted)"),
           ("conical", "Conical (Ottoman pencil)")]


def _ring(cx, cy, r, n, rot=0.0, flutes=0, depth=0.06):
    pts = []
    for i in range(n):
        th = math.radians(rot) + 2 * math.pi * i / n
        rr = r
        if flutes:
            rr = r * (1 - depth * (0.5 + 0.5 * math.cos(flutes * th)))
        pts.append((cx + rr * math.cos(th), cy + rr * math.sin(th)))
    return pts


def _sq(cx, cy, w, rot):
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    h = w / 2
    return [(cx + c * x - s * y, cy + s * x + c * y)
            for x, y in ((-h, -h), (h, -h), (h, h), (-h, h))]


def _prism(pts, z0, z1, color):
    from shapely.geometry import Polygon

    from . import project as PJ
    if z1 - z0 < 1e-3:
        return []
    return [dict(f, color=color) for f in
            PJ._prism(Polygon(pts).buffer(0), z0, z1, 1e-5)]


def _frustum(cx, cy, r0, r1, z0, z1, n, color, rot=0.0):
    """A flaring / tapering ring (a corbel under a gallery)."""
    return DM._lathe([(r0, 0.0), (r1, z1 - z0)], z0, cx, cy, n, color)


def _rail(cx, cy, r, z, n, color, h=0.9, t=0.06, rot=0.0, square=False,
          w=None):
    """A gallery's parapet: a thin wall round its edge."""
    from shapely.geometry import Polygon
    if square:
        outer = Polygon(_sq(cx, cy, w, rot))
        inner = Polygon(_sq(cx, cy, w - 2 * t, rot))
    else:
        outer = Polygon(_ring(cx, cy, r, n, rot))
        inner = Polygon(_ring(cx, cy, r - t, n, rot))
    from . import project as PJ
    return [dict(f, color=color) for f in
            PJ._prism(outer.difference(inner), z, z + h, 1e-5)]


def build_minaret(m, z0, hi=False):
    """[(part, faces, rgb)] of one minaret rising from ``z0``."""
    cx, cy = float(m["x"]), float(m["y"])
    B = max(float(m.get("b", 1.8)), 0.6)
    H = max(float(m.get("h", 30.0)), 6.0)
    rot = float(m.get("rot", 0.0) or 0.0)
    bh = min(max(float(m.get("base_h", 0.55 * H)), 1.0), H - 4.0)
    gal = int(m.get("galleries", 3) or 3)
    gal = min(max(gal, 1), 3)
    n = 32 if hi else 20
    col = DM.COLOR.get(m.get("color", "white"), STONE)
    parts = []
    z = z0
    # 1. the square shaft, a band at its top
    parts.append(("base", _prism(_sq(cx, cy, B, rot), z, z + bh, col), col))
    parts.append(("band", _prism(_sq(cx, cy, B * 1.04, rot), z + bh - 0.35,
                                 z + bh - 0.05, TRIM), TRIM))
    z += bh
    rest = H - bh
    # proportions of what stands over the base (galleries 0.9 m each)
    gh = 0.9
    seg = {1: [0.45], 2: [0.30, 0.20], 3: [0.26, 0.16, 0.12]}[gal]
    lantern = 0.11 * rest
    cup = 0.09 * rest
    shafts = [max(s * rest - gh, 0.6) for s in seg]
    radii = [B * 0.50, B * 0.42, B * 0.36]
    for k in range(gal):
        r_sh = radii[k] if k else B * 0.50
        # corbel (muqarnas, simplified) flaring out under the gallery
        rg = (B * 0.70) if k == 0 else radii[k] * 1.45
        parts.append(("corbel", _frustum(cx, cy, r_sh * 1.0, rg * 0.98, z,
                                         z + 0.55, n, TRIM), TRIM))
        z += 0.55
        parts.append(("gallery", _prism(_ring(cx, cy, rg, n, rot), z,
                                        z + 0.18, ACCENT), ACCENT))
        parts.append(("rail", _rail(cx, cy, rg, z + 0.18, n, ACCENT,
                                    h=0.85, t=0.07, rot=rot), ACCENT))
        z += 0.18
        # the shaft over it: octagonal, then fluted round
        rs = radii[min(k + 1, 2)] if k < gal - 1 else radii[min(k + 1, 2)]
        if k == 0:
            pts = _ring(cx, cy, B * 0.48, 8, rot + 22.5)
            parts.append(("shaft", _prism(pts, z, z + shafts[k], col), col))
            # a zig-zag band and niches: bands of trim
            for f_ in (0.25, 0.55):
                parts.append(("band", _prism(_ring(
                    cx, cy, B * 0.50, 8, rot + 22.5), z + f_ * shafts[k],
                    z + f_ * shafts[k] + 0.15, TRIM), TRIM))
            r_top = B * 0.48
        else:
            pts = _ring(cx, cy, rs, n * 2, 0.0, flutes=n, depth=0.07)
            parts.append(("shaft", _prism(pts, z, z + shafts[k], col), col))
            r_top = rs
        z += shafts[k]
        radii[min(k + 1, 2)] = r_top
    # 3. the open lantern: columns round, a ring over them
    r_l = radii[min(gal, 2)] * 0.95
    parts.append(("gallery", _prism(_ring(cx, cy, r_l * 1.35, n, rot), z,
                                    z + 0.18, ACCENT), ACCENT))
    parts.append(("rail", _rail(cx, cy, r_l * 1.35, z + 0.18, n, ACCENT,
                                h=0.75, t=0.06), ACCENT))
    z += 0.18
    nc = 6
    for i in range(nc):
        th = math.radians(rot) + 2 * math.pi * i / nc
        px, py = cx + r_l * 0.8 * math.cos(th), cy + r_l * 0.8 * math.sin(th)
        parts.append(("lantern", _prism(_ring(px, py, max(0.06, B * 0.035),
                                              8), z, z + lantern, col), col))
    parts.append(("core", _prism(_ring(cx, cy, r_l * 0.45, n), z,
                                 z + lantern, TRIM), TRIM))
    z += lantern
    parts.append(("cap", _prism(_ring(cx, cy, r_l * 1.05, n, rot), z,
                                z + 0.25, ACCENT), ACCENT))
    z += 0.25
    # 4. the cupola and the finial with its crescent
    kind = m.get("cupola", "bulbous")
    R = r_l * 0.95
    prof = DM.profile({"bulbous": "bulbous", "onion": "onion",
                       "conical": "conical"}.get(kind, "bulbous"), R,
                      max(cup, 0.6) if kind != "conical" else
                      max(cup * 2.2, 1.0), 16 if not hi else 28)
    parts.append(("cupola", DM._lathe(prof, z, cx, cy, n, CUPOLA,
                                      ribs=12 if kind == "bulbous" else 0),
                  CUPOLA))
    z += prof[-1][1] - 0.02
    fh = max(H - (z - z0), 0.8)
    parts.append(("finial", DM._lathe(
        [(0.05, 0.0), (0.09, fh * 0.15), (0.03, fh * 0.3), (0.12, fh * 0.42),
         (0.11, fh * 0.52), (0.025, fh * 0.6), (0.02, fh * 0.7), (0.0, fh * 0.72)],
        z, cx, cy, 12, GOLD), GOLD))
    parts.append(("crescent", _crescent(cx, cy, z + fh * 0.72, fh * 0.28,
                                        rot), GOLD))
    return parts


def _crescent(cx, cy, zb, size, rot):
    """A flat crescent (hilal) standing on the rod, facing ``rot``."""
    from shapely.geometry import Point
    from shapely import affinity
    r = size / 2
    moon = Point(0, r).buffer(r, 24).difference(
        Point(r * 0.45, r * 1.12).buffer(r * 0.85, 24))
    out = []
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    t = 0.03
    for g in getattr(moon, "geoms", [moon]):
        if g.geom_type != "Polygon":
            continue
        pts = list(g.exterior.coords)[:-1]
        front = [(cx + c * x - s * (-t / 2), cy + s * x + c * (-t / 2),
                  zb + y) for x, y in pts]
        back = [(cx + c * x - s * (t / 2), cy + s * x + c * (t / 2),
                 zb + y) for x, y in pts]
        out.append({"loop": front, "holes": [], "color": GOLD})
        out.append({"loop": list(reversed(back)), "holes": [], "color": GOLD})
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            out.append({"loop": [front[i], back[i], back[j], front[j]],
                        "holes": [], "color": GOLD})
    _ = affinity
    return out


def build_chhatri(c, z0, hi=False):
    """[(part, faces, rgb)] of a chhatri: a plinth, four piers with arches
    between them under a cornice, a dome with its finial."""
    cx, cy = float(c["x"]), float(c["y"])
    w = max(float(c.get("w", 1.9)), 0.6)
    rot = float(c.get("rot", 0.0) or 0.0)
    col = DM.COLOR.get(c.get("color", "white"), STONE)
    parts = []
    z = z0
    parts.append(("plinth", _prism(_sq(cx, cy, w * 1.08, rot), z,
                                   z + 0.12 * w, TRIM), TRIM))
    z += 0.12 * w
    ph = 0.55 * w
    pw = 0.16 * w
    a = math.radians(rot)
    c_, s_ = math.cos(a), math.sin(a)
    for sx in (-1, 1):
        for sy in (-1, 1):
            lx, ly = sx * (w / 2 - pw / 2), sy * (w / 2 - pw / 2)
            px, py = cx + c_ * lx - s_ * ly, cy + s_ * lx + c_ * ly
            parts.append(("pier", _prism(_sq(px, py, pw, rot), z, z + ph,
                                         col), col))
    # the arches: a band over the openings, each side cut by its arch
    parts.append(("lintel", _arched_band(cx, cy, w, pw, z + ph * 0.55,
                                         z + ph, rot, col), col))
    z += ph
    parts.append(("cornice", _prism(_sq(cx, cy, w * 1.12, rot), z,
                                    z + 0.1 * w, TRIM), TRIM))
    z += 0.1 * w
    d = {"x": cx, "y": cy, "d": w * 0.86, "kind": "hemi", "drum": 0.0,
         "finial": True, "color": c.get("color", "white")}
    for nm, fs, colr in DM.build(d, z, hi):
        parts.append((nm, fs, colr))
    return parts


def _arched_band(cx, cy, w, pw, z0, z1, rot, col):
    """The four spandrels over a chhatri's openings: a square ring with a
    semicircular arch cut from each side."""
    from shapely.geometry import Polygon

    from .engine import structure as S
    out = []
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    span = w - 2 * pw
    rise = min(span / 2, z1 - z0 - 0.02)
    t = pw * 0.6
    for k in range(4):
        th = a + k * math.pi / 2
        ux, uy = math.cos(th), math.sin(th)          # along the side
        nx, ny = -uy, ux                             # out of the side
        # the side's face in its (along, z) plane: a band less the arch
        curve = S.arch_pts(-span / 2, span / 2, z1 - rise, z1 - 0.0, 12,
                           "semi")
        band = Polygon([(-w / 2 + pw, z0), (w / 2 - pw, z0),
                        (w / 2 - pw, z1), (-w / 2 + pw, z1)])
        cut = Polygon([(span / 2, z0 - 0.01)] + [(p[0], p[1] - 0.001)
                                                 for p in curve] +
                      [(-span / 2, z0 - 0.01)])
        g = band.difference(cut)
        from . import project as PJ
        off = w / 2 - t / 2
        for f in PJ._prism(g, -t / 2, t / 2, 1e-5):
            def P(q):
                al, zz, ac = q
                return (cx + ux * al + nx * (off + ac),
                        cy + uy * al + ny * (off + ac), zz)
            loop = [P(q) for q in f["loop"]]
            out.append({"loop": list(reversed(loop)), "holes": [],
                        "color": col})
    _ = (c, s)
    return out


def new_minaret(doc, level, x, y, b=1.83, h=30.0, base_h=None, galleries=3,
                cupola="bulbous", rot=0.0, color="white") -> dict:
    rec = {"id": uuid.uuid4().hex[:8], "level": level, "x": round(x, 4),
           "y": round(y, 4), "b": round(b, 3), "h": round(h, 3),
           "base_h": round(base_h if base_h else 0.55 * h, 3),
           "galleries": int(galleries), "cupola": cupola,
           "rot": round(rot, 2), "color": color}
    doc.setdefault("minarets", []).append(rec)
    return rec


def new_chhatri(doc, level, x, y, w=1.9, rot=0.0, z=None,
                color="white") -> dict:
    rec = {"id": uuid.uuid4().hex[:8], "level": level, "x": round(x, 4),
           "y": round(y, 4), "w": round(w, 3), "rot": round(rot, 2),
           "z": z, "color": color}
    doc.setdefault("chhatris", []).append(rec)
    return rec


def load(raw, key) -> list:
    out = []
    for d in raw or []:
        if not isinstance(d, dict):
            continue
        try:
            r = {"id": str(d.get("id") or uuid.uuid4().hex[:8]),
                 "level": str(d["level"]), "x": float(d["x"]),
                 "y": float(d["y"]), "rot": float(d.get("rot", 0.0) or 0.0),
                 "color": d.get("color") if d.get("color") in DM.COLOR
                 else "white"}
            if key == "minarets":
                r.update(b=min(max(float(d.get("b", 1.83)), 0.6), 10.0),
                         h=min(max(float(d.get("h", 30.0)), 6.0), 150.0),
                         base_h=float(d.get("base_h") or 0.55 * float(
                             d.get("h", 30.0))),
                         galleries=int(d.get("galleries", 3) or 3),
                         cupola=d.get("cupola") if d.get("cupola") in
                         dict(CUPOLAS) else "bulbous")
            else:
                r.update(w=min(max(float(d.get("w", 1.9)), 0.6), 10.0),
                         z=None if d.get("z") is None else float(d["z"]))
            out.append(r)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def groups(doc):
    from core.group import Group

    from . import project as PJ
    from .host import KEY, level_layer
    arch = doc["arch"]
    elev = PJ.elevations(arch)
    idx = {lv["id"]: i for i, lv in enumerate(arch["levels"])}
    st = doc["settings"]
    hi = bool(st.get("hi_poly", False))
    slab_t = float(st.get("slab_t", 0.1016) or 0.1016)
    par = float(st.get("roof_parapet_h", 0.0) or 0.0) \
        if st.get("roof_parapet", True) else 0.0
    out = []
    for k, m in enumerate(doc.get("minarets") or [], 1):
        i = idx.get(m["level"])
        if i is None:
            continue
        lv = arch["levels"][i]
        faces = []
        for _n, fs, _c in build_minaret(m, elev[i], hi):
            faces += fs
        g = Group(PJ._mesh_of(faces), name=f"Minaret {k} · "
                  f"{m['h']:.1f} m · {lv['name']}")
        g.component = False
        g.material = {"color": STONE, "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ifc = {"class": "IfcBuildingElementProxy", "name": f"Minaret {k}"}
        g.ext = {KEY: {"type": "minaret", "id": m["id"], "level": m["level"]}}
        out.append(g)
    for k, c in enumerate(doc.get("chhatris") or [], 1):
        i = idx.get(c["level"])
        if i is None:
            continue
        lv = arch["levels"][i]
        top = elev[i] + float(lv["height"]) + slab_t
        z0 = top + (par if c.get("z") is None else float(c["z"]))
        faces = []
        for _n, fs, _c in build_chhatri(c, z0, hi):
            faces += fs
        g = Group(PJ._mesh_of(faces), name=f"Chhatri {k} · {lv['name']}")
        g.component = False
        g.material = {"color": STONE, "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ifc = {"class": "IfcBuildingElementProxy", "name": f"Chhatri {k}"}
        g.ext = {KEY: {"type": "chhatri", "id": c["id"], "level": c["level"]}}
        out.append(g)
    return out
