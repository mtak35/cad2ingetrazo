"""3.64.45: a perspective's look applied to the model.

A perspective (a photo or a render of a house the client wants) carries
no sizes, but it does carry a look: its colours, and a style — clay-tile
hip roofs over the floors, arched windows, wrought-iron railings and
gate, light walls. «Follow» on a perspective reference applies that look
to the model as the plans draw it (sizes and positions stay):

- the picture's colours (``palette``): walls, roof tiles, frames, metal;
- the style it shows (``detect``): «mediterranean» when clay-tile roofs
  show, else «modern» (colours only);
- the Mediterranean kit (``apply``): a hip roof of clay tiles over every
  block of the top floor (the roof outline split into rectangles), its
  eaves out 2'-0"; the roof's parapets gone; the upper floors' windows
  and the outside doors arched; the ground floor's windows with grilles;
  the railings and the gate in wrought iron; white frames.

Every «Update from CAD» applies it again (the plans made afresh), as the
elevations are followed again.
"""
from __future__ import annotations

import math
import re

STYLES = {"auto": "Auto (from the picture)",
          "mediterranean": "Mediterranean / Spanish villa",
          "modern": "Modern (glass, black frames, sconces)",
          "mosque": "Modern mosque (white, arches, domes, minarets)",
          "industrial": "Industrial (metal cladding, plain)"}
EAVE = 0.6096                     # 2'-0" eaves
SLOPE = 22.0
MIN_SIDE = 1.0                    # a block narrower than this: no roof of its own


# ---- what the picture shows ----------------------------------------------------
def palette(img) -> dict:
    """The picture's colours: {"wall", "roof", "trim", "metal": (r, g, b)
    0..1, "tile_share": share of the picture in clay-tile red}."""
    import numpy as np
    from PySide6.QtGui import QImage
    im = img.convertToFormat(QImage.Format_RGB32)
    if im.width() > 900:
        from PySide6.QtCore import Qt
        im = im.scaledToWidth(900, Qt.SmoothTransformation)
    w, h = im.width(), im.height()
    a = np.frombuffer(im.constBits(), dtype=np.uint8,
                      count=im.sizeInBytes()).reshape(
        h, im.bytesPerLine())[:, :w * 4].reshape(h, w, 4)[:, :, 2::-1]
    px = a.reshape(-1, 3).astype(np.float32)
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    mx, mn = px.max(axis=1), px.min(axis=1)
    sat = (mx - mn) / np.maximum(mx, 1)
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    sky = (b > r + 12) & (b > g - 5) & (lum > 110)
    green = (g > r + 8) & (g > b + 8)
    tile = (r > g + 35) & (r > b + 45) & (lum > 50) & (lum < 190) & \
        (sat > 0.35)
    # the house: the middle of the picture (the neighbours at its sides)
    cx = np.tile(np.arange(w), h)
    mid = (cx > 0.2 * w) & (cx < 0.8 * w)
    wall = ~sky & ~green & ~tile & mid & (lum > 150) & (lum < 245) & \
        (sat > 0.06) & (sat < 0.35) & (r > b + 12)
    metal = (lum < 55) & ~green

    share = float(tile.mean())
    # the tiles: their brighter half (shade and dirt left out)
    if tile.sum() > 100:
        ts = sat[tile]
        tile = tile & (sat >= np.median(ts))
    def med(mask, dflt):
        if mask.sum() < 50:
            return dflt
        return tuple(float(v) / 255 for v in np.median(px[mask], axis=0))
    # 3.64.52: a modern house's neutrals — its light walls, its dark
    # bands / frames, its warm cladding
    light = ~sky & ~green & mid & (lum > 175) & (sat < 0.10)
    dark = ~green & mid & (lum < 80) & (sat < 0.20)
    warm = ~sky & ~green & ~tile & mid & (lum > 80) & (lum < 175) & \
        (r > b + 18) & (sat > 0.12) & (sat < 0.55)
    # 3.64.53: its light grey cladding (stone panels)
    clad = ~sky & ~green & mid & (lum > 130) & (lum < 205) & (sat < 0.06)
    out_n = {"light": med(light, None), "dark": med(dark, None),
             "warm": med(warm, None), "clad": med(clad, None)}
    try:                       # 3.64.53: raked (inclined) edges in it
        from .modern import has_inclines
        out_n["incline"] = has_inclines(img)
    except Exception:  # noqa: BLE001
        out_n["incline"] = False
    out = {"wall": med(wall, (0.88, 0.84, 0.76)),
           "roof": med(tile, (0.66, 0.30, 0.22)),
           "metal": med(metal, (0.12, 0.11, 0.10)),
           "tile_share": share, **out_n}
    # the trims: lighter than the walls, as warm
    wl = np.array(out["wall"]) * 255
    trim = wall & (lum > 0.3 * wl[0] + 0.59 * wl[1] + 0.11 * wl[2] + 12)
    out["trim"] = med(trim, tuple(min(1.0, c * 1.08) for c in out["wall"]))
    return out


def detect(pal) -> str:
    return "mediterranean" if pal["tile_share"] > 0.015 else "modern"


# ---- the roof outline as rectangles -------------------------------------------------
def rectangles(poly, min_side=MIN_SIDE) -> list:
    """An outline (shapely, square-cornered) split into few rectangles,
    the biggest first: [(x0, y0, x1, y1)] in the outline's own frame."""
    xs = sorted({round(x, 2) for x, _y in poly.exterior.coords})
    ys = sorted({round(y, 2) for _x, y in poly.exterior.coords})
    for h in poly.interiors:
        xs = sorted(set(xs) | {round(x, 2) for x, _y in h.coords})
        ys = sorted(set(ys) | {round(y, 2) for _x, y in h.coords})

    def merge(v, tol=0.25):
        out = []
        for x in v:
            if out and x - out[-1] < tol:
                continue
            out.append(x)
        return out
    xs, ys = merge(xs), merge(ys)
    if len(xs) < 2 or len(ys) < 2:
        return []
    from shapely.geometry import Point
    nx, ny = len(xs) - 1, len(ys) - 1
    fill = [[poly.buffer(-0.02).contains(Point((xs[i] + xs[i + 1]) / 2,
                                               (ys[j] + ys[j + 1]) / 2))
             for j in range(ny)] for i in range(nx)]
    rects = []
    while True:
        best = None
        for i0 in range(nx):
            for j0 in range(ny):
                if not fill[i0][j0]:
                    continue
                jmax = ny
                for i1 in range(i0, nx):
                    if not fill[i1][j0]:
                        break
                    j1 = j0
                    while j1 + 1 < jmax and fill[i1][j1 + 1]:
                        j1 += 1
                    jmax = j1 + 1
                    a = (xs[i1 + 1] - xs[i0]) * (ys[jmax] - ys[j0])
                    if best is None or a > best[0]:
                        best = (a, i0, j0, i1, jmax - 1)
        if best is None:
            break
        _a, i0, j0, i1, j1 = best
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                fill[i][j] = False
        x0, x1, y0, y1 = xs[i0], xs[i1 + 1], ys[j0], ys[j1 + 1]
        if min(x1 - x0, y1 - y0) >= min_side:
            rects.append((x0, y0, x1, y1))
        if len(rects) > 16:
            break
    return rects


def _frame_angle(walls) -> float:
    """The building's main direction (radians), from its long walls."""
    acc = {}
    for w in walls:
        dx, dy = w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]
        L = math.hypot(dx, dy)
        if L < 1.0:
            continue
        a = round(math.degrees(math.atan2(dy, dx)) % 90.0)
        acc[a] = acc.get(a, 0.0) + L
    if not acc:
        return 0.0
    return math.radians(max(acc.items(), key=lambda kv: kv[1])[0])


def _outline(arch, lid):
    """The level's built outline: its outer walls' contour (railings
    left out), holes filled."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    ws = [w for w in arch["walls"] if w["level"] == lid and "a" in w and
          not w.get("rail") and w.get("kind", "line") == "line" and not
          str(w.get("name", "")).lower().startswith(("roof parapet",
                                                     "roof edge"))]
    if len(ws) < 3:
        return None, ws
    # 3.64.79: SQUARE caps — flat ones left the outside corner square of
    # every wall junction out (the bands, quoins and cornice lost the
    # corner: cut short inside the walls)
    body = unary_union([LineString([w["a"][:2], w["b"][:2]]).buffer(
        float(w["t"]) / 2 + 0.02, cap_style=3) for w in ws])
    shells = [Polygon(p.exterior) for p in getattr(body, "geoms", [body])
              if p.geom_type == "Polygon" and p.area > 4.0]
    if not shells:
        return None, ws
    return unary_union(shells), ws


#: the tiled roof forms the design can put over every block
PITCHED = ("hip", "gable", "pyramid", "dutch", "jerkinhead", "gambrel",
           "saltbox", "butterfly", "shed", "bonnet", "m_roof", "arched",
           "clerestory")


def hip_roofs(doc, lid, slope=SLOPE, eave=EAVE, kind="hip") -> int:
    """Clay-tile hip roofs over the level's blocks: its outline split in
    rectangles (in the building's own frame), one hip roof each. The
    level's own «look» roofs are made again. How many."""
    from shapely import affinity
    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    arch = doc["arch"]
    arch["structure"] = [e for e in arch["structure"] if not (
        is_look_roof(e) and not e.get("annex") and e["level"] == lid)]
    poly, ws = _outline(arch, lid)
    if poly is None:
        return 0
    ang = _frame_angle(ws)
    c = poly.centroid
    p0 = affinity.rotate(poly, -ang, origin=c, use_radians=True)
    p0 = p0.simplify(0.05)
    if p0.geom_type != "Polygon":
        p0 = max(p0.geoms, key=lambda g: g.area)
    recs = []
    for x0, y0, x1, y1 in rectangles(p0):
        cs = []
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            dx, dy = x - c.x, y - c.y
            cs.append([round(c.x + dx * math.cos(ang) - dy * math.sin(ang), 4),
                       round(c.y + dx * math.sin(ang) + dy * math.cos(ang), 4)])
        rec = {"type": "roof", "level": lid, "kind": kind, "corners": cs,
               "slope": slope, "overhang": eave, "t": 0.15, "ridge": "long",
               "parapet": 0.0, "pt": 0.15, "tiles": True, "look": True}
        if S.why_not(rec):
            continue
        recs.append(rec)
    if recs:
        arch["structure"] += M.new_elements(arch["structure"], recs)
    del PJ
    return len(recs)


# ---- the kit ---------------------------------------------------------------------
# ---- 3.64.51: the elevation kit — every element its own choice -------------------
#: the kit's choices and what they default to (the Mediterranean villa)
KIT_DEFAULT = {
    "style": "mediterranean", "front": "auto",
    "roof": "hip", "roof_slope": SLOPE, "roof_eave": EAVE, "annex_roof": True,
    "win_head": "arch", "win_frame": "upvc", "gf_grille": True,
    "door_arch": True, "arcades": True,
    "rail": "ms_grill", "columns": "ionic",
    "plinth": True, "bands": True, "cornice": True, "quoins": True,
    "surrounds": True, "lanterns": True, "medallions": True,
    "corbels": True, "porch_canopy": True, "entrance_canopy": True,
    "wall": [0.88, 0.84, 0.74], "trim": [0.95, 0.93, 0.88],
    "stone": [0.72, 0.66, 0.58], "roof_c": [0.78, 0.38, 0.24],
    "metal": [0.10, 0.10, 0.10], "gate_color": "black",
    # 3.64.52: the windows' design, the lights' kind, a roof fascia
    "win_style": "asdrawn", "light_style": "lantern", "fascia": False,
    # 3.64.53: the modern massing (modern.py)
    "slab_edges": False, "frame_box": False, "incline_panel": False,
    "entry_clad": False, "clad": [0.80, 0.80, 0.78],
    # 3.64.55: the styles' own elements (stylekit.py)
    "pediment": False, "deco_fins": False, "deco_bands": False,
    "deco_crown": False, "window_boxes": False, "half_timber": False,
    "gf_clad": False, "shutters": False, "siding": False,
    "eave_brackets": False,
    "fascia_d": 0.30, "fascia_h": 0.55, "accent": [0.24, 0.16, 0.10],
    # 3.64.66: a mosque's own elements (mosque.py)
    "mosque": False, "mosque_type": "modern",
    # 3.64.75: more window / facade detail (stylekit.py)
    "brise_soleil": False, "sills_lintels": False, "jali": False,
    "pilasters": False,
    # 3.64.113: geometrical wall panels (wallpanels.py); the parapet
    # cornice (None: leave the model's setting)
    "geo_panel": "none", "geo_where": "front", "geo_size": 0.30,
    "arch_panels": False,
    "parapet_style": None,
}
OFF = {k: False for k, v in KIT_DEFAULT.items() if isinstance(v, bool)}
#: the presets the designer offers (the world's major elevation styles)
PRESETS = {
    "classical": ("Classical (symmetry, cornices, columns, pediment)", {
        "roof": "asdrawn", "win_head": "flat", "gf_grille": False,
        "door_arch": True, "arcades": False, "rail": "asdrawn",
        "columns": "corinthian", "porch_canopy": False, "medallions": True,
        "pediment": True,
        "wall": [0.93, 0.91, 0.86], "trim": [0.98, 0.97, 0.94],
        "stone": [0.80, 0.77, 0.71]}),
    "neoclassical": ("Neoclassical (portico pediment, Ionic order, "
                     "restrained)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "wood",
        "win_style": "colonial", "rail": "ss_bars", "columns": "ionic",
        "plinth": True, "bands": True, "cornice": True, "surrounds": True,
        "pediment": True, "lanterns": True, "light_style": "lantern",
        "wall": [0.96, 0.95, 0.92], "trim": [1.0, 1.0, 0.98],
        "stone": [0.84, 0.82, 0.78], "gate_color": "black"}),
    "royal": ("Royal — palace / grand building (cream stone, gold trim, "
              "balustrades, pediment, Corinthian columns)", {
        **OFF, "roof": "asdrawn", "win_head": "arch", "win_frame": "wood",
        "win_style": "colonial", "rail": "baluster",
        "columns": "corinthian", "plinth": True, "bands": True,
        "cornice": True, "quoins": True, "surrounds": True,
        "corbels": True, "medallions": True, "pediment": True,
        "pilasters": True, "sills_lintels": True, "lanterns": True,
        "entrance_canopy": True, "door_arch": True, "arcades": True,
        "light_style": "lantern", "fascia": True, "fascia_d": 0.22,
        "fascia_h": 0.45,
        "wall": [0.94, 0.90, 0.80], "trim": [0.99, 0.97, 0.90],
        "stone": [0.86, 0.80, 0.66], "accent": [0.78, 0.62, 0.24],
        "metal": [0.62, 0.48, 0.16], "gate_color": "gold"}),
    "royal_villa": ("Royal villa (white stone, tiled hip roof, balustraded "
                    "balconies, arched openings)", {
        **OFF, "roof": "hip", "roof_slope": 24.0, "roof_eave": 0.75,
        "annex_roof": True, "win_head": "arch", "win_frame": "wood",
        "win_style": "colonial", "rail": "baluster", "columns": "composite",
        "plinth": True, "bands": True, "cornice": True, "quoins": True,
        "surrounds": True, "corbels": True, "medallions": True,
        "pediment": True, "pilasters": True, "lanterns": True,
        "porch_canopy": True, "entrance_canopy": True, "door_arch": True,
        "arcades": True, "shutters": True, "light_style": "lantern",
        "wall": [0.97, 0.95, 0.90], "trim": [1.0, 0.99, 0.95],
        "stone": [0.90, 0.85, 0.74], "roof_c": [0.55, 0.28, 0.20],
        "accent": [0.80, 0.64, 0.26], "metal": [0.64, 0.50, 0.18],
        "gate_color": "gold"}),
    "modern": ("Modern (clean box, glass railings, black frames)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "black",
        "rail": "glass", "columns": "asdrawn", "win_style": "modern_grid",
        "light_style": "sconce", "lanterns": True, "fascia": True,
        "slab_edges": True, "frame_box": True, "entry_clad": True,
        "wall": [0.92, 0.92, 0.90], "trim": [0.30, 0.30, 0.32],
        "stone": [0.45, 0.45, 0.47], "metal": [0.12, 0.12, 0.13],
        "gate_color": "charcoal"}),
    "minimalist": ("Minimalist (white box, large glass, no ornament)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "black",
        "rail": "glass", "columns": "square_smooth",
        "win_style": "side_lights", "light_style": "sconce",
        "slab_edges": True, "fascia": True, "fascia_d": 0.04,
        "fascia_h": 0.12,
        "wall": [0.97, 0.97, 0.96], "trim": [0.88, 0.88, 0.87],
        "stone": [0.80, 0.80, 0.78], "metal": [0.12, 0.12, 0.13],
        "gate_color": "charcoal"}),
    "contemporary": ("Contemporary (bands, stone plinth, glass)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "black",
        "rail": "glass_post", "columns": "asdrawn", "plinth": True,
        "bands": True, "surrounds": True, "win_style": "side_lights",
        "light_style": "sconce", "lanterns": True, "fascia": True,
        "wall": [0.86, 0.84, 0.80], "trim": [0.35, 0.33, 0.31],
        "stone": [0.50, 0.46, 0.42]}),
    "artdeco": ("Art Deco (vertical fins, stepped crown, speed bands)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "steel",
        "win_style": "grid", "rail": "ss_bars", "columns": "square_smooth",
        "plinth": True, "deco_fins": True, "deco_bands": True,
        "deco_crown": True, "lanterns": True, "light_style": "sconce",
        "wall": [0.93, 0.89, 0.80], "trim": [0.27, 0.50, 0.48],
        "stone": [0.72, 0.66, 0.58], "accent": [0.80, 0.64, 0.30],
        "metal": [0.20, 0.20, 0.20], "gate_color": "black"}),
    "brutalist": ("Brutalist (raw concrete, heavy masses, deep window "
                  "boxes)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "black",
        "rail": "solid", "columns": "square_smooth", "window_boxes": True,
        "fascia": True, "fascia_d": 0.60, "fascia_h": 1.00,
        "slab_edges": True,
        "wall": [0.63, 0.63, 0.61], "trim": [0.55, 0.55, 0.53],
        "stone": [0.50, 0.50, 0.48], "accent": [0.55, 0.55, 0.53],
        "metal": [0.15, 0.15, 0.15], "gate_color": "charcoal"}),
    "tudor": ("Traditional — Tudor (half-timbering, steep gables, "
              "brick)", {
        **OFF, "roof": "gable", "roof_slope": 40.0, "roof_eave": 0.40,
        "annex_roof": True, "win_head": "flat", "win_frame": "wood",
        "win_style": "diamond", "rail": "wood", "columns": "asdrawn",
        "half_timber": True, "gf_clad": True, "lanterns": True,
        "light_style": "lantern",
        "wall": [0.95, 0.93, 0.86], "trim": [0.90, 0.88, 0.82],
        "stone": [0.58, 0.28, 0.20], "roof_c": [0.30, 0.30, 0.33],
        "accent": [0.22, 0.15, 0.10], "gate_color": "black"}),
    "capecod": ("Traditional — Cape Cod (steep roof, shutters, "
                "clapboard)", {
        **OFF, "roof": "gable", "roof_slope": 35.0, "roof_eave": 0.30,
        "annex_roof": True, "win_head": "flat", "win_frame": "upvc",
        "win_style": "colonial", "rail": "wood", "columns": "square_smooth",
        "shutters": True, "siding": True, "surrounds": True,
        "lanterns": True, "light_style": "lantern",
        "wall": [0.72, 0.77, 0.82], "trim": [0.98, 0.98, 0.97],
        "stone": [0.70, 0.68, 0.66], "roof_c": [0.36, 0.34, 0.33],
        "accent": [0.14, 0.20, 0.32], "gate_color": "white"}),
    "italianate": ("Traditional — Italianate (low hip, wide eaves, "
                   "brackets)", {
        **OFF, "roof": "hip", "roof_slope": 18.0, "roof_eave": 0.90,
        "annex_roof": True, "win_head": "arch", "win_frame": "wood",
        "win_style": "double_hung", "rail": "ss_bars", "columns": "tuscan",
        "eave_brackets": True, "surrounds": True, "quoins": True,
        "bands": True, "plinth": True, "lanterns": True,
        "light_style": "lantern",
        "wall": [0.86, 0.74, 0.56], "trim": [0.95, 0.92, 0.84],
        "stone": [0.80, 0.72, 0.60], "roof_c": [0.70, 0.38, 0.26],
        "accent": [0.95, 0.92, 0.84], "gate_color": "black"}),
    "georgian": ("Traditional — Georgian (red brick, white sashes, "
                 "shutters)", {
        **OFF, "roof": "hip", "roof_slope": 30.0, "roof_eave": 0.35,
        "annex_roof": True, "win_head": "flat", "win_frame": "wood",
        "win_style": "colonial", "rail": "ms_grill", "columns": "doric",
        "plinth": True, "bands": True, "cornice": True, "surrounds": True,
        "pediment": True, "shutters": True, "sills_lintels": True,
        "lanterns": True, "light_style": "lantern",
        "wall": [0.62, 0.34, 0.26], "trim": [0.97, 0.96, 0.93],
        "stone": [0.80, 0.78, 0.72], "roof_c": [0.25, 0.26, 0.29],
        "accent": [0.96, 0.95, 0.92], "gate_color": "black"}),
    "victorian": ("Traditional — Victorian (steep gables, brackets, "
                  "porch)", {
        **OFF, "roof": "gable", "roof_slope": 42.0, "roof_eave": 0.45,
        "annex_roof": True, "win_head": "arch", "win_frame": "wood",
        "win_style": "double_hung", "rail": "wood", "columns": "round_smooth",
        "bands": True, "cornice": True, "surrounds": True, "corbels": True,
        "porch_canopy": True, "eave_brackets": True, "sills_lintels": True,
        "lanterns": True, "light_style": "lantern",
        "wall": [0.56, 0.64, 0.68], "trim": [0.95, 0.93, 0.86],
        "stone": [0.55, 0.48, 0.42], "roof_c": [0.30, 0.22, 0.20],
        "accent": [0.45, 0.22, 0.22], "gate_color": "black"}),
    "farmhouse": ("Modern farmhouse (white siding, black frames, "
                  "gables)", {
        **OFF, "roof": "gable", "roof_slope": 33.0, "roof_eave": 0.40,
        "annex_roof": True, "win_head": "flat", "win_frame": "black",
        "win_style": "grid", "rail": "wood", "columns": "square_smooth",
        "siding": True, "shutters": True, "entrance_canopy": True,
        "lanterns": True, "light_style": "lantern", "sills_lintels": True,
        "wall": [0.96, 0.96, 0.94], "trim": [0.99, 0.99, 0.98],
        "stone": [0.55, 0.52, 0.48], "roof_c": [0.16, 0.17, 0.18],
        "accent": [0.14, 0.14, 0.15], "gate_color": "black"}),
    "midcentury": ("Mid-century modern (low lines, stone, "
                   "screens)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "black",
        "win_style": "side_lights", "rail": "glass", "columns": "square_smooth",
        "fascia": True, "fascia_d": 0.45, "fascia_h": 0.30,
        "slab_edges": True, "gf_clad": True, "brise_soleil": True,
        "lanterns": True, "light_style": "sconce",
        "wall": [0.90, 0.86, 0.78], "trim": [0.96, 0.95, 0.92],
        "stone": [0.55, 0.45, 0.36], "metal": [0.14, 0.14, 0.15],
        "accent": [0.45, 0.30, 0.18], "gate_color": "charcoal"}),
    "tropical": ("Tropical (deep eaves, timber, louvres)", {
        **OFF, "roof": "hip", "roof_slope": 26.0, "roof_eave": 1.0,
        "annex_roof": True, "win_head": "flat", "win_frame": "wood",
        "win_style": "transom_top", "rail": "wood",
        "columns": "round_smooth", "shutters": True, "brise_soleil": True,
        "plinth": True, "lanterns": True, "light_style": "lantern",
        "wall": [0.94, 0.92, 0.86], "trim": [0.88, 0.84, 0.76],
        "stone": [0.60, 0.55, 0.48], "roof_c": [0.55, 0.30, 0.20],
        "accent": [0.40, 0.26, 0.16], "gate_color": "black"}),
    "gulf_palace": ("Gulf palace villa (Moorish arches, carved panels, "
                    "slate hip roofs, limestone)", {
        **OFF, "roof": "hip", "roof_slope": 14.0, "roof_eave": 0.75,
        "annex_roof": True, "win_head": "arch", "win_frame": "black",
        "win_style": "asdrawn", "rail": "solid", "columns": "round_smooth",
        "door_arch": True, "arcades": True, "plinth": True, "cornice": True,
        "bands": True, "surrounds": False, "pilasters": True,
        "lanterns": True, "light_style": "sconce", "entrance_canopy": True,
        "entry_clad": True, "arch_panels": True, "fascia": False,
        "parapet_style": "stepped",
        "wall": [0.92, 0.86, 0.75], "trim": [0.94, 0.89, 0.80],
        "stone": [0.90, 0.84, 0.72], "clad": [0.90, 0.84, 0.72],
        "roof_c": [0.27, 0.28, 0.30], "metal": [0.18, 0.12, 0.08],
        "accent": [0.45, 0.26, 0.13], "gate_color": "brown"}),
    "arabian": ("Arabian / Gulf villa (arches, jali screens, sand "
                "tones)", {
        **OFF, "roof": "asdrawn", "win_head": "arch", "win_frame": "aluminium",
        "win_style": "asdrawn", "rail": "solid", "columns": "round_smooth",
        "door_arch": True, "arcades": True, "plinth": True, "cornice": True,
        "bands": True, "surrounds": True, "jali": True, "lanterns": True,
        "light_style": "lantern", "medallions": True,
        "wall": [0.91, 0.84, 0.70], "trim": [0.98, 0.95, 0.89],
        "stone": [0.74, 0.62, 0.46], "metal": [0.20, 0.16, 0.12],
        "accent": [0.42, 0.28, 0.16], "gate_color": "brown"}),
    "hightech": ("High-tech (steel frame, glass, louvres)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "steel",
        "win_style": "modern_grid", "rail": "glass_post",
        "columns": "square_smooth", "slab_edges": True, "fascia": True,
        "fascia_d": 0.06, "fascia_h": 0.18, "brise_soleil": True,
        "pilasters": True, "light_style": "sconce", "lanterns": True,
        "wall": [0.80, 0.82, 0.84], "trim": [0.30, 0.32, 0.35],
        "stone": [0.50, 0.52, 0.55], "metal": [0.55, 0.58, 0.62],
        "accent": [0.55, 0.58, 0.62], "gate_color": "charcoal"}),
    "bauhaus": ("Bauhaus / International (white cube, ribbon windows)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "steel",
        "win_style": "side_lights", "rail": "ss_bars",
        "columns": "round_smooth", "fascia": True, "fascia_d": 0.05,
        "fascia_h": 0.14, "slab_edges": True, "sills_lintels": True,
        "light_style": "sconce", "lanterns": True,
        "wall": [0.96, 0.96, 0.95], "trim": [0.90, 0.90, 0.89],
        "stone": [0.70, 0.70, 0.68], "metal": [0.18, 0.18, 0.20],
        "gate_color": "charcoal"}),
    "mediterranean": ("Traditional — Mediterranean / Spanish villa", {}),
    "industrial": ("Industrial (metal-clad, flat roofs, plain openings)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "flat",
        "win_frame": "aluminium", "door_arch": False, "rail": "ms_grill",
        "columns": "asdrawn", "slab_edges": False, "fascia": True,
        "fascia_d": 0.10, "fascia_h": 0.45,
        "wall": [0.74, 0.76, 0.78], "trim": [0.42, 0.44, 0.47],
        "stone": [0.62, 0.63, 0.64], "metal": [0.30, 0.31, 0.33],
        "gate_color": "charcoal"}),
    "mosque": ("Modern mosque (white, arched, domes, slim minarets)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "arch",
        "win_frame": "black", "door_arch": True, "rail": "asdrawn",
        "columns": "asdrawn", "slab_edges": True, "fascia": True,
        "fascia_d": 0.45, "fascia_h": 0.60, "mosque": True,
        "wall": [0.95, 0.94, 0.91], "trim": [0.97, 0.96, 0.93],
        "stone": [0.88, 0.86, 0.82], "metal": [0.20, 0.20, 0.22],
        "accent": [0.30, 0.31, 0.33], "gate_color": "charcoal"}),
    "mosque_ottoman": ("Mosque — Ottoman (grey lead dome, pencil minarets, pointed arches)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "arch",
        "win_frame": "wood", "door_arch": True, "rail": "asdrawn",
        "columns": "asdrawn", "slab_edges": True, "fascia": True,
        "fascia_d": 0.45, "fascia_h": 0.60, "mosque": True,
        "mosque_type": "ottoman",
        "wall": [0.93, 0.9, 0.84], "trim": [0.97, 0.95, 0.9],
        "stone": [0.8, 0.76, 0.68], "metal": [0.20, 0.20, 0.22],
        "accent": [0.36, 0.62, 0.55], "gate_color": "black"}),
    "mosque_mughal": ("Mosque — Mughal (red sandstone and white, onion domes)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "arch",
        "win_frame": "wood", "door_arch": True, "rail": "asdrawn",
        "columns": "asdrawn", "slab_edges": True, "fascia": True,
        "fascia_d": 0.45, "fascia_h": 0.60, "mosque": True,
        "mosque_type": "mughal",
        "wall": [0.72, 0.34, 0.24], "trim": [0.96, 0.94, 0.88],
        "stone": [0.9, 0.86, 0.76], "metal": [0.20, 0.20, 0.22],
        "accent": [0.86, 0.69, 0.25], "gate_color": "black"}),
    "mosque_persian": ("Mosque — Persian / Timurid (blue bulbous domes, tile panels)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "arch",
        "win_frame": "aluminium", "door_arch": True, "rail": "asdrawn",
        "columns": "asdrawn", "slab_edges": True, "fascia": True,
        "fascia_d": 0.45, "fascia_h": 0.60, "mosque": True,
        "mosque_type": "persian",
        "wall": [0.9, 0.86, 0.76], "trim": [0.2, 0.44, 0.62],
        "stone": [0.82, 0.74, 0.58], "metal": [0.20, 0.20, 0.22],
        "accent": [0.15, 0.42, 0.66], "gate_color": "charcoal"}),
    "mosque_mamluk": ("Mosque — Mamluk (stone, ribbed dome, stepped minarets)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "arch",
        "win_frame": "wood", "door_arch": True, "rail": "asdrawn",
        "columns": "asdrawn", "slab_edges": True, "fascia": True,
        "fascia_d": 0.45, "fascia_h": 0.60, "mosque": True,
        "mosque_type": "mamluk",
        "wall": [0.84, 0.76, 0.62], "trim": [0.92, 0.88, 0.78],
        "stone": [0.7, 0.62, 0.5], "metal": [0.20, 0.20, 0.22],
        "accent": [0.55, 0.3, 0.22], "gate_color": "black"}),
    "mosque_moorish": ("Mosque — Moorish / Andalusian (horseshoe arches, green accents)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "arch",
        "win_frame": "wood", "door_arch": True, "rail": "asdrawn",
        "columns": "asdrawn", "slab_edges": True, "fascia": True,
        "fascia_d": 0.45, "fascia_h": 0.60, "mosque": True,
        "mosque_type": "moorish",
        "wall": [0.96, 0.93, 0.86], "trim": [0.18, 0.52, 0.36],
        "stone": [0.8, 0.7, 0.55], "metal": [0.20, 0.20, 0.22],
        "accent": [0.18, 0.52, 0.36], "gate_color": "green"}),
    "mosque_arabian": ("Mosque — Arabian / Najdi (plain, shallow domes)", {
        **OFF, "roof": "asdrawn", "annex_roof": False, "win_head": "arch",
        "win_frame": "aluminium", "door_arch": True, "rail": "asdrawn",
        "columns": "asdrawn", "slab_edges": True, "fascia": True,
        "fascia_d": 0.45, "fascia_h": 0.60, "mosque": True,
        "mosque_type": "arabian",
        "wall": [0.9, 0.82, 0.68], "trim": [0.95, 0.9, 0.8],
        "stone": [0.78, 0.68, 0.52], "metal": [0.20, 0.20, 0.22],
        "accent": [0.55, 0.42, 0.3], "gate_color": "brown"}),
}
#: a line on what each style is, under the designer's choice
STYLE_NOTES = {
    "mosque_ottoman": "A great saucer dome, pencil minarets with two "
                      "galleries and conical caps, pointed arches.",
    "mosque_mughal": "Red sandstone with white marble trim, onion domes, "
                     "bulbous minaret caps, multifoil arches.",
    "mosque_persian": "Blue bulbous domes, tiled trims, pointed arches.",
    "mosque_mamluk": "Stone walls, a ribbed dome, minarets with three "
                     "galleries, pointed arches.",
    "mosque_moorish": "Horseshoe arches, green tile trims, a plain square "
                      "minaret.",
    "mosque_arabian": "Plain walls in sand colours, shallow domes, round "
                      "arches.",
    "royal": "A palace front: cream stone, gold trim, Corinthian columns "
             "and a pediment, pilasters, quoins and corbels, a cornice, "
             "stone balustrades on every balcony and terrace.",
    "royal_villa": "A villa with royal detail: white stone, a tiled hip "
                   "roof, balustraded balconies, arched openings, "
                   "pilasters and a pedimented entrance.",
    "industrial": "Grey metal-clad walls, flat roofs with a thin fascia, "
                  "plain flat-headed openings, no ornament.",
    "mosque": "White, every opening arched, deep white slab edges on the "
              "tiers, the domes the plans draw, slim square minarets at "
              "the prayer hall, a lattice boundary wall.",
    "classical": "Symmetry, columns, pediments, Greek / Roman proportions.",
    "neoclassical": "A pedimented portico on Ionic columns, plain walls, "
                    "a cornice and floor bands.",
    "modern": "Flat roofs, a deep dark fascia, big glass, glass railings, "
              "a dark frame and clad corner on the front.",
    "minimalist": "A white box: flat lines, large glass panes, nothing "
                  "added.",
    "contemporary": "Bands, a stone plinth, side-lit windows, glass "
                    "railings.",
    "artdeco": "Vertical emphasis: fins up the front, a stepped crown over "
               "the entrance, speed bands under the roof, metal accents.",
    "brutalist": "Raw concrete masses: a heavy fascia, deep boxed "
                 "windows, solid parapets.",
    "tudor": "Half-timbered upper floors on a brick ground floor, steep "
             "slate gables, leaded (diamond) windows.",
    "capecod": "Steep gables, clapboard siding, shutters by every window, "
               "white trims.",
    "italianate": "A low hip roof with wide eaves on paired brackets, "
                  "tall arched windows with hoods, quoins.",
    "georgian": "Red brick, a pediment and Doric columns, white "
                "six-over-six sashes with sills and lintels, shutters.",
    "victorian": "Steep gables, eave brackets, a corbelled porch roof, "
                 "arched sash windows, a painted-lady palette.",
    "farmhouse": "White clapboard, black grid windows, shutters, a metal "
                 "gable roof, a canopy over the door.",
    "midcentury": "Low flat lines, a deep fascia, a stone ground floor, "
                  "vertical fin screens, picture windows.",
    "tropical": "Deep eaves on a hip roof, timber louvres and shutters, "
                "round columns, warm earth colours.",
    "arabian": "Sand walls, arches and arcades, jali screens over the "
               "windows, cornice and floor bands, a bronze gate.",
    "hightech": "Steel frame look: grey panels, black grid glazing, "
                "louvre fins and pilasters, thin fascia.",
    "bauhaus": "A white cube: thin fascia, ribbon windows, sills and "
               "lintels, tubular railings.",
    "mediterranean": "Clay-tile hip roofs, arches and arcades, wrought "
                     "iron, mouldings, lanterns.",
}
SIDE_DIR = {"north": (0.0, 1.0), "south": (0.0, -1.0), "east": (1.0, 0.0),
            "west": (-1.0, 0.0)}


def preset(name) -> dict:
    return dict(KIT_DEFAULT, **PRESETS.get(name, ("", {}))[1], style=name)


def roof_from_picture(img) -> dict:
    """3.64.100: the roof a perspective shows: its silhouette against the
    sky read column by column. {"roof": "flat" | "hip" | "gable",
    "roof_slope": degrees, "roof_c": (r, g, b) 0..1 (the roof's own colour,
    read just under the silhouette), "inclined": share of the house's width
    with a raked skyline}. The picture carries no true size: the form, the
    pitch and the colour are what it gives."""
    import math
    import numpy as np
    from PySide6.QtGui import QImage
    im = img.convertToFormat(QImage.Format_RGB32)
    if im.width() > 640:
        from PySide6.QtCore import Qt
        im = im.scaledToWidth(640, Qt.SmoothTransformation)
    w, h = im.width(), im.height()
    a = np.frombuffer(im.constBits(), dtype=np.uint8,
                      count=im.sizeInBytes()).reshape(
        h, im.bytesPerLine())[:, :w * 4].reshape(h, w, 4)[:, :, 2::-1]
    a = a.astype(np.float32)
    x0, x1 = int(0.12 * w), int(0.88 * w)
    top = np.median(a[:max(3, h // 40), :, :], axis=0)       # per column
    top = np.stack([np.convolve(top[:, c], np.ones(21) / 21, "same")
                    for c in range(3)], axis=1)
    sil = np.full(w, np.nan)
    for x in range(x0, x1):
        d = np.sqrt(((a[:, x, :] - top[x]) ** 2).sum(axis=1))
        far = d > 55
        run = np.convolve(far.astype(np.float32), np.ones(4), "same") >= 4
        idx = np.flatnonzero(run)
        if len(idx) and idx[0] > h // 40 + 2:
            sil[x] = idx[0]
        elif len(idx):
            sil[x] = np.nan
    xs = np.arange(w)
    ok = ~np.isnan(sil)
    if ok.sum() < 0.4 * (x1 - x0):
        raise ValueError("No skyline found in this picture (a plain sky "
                         "above the house is needed)")
    y = np.interp(xs, xs[ok], sil[ok])
    k = 11
    ys = np.convolve(np.pad(y, k // 2, mode="edge"), np.ones(k) / k, "valid")
    dy = np.gradient(ys)
    seg = np.zeros(w, bool)
    seg[x0:x1] = True
    inc = seg & (np.abs(dy) > 0.18) & (np.abs(dy) < 1.8)
    flat = seg & (np.abs(dy) <= 0.06)
    n = float(seg.sum())
    share_inc, share_flat = float(inc.sum()) / n, float(flat.sum()) / n
    # the roof's colour: under the raked skyline
    cols = []
    for x in np.flatnonzero(inc)[::3]:
        yy = int(ys[x]) + 4
        if yy + 10 < h:
            cols.append(a[yy:yy + 10, x, :].mean(axis=0))
    roof_c = tuple(float(v) / 255 for v in np.median(cols, axis=0)) \
        if len(cols) > 12 else (0.45, 0.30, 0.25)
    kind = "flat"
    slope = 0.0
    if share_inc > 0.22:
        slope = math.degrees(math.atan(float(np.median(np.abs(dy[inc])))))
        slope = min(max(slope * 1.12, 15.0), 42.0)
        # apexes: a point sharper than a hip's plateau means a gable
        lo = ys.min() + 0.04 * (ys.max() - ys.min() + 1)
        apex = (ys <= lo) & seg
        plateau = float(apex.sum()) / max(float(inc.sum()), 1.0)
        kind = "hip" if plateau > 0.18 else "gable"
    return {"roof": kind, "roof_slope": round(slope, 1),
            "roof_c": [round(c, 3) for c in roof_c],
            "inclined": round(share_inc, 2)}


def kit_from_picture(pal, style=None) -> dict:
    """A kit from a perspective: its style's preset, in its colours."""
    style = style or detect(pal)
    col = (lambda c: [round(float(v), 3) for v in c])
    if style == "modern":
        # 3.64.52: a modern house: light walls, dark bands and fascia,
        # its warm cladding as the plinth / stone, black grid windows,
        # glass railings, wall sconces
        k = preset("modern")
        k.update(wall=col(pal.get("light") or pal["wall"]),
                 trim=col(pal.get("dark") or (0.25, 0.25, 0.27)),
                 stone=col(pal.get("warm") or (0.62, 0.52, 0.40)),
                 metal=col(pal.get("dark") or (0.1, 0.1, 0.1)),
                 clad=col(pal.get("clad") or (0.72, 0.72, 0.70)),
                 incline_panel=bool(pal.get("incline")))
        return k
    if style == "mosque":
        k = preset("mosque")
        lt = pal.get("light") or pal["wall"]
        if sum(lt) / 3 > 0.75:              # (its white, as the picture's)
            k.update(wall=col(lt))
        return k
    if style in PRESETS and style != "mediterranean":
        k = preset(style)                 # 3.64.67: the kind's own style,
        lt = pal.get("light") or pal["wall"]          # its walls the
        if style not in ("industrial",) and sum(lt) / 3 > 0.6:  # picture's
            k.update(wall=col(lt))
        return k
    k = preset("mediterranean")
    col = (lambda c: [round(float(v), 3) for v in c])
    k.update(wall=col(pal["wall"]),
             trim=col(tuple(0.5 * c + 0.5 * 0.97 for c in pal["trim"])),
             stone=col(tuple(max(0.0, c * 0.80) for c in pal["wall"])),
             roof_c=col(pal["roof"]), metal=col(pal["metal"]))
    return k


def apply(doc, ref, src=None) -> dict:
    """The perspective's look applied (unless the elevations are designed
    by hand: the design wins). {"look": style, …}."""
    from . import refelev as RE
    if (doc.get("look") or {}).get("manual"):
        rep = apply_kit(doc, doc["look"])
        rep["note"] = "designed by hand: the design kept"
        return rep
    if src is None:
        src = RE.source(ref["file"], int(ref.get("page", 1) or 1))
    pal = palette(src["img"])
    style = ref.get("look") if ref.get("look") in STYLES and \
        ref.get("look") != "auto" else detect(pal)
    try:                      # 3.64.67: the kind of building leads: a
        from . import btype as BT          # mosque's look, a warehouse's…
        if ref.get("look") in (None, "", "auto"):
            st_ = BT.STYLE_OF.get(BT.effective(doc))
            if st_:
                style = st_
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("lookstyle.apply building type")
    return apply_kit(doc, kit_from_picture(pal, style))


def _apply_kit(doc, kit) -> dict:
    """The elevation kit applied to the model as the plans draw it (sizes
    and positions stay): roofs, windows, doors, railings, columns,
    colours; its mouldings are drawn at every rebuild (ornament.py)."""
    k = dict(KIT_DEFAULT, **(kit or {}))
    if str(k.get("style", "")).startswith("mosque"):   # 3.64.72: a hand
        k["mosque"] = True            # design saved by the dialog lost it
        k["mosque_type"] = {"mosque": "modern"}.get(
            k["style"], str(k["style"])[7:] or "modern")
    if isinstance(k.get("roof"), list):      # a look saved by 3.64.49/50:
        k["roof_c"], k["roof"] = k["roof"], "hip"     # «roof» its colour
    arch = doc["arch"]
    rep = {"look": k.get("style", "custom")}
    mats = doc.setdefault("materials", {})
    prev0_ = dict(doc.get("look") or {})
    doc["look"] = {kk: v for kk, v in k.items()}
    if k.get("style") == "mediterranean":
        doc["look"]["style"] = "mediterranean"
    mats["wall"] = {"name": "Plaster, as designed", "color": list(k["wall"])}
    mats["site"] = {"name": "Boundary wall, as designed",
                    "color": list(k["trim"])}
    rep["colours"] = "walls, boundary"
    levels = arch["levels"]
    from . import project as PJ
    el = PJ.elevations(arch)
    order = sorted(range(len(levels)), key=lambda i: el[i])
    ids = [levels[i]["id"] for i in order]
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    # 1. the roofs
    keep_roof = bool(k.get("roof_keep"))    # 3.64.100: the roof is left
    from_ref = k["roof"] == "reference" and not keep_roof
    if from_ref:                            # 3.64.101: the roof the
        try:                                # elevations draw
            from . import roofref as RR
            rr_ = RR.apply(doc, k.get("roof_c"))
        except Exception as e_:  # noqa: BLE001
            from .host import log_error
            log_error("lookstyle roofref")
            rr_ = {"note": f"the roof was not read ({e_})"}
        keep_roof = True                    # (nothing else to do below)
        if rr_.get("note"):
            pic_ = None                     # no elevation: the perspective
            try:                            # gives the form and the pitch
                from . import refelev as RE9
                ref_ = next((r_ for r_ in doc.get("ref_elev") or []
                             if RE9.effective_side(r_) == "perspective"),
                            None)
                if ref_ is not None:
                    src_ = RE9.source(ref_["file"],
                                      int(ref_.get("page", 1) or 1))
                    pic_ = roof_from_picture(src_["img"])
            except Exception as e_:  # noqa: BLE001
                rep["roof_note"] = f"the perspective's roof was not read ({e_})"
            if pic_ and pic_["roof"] in PITCHED:
                k["roof"] = pic_["roof"]
                k["roof_slope"] = pic_["roof_slope"]
                k["roof_c"] = pic_["roof_c"]
                keep_roof = False
                from_ref = False
                arch["structure"] = [e for e in arch["structure"]
                                     if not is_look_roof(e)]
                rep["roof_note"] = ("the roof follows the perspective: "
                                    f"{pic_['roof']} {pic_['roof_slope']:.0f}°")
            elif pic_:
                rep["roof_note"] = "the perspective shows a flat roof: kept"
            else:
                rep.setdefault("roof_note", rr_["note"])
        else:
            rep.update({kk: vv for kk, vv in rr_.items()
                        if kk in ("roofs", "forms", "flat", "parapets_off")})
            rep["colours"] += ", roof tiles"
    elif not keep_roof:                     # exactly as it is (the plan's
        arch["structure"] = [e for e in arch["structure"]   # or an earlier
                             if not is_look_roof(e)]        # design's)
    if k["roof"] in PITCHED and not keep_roof:
        mats["roof"] = {"name": "Roof tiles, as designed",
                        "color": list(k["roof_c"])}
        rep["colours"] += ", roof tiles"
        top = ids[-1]
        roof_lv = top if str(levels[-1].get("name", "")).strip().lower() \
            == "roof" or all(str(w.get("name", "")).lower().startswith(
                ("roof parapet", "roof edge")) or w.get("rail")
                for w in arch["walls"] if w["level"] == top) else None
        under = ids[-2] if roof_lv and len(ids) >= 2 else top
        if roof_lv:
            n0 = len(arch["walls"])
            arch["walls"] = [w for w in arch["walls"] if not (
                w["level"] == roof_lv and (str(w.get("name", "")).lower()
                                           .startswith(("roof parapet",
                                                        "roof edge"))
                                           or w.get("rail")))]
            rep["parapets_off"] = n0 - len(arch["walls"])
        n = hip_roofs(doc, under, float(k["roof_slope"]),
                      float(k["roof_eave"]), kind=k["roof"])
        if roof_lv:
            n += hip_roofs(doc, roof_lv, float(k["roof_slope"]),
                           float(k["roof_eave"]), kind=k["roof"])
        if k["annex_roof"]:
            n += annex_roofs(doc, float(k["roof_slope"]),
                             float(k["roof_eave"]) * 0.75, kind=k["roof"])
        rep["roofs"] = n
        doc["settings"]["roof_parapet"] = False
    # 2. windows and doors (outside ones)
    ws = {w["id"]: w for w in arch["walls"]}
    outer = _outer_walls(arch)
    gid = levels[g]["id"]
    n_arch = n_gr = 0
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or w["id"] not in outer or str(w.get("name", "")) \
                .lower().startswith("corner"):
            continue
        wd = float(o["w"])
        if o["kind"] == "window":
            if k["win_frame"] != "asdrawn":
                o["frame"] = k["win_frame"]
            if k.get("win_style", "asdrawn") != "asdrawn" and \
                    not o.get("vent"):
                o["style"] = k["win_style"]
            if w["level"] != gid and 0.6 <= wd <= 3.0 and \
                    float(o["h"]) >= 0.9:
                if k["win_head"] == "arch" and o.get("head") != "arch":
                    o["head"] = "arch"
                    o["arch"] = "semi"
                    n_arch += 1
                elif k["win_head"] == "flat" and (o.get("head") == "arch"
                                                  or o.get("arch")):
                    o["head"] = "flat"
                    o.pop("arch", None)
            if w["level"] == gid and wd >= 0.6:
                if k["gf_grille"] and o.get("grille") != "ms":
                    o["grille"] = "ms"
                    n_gr += 1
        elif o["kind"] == "door" and wd >= 0.9 and w["level"] == gid \
                and k["door_arch"] and o.get("head") != "arch":
            o["head"] = "arch"
            o["arch"] = "semi"
            n_arch += 1
    rep["arched"] = n_arch
    rep["grilles"] = n_gr
    # 2b. 3.64.75: the corner windows follow the style too (their frame and
    # type — the loop above leaves their legs alone)
    n_cw = 0
    sty_ = k.get("win_style", "asdrawn")
    cw_style = {"colonial": "casement", "double_hung": "sliding",
                "diamond": "casement", "grid": "casement",
                "transom_top": "casement", "modern_grid": "fixed",
                "side_lights": "fixed"}.get(sty_)
    for w in arch["walls"]:
        if not w.get("cwin"):
            continue
        if k["win_frame"] in ("wood", "aluminium", "steel", "upvc", "black"):
            w["cwin_frame"] = k["win_frame"]
        elif k["win_frame"] == "asdrawn":
            pass
        if cw_style and w.get("cwin_style") != "void":
            w["cwin_style"] = cw_style
        n_cw += 1
    rep["corner_windows"] = n_cw
    # 3. the front's wide upper windows as arcades
    if k["arcades"]:
        rep["arcades"] = front_arcades(doc, outer, gid)
    # 4. the railings and the gate
    n_r = 0
    if k["rail"] != "asdrawn":
        for w in arch["walls"]:
            if w.get("rail") and w.get("rail") != k["rail"]:
                w["rail"] = k["rail"]
                n_r += 1
        doc["settings"]["terrace_rail_kind"] = "railing"
    try:
        if k.get("gate_color"):
            doc["site"]["gate_color"] = k["gate_color"]
    except Exception:  # noqa: BLE001
        pass
    rep["rails"] = n_r
    # 4a. 3.64.113: the parapet cornice design
    if k.get("parapet_style"):
        doc["settings"]["parapet_style"] = k["parapet_style"]
    # 4b. 3.64.97: the finishes by area (terraces, car porch, entrance,
    # boundary wall), as the elevation type suggests
    try:
        import re as _re
        st_ = doc["settings"]
        for key in ("fin_terrace", "fin_porch", "fin_entrance"):
            v = k.get(key)
            if v is None or v == "keep":
                continue
            st_[key] = "" if v == "plain" else v
            if key == "fin_terrace":
                for r_ in arch["rooms"]:
                    if _re.search(r"TERRACE|BALCON|VERAND|SIT\s*OUT|DECK",
                                  str(r_.get("name") or ""), _re.I):
                        if st_[key]:
                            r_["mat_floor"] = st_[key]
                        else:
                            r_.pop("mat_floor", None)
        for kk, sk in (("bw_front_style", "front_style"),
                       ("bw_style", "style"),
                       ("bw_front_finish", "front_finish"),
                       ("bw_finish", "finish")):
            v = k.get(kk)
            if v is not None and v != "keep":
                doc["site"][sk] = v
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("lookstyle.finishes by area")
    # 5. the outside free-standing columns
    if k["columns"] != "asdrawn":
        from . import ornament as OR_
        rep["columns"] = OR_.classical_columns(doc, k["columns"])
    # 6. 3.64.66: a mosque's domes, minarets, arches, boundary wall
    if not k.get("mosque"):
        try:
            from . import mosque as MQ
            MQ.remove(doc)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("lookstyle.mosque remove")
    if k.get("mosque"):
        try:
            from . import mosque as MQ
            rep["mosque"] = MQ.apply(doc)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("lookstyle.mosque")
    return rep


_MISSING = {"__missing__": 1}
_GROUPS = (("walls", "walls"), ("open", "openings"), ("struct", "structure"),
           ("rooms", "rooms"))


def _undo_snap(doc) -> dict:
    """What the design may touch, as it stands now."""
    import copy
    a = doc["arch"]
    sn = {g: {e["id"]: copy.deepcopy(e) for e in a.get(k, [])
              if isinstance(e, dict) and e.get("id")} for g, k in _GROUPS}
    for k in ("settings", "site", "materials"):
        sn[k] = copy.deepcopy(doc.get(k) or {})
    return sn


def _undo_diff(pre, post) -> dict:
    out = {}
    for g, _k in _GROUPS:
        a, b = pre[g], post[g]
        out[g] = {"changed": {i: a[i] for i in a if i in b and a[i] != b[i]},
                  "removed": [a[i] for i in a if i not in b],
                  "added": [i for i in b if i not in a]}
    for k in ("settings", "site", "materials"):
        a, b = pre[k], post[k]
        out[k] = {kk: a.get(kk, _MISSING) for kk in set(a) | set(b)
                  if a.get(kk, _MISSING) != b.get(kk, _MISSING)}
    return out


def _undo_merge(old, new) -> dict:
    """Two applications in a row: the first state of everything wins."""
    out = {}
    for g, _k in _GROUPS:
        o = old.get(g) or {"changed": {}, "removed": [], "added": []}
        n = new[g]
        ch = dict(n["changed"])
        ch.update(o["changed"])
        ch = {i: v for i, v in ch.items() if i not in o["added"]}
        rem = list(o["removed"])
        have = {r.get("id") for r in rem}
        for r in n["removed"]:
            if r.get("id") in o["added"]:
                continue            # it came with the first design: no loss
            if r.get("id") not in have:
                rem.append(r)
        gone = {r.get("id") for r in n["removed"]}
        added = [i for i in set(o["added"]) | set(n["added"])
                 if i not in gone]
        out[g] = {"changed": ch, "removed": rem, "added": added}
    for k in ("settings", "site", "materials"):
        d = dict(new[k])
        d.update(old.get(k) or {})
        out[k] = d
    return out


def apply_kit(doc, kit) -> dict:
    """The elevation kit applied (3.64.102: and what it changed kept, so
    «Remove design» can take every bit of it back)."""
    pre = _undo_snap(doc)
    try:
        return _apply_kit(doc, kit)
    finally:
        try:
            doc["look_undo"] = _undo_merge(doc.get("look_undo") or {},
                                           _undo_diff(pre, _undo_snap(doc)))
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("lookstyle undo record")


def remove_kit(doc) -> None:
    """The design taken off, all of it: the roofs and parapets, the
    windows, railings, finishes, the boundary wall and the settings it
    changed, back as they were before it (what the model had since is
    left alone)."""
    a = doc["arch"]
    a["structure"] = [e for e in a["structure"] if not is_look_roof(e)]
    try:
        from . import mosque as MQ
        MQ.remove(doc)
    except Exception:  # noqa: BLE001
        pass
    u = doc.get("look_undo") or {}
    for g, k in _GROUPS:
        d = u.get(g)
        if not d:
            continue
        gone = set(d.get("added") or [])
        cur = [e for e in a.get(k, []) if e.get("id") not in gone]
        ch = d.get("changed") or {}
        cur = [ch.get(e.get("id"), e) for e in cur]
        have = {e.get("id") for e in cur}
        cur += [r for r in d.get("removed") or [] if r.get("id") not in have]
        a[k] = cur
    if not u:         # 3.64.106: no record → the clean-up by defaults
        st = doc.setdefault("settings", {})
        ft = st.get("fin_terrace")
        for r_ in a["rooms"]:
            if ft and r_.get("mat_floor") == ft:
                r_.pop("mat_floor", None)
        for kk in ("fin_terrace", "fin_porch", "fin_entrance", "fin_veranda"):
            st[kk] = ""
        st["roof_parapet"] = True
        for kk in [k for k in st if str(k).startswith(("fin_", "bw_"))]:
            st[kk] = "" if kk.startswith("fin_") else st[kk]
        st.pop("terrace_rail_kind", None)
        # 3.64.103: the design's settings back to the defaults (as imported)
        try:
            from .project import DEFAULTS as _DF
            from . import site as _ST
            for kk in ("fin_terrace", "fin_porch", "fin_entrance",
                       "fin_veranda", "terrace_rail_kind", "terrace_curb_h",
                       "roof_parapet", "roof_parapet_kind", "parapet_style",
                       "terrace_mat"):
                if kk in _DF:
                    st[kk] = _DF[kk]
                else:
                    st.pop(kk, None)
            _sd = _ST.load_site(None)
            _s = doc.setdefault("site", {})
            for kk in ("front_style", "style", "front_finish", "finish",
                       "gate_color", "wall", "sides_on"):
                if kk in _sd:
                    _s[kk] = _sd[kk]
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("lookstyle.remove defaults")
        site = doc.setdefault("site", {})
        for kk in ("finish", "front_finish"):
            if site.get(kk) == "match":
                site[kk] = "plaster"
        mats = doc.get("materials") or {}
        for kk in ("wall", "site", "roof"):
            if str((mats.get(kk) or {}).get("name", "")).endswith(
                    "as designed"):
                mats.pop(kk, None)
    for k in ("settings", "site", "materials"):
        tgt = doc.setdefault(k, {})
        for kk, v in (u.get(k) or {}).items():
            if v == _MISSING:
                tgt.pop(kk, None)
            else:
                tgt[kk] = v
    doc["look_undo"] = {}
    doc["look"] = {}


def _outer_walls(arch) -> set:
    """The ids of the walls on a level's outside (on its outline)."""
    from shapely.geometry import LineString
    out = set()
    for lv in arch["levels"]:
        poly, ws = _outline(arch, lv["id"])
        if poly is None:
            continue
        edge = poly.boundary
        for w in ws:
            ln = LineString([w["a"][:2], w["b"][:2]])
            if ln.length > 0.05 and edge.distance(ln.interpolate(0.5, True)) \
                    <= float(w["t"]) / 2 + 0.1:
                out.add(w["id"])
    return out


def front_side(doc, outer=None):
    """The building's front: the outward direction (unit (x, y)), and
    the main door's wall and opening there. The front faces the way the
    cars drive in (the car porch's cars, along their length, towards the
    nearer edge of the building); without cars, the side of the widest
    outside door of the ground floor. (None, None, None)."""
    from .engine import walls as W
    arch = doc["arch"]
    levels = arch["levels"]
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    gid = levels[g]["id"]
    outer = outer if outer is not None else _outer_walls(arch)
    ws = {w["id"]: w for w in arch["walls"]}
    poly, _ws = _outline(arch, gid)
    if poly is None:
        return None, None, None
    fr = SIDE_DIR.get((doc.get("look") or {}).get("front"))  # set by hand
    cars = []
    for pk in (doc.get("parking") or {}).values():
        cars += [c for c in (pk or {}).get("cars") or [] if c.get("c")]
    if cars and fr is None:
        xs = [v for w in arch["walls"] if "a" in w
              for v in (w["a"][0], w["b"][0])]
        ys = [v for w in arch["walls"] if "a" in w
              for v in (w["a"][1], w["b"][1])]
        c = cars[0]
        an = math.radians(float(c.get("ang", 0.0)))
        ax = (math.cos(an), math.sin(an))
        best = None
        for sg in (1, -1):
            d_ = (ax[0] * sg, ax[1] * sg)
            # how far the car is from the building's edge that way
            tx = ((max(xs) - c["c"][0]) / d_[0] if d_[0] > 1e-6 else
                  (min(xs) - c["c"][0]) / d_[0] if d_[0] < -1e-6 else 1e9)
            ty = ((max(ys) - c["c"][1]) / d_[1] if d_[1] > 1e-6 else
                  (min(ys) - c["c"][1]) / d_[1] if d_[1] < -1e-6 else 1e9)
            far = min(tx, ty)
            if best is None or far < best[0]:
                best = (far, d_)
        fr = best[1]
    pick = None
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or w["id"] not in outer or w["level"] != gid or \
                o["kind"] != "door":
            continue
        sd = _wall_out(w, o, poly)
        if sd is None:
            continue
        if fr is not None and sd[0] * fr[0] + sd[1] * fr[1] < 0.8:
            continue
        if pick is None or float(o["w"]) > float(pick[2]["w"]):
            pick = (sd, w, o)
    if pick is None:
        return fr, None, None
    if fr is None:
        if float(pick[2]["w"]) < 0.9:
            return None, None, None
        fr = pick[0]
    return fr, pick[1], pick[2]


def _wall_out(w, o, poly):
    """The outward direction of an opening's wall (away from the
    outline)."""
    from shapely.geometry import Point
    from .engine import walls as W
    seg = W.centre(w)
    if seg.kind != "line":
        return None
    nl = (-seg.u[1], seg.u[0])
    c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
    t = float(w["t"])
    probe = (c[0] + nl[0] * (t / 2 + 0.25), c[1] + nl[1] * (t / 2 + 0.25))
    return (-nl[0], -nl[1]) if poly.buffer(-0.05).contains(Point(probe)) \
        else nl


def front_arcades(doc, outer, gid, bay=1.1, pier=0.24) -> int:
    """The front's wide upper-floor windows (1.6 m and more) made arcades:
    a row of arched windows between slim piers (their colonettes drawn by
    ornament.py) — the perspective's arched loggia. How many."""
    from .engine import model as M
    from .engine import walls as W
    arch = doc["arch"]
    fr, _w, _o = front_side(doc, outer)
    if fr is None:
        return 0
    ws = {w["id"]: w for w in arch["walls"]}
    new, gone, n = [], set(), 0
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or w["id"] not in outer or w["level"] == gid or \
                o["kind"] != "window" or float(o["w"]) < 1.6 or \
                o.get("arcade"):
            continue
        seg = W.centre(w)
        if seg.kind != "line":
            continue
        nl = (-seg.u[1], seg.u[0])
        if abs(nl[0] * fr[0] + nl[1] * fr[1]) < 0.85:
            continue                       # not on the front
        Wd = float(o["w"])
        k = max(2, int(round((Wd + pier) / (bay + pier))))
        uw = (Wd - (k - 1) * pier) / k
        if uw < 0.55:
            continue
        tag = o["id"][:8]
        x0 = float(o["pos"]) - Wd / 2
        lv = next((x for x in arch["levels"] if x["id"] == w["level"]), {})
        room = float(lv.get("height", 3.0)) - float(o.get("sill", 0.0) or
                                                     0.0) - 0.3
        h = min(max(float(o["h"]), uw / 2 + 1.2), room)
        for i in range(k):
            rec = {kk: v for kk, v in o.items() if kk not in ("id", "name")}
            rec.update(pos=round(x0 + uw / 2 + i * (uw + pier), 4),
                       w=round(uw, 4), h=round(h, 4), head="arch",
                       arch="semi", arcade=tag, frame="upvc")
            new.append(rec)
        gone.add(o["id"])
        n += 1
    if gone:
        arch["openings"] = [o for o in arch["openings"]
                            if o["id"] not in gone]
        arch["openings"] += M.new_openings(arch["openings"], new)
    return n


def _over_rooms(doc, slab, poly) -> bool:
    """True when the roof slab covers rooms (a guard room, a porch block);
    False for a terrace, a roof terrace or an open deck: those have no
    tiled roof — the model stays as the CAD plan draws it."""
    from . import project as PJ
    from .engine import spaces
    if slab.get("auto_annex"):
        return True
    if str(slab.get("id")) in set(doc.get("roof_terraces") or []):
        return False
    if re.search(r"terrace|balcon|deck|roof garden|sit.?out|patio|court",
                 str(slab.get("name", "")), re.I):
        return False
    try:
        rooms = [r["poly"] for r in spaces.of_level(doc["arch"],
                                                    slab["level"])]
    except Exception:  # noqa: BLE001
        return True
    if not rooms:
        return True
    from shapely.ops import unary_union
    indoor = [r["poly"] for r in spaces.of_level(doc["arch"], slab["level"])
              if not PJ.OUTDOOR_WORDS.search(str(r.get("name") or ""))]
    if not indoor:
        return False
    try:
        return poly.intersection(unary_union(indoor)).area >= 0.5 * poly.area
    except Exception:  # noqa: BLE001
        return True


def annex_roofs(doc, slope=SLOPE, eave=EAVE * 0.75, kind="hip") -> int:
    """A clay-tile hip roof over each single-storey annex (a guard room,
    a porch block: a slab marked as a roof on a lower floor): over its
    rectangle. How many."""
    from shapely.geometry import Polygon
    from .engine import model as M
    from .engine import structure as S
    arch = doc["arch"]
    recs = []
    for e in arch["structure"]:
        if e["type"] != "slab" or not e.get("roof") or \
                len(e.get("corners") or []) < 3:
            continue
        try:
            p = Polygon(e["corners"]).buffer(0)
            r = p.minimum_rotated_rectangle
        except Exception:  # noqa: BLE001
            continue
        if r.geom_type != "Polygon" or p.area < 0.8 * r.area or \
                p.area < 2.0:
            continue
        if not _over_rooms(doc, e, p):      # 3.64.116: a terrace / open
            continue                        # deck stays as the CAD plan
        cs = [[round(x, 4), round(y, 4)]
              for x, y in list(r.exterior.coords)[:4]]
        rec = {"type": "roof", "level": e["level"], "kind": kind,
               "corners": cs, "slope": slope, "overhang": eave, "t": 0.15,
               "ridge": "long", "parapet": 0.0, "pt": 0.15, "tiles": True,
               "look": True, "annex": True}
        if not S.why_not(rec):
            recs.append(rec)
    arch["structure"] = [x for x in arch["structure"]
                         if not (is_look_roof(x) and (x.get("annex") or abs(
                             float(x.get("overhang", 0)) - eave) < 1e-3))]
    if recs:
        arch["structure"] += M.new_elements(arch["structure"], recs)
    return len(recs)


def is_look_roof(e) -> bool:
    """A roof the look made (also one saved before 3.64.47, when the
    «look» mark was not kept: tiled, not read off the CAD, at the look's
    slope and eaves)."""
    if e.get("type") != "roof":
        return False
    if e.get("look"):
        return True
    return bool(e.get("tiles")) and not e.get("from_cad") and \
        abs(float(e.get("slope", 0)) - SLOPE) \
        < 1e-3 and min(abs(float(e.get("overhang", 0)) - EAVE),
                       abs(float(e.get("overhang", 0)) - EAVE * 0.75)) < 1e-3


# 3.64.75: every preset is a style a perspective / the dialog can name
# (before, only five were: the others were silently ignored).
STYLES = dict(STYLES, **{k: v[0] for k, v in PRESETS.items()})


# 3.64.75: which elements belong to which style — the Design dialog greys
# out the others (``relevant``). «all» = every style.
_GENERAL = {"plinth", "bands", "cornice", "fascia", "surrounds", "lanterns",
            "gf_grille", "door_arch", "arcades", "sills_lintels"}
ELEMENT_STYLES = {
    "arch_panels": {"gulf_palace", "arabian", "royal", "royal_villa",
                    "mosque"},
    "quoins": {"royal", "royal_villa", "classical", "neoclassical", "italianate", "mediterranean",
               "georgian", "tudor"},
    "corbels": {"royal", "royal_villa", "mediterranean", "classical", "italianate", "victorian",
                "arabian"},
    "porch_canopy": {"royal", "royal_villa", "mediterranean", "victorian", "tropical", "farmhouse",
                     "capecod", "tudor"},
    "entrance_canopy": {"royal", "royal_villa", "mediterranean", "modern", "contemporary",
                        "farmhouse", "victorian", "capecod", "classical",
                        "neoclassical", "midcentury", "arabian"},
    "medallions": {"royal", "royal_villa", "classical", "neoclassical", "mediterranean", "arabian",
                   "italianate", "georgian"},
    "slab_edges": {"modern", "minimalist", "contemporary", "midcentury",
                   "hightech", "bauhaus", "brutalist"},
    "frame_box": {"modern", "contemporary", "midcentury", "hightech"},
    "incline_panel": {"modern", "contemporary", "hightech"},
    "entry_clad": {"modern", "contemporary", "midcentury"},
    "pediment": {"royal", "royal_villa", "classical", "neoclassical", "georgian", "italianate",
                 "mediterranean"},
    "deco_fins": {"artdeco"}, "deco_bands": {"artdeco"},
    "deco_crown": {"artdeco"},
    "window_boxes": {"brutalist", "contemporary"},
    "half_timber": {"tudor"}, "gf_clad": {"tudor", "midcentury",
                                         "contemporary", "mediterranean"},
    "shutters": {"royal", "royal_villa", "capecod", "georgian", "farmhouse", "tropical",
                 "mediterranean", "tudor", "italianate", "victorian"},
    "siding": {"capecod", "farmhouse", "victorian"},
    "eave_brackets": {"italianate", "victorian", "tudor", "tropical"},
    "brise_soleil": {"modern", "midcentury", "tropical", "hightech",
                     "contemporary", "minimalist", "mosque", "arabian",
                     "industrial"},
    "jali": {"arabian", "mosque", "mediterranean", "contemporary",
             "midcentury", "tropical"},
    "pilasters": {"royal", "royal_villa", "hightech", "classical", "neoclassical", "georgian",
                  "artdeco", "modern", "contemporary", "mosque",
                  "italianate"},
}
STYLE_ONLY = set(ELEMENT_STYLES)


def relevant(style, key) -> bool:
    """Is the element ``key`` one of the style's (else the dialog greys it
    out)? What the style's own preset switches on always is."""
    if key not in ELEMENT_STYLES:
        return True
    if str(style).startswith("mosque"):
        style = "mosque"
    if style in (None, "", "auto", "custom"):
        return True
    if style in ELEMENT_STYLES[key]:
        return True
    return bool(PRESETS.get(style, ("", {}))[1].get(key))
