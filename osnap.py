"""Object snaps for CAD2IngeTrazo's handles — as AutoCAD's OSNAP.

While a wall end, a slab corner / edge, a slab opening or a door / window
jamb is dragged, the cursor locks onto the geometry under it: Endpoint
(□), Midpoint (△), Intersection (×), Centre (○), Perpendicular (⊥) and
Nearest (⧗) — each switched on or off in «Snap settings…» (kept for the
user, as AutoCAD keeps its OSNAP modes), the whole thing on / off at once,
an aperture in screen pixels. The snap marker and its name follow the
cursor, as AutoCAD draws them.

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

import math

#: (key, name, on by default) — AutoCAD's running object snaps
MODES = (("end", "Endpoint", True), ("mid", "Midpoint", True),
         ("int", "Intersection", True), ("cen", "Centre", True),
         ("perp", "Perpendicular", True), ("near", "Nearest", False))
#: which wins when two are as near (AutoCAD's order)
PRIORITY = ("end", "int", "mid", "cen", "perp", "near")
NAMES = {k: n for k, n, _d in MODES}
APERTURE_PX = 12

_ORG, _APP = "IngeTrazo", "CAD2IngeTrazo"


def _qs():
    from PySide6.QtCore import QSettings
    return QSettings(_ORG, _APP)


def _bool(v, default):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes")


def settings() -> dict:
    """{"on": bool, "aperture": px, <mode>: bool}."""
    out = {"on": True, "aperture": APERTURE_PX}
    try:
        q = _qs()
        out["on"] = _bool(q.value("osnap/on"), True)
        try:
            out["aperture"] = int(q.value("osnap/aperture") or APERTURE_PX)
        except (TypeError, ValueError):
            pass
        for k, _n, d in MODES:
            out[k] = _bool(q.value(f"osnap/{k}"), d)
    except Exception:  # noqa: BLE001 — no QSettings: the defaults
        for k, _n, d in MODES:
            out[k] = d
    return out


def save(st: dict) -> None:
    try:
        q = _qs()
        q.setValue("osnap/on", bool(st.get("on", True)))
        q.setValue("osnap/aperture", int(st.get("aperture", APERTURE_PX)))
        for k, _n, d in MODES:
            q.setValue(f"osnap/{k}", bool(st.get(k, d)))
    except Exception:  # noqa: BLE001
        pass


def toggle() -> bool:
    st = settings()
    st["on"] = not st["on"]
    save(st)
    return st["on"]


class Snapper:
    """The snap geometry of a level in plan: segments [(a, b)] and circles
    [(centre, r)], world metres."""

    def __init__(self, segs, circles=()):
        self.segs = [(tuple(a[:2]), tuple(b[:2])) for a, b in segs
                     if math.dist(a[:2], b[:2]) > 1e-4]
        self.circles = [(tuple(c[:2]), float(r)) for c, r in circles]

    def snap(self, q, tol, base=None, modes=None):
        """The snapped point near ``q`` (within ``tol`` m) and its mode —
        ``(q, None)`` when nothing is near. ``base``: the point the drag
        started from (for Perpendicular)."""
        st = modes or settings()
        if not st.get("on", True):
            return q, None
        near = [(a, b) for a, b in self.segs if _seg_dist(q, a, b) <= tol]
        cands = []                              # (mode, point)
        if st.get("end"):
            for a, b in near:
                cands += [("end", a), ("end", b)]
        if st.get("mid"):
            for a, b in near:
                cands.append(("mid", ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))
        if st.get("int"):
            sub = near[:60]
            for i, (a, b) in enumerate(sub):
                for c, d in sub[i + 1:]:
                    x = _cross(a, b, c, d)
                    if x is not None:
                        cands.append(("int", x))
        if st.get("cen"):
            for c, r in self.circles:
                if abs(math.dist(q, c) - r) <= tol or math.dist(q, c) <= tol:
                    cands.append(("cen", c))
        if st.get("perp") and base is not None:
            for a, b in near:
                f = _foot(base, a, b)
                if f is not None:
                    cands.append(("perp", f))
        best = None
        for mode, p in cands:
            dd = math.dist(q, p)
            if dd > tol:
                continue
            rank = PRIORITY.index(mode)
            key = (rank, dd)
            if best is None or key < best[0]:
                best = (key, p, mode)
        if best is not None:
            return best[1], best[2]
        if st.get("near") and near:
            a, b = min(near, key=lambda s: _seg_dist(q, *s))
            f = _foot(q, a, b)
            if f is not None:
                return f, "near"
        return q, None


def _seg_dist(p, a, b) -> float:
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    if L2 < 1e-12:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.dist(p, (a[0] + ax * t, a[1] + ay * t))


def _foot(p, a, b):
    """The foot of the perpendicular from ``p`` on segment a-b (on it)."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    if L2 < 1e-12:
        return None
    t = ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2
    if t < -1e-6 or t > 1 + 1e-6:
        return None
    return (a[0] + ax * t, a[1] + ay * t)


def _cross(a, b, c, d):
    """Where segments a-b and c-d cross (on both), or None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if -1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6:
        return (a[0] + r[0] * t, a[1] + r[1] * t)
    return None


def level_geometry(doc, lids, skip_ids=()) -> Snapper:
    """The snap geometry of levels ``lids``: the walls' faces, the slabs'
    edges and openings, the columns, the cores, the beams, the stairs'
    outlines, the doors' and windows' jambs."""
    from shapely.geometry import Polygon

    from .engine import structure as S
    from .engine import walls as W
    arch = doc["arch"]
    segs, circles = [], []

    def ring(pts):
        n = len(pts)
        for i in range(n):
            segs.append((tuple(pts[i][:2]), tuple(pts[(i + 1) % n][:2])))
    ws = [w for w in arch["walls"] if w["level"] in lids]
    try:
        for wid, pcs in W.plan(ws).items():
            if wid in skip_ids:
                continue
            for pc in pcs:
                ring(pc["outer"])
                for h in pc.get("holes") or []:
                    ring(h)
    except Exception:  # noqa: BLE001
        pass
    for w in ws:                       # the wall's centre line too
        if w.get("kind", "line") == "line" and "a" in w and \
                w["id"] not in skip_ids:
            segs.append((tuple(w["a"]), tuple(w["b"])))
        elif w.get("kind") == "circle" and "c" in w:
            circles.append((tuple(w["c"]), float(w["r"])))
    for e in arch.get("structure") or []:
        if e.get("level") not in lids or e.get("id") in skip_ids:
            continue
        try:
            if e["type"] == "column":
                if e.get("shape") == "round":
                    circles.append(((e["x"], e["y"]), float(e["w"]) / 2))
                ring(S.column_outline(e, 0.0))
            elif e.get("corners"):
                ring(e["corners"])
                for h in e.get("holes") or []:
                    if len(h) >= 3:
                        ring(h)
            elif e["type"] == "beam" and "a" in e:
                segs.append((tuple(e["a"]), tuple(e["b"])))
        except Exception:  # noqa: BLE001
            continue
    for m in doc.get("man_shafts") or []:
        if m.get("through") or m.get("level") in lids:
            ring(m["pts"])
    byid = {w["id"]: w for w in ws}
    for o in arch.get("openings") or []:            # door / window jambs
        w = byid.get(o.get("wall"))
        if w is None or w.get("kind", "line") != "line" or "a" not in w:
            continue
        try:
            seg = W.centre(w)
            t2 = float(w["t"]) / 2
            n = (-seg.u[1], seg.u[0])
            for s in (o["pos"] - o["w"] / 2, o["pos"] + o["w"] / 2):
                c = (seg.p0[0] + seg.u[0] * s, seg.p0[1] + seg.u[1] * s)
                segs.append(((c[0] - n[0] * t2, c[1] - n[1] * t2),
                             (c[0] + n[0] * t2, c[1] + n[1] * t2)))
        except Exception:  # noqa: BLE001
            continue
    del Polygon
    return Snapper(segs, circles)


def draw_marker(painter, p, mode) -> None:
    """AutoCAD's snap marker at screen point ``p`` and its name."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QPen, QPolygonF
    if p is None or mode is None:
        return
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    col = QColor(40, 200, 60)
    painter.setPen(QPen(col, 2.0))
    painter.setBrush(QColor(0, 0, 0, 0))
    x, y, r = p[0], p[1], 7.0
    if mode == "end":
        painter.drawRect(QRectF(x - r, y - r, 2 * r, 2 * r))
    elif mode == "mid":
        painter.drawPolygon(QPolygonF([QPointF(x, y - r), QPointF(x + r, y + r),
                                       QPointF(x - r, y + r)]))
    elif mode == "int":
        painter.drawLine(QPointF(x - r, y - r), QPointF(x + r, y + r))
        painter.drawLine(QPointF(x - r, y + r), QPointF(x + r, y - r))
    elif mode == "cen":
        painter.drawEllipse(QPointF(x, y), r, r)
    elif mode == "perp":
        painter.drawLine(QPointF(x - r, y + r), QPointF(x + r, y + r))
        painter.drawLine(QPointF(x - r, y + r), QPointF(x - r, y - r))
        painter.drawLine(QPointF(x - r, y), QPointF(x, y))
        painter.drawLine(QPointF(x, y), QPointF(x, y + r))
    elif mode == "near":
        painter.drawPolygon(QPolygonF([QPointF(x - r, y - r),
                                       QPointF(x + r, y - r),
                                       QPointF(x - r, y + r),
                                       QPointF(x + r, y + r)]))
    painter.setPen(QColor(20, 120, 40))
    painter.drawText(QPointF(x + r + 4, y - r - 2), NAMES.get(mode, mode))
    painter.restore()


def dialog(parent=None) -> bool:
    """«Snap settings…»: the object snap modes, as AutoCAD's Drafting
    Settings ▸ Object Snap tab. True when changed."""
    from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                   QLabel, QSpinBox, QVBoxLayout, QHBoxLayout)
    st = settings()
    dlg = QDialog(parent)
    dlg.setWindowTitle("CAD2IngeTrazo · Snap settings (object snap)")
    lay = QVBoxLayout(dlg)
    on = QCheckBox("Object snap on (while dragging a handle)")
    on.setChecked(st["on"])
    lay.addWidget(on)
    lay.addWidget(QLabel("Object snap modes:"))
    boxes = {}
    marks = {"end": "□", "mid": "△", "int": "×", "cen": "○", "perp": "⊥",
             "near": "⧗"}
    for k, n, _d in MODES:
        b = QCheckBox(f"{marks[k]}  {n}")
        b.setChecked(bool(st.get(k)))
        lay.addWidget(b)
        boxes[k] = b
    row = QHBoxLayout()
    row.addWidget(QLabel("Aperture (pixels)"))
    ap = QSpinBox()
    ap.setRange(4, 40)
    ap.setValue(int(st.get("aperture", APERTURE_PX)))
    row.addWidget(ap)
    lay.addLayout(row)
    lay.addWidget(QLabel("<i>Hold Alt while dragging to move without "
                         "snapping.</i>"))
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    if dlg.exec() != QDialog.Accepted:
        return False
    new = {"on": on.isChecked(), "aperture": ap.value(),
           **{k: b.isChecked() for k, b in boxes.items()}}
    save(new)
    return new != st


__all__ = ["Snapper", "settings", "save", "toggle", "level_geometry",
           "draw_marker", "dialog", "MODES"]
