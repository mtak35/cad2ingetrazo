# SPDX-License-Identifier: GPL-3.0-or-later
"""Wall face finishes: a material laid on ONE face of a wall (the face
picked in the model), over a height band — floor to ceiling, a dado up to
4'-0", the wall above the dado, or a skirting — the way a room's walls
are finished: marble, porcelain and ceramic tiles, wood panelling, stone
cladding, plaster and paint, wallpaper.

Kept on the wall: ``fin`` = [{"side": "l" | "r", "mat": a material key of
matlib (IngeTrazo's library or CAD2IngeTrazo's own finishes), "band":
"full" | "dado" | "upper" | "skirt", "z0", "z1"}] — heights from the floor
finish; ``z1`` 0 = up to the false ceiling (else the slab's soffit).
"l" is the face on the left of the wall drawn a → b. Doors and windows in
the wall are left open.

Built as a thin layer (a tile and its bed) standing on the face, painted
with the material's texture, tagged as its wall's (a click on it picks the
wall).
"""
from __future__ import annotations

import math

#: band → (label, z0, z1) — z1 0: up to the ceiling
BANDS = [("full", "Floor to ceiling", 0.0, 0.0),
         ("dado", "Dado — floor up to 4'-0\"", 0.0, 1.2192),
         ("upper", "Above the dado (4'-0\" to ceiling)", 1.2192, 0.0),
         ("skirt", "Skirting — 4\" high", 0.0, 0.1016)]
BAND = {k: (lab, z0, z1) for k, lab, z0, z1 in BANDS}
#: how far each band stands off the wall's face (tile + bed)
THICK = {"full": 0.012, "dado": 0.015, "upper": 0.010, "skirt": 0.020}

#: the finish menu: (title, [material keys]) — the keys that exist only
GROUPS = [
    ("Marble & granite", [
        "finish/statuario_marble.jpg", "finish/carrara_marble.jpg",
        "finish/botticino_marble.jpg", "finish/emperador_marble.jpg",
        "finish/marquina_marble.jpg", "finish/black_galaxy_granite.jpg",
        "misc/white_marble.jpg", "misc/gray_marble.jpg",
        "misc/compact_gray_marble.jpg", "misc/beige_granite.jpg",
        "misc/dark_granite.jpg", "misc/granite.jpg",
        "wall/marble_tiles.jpg", "wall/travertine_tiles.jpg"]),
    ("Porcelain & ceramic tiles", [
        "finish/porcelain_grey.jpg", "finish/porcelain_beige.jpg",
        "finish/ceramic_white.jpg", "finish/subway_white.jpg",
        "finish/ceramic_blue.jpg", "finish/terrazzo.jpg",
        "wall/white_tile.jpg", "wall/small_tiles.jpg",
        "wall/beige_tiles_2.jpg", "wall/brown_tiles.jpg",
        "wall/white_tiles_with_border.png", "wall/blue_small_ceramic.jpg",
        "wall/green_small_ceramic.jpg", "wall/geometric_tiles.png",
        "wall/blue_mosaic.jpg", "wall/green_mosaic.jpg",
        "floor/gray_ceramic_tiles.jpg", "floor/dark_ceramic_tiles.jpg"]),
    ("Wood", [
        "finish/oak_planks.jpg", "finish/walnut_planks.jpg",
        "finish/teak_panel.jpg", "finish/ash_white.jpg",
        "finish/oak_chevron.jpg", "wall/wood_paneling.jpg",
        "wall/wood_paneling_2.jpg", "wall/wood_paneling_3.jpg",
        "wall/vertical_wood.jpg", "wall/white_wood.jpg",
        "wall/gray_wood.jpg", "wood/oak.jpg", "wood/cherry.jpg",
        "wood/dark_brown.jpg"]),
    ("Stone & brick", [
        "finish/sandstone_cladding.jpg", "finish/slate_tiles.jpg",
        "wall/rectangular_stones.jpg", "wall/stone_bricks.jpg",
        "wall/tiled_stones.jpg", "wall/brown_stones.jpg",
        "stone/stone_ashlar.png", "wall/beige_bricks.jpg",
        "wall/red_bricks.jpg", "brick/brick_clay.png"]),
    ("Plaster & paint", [
        "finish/plaster_white.jpg", "finish/texture_paint.jpg",
        "wall/beige_tadelakt.jpg", "wall/gray_tadelakt.jpg",
        "wall/white_roughcast.jpg", "wall/pastel_gray_sponge_wallpaint.jpg",
        "wall/pastel_yellow_sponge_wallpaint.jpg",
        "wall/light_brown_sponge_wallpaint.jpg",
        "concrete/concrete_smooth.png"]),
    ("Wallpaper", [
        "wallpaper/beige_lines.png", "wallpaper/beige_waves.png",
        "wallpaper/gray_waves.jpg", "wallpaper/geometric_wallpaper.png",
        "wallpaper/gold_circles.png", "wallpaper/gray_diamonds.jpg",
        "wallpaper/natural_colors.png", "wallpaper/classic_red.png",
        "wallpaper/green_wallpaper_with_leaves.jpg",
        "wallpaper/cranes_and_pine_trees.jpg"]),
]
#: the floor finish menu (a room's ``mat_floor``)
FLOOR_GROUPS = [
    ("Marble & granite", [
        "finish/statuario_marble.jpg", "finish/carrara_marble.jpg",
        "finish/botticino_marble.jpg", "finish/emperador_marble.jpg",
        "finish/marquina_marble.jpg", "finish/black_galaxy_granite.jpg",
        "floor/marble_floor_tiles.jpg", "misc/white_marble.jpg",
        "misc/gray_marble.jpg", "misc/beige_granite.jpg",
        "misc/dark_granite.jpg"]),
    ("Porcelain & ceramic tiles", [
        "finish/porcelain_grey.jpg", "finish/porcelain_beige.jpg",
        "finish/terrazzo.jpg", "floor/floor_ceramic_white.png",
        "floor/floor_ceramic_gray.png", "floor/gray_ceramic_tiles.jpg",
        "floor/dark_ceramic_tiles.jpg", "floor/thin_gray_ceramic_tiles.jpg",
        "floor/beige_tiles.jpg", "floor/beige_tiles_3.jpg",
        "floor/light_brown_tiles.jpg", "floor/gray_tiles.jpg",
        "floor/hexagonal_tiles.jpg", "floor/floor_checker.png"]),
    ("Wood", [
        "finish/oak_planks.jpg", "finish/walnut_planks.jpg",
        "finish/ash_white.jpg", "finish/oak_chevron.jpg",
        "floor/wooden_floor.jpg", "floor/wooden_floor_2.jpg",
        "floor/oak_wooden_floor.jpg", "floor/light_beige_wooden_floor.jpg",
        "floor/gray_dark_wooden_floor.jpg", "floor/red_brown_wooden_floor.jpg",
        "floor/hungarian_wooden_floor.jpg", "floor/chess_wooden_floor.jpg"]),
    ("Stone", [
        "finish/slate_tiles.jpg", "finish/sandstone_cladding.jpg",
        "floor/gray_stones_tiles.jpg", "floor/stoneway_tiles.jpg",
        "floor/floor_stones.jpg", "floor/big_stones.jpg",
        "floor/paving_stone.jpg", "floor/brown_terrace_tiles.jpg"]),
    ("Carpet", [
        "floor/gray_carpeting.jpg", "floor/gray_medium_thick_carpeting.jpg",
        "floor/gray_with_squares_carpeting.jpg", "floor/dark_blue_carpeting.jpg",
        "floor/brown_circles_carpeting.jpg", "floor/pink_carpeting.jpg"]),
]
#: a colour for the layer when the texture is not there
FALLBACK = {"marble": (0.93, 0.91, 0.88), "granite": (0.25, 0.25, 0.27),
            "porcelain": (0.62, 0.62, 0.61), "ceramic": (0.95, 0.95, 0.94),
            "tile": (0.90, 0.88, 0.84), "wood": (0.62, 0.45, 0.30),
            "oak": (0.74, 0.60, 0.42), "walnut": (0.42, 0.27, 0.16),
            "stone": (0.75, 0.66, 0.52), "brick": (0.66, 0.36, 0.28),
            "plaster": (0.93, 0.92, 0.89), "paint": (0.85, 0.80, 0.72),
            "black": (0.15, 0.15, 0.16)}


def groups_menu(floor=False) -> list:
    """[(title, [(key, label)])] of the finishes there are (a wall's, or a
    floor's)."""
    from . import matlib as ML
    its = ML.items()
    out = []
    for title, keys in (FLOOR_GROUPS if floor else GROUPS):
        ks = [(k, its[k]["name"]) for k in keys if k in its]
        if ks:
            out.append((title, ks))
    return out


def colour_of(key) -> tuple:
    k = str(key or "").lower()
    for word, c in FALLBACK.items():
        if word in k:
            return c
    return (0.85, 0.83, 0.80)


def label(key) -> str:
    from . import matlib as ML
    it = ML.items().get(key or "")
    return it["name"] if it else str(key or "").split("/")[-1]


def set_band(w, side, mat, band) -> None:
    """The finish ``mat`` on the wall's face ``side`` over ``band``; a
    floor-to-ceiling finish takes the place of the dado / upper ones (and
    they of it); ``mat`` None takes the band off (band None: the face's
    every finish)."""
    fins = [f for f in w.get("fin") or [] if f.get("side") != side or (
        band is not None and not _clash(f.get("band"), band))]
    if mat and band in BAND:
        _l, z0, z1 = BAND[band]
        fins.append({"side": side, "mat": mat, "band": band,
                     "z0": z0, "z1": z1})
    if fins:
        w["fin"] = fins
    else:
        w.pop("fin", None)


def _clash(a, b) -> bool:
    if a == b:
        return True
    return {a, b} in ({"full", "dado"}, {"full", "upper"})


def side_of_face(w, normal) -> str | None:
    """"l" / "r": the face of wall ``w`` a face with ``normal`` (x, y, z)
    is on, or None (its top, an end)."""
    a, b = w["a"], w["b"]
    L = math.dist(a, b)
    if L < 1e-6 or abs(normal[2]) > 0.5:
        return None
    nl = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)       # the left normal
    h = math.hypot(normal[0], normal[1]) or 1.0
    d = (normal[0] * nl[0] + normal[1] * nl[1]) / h
    if d > 0.7:
        return "l"
    if d < -0.7:
        return "r"
    return None


def side_of_point(w, p) -> str | None:
    """"l" / "r": the side of wall ``w`` the point ``p`` (x, y) is on."""
    a, b = w["a"], w["b"]
    cr = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cr) < 1e-9:
        return None
    return "l" if cr > 0 else "r"


def _face_span(w, sg, L) -> tuple:
    """(s0, s1) of the face on side ``sg`` along the wall: its outline's
    points on that face (a mitred corner makes it longer or shorter
    than the centre line)."""
    try:
        from . import slabedges as SE
        a, b = w["a"], w["b"]
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-u[1], u[0])
        t2 = float(w["t"]) / 2
        ss = []
        for g in SE.wall_polys([w]):
            for g2 in getattr(g, "geoms", [g]):
                for x, y in list(g2.exterior.coords):
                    d = (x - a[0], y - a[1])
                    c = d[0] * n[0] + d[1] * n[1]
                    if abs(c - sg * t2) < 0.02:
                        ss.append(d[0] * u[0] + d[1] * u[1])
        if len(ss) >= 2 and max(ss) - min(ss) > 0.05:
            return min(ss), max(ss)
    except Exception:  # noqa: BLE001
        pass
    return 0.0, L


def _layer(R, P, c0, c1) -> list:
    """The band's slab: (s, z) polygon ``R`` from ``c0`` to ``c1`` off the
    face; the front face first (it carries the texture)."""
    from .wallclad import LinearRingCCW
    out = []
    for g in getattr(R, "geoms", [R]):
        if g.geom_type != "Polygon" or g.area < 1e-4:
            continue
        g = g.simplify(0.0005)
        ext = list(g.exterior.coords)[:-1]
        if g.exterior.is_ccw:
            ext = ext[::-1]
        holes = [list(h.coords)[:-1] for h in g.interiors]
        holes = [h if LinearRingCCW(h) else h[::-1] for h in holes]
        out.append({"loop": [P(s, z, c1) for s, z in ext],
                    "holes": [[P(s, z, c1) for s, z in h] for h in holes],
                    "front": True})
        out.append({"loop": [P(s, z, c0) for s, z in ext[::-1]],
                    "holes": [[P(s, z, c0) for s, z in h[::-1]]
                              for h in holes]})
        for ring in [ext] + holes:
            for (s0, z0), (s1, z1) in zip(ring, ring[1:] + ring[:1]):
                out.append({"loop": [P(s0, z0, c0), P(s1, z1, c0),
                                     P(s1, z1, c1), P(s0, z0, c1)]})
    return out


def groups(doc) -> list:
    """A group per finished wall face band (IfcCovering), tagged as its
    wall's."""
    from PySide6.QtGui import QVector3D
    from shapely.geometry import box

    from core.group import Group
    from core.mesh import Mesh

    from . import matlib as ML
    from . import project as PJ
    from . import wallclad as WC
    from .engine import spaces
    from .host import KEY, level_layer
    arch = doc["arch"]
    ws = [w for w in arch["walls"] if w.get("fin")
          and w.get("kind", "line") == "line" and "a" in w
          and not w.get("rail") and w.get("type") != "curtain"]
    if not ws:
        return []
    st = doc["settings"]
    elev = PJ.elevations(arch)
    z_of = {lv["id"]: elev[i] for i, lv in enumerate(arch["levels"])}
    lvh = {lv["id"]: float(lv.get("height") or 3.0) for lv in arch["levels"]}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    fin = float(st.get("finish_t", 0.0508) or 0.0) \
        if st.get("finish_on", True) else 0.0
    plaster = float(st.get("plaster_t", 0.0127) or 0.0)
    ops_of = {}
    for o in arch["openings"]:
        ops_of.setdefault(o.get("wall"), []).append(o)
    rooms_of = {}
    out = []
    for w in ws:
        lid = w["level"]
        if lid not in z_of:
            continue
        try:
            if lid not in rooms_of:
                rooms_of[lid] = [r for r in spaces.of_level(arch, lid)
                                 if r["area"] >= 1.0]
            rooms = rooms_of[lid]
            a, b = w["a"], w["b"]
            L = math.dist(a, b)
            if L < 0.15:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            n = (-u[1], u[0])
            t = float(w["t"])
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            zf = z_of[lid] + fin
            if w.get("height", "level") == "level":
                ztop = z_of[lid] + lvh[lid] - float(st.get("slab_t", 0.15)
                                                    or 0.15)
            else:
                ztop = z_of[lid] + float(w.get("base", 0.0) or 0.0) + \
                    float(w["height"])
            for f_ in w["fin"]:
                sg = 1 if f_.get("side") == "l" else -1
                s0, s1 = _face_span(w, sg, L)
                side_pt = (mid[0] + n[0] * sg * (t / 2 + 0.3),
                           mid[1] + n[1] * sg * (t / 2 + 0.3))
                za = zf + float(f_.get("z0") or 0.0)
                if float(f_.get("z1") or 0.0) > 0:
                    zb = zf + float(f_["z1"])
                else:
                    ch = WC._ceiling_h(doc, lid, rooms, side_pt)
                    zb = z_of[lid] + fin + ch if ch else ztop
                zb = min(zb, ztop)
                if zb - za < 0.03:
                    continue
                R = box(s0, za, s1, zb)
                for o in ops_of.get(w["id"], []):
                    p_ = float(o.get("pos", 0.0))
                    ww = float(o.get("w", 0.9))
                    zs = z_of[lid] + float(o.get("sill", 0.0) or 0.0)
                    R = R.difference(box(p_ - ww / 2, zs if zs > zf + 0.05
                                         else zf - 1, p_ + ww / 2,
                                         zs + float(o.get("h", 2.1))))
                if R.is_empty:
                    continue
                f0 = sg * (t / 2 + plaster)
                th = THICK.get(f_.get("band"), 0.012)

                def P(s, z, c, a=a, u=u, n=n, f0=f0, sg=sg):
                    cc = f0 + sg * c
                    return (a[0] + u[0] * s + n[0] * cc,
                            a[1] + u[1] * s + n[1] * cc, z)
                fs = _layer(R, P, 0.0, th)
                if sg < 0:                  # mirrored: the loops turned
                    for f in fs:
                        f["loop"] = f["loop"][::-1]
                        f["holes"] = [h[::-1] for h in f.get("holes") or []]
                if not fs:
                    continue
                att = ML.attrs_of(f_["mat"])
                col = colour_of(f_["mat"])
                mesh = Mesh()
                for f in fs:
                    face = PJ._safe_add(
                        mesh, [QVector3D(*q) for q in f["loop"]],
                        [[QVector3D(*q) for q in hh]
                         for hh in f.get("holes") or []])
                    if face is None:
                        continue
                    if f.get("front") and att:
                        face.attrs.update(att)
                    else:
                        face.attrs["color"] = col
                band_l = BAND.get(f_.get("band"), ("Finish",))[0]
                g = Group(mesh, name=f"{label(f_['mat'])} · "
                          f"{band_l.split(' — ')[0]} · "
                          f"{w.get('name') or 'Wall'} · {names[lid]}")
                g.component = False
                g.material = {"color": col, "opacity": 1.0}
                g.layer = level_layer(names[lid])
                g.ifc = {"class": "IfcCovering", "name": "Wall finish"}
                g.ext = {KEY: {"type": "wall", "id": w["id"], "level": lid,
                               "part": "finish"}}
                out.append(g)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("finishes.groups")
    return out
