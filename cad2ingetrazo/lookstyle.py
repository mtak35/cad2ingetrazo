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
          "modern": "Modern (colours only)"}
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

    def med(mask, dflt):
        if mask.sum() < 50:
            return dflt
        return tuple(float(v) / 255 for v in np.median(px[mask], axis=0))
    out = {"wall": med(wall, (0.88, 0.84, 0.76)),
           "roof": med(tile, (0.66, 0.30, 0.22)),
           "metal": med(metal, (0.12, 0.11, 0.10)),
           "tile_share": float(tile.mean())}
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
        e["type"] == "roof" and e.get("look") and e["level"] == lid)]
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
def apply(doc, ref, src=None) -> dict:
    """The perspective's look applied: {"look": style, "roofs", "arched",
    "grilles", "rails", "colours"}."""
    from . import refelev as RE
    if src is None:
        src = RE.source(ref["file"], int(ref.get("page", 1) or 1))
    pal = palette(src["img"])
    style = ref.get("look") if ref.get("look") in STYLES and \
        ref.get("look") != "auto" else detect(pal)
    arch = doc["arch"]
    rep = {"look": style}
    mats = doc.setdefault("materials", {})

    def col(c):
        return [round(float(v), 3) for v in c]
    mats["wall"] = {"name": "Plaster, as the picture", "color": col(pal["wall"])}
    if style == "modern":
        rep["colours"] = "walls"
        return rep
    mats["roof"] = {"name": "Clay tiles, as the picture",
                    "color": col(pal["roof"])}
    mats["site"] = {"name": "Boundary wall, as the picture",
                    "color": col(pal["trim"])}
    rep["colours"] = "walls, roof tiles, boundary"
    levels = arch["levels"]
    from . import project as PJ
    el = PJ.elevations(arch)
    order = sorted(range(len(levels)), key=lambda i: el[i])
    ids = [levels[i]["id"] for i in order]
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    # the roof level: the top level holding only parapets / a stair room
    top = ids[-1]
    roof_lv = top if str(levels[-1].get("name", "")).strip().lower() == \
        "roof" or all(str(w.get("name", "")).lower().startswith(
            ("roof parapet", "roof edge")) or w.get("rail")
            for w in arch["walls"] if w["level"] == top) else None
    under = ids[-2] if roof_lv and len(ids) >= 2 else top
    # 1. the roofs: no parapets up there; hip roofs over the floor below
    #    the roof (and over a stair room on the roof)
    if roof_lv:
        n0 = len(arch["walls"])
        arch["walls"] = [w for w in arch["walls"] if not (
            w["level"] == roof_lv and (str(w.get("name", "")).lower()
                                       .startswith(("roof parapet",
                                                    "roof edge"))
                                       or w.get("rail")))]
        rep["parapets_off"] = n0 - len(arch["walls"])
    n = hip_roofs(doc, under)
    if roof_lv:
        n += hip_roofs(doc, roof_lv)
    rep["roofs"] = n
    doc["settings"]["roof_parapet"] = False
    # 2. windows and doors
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
        if o["kind"] == "window" and w["level"] != gid and \
                0.6 <= wd <= 3.0 and float(o["h"]) >= 0.9:
            if o.get("head") != "arch":
                o["head"] = "arch"
                o["arch"] = "semi"
                n_arch += 1
            o["frame"] = "upvc"
        elif o["kind"] == "window" and w["level"] == gid and wd >= 0.6:
            if o.get("grille") != "ms":
                o["grille"] = "ms"
                n_gr += 1
            o["frame"] = "upvc"
        elif o["kind"] == "door" and wd >= 0.9 and w["level"] == gid:
            if o.get("head") != "arch":
                o["head"] = "arch"
                o["arch"] = "semi"
                n_arch += 1
    rep["arched"] = n_arch
    rep["grilles"] = n_gr
    # 3. the railings and the gate: wrought iron
    n_r = 0
    for w in arch["walls"]:
        if w.get("rail") and w.get("rail") not in ("ms_grill",):
            w["rail"] = "ms_grill"
            n_r += 1
    doc["settings"]["terrace_rail_kind"] = "railing"
    try:
        doc["site"]["gate_color"] = "black"
    except Exception:  # noqa: BLE001
        pass
    rep["rails"] = n_r
    return rep


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
