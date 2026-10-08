"""The drawings to DXF — one file per CAD2IngeTrazo sheet, true size in metres.

Community module (GPL-3.0-or-later): the Lite ships without ``docsdxf``;
``ui.export_dxf`` calls

    export_all(window, doc, elevations, folder, opts) -> [paths written]

Each sheet CAD2IngeTrazo made becomes ``<sheet name>.dxf`` (AutoCAD 2010, units
metres) holding its drawings at 1:1 — a plan in the model's own X / Y, an
elevation or a section as distance along it by TRUE elevation — side by
side when a sheet has two. The lines come from the same exact hidden-line
pass the sheet prints, on one layer per line weight:

    A-CUT      what the plan / section cuts         0.50 mm
    A-PROFILE  outlines against the background      0.35 mm
    A-EDGE     the edges between faces              0.18 mm
    A-HIDDEN   hidden lines (when the frame shows them), dashed
    A-ROOM     room names and areas (plans)
    A-DIMS     the sheet's dimension chains, as real DIMENSION entities
    A-LEVEL    level marks (elevations, sections)
    A-TITLE    each drawing's title and scale

Nothing here touches the model: the composer draws, this writes.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .host import area_txt  # noqa: E402
LAYERS = {  # name: (ACI colour, lineweight in 1/100 mm, linetype)
    "A-CUT": (7, 50, "CONTINUOUS"),
    "A-PROFILE": (7, 35, "CONTINUOUS"),
    "A-EDGE": (8, 18, "CONTINUOUS"),
    "A-HIDDEN": (8, 13, "DASHED"),
    "A-ROOM": (3, 18, "CONTINUOUS"),
    "A-DIMS": (2, 13, "CONTINUOUS"),
    "A-LEVEL": (5, 18, "CONTINUOUS"),
    "A-TITLE": (7, 25, "CONTINUOUS"),
}
GAP_M = 6.0           # m between two drawings of one sheet


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "sheet"


def _new_doc():
    import ezdxf
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 6                                    # metres
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 0.5
    for name, (color, lw, lt) in LAYERS.items():
        doc.layers.add(name, color=color, lineweight=lw,
                       linetype=lt if lt in doc.linetypes else "CONTINUOUS")
    style = doc.dimstyles.duplicate_entry("EZ_M_100_H25_CM", "ARCHXQ") \
        if "EZ_M_100_H25_CM" in doc.dimstyles else None
    return doc, (style.dxf.name if style is not None else "Standard")


def _frame_basis(view_key: str, scene):
    """(kind, level name or None, right (x, y)) of a frame's CAD2IngeTrazo view."""
    from . import sheets as docs
    name = view_key[len("scene:"):] if view_key.startswith("scene:") \
        else view_key
    if not name.startswith(docs.PREFIX):
        return None
    rest = name[len(docs.PREFIX):]
    view = next((v for v in scene.saved_views if v.name == name), None)
    if view is None:
        return None
    if rest.startswith("Plan · "):
        return "plan", rest[len("Plan · "):], (1.0, 0.0)
    # looking along (-cos yaw, -sin yaw): the page's right is (dy, -dx)
    dx, dy = -math.cos(view.yaw), -math.sin(view.yaw)
    return ("sect" if rest.startswith("Section") else "elev"), None, (dy, -dx)


def export_all(window, doc: dict, elevations, folder, opts: dict) -> list:
    """Every CAD2IngeTrazo sheet to its own DXF in ``folder``; the paths written."""
    import numpy as np

    from core.hlr import KIND_CUT, KIND_EDGE, KIND_HIDDEN, KIND_PROFILE

    from . import sheets as docs
    from .engine import spaces

    comp_win = window._ensure_composer()
    docs.refresh_sheets(window)
    scene = window.viewport.scene
    levels = {lv["name"]: lv for lv in doc.get("levels") or []}
    layer_of = {KIND_CUT: "A-CUT", KIND_PROFILE: "A-PROFILE",
                KIND_EDGE: "A-EDGE", KIND_HIDDEN: "A-HIDDEN"}
    out = []
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for comp in scene.compositions:
        if not docs.is_ours(comp) or not comp.frames:
            continue
        dxf, dimstyle = _new_doc()
        msp = dxf.modelspace()
        shift_x = 0.0
        mapping = {}                     # frame uid → (kind, map world → 2D)
        for fr in comp.frames:
            basis = _frame_basis(fr.view_key, scene)
            if basis is None:
                continue
            kind, level, right = basis
            drawing = comp_win.model_view_drawing(fr)
            W = np.asarray(drawing.world, dtype=np.float64)
            if not len(W):
                continue
            if kind == "plan":
                def to2(p, sx=0.0):
                    return (p[0] + sx, p[1])
            else:
                def to2(p, sx=0.0, r=right):
                    return (p[0] * r[0] + p[1] * r[1] + sx, p[2])
            # side by side: this drawing starts GAP_M after the last one
            if kind != "plan":
                xs = W[:, :, 0] * right[0] + W[:, :, 1] * right[1]
                sx = shift_x - float(xs.min())
                shift_x = sx + float(xs.max()) + GAP_M
            else:
                sx = 0.0
            mapping[fr.uid] = (kind, lambda p, f=to2, s=sx: f(p, s))
            put = mapping[fr.uid][1]
            for (a, b), k in zip(W, drawing.kinds):
                pa, pb = put(a), put(b)
                if math.dist(pa, pb) < 1e-6:
                    continue
                msp.add_line(pa, pb, dxfattribs={"layer": layer_of.get(
                    int(k), "A-EDGE")})
            # the drawing's title under it
            xs = [put(p)[0] for p in W.reshape(-1, 3)]
            ys = [put(p)[1] for p in W.reshape(-1, 3)]
            title = f"{fr.title_text or comp.name}   1:{fr.scale_n:g}"
            h = 0.004 * fr.scale_n
            msp.add_text(title, height=h, dxfattribs={
                "layer": "A-TITLE", "insert": (min(xs), min(ys) - 4 * h)})
            # rooms (plans): name and area at their label point
            if kind == "plan" and level in levels:
                lid = levels[level]["id"]
                th = 0.0025 * fr.scale_n
                for room in spaces.of_level(doc, lid):
                    x, y = room["at"]
                    for i, line in enumerate((room["name"],
                                              f"{area_txt(room['area'])}")):
                        t = msp.add_text(line, height=th if i == 0
                                         else th * 0.8,
                                         dxfattribs={"layer": "A-ROOM"})
                        t.set_placement((x, y + (0.7 - 1.6 * i) * th),
                                        align=_mid())
        # the sheet's dimension chains → real dimensions
        for c in comp.cotas:
            m = mapping.get(c.anchor_uid)
            if m is None or not c.a_world or not c.b_world:
                continue
            put = m[1]
            pa, pb = put(c.a_world), put(c.b_world)
            L = math.dist(pa, pb)
            if L < 1e-4:
                continue
            # the dimension line's offset: paper mm → model m, same side
            ux, uy = (pb[0] - pa[0]) / L, (pb[1] - pa[1]) / L
            nx, ny = -uy, ux
            # the page's y runs down, the model's up: the side flips
            dist = -c.sep_mm * c.scale_n / 1000.0
            try:
                dim = msp.add_aligned_dim(p1=pa, p2=pb, distance=dist,
                                          dimstyle=dimstyle,
                                          dxfattribs={"layer": "A-DIMS"})
                dim.render()
            except Exception:  # noqa: BLE001 — a line and its number then
                q1 = (pa[0] + nx * dist, pa[1] + ny * dist)
                q2 = (pb[0] + nx * dist, pb[1] + ny * dist)
                msp.add_line(q1, q2, dxfattribs={"layer": "A-DIMS"})
                msp.add_text(f"{L:.2f}", height=0.002 * c.scale_n,
                             dxfattribs={"layer": "A-DIMS",
                                         "insert": ((q1[0] + q2[0]) / 2,
                                                    (q1[1] + q2[1]) / 2)})
        # level marks → a triangle on the line and «Name +3.20»
        for nv in comp.niveles:
            m = mapping.get(nv.anchor_uid)
            if m is None or not nv.a_world or m[0] == "plan":
                continue
            x, y = m[1](nv.a_world)
            s = 0.0025 * comp.frames[0].scale_n
            x += 2 * s
            msp.add_lwpolyline([(x, y), (x - s, y + 1.6 * s),
                                (x + s, y + 1.6 * s)], close=True,
                               dxfattribs={"layer": "A-LEVEL"})
            msp.add_line((x - s, y), (x + 8 * s, y),
                         dxfattribs={"layer": "A-LEVEL"})
            msp.add_text(nv.label(), height=s, dxfattribs={
                "layer": "A-LEVEL", "insert": (x + 1.5 * s, y + 0.5 * s)})
        path = folder / f"{_safe(comp.name)}.dxf"
        dxf.saveas(str(path))
        out.append(str(path))
    return out


def _mid():
    from ezdxf.enums import TextEntityAlignment
    return TextEntityAlignment.MIDDLE_CENTER
