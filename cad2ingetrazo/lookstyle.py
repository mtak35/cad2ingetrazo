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

STYLES = {"auto": "Auto (from the picture)",
          "mediterranean": "Mediterranean / Spanish villa",
          "modern": "Modern (glass, black frames, sconces)"}
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
    body = unary_union([LineString([w["a"][:2], w["b"][:2]]).buffer(
        float(w["t"]) / 2 + 0.02, cap_style=2) for w in ws])
    shells = [Polygon(p.exterior) for p in getattr(body, "geoms", [body])
              if p.geom_type == "Polygon" and p.area > 4.0]
    if not shells:
        return None, ws
    return unary_union(shells), ws


def hip_roofs(doc, lid, slope=SLOPE, eave=EAVE) -> int:
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
        rec = {"type": "roof", "level": lid, "kind": "hip", "corners": cs,
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
}
OFF = {k: False for k, v in KIT_DEFAULT.items() if isinstance(v, bool)}
#: the presets the designer offers
PRESETS = {
    "mediterranean": ("Mediterranean / Spanish villa", {}),
    "classical": ("Classical (flat roof, cornices, columns)", {
        "roof": "asdrawn", "win_head": "flat", "gf_grille": False,
        "door_arch": True, "arcades": False, "rail": "asdrawn",
        "columns": "corinthian", "porch_canopy": False, "medallions": True,
        "wall": [0.93, 0.91, 0.86], "trim": [0.98, 0.97, 0.94],
        "stone": [0.80, 0.77, 0.71]}),
    "modern": ("Modern (clean box, glass railings, black frames)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "black",
        "rail": "glass", "columns": "asdrawn", "win_style": "modern_grid",
        "light_style": "sconce", "lanterns": True, "fascia": True,
        "slab_edges": True, "frame_box": True, "entry_clad": True,
        "wall": [0.92, 0.92, 0.90], "trim": [0.30, 0.30, 0.32],
        "stone": [0.45, 0.45, 0.47], "metal": [0.12, 0.12, 0.13],
        "gate_color": "charcoal"}),
    "contemporary": ("Contemporary (bands, stone plinth, glass)", {
        **OFF, "roof": "asdrawn", "win_head": "flat", "win_frame": "black",
        "rail": "glass_post", "columns": "asdrawn", "plinth": True,
        "bands": True, "surrounds": True, "win_style": "side_lights",
        "light_style": "sconce", "lanterns": True, "fascia": True,
        "wall": [0.86, 0.84, 0.80], "trim": [0.35, 0.33, 0.31],
        "stone": [0.50, 0.46, 0.42]}),
}
SIDE_DIR = {"north": (0.0, 1.0), "south": (0.0, -1.0), "east": (1.0, 0.0),
            "west": (-1.0, 0.0)}


def preset(name) -> dict:
    return dict(KIT_DEFAULT, **PRESETS.get(name, ("", {}))[1], style=name)


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
    return apply_kit(doc, kit_from_picture(pal, style))


def apply_kit(doc, kit) -> dict:
    """The elevation kit applied to the model as the plans draw it (sizes
    and positions stay): roofs, windows, doors, railings, columns,
    colours; its mouldings are drawn at every rebuild (ornament.py)."""
    k = dict(KIT_DEFAULT, **(kit or {}))
    if isinstance(k.get("roof"), list):      # a look saved by 3.64.49/50:
        k["roof_c"], k["roof"] = k["roof"], "hip"     # «roof» its colour
    arch = doc["arch"]
    rep = {"look": k.get("style", "custom")}
    mats = doc.setdefault("materials", {})
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
    arch["structure"] = [e for e in arch["structure"] if not is_look_roof(e)]
    if k["roof"] == "hip":
        mats["roof"] = {"name": "Clay tiles, as designed",
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
                      float(k["roof_eave"]))
        if roof_lv:
            n += hip_roofs(doc, roof_lv, float(k["roof_slope"]),
                           float(k["roof_eave"]))
        if k["annex_roof"]:
            n += annex_roofs(doc, float(k["roof_slope"]),
                             float(k["roof_eave"]) * 0.75)
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
    # 5. the outside free-standing columns
    if k["columns"] != "asdrawn":
        from . import ornament as OR_
        rep["columns"] = OR_.classical_columns(doc, k["columns"])
    return rep


def remove_kit(doc) -> None:
    """The design taken off: the roofs it made gone, the look cleared (the
    rest comes back as drawn at the next «Update from CAD»)."""
    doc["arch"]["structure"] = [e for e in doc["arch"]["structure"]
                                if not is_look_roof(e)]
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


def annex_roofs(doc, slope=SLOPE, eave=EAVE * 0.75) -> int:
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
        cs = [[round(x, 4), round(y, 4)]
              for x, y in list(r.exterior.coords)[:4]]
        rec = {"type": "roof", "level": e["level"], "kind": "hip",
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
