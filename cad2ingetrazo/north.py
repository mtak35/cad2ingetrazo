# SPDX-License-Identifier: GPL-3.0-or-later
"""The project north in the viewport: a compass in the top-right corner,
its needle along the model's north as the camera sees it (a plan shows it
true; in 3D it turns with the orbit)."""
from __future__ import annotations

import math

_cache = {"key": None, "c": None}


def _centre(arch):
    walls = arch.get("walls") or []
    key = (len(walls), walls[0]["id"] if walls else None)
    if _cache["key"] != key:
        xs, ys = [], []
        for w in walls:
            for p in (w.get("a"), w.get("b")):
                if p:
                    xs.append(p[0]); ys.append(p[1])
        _cache["key"] = key
        _cache["c"] = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2) \
            if xs else None
    return _cache["c"]


def draw(viewport, painter) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF, \
        QVector3D
    from . import project as PJ

    scene = viewport.scene
    data = getattr(scene, "plugin_data", {}).get(PJ.KEY)
    if not data or not (data.get("arch") or {}).get("walls"):
        return
    if not (data.get("settings") or {}).get("north_show", True):
        return
    c = _centre(data["arch"])
    if c is None:
        return
    deg = float((data["arch"].get("project") or {}).get("north_deg", 0.0)
                or 0.0)
    th = math.radians(deg)
    w2p = viewport._world_to_pixel
    z = 0.0
    a = w2p(QVector3D(c[0], c[1], z))
    b = w2p(QVector3D(c[0] + 10 * math.sin(th), c[1] + 10 * math.cos(th), z))
    if a is None or b is None:
        return
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return
    ux, uy = dx / L, dy / L                    # north on screen (y down)
    vx, vy = -uy, ux
    R = 24.0
    cx, cy = viewport.width() - 58.0, 64.0
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(40, 48, 64, 220), 1.4))
    painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
    painter.drawEllipse(QPointF(cx, cy), R, R)
    tip = QPointF(cx + ux * R * 0.95, cy + uy * R * 0.95)
    tail = QPointF(cx - ux * R * 0.95, cy - uy * R * 0.95)
    l_ = QPointF(cx + vx * R * 0.28, cy + vy * R * 0.28)
    r_ = QPointF(cx - vx * R * 0.28, cy - vy * R * 0.28)
    painter.setPen(QPen(QColor(40, 48, 64), 1.0))
    painter.setBrush(QBrush(QColor(40, 48, 64)))
    painter.drawPolygon(QPolygonF([tip, l_, QPointF(cx, cy)]))
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    painter.drawPolygon(QPolygonF([tip, r_, QPointF(cx, cy)]))
    painter.drawPolygon(QPolygonF([tail, l_, r_]))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(13)
    painter.setFont(f)
    nx, ny = cx + ux * (R + 10), cy + uy * (R + 10)
    painter.setPen(QPen(QColor(200, 40, 40)))
    painter.drawText(QPointF(nx - 5, ny + 5), "N")
    f.setPixelSize(10)
    f.setBold(False)
    painter.setFont(f)
    painter.setPen(QPen(QColor(40, 48, 64)))
    painter.drawText(QPointF(cx - 18, cy + R + 16), f"{deg:.1f}°")
    painter.restore()
