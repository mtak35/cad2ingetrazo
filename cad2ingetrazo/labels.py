# SPDX-License-Identifier: GPL-3.0-or-later
"""Plan texts drawn to scale. The host draws a text label at one screen
size whatever the zoom — a plan full of room names and CAD notes becomes
a blot when zoomed out and stays tiny when zoomed in. In a CAD2IngeTrazo
plan view the labels are drawn here instead, at their real height in
metres (as on paper): they grow and shrink with the zoom, fade out when
too small to read and stop growing when they would fill the screen.
The sheets keep the host's labels (their layer is shown by the plan's
scene; only the live model hides it)."""
from __future__ import annotations

import math

from .host import KEY, PREFIX_PLAN_CUT, dim_layer, text_layer

from .host import area_txt  # noqa: E402
MIN_PX = 3.5          # smaller than this: not drawn
FADE_PX = 7.0         # … faded in up to this
MAX_PX = 160.0        # never taller than this
DIM_PX = 55.0         # a dimension shorter on screen: the chains hidden
ROOM_H = 0.28         # m, a room's name (its area 0.75 of it)
_cache: dict = {}


def _level_of_view(scene):
    """The level name of the CAD2IngeTrazo plan being looked at, or None."""
    sp = scene.active_section() if hasattr(scene, "active_section") else None
    name = str(getattr(sp, "name", "") or "")
    if not name.startswith(PREFIX_PLAN_CUT):
        return None
    return name[len(PREFIX_PLAN_CUT):]


def _items(scene, level_name):
    """[(x, y, z, text, h, rot, bold)] for that level, cached per document."""
    raw = (getattr(scene, "plugin_data", {}) or {}).get(KEY)
    key = (id(raw), level_name)
    if key in _cache:
        return _cache[key]
    from . import project as PJ
    from .engine import spaces
    doc = PJ.load(raw)
    arch = doc["arch"]
    elev = PJ.elevations(arch)
    out = []
    for i, lv in enumerate(arch["levels"]):
        if lv["name"] != level_name:
            continue
        z = elev[i] + 0.012
        st = doc["settings"]
        used = set()
        if st.get("ann_rooms", True):
            try:
                rooms = spaces.of_level(arch, lv["id"])
            except Exception:  # noqa: BLE001
                rooms = []
            for r in rooms:
                # a small room gets smaller words (never over its width)
                h = min(ROOM_H, max(0.12, math.sqrt(max(r["area"], 0.1))
                                    / 9.0))
                out.append((r["at"][0], r["at"][1] + h * 0.15, z, r["name"],
                            h, 0.0, True, "c"))
                out.append((r["at"][0], r["at"][1] - h * 0.95, z,
                            f"{area_txt(r['area'])}", h * 0.75, 0.0, False, "c"))
                if r["rec"] is not None:
                    used.add(r["name"])
        if st.get("ann_texts", True):
            for t in doc["texts"]:
                if t["level"] != lv["id"] or \
                        t["text"].split("\n")[0].strip() in used:
                    continue
                out.append((t["x"], t["y"], z, t["text"],
                            max(float(t.get("h", 0.2)), 0.02),
                            float(t.get("rot", 0.0)), False, "l"))
        if any(w["level"] == lv["id"] for w in arch["walls"]):
            try:                              # the grid's bubbles
                for x, y, tag in PJ.grid_tags(doc):
                    out.append((x, y, z, tag, 0.38, 0.0, True, "c"))
            except Exception:  # noqa: BLE001
                pass
    if len(_cache) > 32:
        _cache.clear()
    _cache[key] = out
    return out


def _dims_by_zoom(viewport, scene, name, ppm) -> None:
    """The level's dimension chains shown only while their figures fit:
    the median dimension at least DIM_PX long on screen."""
    dl = dim_layer(name)
    L = next((x for x in scene.layers if x.name == dl), None)
    if L is None:
        return
    lens = sorted(d.value() if hasattr(d, "value") else
                  (d.b - d.a).length()
                  for d in scene.dimensions if d.layer == dl)
    if not lens:
        return
    want = lens[len(lens) // 2] * ppm >= DIM_PX
    if L.visible != want:
        L.visible = want
        scene.version += 1
        viewport.update()


def draw(viewport, painter) -> None:
    """Called every frame by the overlay: in a plan view, the level's
    texts at their true size; elsewhere nothing."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QFont, QPen, QVector3D
    try:                       # the CAD's own linework first, under the texts
        from . import linework
        linework.draw(viewport, painter)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("linework.draw")

    scene = viewport.scene
    try:                                   # the project north, a compass
        from . import north
        north.draw(viewport, painter)
    except Exception:  # noqa: BLE001
        pass
    name = _level_of_view(scene)
    if name is None:
        return
    tl = text_layer(name)
    for L in scene.layers:                 # the host's fixed-size copies off
        if L.name == tl and L.visible:
            L.visible = False
            scene.version += 1
            viewport.update()
    items = _items(scene, name)
    w2p = viewport._world_to_pixel
    z = items[0][2] if items else 0.0
    o = w2p(QVector3D(0.0, 0.0, z))
    e = w2p(QVector3D(1.0, 0.0, z))
    if o is None or e is None:
        return
    ppm = math.hypot(e[0] - o[0], e[1] - o[1])         # pixels per metre
    _dims_by_zoom(viewport, scene, name, ppm)
    if not items:
        return
    ux = ((e[0] - o[0]) / ppm, (e[1] - o[1]) / ppm) if ppm else (1.0, 0.0)
    base_deg = math.degrees(math.atan2(ux[1], ux[0]))  # model x on screen
    W, H = viewport.width(), viewport.height()
    ink = QColor(40, 48, 64)
    halo = QColor(255, 255, 255, 210)
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    painter.setRenderHint(painter.RenderHint.TextAntialiasing, True)
    font = QFont()
    for x, y, z, text, h, rot, bold, align in items:
        px = h * ppm
        if px < MIN_PX:
            continue
        p = w2p(QVector3D(x, y, z))
        if p is None or not (-200 < p[0] < W + 200 and -200 < p[1] < H + 200):
            continue
        px = min(px, MAX_PX)
        alpha = 1.0 if px >= FADE_PX else (px - MIN_PX) / (FADE_PX - MIN_PX)
        font.setPixelSize(max(int(round(px)), 1))
        font.setBold(bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        lines = text.splitlines() or [""]
        painter.save()
        painter.translate(QPointF(p[0], p[1]))
        painter.rotate(base_deg - rot)
        for k, line in enumerate(lines):
            wpx = fm.horizontalAdvance(line)
            dx = -wpx / 2 if align == "c" else 0.0
            dy = k * fm.height() + (fm.ascent() / 2 if align == "c" else 0.0)
            c = QColor(halo)
            c.setAlphaF(halo.alphaF() * alpha)
            painter.setPen(QPen(c))
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                painter.drawText(QPointF(dx + ox, dy + oy), line)
            c = QColor(ink)
            c.setAlphaF(alpha)
            painter.setPen(QPen(c))
            painter.drawText(QPointF(dx, dy), line)
        painter.restore()
    painter.restore()
