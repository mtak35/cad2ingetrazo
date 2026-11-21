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
from PySide6.QtWidgets import (QDoubleSpinBox, QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QSplitter,
                               QTableWidget, QVBoxLayout, QWidget)

#: what a CAD layer is read as (Select floor on drawing ▸ Layers)
LAYER_ROLES = [("auto", "Auto (as detected)"), ("walls", "Walls"),
               ("doors", "Doors"), ("windows", "Windows"),
               ("columns", "Columns"), ("beams", "Beams"),
               ("stairs", "Stairs"), ("steps", "Steps (entrance / level)"),
               ("rails", "Railings"), ("slab", "Slab edge"),
               ("holes", "Shafts / voids"), ("lift", "Lift"),
               ("escalators", "Travelators / escalators"),
               ("text", "Room names / text"), ("plot", "Plot boundary"),
               ("grid", "Grid"), ("lines", "Other lines (no element)"),
               ("off", "Off — not read")]

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
        self.outline = []                       # the plot limit, once set
        self.wall = []                          # the boundary wall's line
        self.on_part = None                     # click on a part → its index
        self._vdrag = None                      # corner being dragged (edit)
        self.parts = []                         # [(poly, z)] level parts
        self.lines = [QLineF(s[0], s[1], s[2], s[3]) for s in drawing["segs"]]
        # the drawing as AutoCAD shows it: each line's colour, line weight
        # and line type (by entity, layer or block)
        self.styles = drawing.get("styles") or []
        sty = drawing.get("seg_style") or []
        self._sty = sty
        self.off = set()                         # layers switched off
        self._build_sets()
        self.view = None                        # QTransform drawing → px
        self._drag = None                       # box start (drawing)
        self._pan = None
        self._mouse = None
        self._snap = None

    def _build_sets(self):
        """The lines to draw, by style — the layers switched off (in the
        CAD, or here) left out."""
        hidden = set(self.d.get("hidden_layers") or ()) | set(self.off)
        self.sets = {}
        self.shown = [ln for ln, sg in zip(self.lines, self.d["segs"])
                      if sg[4] not in hidden]
        if len(self._sty) == len(self.lines) and self.styles:
            for ln, k, sg in zip(self.lines, self._sty, self.d["segs"]):
                if sg[4] in hidden:
                    continue
                self.sets.setdefault(k if 0 <= k < len(self.styles) else -1,
                                     []).append(ln)

    def _texts(self, p):
        """The plan's texts (room names, notes, levels) at their place and
        height, once big enough to read — the layers switched off left
        out."""
        ts = self.d.get("texts") or ()
        if not ts:
            return
        hidden = set(self.d.get("hidden_layers") or ()) | set(self.off)
        k = self.scale()
        W_, H_ = self.width(), self.height()
        f = QFont()
        p.setPen(QColor("#f0d37a"))
        n = 0
        for t in ts:
            if t.get("layer") in hidden:
                continue
            try:
                h = float(t.get("h") or 0.0) * k
                if h < 5.0:
                    continue
                q = self.view.map(QPointF(float(t["x"]), float(t["y"])))
            except (TypeError, ValueError, KeyError):
                continue
            if not (-200 <= q.x() <= W_ + 50 and -50 <= q.y() <= H_ + 50):
                continue
            f.setPixelSize(max(int(h), 5))
            p.setFont(f)
            p.save()
            p.translate(q)
            rot = float(t.get("rot") or 0.0)
            if rot:
                p.rotate(-rot)
            p.drawText(QPointF(0, 0), str(t.get("text", ""))[:80])
            p.restore()
            n += 1
            if n > 3000:
                break

    def set_off(self, names):
        self.off = set(names)
        self._build_sets()
        self.update()

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
        if e.button() == Qt.RightButton and self.mode == "edit" \
                and len(self.poly) > 3:
            pos = e.position()
            for i, q in enumerate(self.poly):
                c = self.view.map(QPointF(*q))
                if math.hypot(c.x() - pos.x(), c.y() - pos.y()) < 9:
                    self.poly.pop(i)
                    self.update()
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
        elif self.mode == "partpick":
            q = self.to_dwg(e.position())
            from shapely.geometry import Point
            hit = [i for i, (pg, _z) in enumerate(self.parts)
                   if len(pg) >= 3 and _inside((q.x(), q.y()), pg)]
            if hit and self.on_part:
                self.on_part(min(hit, key=lambda i: _area(self.parts[i][0])))
        elif self.mode == "edit":
            self._edit_press(e)
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

    def _edit_press(self, e):
        """Edit mode: drag a corner of the polyline; click on an edge to add
        a corner there; right-click a corner to delete it."""
        pts = [self.view.map(QPointF(*q)) for q in self.poly]
        pos = e.position()
        near = [i for i, q in enumerate(pts)
                if math.hypot(q.x() - pos.x(), q.y() - pos.y()) < 9]
        if near:
            self._vdrag = near[0]
            return
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            dx, dy = b.x() - a.x(), b.y() - a.y()
            L2 = dx * dx + dy * dy or 1e-9
            t = max(0.0, min(1.0, ((pos.x() - a.x()) * dx +
                                   (pos.y() - a.y()) * dy) / L2))
            if math.hypot(a.x() + t * dx - pos.x(),
                          a.y() + t * dy - pos.y()) < 7:
                q = self.snap(pos)
                if q is None:
                    w = self.to_dwg(pos)
                    q = (w.x(), w.y())
                self.poly.insert(i + 1, tuple(q))
                self._vdrag = i + 1
                return

    def _edit_move(self, pos):
        if self._vdrag is None or self._vdrag >= len(self.poly):
            return
        q = self.snap(pos)
        if q is None:
            w = self.to_dwg(pos)
            q = (w.x(), w.y())
        self.poly[self._vdrag] = tuple(q)

    def mouseMoveEvent(self, e):
        self._mouse = e.position()
        if self.mode == "edit" and self._vdrag is not None:
            self._edit_move(e.position())
            self.update()
            return
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            t = QTransform()
            t.translate(d.x(), d.y())
            self.view = self.view * t
        elif self._drag is not None:
            q = self.to_dwg(e.position())
            self.region = [self._drag[0], self._drag[1], q.x(), q.y()]
        elif self.mode in ("base", "poly", "edit"):
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
        if self._vdrag is not None:
            self._vdrag = None
            self.update()
            return
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
        if self.sets:
            k = abs(self.view.m11()) or 1.0          # px per drawing unit
            unit = float(self.d.get("unit") or 1.0)  # m per drawing unit
            p.setRenderHint(QPainter.Antialiasing, True)
            for i, lines in self.sets.items():
                w_mm, pat, col = (list(self.styles[i]) + [None, None, None]
                                  )[:3] if i >= 0 else (0.25, [], None)
                c = QColor(*col) if col else QColor("#c9d1d9")
                if c.lightness() < 70:          # dark on the dark ground
                    c = c.lighter(260)
                # AutoCAD's lineweight display (≤0.25 mm one pixel, two
                # to 0.50, then three…), growing as plotted at 1:100 when
                # zoomed in
                wm = float(w_mm or 0.0)
                scr = 1.0 if wm <= 0.25 else 2.0 if wm <= 0.5 else 3.0
                paper = max(wm, 0.05) * k * 100.0 / (1000.0 * unit)
                width = max(scr, paper)
                pen = QPen(c)
                pen.setCosmetic(True)
                pen.setWidthF(width)
                pen.setCapStyle(Qt.FlatCap)
                dp = _dash(pat, k, width)
                if dp:
                    pen.setDashPattern(dp)
                p.setPen(pen)
                p.drawLines(lines)
        elif self.shown:
            pen = QPen(QColor("#c9d1d9"))
            pen.setCosmetic(True)
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.drawLines(self.shown)
        p.resetTransform()
        p.setRenderHint(QPainter.Antialiasing, True)
        self._texts(p)
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
        if self.outline:
            from PySide6.QtGui import QPolygonF
            p.setPen(QPen(QColor("#e8a317"), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(QPolygonF([self.view.map(QPointF(*q))
                                     for q in self.outline]))
            pal = ("#3b82f6", "#a855f7", "#14b8a6", "#f43f5e", "#84cc16")
            for i, (pg, zz) in enumerate(self.parts):
                c = QColor(pal[i % len(pal)])
                p.setPen(QPen(c, 2))
                c.setAlpha(70)
                p.setBrush(c)
                qp = QPolygonF([self.view.map(QPointF(*q)) for q in pg])
                p.drawPolygon(qp)
                p.setPen(QPen(QColor("#111"), 1))
                from .host import both_txt
                p.drawText(qp.boundingRect().center(),
                           f"Level {i + 1}: {both_txt(zz)}")
        if self.wall:
            from PySide6.QtGui import QPolygonF
            p.setPen(QPen(QColor("#d946ef"), 3))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(QPolygonF([self.view.map(QPointF(*q))
                                     for q in self.wall]))
        if self.poly:
            from PySide6.QtGui import QPolygonF
            pts = [self.view.map(QPointF(*q)) for q in self.poly]
            col = QColor("#38c172")
            p.setPen(QPen(col, 2))
            if self.closed or self.mode == "edit":
                c = QColor(col)
                c.setAlpha(45)
                p.setBrush(c)
                p.drawPolygon(QPolygonF(pts))
            else:
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(QPolygonF(pts + ([self._mouse]
                                                if self._mouse else [])))
            for q in pts:
                p.drawEllipse(q, 5 if self.mode == "edit" else 3.5,
                              5 if self.mode == "edit" else 3.5)
        if self.mode in ("base", "poly", "edit") and self._snap:
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


def _dash(pat, ppu, width):
    """A Qt dash pattern from a CAD line type's (drawing units), or None
    (solid, or too fine to see at this zoom)."""
    try:
        from .linework import _pattern
        return _pattern(pat, ppu, width)
    except Exception:  # noqa: BLE001
        return None


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
                 base=None, roles=None, detected=None, actions=()):
        super().__init__(parent)
        self.layer_roles = dict(roles or {})
        self.action = None          # 3.64.59: what to do after (import…)
        self.setWindowTitle(f"CAD2IngeTrazo — select «{level_name}» on the "
                            "drawing")
        self.resize(1360, 820)
        self.whole = False
        v = QVBoxLayout(self)
        self.tip = QLabel()
        self.tip.setWordWrap(True)
        v.addWidget(self.tip)
        self.canvas = Canvas(drawing, list(taken), region, base, self._changed)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.canvas)
        split.addWidget(self._layers_box(drawing, detected or {}))
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([980, 420])
        v.addWidget(split, 1)
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
        # 3.64.60: no «Use the plan's lower-left corner» / «Use this floor»
        # buttons (kept unshown: their state still steers the others)
        self.b_ll.setVisible(False)
        for b in (self.b_box, self.b_base, b_fit, b_all):
            row.addWidget(b)
        row.addStretch(1)
        self.ok = QPushButton("Use this floor")
        self.ok.setDefault(True)
        self.ok.setStyleSheet("QPushButton { background: #2f6fdd; color: "
                              "white; font-weight: bold; padding: 4px 12px; }")
        self.ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        if actions:
            self.ok.setVisible(False)
            self.ok.setDefault(False)
        else:
            row.addWidget(self.ok)
        self.acts = []
        for key, label, tip in actions or ():
            b = QPushButton(label)
            b.setToolTip(tip)
            if key == "import":
                b.setDefault(True)
                b.setStyleSheet("QPushButton { background: #1f9d55; color: "
                                "white; font-weight: bold; padding: 4px "
                                "12px; } QPushButton:disabled { background: "
                                "#a9cdb8; color: #eef5f0; }")
            b.clicked.connect(lambda _c=False, k=key: self._act(k))
            row.addWidget(b)
            self.acts.append(b)
        row.addWidget(cancel)
        v.addLayout(row)
        self._changed()

    def _act(self, key):
        """Use this floor, then the panel does ``key`` (import, furniture)."""
        if not (self.ok.isEnabled() or self.whole):
            return
        self.action = key
        self.accept()

    def _layers_box(self, drawing, detected):
        """Every layer of the CAD on / off: shown here, and read at the
        import (off: left out)."""
        box = QWidget()
        box.setMaximumWidth(470)
        lv = QVBoxLayout(box)
        lv.setContentsMargins(0, 0, 0, 0)
        t = QLabel("<b>Layers</b> — untick a layer to leave it out (not "
                   "shown, not read at the import).")
        t.setWordWrap(True)
        lv.addWidget(t)
        counts = {}
        for s_ in drawing["segs"]:
            counts[s_[4]] = counts.get(s_[4], 0) + 1
        for key in ("texts", "inserts", "arcs", "circles", "loops", "fills"):
            for e in drawing.get(key) or ():
                n = e.get("layer") if isinstance(e, dict) else None
                if n is not None:
                    counts[n] = counts.get(n, 0) + 1
        names = sorted(counts)
        self.tbl = QTableWidget(len(names), 3)
        self.tbl.setHorizontalHeaderLabels(["On", "Layer", "Read as"])
        self.tbl.verticalHeader().setVisible(False)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self._rows = []
        from PySide6.QtWidgets import QTableWidgetItem
        for i, n in enumerate(names):
            cb = QCheckBox()
            cb.setChecked(self.layer_roles.get(n) != "off")
            self.tbl.setCellWidget(i, 0, cb)
            it = QTableWidgetItem(f"{n}  ({counts[n]})")
            if detected.get(n):
                it.setToolTip(f"Read as: {detected[n]}")
            self.tbl.setItem(i, 1, it)
            cb.toggled.connect(lambda _on: self._apply_off())
            # what the layer is read as: as detected, or picked here
            co = QComboBox()
            for k_, lab_ in LAYER_ROLES:
                if k_ != "off":
                    co.addItem(lab_, k_)
            now_ = self.layer_roles.get(n)
            if now_ and now_ != "off":
                co.setCurrentIndex(max(co.findData(now_), 0))
            if detected.get(n):
                co.setItemText(0, f"Auto ({detected[n]})")
            co.currentIndexChanged.connect(lambda _i: self._apply_off())
            self.tbl.setCellWidget(i, 2, co)
            self._rows.append((n, cb, co))
        lv.addWidget(self.tbl, 1)
        row = QHBoxLayout()
        for lab, on in (("All on", True), ("All off", False)):
            b = QPushButton(lab)
            b.clicked.connect(lambda _c=False, o=on: self._all(o))
            row.addWidget(b)
        lv.addLayout(row)
        self._apply_off()
        return box

    def _all(self, on):
        for _n, cb, _co in self._rows:
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)
        self._apply_off()

    def _apply_off(self):
        off = [n for n, cb, _co in self._rows if not cb.isChecked()]
        self.canvas.set_off(off)
        roles = {n: "off" for n in off}
        for n, cb, co in self._rows:
            r_ = co.currentData()
            if cb.isChecked() and r_ and r_ != "auto":
                roles[n] = r_
        self.layer_roles = roles

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
            self.tip.setText(("<b>Ready.</b> «Import to …» (this floor, "
                              "imported now), «Furniture & fixtures from "
                              "CAD» or «Landscape from CAD» (only them, on "
                              "the level chosen) — or "
                              "draw the box / pick the point again."
                              if getattr(self, "acts", None) else
                              "<b>Ready.</b> «Use this floor» — or draw the "
                              "box / pick the point again.") + others)
        self.ok.setEnabled(c.region is not None and c.base is not None)
        if self.ok.isEnabled():
            self.whole = False             # a box drawn: not the whole file
        for b in getattr(self, "acts", ()):
            b.setEnabled(self.ok.isEnabled() or self.whole)
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
        if getattr(self, "acts", None):     # 3.64.60: then Import / Furniture
            for b in self.acts:
                b.setEnabled(True)
            self.tip.setText("<b>The whole drawing</b> is this floor — "
                             "«Import to …», «Furniture & fixtures from "
                             "CAD» or «Landscape from CAD».")
            return
        self.accept()


class LevelDlg(QDialog):
    """A part's ground level, over (+) or under (−) the main ground — typed
    in metres or in feet-inches; the other follows."""

    def __init__(self, parent, k, z0=0.0):
        super().__init__(parent)
        from PySide6.QtWidgets import QFormLayout, QLineEdit
        self.setWindowTitle(f"Level of part {k}")
        f = QFormLayout(self)
        f.addRow(QLabel("Ground level of this part, over (+) or under (−) "
                        "the main ground:"))
        self.m = QLineEdit()
        self.ft = QLineEdit()
        f.addRow("Metres", self.m)
        f.addRow("Feet-inches", self.ft)
        self._z = float(z0)
        self._fill(None)
        self.m.editingFinished.connect(lambda: self._read("m"))
        self.ft.editingFinished.connect(lambda: self._read("ft"))
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        no = QPushButton("Skip this part")
        no.clicked.connect(self.reject)
        r = QHBoxLayout()
        r.addWidget(ok)
        r.addWidget(no)
        f.addRow(r)

    def _fill(self, skip):
        from .host import ft_in_txt
        if skip != "m":
            self.m.setText(f"{self._z:.3f}")
        if skip != "ft":
            self.ft.setText(ft_in_txt(self._z))

    def _read(self, which):
        from .host import parse_len
        t = (self.m if which == "m" else self.ft).text().strip()
        if which == "m" and t.replace(".", "", 1).replace("-", "", 1)\
                .replace("+", "", 1).isdigit():
            t += "m"
        v = parse_len(t.lstrip("+"))
        if v is not None:
            self._z = max(-50.0, min(50.0, float(v)))
        self._fill(which)

    def _ok(self):
        self._read("m" if self.m.hasFocus() else "ft"
                   if self.ft.hasFocus() else "m")
        self.accept()

    def value(self):
        return self._z


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
        row2 = QHBoxLayout()
        self.b_part = QPushButton("Level parts…")
        self.b_part.setToolTip(
            "A plot on more than one level: after the plot limit, pick its "
            "parts one by one — each polyline picked is one level (asked "
            "for in metres and feet-inches); when it is complete, pick the "
            "next one, until the whole plot limit is covered.")
        self.b_part.clicked.connect(self._start_parts)
        self.b_rest = QPushButton("The rest is one level")
        self.b_rest.setToolTip("What is not yet in a part becomes the last "
                               "part")
        self.b_rest.clicked.connect(self._rest_part)
        self.b_undo = QPushButton("Remove last part")
        self.b_undo.clicked.connect(self._undo_part)
        self.b_wall = QPushButton("Boundary wall line…")
        self.b_wall.setToolTip(
            "The boundary wall is not always on the plot limit: pick its "
            "own line (else the wall's CAD layer is used, else the plot "
            "limit).")
        self.b_wall.clicked.connect(self._start_wall)
        self.b_marks = QPushButton("Levels from the plan's marks")
        self.b_marks.setToolTip(
            "Where the plan has levels written (LEV. +2'-6\", +0.45 …), "
            "a polyline is made round each — the closed outline holding "
            "the mark, else a patch round it — with that level. Edit them "
            "after with «Edit a part…».")
        self.b_marks.clicked.connect(self._auto_marks)
        self.b_edit = QPushButton("Edit a part…")
        self.b_edit.setToolTip(
            "Click a part, then drag its corners, click an edge to add a "
            "corner, right-click a corner to delete it; «Done editing» "
            "keeps it (its level can be changed).")
        self.b_edit.clicked.connect(self._edit_pick)
        self.b_done = QPushButton("Done editing")
        self.b_done.clicked.connect(self._edit_done)
        self.cov = QLabel()
        for w in (self.b_part, self.b_marks, self.b_edit, self.b_done,
                  self.b_rest, self.b_undo, self.b_wall, self.cov):
            row2.addWidget(w)
        row2.addStretch(1)
        v.addLayout(row2)
        self._phase = "plot"
        self._plot_poly = []
        self._parts = []                         # [(poly, z)] in drawing units
        self._wall_poly = []
        self._last_z = 0.0
        self._busy = False
        self._editing = None                     # (index, z) of a part
        self.canvas.on_part = self._part_clicked
        self.ok = QPushButton("Use this plot")
        self.ok.setStyleSheet("QPushButton { background: #2f6fdd; color: "
                              "white; font-weight: bold; padding: 4px 12px; }")
        self.ok.clicked.connect(self._ok_clicked)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(self.ok)
        row.addWidget(cancel)
        v.addLayout(row)
        self._changed()

    @property
    def poly(self):
        return list(self._plot_poly if self._phase != "plot"
                    else self.canvas.poly)

    @property
    def parts(self):
        """[(poly, z m)] — the level parts, each clipped by the parts
        before it (empty: one level)."""
        return [(list(p), z) for p, z in self._parts]

    @property
    def wall(self):
        """The boundary wall's own line picked here ([] — the layer, else
        the plot limit)."""
        return list(self._wall_poly)

    def _geo(self, poly):
        from shapely.geometry import Polygon
        return Polygon(poly).buffer(0)

    def _left(self):
        from shapely.ops import unary_union
        g = self._geo(self._plot_poly)
        if self._parts:
            g = g.difference(unary_union([self._geo(p) for p, _z in
                                          self._parts]))
        return g

    def _start_parts(self):
        c = self.canvas
        if self._phase == "plot":
            if not (c.closed and len(c.poly) >= 3):
                return
            self._plot_poly = list(c.poly)
            c.outline = list(c.poly)
        self._phase = "parts"
        c.poly, c.closed = [], False
        c.mode = "chain"
        c.update()
        self._changed()

    def _start_wall(self):
        c = self.canvas
        if self._phase == "plot":
            if not (c.closed and len(c.poly) >= 3):
                return
            self._plot_poly = list(c.poly)
            c.outline = list(c.poly)
        self._phase = "wall"
        c.poly, c.closed = [], False
        c.mode = "chain"
        c.update()
        self._changed()

    def _add(self, poly, z):
        from shapely.ops import unary_union
        g = self._geo(poly)
        if self._parts:
            g = g.difference(unary_union([self._geo(p) for p, _z in
                                          self._parts]))
        n0 = len(self._parts)
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon" and q.area > 1e-6:
                self._parts.append(([tuple(x) for x in
                                     list(q.exterior.coords)[:-1]], z))
        self.canvas.parts = list(self._parts)
        return len(self._parts) > n0

    def _level_for(self, k):
        """Ask the level of part k — metres and feet-inches, one value."""
        d = LevelDlg(self, k, self._last_z)
        if d.exec():
            self._last_z = d.value()
            return self._last_z
        return None

    def _complete(self):
        """A polyline picked and closed: in the parts phase it is one level
        — asked for, kept; the next pick is the next level."""
        c = self.canvas
        self._busy = True
        try:
            if self._phase == "parts":
                z = self._level_for(len(self._parts) + 1)
                if z is not None:
                    self._add(c.poly, z)
                c.poly, c.closed = [], False
            elif self._phase == "wall":
                self._wall_poly = list(c.poly)
                c.wall = list(c.poly)
                c.poly, c.closed = [], False
                self._phase = "parts"
            c.update()
        finally:
            self._busy = False
        self._changed()

    def _ok_clicked(self):
        if self._editing is not None:        # keep the part being edited
            self._edit_done()
        self.accept()

    def _need_plot(self):
        c = self.canvas
        if self._phase == "plot":
            if not (c.closed and len(c.poly) >= 3):
                return False
            self._plot_poly = list(c.poly)
            c.outline = list(c.poly)
            self._phase = "parts"
            c.poly, c.closed = [], False
        return True

    def _auto_marks(self):
        """A polyline round each level written on the plan."""
        if not self._need_plot():
            return
        from collections import Counter
        from shapely.geometry import LineString, Point, Polygon
        from shapely.ops import polygonize, unary_union
        from . import parking as PK
        plot = self._geo(self._plot_poly)
        near = plot.buffer(max(plot.length * 0.02, 1.0))
        marks = []
        for t in self.canvas.d.get("texts") or []:
            v = PK.level_note(t.get("text"))
            if v and v[1] is not None and near.contains(
                    Point(t["x"], t["y"])):
                marks.append((t["x"], t["y"], float(v[1]),
                              float(t.get("h") or 0.0)))
        if not marks:
            self.tip.setText("<b>No level marks found</b> inside the plot "
                             "(notes like «LEV. +2'-6\"»). Pick the levels "
                             "polyline by polyline instead.")
            return
        ref = Counter(round(m[2], 3) for m in marks).most_common(1)[0][0]
        x0, y0, x1, y1 = near.bounds
        ls = []
        for sg in self.canvas.d.get("segs") or []:
            if x0 <= sg[0] <= x1 and y0 <= sg[1] <= y1 and \
                    x0 <= sg[2] <= x1 and y0 <= sg[3] <= y1:
                ls.append(LineString([(sg[0], sg[1]), (sg[2], sg[3])]))
        for lp in self.canvas.d.get("loops") or []:
            if len(lp["pts"]) >= 3:
                ls.append(LineString(list(lp["pts"]) + [lp["pts"][0]]))
        cand = []
        try:
            cand = [g for g in polygonize(unary_union(ls))
                    if 0.002 * plot.area < g.area < 0.98 * plot.area
                    and plot.buffer(1e-6).contains(g.representative_point())]
        except Exception:  # noqa: BLE001
            cand = []
        cand.sort(key=lambda g: g.area)
        groups = {}                       # candidate index → [(z…)], poly
        loose = []
        for x, y, v, h in marks:
            pt = Point(x, y)
            k = next((i for i, g in enumerate(cand) if g.contains(pt)), None)
            if k is None:
                loose.append((x, y, v, h))
            else:
                groups.setdefault(k, []).append(v)
        made = []
        for k, vs in groups.items():
            z = Counter(round(q, 3) for q in vs).most_common(1)[0][0] - ref
            if abs(z) > 1e-6 or len(groups) + len(loose) == 1:
                made.append((cand[k], z))
        r_ = max(plot.length / 40.0, 1.0)
        for x, y, v, h in loose:                # no outline: a patch
            z = v - ref
            if abs(z) > 1e-6:
                made.append((Point(x, y).buffer(max(r_, 4 * h), 4)
                             .intersection(plot), z))
        made.sort(key=lambda m: m[0].area)       # small ones win the overlap
        for g, z in made:
            for q in getattr(g, "geoms", [g]):
                if q.geom_type == "Polygon":
                    self._add([tuple(c) for c in
                               list(q.exterior.coords)[:-1]], z)
        self.canvas.parts = list(self._parts)
        self.canvas.mode = "chain"
        self.canvas.update()
        self._changed()
        self.tip.setText(
            f"<b>{len(made)} level parts from the plan's marks</b> (main "
            "ground = the commonest mark). Fix any with «Edit a part…»; "
            "the rest of the plot stays on the main ground.")

    def _edit_pick(self):
        if self._need_plot() and self._parts:
            self.canvas.poly, self.canvas.closed = [], False
            self.canvas.mode = "partpick"
            self.tip.setText("<b>Click the part to edit</b> (inside it).")
            self.canvas.update()

    def _part_clicked(self, i):
        pg, z = self._parts.pop(i)
        self._editing = (i, z)
        self._last_z = z
        c = self.canvas
        c.parts = list(self._parts)
        c.poly, c.closed = [tuple(q) for q in pg], False
        c.mode = "edit"
        c.update()
        self.tip.setText(
            "<b>Editing the part</b> — drag a corner · click an edge to add "
            "a corner · right-click a corner to delete it · «Done editing» "
            "keeps it.")
        self._changed()

    def _edit_done(self):
        c = self.canvas
        if self._editing is None or len(c.poly) < 3:
            return
        i, z = self._editing
        zz = self._level_for(i + 1)
        pg = list(c.poly)
        self._parts.insert(min(i, len(self._parts)),
                           ([tuple(q) for q in pg], z if zz is None else zz))
        self._editing = None
        c.parts = list(self._parts)
        c.poly, c.closed = [], False
        c.mode = "chain"
        c.update()
        self._changed()

    def _rest_part(self):
        g = self._left()
        if g.is_empty:
            return
        z = self._level_for(len(self._parts) + 1)
        if z is None:
            return
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon" and q.area > 1e-6:
                self._parts.append(([tuple(x) for x in
                                     list(q.exterior.coords)[:-1]], z))
        self.canvas.parts = list(self._parts)
        self.canvas.update()
        self._changed()

    def _undo_part(self):
        if self._parts:
            self._parts.pop()
            self.canvas.parts = list(self._parts)
            self.canvas.update()
        self._changed()

    def _mode(self, m):
        self.canvas.mode = m
        self._changed()

    def _clear(self):
        if self._phase == "wall" and not self.canvas.poly:
            self._wall_poly = []
            self.canvas.wall = []
        self.canvas.poly, self.canvas.closed = [], False
        self.canvas.update()
        self._changed()

    def _changed(self):
        c = self.canvas
        if self._phase != "plot" and c.closed and len(c.poly) >= 3 \
                and not self._busy and c.mode != "edit":
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._complete)
            return
        ph = self._phase
        self.b_rest.setEnabled(ph == "parts")
        self.b_marks.setEnabled(ph != "plot" or (c.closed and
                                                 len(c.poly) >= 3))
        self.b_edit.setEnabled(bool(self._parts) and self._editing is None)
        self.b_done.setEnabled(self._editing is not None)
        self.b_undo.setEnabled(ph == "parts" and bool(self._parts))
        self.b_part.setEnabled(ph != "plot" or (c.closed and
                                                len(c.poly) >= 3))
        self.b_wall.setEnabled(ph != "plot" or (c.closed and
                                                len(c.poly) >= 3))
        if ph != "plot":
            tot = self._geo(self._plot_poly).area or 1.0
            left = self._left().area
            self.cov.setText(
                f"{len(self._parts)} levels · "
                f"{100 * (1 - left / tot):.0f}% of the plot covered" +
                (" · wall line set" if self._wall_poly else ""))
            if ph == "wall":
                self.tip.setText(
                    "<b>Boundary wall line</b> — click the wall's own line "
                    "(followed all the way round); the wall is built on it, "
                    "not on the plot limit. Then «Use this plot».")
            elif left / tot < 0.002:
                self.tip.setText("<b>The whole plot limit is covered.</b> "
                                 "«Use this plot».")
            else:
                self.tip.setText(
                    "<b>Level parts</b> — click ONE polyline (its line, "
                    "inside it, or its corners): it is one level, asked "
                    "for in metres / feet-inches. When it is complete, "
                    "click the next polyline for the next level, until the "
                    "plot limit is covered («The rest is one level» closes "
                    "it). What is left stays on the main ground.")
            self.ok.setEnabled(True)
            return
        self.cov.setText("")
        if c.closed:
            self.tip.setText(f"<b>Plot closed — {len(c.poly)} corners.</b> "
                             "«Use this plot», «Level parts…» (a plot on "
                             "more than one level), «Boundary wall line…», "
                             "or Clear to start again.")
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
