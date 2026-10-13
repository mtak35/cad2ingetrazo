"""Documentation — the building's drawings on IngeTrazo's sheets.

Community module (GPL-3.0-or-later): the Lite ships without ``docs``; this
one is written for the calls ``ui.py`` makes:

- ``PAPERS``                      the papers the sheets can take;
- ``full_geometry(viewport, on)`` sheets drawn from the WHOLE model;
- ``make(doc, elevations, opts)`` → ``(planes, views, sheets)``, plain
  data: what to cut, what to look at, what goes on which sheet;
- ``commit(viewport, planes, views, sheets, store)`` → ``(made,
  replaced)``: section planes + scenes + sheets in the model, ONE Ctrl+Z
  (with ``store = (key, doc)`` the CAD2IngeTrazo document goes in the same step);
- ``refresh_sheets(window)``, ``is_ours(comp)``, ``open_sheets(win, i)``,
  ``export_pdf(win, path)`` → the sheets that would not draw.

What is made (``opts``: paper, scale «auto» | N, cut, elev, sect, dims,
rooms, prefix):

- a PLAN of every level that has walls: the model cut ``cut`` m over the
  floor (a horizontal section plane: walls, columns and openings cut in
  poché, the level's slab hides the floors below), the rooms' names and
  areas, dimension chains outside the walls — through the openings — and
  the overall sizes, both ANCHORED to the model (they follow it), the
  section marks, and the level's room schedule;
- the four ELEVATIONS, named by the compass (the project's north);
- SECTIONS A-A (across the long side) and B-B (across the short side),
  placed through the openings and the stair holes, plus every section
  line drawn on a plan (``doc["sections"]``);
- level marks on elevations and sections; a title block on every sheet.

The drawings are the host's exact hidden-line pass («vectorial» frames),
so they print sharp at any size and export to DXF line by line.
"""
from __future__ import annotations

import datetime
import math
import uuid

from .host import area_txt  # noqa: E402
PAPERS = ("A1", "A2", "A3", "A4")
#: the scales «auto» picks from (the largest that holds the drawing)
SCALES = (20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000)
#: what marks CAD2IngeTrazo's own sheets, scenes and planes (made again = replaced)
MARK = "CAD2IngeTrazo"
PREFIX = "C2I · "
VIEW_3D = PREFIX + "3D"

MARGIN = 10.0          # mm, the sheet's margin
GAP = 8.0              # mm, around a drawing inside the margin
TB_W, TB_H = 180.0, 33.0   # the title block
TITLE_H = 12.0         # mm under a frame for its title
DIM_ROOM = 20.0        # mm round a plan for its dimension chains
PAD_M = 0.6            # m of model round a drawing inside its frame
MIN_DIM_MM = 1.2       # mm on paper: the shortest dimension in a chain
EXT_M = 0.6            # m: the longest extension line inside the building
DIM_SEP = (7.0, 13.0)  # mm outside the building: the chain, the overall size
#: the pens (paper mm) unless set: cut, profile, edge, dimension
PENS = {"cut": 0.5, "profile": 0.35, "edge": 0.18, "dim": 0.18}


# =====================================================================================
# The whole model for the sheets
# =====================================================================================
def _collect(scene):
    """The hidden-line pass's geometry, read now from the visible
    entities — inside a frame, the layers ITS scene shows (the viewport's
    cached arrays only know what its last paint drew)."""
    import numpy as np
    from core.hlr import collect_geometry
    tris, hard, soft = collect_geometry(scene)
    nan3 = (float("nan"),) * 3
    return (np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3),
            np.asarray(hard, dtype=np.float64).reshape(-1, 2, 3),
            np.asarray([(p0, p1) for p0, p1, _a, _b in soft],
                       dtype=np.float64).reshape(-1, 2, 3),
            np.asarray([(na, nan3 if nb is None else nb)
                        for _p0, _p1, na, nb in soft],
                       dtype=np.float64).reshape(-1, 2, 3))


def _auto_draw_ours() -> None:
    """The composer draws a VECTOR frame only on «Update» (its exact pass
    costs seconds), so a sheet CAD2IngeTrazo made opened blank. Shown, an CAD2IngeTrazo
    sheet now draws its own frames that have no drawing yet — other
    sheets keep the host's behaviour. Installed once, on the class."""
    try:
        from views.composer import ComposerWindow
    except ImportError:
        return
    if getattr(ComposerWindow, "_c2i_auto_draw", False):
        return
    original = ComposerWindow._auto_render_stale

    def auto(self, *a, **k):
        original(self, *a, **k)
        try:
            if not self.isVisible() or not is_ours(self.comp):
                return
            todo = [f for f in self.comp.frames if f.style == "vectorial"
                    and (id(f) not in self.hlr_cache or id(f) in self._stale)]
            if not todo:
                return
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                for f in todo:
                    self.render_frame(f)
            finally:
                QApplication.restoreOverrideCursor()
            self._rebuild_canvas()
        except Exception:  # noqa: BLE001 — «Update» still does it by hand
            from .host import log_error
            log_error("sheets._auto_draw_ours")

    ComposerWindow._auto_render_stale = auto

    # The composer collects the model ONCE for all its frames, under
    # whatever layers the first frame's scene showed — so a plan scene that
    # hides the earth hid it from the elevations too (and a level isolated
    # while modelling went missing from every sheet). One collection per
    # set of visible layers instead: each frame reads what ITS scene shows.
    geom = ComposerWindow._scene_geometry
    inval = ComposerWindow._invalidate_geometry_caches

    def scene_geometry(self):
        scene = self._scene()
        key = tuple(sorted(L.name for L in scene.layers if L.visible))
        cache = self.__dict__.setdefault("_c2i_geom", {})
        if key not in cache:
            self._geom_cache = None
            cache[key] = geom(self)
        self._geom_cache = cache[key]
        return cache[key]

    def invalidate(self, *a, **k):
        self.__dict__.pop("_c2i_geom", None)
        return inval(self, *a, **k)

    ComposerWindow._scene_geometry = scene_geometry

    # A drawing scene (plan, elevation, section) opened in the MODEL cuts
    # it, shows the 2D symbols, hides the earth… and nothing used to undo
    # that: the 3D view stayed cut. Remember what the model showed before
    # it, so tidy_3d can put it back the moment the view is left.
    from core.saved_views import SavedView
    if not getattr(SavedView, "_c2i_remember", False):
        apply = SavedView.apply

        def remembering(self, scene, camera, *a, **k):
            mine = str(self.name).startswith(PREFIX) and self.name != VIEW_3D
            if mine and getattr(scene, "_c2i_before", None) is None:
                scene._c2i_before = {
                    "layers": [(L, L.visible) for L in scene.layers],
                    "hidden": [(g, g.hidden) for g in scene.groups],
                    "section": scene.active_section(),
                    "planes": getattr(scene, "show_section_planes", True)}
            elif self.name == VIEW_3D or not mine:
                rec = getattr(scene, "_c2i_before", None)
                scene._c2i_before = None          # a scene of its own: kept
                out = apply(self, scene, camera, *a, **k)
                if rec is not None and self.name == VIEW_3D:
                    # the clean 3D: what the model hid before the drawing
                    # (the structure inside the walls…) hidden again
                    for g, hid in rec["hidden"]:
                        if g in scene.groups:
                            g.hidden = hid
                return out
            return apply(self, scene, camera, *a, **k)

        SavedView.apply = remembering
        SavedView._c2i_remember = True
    ComposerWindow._invalidate_geometry_caches = invalidate
    ComposerWindow._c2i_auto_draw = True


def _drawing_view(scene, plane):
    """The CAD2IngeTrazo scene that cuts with ``plane``, or None."""
    for v in scene.saved_views:
        sec = getattr(v, "section", None) or {}
        if str(v.name).startswith(PREFIX) and sec.get("active") == plane.uid:
            return v
    return None


def tidy_3d(viewport) -> bool:
    """Every frame (CAD2IngeTrazo's overlay): an CAD2IngeTrazo drawing scene left behind
    by the camera — orbited, another standard view, perspective — gives
    the model back as it was before the scene: uncut, its layers, its
    hidden objects. True when it tidied."""
    scene = viewport.scene
    sp = scene.active_section() if hasattr(scene, "active_section") else None
    before = getattr(scene, "_c2i_before", None)
    if sp is None or not str(getattr(sp, "name", "")).startswith(PREFIX):
        if before is not None and sp is None:
            scene._c2i_before = None           # the composer put it back
        if sp is None:
            # the site plan's notes stay with the site plan: hidden as
            # soon as the camera leaves the top view
            cam = viewport.camera
            if cam.perspective or abs(cam.pitch) < math.radians(80):
                from .host import SITE, ann_layer
                for L in scene.layers:
                    if L.name == ann_layer(SITE) and L.visible:
                        L.visible = False
                        scene.version += 1
        return False
    view = _drawing_view(scene, sp)
    cam = viewport.camera
    if view is not None and not cam.perspective:
        d_pitch = abs(cam.pitch - view.pitch)
        d_yaw = abs((cam.yaw - view.yaw + math.pi) % (2 * math.pi) - math.pi)
        plan = abs(view.pitch) > math.radians(80)
        if d_pitch < math.radians(1.0) and (plan or
                                            d_yaw < math.radians(1.0)):
            return False                       # still looking at it
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, lambda: _restore_3d(viewport))
    return True


def _restore_3d(viewport) -> None:
    scene = viewport.scene
    sp = scene.active_section()
    if sp is None or not str(getattr(sp, "name", "")).startswith(PREFIX):
        return
    before = getattr(scene, "_c2i_before", None)
    from .host import SYMBOL_LAYER, TERRAIN_LAYER, is_ann_layer
    from .host import refresh_host_layers as _refresh_host_layers
    if before is not None:
        for L, vis in before["layers"]:
            L.visible = vis
        for g, hid in before["hidden"]:
            if g in scene.groups:
                g.hidden = hid
        prev = before["section"]
        scene.set_active_section(prev if prev in scene.section_planes
                                 and not str(prev.name).startswith(PREFIX)
                                 else None)
        scene.show_section_planes = before["planes"]
    else:                                      # no record: a clean model
        scene.set_active_section(None)
        for L in scene.layers:
            if L.name == TERRAIN_LAYER:
                L.visible = True
    for L in scene.layers:          # 2D symbols and notes: the plans only
        if L.name == SYMBOL_LAYER or is_ann_layer(L.name):
            L.visible = False
    scene._c2i_before = None
    scene.version += 1
    try:
        _refresh_host_layers(viewport)
    except Exception:  # noqa: BLE001 — the tray catches up on its own
        pass
    viewport.update()


def full_geometry(viewport, on: bool) -> None:
    """The composer collects the model ONCE per refresh, through the
    viewport's fast path — whose arrays hold what the last frame painted
    (a level hidden in CAD2IngeTrazo, the parts switched off…). On: the sheets
    read the whole model instead, under each scene's own visibility."""
    if on:
        _auto_draw_ours()
        if getattr(viewport, "_c2i_full_geometry", False):
            return
        viewport._c2i_full_geometry = True
        viewport.hlr_geometry = lambda: _collect(viewport.scene)
    elif getattr(viewport, "_c2i_full_geometry", False):
        viewport._c2i_full_geometry = False
        try:
            del viewport.hlr_geometry           # the class's own again
        except AttributeError:
            pass


# =====================================================================================
# What is drawn (pure data)
# =====================================================================================
def _points(faces):
    for f in faces:
        loop = f["loop"] if isinstance(f, dict) else f
        for q in loop:
            yield q


def _bbox(elements):
    xs, ys, zs = [], [], []
    for e in elements:
        for q in _points(e["faces"]):
            xs.append(q[0])
            ys.append(q[1])
            zs.append(q[2])
    if not xs:
        return None
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _page(paper: str):
    from core.composition import PAPER_SIZES_MM
    w, h = PAPER_SIZES_MM[paper]
    return (h, w)                                   # landscape


def _zone(paper: str):
    """The drawing zone of a sheet: inside the margin, above the title
    block's row."""
    pw, ph = _page(paper)
    return (MARGIN + GAP, MARGIN + GAP, pw - MARGIN - GAP,
            ph - MARGIN - TB_H - GAP)


def _auto(fits) -> int:
    """The largest scale (smallest N) whose drawing fits."""
    for n in SCALES:
        if fits(n):
            return n
    return SCALES[-1]


def _compass(dx: float, dy: float, north_deg: float) -> str:
    """The compass name of a horizontal direction (project north
    ``north_deg`` clockwise from +Y)."""
    ang = (math.degrees(math.atan2(dx, dy)) - north_deg) % 360.0
    return ("North", "East", "South", "West")[int(((ang + 45) % 360) // 90)]


def _look_view(name, centre, d, plane=None) -> dict:
    """A parallel view looking along the horizontal unit direction ``d``."""
    return {"name": name, "target": centre,
            "yaw": math.atan2(-d[1], -d[0]), "pitch": 0.0, "plane": plane}


def _section_line(doc, walls, openings, holes, box, along_x: bool):
    """Where A-A (across X) / B-B (across Y) cuts: near the middle, never
    inside a wall running with it, through as many openings and stair
    holes as it can."""
    from .engine import walls as W
    x0, y0, _z0, x1, y1, _z1 = box
    lo, hi = (y0, y1) if along_x else (x0, x1)
    mid = (lo + hi) / 2.0
    best = None
    for k in range(-24, 25):
        c = mid + k * 0.1
        if not lo + 0.25 * (hi - lo) <= c <= hi - 0.25 * (hi - lo):
            continue
        bad = False
        for w in walls:
            if w.get("kind", "line") != "line":
                continue
            a, b = w["a"], w["b"]
            if along_x and abs(a[1] - b[1]) < 1e-3:
                if abs(c - (W.centre(w).p0[1])) < w["t"] / 2 + 0.15:
                    bad = True
                    break
            if not along_x and abs(a[0] - b[0]) < 1e-3:
                if abs(c - (W.centre(w).p0[0])) < w["t"] / 2 + 0.15:
                    bad = True
                    break
        if bad:
            continue
        score = 0.0
        for (p, q) in openings:
            v0, v1 = (p[1], q[1]) if along_x else (p[0], q[0])
            if min(v0, v1) - 0.05 <= c <= max(v0, v1) + 0.05:
                score += 1.0
        for h in holes:
            vs = [pt[1] if along_x else pt[0] for pt in h]
            if min(vs) + 0.1 <= c <= max(vs) - 0.1:
                score += 3.0
        score -= abs(k) * 0.02
        if best is None or score > best[0]:
            best = (score, c)
    return best[1] if best else mid


def _opening_spans(doc):
    """Every opening as its two jamb points (plan) on the wall's centre
    line: [(p, q)]."""
    from .engine import walls as W
    walls = {w["id"]: w for w in doc.get("walls") or []}
    out = []
    for o in doc.get("openings") or []:
        w = walls.get(o["wall"])
        if w is None or w.get("kind", "line") != "line":
            continue
        seg = W.centre(w)
        s0, s1 = o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2
        out.append(((seg.p0[0] + seg.u[0] * s0, seg.p0[1] + seg.u[1] * s0),
                    (seg.p0[0] + seg.u[0] * s1, seg.p0[1] + seg.u[1] * s1)))
    return out


def _outline(walls):
    """The level's outside: the union of its walls' plans, its outer
    rings (shapely Polygons)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from .engine import walls as W
    polys = [Polygon(pc["outer"], pc["holes"]).buffer(0)
             for pcs in W.plan(walls).values() for pc in pcs]
    if not polys:
        return []
    u = unary_union(polys).buffer(1e-4, join_style=2).buffer(
        -1e-4, join_style=2)
    return [Polygon(g.exterior).simplify(0.005)
            for g in getattr(u, "geoms", [u]) if g.area > 0.5]


def chains(doc, level_id, z):
    """The plan's dimension chains, as drawn by hand: on each of the four
    sides ONE straight chain — every corner and every opening jamb seen
    from that side, all on one line, parallel to the side, a fixed
    distance outside the building — and outside it the overall size.
    [(points [(x, y, z)…], outward (nx, ny), sep_mm, overall, edge
    point)] — ``edge``: the point of the level's outline furthest out on
    that side (the chain's line is ``sep_mm`` beyond it)."""
    from .engine import walls as W
    walls = [w for w in doc.get("walls") or [] if w["level"] == level_id]
    ids = {w["id"] for w in walls}
    jambs = []
    byid = {w["id"]: w for w in walls}
    for o in doc.get("openings") or []:
        w = byid.get(o["wall"]) if o["wall"] in ids else None
        if w is None or w.get("kind", "line") != "line":
            continue
        seg = W.centre(w)
        for s in (o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2):
            jambs.append(((seg.p0[0] + seg.u[0] * s,
                           seg.p0[1] + seg.u[1] * s), w["t"]))
    rings = _outline(walls)
    if not rings:
        return []
    xs = [v for r in rings for v in (r.bounds[0], r.bounds[2])]
    ys = [v for r in rings for v in (r.bounds[1], r.bounds[3])]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    sides = {(0.0, -1.0): [], (0.0, 1.0): [], (-1.0, 0.0): [],
             (1.0, 0.0): []}
    for poly in rings:
        ring = list(poly.exterior.coords)[:-1]
        n = len(ring)
        if n < 3:
            continue
        ccw = poly.exterior.is_ccw
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            if L < 0.05:
                continue
            ux, uy = dx / L, dy / L
            # outward: right of a → b on a counter-clockwise ring
            nx, ny = (uy, -ux) if ccw else (-uy, ux)
            pts = [a, b]
            for (p, t) in jambs:
                rx, ry = p[0] - a[0], p[1] - a[1]
                s_ = rx * ux + ry * uy
                off = rx * nx + ry * ny
                if 0.05 < s_ < L - 0.05 and abs(off + t / 2) < 0.03:
                    pts.append((a[0] + ux * s_, a[1] + uy * s_))
            for sn, bag in sides.items():
                if nx * sn[0] + ny * sn[1] > 0.3:     # this face looks there
                    bag += pts
    # only what is SEEN from the side: a point with the building in front
    # of it (a recess, a court) would string its extension line right
    # across the plan
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    body = unary_union(rings).buffer(-0.02, join_style=2)
    far = 2.0 + max(x1 - x0, y1 - y0)

    def seen(q, sn):
        a = (q[0] + sn[0] * 0.03, q[1] + sn[1] * 0.03)
        b = (q[0] + sn[0] * far, q[1] + sn[1] * far)
        try:
            return not LineString([a, b]).intersects(body)
        except Exception:  # noqa: BLE001
            return True
    out = []
    for sn, bag in sides.items():
        bag = [q for q in bag if seen(q, sn)]
        horiz = sn[0] == 0.0             # a chain along x (south / north)
        key = (lambda q: q[0]) if horiz else (lambda q: q[1])
        out_of = (lambda q: q[1] * sn[1]) if horiz else \
            (lambda q: q[0] * sn[0])
        bag = sorted(bag, key=key)
        pick = []
        for q in bag:                  # one point per station, the outer
            if pick and abs(key(q) - key(pick[-1])) < 0.05:
                if out_of(q) > out_of(pick[-1]):
                    pick[-1] = q
                continue
            pick.append(q)
        edge = {(0.0, -1.0): (x0, y0), (0.0, 1.0): (x0, y1),
                (-1.0, 0.0): (x0, y0), (1.0, 0.0): (x1, y0)}[sn]
        # short extension lines (fixed length, as drawn by hand): a point
        # set back from the side is measured from just inside the side
        lim = (edge[1] * sn[1] if horiz else edge[0] * sn[0]) - EXT_M
        pick = [((q[0], sn[1] * lim) if horiz else (sn[0] * lim, q[1]))
                if out_of(q) < lim else q for q in pick]
        e3 = (edge[0], edge[1], z)
        if len(pick) > 2:
            out.append(([(q[0], q[1], z) for q in pick], sn, DIM_SEP[0],
                        False, e3))
        if len(pick) >= 2:
            out.append(([(pick[0][0], pick[0][1], z),
                         (pick[-1][0], pick[-1][1], z)], sn, DIM_SEP[1],
                        True, e3))
    return out


def pens_of(opts) -> dict:
    """The sheets' line weights (paper mm) from ``opts`` (``pen_cut``,
    ``pen_profile``, ``pen_edge``, ``pen_dim``), the defaults else."""
    out = {}
    for k, v in PENS.items():
        try:
            out[k] = min(max(float((opts or {}).get("pen_" + k, v) or v),
                             0.05), 3.0)
        except (TypeError, ValueError):
            out[k] = v
    return out


def _set_pens(fr, pens) -> None:
    for k, attr in (("cut", "pen_cut_mm"), ("profile", "pen_profile_mm"),
                    ("edge", "pen_edge_mm")):
        if hasattr(fr, attr):
            setattr(fr, attr, float(pens[k]))


def make(doc: dict, elevations, opts: dict):
    """``(planes, views, sheets)`` — see the module docstring. Empty when
    the building has no walls yet."""
    from .engine import spaces
    from .engine import structure as S

    elements = S.build(doc, elevations)
    if not any(e["kind"] == "wall" for e in elements):
        return [], [], []
    box = _bbox(elements)
    x0, y0, z0, x1, y1, z1 = box
    W_, D_ = x1 - x0, y1 - y0
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    info = S.levels_info(doc, elevations)
    project = doc.get("project") or {}
    north = float(project.get("north_deg", 0.0) or 0.0)
    ground = float(project.get("ground_level", 0.0) or 0.0)
    paper = opts.get("paper") if opts.get("paper") in PAPERS else "A3"
    zx0, zy0, zx1, zy1 = _zone(paper)
    zw, zh = zx1 - zx0, zy1 - zy0
    prefix = str(opts.get("prefix") or "A-")
    cut = float(opts.get("cut", 1.2))
    fixed = str(opts.get("scale", "auto"))
    planes, views, sheets = [], [], []

    # ---- the plans ------------------------------------------------------------------
    levels = [lv for lv in doc["levels"]
              if any(w["level"] == lv["id"] for w in doc["walls"])]
    dims_on = opts.get("dims", "yes") == "yes"
    room = DIM_ROOM if dims_on else 4.0

    def plan_fits(n):
        k = 1000.0 / n
        return ((W_ + 2 * PAD_M) * k + 2 * room <= zw
                and (D_ + 2 * PAD_M) * k + 2 * room + TITLE_H <= zh)

    n_plan = int(fixed) if fixed.isdigit() else _auto(plan_fits)
    for k, lv in enumerate(levels, 1):
        li = info[lv["id"]]
        pname = f"{PREFIX}Plan cut · {lv['name']}"
        planes.append({"name": pname, "point": (cx, cy, li["z0"] + cut),
                       "normal": (0.0, 0.0, 1.0), "symbol": ""})
        vname = f"{PREFIX}Plan · {lv['name']}"
        # a plan shows its own level: the floors below are left out
        from .host import level_layer
        below = [level_layer(o["name"]) for o in doc["levels"]
                 if o["id"] in info and info[o["id"]]["z0"] < li["z0"] - 1e-6]
        # the ground floor's plan shows the boundary wall and gates
        from .host import BOUNDARY_LAYER as _BW
        views.append({"name": vname, "target": (cx, cy, li["z0"]),
                      "yaw": -math.pi / 2, "pitch": math.pi / 2,
                      "plane": pname, "hide": below,
                      "show": [_BW] if lv["kind"] == "ground" else []})
        kz = 1000.0 / n_plan
        # the frame holds the dimension chains round the plan too (so its
        # title sits under them, never on them)
        fw = (W_ + 2 * PAD_M) * kz + 2 * room
        fh = (D_ + 2 * PAD_M) * kz + 2 * room
        fx = zx0 + (zw - fw) / 2
        fy = zy0 + (zh - TITLE_H - fh) / 2
        frame = {"view": vname, "scale": n_plan, "rect": (fx, fy, fw, fh),
                 "title": f"Plan — {lv['name']}", "kind": "plan",
                 "number": str(k)}
        sheet = {"name": f"{prefix}1{k:02d} Plan {lv['name']}",
                 "number": f"{prefix}1{k:02d}", "paper": paper,
                 "title": f"Plan — {lv['name']}", "scale": n_plan,
                 "frames": [frame], "rooms": [], "cotas": [], "levels": [],
                 "note": ""}
        z = li["z0"]
        if opts.get("rooms", "yes") == "yes":
            rooms = spaces.of_level(doc, lv["id"])
            for r in rooms:
                sheet["rooms"].append((0, (r["at"][0], r["at"][1], z),
                                       r["name"], r["area"]))
            mine = [w for w in doc["walls"] if w["level"] == lv["id"]]
            if rooms:
                net = sum(r["area"] for r in rooms)
                rows = "   ·   ".join(f"{r['name']} {area_txt(r['area'])}"
                                      for r in rooms)
                sheet["note"] = (f"ROOMS — {lv['name']}:  {rows}\n"
                                 f"Net {area_txt(net)}   ·   gross "
                                 f"{area_txt(spaces.gross(mine))}")
        if dims_on:
            for ch in chains(doc, lv["id"], z):
                sheet["cotas"].append((0,) + tuple(ch[:3]) + (ch[3], ch[4]))
        sheets.append(sheet)

    # ---- the foundation plan: cut just under the lowest slab --------------------
    foots = [e for e in doc.get("structure") or [] if e["type"] == "footing"]
    if foots and doc["levels"]:
        li = info[doc["levels"][0]["id"]]
        ftop = li["z0"] - li["slab"]
        pname = f"{PREFIX}Plan cut · Foundation"
        planes.append({"name": pname, "point": (cx, cy, ftop - 0.03),
                       "normal": (0.0, 0.0, 1.0), "symbol": ""})
        vname = f"{PREFIX}Plan · Foundation"
        views.append({"name": vname, "target": (cx, cy, ftop),
                      "yaw": -math.pi / 2, "pitch": math.pi / 2,
                      "plane": pname, "hide": []})
        kz = 1000.0 / n_plan
        fw, fh = (W_ + 2 * PAD_M) * kz, (D_ + 2 * PAD_M) * kz
        frame = {"view": vname, "scale": n_plan,
                 "rect": (zx0 + (zw - fw) / 2, zy0 + (zh - TITLE_H - fh) / 2,
                          fw, fh),
                 "title": "Foundation plan", "kind": "plan", "number": "F"}
        from collections import Counter as _C
        kinds_ = _C(f.get("kind", "pad") for f in foots)
        note_ = "   ·   ".join(f"{n} {k}{'s' if n > 1 else ''}"
                               for k, n in kinds_.items())
        deep = max(float(f["d"]) for f in foots)
        sheets.insert(0, {
            "name": f"{prefix}100 Foundation plan", "number": f"{prefix}100",
            "paper": paper, "title": "Foundation plan", "scale": n_plan,
            "frames": [frame], "rooms": [], "cotas": [], "levels": [],
            "note": f"FOUNDATIONS:  {note_}   ·   "
                    f"founding level {ftop - deep:+.2f} m"})

    # ---- the site plan: the plot, its setbacks, the building's roof ------------
    plot = doc.get("plot")
    if plot:
        from .host import SITE, ann_layer as _ann
        xs = [p[0] for p in plot["corners"]] + [x0, x1]
        ys = [p[1] for p in plot["corners"]] + [y0, y1]
        sx0, sx1, sy0, sy1 = min(xs) - 2, max(xs) + 2, min(ys) - 2, max(ys) + 2
        SW, SD = sx1 - sx0, sy1 - sy0

        def site_fits(n):
            k = 1000.0 / n
            return SW * k + 2 * room <= zw and SD * k + 2 * room + TITLE_H <= zh
        n_site = _auto(site_fits) if not fixed.isdigit() else int(fixed)
        if not site_fits(n_site):
            for n_site in (100, 200, 250, 500, 1000, 2000):
                if site_fits(n_site):
                    break
        vname = f"{PREFIX}Site plan"
        views.append({"name": vname, "target": ((sx0 + sx1) / 2,
                                                (sy0 + sy1) / 2, z1),
                      "yaw": -math.pi / 2, "pitch": math.pi / 2,
                      "plane": None, "show": [_ann(SITE)]})
        kz = 1000.0 / n_site
        fw, fh = SW * kz, SD * kz
        frame = {"view": vname, "scale": n_site,
                 "rect": (zx0 + (zw - fw) / 2, zy0 + (zh - TITLE_H - fh) / 2,
                          fw, fh),
                 "title": "Site plan", "kind": "plan", "number": "S"}
        from .engine import plotgeo
        _r, _d, area = plotgeo.setbacks_of(plot)
        dist = plot.get("sb_dist") or {}
        note = (f"PLOT  {area_txt(plotgeo.area(plot['corners']))}   ·   "
                f"perimeter {plotgeo.perimeter(plot['corners']):,.2f} m")
        if area:
            note += (f"\nSETBACKS  front {dist.get('front', 0):.2f} m · back "
                     f"{dist.get('back', 0):.2f} m · sides "
                     f"{dist.get('sides', 0):.2f} m   ·   buildable "
                     f"{area_txt(plotgeo.area(area))}")
        sheets.insert(0, {
            "name": f"{prefix}001 Site plan", "number": f"{prefix}001",
            "paper": paper, "title": "Site plan", "scale": n_site,
            "frames": [frame], "rooms": [], "cotas": [], "levels": [],
            "note": note})

    # ---- elevations and sections: one scale --------------------------------------
    sym = []                      # (symbol, a, b, flip)
    if opts.get("sect", "yes") == "yes":
        holes = [h for s in doc.get("structure") or []
                 if s["type"] == "slab" for h in s.get("holes") or []]
        spans = _opening_spans(doc)
        long_x = W_ >= D_
        ca = _section_line(doc, doc["walls"], spans, holes, box, long_x)
        cb = _section_line(doc, doc["walls"], spans, holes, box, not long_x)
        if long_x:
            sym.append(("A", (x0 - 1, ca), (x1 + 1, ca), False))
            sym.append(("B", (cb, y0 - 1), (cb, y1 + 1), False))
        else:
            sym.append(("A", (ca, y0 - 1), (ca, y1 + 1), False))
            sym.append(("B", (x0 - 1, cb), (x1 + 1, cb), False))
    for s in doc.get("sections") or []:
        sym.append((s["symbol"] or "?", tuple(s["a"]), tuple(s["b"]),
                    bool(s["flip"])))

    # elevations stop a little under the ground (what is under it is not
    # seen from outside); sections go down to the footings
    ground_z = min(0.0, ground)
    e_lo, e_hi = max(z0, ground_z - 0.5), z1
    drawings = []        # {kind, view, title, width, look, lo, hi}
    if opts.get("elev", "yes") == "yes":
        for d in ((0.0, 1.0), (0.0, -1.0), (-1.0, 0.0), (1.0, 0.0)):
            # the facade seen when looking along d faces -d
            face = _compass(-d[0], -d[1], north)
            vname = f"{PREFIX}Elevation · {face}"
            views.append(_look_view(vname, (cx, cy, (e_lo + e_hi) / 2), d))
            drawings.append({"kind": "elev", "view": vname,
                             "title": f"{face} elevation",
                             "width": W_ if d[1] else D_, "look": d,
                             "lo": e_lo, "hi": e_hi})
    for s_, a, b, flip in sym:
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        look = (-dy / L, dx / L)                     # left of a → b
        if flip:
            look = (-look[0], -look[1])
        pname = f"{PREFIX}Section {s_}-{s_}"
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        planes.append({"name": pname, "point": (mx, my, cz),
                       "normal": (-look[0], -look[1], 0.0), "symbol": s_})
        # the target on the cut, over the building's middle along it
        t = ((cx - a[0]) * dx + (cy - a[1]) * dy) / (L * L)
        tx, ty = a[0] + dx * t, a[1] + dy * t
        vname = f"{PREFIX}Section · {s_}-{s_}"
        views.append(_look_view(vname, (tx, ty, cz), look, pname))
        ux, uy = dx / L, dy / L
        ext = [(px - tx) * ux + (py - ty) * uy
               for px in (x0, x1) for py in (y0, y1)]
        drawings.append({"kind": "sect", "view": vname,
                         "title": f"Section {s_}-{s_}",
                         "width": 2 * max(abs(min(ext)), abs(max(ext))),
                         "look": look, "lo": z0, "hi": z1})

    def sizes(dws, n):
        k = 1000.0 / n
        return ([(dw["width"] + 2 * PAD_M) * k for dw in dws],
                [(dw["hi"] - dw["lo"] + 2 * PAD_M) * k for dw in dws])

    def arrangements(dws, n):
        ws, hs = sizes(dws, n)
        stack = (max(ws) + 30 <= zw
                 and sum(hs) + len(dws) * TITLE_H + GAP * (len(dws) - 1)
                 <= zh)
        side = (sum(ws) + 30 * len(dws) + GAP * (len(dws) - 1) <= zw
                and max(hs) + TITLE_H <= zh)
        return stack, side

    # one kind a sheet, two drawings a sheet
    groups = []
    for kind in ("elev", "sect"):
        mine = [dw for dw in drawings if dw["kind"] == kind]
        groups += [mine[i:i + 2] for i in range(0, len(mine), 2)]
    if groups:
        n_el = int(fixed) if fixed.isdigit() else _auto(
            lambda n: all(any(arrangements(g, n)) for g in groups))
        series = {"elev": (2, "Elevations"), "sect": (3, "Sections")}
        count = {"elev": 0, "sect": 0}
        for g in groups:
            kind = g[0]["kind"]
            count[kind] += 1
            ser, label = series[kind]
            number = f"{prefix}{ser}{count[kind]:02d}"
            ws, hs = sizes(g, n_el)
            stack, side = arrangements(g, n_el)
            # wide drawings stack, tall ones stand side by side
            side = side and (not stack or max(ws) <= max(hs))
            frames = []
            if side:
                total = sum(ws) + GAP * (len(g) - 1)
                fx = zx0 + (zw - total) / 2
                for dw, fw, fh in zip(g, ws, hs):
                    frames.append({"rect": (fx, zy0 + (zh - TITLE_H - fh) / 2,
                                            fw, fh)})
                    fx += fw + GAP
            else:
                total = sum(hs) + len(g) * TITLE_H + GAP * (len(g) - 1)
                fy = zy0 + (zh - total) / 2
                for dw, fw, fh in zip(g, ws, hs):
                    frames.append({"rect": (zx0 + (zw - fw) / 2, fy, fw, fh)})
                    fy += fh + TITLE_H + GAP
            for i, (fr, dw) in enumerate(zip(frames, g), 1):
                fr.update(view=dw["view"], scale=n_el, title=dw["title"],
                          kind=kind, number=str(i))
            sheet = {"name": f"{number} {label}", "number": number,
                     "paper": paper, "title": " · ".join(dw["title"]
                                                         for dw in g),
                     "scale": n_el, "frames": frames, "rooms": [],
                     "cotas": [], "levels": [], "note": ""}
            # level marks: every level's floor (that the drawing shows),
            # at the drawing's right
            for fi, dw in enumerate(g):
                look = dw["look"]
                right = (look[1], -look[0])                # the page's right
                ext = max(((px, py) for px in (x0, x1) for py in (y0, y1)),
                          key=lambda p: p[0] * right[0] + p[1] * right[1])
                marks = [(info[lv["id"]]["z0"], lv["name"])
                         for lv in doc["levels"]]
                marks.append((max(info[lv["id"]]["z0"] + lv["height"]
                                  for lv in doc["levels"]), "Top"))
                for z, name in marks:
                    if dw["lo"] - 1e-6 <= z <= dw["hi"] + 1e-6:
                        sheet["levels"].append((fi, (ext[0], ext[1], z),
                                                name, ground))
            sheets.append(sheet)

    # every sheet: what the title block reads, its pens
    date = project.get("date") or datetime.date.today().isoformat()
    pens = pens_of(opts)
    for s in sheets:
        s["pens"] = dict(pens)
        s["block"] = [["PROJECT", project.get("name") or "CAD2IngeTrazo project"],
                      ["CLIENT", project.get("client") or ""],
                      ["DRAWING", s["title"]],
                      ["SCALE", f"1:{s['scale']}"],
                      ["DATE", date],
                      ["DRAWN", project.get("author") or ""],
                      ["LOCATION", project.get("location") or ""],
                      ["SHEET", s["number"]]]
    # a north arrow on every sheet with a plan (the plans sit with the
    # model's +Y up: the arrow turns by the project north)
    if opts.get("north", "yes") == "yes":
        for sh in sheets:
            if any(f.get("kind") == "plan" for f in sh["frames"]):
                sh["north"] = north
    return planes, views, sheets


# =====================================================================================
# Into the model — one Ctrl+Z
# =====================================================================================
def is_ours(comp) -> bool:
    """A sheet CAD2IngeTrazo made (its hidden marker text)."""
    return any(getattr(t, "list_name", "") == MARK
               for t in getattr(comp, "texts", ()) or ())


def _camera_for(view: dict, frame):
    """An OrbitCamera exactly as the composer sets it up for ``frame``
    bound to ``view`` (parallel, its scale)."""
    from PySide6.QtGui import QVector3D

    from core.camera import OrbitCamera
    from core.composition import ortho_distance_for_height
    cam = OrbitCamera()
    cam.target = QVector3D(*view["target"])
    cam.yaw = float(view["yaw"])
    cam.pitch = float(view["pitch"])
    cam.up = QVector3D(0.0, 0.0, 1.0)
    w_px, h_px = frame.render_px()
    cam.aspect = w_px / h_px
    cam.perspective = False
    cam.distance = ortho_distance_for_height(frame.model_height_m(),
                                             cam.fov_deg)
    return cam


def _projector(view: dict, frame):
    """World (x, y, z) → page mm through ``frame`` showing ``view``."""
    import numpy as np

    from core.composition import frame_page_projector
    from core.hlr import _to_cam, camera_basis
    cam = _camera_for(view, frame)
    e, r, u, f = camera_basis(cam)
    local = frame_page_projector(frame, cam)

    def to_page(p):
        c = _to_cam(np.asarray([p], dtype=np.float64), e, r, u, f)[0]
        px, py = local(float(c[0]), float(c[1]), float(c[2]))
        return (frame.x_mm + px, frame.y_mm + py)
    return to_page


def _build_sheet(s: dict, views: dict):
    """A Composicion from a sheet's data (frames, labels, cotas, levels,
    title block, the room schedule)."""
    from core.composition import (Composicion, CotaItem, MarcoVista,
                                  NivelItem, TextoItem)
    comp = Composicion(name=s["name"], paper=s["paper"], landscape=True,
                       margin_mm=MARGIN)
    comp.border = True
    comp.border_mm = 0.5
    pens = dict(PENS, **(s.get("pens") or {}))
    proj = []
    for f in s["frames"]:
        x, y, w, h = f["rect"]
        fr = MarcoVista(x_mm=x, y_mm=y, w_mm=w, h_mm=h,
                        scale_n=float(f["scale"]),
                        view_key="scene:" + f["view"], style="vectorial",
                        paper_bg=True, show_title=True,
                        title_text=f["title"], title_number=f["number"],
                        title_sheet=s["number"], title_scale=True,
                        uid=uuid.uuid4().hex,
                        section_marks=f["kind"] == "plan",
                        cut_fill="solid", cut_fill_color="#3c4048")
        _set_pens(fr, pens)
        comp.frames.append(fr)
        proj.append((fr, _projector(views[f["view"]], fr)))
    # rooms: name over area, at the room's label point
    for fi, p, name, area in s["rooms"]:
        fr, to_page = proj[fi]
        px, py = to_page(p)
        comp.texts.append(TextoItem(x_mm=px - 15.0, y_mm=py - 3.2, w_mm=30.0,
                                    text=f"{name}\n{area_txt(area)}",
                                    size_pt=7.0, align="center",
                                    frame_uid=fr.uid, follow=True,
                                    list_name=f"Room {name}"))
    # dimension chains, anchored to the frame's model: each chain on ONE
    # straight line (the host's horizontal / vertical dimension: the
    # extension lines reach each real point), its short dimensions'
    # figures staggered so none sits on another
    has_axis = hasattr(CotaItem(), "axis")
    for c in s["cotas"]:
        fi, pts, nrm, sep = c[0], c[1], c[2], c[3]
        overall = len(c) > 4 and c[4]
        edge = c[5] if len(c) > 5 else None
        fr, to_page = proj[fi]
        if not overall and len(pts) > 2:
            # stations closer than MIN_DIM_MM on paper: one (the chain
            # still adds up — only a crowded figure goes)
            ax_ = 0 if abs(nrm[0]) < 0.5 else 1      # along the chain
            mm = 1000.0 / float(fr.scale_n)

            def gap(p_, q_):
                return abs(p_[ax_] - q_[ax_]) * mm
            kept = [pts[0]]
            for q in pts[1:-1]:
                if gap(q, kept[-1]) >= MIN_DIM_MM:
                    kept.append(q)
            if len(kept) > 1 and gap(pts[-1], kept[-1]) < MIN_DIM_MM:
                kept.pop()
            pts = kept + [pts[-1]]
        segs = [(pts[0], pts[-1])] if overall else list(zip(pts, pts[1:]))
        axis, base = "", None
        if edge is not None and has_axis:
            pe = to_page(edge)
            q = to_page((edge[0] + nrm[0], edge[1] + nrm[1], edge[2]))
            ox, oy = q[0] - pe[0], q[1] - pe[1]
            Lo = math.hypot(ox, oy) or 1.0
            ox, oy = ox / Lo, oy / Lo
            if abs(ox) < abs(oy):
                axis, base = "h", pe[1] + oy * sep
            else:
                axis, base = "v", pe[0] + ox * sep
        short = 0
        for a, b in segs:
            pa, pb = to_page(a), to_page(b)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            if axis == "h":
                L = abs(dx)
            elif axis == "v":
                L = abs(dy)
            else:
                L = math.hypot(dx, dy)
            if L < 0.4:
                continue
            kw = {}
            if axis:
                kw["axis"] = axis
                sep_c = base - (pa[1] if axis == "h" else pa[0])
                out_dir = (oy if axis == "h" else ox)
            else:
                Lh = math.hypot(dx, dy)
                q = to_page((a[0] + nrm[0], a[1] + nrm[1], a[2]))
                ox_, oy_ = q[0] - pa[0], q[1] - pa[1]
                nx, ny = -dy / Lh, dx / Lh
                sep_c = sep if nx * ox_ + ny * oy_ > 0 else -sep
                out_dir = 1.0
            # a figure longer than its dimension: lifted clear of the
            # neighbour's, every other one
            label_w = 6 * 2.0 * 0.62 + 2.0
            if L < label_w:
                short += 1
                if short % 2 == 0:
                    if axis == "h":
                        kw["text_dy_mm"] = out_dir * 3.0
                    elif axis == "v":
                        kw["text_dx_mm"] = out_dir * 3.0
            else:
                short = 0
            cot = CotaItem(
                x_mm=pa[0], y_mm=pa[1], dx_mm=dx, dy_mm=dy,
                scale_n=fr.scale_n, sep_mm=sep_c, offset_mm=0.5,
                text_mm=2.0, decimals=2, units="m", ends="tick",
                stroke_mm=float(pens["dim"]), text_pos="above",
                text_along="middle", text_align="aligned")
            # NOT anchored: the composer re-snaps an anchored dimension's
            # ends to the nearest drawn point (up to half a metre away at
            # 1:200), which pulled the chains out of line — «Make sheets»
            # draws them again from the model
            for k_, v_ in kw.items():
                try:
                    setattr(cot, k_, v_)
                except Exception:  # noqa: BLE001
                    pass
            comp.cotas.append(cot)
    # level marks, right of the drawing
    for fi, p, name, datum in s["levels"]:
        fr, to_page = proj[fi]
        px, py = to_page(p)
        apex_x = max(px, fr.x_mm + fr.w_mm - 2.0) + 4.0
        comp.niveles.append(NivelItem(
            x_mm=apex_x, y_mm=py, ax_mm=px - apex_x, ay_mm=0.0,
            symbol="triangle", text=f"{name} {{z}}", datum_m=datum,
            decimals=2, size_mm=2.2, line_mm=18.0, anchor_uid=fr.uid,
            a_world=list(p), uid=uuid.uuid4().hex))
    # the title block, and the room schedule beside it
    tb = comp.default_cajetin()
    tb.campos = [list(r) for r in s["block"]]
    tb.columns = 2
    comp.cajetin = tb
    if s.get("note"):
        pw, ph = comp.page_size_mm()
        comp.texts.append(TextoItem(
            x_mm=MARGIN + 3.0, y_mm=ph - MARGIN - TB_H + 2.0,
            w_mm=pw - 2 * MARGIN - TB_W - 9.0, text=s["note"], size_pt=7.0,
            list_name="Room schedule"))
    # the north arrow, top right of the drawing zone
    if s.get("north") is not None:
        try:
            from core.composition import FlechaNorte
            pw, ph = comp.page_size_mm()
            comp.nortes.append(FlechaNorte(
                x_mm=pw - MARGIN - GAP - 20.0, y_mm=MARGIN + GAP + 4.0,
                size_mm=16.0, angle_deg=float(s["north"]),
                list_name="North"))
        except Exception:  # noqa: BLE001 — a host without north arrows
            pass
    # the marker: CAD2IngeTrazo made this sheet (made again = replaced)
    comp.texts.append(TextoItem(x_mm=0.0, y_mm=0.0, w_mm=10.0, text=MARK,
                                size_pt=1.0, hidden=True, list_name=MARK))
    return comp


def commit(viewport, planes, views, sheets, store=None):
    """See :func:`swap_command` — executed as its own Ctrl+Z."""
    from core.history import CompoundCommand, SetPluginDataCommand
    cmd, made, replaced = swap_command(viewport, planes, views, sheets)
    cmds = [cmd]
    if store is not None:
        cmds.append(SetPluginDataCommand(store[0], store[1]))
    viewport.history.execute(CompoundCommand(cmds))
    err = getattr(viewport.history, "last_error", None)
    if err:
        raise RuntimeError(err)
    viewport.update()
    return made, replaced


def swap_command(viewport, planes, views, sheets, bbox=None,
                 ann_layers=None):
    """The command that puts the drawings in the model in place of the
    previous ones: section planes, scenes, sheets. The user's own sheets,
    scenes and planes are never touched. ``sheets=None``: the planes and
    scenes only, the sheets left as they are. ``bbox``: (lo, hi) of the
    building, for the 3D scene (else the model's bounds). Returns
    ``(command, sheets made, sheets replaced)``."""
    from PySide6.QtGui import QVector3D

    from core.history import Command
    from core.saved_views import SavedView
    from core.section import SectionPlane

    scene = viewport.scene
    new_planes = {}
    for p in planes:
        new_planes[p["name"]] = SectionPlane(QVector3D(*p["point"]),
                                             QVector3D(*p["normal"]),
                                             name=p["name"],
                                             symbol=p["symbol"])
    new_views = []
    vmap = {}
    for v in views:
        # a plan shows the building, not the earth cut round a basement
        # a plan shows its own level's notes; every other drawing none,
        # and no 2D door symbols outside the plans
        from .host import SYMBOL_LAYER as _SYM, ann_layer, is_ann_layer
        from .host import dim_layer, text_layer
        plan = v["name"].startswith(f"{PREFIX}Plan · ")
        anns = list(ann_layers) if ann_layers is not None else \
            [L.name for L in scene.layers if is_ann_layer(L.name)]
        from .host import TERRAIN_LAYER as _TER
        if plan:
            lvname = v["name"][len(f"{PREFIX}Plan · "):]
            own = {ann_layer(lvname), text_layer(lvname),
                   dim_layer(lvname)}
            hidden = [n for n in anns if n not in own] + \
                list(v.get("hide", []))
        else:
            hidden = anns + [_SYM]
        # the plot's ground: the site plan and the 3D only
        if v["name"] != f"{PREFIX}Site plan":
            from .host import BOUNDARY_LAYER as _BND
            hidden += [_TER, _BND]
        hidden = [n for n in hidden if n not in v.get("show", ())]
        sv = SavedView(v["name"], target=tuple(v["target"]), distance=30.0,
                       yaw=v["yaw"], pitch=v["pitch"], perspective=False,
                       hidden_layers=hidden)
        plane = new_planes.get(v.get("plane"))
        sv.section = {"active": plane.uid if plane else None,
                      "planes_shown": False, "cuts_shown": True}
        sv.hidden_objects = []
        new_views.append(sv)
        vmap[v["name"]] = v
    new_comps = [_build_sheet(s, vmap) for s in sheets or []]
    # «CAD2IngeTrazo · 3D»: the whole model, uncut, the 2D plan symbols off —
    # double-click it to be back in a clean 3D view from any drawing
    from .host import SYMBOL_LAYER, is_ann_layer
    lo, hi = bbox if bbox is not None else scene.bounds()
    if lo is not None:
        import math as _m
        c = ((lo.x() + hi.x()) / 2, (lo.y() + hi.y()) / 2,
             (lo.z() + hi.z()) / 2)
        diag = _m.dist((lo.x(), lo.y(), lo.z()), (hi.x(), hi.y(), hi.z()))
        v3 = SavedView(VIEW_3D, target=c, distance=max(diag * 1.3, 10.0),
                       yaw=_m.radians(-60.0), pitch=_m.radians(28.0),
                       perspective=True,
                       hidden_layers=[SYMBOL_LAYER] + (
                           list(ann_layers) if ann_layers is not None else
                           [L.name for L in scene.layers
                            if is_ann_layer(L.name)]))
        v3.section = {"active": None, "planes_shown": False,
                      "cuts_shown": True}
        new_views.insert(0, v3)

    keep_sheets = sheets is None
    if keep_sheets:
        new_comps = []
    old_comps = [] if keep_sheets else \
        [c for c in scene.compositions if is_ours(c)]
    old_views = [v for v in scene.saved_views if v.name.startswith(PREFIX)]
    old_planes = [p for p in getattr(scene, "section_planes", [])
                  if str(p.name).startswith(PREFIX)]

    class _Swap(Command):
        def do(self, sc) -> None:
            self.at = sc.compositions.index(old_comps[0]) if old_comps \
                and old_comps[0] in sc.compositions else len(sc.compositions)
            self.active = sc.active_section()
            # the planes only serve the sheets' scenes: not drawn in 3D
            self.shown = getattr(sc, "show_section_planes", True)
            sc.show_section_planes = False
            sc.compositions[:] = [c for c in sc.compositions
                                  if c not in old_comps]
            at = min(self.at, len(sc.compositions))
            sc.compositions[at:at] = new_comps
            sc.saved_views[:] = [v for v in sc.saved_views
                                 if v not in old_views] + new_views
            sc.section_planes[:] = [p for p in sc.section_planes
                                    if p not in old_planes] \
                + list(new_planes.values())
            if self.active in old_planes:
                sc.set_active_section(None)
            sc.version += 1

        def undo(self, sc) -> None:
            sc.compositions[:] = [c for c in sc.compositions
                                  if c not in new_comps]
            at = min(self.at, len(sc.compositions))
            sc.compositions[at:at] = old_comps
            sc.saved_views[:] = [v for v in sc.saved_views
                                 if v not in new_views] + old_views
            sc.section_planes[:] = [p for p in sc.section_planes
                                    if p not in new_planes.values()] \
                + old_planes
            if self.active is not None and self.active in sc.section_planes:
                sc.set_active_section(self.active)
            sc.show_section_planes = self.shown
            sc.version += 1

    return _Swap(), len(new_comps), len(old_comps)


# =====================================================================================
# The host's sheet window
# =====================================================================================
def refresh_sheets(window) -> None:
    """The composer (if open) follows the new sheets: its list, its
    current sheet, fresh drawings."""
    comp = getattr(window, "_composer", None)
    if comp is not None:
        try:
            comps = comp._scene().compositions
            if comp.comp not in comps and comps:
                ours = [c for c in comps if is_ours(c)]
                comp.comp = (ours or comps)[0]
            inval = getattr(comp, "_invalidate_geometry_caches", None)
            if inval:
                inval()
            for name in ("render_cache", "hlr_cache", "annot_cache",
                         "hlr_kinds", "hlr_fills"):
                cache = getattr(comp, name, None)
                if isinstance(cache, dict):
                    cache.clear()
            comp._reload_comp_combo()
            comp._rebuild_canvas()
        except Exception:  # noqa: BLE001 — the composer re-reads on show
            from .host import log_error
            log_error("sheets.refresh_sheets")
    sync = getattr(window, "_refresh_sheet_tabs", None)
    if sync is not None:
        sync()


def apply_pens(win, scene, pens) -> int:
    """New line weights on the sheets already made (CAD2IngeTrazo's): the
    drawings' cut / profile / edge pens and the dimensions' line. Returns
    how many sheets changed."""
    n = 0
    for comp in scene.compositions:
        if not is_ours(comp):
            continue
        for fr in comp.frames:
            _set_pens(fr, pens)
        for c in getattr(comp, "cotas", []) or []:
            c.stroke_mm = float(pens["dim"])
        n += 1
    scene.version += 1
    refresh_sheets(win)
    return n


# ---- zoom on the sheets: the wheel (no Ctrl needed) and buttons ------------
def install_zoom(win) -> None:
    """The sheet window zooms like a CAD: the mouse wheel zooms in / out
    round the cursor (Shift + wheel scrolls), and a small bar in its top
    right corner: − / + / fit the page / fit the width / 100 %."""
    comp = getattr(win, "_composer", None)
    view = getattr(comp, "_view", None)
    if comp is None or view is None or getattr(comp, "_c2i_zoom", None):
        return
    from PySide6.QtCore import QEvent, QObject, Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton
    from PySide6.QtWidgets import QGraphicsView

    def zoom(f, at=None):
        try:
            if at is not None:
                old = view.transformationAnchor()
                view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
                view.scale(f, f)
                view.setTransformationAnchor(old)
                comp.update_zoom_label()
            else:
                comp.set_zoom(comp.zoom_percent() * f)
        except Exception:  # noqa: BLE001
            pass

    class _Wheel(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() != QEvent.Wheel:
                return False
            mods = ev.modifiers()
            if mods & (Qt.ControlModifier | Qt.ShiftModifier |
                       Qt.AltModifier):
                return False           # Ctrl: the host's; Shift: scroll
            if getattr(comp, "view_edit_item", None) is not None:
                return False           # zooming INSIDE a drawing
            dy = ev.angleDelta().y()
            if not dy:
                return False
            zoom(1.2 ** (dy / 120.0), at=True)
            return True

    filt = _Wheel(comp)
    view.viewport().installEventFilter(filt)
    bar = QFrame(view)
    bar.setObjectName("c2iZoomBar")
    bar.setStyleSheet("#c2iZoomBar{background:rgba(255,255,255,225);"
                      "border:1px solid #9aa3ad;border-radius:4px}"
                      "QToolButton{min-width:26px;padding:2px 4px}")
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(3, 2, 3, 2)
    lay.setSpacing(2)
    for text, tip, fn in (("−", "Zoom out", lambda: zoom(1 / 1.25)),
                          ("+", "Zoom in", lambda: zoom(1.25)),
                          ("Fit", "The whole sheet", comp.zoom_fit_page),
                          ("↔", "Fit the width", comp.zoom_fit_width),
                          ("100%", "True paper size",
                           lambda: comp.set_zoom(100.0))):
        b = QToolButton(bar)
        b.setText(text)
        b.setToolTip(tip + "  ·  the mouse wheel zooms round the cursor "
                     "(Shift + wheel scrolls)")
        b.clicked.connect(lambda _=False, f=fn: f())
        lay.addWidget(b)
    bar.adjustSize()

    class _Place(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() in (QEvent.Resize, QEvent.Show):
                try:
                    sb = view.verticalScrollBar()
                    w = sb.width() if sb.isVisible() else 0
                    bar.move(max(view.width() - bar.width() - w - 10, 4), 8)
                    bar.raise_()
                except Exception:  # noqa: BLE001
                    pass
            return False
    plc = _Place(comp)
    view.installEventFilter(plc)
    bar.show()
    bar.move(max(view.width() - bar.width() - 30, 4), 8)
    comp._c2i_zoom = (filt, plc, bar)


def hook_composer(win) -> None:
    """Every time the host makes / opens its sheet window: the zoom tools
    on it."""
    if getattr(win, "_c2i_comp_hook", False):
        install_zoom(win)
        return
    orig = getattr(win, "_ensure_composer", None)
    if orig is not None:
        def ensure(*a, **k):
            c = orig(*a, **k)
            try:
                install_zoom(win)
            except Exception:  # noqa: BLE001
                pass
            return c
        win._ensure_composer = ensure
    win._c2i_comp_hook = True
    install_zoom(win)


def open_sheets(win, first: int = 0) -> None:
    """The composer on sheet ``first``."""
    show = getattr(win, "_show_sheet", None)
    if show is not None:
        show(first)
        install_zoom(win)
        return
    win._on_open_composer()
    win._composer.show_sheet(first)
    install_zoom(win)


def export_pdf(win, path: str) -> list:
    """Every sheet into ONE PDF (the host's atlas), each at its paper
    size. Returns the names of the sheets with a drawing that would not
    render (they print «update the view»)."""
    comp = win._ensure_composer() if hasattr(win, "_ensure_composer") \
        else None
    if comp is None:
        win._on_open_composer()
        comp = win._composer
    refresh_sheets(win)
    return list(comp.export_all_pdf(path) or [])
