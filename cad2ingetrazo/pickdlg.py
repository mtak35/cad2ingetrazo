# SPDX-License-Identifier: GPL-3.0-or-later
"""«Select floor on drawing» — the CAD file shown in a window: drag a box
round ONE floor plan, then click its reference point (a grid crossing or a
building corner that is the same on every floor). Each level takes its own
part of the same drawing; the reference points put the floors one over the
other."""
from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTransform
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

SNAP_PX = 12
COLORS = ["#d9822b", "#2e9e5b", "#9b59b6", "#c0392b", "#16a085", "#7f8c8d"]


class Canvas(QWidget):
    def __init__(self, drawing, taken, region, base, on_change):
        super().__init__()
        self.setMinimumSize(760, 520)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.d = drawing
        self.taken = taken                      # [(name, region, base)]
        self.region = list(region) if region else None
        self.base = tuple(base) if base else None
        self.on_change = on_change
        self.mode = "box" if not self.region else "base"
        self.poly = []                          # plot corners (drawing)
        self.closed = False
        self.lines = [QLineF(s[0], s[1], s[2], s[3]) for s in drawing["segs"]]
        self.view = None                        # QTransform drawing → px
        self._drag = None                       # box start (drawing)
        self._pan = None
        self._mouse = None
        self._snap = None

    # ---- the view ----------------------------------------------------------
    def fit(self, rect=None):
        x0, y0, x1, y1 = rect or self.d["extents"]
        w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        k = 0.92 * min(self.width() / w, self.height() / h)
        t = QTransform()
        t.translate(self.width() / 2, self.height() / 2)
        t.scale(k, -k)
        t.translate(-(x0 + x1) / 2, -(y0 + y1) / 2)
        self.view = t
        self.update()

    def resizeEvent(self, e):
        if self.view is None:
            self.fit()
        super().resizeEvent(e)

    def to_dwg(self, p):
        inv, _ok = self.view.inverted()
        return inv.map(QPointF(p))

    def scale(self):
        return math.hypot(self.view.m11(), self.view.m12())

    # ---- snapping ----------------------------------------------------------
    def snap(self, pos):
        """The nearest end point or crossing of lines within SNAP_PX."""
        q = self.to_dwg(pos)
        tol = SNAP_PX / self.scale()
        best, bd = None, tol
        near = []
        for ln in self.lines:
            for p in (ln.p1(), ln.p2()):
                d = math.hypot(p.x() - q.x(), p.y() - q.y())
                if d < bd:
                    best, bd = (p.x(), p.y()), d
            if _dist_seg(q, ln) < tol:
                near.append(ln)
                if len(near) > 60:
                    break
        for i, a in enumerate(near):
            for b in near[i + 1:]:
                kind, x = a.intersects(b)
                if kind == QLineF.BoundedIntersection:
                    d = math.hypot(x.x() - q.x(), x.y() - q.y())
                    if d < bd:
                        best, bd = (x.x(), x.y()), d
        return best

    # ---- mouse -------------------------------------------------------------
    def wheelEvent(self, e):
        f = 1.2 if e.angleDelta().y() > 0 else 1 / 1.2
        p = e.position()
        t = QTransform()
        t.translate(p.x(), p.y())
        t.scale(f, f)
        t.translate(-p.x(), -p.y())
        self.view = self.view * t
        self.update()

    def mousePressEvent(self, e):
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan = e.position()
            return
        if e.button() != Qt.LeftButton:
            return
        if self.mode == "box":
            q = self.to_dwg(e.position())
            self._drag = (q.x(), q.y())
            self.region = [q.x(), q.y(), q.x(), q.y()]
        elif self.mode == "poly":
            if self.closed:
                self.poly, self.closed = [], False
            p = self.snap(e.position())
            if p is None:
                q = self.to_dwg(e.position())
                p = (q.x(), q.y())
            if self.poly and len(self.poly) >= 3 and math.hypot(
                    p[0] - self.poly[0][0], p[1] - self.poly[0][1]) \
                    * self.scale() < SNAP_PX:
                self.closed = True             # back on the first corner
            else:
                self.poly.append(p)
            self.on_change()
        elif self.mode == "chain":
            q = self.to_dwg(e.position())
            loop = _chain_from(self.d, (q.x(), q.y()), SNAP_PX * 2 / self.scale())
            if loop:
                self.poly, self.closed = loop, True
            self.on_change()
        elif self.mode == "inside":
            q = self.to_dwg(e.position())
            hit = [lp["pts"] for lp in self.d["loops"]
                   if len(lp["pts"]) >= 3 and _inside((q.x(), q.y()),
                                                      lp["pts"])]
            if hit:
                self.poly = [tuple(p) for p in min(hit, key=_area)]
                self.closed = True
            self.on_change()
        else:
            p = self.snap(e.position())
            if p is None:
                q = self.to_dwg(e.position())
                p = (q.x(), q.y())
            self.base = p
            self.on_change()
        self.update()

    def mouseMoveEvent(self, e):
        self._mouse = e.position()
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            t = QTransform()
            t.translate(d.x(), d.y())
            self.view = self.view * t
        elif self._drag is not None:
            q = self.to_dwg(e.position())
            self.region = [self._drag[0], self._drag[1], q.x(), q.y()]
        elif self.mode in ("base", "poly"):
            self._snap = self.snap(e.position())
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self.mode == "poly" and len(self.poly) >= 3:
            self.closed = True
            self.on_change()
            self.update()

    def keyPressEvent(self, e):
        if self.mode == "poly" and e.key() == Qt.Key_Backspace and \
                self.poly and not self.closed:
            self.poly.pop()
            self.on_change()
            self.update()
        elif self.mode == "poly" and e.key() in (Qt.Key_Return,
                                                  Qt.Key_Enter) and \
                len(self.poly) >= 3:
            self.closed = True
            self.on_change()
            self.update()
        else:
            super().keyPressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            return
        if self._drag is not None:
            self._drag = None
            x0, y0, x1, y1 = self.region
            r = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            if (r[2] - r[0]) * self.scale() < 8 or \
                    (r[3] - r[1]) * self.scale() < 8:
                self.region = None
            else:
                self.region = r
                self.base = None
                self.mode = "base"
            self.on_change()
            self.update()

    # ---- painting ----------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1e2228"))
        if self.view is None:
            return
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setTransform(self.view)
        pen = QPen(QColor("#c9d1d9"))
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        p.setPen(pen)
        if self.lines:
            p.drawLines(self.lines)
        p.resetTransform()
        p.setRenderHint(QPainter.Antialiasing, True)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        p.setFont(f)
        for i, (name, reg, base) in enumerate(self.taken):
            col = QColor(COLORS[i % len(COLORS)])
            self._box(p, reg, col, Qt.DashLine, name)
            if base:
                self._cross(p, base, col)
        if self.region:
            self._box(p, self.region, QColor("#2f6fdd"), Qt.SolidLine,
                      "this level", fill=True)
        if self.base:
            self._cross(p, self.base, QColor("#ff4040"), big=True)
        if self.poly:
            from PySide6.QtGui import QPolygonF
            pts = [self.view.map(QPointF(*q)) for q in self.poly]
            col = QColor("#38c172")
            p.setPen(QPen(col, 2))
            if self.closed:
                c = QColor(col)
                c.setAlpha(45)
                p.setBrush(c)
                p.drawPolygon(QPolygonF(pts))
            else:
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(QPolygonF(pts + ([self._mouse]
                                                if self._mouse else [])))
            for q in pts:
                p.drawEllipse(q, 3.5, 3.5)
        if self.mode in ("base", "poly") and self._snap:
            c = self.view.map(QPointF(*self._snap))
            p.setPen(QPen(QColor("#ffd400"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(c.x() - 6, c.y() - 6, 12, 12))
        p.end()

    def _box(self, p, reg, col, style, label, fill=False):
        a = self.view.map(QPointF(reg[0], reg[1]))
        b = self.view.map(QPointF(reg[2], reg[3]))
        r = QRectF(a, b).normalized()
        pen = QPen(col, 2, style)
        p.setPen(pen)
        if fill:
            c = QColor(col)
            c.setAlpha(40)
            p.setBrush(c)
        else:
            p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.setPen(col)
        p.drawText(r.topLeft() + QPointF(4, 14), label)

    def _cross(self, p, pt, col, big=False):
        c = self.view.map(QPointF(*pt))
        s = 10 if big else 6
        p.setPen(QPen(col, 2))
        p.drawLine(QPointF(c.x() - s, c.y()), QPointF(c.x() + s, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - s), QPointF(c.x(), c.y() + s))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, s * 0.6, s * 0.6)


def _chain_from(d, p, tol):
    """The closed line the click is on — straight pieces and arcs (a
    curved plot boundary) followed end to end on that layer."""
    best, bd = None, tol
    for i, s in enumerate(d["segs"]):
        q = QPointF(p[0], p[1])
        dist = _dist_seg(q, QLineF(s[0], s[1], s[2], s[3]))
        if dist < bd:
            best, bd = i, dist
    if best is None:
        return None
    lay = d["segs"][best][4]
    segs = [s for s in d["segs"] if s[4] == lay]
    k = d.get("unit", 1.0) or 1.0
    eps = 0.02 / k                                 # 2 cm, in drawing units

    def key(x, y):
        return (round(x / eps), round(y / eps))
    ends = {}
    for j, s in enumerate(segs):
        for e_, (x, y) in enumerate(((s[0], s[1]), (s[2], s[3]))):
            ends.setdefault(key(x, y), []).append((j, e_))
    start = d["segs"][best]
    j0 = next(j for j, s in enumerate(segs) if s is start)
    used = {j0}
    pts = [(start[0], start[1]), (start[2], start[3])]
    cur = (start[2], start[3])
    for _ in range(20000):
        nxt = None
        kx = key(*cur)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j, e_ in ends.get((kx[0] + dx, kx[1] + dy), ()):
                    if j not in used:
                        nxt = (j, e_)
                        break
                if nxt:
                    break
            if nxt:
                break
        if nxt is None:
            break
        j, e_ = nxt
        used.add(j)
        s = segs[j]
        far = (s[2], s[3]) if e_ == 0 else (s[0], s[1])
        if math.hypot(far[0] - pts[0][0], far[1] - pts[0][1]) <= eps * 1.5:
            return pts                             # back at the start
        pts.append(far)
        cur = far
    return pts if len(pts) >= 3 else None


def _area(pts):
    return abs(0.5 * sum(a[0] * b[1] - b[0] * a[1]
                         for a, b in zip(pts, list(pts[1:]) + [pts[0]])))


def _inside(p, pts) -> bool:
    x, y = p
    c = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y) and \
                x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _dist_seg(q, ln):
    ax, ay, bx, by = ln.x1(), ln.y1(), ln.x2(), ln.y2()
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((q.x() - ax) * dx
                                              + (q.y() - ay) * dy) / L))
    return math.hypot(ax + t * dx - q.x(), ay + t * dy - q.y())


class PortionDialog(QDialog):
    """``exec()`` → Accepted with ``.region`` (x0, y0, x1, y1) and
    ``.base`` (x, y), drawing units; or ``.whole`` True for all of it."""

    def __init__(self, parent, drawing, level_name, taken=(), region=None,
                 base=None):
        super().__init__(parent)
        self.setWindowTitle(f"CAD2IngeTrazo — select «{level_name}» on the "
                            "drawing")
        self.resize(1100, 760)
        self.whole = False
        v = QVBoxLayout(self)
        self.tip = QLabel()
        self.tip.setWordWrap(True)
        v.addWidget(self.tip)
        self.canvas = Canvas(drawing, list(taken), region, base, self._changed)
        v.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        self.b_box = QPushButton("1  Draw the box again")
        self.b_box.clicked.connect(self._again)
        self.b_base = QPushButton("2  Pick the reference point again")
        self.b_base.clicked.connect(self._base_again)
        self.b_ll = QPushButton("Use the plan's lower-left corner")
        self.b_ll.setToolTip("When the floors share no grid point — they "
                             "line up only if drawn in the same place in "
                             "each box")
        self.b_ll.clicked.connect(self._lower_left)
        b_fit = QPushButton("Fit")
        b_fit.clicked.connect(lambda: self.canvas.fit())
        b_all = QPushButton("Whole drawing")
        b_all.setToolTip("The file holds only this floor")
        b_all.clicked.connect(self._whole)
        for b in (self.b_box, self.b_base, self.b_ll, b_fit, b_all):
            row.addWidget(b)
        row.addStretch(1)
        self.ok = QPushButton("Use this floor")
        self.ok.setDefault(True)
        self.ok.setStyleSheet("QPushButton { background: #2f6fdd; color: "
                              "white; font-weight: bold; padding: 4px 12px; }")
        self.ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(self.ok)
        row.addWidget(cancel)
        v.addLayout(row)
        self._changed()

    @property
    def region(self):
        return self.canvas.region

    @property
    def base(self):
        return self.canvas.base

    def _changed(self):
        c = self.canvas
        others = (" Dashed boxes: the floors already taken from this file."
                  if c.taken else "")
        if c.region is None:
            self.tip.setText("<b>1 · Drag a box round this floor's plan.</b>"
                             "  Wheel: zoom · right or middle drag: pan."
                             + others)
        elif c.base is None:
            self.tip.setText("<b>2 · Click this floor's reference point</b> "
                             "— the same grid crossing (e.g. A/1) or "
                             "building corner you use on every floor. It "
                             "snaps to line ends and crossings (yellow)."
                             + others)
        else:
            self.tip.setText("<b>Ready.</b> «Use this floor» — or draw the box"
                             " / pick the point again." + others)
        self.ok.setEnabled(c.region is not None and c.base is not None)
        self.b_base.setEnabled(c.region is not None)
        self.b_ll.setEnabled(c.region is not None)

    def _again(self):
        self.canvas.region = None
        self.canvas.base = None
        self.canvas.mode = "box"
        self.canvas.update()
        self._changed()

    def _base_again(self):
        self.canvas.base = None
        self.canvas.mode = "base"
        self.canvas.update()
        self._changed()

    def _lower_left(self):
        from .cadread import crop
        ext = crop(self.canvas.d, self.canvas.region)["extents"]
        self.canvas.base = (ext[0], ext[1])
        self.canvas.update()
        self._changed()

    def _whole(self):
        self.whole = True
        self.accept()


class PlotDialog(QDialog):
    """The plot's boundary on the CAD drawing: click its corners (they
    snap), or click inside a closed outline (the boundary polyline).
    ``exec()`` → Accepted with ``.poly`` [(x, y)…] in drawing units."""

    def __init__(self, parent, drawing, taken=()):
        super().__init__(parent)
        self.setWindowTitle("CAD2IngeTrazo — the plot on the drawing")
        self.resize(1100, 760)
        v = QVBoxLayout(self)
        self.tip = QLabel()
        self.tip.setWordWrap(True)
        v.addWidget(self.tip)
        self.canvas = Canvas(drawing, list(taken), None, None, self._changed)
        self.canvas.mode = "poly"
        v.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        b1 = QPushButton("Click the corners")
        b1.clicked.connect(lambda: self._mode("poly"))
        b2 = QPushButton("Click inside the boundary outline")
        b2.clicked.connect(lambda: self._mode("inside"))
        b2b = QPushButton("Click the boundary line (curves too)")
        b2b.setToolTip("Follows the line you click — straight pieces and "
                       "arcs — all the way round")
        b2b.clicked.connect(lambda: self._mode("chain"))
        b3 = QPushButton("Clear")
        b3.clicked.connect(self._clear)
        b4 = QPushButton("Fit")
        b4.clicked.connect(lambda: self.canvas.fit())
        for b in (b1, b2, b2b, b3, b4):
            row.addWidget(b)
        row.addStretch(1)
        self.ok = QPushButton("Use this plot")
        self.ok.setStyleSheet("QPushButton { background: #2f6fdd; color: "
                              "white; font-weight: bold; padding: 4px 12px; }")
        self.ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(self.ok)
        row.addWidget(cancel)
        v.addLayout(row)
        self._changed()

    @property
    def poly(self):
        return list(self.canvas.poly)

    def _mode(self, m):
        self.canvas.mode = m
        self._changed()

    def _clear(self):
        self.canvas.poly, self.canvas.closed = [], False
        self.canvas.update()
        self._changed()

    def _changed(self):
        c = self.canvas
        if c.closed:
            self.tip.setText(f"<b>Plot closed — {len(c.poly)} corners.</b> "
                             "«Use this plot», or Clear to start again.")
        elif c.mode == "inside":
            self.tip.setText("<b>Click inside the plot's boundary</b> (a "
                             "closed polyline in the drawing).")
        elif c.mode == "chain":
            self.tip.setText("<b>Click on the plot's boundary line</b> — it is "
                             "followed round, arcs and curves included.")
        else:
            self.tip.setText("<b>Click the plot's corners</b> in order — they "
                             "snap to line ends and crossings (yellow). Click "
                             "the first corner again, double-click or press "
                             "Enter to close; Backspace takes the last one "
                             "back. Wheel: zoom · right drag: pan.")
        self.ok.setEnabled(c.closed and len(c.poly) >= 3)
