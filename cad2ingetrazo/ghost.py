# SPDX-License-Identifier: GPL-3.0-or-later
"""The other floors, greyed out, under the plan being looked at — to lay
the floors over each other: the floor below in solid grey, the floor
above dashed (as on paper). Drawn by the overlay only; the model and the
sheets are untouched. ``MODE``: "off" | "below" | "above" | "both" | "all".
"""
from __future__ import annotations

from .host import KEY, PREFIX_PLAN_CUT

MODE = "below"
MODES = [("off", "None"), ("below", "The floor below"),
         ("above", "The floor above"), ("both", "Below and above"),
         ("all", "All other floors")]
_cache: dict = {}


def _outlines(arch, lid):
    """The level's walls and columns as closed 2D loops."""
    from .engine import structure as S
    from .engine import walls as W
    walls = [w for w in arch["walls"] if w["level"] == lid
             and W.why_not(w) is None]
    loops = []
    for pieces in W.plan(walls).values():
        for pc in pieces:
            loops.append(([tuple(p[:2]) for p in pc["outer"]], True))
            loops += [([tuple(p[:2]) for p in h], False)
                      for h in pc["holes"]]
    for e in arch["structure"]:
        if e["level"] != lid:
            continue
        try:
            if e["type"] == "column":
                loops.append(([tuple(p) for p in S.column_outline(e)], True))
            elif e["type"] == "core":
                loops.append(([tuple(p) for p in e["corners"]], True))
            elif e["type"] == "slab":
                loops.append(([tuple(p) for p in e["corners"]], False))
        except Exception:  # noqa: BLE001
            pass
    return loops


def _which(arch, name):
    """[(loops, "below" | "above")] of the floors to show under ``name``."""
    names = [lv["name"] for lv in arch["levels"]]
    if name not in names:
        return []
    i = names.index(name)
    picks = []
    for j, lv in enumerate(arch["levels"]):
        if j == i:
            continue
        rel = "below" if j < i else "above"
        if MODE == "all" or (MODE in (rel, "both") and abs(j - i) == 1):
            picks.append((lv["id"], rel))
    return [(_outlines(arch, lid), rel) for lid, rel in picks]


def draw(viewport, painter) -> None:
    if MODE == "off":
        return
    scene = viewport.scene
    sp = scene.active_section() if hasattr(scene, "active_section") else None
    name = str(getattr(sp, "name", "") or "")
    if not name.startswith(PREFIX_PLAN_CUT):
        return
    name = name[len(PREFIX_PLAN_CUT):]
    raw = (getattr(scene, "plugin_data", {}) or {}).get(KEY)
    key = (id(raw), name, MODE)
    if key not in _cache:
        from . import project as PJ
        doc = PJ.load(raw)
        arch = doc["arch"]
        elev = PJ.elevations(arch)
        z = next((elev[i] for i, lv in enumerate(arch["levels"])
                  if lv["name"] == name), 0.0)
        if len(_cache) > 16:
            _cache.clear()
        _cache[key] = (_which(arch, name), z)
    sets, z = _cache[key]
    if not sets:
        return
    import numpy as np
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPen, QPolygonF
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    for loops, rel in sets:
        ink = QColor(95, 102, 114, 190) if rel == "below" \
            else QColor(60, 100, 165, 190)
        pen = QPen(ink, 1.3)
        if rel == "above":
            pen.setStyle(Qt.DashLine)
        fill = QColor(ink)
        fill.setAlpha(55)
        painter.setPen(pen)
        for loop, solid in loops:
            painter.setBrush(fill if solid else Qt.NoBrush)
            if len(loop) < 2:
                continue
            pts = np.array([(p[0], p[1], z + 0.02) for p in loop],
                           dtype=float)
            px, py, ok = viewport._project_px(pts)
            if not ok.all():
                continue
            poly = QPolygonF([QPointF(float(x), float(y))
                              for x, y in zip(px, py)])
            painter.drawPolygon(poly)
    painter.restore()
