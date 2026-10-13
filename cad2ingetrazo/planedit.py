# SPDX-License-Identifier: GPL-3.0-or-later
"""Editing in the viewport itself.

- **Level marks.** In a CAD2IngeTrazo plan view, a double-click on a floor
  slab writes its finished level there — «+1'-0" F.F.L.», «±0'-0" F.F.L.»
  (the level's, with a sunk / raised room's step) — plan views only; a
  double-click on a mark takes it away. ``doc["ffl_marks"]`` = [{"id",
  "level", "x", "y"}]: the figure is worked out when drawn, so it follows
  the level's height.
- **Wall handles.** A CAD2IngeTrazo wall selected shows three handles:
  its two ends (drag to stretch it along its line; with Ctrl, anywhere)
  and its middle (drag to move it; with Shift, square to itself only).
  The walls joined at a moved end follow; its doors and windows keep
  their places.
"""
from __future__ import annotations

import math
import uuid

HANDLE_PX = 7          # half the handle's size
GRAB_PX = 11           # how near a press grabs it
SNAP = 0.25            # m: an end lands on another wall's end this near


class PlanEdit:
    def __init__(self, panel):
        from PySide6.QtCore import QObject

        self.panel = panel
        self.vp = panel.vp
        self.drag = None              # {"which", "wall", "p"(world), …}
        self._cache = (None, None)    # (sel, raw id) → wall info

        outer = self

        class _Filter(QObject):
            def eventFilter(self, obj, ev):     # noqa: N802
                try:
                    return outer.event(ev)
                except Exception:  # noqa: BLE001
                    from .host import log_error
                    log_error("planedit.event")
                    outer.drag = None
                    return False
        self._filter = _Filter(panel)
        self.vp.installEventFilter(self._filter)

    # ---- helpers ------------------------------------------------------------
    def _raw(self):
        from .host import KEY
        return (getattr(self.vp.scene, "plugin_data", {}) or {}).get(KEY)

    def _world(self, pos, z):
        from PySide6.QtGui import QVector3D
        o, d = self.vp._pixel_to_ray(pos.x(), pos.y())
        if o is None:
            return None
        p = self.vp._ray_plane(o, d, QVector3D(0.0, 0.0, z),
                               QVector3D(0.0, 0.0, 1.0))
        return None if p is None else (p.x(), p.y())

    def _px(self, x, y, z):
        from PySide6.QtGui import QVector3D
        return self.vp._world_to_pixel(QVector3D(x, y, z))

    def _wall(self):
        """{"rec", "z", "level"} of the CAD2IngeTrazo wall selected (a
        straight one), or None — cached per selection and document."""
        sel = getattr(self.panel, "_sel_key", None)
        if not sel or sel[0] not in ("wall", "beam"):
            return None
        raw = self._raw()
        key = (sel, id(raw))
        if self._cache[0] == key:
            return self._cache[1]
        info = None
        try:
            from . import project as PJ
            doc = PJ.load(raw)
            w = PJ.find_record(doc, sel[0], sel[1])
            if w is not None and w.get("kind", "line") == "line" and \
                    "a" in w:
                el = PJ.elevations(doc["arch"])
                i = next(k for k, lv in enumerate(doc["arch"]["levels"])
                         if lv["id"] == w["level"])
                if sel[0] == "beam":       # its soffit, under the slab
                    top = el[i + 1] if i + 1 < len(el) else el[i] + 3.0
                    z = top - float(w.get("h", 0.6))
                else:
                    z = el[i] + float(w.get("base", 0.0)) + 0.02
                info = {"rec": w, "z": z, "level": w["level"],
                        "kind": sel[0]}
        except Exception:  # noqa: BLE001
            info = None
        self._cache = (key, info)
        return info

    def _handles(self, info):
        a, b = info["rec"]["a"], info["rec"]["b"]
        return {"a": tuple(a), "b": tuple(b),
                "m": ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)}

    # ---- events ---------------------------------------------------------------
    def event(self, ev) -> bool:
        from PySide6.QtCore import QEvent, Qt
        t = ev.type()
        if getattr(self, "rect", None) is not None:
            return self._rect_event(ev)
        if t == QEvent.MouseButtonDblClick and ev.button() == Qt.LeftButton:
            return self._double(ev)
        if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            return self._press(ev)
        if t == QEvent.MouseMove and self.drag is not None:
            self._move(ev)
            return True
        if t == QEvent.MouseButtonRelease and self.drag is not None and \
                ev.button() == Qt.LeftButton:
            self._release(ev)
            return True
        if t == QEvent.KeyPress and getattr(self, "pick", None) is not None \
                and ev.key() == Qt.Key_Escape:
            self.pick = None
            self.panel.flash("Cancelled")
            return True
        if t == QEvent.KeyPress and self.drag is not None and \
                ev.key() == Qt.Key_Escape:
            self.drag = None
            self.vp.update()
            return True
        return False

    def _select_tool(self) -> bool:
        tool = getattr(self.vp, "active_tool", None)
        return tool is None or bool(getattr(tool, "box_select", False))

    def pick_point(self, z, cb, msg="Click the point in the model "
                   "(Esc cancels)"):
        """The next left click in the viewport → ``cb((x, y))`` (at height
        ``z``); Esc cancels."""
        self.pick = (z, cb)
        self.panel.flash(msg, 10000)

    def pick_rect(self, z, cb, msg="Click one corner of the rectangle, "
                  "then the opposite corner (Esc cancels)"):
        """Two clicks in the viewport at height ``z`` → ``cb(a, b)``, the
        rectangle's opposite corners; a rubber rectangle follows the mouse
        between them. Esc cancels."""
        self.rect = {"z": z, "cb": cb, "a": None, "cur": None}
        self.panel.flash(msg, 15000)

    def _rect_event(self, ev) -> bool:
        from PySide6.QtCore import QEvent, Qt, QTimer
        rc = getattr(self, "rect", None)
        if rc is None:
            return False
        t = ev.type()
        if t == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
            self.rect = None
            self.panel.flash("Cancelled")
            self.vp.update()
            return True
        if t == QEvent.MouseMove and rc["a"] is not None:
            p = self._world(ev.position(), rc["z"])
            if p is not None:
                rc["cur"] = p
                self.vp.update()
            return False
        if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            p = self._world(ev.position(), rc["z"])
            if p is None:
                return True
            if rc["a"] is None:
                rc["a"] = p
                rc["cur"] = p
                self.panel.flash("Now click the opposite corner (Esc "
                                 "cancels)", 15000)
                return True
            a, cb = rc["a"], rc["cb"]
            self.rect = None
            self.vp.update()
            QTimer.singleShot(0, lambda: cb(a, p))
            return True
        if t in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick) \
                and ev.button() == Qt.LeftButton:
            return True
        return False

    def _press(self, ev) -> bool:
        pk = getattr(self, "pick", None)
        if pk is not None:
            self.pick = None
            p = self._world(ev.position(), pk[0])
            if p is not None:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: pk[1](p))
            return True
        if not self._select_tool():
            return False
        if self._box_press(ev):
            return True
        info = self._wall()
        if info is None:
            return False
        pos = ev.position()
        best = None
        for k, (x, y) in self._handles(info).items():
            p = self._px(x, y, info["z"])
            if p is None:
                continue
            d = math.hypot(p[0] - pos.x(), p[1] - pos.y())
            if d <= GRAB_PX and (best is None or d < best[0]):
                best = (d, k)
        if best is None:
            return False
        w = info["rec"]
        self.drag = {"which": best[1], "info": info,
                     "a": tuple(w["a"]), "b": tuple(w["b"]),
                     "na": tuple(w["a"]), "nb": tuple(w["b"])}
        return True

    # ---- section box handles -------------------------------------------------
    def _secbox(self):
        raw = self._raw() or {}
        b = (raw.get("settings") or {}).get("section_box")
        return [float(v) for v in b] if b and len(b) == 6 else None

    def _box_handles(self, box):
        """[(axis 0/1/2, side 0 = min / 1 = max, centre (x, y, z))]."""
        c = [(box[k] + box[k + 3]) / 2 for k in range(3)]
        out = []
        for k in range(3):
            for sd in (0, 1):
                p = list(c)
                p[k] = box[k + 3 * sd]
                out.append((k, sd, tuple(p)))
        return out

    def _box_press(self, ev) -> bool:
        box = self._secbox()
        if box is None:
            return False
        pos = ev.position()
        best = None
        for k, sd, c in self._box_handles(box):
            p = self._px(*c)
            if p is None:
                continue
            dd = math.hypot(p[0] - pos.x(), p[1] - pos.y())
            if dd <= GRAB_PX + 6 and (best is None or dd < best[0]):
                best = (dd, k, sd, c, p)
        if best is None:
            return False
        _dd, k, sd, c, p = best
        q = list(c)
        q[k] += 1.0                              # 1 m along the axis
        p1 = self._px(*q)
        if p1 is None:
            return False
        dvec = (p1[0] - p[0], p1[1] - p[1])
        if math.hypot(*dvec) < 1e-3:
            self.panel.flash("Look at that face of the box from the side "
                             "to drag it")
            return True
        self.drag = {"box": True, "k": k, "sd": sd, "box0": box,
                     "cur": list(box), "p0": (pos.x(), pos.y()),
                     "dvec": dvec}
        return True

    def _box_move(self, ev):
        d = self.drag
        pos = ev.position()
        dx, dy = pos.x() - d["p0"][0], pos.y() - d["p0"][1]
        v = d["dvec"]
        m = (dx * v[0] + dy * v[1]) / (v[0] * v[0] + v[1] * v[1])
        i = d["k"] + 3 * d["sd"]
        val = round((d["box0"][i] + m) / 0.05) * 0.05
        cur = list(d["box0"])
        if d["sd"] == 0:
            val = min(val, cur[d["k"] + 3] - 0.1)
        else:
            val = max(val, cur[d["k"]] + 0.1)
        cur[i] = round(val, 4)
        d["cur"] = cur
        self.vp.update()

    def _box_release(self):
        d, self.drag = self.drag, None
        if d["cur"] == d["box0"]:
            self.vp.update()
            return
        from . import project as PJ
        doc = PJ.load(self._raw())
        doc["settings"]["section_box"] = [round(v, 4) for v in d["cur"]]
        self.panel.commit(doc, "Section box: face moved")
        try:
            dlg = getattr(self.panel, "_sb_dlg", None)
            if dlg is not None and hasattr(dlg, "_put"):
                dlg._put(d["cur"])
        except Exception:  # noqa: BLE001
            pass

    def _move(self, ev):
        from PySide6.QtCore import Qt
        d = self.drag
        if d.get("box"):
            self._box_move(ev)
            return
        info = d["info"]
        p = self._world(ev.position(), info["z"])
        if p is None:
            return
        mods = ev.modifiers()
        a, b = d["a"], d["b"]
        L = math.dist(a, b) or 1e-9
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        if d["which"] == "m":
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            dx, dy = p[0] - m[0], p[1] - m[1]
            if mods & Qt.ShiftModifier:          # square to the wall only
                n = (-u[1], u[0])
                k = dx * n[0] + dy * n[1]
                dx, dy = n[0] * k, n[1] * k
            dx, dy = round(dx, 2), round(dy, 2)
            d["na"] = (a[0] + dx, a[1] + dy)
            d["nb"] = (b[0] + dx, b[1] + dy)
        else:
            fixed = b if d["which"] == "a" else a
            if mods & Qt.ControlModifier:        # anywhere
                q = (round(p[0], 2), round(p[1], 2))
            else:                                 # along its own line
                s = (p[0] - fixed[0]) * (u[0]) + (p[1] - fixed[1]) * u[1]
                s = round(s, 2)
                q = (fixed[0] + u[0] * s, fixed[1] + u[1] * s)
            q = self._snap_end(q, info)
            if math.dist(q, fixed) >= 0.1:
                if d["which"] == "a":
                    d["na"] = q
                else:
                    d["nb"] = q
        self.vp.update()

    def _snap_end(self, q, info):
        try:
            from . import project as PJ
            doc = PJ.load(self._raw())
            best = None
            for w in doc["arch"]["walls"]:
                if w["level"] != info["level"] or \
                        w["id"] == info["rec"]["id"] or "a" not in w:
                    continue
                for e in (w["a"], w["b"]):
                    dd = math.dist(q, e)
                    if dd <= SNAP and (best is None or dd < best[0]):
                        best = (dd, tuple(e))
            return best[1] if best else q
        except Exception:  # noqa: BLE001
            return q

    def _release(self, ev):
        if self.drag is not None and self.drag.get("box"):
            self._box_release()
            return
        d, self.drag = self.drag, None
        if d is None or (d["na"] == d["a"] and d["nb"] == d["b"]):
            self.vp.update()
            return
        from . import project as PJ
        doc = PJ.load(self._raw())
        kind = d["info"].get("kind", "wall")
        if kind == "beam":
            n = apply_beam_edit(doc, d["info"]["rec"]["id"], d["a"], d["b"],
                                d["na"], d["nb"])
            msg = "Beam moved" if d["which"] == "m" else \
                ("Beam extended" if math.dist(d["na"], d["nb"]) >
                 math.dist(d["a"], d["b"]) else "Beam trimmed")
        else:
            n = apply_wall_edit(doc, d["info"]["rec"]["id"], d["a"], d["b"],
                                d["na"], d["nb"])
            msg = "Wall moved" if d["which"] == "m" else "Wall stretched"
        if n:
            msg += f" ({n} joined wall(s) followed)"
        self.panel.commit(doc, msg)
        try:
            self.panel._reselect((kind, d["info"]["rec"]["id"]))
        except Exception:  # noqa: BLE001
            pass

    def _double(self, ev) -> bool:
        """A double-click in a plan view: a level mark on the slab there
        (or the mark there taken away)."""
        if not self._select_tool():
            return False
        from . import labels
        from . import project as PJ
        name = labels._level_of_view(self.vp.scene)
        if name is None:
            return False
        raw = self._raw()
        if raw is None:
            return False
        doc = PJ.load(raw)
        arch = doc["arch"]
        el = PJ.elevations(arch)
        i = next((k for k, lv in enumerate(arch["levels"])
                  if lv["name"] == name), None)
        if i is None:
            return False
        lid = arch["levels"][i]["id"]
        p = self._world(ev.position(), el[i])
        if p is None:
            return False
        marks = doc.setdefault("ffl_marks", [])
        near = [m for m in marks if m["level"] == lid and
                math.dist((m["x"], m["y"]), p) < 0.6]
        if near:
            doc["ffl_marks"] = [m for m in marks if m not in near]
            PJ.store_only(self.vp, doc)
            self.panel.flash("Level mark taken away")
            return True
        if not on_slab(doc, lid, p):
            return False
        marks.append({"id": uuid.uuid4().hex[:8], "level": lid,
                      "x": round(p[0], 3), "y": round(p[1], 3)})
        PJ.store_only(self.vp, doc)
        self.panel.flash(f"Level mark: {mark_text(doc, lid, p)} "
                         "(double-click it again to take it away)")
        return True

    # ---- drawing ----------------------------------------------------------------
    def _draw_box_handles(self, painter, box):
        """A grip on each face of the section box: a dot and an arrow
        pointing out — drag it to move that face."""
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QBrush, QColor, QPen
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        dr = self.drag if (self.drag or {}).get("box") else None
        for k, sd, c in self._box_handles(box):
            p = self._px(*c)
            if p is None:
                continue
            q = list(c)
            q[k] += (1.0 if sd else -1.0)
            p1 = self._px(*q)
            on = dr is not None and dr["k"] == k and dr["sd"] == sd
            col = QColor(20, 110, 230) if on else QColor(230, 120, 20)
            painter.setPen(QPen(col, 2.0))
            if p1 is not None:
                L = math.hypot(p1[0] - p[0], p1[1] - p[1])
                if L > 1e-3:
                    e = (p[0] + (p1[0] - p[0]) / L * 26,
                         p[1] + (p1[1] - p[1]) / L * 26)
                    _arrow(painter, p, e)
            painter.setBrush(QBrush(col))
            painter.drawEllipse(QPointF(p[0], p[1]), 6.0, 6.0)
        painter.restore()

    def draw(self, viewport, painter):
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QPen
        try:                                 # the section box and handles
            box = self._secbox()
            dr = self.drag
            if dr is not None and dr.get("box"):
                box = dr["cur"]
            if box:
                from . import secbox
                secbox.draw(self.vp, painter, box)
                self._draw_box_handles(painter, box)
        except Exception:  # noqa: BLE001
            pass
        rc = getattr(self, "rect", None)
        if rc is not None and rc.get("a") is not None and rc.get("cur"):
            (x0, y0), (x1, y1) = rc["a"], rc["cur"]
            pts = [self._px(x, y, rc["z"]) for x, y in
                   ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            if all(pts):
                painter.save()
                painter.setRenderHint(painter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(QColor(230, 60, 30), 2.0, Qt.DashLine))
                for i in range(4):
                    pa, pb = pts[i], pts[(i + 1) % 4]
                    painter.drawLine(QPointF(pa[0], pa[1]),
                                     QPointF(pb[0], pb[1]))
                from .host import len_txt
                painter.drawText(QPointF(pts[2][0] + 8, pts[2][1] + 14),
                                 f"{len_txt(abs(x1 - x0))} × "
                                 f"{len_txt(abs(y1 - y0))}")
                painter.restore()
        info = self._wall() if self.drag is None else self.drag.get("info")
        if info is None:
            return
        z = info["z"]
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        if self.drag is not None:
            a, b = self.drag["na"], self.drag["nb"]
            pa, pb = self._px(*a, z), self._px(*b, z)
            if pa and pb:
                pen = QPen(QColor(230, 90, 20), 2.0, Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(QPointF(*pa[:2]), QPointF(*pb[:2]))
                from .host import len_txt
                painter.setPen(QColor(230, 90, 20))
                painter.drawText(QPointF((pa[0] + pb[0]) / 2 + 8,
                                         (pa[1] + pb[1]) / 2 - 8),
                                 len_txt(math.dist(a, b)))
            hs = {"a": a, "b": b, "m": ((a[0] + b[0]) / 2,
                                        (a[1] + b[1]) / 2)}
        else:
            hs = self._handles(info)
        for k, (x, y) in hs.items():
            p = self._px(x, y, z)
            if p is None:
                continue
            r = HANDLE_PX
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.setBrush(QColor(20, 110, 230) if k != "m"
                             else QColor(230, 140, 20))
            if k == "m":
                painter.drawEllipse(QPointF(p[0], p[1]), r, r)
            else:
                painter.drawRect(QRectF(p[0] - r, p[1] - r, 2 * r, 2 * r))
        painter.restore()


# ---- the model's side ---------------------------------------------------------------
def _arrow(painter, a, b):
    from PySide6.QtCore import QPointF
    painter.drawLine(QPointF(*a), QPointF(*b))
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    for s in (1, -1):
        q = (b[0] - u[0] * 7 + s * -u[1] * 4, b[1] - u[1] * 7 + s * u[0] * 4)
        painter.drawLine(QPointF(*b), QPointF(*q))


def on_slab(doc, lid, p) -> bool:
    """Whether ``p`` stands on the floor slab of ``lid`` (not in a hole)."""
    from shapely.geometry import Point, Polygon

    from . import project as PJ
    pt = Point(p)
    for s in PJ._floor_slabs(doc, lid):
        try:
            poly = Polygon(s["corners"])
            if not poly.buffer(0).contains(pt):
                continue
            if any(Polygon(h).buffer(0).contains(pt)
                   for h in s.get("holes") or [] if len(h) >= 3):
                continue
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def mark_value(doc, lid, p) -> float:
    from . import project as PJ
    arch = doc["arch"]
    el = PJ.elevations(arch)
    i = next(k for k, lv in enumerate(arch["levels"]) if lv["id"] == lid)
    try:
        off = PJ.floor_offset_at(doc, lid, p)
    except Exception:  # noqa: BLE001
        off = 0.0
    return el[i] + off


def mark_text(doc, lid, p) -> str:
    from . import project as PJ
    return PJ.ffl_text(mark_value(doc, lid, p))


def apply_wall_edit(doc, wid, a0, b0, a1, b1) -> int:
    """The wall ``wid`` from a0–b0 to a1–b1: the walls joined at a moved
    end follow it; its doors and windows stay where they stood. The
    number of joined walls moved."""
    arch = doc["arch"]
    w = next((x for x in arch["walls"] if x["id"] == wid), None)
    if w is None:
        return 0
    moved = 0
    for old, new in ((a0, a1), (b0, b1)):
        if math.dist(old, new) < 1e-6:
            continue
        for o in arch["walls"]:
            if o["id"] == wid or o["level"] != w["level"] or "a" not in o:
                continue
            for k in ("a", "b"):
                if math.dist(tuple(o[k]), old) <= 0.03:
                    o[k] = [round(new[0], 4), round(new[1], 4)]
                    moved += 1
    L0 = math.dist(a0, b0) or 1e-9
    u0 = ((b0[0] - a0[0]) / L0, (b0[1] - a0[1]) / L0)
    L1 = math.dist(a1, b1) or 1e-9
    u1 = ((b1[0] - a1[0]) / L1, (b1[1] - a1[1]) / L1)
    same = math.dist((a1[0] - a0[0], a1[1] - a0[1]),
                     (b1[0] - b0[0], b1[1] - b0[1])) < 1e-6
    for o in arch["openings"]:
        if o["wall"] != wid:
            continue
        if not same:                # stretched: it keeps its place
            c = (a0[0] + u0[0] * o["pos"], a0[1] + u0[1] * o["pos"])
            pos = (c[0] - a1[0]) * u1[0] + (c[1] - a1[1]) * u1[1]
            half = float(o["w"]) / 2
            o["pos"] = round(min(max(pos, half), max(L1 - half, half)), 4)
    w["a"] = [round(a1[0], 4), round(a1[1], 4)]
    w["b"] = [round(b1[0], 4), round(b1[1], 4)]
    return moved


def apply_beam_edit(doc, bid, a0, b0, a1, b1) -> int:
    """The beam ``bid`` from a0–b0 to a1–b1; the beams joined at a moved
    end follow. The number of joined beams moved."""
    st = doc["arch"]["structure"]
    b = next((e for e in st if e["id"] == bid and e["type"] == "beam"), None)
    if b is None:
        return 0
    moved = 0
    for old, new in ((a0, a1), (b0, b1)):
        if math.dist(old, new) < 1e-6:
            continue
        for e in st:
            if e["id"] == bid or e["type"] != "beam" or \
                    e["level"] != b["level"]:
                continue
            for k in ("a", "b"):
                if math.dist(tuple(e[k]), old) <= 0.03:
                    e[k] = [round(new[0], 4), round(new[1], 4)]
                    moved += 1
    b["a"] = [round(a1[0], 4), round(a1[1], 4)]
    b["b"] = [round(b1[0], 4), round(b1[1], 4)]
    return moved


def trim_extend_beam(doc, bid, end, how, value=0.0, pt=None):
    """One end of a beam moved along its own line: ``how`` = «length»
    (``value`` m: + extends, − trims), «point» (to ``pt`` projected on the
    beam), «column» (to the face of the nearest column ahead or behind it
    in its line), «beam» (to the nearest beam / wall it meets). ``end`` =
    "a" | "b" | "near" (the end nearest ``pt``). (ok, why)."""
    from shapely.geometry import LineString, Point, Polygon

    from . import project as PJ
    from .engine import structure as S
    st = doc["arch"]["structure"]
    b = next((e for e in st if e["id"] == bid and e["type"] == "beam"), None)
    if b is None:
        return False, "No such beam"
    a, c = tuple(b["a"]), tuple(b["b"])
    L = math.dist(a, c)
    if L < 1e-6:
        return False, "The beam has no length"
    if end == "near" and pt is not None:
        end = "a" if math.dist(pt, a) <= math.dist(pt, c) else "b"
    fixed, moving = (c, a) if end == "a" else (a, c)
    ux, uy = (moving[0] - fixed[0]) / L, (moving[1] - fixed[1]) / L
    if how == "length":
        s_new = L + float(value)
    elif how == "point":
        if pt is None:
            return False, "No point"
        s_new = (pt[0] - fixed[0]) * ux + (pt[1] - fixed[1]) * uy
    else:                                    # to a column / a beam or wall
        ray = LineString([(fixed[0] - ux * 0.01, fixed[1] - uy * 0.01),
                          (fixed[0] + ux * 60.0, fixed[1] + uy * 60.0)])
        targets = []
        if how == "column":
            for e in st:
                if e["type"] == "column" and e["level"] == b["level"]:
                    try:
                        targets.append(Polygon(S.column_outline(e, 0.0))
                                       .buffer(0))
                    except Exception:  # noqa: BLE001
                        pass
        else:
            for e in st:
                if e["type"] == "beam" and e["level"] == b["level"] and \
                        e["id"] != bid:
                    targets.append(LineString([tuple(e["a"]),
                                               tuple(e["b"])]).buffer(
                        float(e["w"]) / 2))
            for w in doc["arch"]["walls"]:
                if w["level"] == b["level"] and "a" in w:
                    targets.append(LineString([tuple(w["a"]),
                                               tuple(w["b"])]).buffer(
                        float(w["t"]) / 2))
        best = None
        for tg in targets:
            hit = ray.intersection(tg)
            if hit.is_empty:
                continue
            ss = [(q[0] - fixed[0]) * ux + (q[1] - fixed[1]) * uy
                  for g in getattr(hit, "geoms", [hit])
                  for q in getattr(g, "coords", [])]
            ss = [v for v in ss if v > 0.3]
            if not ss:
                continue
            s_ = min(ss)                 # its face toward the beam
            if best is None or abs(s_ - L) < abs(best - L):
                best = s_                # the one nearest the end now
        if best is None:
            return False, ("No column in the beam's line" if how ==
                           "column" else "Nothing in the beam's line")
        s_new = best
    if s_new < 0.2:
        return False, "That would leave the beam under 0.2 m"
    new = (fixed[0] + ux * s_new, fixed[1] + uy * s_new)
    if end == "a":
        apply_beam_edit(doc, bid, a, c, new, c)
    else:
        apply_beam_edit(doc, bid, a, c, a, new)
    return True, f"{s_new:.2f} m"
