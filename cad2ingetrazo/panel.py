# SPDX-License-Identifier: GPL-3.0-or-later
"""The CAD2IngeTrazo panel — a tab in IngeTrazo's side tray, laid out as
the workflow: Project & levels → Import plan → Openings → Structure →
Roof → Rooms → Selected element → Sheets & export, each part folding away.
Every button is one Ctrl+Z."""
from __future__ import annotations

import math
import os

from PySide6.QtCore import QEvent, QObject, QSettings, Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSlider,
                               QAbstractSpinBox, QApplication, QCheckBox,
                               QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from . import cadread, ghost, project as PJ
from . import site as SITE_
from .pickdlg import PlotDialog, PortionDialog
from .host import FOUNDATION
from .engine import model as M
from .engine import spaces
from .host import log_error

from .host import area_txt, len_txt, parse_len  # noqa: E402
SET = "cad2ingetrazo2"
NEW = "__new_above__"          # the level combo's «＋ next level» entry
NEW_BELOW = "__new_below__"    # …«＋ basement»
SITE_LV = "__site__"           # …«Site · ground»: plot, boundary, gates
ROOF_NEW = "__roof__"          # …«＋ Roof level»
VIRTUAL = (NEW, NEW_BELOW, FOUNDATION, SITE_LV, ROOF_NEW)
BLUE = "#2f6fdd"


def _settings():
    return QSettings("ingetrazo", SET)


def _fold(title, key, open_=True):
    """A section that folds (the host's), or a plain group box."""
    try:
        from views.fold_section import FoldSection
        f = FoldSection(title, f"{SET}/fold/{key}", default_open=open_)
        return f, f.body
    except Exception:  # noqa: BLE001
        g = QGroupBox(title)
        return g, g



def _place_on_screen(dlg, pos):
    """A small dialog by the cursor, kept whole on its screen."""
    x, y = pos.x() + 12, pos.y() + 12
    try:
        scr = QApplication.screenAt(pos) or QApplication.primaryScreen()
        r = scr.availableGeometry()
        w, h = dlg.width(), dlg.height()
        x = max(r.left(), min(x, r.right() - w - 8))
        y = max(r.top(), min(y, r.bottom() - h - 40))
    except Exception:  # noqa: BLE001
        pass
    dlg.move(x, y)

class LenSpin(QDoubleSpinBox):
    """A length field in the document's units (m, cm, mm, feet-inches…):
    it shows and reads them, and holds metres."""

    def __init__(self, step):
        super().__init__()
        self._step_m = step
        self.setDecimals(5)
        self.setKeyboardTracking(False)

    def textFromValue(self, v):
        from .host import len_txt
        return len_txt(v)

    def valueFromText(self, text):
        from .host import parse_len
        v = parse_len(text)
        return self.value() if v is None else v

    def validate(self, text, pos):
        from PySide6.QtGui import QValidator
        from .host import parse_len
        ok = parse_len(text) is not None
        return (QValidator.Acceptable if ok else QValidator.Intermediate,
                text, pos)

    def retune(self):
        """The units changed: the step and the text follow."""
        from .host import imperial
        self.setSingleStep(0.0254 if imperial() and self._step_m < 0.3
                           else 0.3048 if imperial() else self._step_m)
        self.lineEdit().setText(self.textFromValue(self.value()))


def _spin(lo, hi, val, step=0.05, dec=2, suffix=" m"):
    if suffix == " m":
        s = LenSpin(step)
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(val)
        s.setMinimumWidth(40)
        return s
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    s.setSuffix(suffix)
    s.setMinimumWidth(40)
    return s


def _btn(text, fn, tip="", primary=False):
    b = QPushButton(text)
    # called with no arguments: Qt's «checked» flag would otherwise land in
    # a handler's first optional argument (Isolate level ran as Show all,
    # «Basement outer walls → RCC» as Undo)
    b.clicked.connect(lambda _c=False, f=fn: f())
    if tip:
        b.setToolTip(tip)
    if primary:
        b.setStyleSheet(f"QPushButton {{ background: {BLUE}; color: white; "
                        "font-weight: bold; padding: 4px 8px; }")
    return b


def _form(parent):
    f = QFormLayout(parent)
    f.setRowWrapPolicy(QFormLayout.WrapLongRows)
    f.setContentsMargins(6, 6, 6, 6)
    return f


#: what the «Selected element» part shows, per kind:
#: (key, label, kind, options / range)
from . import matlib as _ML  # noqa: E402
FIELDS = {
    "wall": [("type", "Wall type", "choice", ("solid", "curtain")),
             ("glass", "Curtain wall glass", "choice",
              ("clear", "double", "lowe", "grey", "bronze", "green",
               "blue_ref", "silver_ref", "frosted")),
             ("rail", "Build as railing", "choice",
              ("solid", "ss_bars", "ms_grill", "glass", "glass_post", "pipe",
               "wood", "wall_rail")),
             ("t", "Thickness", "len", (0.02, 3.0)),
             ("grid", "Curtain wall: mullions every", "len", (0.3, 6.0)),
             ("tgrid", "Curtain wall: transoms every", "len", (0.3, 6.0)),
             ("cw_low", "Curtain wall: lower panel height", "len",
              (0.0, 6.0)),
             ("cw_up", "Curtain wall: upper panel height", "len", (0.0, 6.0)),
             ("cw_fill", "Curtain wall: lower / upper panels", "choice",
              ("glass", "spandrel")),
             ("top_att", "Top", "choice", ("slab", "free")),
             ("bot_att", "Bottom", "choice", ("slab", "free")),
             ("height", "Height", "height", (0.1, 50.0)),
             ("base", "Base offset", "len", (-5.0, 10.0))],
    "opening": [("kind", "Type", "choice", ("door", "window", "void")),
                ("w", "Width", "len", (0.2, 20.0)),
                ("h", "Height", "len", (0.2, 20.0)),
                ("sill", "Sill", "len", (0.0, 20.0)),
                ("pos", "Centre along wall", "len", (0.0, 500.0)),
                ("swing", "Hinge", "choice", ("left", "right")),
                ("face", "Opens to", "choice", (1, -1)),
                ("style", "Opening type", "choice",
                 ("hinged", "main", "glass", "alu_glass", "louvre", "glazed",
                  "sliding",
                  "pocket", "folding", "rolling", "garage", "casement",
                  "fixed", "louvre", "top-hung")),
                ("leaves", "Leaves (single / double)", "choice", (1, 2)),
                ("head", "Head", "choice", ("flat", "transom", "arch")),
                ("frame", "Frame", "choice",
                 ("auto", "wood", "aluminium", "steel", "upvc")),
                ("frame_w", "Frame width (its face)", "len", (0.02, 0.30)),
                ("frame_d", "Frame thickness (its depth)", "len",
                 (0.03, 0.50)),
                ("panel", "Door panel", "choice",
                 ("auto", "flush", "panel2", "panel4", "panel6",
                  "glazed_half", "glazed_full", "louvred", "ledged")),
                ("handle", "Door handle", "choice",
                 ("auto", "lever_rose", "lever_plate", "knob", "pull_bar",
                  "d_pull", "flush", "none")),
                ("glass", "Glass type", "choice",
                 ("clear", "double", "lowe", "grey", "bronze", "green",
                  "blue_ref", "silver_ref", "frosted"))],
    "column": [("shape", "Shape", "choice", ("rect", "round")),
               ("w", "Width / Ø", "len", (0.05, 5.0)),
               ("d", "Depth", "len", (0.05, 5.0)),
               ("angle", "Angle", "deg", (-360.0, 360.0)),
               ("height", "Height", "height", (0.2, 50.0)),
               ("base", "Base offset", "len", (-20.0, 20.0))],
    "ramp": [("slope", "Slope", "pct", (0.5, 30.0)),
             ("rise", "Climb (− = down)", "len", (-8.0, 8.0)),
             ("t", "Slab thickness", "len", (0.05, 1.0))],
    "core": [("height", "Height", "height", (0.2, 50.0)),
             ("base", "Base offset", "len", (-20.0, 20.0))],
    "beam": [("w", "Width", "len", (0.05, 3.0)),
             ("h", "Depth", "len", (0.05, 5.0))],
    "slab": [("t", "Thickness", "len", (0.02, 3.0)),
             ("offset", "Top offset", "len", (-3.0, 3.0)),
             ("fin", "Floor finish", "choice", ("rooms", "whole", "off")),
             ("fin_t", "Finish thickness (0 = default)", "len", (0.0, 0.3))],
    "footing": [("w", "Width", "len", (0.1, 10.0)),
                ("d", "Depth", "len", (0.05, 5.0))],
    "stair": [("rise", "Riser (max)", "len", (0.10, 0.25)),
              ("going", "Tread (going)", "len", (0.18, 0.45)),
              ("risers", "Number of risers (steps)", "int", (2, 80)),
              ("stype", "Stair type", "choice",
               ("monolithic", "solid", "open", "cantilever")),
              ("rail", "Railing", "choice",
               ("none", "ss_bars", "ms_grill", "glass", "glass_post", "pipe",
                "wood", "wall_rail", "solid")),
              ("rail_h", "Railing height", "len", (0.3, 2.0)),
              ("rail_sides", "Railing sides", "choice",
               ("inner", "outer", "both", "none")),
              ("rail_off", "Railing in from the flight's edge", "len",
               (0.0, 0.5)),
              ("rail_gap", "Baluster spacing (0 = the type's)", "len",
               (0.0, 2.0)),
              ("rail_ext", "Run-on past the first / last step", "len",
               (0.0, 1.0))],
    "stairrail": [("rail", "Railing type", "choice",
                   ("none", "ss_bars", "ms_grill", "glass", "glass_post",
                    "pipe", "wood", "wall_rail", "solid")),
                  ("rail_h", "Railing height", "len", (0.3, 2.0)),
                  ("rail_sides", "Railing sides", "choice",
                   ("inner", "outer", "both", "none")),
                  ("rail_off", "Railing in from the flight's edge", "len",
                   (0.0, 0.5)),
                  ("rail_gap", "Baluster spacing (0 = the type's)", "len",
                   (0.0, 2.0)),
                  ("rail_ext", "Run-on past the first / last step", "len",
                   (0.0, 1.0))],
    "dig": [("name", "Name", "text", None)],
    "room": [("size", "Size (width × length)", "info", None),
             ("name", "Room name", "text", None),
             ("ceiling", "False ceiling", "choice",
              ("level", "none", "gypsum", "tiles", "pop", "wood", "pvc",
               "metal")),
             ("ceiling_h", "Ceiling height from floor", "len", (2.0, 8.0)),
             ("finish", "Floor finish thickness", "len", (0.0, 0.3)),
             ("fz", "Floor sunk (−) / raised (+)", "len", (-3.0, 3.0)),
             ("mat_floor", "Floor material (IngeTrazo library)", "choice",
              _ML.keys_for("floor")),
             ("mat_wall", "Walls material (inside this room)", "choice",
              _ML.keys_for("wall")),
             ("mat_ceil", "Ceiling material", "choice",
              _ML.keys_for("ceiling"))],
    "roof": [("kind", "Type", "choice", ("flat", "gable", "hip")),
             ("slope", "Slope", "deg", (5.0, 75.0)),
             ("overhang", "Overhang", "len", (0.0, 3.0)),
             ("t", "Thickness", "len", (0.02, 1.0)),
             ("parapet", "Parapet", "len", (0.0, 3.0))],
}


def _choice_labels() -> dict:
    """Plain names for the keys a choice field stores."""
    from .engine import railings as RL
    out = dict(RL.TYPES)
    from .engine import structure as S_
    out.update({k: lab for k, lab, _c in S_.GLASS_TYPES})
    from . import ceilings as CE_
    out.update({t[0]: t[1] for t in CE_.TYPES})
    out.update({"level": "As the level"})
    out.update({"none": "No railing", "inner": "Inner side (by the well)",
                "both": "Both sides", "outer": "Outer side (by the wall)",
                "monolithic": "Monolithic RCC",
                "solid": "Solid (masonry)", "open": "Open riser",
                "cantilever": "Cantilever (floating treads)",
                "alu_glass": "Glass door, aluminium frame",
                "glass": "Frameless glass", "glass_post":
                "Glass panels between steel posts", "curtain": "Curtain wall",
                "spandrel": "Spandrel panels", "transom": "Transom light",
                "arch": "Arch top", "flat": "Flat",
                "rooms": "In the rooms and out to the slab edge",
                "whole": "Over the whole slab", "off": "No floor finish"})
    return out


CHOICE_LABELS = _choice_labels()
from .engine import structure as _S_PT  # noqa: E402
CHOICE_LABELS.update(_ML.labels())
CHOICE_LABELS.update({k: lab for k, lab in _S_PT.PANEL_TYPES
                      if k != "auto"})
CHOICE_LABELS.update({k: lab for k, lab in _S_PT.HANDLE_TYPES
                      if k != "auto"})
CHOICE_LABELS.update({"slab": "Attached to the slab",
                      "free": "Detached (its own height / base)"})


class _WheelGuard(QObject):
    """The mouse wheel never changes a value in the panel: a wheel turn
    over a spin box, list or slider (clicked into or not) scrolls the
    panel instead. Values change only by typing, the arrows or picking.

    The panel is scrolled directly (its scroll bar's value set) — the wheel
    event is never sent on again, so it can't come back through this
    filter (3.13 re-sent it to the scroll bar, which looped until the
    stack overflowed and IngeTrazo closed)."""

    FIELDS = (QAbstractSpinBox, QComboBox, QAbstractSlider)

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self._busy = False

    def eventFilter(self, obj, ev):  # noqa: N802
        if self._busy:
            return False
        try:
            if ev.type() != QEvent.Wheel or not isinstance(obj, QWidget):
                return False
            from PySide6.QtWidgets import QScrollBar
            # the field the wheel is over: the widget or a parent of it
            # (a spin box's own line edit gets the wheel first)
            w, field = obj, None
            for _ in range(4):
                if w is None:
                    break
                if isinstance(w, QScrollBar):
                    return False             # the panel's own scroll bar
                if isinstance(w, self.FIELDS):
                    field = w
                    break
                w = w.parentWidget()
            if field is None or not self.panel.isAncestorOf(field):
                return False
            self._busy = True
            try:
                sc = getattr(self.panel, "_scroll", None)
                if sc is not None:
                    sb = sc.verticalScrollBar()
                    px = ev.pixelDelta().y()
                    if px:
                        step = -px
                    else:
                        step = -int(ev.angleDelta().y() / 120.0 * 3 *
                                    max(sb.singleStep(), 20))
                    sb.setValue(sb.value() + step)
            finally:
                self._busy = False
            return True                      # the field never sees it
        except Exception:  # noqa: BLE001
            self._busy = False
            return False


def remove_old_guards(app=None):
    """Wheel guards of earlier versions (a hot install) taken off."""
    import gc
    app = app or QApplication.instance()
    n = 0
    for o in gc.get_objects():
        try:
            if type(o).__name__ == "_WheelGuard" and isinstance(o, QObject):
                app.removeEventFilter(o)
                n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def _flat_shape(vs):
    """("h", z) for a horizontal shape, ("v", None) for a vertical one,
    None for a tilted one."""
    zs = [v[2] for v in vs]
    if max(zs) - min(zs) < 0.005:
        return ("h", sum(zs) / len(zs))
    # vertical: every point on one vertical plane
    import numpy as np
    P = np.asarray([v[:2] for v in vs])
    c = P.mean(axis=0)
    _u, sv, _vt = np.linalg.svd(P - c)
    if len(sv) > 1 and sv[1] < 0.005 * max(sv[0], 1e-9) + 1e-4:
        return ("v", None)
    return None


def _is_circle(vs) -> bool:
    """A circle drawn: many points, all as far from their middle."""
    if len(vs) < 10:
        return False
    cx = sum(v[0] for v in vs) / len(vs)
    cy = sum(v[1] for v in vs) / len(vs)
    cz = sum(v[2] for v in vs) / len(vs)
    ds = [math.dist(v, (cx, cy, cz)) for v in vs]
    m = sum(ds) / len(ds)
    return m > 0.02 and max(ds) - min(ds) < 0.06 * m


def _wall_hit(arch, vs, zof, info=None):
    """The straight wall whose face the vertical shape ``vs`` lies on:
    (wall, its centre seg, s0, s1, z bottom, z top) or None."""
    from .engine import walls as W
    best = None
    for w in arch["walls"]:
        if w.get("kind", "line") != "line" or "a" not in w or w.get("rail"):
            continue
        try:
            seg = W.centre(w)
        except Exception:  # noqa: BLE001
            continue
        u = seg.u
        nv = (-u[1], u[0])
        T2 = float(w["t"]) / 2
        cs = [(v[0] - seg.p0[0]) * nv[0] + (v[1] - seg.p0[1]) * nv[1]
              for v in vs]
        if not all(abs(abs(c) - T2) < 0.02 for c in cs) or \
                (max(cs) > 0) != (min(cs) > 0):
            continue
        ss = [(v[0] - seg.p0[0]) * u[0] + (v[1] - seg.p0[1]) * u[1]
              for v in vs]
        if min(ss) < -0.01 or max(ss) > seg.L + 0.01:
            continue
        z0 = zof.get(w["level"], 0.0)
        zs = [v[2] for v in vs]
        if min(zs) < z0 - 0.05 or max(zs) > z0 + 12.0:
            continue
        d = max(abs(abs(c) - T2) for c in cs)
        if best is None or d < best[0]:
            best = (d, (w, seg, max(min(ss), 0.0), min(max(ss), seg.L),
                        min(zs), max(zs)))
    return best[1] if best else None


def _walk_world(groups, parent=None):
    """(group, its world matrix | None) through the groups inside groups."""
    for g in groups or []:
        xf = getattr(g, "xform", None)
        m = parent
        if xf is not None:
            m = (parent * xf) if parent is not None else xf
        yield g, m
        yield from _walk_world(getattr(g, "children", None), m)


def _xf_gap(a, b) -> float:
    """How far apart two placements are (their origins), 0 when equal."""
    def o(m):
        if m is None:
            return (0.0, 0.0, 0.0)
        return (m(0, 3), m(1, 3), m(2, 3))
    pa, pb = o(a), o(b)
    return sum((x - y) ** 2 for x, y in zip(pa, pb))


class Panel(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self.vp = app.viewport
        self.win = app.window
        try:                       # the sheet window: CAD-like zoom
            from . import sheets as _SH
            _SH.ON_PENS[:] = [self._pens_from_bar]
            _SH.hook_composer(self.win)
        except Exception:  # noqa: BLE001
            log_error("panel.hook_composer")
        self._sel_key = None
        self._building = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(6, 6, 6, 6)
        self.lay.setSpacing(6)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self._scroll = scroll
        # the wheel scrolls the panel; it changes a field only when that
        # field has been clicked into (no value changes by accident while
        # scrolling past a spin box or a list)
        remove_old_guards()
        self._wheel_guard = _WheelGuard(self)
        QApplication.instance().installEventFilter(self._wheel_guard)
        self._region = None            # this level's part of the drawing
        self._head()
        self._import_part()
        self._overlap_part()
        self._project_part()
        self._plot_part()
        self._openings_part()
        self._structure_part()
        self._stairs_part()
        self._roof_part()
        self._rooms_part()
        self._materials_part()
        self._selected_part()
        self._components_part()
        self._sheets_part()
        self.lay.addStretch(1)
        # narrow docks: nothing insists on its full text width
        for c in self.findChildren(QComboBox):
            c.setSizeAdjustPolicy(
                QComboBox.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(6)
        for w in self.findChildren(QLineEdit) + \
                self.findChildren(QDoubleSpinBox):
            w.setMinimumWidth(40)
        for b in self.findChildren(QPushButton):
            b.setMinimumWidth(30)
        for c in self.findChildren(QCheckBox):
            c.setMinimumWidth(30)
        for lab in self.findChildren(QLabel):
            lab.setWordWrap(True)
        self._load_prefs()
        self.refresh()
        self.retune_units()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._watch_selection)
        self._timer.start(400)

    # ---- the document ---------------------------------------------------------
    def doc(self):
        return PJ.get(self.vp.scene)

    def level(self):
        """The level picked at the top: (id, record)."""
        doc = self.doc()
        lid = self.level_box.currentData()
        if lid == NEW:                 # not made yet: the top one stands in
            return self._top(doc)["id"], self._top(doc)
        if lid in (ROOF_NEW,):
            return self._top(doc)["id"], self._top(doc)
        if lid == SITE_LV:
            g = next(lv for lv in doc["arch"]["levels"]
                     if lv["kind"] == "ground")
            return g["id"], g
        if lid in (NEW_BELOW, FOUNDATION):     # …the lowest one
            low = doc["arch"]["levels"][0]
            return low["id"], low
        lv = PJ.level_by_id(doc["arch"], lid) if lid else None
        if lv is None:
            lv = next(lv for lv in doc["arch"]["levels"]
                      if lv["kind"] == "ground")
        return lv["id"], lv

    @staticmethod
    def _top(doc):
        elev = PJ.elevations(doc["arch"])
        i = max(range(len(elev)), key=lambda k: elev[k])
        return doc["arch"]["levels"][i]

    def _next_name(self, doc):
        """The name «+ Above» would give the next level."""
        levels = doc["arch"]["levels"]
        new = M.add_floor([dict(x) for x in levels])
        old = {x["id"] for x in levels}
        made = [x for x in new if x["id"] not in old]
        return made[0]["name"] if made else "next level"

    def ann_opts(self):
        return {"dims": self.c_dims.isChecked(),
                "rooms": self.c_roomlbl.isChecked(),
                "texts": self.c_texts.isChecked(),
                "cut": self.s_cut.value()}

    def commit(self, doc, msg=""):
        """Store ``doc``, the model made again — one Ctrl+Z."""
        doc["settings"]["ann_rooms"] = self.c_roomlbl.isChecked()
        doc["settings"]["ann_texts"] = self.c_texts.isChecked()
        doc["settings"]["marks_on"] = self.c_marks.isChecked()
        doc["settings"]["cad_lines"] = self.c_cadlines.isChecked()
        doc["settings"]["park_nums"] = self.c_cars.isChecked()
        doc["settings"]["cars_lib"] = self.c_carlib.isChecked()
        doc["settings"]["car_model"] = self.c_carmodel.currentData() or "suv"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            PJ.commit(self.vp, doc, self.ann_opts())
        except Exception as e:  # noqa: BLE001 — say it
            log_error("panel.commit")
            self.flash(f"Not built — {e}", 9000)
            return False
        finally:
            QApplication.restoreOverrideCursor()
        if msg:
            self.flash(msg + "  ·  Ctrl+Z undoes it", 7000)
        self.refresh()
        return True

    def flash(self, text, ms=5000):
        try:
            self.vp.flash_status(text, ms)
        except Exception:  # noqa: BLE001
            pass
        self.status.setText(text)

    # ---- top: the views --------------------------------------------------------
    def _head(self):
        try:                   # the version installed (never typed in)
            import sys as _sys
            ver = getattr(_sys.modules.get(__package__), "__version__", "")
        except Exception:  # noqa: BLE001
            ver = ""
        t = QLabel("<b style='font-size:14px'>CAD2<span style='color:"
                   f"{BLUE}'>IngeTrazo</span></b> <span style='color:gray'>"
                   f"{ver}</span>")
        self.lay.addWidget(t)
        row = QHBoxLayout()
        self.level_box = QComboBox()
        self.level_box.setToolTip("The level the buttons below work on")
        self.level_box.currentIndexChanged.connect(self._level_changed)
        row.addWidget(QLabel("Level"))
        row.addWidget(self.level_box, 1)
        self.lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_btn("3D", self.show_3d, "The whole model, uncut, "
                           "without the 2D notes"))
        row.addWidget(_btn("Plan", self.show_plan, "This level's plan: cut, "
                           "with its dimensions, texts and door swings"))
        row.addWidget(_btn("Sheets", self.open_sheets, "Open the sheets"))
        self.c_cadlines_top = QCheckBox("CAD lines")
        self.c_cadlines_top.setChecked(True)
        self.c_cadlines_top.setToolTip("Show / hide the CAD plan's linework "
                                       "in the plan views")
        self.c_cadlines_top.toggled.connect(self.set_cad_lines)
        row.addWidget(self.c_cadlines_top)
        self.lay.addLayout(row)
        # the level picked at the top, alone in 3D (and its whole model)
        row = QHBoxLayout()
        row.addWidget(_btn("Isolate level", lambda _=False: self.isolate_level(True),
                           "3D: only the level picked at the top — every "
                           "other floor, the plot and the site hidden"))
        row.addWidget(_btn("Show all", lambda: self.isolate_level(False),
                           "Every floor shown again"))
        self.c_lvgroups = QCheckBox("Floors as groups")
        self.c_lvgroups.setToolTip(
            "Each floor's whole 3D model — walls, doors, windows, columns, "
            "beams, slabs, stairs, finishes, cars… — one group "
            "«Level · Ground Floor» (move, hide, copy, export it as one); "
            "double-click a floor group to reach its elements")
        self.c_lvgroups.toggled.connect(self._level_groups)
        row.addWidget(_btn("Select level", self.select_level,
                           "Select the whole level picked at the top — its "
                           "walls, doors, windows, structure, finishes, "
                           "stairs… (one level = one layer: "
                           "«C2I · <level>»)"))
        row.addWidget(_btn("Stray elements…", self.stray_dialog,
                           "Elements the CAD draws on this floor that are "
                           "not on it (an upper floor's plan repeating the "
                           "porch pillars, the plot walls…): found, and kept "
                           "out of the 3D model — or put back"))
        row.addWidget(_btn("Section box", self.section_box,
                           "3D: the model cut to a box (as Revit's section "
                           "box) — set its six faces, fit it to the level or "
                           "to what you selected, or turn it off"))
        self.lay.addLayout(row)
        # the model's edges in the 3D view: on / off (and the profiles)
        row = QHBoxLayout()
        st_ = getattr(self.vp.scene, "display_style", None)
        self.c_edges = QCheckBox("Model edges")
        self.c_edges.setToolTip("Draw the lines along the edges of the "
                                "model in the 3D view — off: faces only")
        self.c_edges.setChecked(bool(getattr(st_, "edges", True)))
        self.c_edges.toggled.connect(lambda on: self._edge_style("edges",
                                                                 on))
        self.c_prof = QCheckBox("Profiles")
        self.c_prof.setToolTip("The outline of each shape drawn thicker")
        self.c_prof.setChecked(bool(getattr(st_, "profiles", False)))
        self.c_prof.toggled.connect(lambda on: self._edge_style("profiles",
                                                                on))
        self.c_autoop = QCheckBox("Shapes → openings")
        self.c_autoop.setToolTip(
            "A rectangle, circle or closed shape drawn on the face of a "
            "wall becomes an opening there (round for a circle); drawn on a "
            "slab's top, a shaft through it — at once")
        self.c_autoop.setChecked(True)
        self.c_autoop.toggled.connect(self._auto_op_toggle)
        row.addWidget(self.c_edges)
        row.addWidget(self.c_prof)
        row.addWidget(self.c_autoop)
        row.addWidget(_btn("Snaps…", self._snap_dialog,
                           "Object snap for the handles, as AutoCAD's "
                           "OSNAP: endpoint, midpoint, intersection, "
                           "centre, perpendicular, nearest"))
        row.addWidget(self.c_lvgroups)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #8a94a3;")
        self.lay.addWidget(self.status)

    def _cad_furniture(self):
        from . import furnish as FU
        doc = self.doc()
        if not doc.get("imports"):
            self.flash("Import a CAD plan first")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            got = FU.furnish(doc)
        except Exception as e:  # noqa: BLE001
            log_error("panel._cad_furniture")
            self.flash(f"Furniture not read — {e}", 8000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        from collections import Counter
        tot = Counter()
        for v_ in got.values():
            tot.update(v_)
        if not tot:
            self.flash("No furniture or fixture blocks recognised in the "
                       "CAD plan", 8000)
            return
        doc["settings"]["cad_furniture"] = True
        self.commit(doc, "Furniture from the CAD: " + ", ".join(
            f"{n} {k}" for k, n in tot.most_common()))

    def _cad_furniture_off(self):
        doc = self.doc()
        n = sum(1 for f in doc.get("furniture") or [] if f.get("cad"))
        if not n:
            if doc["settings"].get("cad_furniture"):
                doc["settings"]["cad_furniture"] = False
                PJ.store_only(self.vp, doc)
            self.flash("Furniture from the CAD: off")
            return
        doc["furniture"] = [f for f in doc["furniture"] if not f.get("cad")]
        doc["settings"]["cad_furniture"] = False
        self.commit(doc, f"{n} pieces of CAD furniture removed")

    def _auto_op_toggle(self, on):
        if self._building:
            return
        doc = self.doc()
        if bool(doc["settings"].get("auto_openings", True)) == bool(on):
            return
        doc["settings"]["auto_openings"] = bool(on)
        PJ.store_only(self.vp, doc)
        self.flash("Drawn shapes become openings" if on else
                   "Drawn shapes stay as drawn")

    def _snap_dialog(self):
        from . import osnap as OS
        if OS.dialog(self):
            st = OS.settings()
            on = [n for k, n, _d in OS.MODES if st.get(k)]
            self.flash(("Object snap: " + ", ".join(on)) if st["on"] and on
                       else "Object snap off")

    def _edge_style(self, name, on):
        """The 3D view's style: its edges / profiles on or off (the host's
        Style menu follows)."""
        st = getattr(self.vp.scene, "display_style", None)
        if st is None or not hasattr(st, name):
            self.flash("This IngeTrazo has no edge setting in its style")
            return
        setter = getattr(self.win, "_set_style_field", None)
        if setter is not None:
            setter(name, bool(on))
        else:
            setattr(st, name, bool(on))
            self.vp.update()
        act = getattr(self.win, "_act_style_edges" if name == "edges"
                      else "_act_style_profiles", None)
        if act is not None and act.isChecked() != bool(on):
            act.blockSignals(True)
            act.setChecked(bool(on))
            act.blockSignals(False)
        self.flash(("Model edges" if name == "edges" else "Profiles")
                   + (" on" if on else " off"))

    def _terrace_rkind(self, *_a):
        doc = self.doc()
        k = self.t_rkind.currentData() or "wall3"
        if doc["settings"].get("terrace_rail_kind", "wall3") == k:
            return
        doc["settings"]["terrace_rail_kind"] = k
        PJ.store_only(self.vp, doc)
        self.flash(("Terrace edges: a 3\" plastered wall" if k == "wall3"
                    else "Terrace edges: railing on a 3\" upstand")
                   + " — «Terrace railings from the CAD» (or a roof terrace) "
                   "builds them", 8000)

    def _scene_named(self, name):
        return next((v for v in self.vp.scene.saved_views if v.name == name),
                    None)

    def _apply_view(self, name):
        v = self._scene_named(name)
        if v is None:
            self.flash("No model yet — import a level first", 5000)
            return
        v.apply(self.vp.scene, self.vp.camera)
        self.vp.scene.version += 1
        try:                  # a plan: the CAD's own line weights, not the
            self._plan_lines(name.startswith("C2I · Plan"))  # model's
        except Exception:  # noqa: BLE001
            log_error("panel._plan_lines")
        if name.endswith("· 3D"):
            try:
                self.win._on_standard_view("iso")
            except Exception:  # noqa: BLE001
                pass
            self.vp.camera.perspective = True
            try:
                self.win._on_zoom_extents()
            except Exception:  # noqa: BLE001
                pass
        self.vp.update()

    def _plan_lines(self, plan):
        """In a plan view with the CAD's linework on, the plan reads with
        the CAD's own line weights: the model's thin edge lines are left
        out under them (and come back in 3D, as «Model edges» says)."""
        st_ = getattr(self.vp.scene, "display_style", None)
        if st_ is None or not hasattr(st_, "edges"):
            return
        doc = self.doc()
        want_cad = plan and doc["settings"].get("cad_lines", True)
        if want_cad:
            if not getattr(self, "_plan_edges_off", False):
                self._edges_before = bool(st_.edges)
            self._plan_edges_off = True
            if st_.edges:
                st_.edges = False
        elif getattr(self, "_plan_edges_off", False):
            self._plan_edges_off = False
            st_.edges = bool(getattr(self, "_edges_before", True))
        self.vp.update()

    def show_3d(self):
        self._apply_view("C2I · 3D")

    def isolate_level(self, on=True):
        """3D: only the level picked at the top — its walls, doors,
        windows, columns, beams, stairs, finishes… standing on its floor
        slab (the slab under it), the slab cast over it taken off so the
        floor can be seen into; every other floor, the plot and the site
        hidden. «Show all» puts everything back."""
        sc = self.vp.scene
        was = getattr(sc, "_c2i_iso_hidden", None) or []
        for g in was:                       # whatever an earlier isolate hid
            try:
                g.hidden = False
            except Exception:  # noqa: BLE001
                pass
        sc._c2i_iso_hidden = []
        # (3.14.0 hid layers: those back on too)
        from .host import LAYER_PREFIX, is_ann_layer
        lay_was = getattr(sc, "_c2i_iso", None)
        if lay_was:
            for L in sc.layers:
                if L.name in lay_was:
                    L.visible = lay_was[L.name]
            sc._c2i_iso = None
        if not on:
            for L in sc.layers:
                if L.name.startswith(LAYER_PREFIX) and \
                        not is_ann_layer(L.name) and not L.visible:
                    L.visible = True
            sc.version += 1
            self.vp.update()
            self.flash("Every floor shown")
            return
        lid, lv = self.level()
        if not lid or not lv:
            self.flash("Pick a level at the top first")
            return
        self.show_3d()
        doc = self.doc()
        arch = doc["arch"]
        el = PJ.elevations(arch)
        order = [arch["levels"][i]["id"] for i in
                 sorted(range(len(arch["levels"])), key=lambda i: el[i])]
        k = order.index(lid) if lid in order else -1
        below = order[k - 1] if k > 0 else None
        slabs = {e["id"]: e for e in arch["structure"] if e["type"] == "slab"}
        on_top = PJ.slab_on_top(doc)

        def keep(t):
            lv_ = t.get("level")
            if t.get("type") == "levelgroup":
                return lv_ in (lid, below)
            if t.get("type") == "slab":
                s_ = slabs.get(t.get("id")) or {}
                if on_top:              # slabs cast over each floor
                    if lv_ == lid:
                        return not s_.get("top")      # its ceiling: off
                    return lv_ == below and bool(s_.get("top"))  # its floor
                return lv_ == lid
            return lv_ == lid
        hid = []
        for g in sc.groups:                 # the top-level groups
            t = PJ.tag_of(g)
            if not t or t.get("type") == "symbols":
                continue
            if t.get("type") == "levelgroup":
                # floors as groups: a whole floor group shown or hidden
                if t.get("level") != lid and not g.hidden:
                    g.hidden = True
                    hid.append(g)
                continue
            if not keep(t) and not g.hidden:
                g.hidden = True
                hid.append(g)
        sc._c2i_iso_hidden = hid
        sc._c2i_before = None           # a plan view left: not «restored»
        sc.version += 1
        self.vp.update()

        def again(_h=hid, _sc=sc):
            # the 3D view's scene (and the plan's restore) may put hidden
            # objects back a moment later: hidden again
            if getattr(_sc, "_c2i_iso_hidden", None) is not _h:
                return
            n_ = 0
            for g_ in _h:
                if not g_.hidden:
                    g_.hidden = True
                    n_ += 1
            if n_:
                _sc.version += 1
                self.vp.update()
        for ms in (150, 600, 1500):
            QTimer.singleShot(ms, again)
        self.flash(f"«{lv['name']}» isolated (on its floor slab, the slab "
                   "over it off) — «Show all» brings everything back")

    def _level_groups(self, on):
        if self._building:
            return
        doc = self.doc()
        if bool(doc["settings"].get("level_groups")) == bool(on):
            return
        doc["settings"]["level_groups"] = bool(on)
        self.commit(doc, "Each floor one group in 3D" if on else
                    "Floors' elements loose again (no floor groups)")

    def select_level(self):
        """Every CAD2IngeTrazo group of the level picked at the top."""
        lid, lv = self.level()
        if not lid:
            self.flash("Pick a level at the top first")
            return
        sc = self.vp.scene
        hits = [g for g in sc.groups if (PJ.tag_of(g) or {}).get("level")
                == lid and (PJ.tag_of(g) or {}).get("type") != "symbols"]
        sc.selection.clear()
        for g in hits:
            sc.selection.add(g)
        self.vp.update()
        self.flash(f"«{lv['name']}»: {len(hits)} elements selected")

    def show_plan(self):
        if self.level_box.currentData() == SITE_LV:
            self.show_site()
            return
        if self.level_box.currentData() == FOUNDATION:
            self._apply_view("C2I · Plan · Foundation")
            return
        _lid, lv = self.level()
        self._apply_view(f"C2I · Plan · {lv['name']}")

    def show_site(self):
        self._apply_view("C2I · Site plan")

    # ---- 1. project & levels -------------------------------------------------
    def _project_part(self):
        box, body = _fold("3  Project and levels", "project")
        f = _form(body)
        self.p_name, self.p_client = QLineEdit(), QLineEdit()
        self.p_author, self.p_loc = QLineEdit(), QLineEdit()
        f.addRow("Project", self.p_name)
        f.addRow("Client", self.p_client)
        f.addRow("Drawn by", self.p_author)
        f.addRow("Location", self.p_loc)
        row = QHBoxLayout()
        self.p_north = QDoubleSpinBox()
        self.p_north.setRange(0.0, 359.99)
        self.p_north.setDecimals(1)
        self.p_north.setWrapping(True)
        self.p_north.setSuffix(" °")
        self.p_north.setToolTip("Project north: degrees CLOCKWISE from the "
                                "plan's up (+Y). Read from the CAD's north "
                                "arrow on import; the compass, the sheets' "
                                "north arrows and the elevations' names "
                                "(North / East…) follow it")
        self.p_north.editingFinished.connect(self._north_typed)
        row.addWidget(self.p_north, 1)
        row.addWidget(_btn("From CAD", self._north_cad,
                           "The north read from the CAD plan's north arrow"))
        row.addWidget(_btn("↻ 90°", lambda: self._north_set(
            (self.p_north.value() + 90.0) % 360.0, "manual"),
            "Turn the north a quarter clockwise"))
        f.addRow("North", row)
        self.p_compass = QCheckBox("Show the compass in the view")
        self.p_compass.setChecked(True)
        self.p_compass.toggled.connect(self._compass_toggled)
        f.addRow(self.p_compass)
        self.p_north_src = QLabel("")
        self.p_north_src.setStyleSheet("color: #8a94a3;")
        self.p_north_src.setWordWrap(True)
        f.addRow(self.p_north_src)
        self.levels = QTableWidget(0, 3)
        self.levels.setHorizontalHeaderLabels(["Level", "Height", "Floor at"])
        self.levels.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.levels.verticalHeader().setVisible(False)
        self.levels.setMinimumHeight(120)
        self.levels.setSelectionBehavior(QAbstractItemView.SelectRows)
        f.addRow(self.levels)
        row = QHBoxLayout()
        row.addWidget(_btn("+ Above", lambda: self._add_level(True)))
        row.addWidget(_btn("+ Basement", lambda: self._add_level(False)))
        row.addWidget(_btn("Remove", self._remove_level))
        f.addRow(row)
        f.addRow(_btn("Apply project and levels", self._apply_levels,
                      "Store the names and heights (the model follows)",
                      primary=True))
        self.lay.addWidget(box)

    def _north_set(self, deg, src):
        doc = self.doc()
        if abs(PJ.north_of(doc) - deg % 360.0) < 1e-3 and \
                doc["settings"].get("north_src") == src:
            return
        PJ.set_north(doc, deg, src)
        PJ.store_only(self.vp, doc)
        self.flash(f"North {deg % 360.0:.1f}° clockwise from the plan's up "
                   "— «Make sheets» puts it on the plans  ·  Ctrl+Z undoes "
                   "it", 7000)
        self.refresh()

    def _north_typed(self):
        if not self._building:
            self._north_set(self.p_north.value(), "manual")

    def _north_cad(self):
        doc = self.doc()
        v = doc["settings"].get("north_cad")
        if v is None:
            try:
                v = PJ.north_from_imports(doc)
            except Exception:  # noqa: BLE001
                log_error("panel._north_cad")
        if v is None:
            self.flash("No north arrow found in the CAD plan — type the "
                       "angle instead")
            return
        self._north_set(float(v), "cad")

    def _compass_toggled(self, on):
        if self._building:
            return
        doc = self.doc()
        doc["settings"]["north_show"] = bool(on)
        PJ.store_only(self.vp, doc)

    def _fill_north(self, doc):
        st = doc["settings"]
        if not self.p_north.hasFocus():
            self.p_north.blockSignals(True)
            self.p_north.setValue(PJ.north_of(doc))
            self.p_north.blockSignals(False)
        self.p_compass.blockSignals(True)
        self.p_compass.setChecked(bool(st.get("north_show", True)))
        self.p_compass.blockSignals(False)
        cad = st.get("north_cad")
        if st.get("north_src", "cad") == "cad" and cad is not None:
            self.p_north_src.setText(f"From the CAD's north arrow ({cad:.1f}°)")
        elif cad is not None:
            self.p_north_src.setText(f"Typed — the CAD's arrow says {cad:.1f}°")
        else:
            self.p_north_src.setText("No north arrow found in the CAD — "
                                     "type it")

    def _fill_levels(self, doc):
        arch = doc["arch"]
        elev = PJ.elevations(arch)
        self.levels.blockSignals(True)
        self.levels.setRowCount(0)
        for i, lv in reversed(list(enumerate(arch["levels"]))):
            r = self.levels.rowCount()
            self.levels.insertRow(r)
            it = QTableWidgetItem(lv["name"])
            it.setData(Qt.UserRole, lv["id"])
            self.levels.setItem(r, 0, it)
            self.levels.setItem(r, 1, QTableWidgetItem(f"{lv['height']:.2f}"))
            z = QTableWidgetItem(f"{elev[i]:+.2f}"
                                 + ("  ✓ plan" if lv["id"] in doc["imports"]
                                    else ""))
            z.setFlags(z.flags() & ~Qt.ItemIsEditable)
            self.levels.setItem(r, 2, z)
        self.levels.blockSignals(False)

    def _levels_from_table(self, arch):
        rows = []
        for r in range(self.levels.rowCount() - 1, -1, -1):
            lid = self.levels.item(r, 0).data(Qt.UserRole)
            old = PJ.level_by_id(arch, lid) or {"kind": "floor"}
            try:
                h = float(self.levels.item(r, 1).text())
            except ValueError:
                h = old.get("height", 3.0)
            rows.append({"id": lid, "name": self.levels.item(r, 0).text()
                         .strip(), "kind": old["kind"], "height": h})
        return rows

    def _add_level(self, above):
        doc = self.doc()
        arch = doc["arch"]
        arch["levels"] = self._levels_from_table(arch) or arch["levels"]
        arch["levels"] = (M.add_floor if above else M.add_basement)(
            arch["levels"])
        self.commit(doc, "Level added")

    def _remove_level(self):
        doc = self.doc()
        arch = doc["arch"]
        r = self.levels.currentRow()
        if r < 0:
            return
        lid = self.levels.item(r, 0).data(Qt.UserRole)
        lv = PJ.level_by_id(arch, lid)
        if lv is None or lv["kind"] == "ground":
            self.flash("The ground floor stays (rename it instead)")
            return
        if QMessageBox.question(self, "Remove level", f"Remove «{lv['name']}"
                                "» and everything on it?") != \
                QMessageBox.Yes:
            return
        ids = {w["id"] for w in arch["walls"] if w["level"] == lid}
        arch["walls"] = [w for w in arch["walls"] if w["level"] != lid]
        arch["openings"] = [o for o in arch["openings"] if o["wall"] not in ids]
        arch["structure"] = [e for e in arch["structure"] if e["level"] != lid]
        arch["rooms"] = [x for x in arch["rooms"] if x["level"] != lid]
        doc["texts"] = [t for t in doc["texts"] if t["level"] != lid]
        doc["imports"].pop(lid, None)
        arch["levels"] = [x for x in arch["levels"] if x["id"] != lid]
        self.commit(doc, f"«{lv['name']}» removed")

    def _apply_levels(self):
        doc = self.doc()
        arch = doc["arch"]
        arch["levels"] = self._levels_from_table(arch) or arch["levels"]
        proj = dict(arch.get("project") or M.new_project())
        proj.update(name=self.p_name.text().strip(),
                    client=self.p_client.text().strip(),
                    author=self.p_author.text().strip(),
                    location=self.p_loc.text().strip())
        arch["project"] = proj
        self.commit(doc, "Project and levels stored")

    def _level_changed(self, _i):
        if not self._building:
            self._fill_overlap(self.doc())
            self._fill_rooms(self.doc())
            self._fill_import(self.doc())

    # ---- 2. import a plan --------------------------------------------------------
    def _import_part(self):
        box, body = _fold("1  Import CAD plan — level by level", "import")
        f = _form(body)
        row = QHBoxLayout()
        self.i_file = QLineEdit()
        self.i_file.setPlaceholderText("plan.dxf / plan.dwg")
        row.addWidget(self.i_file, 1)
        row.addWidget(_btn("…", self._browse, "Pick the plan"))
        f.addRow("File", row)
        row = QHBoxLayout()
        row.addWidget(_btn("Select floor on drawing…", self._pick,
                           "Drag a box round this level's plan in the CAD "
                           "file and click its reference point (grid A/1 "
                           "or a corner) — one file can hold every floor",
                           primary=True))
        f.addRow(row)
        self.i_portion = QLabel("")
        self.i_portion.setWordWrap(True)
        self.i_portion.setStyleSheet("color: #8a94a3;")
        f.addRow(self.i_portion)
        row = QHBoxLayout()
        self.i_gffl = _spin(0.0, 1.2192, 0.6096, 0.0762)   # 0 … 4'-0"
        self.i_gffl.setSpecialValueText("As the CAD notes it")
        self.i_gffl.setToolTip(
            "The ground floor's finished level above the natural ground / "
            "road (N.G.L. = 0), 1'-0\" to 4'-0\" as the project needs: the "
            "ground floor, the floors above and the basements follow, and "
            "the F.F.L. marks read from it. At the bottom of the range: the "
            "CAD's own level note («LEV. +4'-0\"») decides.")
        row.addWidget(self.i_gffl, 1)
        row.addWidget(_btn("Apply", self._apply_gffl))
        f.addRow("Ground floor level (F.F.L.)", row)
        self.i_floor_h = _spin(1.5, 20.0, 3.048)        # 10'-0"
        self.i_floor_h.setToolTip("The level's storey height, floor to "
                                  "floor (the CAD's level notes, when read, "
                                  "set it instead)")
        f.addRow("Floor height (floor to floor)", self.i_floor_h)
        f.addRow(_btn("Update floors and levels (all levels)",
                      self._update_levels,
                      "Every floor made again at the ground floor level and "
                      "floor height above (the CAD's level notes, when "
                      "«Floor levels from the CAD's level notes» is on, "
                      "still set the floors they note) — the walls, slabs, "
                      "stairs, ramps and everything on them follow"))
        row = QHBoxLayout()
        row.addWidget(_btn("Analyse", self._analyse,
                           "Read the file and list its layers — nothing "
                           "changes"))
        self.i_go = _btn("Import to level", self._import, "Walls, doors, "
                           "windows, columns, beams, slab with holes, room "
                           "names and texts — replaces this level's earlier "
                           "import", primary=True)
        row.addWidget(self.i_go)
        f.addRow(row)
        self.i_changed = QLabel("")
        self.i_changed.setWordWrap(True)
        self.i_changed.setStyleSheet("color: #c0392b; font-weight: bold;")
        f.addRow(self.i_changed)
        f.addRow(_btn("Update from CAD (all levels)", self._update_cad,
                      "Read every level's plan again with the settings it "
                      "was imported with — after the CAD file changed"))
        # the import settings fold under the import (as the layers):
        # «Import to …» stays right under «Select floor on drawing…»
        sbox, sbody = _fold("Import settings (units, base point, insert, "
                            "levels…)", "importset", False)
        sf = _form(sbody)
        self.i_unit = QComboBox()
        for _k, label, _v in cadread.UNITS:
            self.i_unit.addItem(label)
        sf.addRow("Drawing units", self.i_unit)
        from .host import UNIT_CHOICES
        self.i_munits = QComboBox()
        for k, label in UNIT_CHOICES:
            self.i_munits.addItem(label, k)
        self.i_munits.setToolTip("The units every length is shown and typed "
                                 "in — the panel, dimensions, room areas, "
                                 "sheets. Auto: as the CAD plan is drawn "
                                 "(inches / feet → feet-inches, mm, cm, m)")
        self.i_munits.currentIndexChanged.connect(self._units_choice)
        sf.addRow("Model units", self.i_munits)
        self.i_base = QComboBox()
        for _k, label in cadread.BASE_MODES:
            self.i_base.addItem(label)
        self.i_base.currentIndexChanged.connect(
            lambda i: self.i_bxy.setEnabled(cadread.BASE_MODES[i][0] ==
                                            "custom"))
        sf.addRow("Base point", self.i_base)
        self.i_bxy = QWidget()
        h = QHBoxLayout(self.i_bxy)
        h.setContentsMargins(0, 0, 0, 0)
        self.i_bx = _spin(-1e9, 1e9, 0.0, 1.0, 3, "")
        self.i_by = _spin(-1e9, 1e9, 0.0, 1.0, 3, "")
        h.addWidget(self.i_bx)
        h.addWidget(self.i_by)
        sf.addRow("  X, Y (drawing units)", self.i_bxy)
        row = QHBoxLayout()
        self.i_ix = _spin(-1e6, 1e6, 0.0, 0.5, 3)
        self.i_iy = _spin(-1e6, 1e6, 0.0, 0.5, 3)
        row.addWidget(self.i_ix)
        row.addWidget(self.i_iy)
        sf.addRow("Insert at X, Y", row)
        self.i_rot = _spin(-360, 360, 0.0, 90, 2, " °")
        sf.addRow("Rotation", self.i_rot)
        row = QHBoxLayout()
        self.i_tmin = _spin(0.02, 2.0, 0.08, 0.01, 3)
        self.i_tmax = _spin(0.02, 3.0, 0.40, 0.01, 3)
        row.addWidget(self.i_tmin)
        row.addWidget(self.i_tmax)
        sf.addRow("Wall thickness min/max", row)
        lbox, lbody = _fold("Layers (wildcards, comma separated)",
                            "layers", False)
        lf = _form(lbody)
        self.i_layers = {}
        for k, label in (("walls", "Walls"), ("doors", "Doors"),
                         ("windows", "Windows"), ("columns", "Columns"),
                         ("beams", "Beams"), ("slab", "Slab outline"),
                         ("holes", "Slab holes"), ("text", "Texts"),
                         ("plot", "Plot boundary"),
                         ("footings", "Footings"), ("stairs", "Stairs"),
                         ("grid", "Column grid"), ("lift", "Lift core"),
                         ("parking", "Parking bays"), ("cars", "Cars"),
                         ("bikes", "Motorbike parking"),
                         ("ramps", "Car ramps"),
                         ("rails", "Railings (slab edges)")):
            e = QLineEdit()
            lf.addRow(label, e)
            self.i_layers[k] = e
        self.i_auto = QCheckBox("Detect layers automatically")
        self.i_auto.setChecked(True)
        self.i_auto.setToolTip("From layer and block names (any language, "
                               "AIA codes) and wall line pairs: walls, "
                               "doors, windows, columns, beams, slab, "
                               "plot and footings found from the drawing; a "
                               "role nothing shows keeps the patterns below")
        sf.addRow(self.i_auto)
        self.i_levels = QCheckBox("Floor levels from the CAD's level notes "
                                  "(LEV. +4'-0\", FFL …)")
        self.i_levels.setChecked(True)
        self.i_levels.setToolTip("The level a floor's CAD plan notes most "
                                 "is its floor level, in the plans and in "
                                 "3D; the storey heights follow")
        sf.addRow(self.i_levels)
        f.addRow(sbox)
        f.addRow(lbox)
        self.i_report = QLabel("")
        self.i_report.setWordWrap(True)
        self.i_report.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow(self.i_report)
        self.lay.addWidget(box)

    def _browse(self):
        start = os.path.dirname(self.i_file.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "CAD plan", start,
                                              "CAD plans (*.dxf *.dwg)")
        if path:
            self.i_file.setText(path)

    def _how(self):
        how = {"unit": cadread.UNITS[self.i_unit.currentIndex()][2],
               "unit_key": cadread.UNITS[self.i_unit.currentIndex()][0],
               "base": cadread.BASE_MODES[self.i_base.currentIndex()][0],
               "bx": self.i_bx.value(), "by": self.i_by.value(),
               "ix": self.i_ix.value(), "iy": self.i_iy.value(),
               "rot": self.i_rot.value(), "tmin": self.i_tmin.value(),
               "tmax": self.i_tmax.value(),
               "region": list(self._region) if self._region else None,
               "auto": self.i_auto.isChecked()}
        for k, e in self.i_layers.items():
            how[k] = e.text()
        self._save_prefs(how)
        return how

    def _fill_import(self, doc):
        lid = self.level_box.currentData()
        how = doc["imports"].get(lid) if lid not in (NEW, NEW_BELOW) else None
        if not how:
            self._region = None        # a level not read yet: pick its part
            self._show_portion()
            return
        self._region = how.get("region")
        self.i_file.setText(how.get("file", ""))
        keys = [k for k, _l, _v in cadread.UNITS]
        if how.get("unit_key") in keys:
            self.i_unit.setCurrentIndex(keys.index(how["unit_key"]))
        modes = [k for k, _l in cadread.BASE_MODES]
        if how.get("base") in modes:
            self.i_base.setCurrentIndex(modes.index(how["base"]))
        for w, k in ((self.i_bx, "bx"), (self.i_by, "by"), (self.i_ix, "ix"),
                     (self.i_iy, "iy"), (self.i_rot, "rot"),
                     (self.i_tmin, "tmin"), (self.i_tmax, "tmax")):
            if k in how:
                w.setValue(float(how[k]))
        for k, e in self.i_layers.items():
            if k in how:
                e.setText(how[k])
        self._show_portion()

    def _target_name(self):
        if self.level_box.currentData() == NEW:
            return self._next_name(self.doc()) + " (new)"
        if self.level_box.currentData() == NEW_BELOW:
            return "Basement (new)"
        if self.level_box.currentData() == FOUNDATION:
            return "Foundation"
        if self.level_box.currentData() == SITE_LV:
            return "Site"
        if self.level_box.currentData() == ROOF_NEW:
            return "Roof level"
        return self.level()[1]["name"]

    def _show_portion(self):
        name = self._target_name()
        if self._region:
            x0, y0, x1, y1 = self._region
            self.i_portion.setText(
                f"«{name}»: part of the drawing {x1 - x0:.0f} × {y1 - y0:.0f}"
                f" units, reference point {self.i_bx.value():.1f}, "
                f"{self.i_by.value():.1f}")
        else:
            self.i_portion.setText(f"«{name}»: the whole drawing — or "
                                   "«Select floor on drawing…» when the file "
                                   "holds several floors")
        try:
            self.i_go.setText(f"Import to «{name}»")
        except AttributeError:
            pass

    def _taken(self, doc, path):
        """The parts of this file other levels took: [(name, region, base)]"""
        out = []
        here = self.level_box.currentData()
        named = [(lv["id"], lv["name"]) for lv in doc["arch"]["levels"]] + \
            [(FOUNDATION, "Foundation")]
        for lid, lname in named:
            how = doc["imports"].get(lid)
            if not how or lid == here or not how.get("region"):
                continue
            if os.path.normcase(os.path.abspath(how.get("file", ""))) != \
                    os.path.normcase(os.path.abspath(path)):
                continue
            out.append((lname, how["region"],
                        (how.get("bx"), how.get("by"))
                        if how.get("base") == "custom" else None))
        return out

    def _pick(self):
        path = self.i_file.text().strip()
        if not path:
            self._browse()
            path = self.i_file.text().strip()
            if not path:
                return
        how = self._how()
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            d = cadread.read(path, how["unit"])
        except Exception as e:  # noqa: BLE001
            self.flash(f"Not read — {e}", 8000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        base = (self.i_bx.value(), self.i_by.value()) if self._region and \
            cadread.BASE_MODES[self.i_base.currentIndex()][0] == "custom" \
            else None
        dlg = PortionDialog(self, d, self._target_name(),
                            self._taken(self.doc(), path), self._region, base)
        if not dlg.exec():
            return
        if dlg.whole:
            self._region = None
        else:
            self._region = [round(v, 4) for v in dlg.region]
            modes = [k for k, _l in cadread.BASE_MODES]
            self.i_base.setCurrentIndex(modes.index("custom"))
            self.i_bx.setValue(dlg.base[0])
            self.i_by.setValue(dlg.base[1])
        self._show_portion()

    def _analyse(self):
        path = self.i_file.text().strip()
        how = self._how()
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            d = cadread.read(path, how["unit"])
        except Exception as e:  # noqa: BLE001
            self.i_report.setText(f"⚠ {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        base = cadread.base_point(d, how["base"], (how["bx"], how["by"]))
        far = cadread.far_from_base(d, base)
        lines = [f"Units: 1 unit = {d['unit']:g} m ({d['unit_note']})",
                 f"Extents: {d['extents'][0]:.1f}, {d['extents'][1]:.1f} → "
                 f"{d['extents'][2]:.1f}, {d['extents'][3]:.1f}",
                 f"{len(d['texts'])} texts, {len(d['loops'])} closed "
                 f"outlines, {len(d['circles'])} circles"]
        if far > 1000:
            lines.append(f"⚠ The drawing lies {far / 1000:.1f} km from its "
                         "base point — pick a base point near the building")
        d = cadread.crop(d, self._region)
        P, found = PJ.layer_patterns(d, how, PJ.DEFAULTS)
        if found:
            self._show_roles(found)
        counts = {}
        for s_ in d["segs"]:
            counts[s_[4]] = counts.get(s_[4], 0) + 1
        blocks = {}
        from . import detect
        for ins in d.get("inserts", ()):
            k = detect.block_kind(ins["name"], ins["layer"])
            if k:
                blocks[k] = blocks.get(k, 0) + 1
        if blocks:
            lines.append("Blocks: " + ", ".join(f"{n} {k}s"
                                                 for k, n in blocks.items()))
        lines.append("Layers" + (" (detected)" if found else "") + ":")
        for name in sorted(counts):
            roles = [k for k, p in P.items() if PJ._match(name, p)]
            lines.append(f"  {name} — {counts[name]}"
                         + (f"  [{', '.join(roles)}]" if roles else ""))
        self.i_report.setText("\n".join(lines))

    def _apply_units(self, k=None):
        """The model's units: as chosen, or (Auto) as the CAD plan is
        drawn; every length field follows."""
        from .host import set_units, units_for_cad
        mode = self.i_munits.currentData() or "auto"
        if mode == "auto":
            if k is None:
                return
            u, p = units_for_cad(k)
        else:
            u, p = mode, None
        set_units(self.vp.scene, u, p)
        self.retune_units()

    def retune_units(self):
        for s_ in self.findChildren(LenSpin):
            s_.retune()
        self.vp.update()

    def _units_choice(self, _i=None):
        _settings().setValue("units_mode", self.i_munits.currentData())
        if self.i_munits.currentData() != "auto":
            self._apply_units()
            self.commit(self.doc(), "Units changed")

    def _update_cad(self):
        doc = self.doc()
        if not any(k for k in doc["imports"] if not k.startswith("__plot")):
            self.flash("Nothing imported yet")
            return
        if QMessageBox.question(
                self, "Update from CAD", "Read every level again from its "
                "CAD plan? Walls, doors, windows, columns and slabs made "
                "from the plans are made again (Ctrl+Z undoes it).") != \
                QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            out = PJ.update_from_cad(doc)
        except Exception as e:  # noqa: BLE001
            log_error("panel._update_cad")
            self.flash(f"Not updated — {e}", 9000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.commit(doc, "Updated from CAD: " + ", ".join(
            f"{n} ({r.get('walls', r.get('pads', 0))})" for n, r in out))

    def _show_roles(self, found):
        """The layers found, into the pattern fields (to see and to edit)."""
        from . import detect
        for k, e in self.i_layers.items():
            if found.get(k):
                e.setText(detect.as_patterns(found[k]))

    def _import(self):
        path = self.i_file.text().strip()
        if not path:
            self.flash("Pick a DXF / DWG first")
            return
        doc = self.doc()
        here = self.level_box.currentData()
        if here == FOUNDATION:
            self._import_foundation(doc, path)
            return
        if here == SITE_LV:
            self._plot_from_cad()
            return
        if here == ROOF_NEW:
            self._roof_level()
            return
        new = here == NEW
        if here == NEW_BELOW:          # «＋ basement»: made with its plan
            arch = doc["arch"]
            old = {x["id"] for x in arch["levels"]}
            arch["levels"] = M.add_basement(arch["levels"])
            lv = next(x for x in arch["levels"] if x["id"] not in old)
            lid = lv["id"]
        elif new:                      # «＋ next level»: made with its plan
            arch = doc["arch"]
            old = {x["id"] for x in arch["levels"]}
            arch["levels"] = M.add_floor(arch["levels"])
            lv = next(x for x in arch["levels"] if x["id"] not in old)
            lid = lv["id"]
        else:
            lid, lv = self.level()
        lv_ = PJ.level_by_id(doc["arch"], lid)
        if lv_ is not None:              # its storey height, as typed
            lv_["height"] = round(float(self.i_floor_h.value()), 4)
        doc["settings"].update(self._settings_from_ui())
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rep = PJ.import_level(doc, lid, path, self._how())
        except Exception as e:  # noqa: BLE001
            log_error("panel._import")
            self.i_report.setText(f"⚠ Not read — {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not rep["walls"]:
            self.i_report.setText("⚠ No walls found — check the wall layers "
                                  "and the thicknesses (Analyse lists the "
                                  "layers)")
            return
        if self.i_auto.isChecked() and rep.get("roles"):
            self._show_roles(rep["roles"])
        self._apply_units(rep.get("unit_k"))
        # the stairs as the plans draw them, on every floor (with this one)
        try:
            from . import stairs as ST
            self._stair_opts(doc)
            sr = ST.auto(doc, flip=self.st_flip.isChecked())
            rep["stairs_built"] = sr.get("stairs", 0)
        except Exception:  # noqa: BLE001
            log_error("panel._import stairs")
        if not self.commit(doc):
            return
        if rep["columns"] == 0 and rep["walls"] and QMessageBox.question(
                self, "Columns", f"The plan of «{lv['name']}» shows no "
                "columns. Add columns at the wall corners?") == \
                QMessageBox.Yes:
            d2 = self.doc()
            n = PJ.add_corner_columns(d2, lid, self.s_col.value())
            self.commit(d2, f"{n} columns added at the corners")
        # the next floor up offered at once: same file, its own part
        top = self._top(self.doc())["id"] == lid
        self.level_box.setCurrentIndex(self.level_box.findData(
            NEW if top else lid))
        txt = (f"«{lv['name']}»: {rep['walls']} walls, {rep['openings']} "
               f"openings, {rep['columns']} columns, {rep['beams']} beams, "
               f"{'a slab' if rep['slab'] else 'no slab'}"
               f"{' with ' + str(rep['holes']) + ' holes' if rep['holes'] else ''}"
               f", {rep['rooms']} rooms, {rep['texts']} texts")
        if rep.get("blocks"):
            txt += f"\n{rep['blocks']} door / window blocks placed in walls"
        if rep.get("stairs_built"):
            txt += (f"\n{rep['stairs_built']} stair(s) built from the plans' "
                    "tread lines")
        if rep.get("bays") or rep.get("cars"):
            txt += (f"\nCar parking: {rep.get('stalls', 0)} cars (bays "
                    "numbered P1… in plan, painted on the floor)")
        if rep.get("ramps"):
            txt += (f"\n{rep['ramps']} car ramp(s) from the RAMP lines, the "
                    "climb from their notes; wells cut in the slabs "
                    "(select one to change its climb or flip it)")
        if rep.get("marks"):
            txt += f"\n{rep['marks']} level mark(s) from the CAD's LEV. notes"
        if rep.get("levels_set"):
            from .host import len_txt
            txt += "\nFloor levels from the CAD: " + ", ".join(
                f"{n} {'+' if e >= 0 else '-'}{len_txt(abs(e))}"
                for n, e in rep["levels_set"])
        if rep.get("shafts"):
            txt += (f"\n{rep['shafts']} shaft / slab opening(s) cut through "
                    "the floor slab (X in plan)")
        if rep.get("cores"):
            txt += (f"\n{rep['cores']} lift core(s) in RCC, as the columns, "
                    "with their landing doors; the shafts cut the slab")
        if rep.get("plot"):
            txt += "\nPlot boundary taken from the drawing (part 3)"
        if rep["skipped"]:
            txt += "\nLeft out: " + "; ".join(rep["skipped"][:6])
        if rep["far_km"] > 1:
            txt += (f"\n⚠ {rep['far_km']:.1f} km from its base point — "
                    "use a base point near the building")
        if self.level_box.currentData() == NEW:
            txt += (f"\n→ Next: «{self._target_name()}» — «Select floor on "
                    "drawing…», take its part of the file (same reference "
                    "point), Import. A single-storey building: nothing more "
                    "to do.")
        self.i_report.setText(txt)
        self.flash(txt.split("\n")[0] + "  ·  Ctrl+Z undoes it", 8000)

    # ---- 2. floors over each other ------------------------------------------------
    def _overlap_part(self):
        box, body = _fold("2  Overlap floors", "overlap")
        f = _form(body)
        self.g_mode = QComboBox()
        for k, label in ghost.MODES:
            self.g_mode.addItem(label, k)
        self.g_mode.setToolTip("In a plan view, the other floors drawn greyed "
                               "out under this one (below: grey, above: "
                               "dashed) — the model and sheets unchanged")
        self.g_mode.currentIndexChanged.connect(self._ghost_mode)
        f.addRow("Show greyed out", self.g_mode)
        f.addRow(QLabel("<i>Lay one floor over another:</i>"))
        self.o_move = QComboBox()
        self.o_move.setToolTip("The floor that moves — by default the one "
                               "picked at the top, else the last one "
                               "imported")
        self.o_move.currentIndexChanged.connect(
            lambda _i: self._fill_overlap(self.doc(), keep_move=True))
        f.addRow("Level to move", self.o_move)
        self.o_ref = QComboBox()
        f.addRow("Over level", self.o_ref)
        self.o_how = QComboBox()
        for k, label in (("best", "Best fit (wall corners meet)"),
                         ("ll", "Lower-left corners together"),
                         ("centre", "Centres together")):
            self.o_how.addItem(label, k)
        f.addRow("How", self.o_how)
        f.addRow(_btn("Overlap", self._overlap, "Move the whole level so it "
                      "sits over the other one — walls, doors, windows, "
                      "structure, rooms and texts; a later import of its "
                      "plan lands in the same place", primary=True))
        row = QHBoxLayout()
        self.o_dx = _spin(-1e4, 1e4, 0.0, 0.05, 3)
        self.o_dy = _spin(-1e4, 1e4, 0.0, 0.05, 3)
        row.addWidget(self.o_dx)
        row.addWidget(self.o_dy)
        f.addRow("…or move by X, Y", row)
        f.addRow(_btn("Move the level", self._nudge))
        # rotate: a level of its own choosing, about the middle of its walls
        f.addRow(QLabel("<i>Rotate a floor:</i>"))
        self.o_rlev = QComboBox()
        self.o_rlev.setToolTip("The floor to rotate")
        f.addRow("Level to rotate", self.o_rlev)
        row = QHBoxLayout()
        self.o_rot = _spin(-360.0, 360.0, 90.0, 1.0, 2, " °")
        self.o_rot.setToolTip("Anticlockwise; a minus angle turns clockwise")
        row.addWidget(self.o_rot)
        row.addWidget(_btn("Rotate the level", lambda _=False: self._rotate(
            self.o_rot.value()), "Turn the whole level about the middle of "
            "its walls — walls, doors, windows, structure, stairs, parking, "
            "ramps, rooms and texts; a later import of its plan lands the "
            "same way"))
        f.addRow("Rotate by", row)
        row = QHBoxLayout()
        for label, deg in (("↺ 90°", 90.0), ("↻ 90°", -90.0),
                           ("180°", 180.0)):
            row.addWidget(_btn(label, lambda _=False, d=deg: self._rotate(d)))
        f.addRow("Quick turn", row)
        self.lay.addWidget(box)

    def _ghost_mode(self, _i=None):
        ghost.MODE = self.g_mode.currentData() or "off"
        _settings().setValue("ghost", ghost.MODE)
        self.vp.update()

    def _fill_overlap(self, doc, keep_move=False):
        """«Level to move» and «Over level»: the floors with walls — the
        one to move is the level picked at the top when it is a real one,
        else the last floor imported; it goes over the floor below it."""
        levels = doc["arch"]["levels"]
        walls = doc["arch"]["walls"]
        ids = [lv["id"] for lv in levels]
        real = [lv for lv in levels
                if any(w["level"] == lv["id"] for w in walls)]
        top = self.level_box.currentData()
        mv = self.o_move.currentData()
        if not keep_move:
            if top in ids and any(lv["id"] == top for lv in real):
                mv = top
            elif mv not in [lv["id"] for lv in real]:
                mv = None
            if mv is None and real:
                mv = real[-1]["id"]
            self.o_move.blockSignals(True)
            self.o_move.clear()
            for lv in reversed(real):
                self.o_move.addItem(lv["name"], lv["id"])
            if doc["arch"].get("plot"):
                self.o_move.addItem("Plot + shoring (site)", PJ.PLOT_ITEM)
            self.o_move.setCurrentIndex(max(self.o_move.findData(mv), 0))
            self.o_move.blockSignals(False)
        mv = self.o_move.currentData()
        cur = self.o_ref.currentData()
        self.o_ref.blockSignals(True)
        self.o_ref.clear()
        for lv in reversed(real):
            if lv["id"] != mv:
                self.o_ref.addItem(lv["name"], lv["id"])
        rc = self.o_rlev.currentData()
        self.o_rlev.blockSignals(True)
        self.o_rlev.clear()
        for lv in reversed(real):
            self.o_rlev.addItem(lv["name"], lv["id"])
        if doc["arch"].get("plot"):
            self.o_rlev.addItem("Plot + shoring (site)", PJ.PLOT_ITEM)
        kr = self.o_rlev.findData(rc)
        self.o_rlev.setCurrentIndex(kr if kr >= 0 else
                                    max(self.o_rlev.findData(mv), 0))
        self.o_rlev.blockSignals(False)
        k = self.o_ref.findData(cur) if cur != mv else -1
        if k < 0 and mv in ids:               # the floor below, by default
            below = [lv["id"] for lv in real
                     if ids.index(lv["id"]) < ids.index(mv)]
            k = self.o_ref.findData(below[-1]) if below else 0
        self.o_ref.setCurrentIndex(max(k, 0))
        self.o_ref.blockSignals(False)

    def _overlap(self):
        lid = self.o_move.currentData()
        ref = self.o_ref.currentData()
        if not lid or not ref or ref == lid:
            self.flash("Overlap needs two floors with walls — import the "
                       "second floor first")
            return
        doc = self.doc()
        if lid == PJ.PLOT_ITEM:            # the plot (and its shoring)
            r = PJ.plot_overlap_offset(doc, ref, self.o_how.currentData())
            if r is None:
                self.flash("The plot and that level's walls are needed")
                return
            PJ.move_plot(doc, *r)
            other = PJ.level_by_id(doc["arch"], ref)["name"]
            self.commit(doc, f"Plot and shoring moved {r[0]:+.3f}, "
                             f"{r[1]:+.3f} m over «{other}»")
            return
        r = PJ.overlap_offset(doc, lid, ref, self.o_how.currentData())
        if r is None:
            self.flash("Both levels need walls")
            return
        dx, dy, good = r
        name = PJ.level_by_id(doc["arch"], lid)["name"]
        other = PJ.level_by_id(doc["arch"], ref)["name"]
        if abs(dx) < 1e-4 and abs(dy) < 1e-4:
            self.flash(f"«{name}» already sits over «{other}»")
            return
        PJ.move_level(doc, lid, dx, dy)
        extra = f" — {good * 100:.0f}% of its corners meet" \
            if good is not None else ""
        self.commit(doc, f"«{name}» moved {dx:+.3f}, {dy:+.3f} m over "
                         f"«{other}»{extra}")

    def _nudge(self):
        lid = self.o_move.currentData()
        if not lid:
            self.flash("Pick the level to move")
            return
        dx, dy = self.o_dx.value(), self.o_dy.value()
        if not dx and not dy:
            return
        doc = self.doc()
        if lid == PJ.PLOT_ITEM:
            PJ.move_plot(doc, dx, dy)
            self.commit(doc, f"Plot and shoring moved {dx:+.3f}, {dy:+.3f} m")
            return
        PJ.move_level(doc, lid, dx, dy)
        self.commit(doc, f"Level moved {dx:+.3f}, {dy:+.3f} m")

    def _rotate(self, deg):
        lid = self.o_rlev.currentData()
        if not lid:
            self.flash("Pick the level to rotate")
            return
        if not deg or abs(deg) % 360.0 < 1e-6:
            return
        doc = self.doc()
        if lid == PJ.PLOT_ITEM:
            if PJ.rotate_plot(doc, deg):
                self.commit(doc, f"Plot and shoring rotated {deg:+g}°")
            return
        if not PJ.rotate_level(doc, lid, deg):
            self.flash("That level has no walls to rotate")
            return
        name = PJ.level_by_id(doc["arch"], lid)["name"]
        way = "anticlockwise" if deg > 0 else "clockwise"
        self.commit(doc, f"«{name}» rotated {abs(deg):g}° {way}")

    # ---- 3. the plot -------------------------------------------------------------
    def _plot_part(self):
        box, body = _fold("4  Plot (site)", "plot", False)
        f = _form(body)
        self.pl_info = QLabel("<i>No plot yet.</i>")
        self.pl_info.setWordWrap(True)
        f.addRow(self.pl_info)
        f.addRow(_btn("Plot from the drawing…", self._plot_from_cad,
                      "Click the plot's corners on the CAD file, or click "
                      "inside its boundary outline — placed like the ground "
                      "floor's plan", primary=True))
        row = QHBoxLayout()
        self.pl_w = _spin(1, 5000, 20.0, 0.5)
        self.pl_d = _spin(1, 5000, 30.0, 0.5)
        row.addWidget(self.pl_w)
        row.addWidget(self.pl_d)
        f.addRow("…or a rectangle W × D", row)
        row = QHBoxLayout()
        self.pl_x = _spin(-1e5, 1e5, -5.0, 0.5)
        self.pl_y = _spin(-1e5, 1e5, -5.0, 0.5)
        row.addWidget(self.pl_x)
        row.addWidget(self.pl_y)
        f.addRow("  lower-left corner X, Y", row)
        self.pl_rot = _spin(-360, 360, 0.0, 5, 1, " °")
        f.addRow("  rotation", self.pl_rot)
        f.addRow(_btn("Make the rectangular plot", self._plot_rect))
        f.addRow(QLabel("<i>Setbacks (ArchXQ):</i>"))
        self.pl_front = QComboBox()
        self.pl_front.setToolTip("The side on the road: the front setback "
                                 "is measured from it; the side opposite is "
                                 "the back")
        f.addRow("Front side", self.pl_front)
        self.sb_front = _spin(0, 100, 3.0)
        self.sb_back = _spin(0, 100, 1.5)
        self.sb_sides = _spin(0, 100, 1.0)
        f.addRow("Front", self.sb_front)
        f.addRow("Back", self.sb_back)
        f.addRow("Sides", self.sb_sides)
        self.pl_plinth = _spin(0, 3, 0.15)
        self.pl_plinth.setToolTip("How far the ground floor stands above the "
                                  "plot's ground")
        f.addRow("Plinth (floor above ground)", self.pl_plinth)
        row = QHBoxLayout()
        row.addWidget(_btn("Apply setbacks", self._plot_setbacks,
                           primary=True))
        row.addWidget(_btn("Site plan", self.show_site))
        row.addWidget(_btn("Remove plot", self._plot_remove))
        f.addRow(row)
        # excavations and fills — ArchXQ's terrain cuts
        from . import excavation as EX_
        f.addRow(QLabel("<i>Excavation / fill (ArchXQ):</i>"))
        self.ex_kind = QComboBox()
        self.ex_kind.addItem("Excavation (cut)", "cut")
        self.ex_kind.addItem("Fill (raise the ground)", "fill")
        f.addRow("Make", self.ex_kind)
        self.ex_shape = QComboBox()
        for k, label in EX_.SHAPES:
            self.ex_shape.addItem(label, k)
        f.addRow("Outline", self.ex_shape)
        self.ex_margin = _spin(0.0, 20.0, 1.0, 0.1)
        self.ex_margin.setToolTip("Working space round the footprint (or the "
                                  "inset from the plot's edge)")
        f.addRow("Working space / margin", self.ex_margin)
        self.ex_bottom = QComboBox()
        for k, label in EX_.BOTTOMS:
            self.ex_bottom.addItem(label, k)
        self.ex_bottom.addItem("Height above the ground (a fill)", "height")
        f.addRow("Bottom", self.ex_bottom)
        row = QHBoxLayout()
        self.ex_val = _spin(-100.0, 100.0, 3.0, 0.1)
        self.ex_val.setToolTip("Depth below / height above the ground, the "
                               "elevation, or (under the lowest level) the "
                               "margin under its floor")
        self.ex_ang = _spin(5.0, 90.0, 90.0, 5.0, 0, " °")
        self.ex_ang.setToolTip("The sides' slope: 90° = vertical (shored), "
                               "45° = 1:1 batter")
        row.addWidget(self.ex_val)
        row.addWidget(self.ex_ang)
        f.addRow("Value / side angle", row)
        self.ex_bottom.currentIndexChanged.connect(self._ex_bottom_changed)
        row = QHBoxLayout()
        row.addWidget(_btn("Add", self._dig_add, "Open the excavation (or "
                           "build the fill) in the plot", primary=True))
        self.ex_list = QComboBox()
        row.addWidget(self.ex_list, 1)
        row.addWidget(_btn("Remove", self._dig_remove))
        f.addRow(row)
        self.ex_info = QLabel("")
        self.ex_info.setWordWrap(True)
        self.ex_info.setStyleSheet("color: #8a94a3;")
        f.addRow(self.ex_info)
        f.addRow(QLabel("<i>Boundary wall and gates (ground level):</i>"))
        self.bw_on = QCheckBox("Boundary wall on the plot's edge")
        f.addRow(self.bw_on)
        row = QHBoxLayout()
        self.bw_h = _spin(0.3, 6, 2.10)
        self.bw_t = _spin(0.05, 1, 0.23)
        row.addWidget(self.bw_h)
        row.addWidget(self.bw_t)
        f.addRow("Height / thickness", row)
        self.bw_pil = QCheckBox("Pillars at corners and gates")
        self.bw_pil.setChecked(True)
        f.addRow(self.bw_pil)
        self.gt_side = QComboBox()
        f.addRow("Gate on side", self.gt_side)
        row = QHBoxLayout()
        self.gt_pos = _spin(0, 1000, 3.0, 0.1)
        self.gt_w = _spin(0.6, 15, 3.6, 0.1)
        row.addWidget(self.gt_pos)
        row.addWidget(self.gt_w)
        f.addRow("Centre at / width", row)
        self.gt_kind = QComboBox()
        for k, label in SITE_.GATE_KINDS:
            self.gt_kind.addItem(label, k)
        f.addRow("Gate type", self.gt_kind)
        row = QHBoxLayout()
        row.addWidget(_btn("Add gate", self._gate_add))
        self.gt_list = QComboBox()
        row.addWidget(self.gt_list, 1)
        row.addWidget(_btn("Remove", self._gate_remove))
        f.addRow(row)
        f.addRow(_btn("Apply boundary wall", self._boundary, primary=True))
        self.lay.addWidget(box)

    def _ex_bottom_changed(self, _i=0):
        mode = self.ex_bottom.currentData()
        self.ex_val.setValue({"level": 0.30, "depth": 3.0, "elev": -3.0,
                              "height": 1.0}.get(mode, 3.0))

    def _selected_outline(self):
        """The plan outline of the slab / room / ramp selected, or None."""
        sel = self._selected()
        if not sel:
            return None
        doc = self.doc()
        rec = PJ.find_record(doc, *sel)
        if rec is None:
            return None
        if sel[0] == "ramp":
            from . import parking as PK
            g = PK.footprint(rec)
            g = max(getattr(g, "geoms", [g]), key=lambda q: q.area)
            return [tuple(p) for p in list(g.exterior.coords)[:-1]]
        for k in ("corners", "pts", "outline", "poly"):
            v = rec.get(k)
            if isinstance(v, list) and len(v) >= 3 and \
                    isinstance(v[0], (list, tuple)):
                return [tuple(p[:2]) for p in v]
        return None

    def _dig_add(self):
        from . import excavation as EX
        doc = self.doc()
        kind = self.ex_kind.currentData()
        shape = self.ex_shape.currentData()
        rect = (self.pl_x.value(), self.pl_y.value(), self.pl_w.value(),
                self.pl_d.value(), self.pl_rot.value())
        pts, why = EX.outline_of(doc, shape, self.ex_margin.value(), rect,
                                 self._selected_outline()
                                 if shape == "selected" else None)
        if why:
            self.flash(f"No excavation — {why}", 8000)
            return
        mode = self.ex_bottom.currentData()
        v = self.ex_val.value()
        if kind == "fill" and mode not in ("height", "elev"):
            mode = "height"
        if mode == "level":
            lid, _z = EX.lowest_level(doc["arch"])
            bottom = {"mode": "level", "level": lid, "offset": -abs(v)}
        elif mode == "depth":
            bottom = {"mode": "depth", "d": max(abs(v), 0.05)}
        elif mode == "height":
            bottom = {"mode": "height", "h": max(abs(v), 0.05)}
        else:
            bottom = {"mode": "elev", "z": v}
        d = EX.new(doc, pts, kind, bottom, self.ex_ang.value())
        ground = PJ.plot_top(doc)
        if kind != "fill" and EX.bottom_z(d, doc, ground) >= ground - 0.01:
            doc["arch"]["digs"].remove(d)
            self.flash("No excavation — its bottom is not under the ground "
                       "(the lowest level stands above it: use a depth)", 9000)
            return
        self.commit(doc, EX.describe(d, doc, ground))

    def _dig_remove(self):
        doc = self.doc()
        did = self.ex_list.currentData()
        digs = doc["arch"].get("digs") or []
        if not did or not any(d["id"] == did for d in digs):
            return
        doc["arch"]["digs"] = [d for d in digs if d["id"] != did]
        self.commit(doc, "Excavation removed")

    def _fill_digs(self, doc):
        from . import excavation as EX
        self.ex_list.clear()
        digs = doc["arch"].get("digs") or []
        if not digs:
            self.ex_info.setText("")
            return
        ground = PJ.plot_top(doc)
        cut = fill = 0.0
        for d in digs:
            try:
                v = EX.volume(d, doc, ground)
                txt = EX.describe(d, doc, ground)
            except Exception:  # noqa: BLE001
                v, txt = 0.0, d.get("name", "?")
            if d.get("kind") == "fill":
                fill += v
            else:
                cut += v
            self.ex_list.addItem(txt, d["id"])
        self.ex_info.setText(f"Cut {cut:,.0f} m³ · fill {fill:,.0f} m³ · "
                             f"to cart away {max(cut - fill, 0):,.0f} m³")

    def _site_from_ui(self, doc):
        st = doc["site"]
        st.update(wall=self.bw_on.isChecked(), h=self.bw_h.value(),
                  t=self.bw_t.value(), pillars=self.bw_pil.isChecked())
        return st

    def _boundary(self):
        doc = self.doc()
        if not doc["arch"].get("plot"):
            self.flash("Make the plot first (part 4)")
            return
        self._site_from_ui(doc)
        self.commit(doc, "Boundary wall " + ("made" if self.bw_on.isChecked()
                                             else "removed"))

    def _gate_add(self):
        doc = self.doc()
        if not doc["arch"].get("plot"):
            self.flash("Make the plot first (part 4)")
            return
        st = self._site_from_ui(doc)
        st["wall"] = True
        self.bw_on.setChecked(True)
        st["gates"].append({"side": self.gt_side.currentData() or 0,
                            "pos": self.gt_pos.value(),
                            "w": self.gt_w.value(),
                            "kind": self.gt_kind.currentData()})
        self.commit(doc, "Gate added")

    def _gate_remove(self):
        doc = self.doc()
        i = self.gt_list.currentData()
        if i is None or i >= len(doc["site"]["gates"]):
            return
        doc["site"]["gates"].pop(i)
        self.commit(doc, "Gate removed")

    def _fill_site(self, doc):
        st = doc["site"]
        self.bw_on.setChecked(st["wall"])
        self.bw_h.setValue(st["h"])
        self.bw_t.setValue(st["t"])
        self.bw_pil.setChecked(st["pillars"])
        plot = doc["arch"].get("plot")
        self.gt_side.clear()
        if plot:
            pts = plot["corners"]
            n = len(pts)
            for i in range(n):
                L = math.dist(pts[i], pts[(i + 1) % n])
                self.gt_side.addItem(f"Side {i + 1}  ({L:.2f} m)", i)
            fr = plot.get("sb_front") or []
            if True in fr:
                self.gt_side.setCurrentIndex(fr.index(True))
        self.gt_list.clear()
        kinds = dict(SITE_.GATE_KINDS)
        for i, g in enumerate(st["gates"]):
            self.gt_list.addItem(f"Gate {i + 1}: side {g['side'] + 1}, "
                                 f"{g['w']:.2f} m {kinds[g['kind']].lower()}",
                                 i)

    def _fill_plot(self, doc):
        from .engine import plotgeo
        self._fill_site(doc)
        try:
            self._fill_digs(doc)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_digs")
        plot = doc["arch"].get("plot")
        self.pl_front.blockSignals(True)
        self.pl_front.clear()
        if not plot:
            self.pl_info.setText("<i>No plot yet — from the drawing, a "
                                 "rectangle, or a boundary layer found on "
                                 "import.</i>")
            self.pl_front.blockSignals(False)
            return
        pts = plot["corners"]
        n = len(pts)
        for i in range(n):
            L = math.dist(pts[i], pts[(i + 1) % n])
            self.pl_front.addItem(f"Side {i + 1}  ({L:.2f} m)", i)
        fr = plot.get("sb_front") or []
        if True in fr:
            self.pl_front.setCurrentIndex(fr.index(True))
        self.pl_front.blockSignals(False)
        dist = plot.get("sb_dist") or {}
        self.sb_front.setValue(dist.get("front", 3.0))
        self.sb_back.setValue(dist.get("back", 1.5))
        self.sb_sides.setValue(dist.get("sides", 1.0))
        self.pl_plinth.setValue(float(doc["settings"].get("plinth", 0.15)))
        _r, _d, area = plotgeo.setbacks_of(plot)
        txt = (f"<b>Plot {area_txt(plotgeo.area(pts))}</b> · {n} sides · "
               f"perimeter {plotgeo.perimeter(pts):,.2f} m")
        if area:
            txt += f"<br>Buildable (inside setbacks) {area_txt(plotgeo.area(area))}"
            ws = [w for w in doc["arch"]["walls"]]
            if ws:
                from .engine import walls as W
                lid = next(lv["id"] for lv in doc["arch"]["levels"]
                           if lv["kind"] == "ground")
                mine = [w for w in ws if w["level"] == lid]
                pieces = [pc for pcs in W.plan(mine).values() for pc in pcs]
                fp = PJ._outer_loop(pieces) if pieces else None
                if fp is not None:
                    ok = plotgeo.within(fp, area, margin=0.0)
                    txt += ("<br><span style='color:#2e9e5b'>✓ The building "
                            "keeps the setbacks</span>" if ok else
                            "<br><span style='color:#c0392b'>⚠ The building "
                            "crosses a setback line</span>")
        self.pl_info.setText(txt)

    def _plot_store(self, corners, msg):
        doc = self.doc()
        doc["settings"]["plinth"] = self.pl_plinth.value()
        why = PJ.set_plot(doc, corners, dist={"front": self.sb_front.value(),
                                              "back": self.sb_back.value(),
                                              "sides": self.sb_sides.value()})
        if why:
            self.flash(f"No plot — {why}", 8000)
            return
        self.commit(doc, msg)

    def _plot_rect(self):
        x, y = self.pl_x.value(), self.pl_y.value()
        w, d = self.pl_w.value(), self.pl_d.value()
        a = math.radians(self.pl_rot.value())
        c, s_ = math.cos(a), math.sin(a)
        pts = [[x + c * px - s_ * py, y + s_ * px + c * py]
               for px, py in ((0, 0), (w, 0), (w, d), (0, d))]
        self._plot_store(pts, f"Plot {w:.2f} × {d:.2f} m made")

    def _plot_from_cad(self):
        path = self.i_file.text().strip()
        if not path:
            self._browse()
            path = self.i_file.text().strip()
            if not path:
                return
        doc = self.doc()
        # placed the way the ground floor's plan was (else as set above)
        g = next(lv["id"] for lv in doc["arch"]["levels"]
                 if lv["kind"] == "ground")
        how = dict(self._how())
        how.update(doc["imports"].get(g) or {})
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            d = cadread.read(path, how.get("unit"))
        except Exception as e:  # noqa: BLE001
            self.flash(f"Not read — {e}", 8000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        dlg = PlotDialog(self, d, self._taken(doc, path))
        if not dlg.exec():
            return
        base = cadread.base_point(d, how.get("base", "origin"),
                                  (how.get("bx", 0.0), how.get("by", 0.0)))
        pts = cadread.to_model(d, base, (how.get("ix", 0.0),
                                         how.get("iy", 0.0)),
                               how.get("rot", 0.0), dlg.poly)
        self._plot_store(pts, f"Plot of {len(pts)} corners taken from the "
                              "drawing")

    def _plot_setbacks(self):
        doc = self.doc()
        plot = doc["arch"].get("plot")
        if not plot:
            self.flash("Make the plot first")
            return
        n = len(plot["corners"])
        i = self.pl_front.currentData()
        front = [k == i for k in range(n)]
        doc["settings"]["plinth"] = self.pl_plinth.value()
        PJ.set_plot(doc, plot["corners"], front=front,
                    dist={"front": self.sb_front.value(),
                          "back": self.sb_back.value(),
                          "sides": self.sb_sides.value()})
        self.commit(doc, "Setbacks applied")

    def _plot_remove(self):
        doc = self.doc()
        doc["arch"]["plot"] = None
        doc["imports"].pop(PJ.PLOT_KEY, None)
        self.commit(doc, "Plot removed")

    # ---- 3. openings ------------------------------------------------------------
    def _type_settings(self, st):
        st["win_style"] = self.o_wstyle.currentData() or "sliding"
        st["door_style"] = self.o_dstyle.currentData() or "hinged"
        st["door2_style"] = self.o_d2style.currentData() or "double"
        st["door_head"] = self.o_dhead.currentData() or "flat"
        st["win_head"] = self.o_whead.currentData() or "flat"
        st["door_frame"] = self.o_dframe.currentData() or "auto"
        st["win_frame"] = self.o_wframe.currentData() or "auto"

    def set_cad_lines(self, on):
        """The CAD's linework in the plan views on / off — the toolbar's
        button, the panel's checkbox and the setting kept as one."""
        on = bool(on)
        for w in (getattr(self, "c_cadlines", None),
                  getattr(self, "c_cadlines_top", None),
                  getattr(self, "_tb_cad", None)):
            if w is not None and w.isChecked() != on:
                w.blockSignals(True)
                w.setChecked(on)
                w.blockSignals(False)
        self._store_flag("cad_lines", on)
        try:
            from .host import PREFIX_PLAN_CUT as _PPC
            sp_ = self.vp.scene.active_section()
            self._plan_lines(str(getattr(sp_, "name", "") or "")
                             .startswith(_PPC))
        except Exception:  # noqa: BLE001
            pass

    def _corner_windows(self):
        lid, lv = self.level()
        if not lid:
            self.flash("Pick a level at the top first")
            return
        doc = self.doc()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = PJ.redetect_corner_windows(doc, [lid])
        except Exception as e:  # noqa: BLE001
            log_error("panel._corner_windows")
            self.flash(f"Not read — {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if lid not in r:
            self.flash("This level has no CAD plan imported")
            return
        if not r[lid]:          # the old ones (if any) go all the same
            self.commit(doc, f"No corner window on «{lv['name']}»")
            self.flash("No corner window found on this level's plan")
            return
        self.commit(doc, f"{r[lid]} corner window(s) on «{lv['name']}» "
                         "— aluminium, one piece round the corner")

    def section_box(self):
        """The section box dialog: six faces (X, Y, Z from / to), «Whole
        model», «This level», «Selection», «Apply», «Off» — stays open
        while you work."""
        from PySide6.QtWidgets import QDialog, QGridLayout
        from . import secbox as SB
        dlg = getattr(self, "_sb_dlg", None)
        if dlg is not None:
            try:
                dlg.deleteLater()
            except Exception:  # noqa: BLE001
                pass
            self._sb_dlg = None
        dlg = QDialog(self)
        dlg.setWindowTitle("CAD2IngeTrazo · Section box")
        dlg.setModal(False)
        g = QGridLayout(dlg)
        spins = []
        for r_, ax in enumerate("XYZ"):
            g.addWidget(QLabel(f"{ax} from"), r_, 0)
            a = _spin(-1000.0, 1000.0, 0.0)
            g.addWidget(a, r_, 1)
            g.addWidget(QLabel("to"), r_, 2)
            b = _spin(-1000.0, 1000.0, 0.0)
            g.addWidget(b, r_, 3)
            spins.append((a, b))

        def put(bx):
            if not bx:
                return
            for k_, (a, b) in enumerate(spins):
                a.setValue(float(bx[k_]))
                b.setValue(float(bx[k_ + 3]))

        def model_box():
            gs = [x for x in PJ.all_groups(self.vp.scene) if PJ.tag_of(x)]
            # the true model: the box off, its bounds from the records
            return SB.model_bounds(gs)

        def whole():
            st = self.doc()["settings"]
            if st.get("section_box"):
                d_ = self.doc()
                d_["settings"]["section_box"] = None
                self.commit(d_, "Section box off")
            put(model_box())

        def level_box():
            lid, lv = self.level()
            if not lid:
                self.flash("Pick a level at the top first")
                return
            d_ = self.doc()
            arch = d_["arch"]
            el = PJ.elevations(arch)
            ids = [x["id"] for x in arch["levels"]]
            i = ids.index(lid)
            bx = model_box() or [0, 0, 0, 1, 1, 1]
            z0 = el[i] - 0.05
            z1 = el[i] + float(arch["levels"][i].get("height", 3.0)) + 0.05
            put([bx[0] - 0.5, bx[1] - 0.5, z0, bx[3] + 0.5, bx[4] + 0.5, z1])

        def sel_box():
            sel = [x for x in self.vp.scene.selection
                   if hasattr(x, "mesh")]
            bb = SB.model_bounds(sel) if sel else None
            if not bb:
                self.flash("Select something in 3D first")
                return
            put([bb[0] - 0.3, bb[1] - 0.3, bb[2] - 0.3, bb[3] + 0.3,
                 bb[4] + 0.3, bb[5] + 0.3])

        def apply():
            bx = [spins[k_][0].value() for k_ in range(3)] + \
                [spins[k_][1].value() for k_ in range(3)]
            for k_ in range(3):
                if bx[k_ + 3] - bx[k_] < 0.05:
                    self.flash("Each face «to» must be past its «from»")
                    return
            d_ = self.doc()
            d_["settings"]["section_box"] = [round(v, 4) for v in bx]
            self.commit(d_, "Section box")

        def off():
            d_ = self.doc()
            d_["settings"]["section_box"] = None
            self.commit(d_, "Section box off")
        r_ = 3
        for c_, (lab_, fn_) in enumerate((("Whole model", whole),
                                          ("This level", level_box),
                                          ("Selection", sel_box))):
            g.addWidget(_btn(lab_, fn_), r_, c_)
        g.addWidget(_btn("Apply", apply, primary=True), r_ + 1, 0, 1, 2)
        g.addWidget(_btn("Off", off), r_ + 1, 2, 1, 2)
        hint = QLabel("In 3D, drag the orange grips on the box's six faces "
                      "to move them (the dot, along its arrow) — or type "
                      "the faces here and Apply.")
        hint.setWordWrap(True)
        g.addWidget(hint, r_ + 2, 0, 1, 4)
        cur_ = self.doc()["settings"].get("section_box")
        if not cur_:                     # on at once round the whole model,
            mb = model_box()             # its grips ready to drag
            if mb:
                cur_ = [mb[0] - 0.3, mb[1] - 0.3, mb[2] - 0.1,
                        mb[3] + 0.3, mb[4] + 0.3, mb[5] + 0.1]
                d_ = self.doc()
                d_["settings"]["section_box"] = [round(v, 4) for v in cur_]
                self.commit(d_, "Section box on")
        put(cur_)
        dlg._put = put
        self._sb_dlg = dlg
        dlg.show()

    def _terrace_mat(self):
        doc = self.doc()
        k_ = self.t_mat.currentData() or ""
        doc["settings"]["terrace_mat"] = "" if k_ == "none" else k_
        self.commit(doc, "Terrace floors: " + self.t_mat.currentText())

    def _terrace_rails(self):
        lid, lv = self.level()
        if not lid:
            self.flash("Pick a level at the top first")
            return
        doc = self.doc()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = PJ.terrace_railings(doc, lid)
        except Exception as e:  # noqa: BLE001
            log_error("panel._terrace_rails")
            self.flash(f"Not made — {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        n = r["lines"] + r["edges"]
        if not n:
            self.flash("No terrace on this level (no slab under it out past "
                       "its walls)")
            return
        self.commit(doc, f"{n} terrace railing(s) on «{lv['name']}», "
                         f"each on a 3\" upstand")

    def _roof_terrace(self, slab_id=None):
        sel = self._sel_key
        if slab_id is None:
            if not sel or sel[0] != "slab":
                self.flash("Select a slab in the model first")
                return
            slab_id = sel[1]
        doc = self.doc()
        r = PJ.roof_terrace(doc, slab_id)
        if r.get("error"):
            self.flash(r["error"])
            return
        lv = next((x for x in doc["arch"]["levels"] if x["id"] == r["level"]),
                  {})
        self.commit(doc, f"Roof terrace on «{lv.get('name', '')}»: "
                         f"{r['railings']} railing(s), tiles, outlets")

    def _off3d_selected(self):
        sels = [x for x in self._selected_all() if x[0] != "symbols"] \
            or ([self._sel_key] if self._sel_key else [])
        if not sels:
            return
        doc = self.doc()
        off = set(doc.get("off3d") or [])
        for k_, i_ in sels:
            off.add(f"{'stair' if k_ == 'stairrail' else k_}|{i_}")
        doc["off3d"] = sorted(off)
        self.commit(doc, f"{len(sels)} element(s) kept out of 3D — "
                         "«Stray elements…» puts them back")

    def stray_dialog(self):
        """The level's stray elements (found) and those kept out of 3D:
        keep the found ones out, or put the kept ones back."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem
        lid, lv = self.level()
        if not lid:
            self.flash("Pick a level at the top first")
            return
        doc = self.doc()
        found = [f for f in PJ.stray_elements(doc, lid)
                 if f"{f[0]}|{f[1]}" not in set(doc.get("off3d") or [])]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Stray elements — {lv['name']}")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"<b>Found on «{lv['name']}»</b> — drawn on this floor but with "
            "no floor under them (tick the ones to keep out of 3D):"))
        lst = QListWidget()
        for k_, i_, nm, why in found:
            it = QListWidgetItem(f"{nm}  ({k_}) — {why}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole, f"{k_}|{i_}")
            lst.addItem(it)
        if not found:
            lst.addItem("Nothing found — or select elements in 3D, "
                        "right-click ▸ «Not on this floor — keep out of 3D»")
        lay.addWidget(lst)
        kept = list(doc.get("off3d") or [])
        lay.addWidget(QLabel(f"<b>Kept out of 3D:</b> {len(kept)} element(s) "
                             "(all levels)"))
        lst2 = QListWidget()
        for key in kept:
            k_, i_ = key.split("|", 1)
            rec = PJ.find_record(doc, k_, i_)
            it = QListWidgetItem(f"{(rec or {}).get('name', i_)}  ({k_})")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            it.setData(Qt.UserRole, key)
            lst2.addItem(it)
        lay.addWidget(lst2)
        row = QHBoxLayout()

        def keep_out():
            d_ = self.doc()
            off = set(d_.get("off3d") or [])
            n = 0
            for r in range(lst.count()):
                it = lst.item(r)
                key = it.data(Qt.UserRole)
                if key and it.checkState() == Qt.Checked:
                    off.add(key)
                    n += 1
            d_["off3d"] = sorted(off)
            dlg.accept()
            if n:
                self.commit(d_, f"{n} stray element(s) kept out of 3D")

        def put_back():
            d_ = self.doc()
            back = {lst2.item(r).data(Qt.UserRole) for r in range(lst2.count())
                    if lst2.item(r).checkState() == Qt.Checked}
            if not back:
                back = set(d_.get("off3d") or [])     # none ticked: all
            d_["off3d"] = sorted(set(d_.get("off3d") or []) - back)
            dlg.accept()
            self.commit(d_, f"{len(back)} element(s) back in 3D")
        row.addWidget(_btn("Keep the ticked found ones out of 3D", keep_out,
                           primary=True))
        row.addWidget(_btn("Put back (ticked, or all)", put_back))
        lay.addLayout(row)
        _place_on_screen(dlg, QCursor.pos())
        dlg.exec()

    def _convert_opening(self, sel, kind):
        doc = self.doc()
        ids = [i for k, i in self._selected_all() if k == "opening"] \
            or [sel[1]]
        n = 0
        for oid in ids:
            rec = PJ.find_record(doc, "opening", oid)
            if rec is None or rec.get("kind") == kind:
                continue
            new = PJ.opening_as(rec, kind, doc["settings"])
            why = PJ.check_record(doc, "opening", dict(new, id=rec["id"]))
            if why:
                self.flash(f"{rec.get('name')} not changed — {why}")
                continue
            rec.clear()
            rec.update(new)
            n += 1
        if n:
            lab = {"door": "door(s)", "window": "window(s)",
                   "void": "plain opening(s)"}[kind]
            self.commit(doc, f"{n} made {lab}, with that type's sizes")

    def _empty_openings(self):
        lid, lv = self.level()
        if not lid:
            self.flash("Pick a level at the top first")
            return
        doc = self.doc()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = PJ.revise_empty_openings(doc, [lid])
        except Exception as e:  # noqa: BLE001
            log_error("panel._empty_openings")
            self.flash(f"Not read — {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if lid not in r:
            self.flash("This level has no CAD plan imported")
            return
        if not r[lid]:
            self.flash("Every door here has a door drawn in the CAD")
            return
        self.commit(doc, f"{r[lid]} opening(s) with no door on «{lv['name']}»")

    def _update_levels(self):
        """Every level's storey height = the floor height typed (basements
        too), the ground floor at the level typed, the CAD's level notes
        applied over that when asked — then the model made again."""
        doc = self.doc()
        st = doc["settings"]
        h = round(float(self.i_floor_h.value()), 4)
        st["floor_h"] = h
        v = self.i_gffl.value()
        if 0.0 < v < 0.3048 - 1e-6:
            v = 0.3048
        st["ground_ffl"] = round(v, 4)
        if v > 0:
            st["plinth"] = round(v, 4)
        n = 0
        for lv_ in doc["arch"]["levels"]:
            if str(lv_.get("name", "")).strip().lower() == "roof":
                continue
            if abs(float(lv_.get("height") or 0) - h) > 1e-4:
                lv_["height"] = h
                n += 1
        doc["arch"]["levels"] = M.fix_levels(doc["arch"]["levels"])
        noted = []
        if self.i_levels.isChecked() and st.get("levels_cad", True):
            try:
                noted = PJ.levels_from_cad(doc) or []
            except Exception:  # noqa: BLE001
                log_error("panel._update_levels")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            try:
                PJ.recut_wells(doc)
            except Exception:  # noqa: BLE001
                log_error("panel._update_levels recut")
        finally:
            QApplication.restoreOverrideCursor()
        from .host import len_txt
        self.commit(doc, f"Floors and levels updated: {n} storey height(s) "
                         f"set to {len_txt(h)}, ground floor at "
                         + (PJ.ffl_text(v) if v > 0 else "the CAD's note")
                         + (f", {len(noted)} floor(s) as the CAD notes them"
                            if noted else ""))

    def _apply_gffl(self):
        doc = self.doc()
        v = self.i_gffl.value()
        if 0.0 < v < 0.3048 - 1e-6:
            v = 0.3048                       # 1'-0" at the least
            self.i_gffl.setValue(v)
        doc["settings"]["ground_ffl"] = round(v, 4)
        if v > 0:
            doc["settings"]["plinth"] = round(v, 4)
        from .host import len_txt
        self.commit(doc, "Ground floor at " + (PJ.ffl_text(v) if v > 0
                                              else "the CAD's level note"))

    def _store_flag(self, key, on):
        """A view setting stored (no rebuild; the overlay reads it)."""
        if getattr(self, "_building", False):
            return
        doc = self.doc()
        doc["settings"][key] = bool(on)
        try:
            PJ.store_only(self.vp, doc)
        except Exception:  # noqa: BLE001
            log_error("panel._store_flag")
        self.vp.update()

    def _apply_types(self):
        doc = self.doc()
        lid, _lv = self.level()
        if not lid:
            self.flash("Pick a level at the top first")
            return
        st = doc["settings"]
        self._type_settings(st)
        walls = {w["id"] for w in doc["arch"]["walls"] if w["level"] == lid}
        n = 0
        for o in doc["arch"]["openings"]:
            if o["wall"] not in walls or o["kind"] == "void":
                continue
            if o["kind"] == "door":
                if o.get("style") in PJ.SINGLE_TYPES + PJ.DOUBLE_TYPES + (
                        "double", "french"):
                    o["style"] = "hinged"
            else:
                if o.get("style") != st["win_style"]:
                    o["style"] = st["win_style"]
            PJ.opening_types(o, st)
            n += 1
        self.commit(doc, f"{n} doors / windows: types and heads applied")

    def _openings_part(self):
        box, body = _fold("5  Openings", "openings", False)
        f = _form(body)
        # read again from the level's CAD plan (the level picked at the top)
        f.addRow(_btn("Find corner windows (this level)",
                      self._corner_windows,
                      "Glazing drawn double turning a corner where the "
                      "walls stop made one aluminium corner window — from "
                      "this level's CAD plan; the rest of the level stays "
                      "(glazing round a terrace becomes its railing)"))
        f.addRow(_btn("Openings with no door drawn → no door (this level)",
                      self._empty_openings,
                      "The sliding doors put in openings the CAD shows empty "
                      "(no swing, no glazing, no door block) made plain "
                      "openings, a doorway with no door"))
        self.o_door_h = _spin(0.5, 6, 2.10)
        self.o_win_h = _spin(0.2, 6, 1.20)
        self.o_sill = _spin(0, 6, 0.90)
        f.addRow("Door height (import)", self.o_door_h)
        f.addRow("Window height (import)", self.o_win_h)
        f.addRow("Window sill (import)", self.o_sill)
        self.o_wstyle = QComboBox()
        for k, label in (("casement", "Casement (hinged)"),
                         ("sliding", "Sliding"), ("fixed", "Fixed glass"),
                         ("top-hung", "Top-hung"), ("louvre", "Louvre")):
            self.o_wstyle.addItem(label, k)
        f.addRow("Window type (import)", self.o_wstyle)
        from .engine import structure as S_
        self.o_dstyle = QComboBox()
        self.o_d2style = QComboBox()
        for k, label in S_.DOOR_STYLES:
            if k in PJ.SINGLE_TYPES:
                self.o_dstyle.addItem(label, k)
            if k in PJ.DOUBLE_TYPES:
                self.o_d2style.addItem(label, k)
        f.addRow("Door type, single leaf (import)", self.o_dstyle)
        f.addRow("Door type, double leaf (import)", self.o_d2style)
        f.addRow(QLabel("<i>Leaves: up to 4'-0\" single, up to 8'-0\" "
                        "double, wider a glass sliding door — and any door "
                        "can be set single or double in «Selected "
                        "element».</i>"))
        self.o_dhead = QComboBox()
        self.o_whead = QComboBox()
        for k, label in S_.HEADS:
            self.o_dhead.addItem(label, k)
            self.o_whead.addItem(label, k)
        f.addRow("Door head (import)", self.o_dhead)
        f.addRow("Window head (import)", self.o_whead)
        self.o_dframe = QComboBox()
        self.o_wframe = QComboBox()
        for cb_ in (self.o_dframe, self.o_wframe):
            cb_.addItem("Auto (wood: hinged, aluminium: sliding / windows)",
                        "auto")
            for k, (label, *_r) in S_.FRAMES.items():
                cb_.addItem(label, k)
        f.addRow("Door frame (import)", self.o_dframe)
        f.addRow("Window frame (import)", self.o_wframe)
        f.addRow(_btn("Apply these types and heads to this level's doors "
                      "and windows", self._apply_types,
                      "Every door and window of the level picked at the "
                      "top: the types and heads above (wide openings stay "
                      "double / sliding by their width)"))
        f.addRow(QLabel("<i>Openings drawn without swing or glazing — down "
                        "to the floor — come in as glass sliding doors. "
                        "Change a door / window's type, hinge, side or place "
                        "in part «Selected element».</i>"))
        f.addRow(QLabel("<i>Add one to the selected wall:</i>"))
        self.o_kind = QComboBox()
        self.o_kind.addItems(["door", "window", "void"])
        self.o_w = _spin(0.2, 20, 0.90)
        self.o_pos = _spin(0, 500, 1.0)
        f.addRow("Type", self.o_kind)
        f.addRow("Width", self.o_w)
        f.addRow("Centre from wall start", self.o_pos)
        f.addRow(_btn("Add to selected wall", self._add_opening))
        self.lay.addWidget(box)

    def _add_opening(self):
        sel = self._selected()
        if not sel or sel[0] != "wall":
            self.flash("Select a wall first (click it in the model)")
            return
        doc = self.doc()
        kind = self.o_kind.currentText()
        w_ = PJ.find_record(doc, "wall", sel[1])
        if w_ is not None and w_.get("type") == "curtain":
            if kind != "door":
                self.flash("A curtain wall is glass already — add a door "
                           "to it, or right-click it ▸ Add door")
                return
            rec, why = PJ.add_cw_door(doc, sel[1], "alu_glass",
                                      self.o_w.value(), self.o_pos.value())
            if why:
                self.flash(f"Not added — {why}")
                return
            self.commit(doc, "Door added to the curtain wall (on its grid)")
            return
        rec = {"kind": kind, "wall": sel[1], "pos": self.o_pos.value(),
               "w": self.o_w.value(),
               "h": self.o_door_h.value() if kind != "window"
               else self.o_win_h.value(),
               "sill": 0.0 if kind != "window" else self.o_sill.value(),
               "swing": "left"}
        why = PJ.check_record(doc, "opening", rec)
        if why:
            self.flash(f"Not added — {why}")
            return
        doc["arch"]["openings"] += M.new_openings(doc["arch"]["openings"],
                                                  [rec])
        self.commit(doc, f"{kind.title()} added")

    # ---- 4. structure -------------------------------------------------------------
    def _structure_part(self):
        box, body = _fold("6  Structure and foundation", "structure", False)
        f = _form(body)
        self.s_slab = QCheckBox("Floor slab on import (outline layer, else "
                                "round the walls)")
        self.s_slab_t = _spin(0.05, 2, 0.15)
        f.addRow(self.s_slab)
        f.addRow("Slab thickness", self.s_slab_t)
        self.s_slab_pos = QComboBox()
        self.s_slab_pos.addItem("Over each floor (cast on its walls)", "top")
        self.s_slab_pos.addItem("Under each floor (at its floor level)",
                                "bottom")
        self.s_slab_pos.setToolTip(
            "Over: each floor's slab on top of its walls — the top floor "
            "gets its roof slab, the ground floor stands on the ground. "
            "The stair / ramp wells move with it.")
        self.s_slab_pos.currentIndexChanged.connect(self._slab_pos)
        f.addRow("Slab position", self.s_slab_pos)
        f.addRow(QLabel("<i>Sunk / raised floor — select rooms' floor "
                        "finishes, or draw a rectangle (Rectangle tool) on "
                        "the floor and select it:</i>"))
        row = QHBoxLayout()
        self.s_sunk = _spin(-3.0, 3.0, -0.1524, 0.0127, 3)
        self.s_sunk.setToolTip("− sinks the floor (a toilet, a pool), + "
                               "raises it (a platform)")
        row.addWidget(self.s_sunk)
        row.addWidget(_btn("Sunk / raise selected", self._sunk_selected,
                           "The selected rooms' floors, or the selected "
                           "drawn areas, at this level against the floor"))
        f.addRow("Level ±", row)
        self.s_slab_re = QCheckBox("Replace the slabs there already")
        f.addRow(self.s_slab_re)
        f.addRow(_btn("Auto slab on every floor", self._auto_slabs,
                      "A floor slab on each level with walls, round the "
                      "outside of its walls (stair holes kept)"))
        self.s_col = _spin(0.1, 2, 0.30)
        f.addRow("Column size", self.s_col)
        row = QHBoxLayout()
        row.addWidget(_btn("Columns from the CAD (all levels)",
                           lambda: self._cad_columns(False),
                           "Read every imported level's columns again from "
                           "its CAD plan — walls, openings and your edits "
                           "stay; a layer naming a run of floors («S-CONC "
                           "FOUNDATION TO 6TH») only on those floors",
                           primary=True))
        row.addWidget(_btn("This level", lambda: self._cad_columns(True)))
        f.addRow(row)
        f.addRow(_btn("Columns at wall corners (this level)",
                      self._corner_columns))
        row = QHBoxLayout()
        row.addWidget(_btn("Open shaft (draw ▭)",
                           lambda: self.shaft_rect(None, "open"),
                           "Select a slab, click this, then click two "
                           "opposite corners on it: a shaft opened there"))
        row.addWidget(_btn("Through all floors",
                           lambda: self.shaft_rect(None, "through")))
        row.addWidget(_btn("Close shaft (draw ▭)",
                           lambda: self.shaft_rect(None, "close"),
                           "Select a slab, click this, then draw a rectangle "
                           "round the opening to close"))
        f.addRow("Shaft open / close", row)
        f.addRow(_btn("Shaft by size (W × D at X, Y)…",
                      lambda: self.shaft_dialog(None)))
        row = QHBoxLayout()
        self.s_bw = _spin(0.1, 2, 0.2032, 0.0254)        # 8"
        self.s_bh = _spin(0.1, 3, 0.6096, 0.0254)        # 24"
        self.s_bw.setToolTip("Beam width (8\" by default)")
        self.s_bh.setToolTip("Beam depth, slab included (24\" by default)")
        row.addWidget(self.s_bw)
        row.addWidget(self.s_bh)
        f.addRow("Beam width / depth", row)
        self.s_bon = QComboBox()
        self.s_bon.addItem("Column to column (the column grid)", "columns")
        self.s_bon.addItem("Over the walls", "walls")
        f.addRow("Beams run", self.s_bon)
        self.s_bspan = _spin(2.0, 20.0, 10.0, 0.3048)
        self.s_bspan.setToolTip("The longest span joined by a beam: columns "
                                "farther apart are left without one")
        f.addRow("Longest beam span", self.s_bspan)
        row = QHBoxLayout()
        row.addWidget(_btn("Beams (this level)", self._beams,
                           "Column to column: each column joined to the "
                           "nearest column in each of its four grid "
                           "directions, the beam between their faces — each "
                           "beam its own element (typed B-nn by its size). "
                           "Replaces this level's beams"))
        row.addWidget(_btn("All levels", lambda: self._beams(True)))
        f.addRow(row)
        f.addRow(QLabel("<i>Foundation:</i>"))
        self.s_found = _spin(-30, 0, -1.50, 0.05, 2)
        self.s_found.setToolTip("The footings' bottom, from ±0.00 (the "
                                "ground floor). Footings hang from under "
                                "the lowest level's slab down to here.")
        f.addRow("Foundation level", self.s_found)
        self.s_pad = _spin(0.3, 6, 1.20)
        f.addRow("Pad width (under columns)", self.s_pad)
        self.s_strip = _spin(0.2, 4, 0.60)
        f.addRow("Strip width (under walls)", self.s_strip)
        self.s_ftype = QComboBox()
        for k_, lab_ in PJ.FOUNDATION_TYPES:
            self.s_ftype.addItem(lab_, k_)
        f.addRow("Foundation type", self.s_ftype)
        row = QHBoxLayout()
        self.s_raft_t = _spin(0.2, 3.0, 0.6096, 0.0508)       # 2'-0"
        self.s_raft_t.setToolTip("Raft thickness")
        self.s_raft_o = _spin(0.0, 5.0, 0.6096, 0.0508)
        self.s_raft_o.setToolTip("How far the raft runs out past the walls "
                                 "and columns")
        row.addWidget(self.s_raft_t)
        row.addWidget(self.s_raft_o)
        f.addRow("Raft thickness / projection", row)
        f.addRow(_btn("Footings under the lowest level", self._footings,
                      "Pads under its columns, strips under its walls — "
                      "or import a foundation plan: Level ▸ Foundation"))
        f.addRow(QLabel("<i>Basement: Level ▸ «＋ Basement (new, below)», "
                        "then import its plan — or + Basement in part 2.</i>"))
        self.s_rt = _spin(0.15, 1.0, 0.3048, 0.0254)     # 12"
        self.s_rt.setToolTip("The RCC retaining walls' least thickness "
                             "(12\" by default)")
        f.addRow("Retaining wall (RCC) min.", self.s_rt)
        row = QHBoxLayout()
        row.addWidget(_btn("Basement outer walls → RCC", self._retaining,
                           "Every basement's outer walls made RCC retaining "
                           "walls (as a lift core's): no doors or windows in "
                           "them, at least the thickness above. Done by "
                           "itself when a basement plan is imported"))
        row.addWidget(_btn("Undo RCC", lambda: self._retaining(False)))
        f.addRow(row)
        from . import shoring as SH
        self.s_sh = QCheckBox("Shoring (basement dig)")
        self.s_sh.setToolTip("Piles (or sheet piles) round the plot, from "
                             "the ground to under the lowest basement")
        f.addRow(self.s_sh)
        self.s_sh_kind = QComboBox()
        for k, lab in SH.TYPES:
            self.s_sh_kind.addItem(lab, k)
        f.addRow("Shoring type", self.s_sh_kind)
        self.s_sh_on = QComboBox()
        self.s_sh_on.addItem("Along the plot limits", "plot")
        self.s_sh_on.addItem("Round the basement's outer (RCC) walls",
                             "walls")
        f.addRow("Shoring along", self.s_sh_on)
        row = QHBoxLayout()
        self.s_sh_d = _spin(0.3, 1.5, 0.6096, 0.0254)      # 24" piles
        self.s_sh_d.setToolTip("Pile diameter")
        self.s_sh_e = _spin(0.5, 20, 3.048, 0.1524)        # 10'-0"
        self.s_sh_e.setToolTip("Embedment under the lowest basement floor")
        row.addWidget(self.s_sh_d)
        row.addWidget(self.s_sh_e)
        f.addRow("Pile Ø / embedment", row)
        f.addRow(_btn("Apply shoring", self._shoring))
        self.lay.addWidget(box)

    def _retaining(self, on=True):
        doc = self.doc()
        doc["settings"]["retain_t"] = self.s_rt.value()
        doc["settings"]["basement_rcc"] = bool(on)
        r = PJ.basement_walls(doc, None, self.s_rt.value(), on)
        if not r["walls"]:
            self.flash("No basement outer walls found (add a basement and "
                       "import its plan first)")
            return
        self.commit(doc, f"{r['walls']} basement walls RCC, "
                         f"{r['openings']} openings closed" if on else
                    f"{r['walls']} basement walls ordinary again")

    def _shoring(self):
        doc = self.doc()
        st = doc["settings"]
        st["shoring"] = self.s_sh.isChecked()
        st["shoring_type"] = self.s_sh_kind.currentData() or "piles"
        st["shoring_on"] = self.s_sh_on.currentData() or "plot"
        st["shoring_d"] = self.s_sh_d.value()
        st["shoring_embed"] = self.s_sh_e.value()
        if st["shoring"] and st["shoring_on"] == "plot" and \
                not doc["arch"].get("plot"):
            self.flash("Set the plot first (Site ▸ Plot) — shoring follows "
                       "its limits")
        elif st["shoring"] and not any(lv.get("kind") == "basement"
                                       for lv in doc["arch"]["levels"]):
            self.flash("There's no basement — shoring is for a basement dig")
        self.commit(doc, "Shoring " + ("on" if st["shoring"] else "off"))

    def _slab_pos(self, _i=None):
        if self._building:
            return
        doc = self.doc()
        pos = self.s_slab_pos.currentData() or "top"
        if doc["settings"].get("slab_pos", "top") == pos:
            return
        doc["settings"]["slab_pos"] = pos
        PJ.apply_slab_pos(doc)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            PJ.recut_wells(doc)
        finally:
            QApplication.restoreOverrideCursor()
        self.commit(doc, "Slabs " + ("over each floor, on its walls"
                                     if pos == "top" else
                                     "under each floor, at its level"))

    def _sunk_selected(self):
        """The selected rooms' floors (their finishes picked in the model)
        or the drawn areas selected: sunk / raised by the offset typed."""
        off = round(self.s_sunk.value(), 4)
        doc = self.doc()
        arch = doc["arch"]
        rooms, areas = [], []
        for e in list(self.vp.scene.selection):
            tag = None
            for g in (e, getattr(e, "owner", None)):
                tag = PJ.tag_of(g) if g is not None else None
                if tag:
                    break
            if tag and tag.get("type") == "room":
                if tag["id"] not in rooms:
                    rooms.append(tag["id"])
                continue
            if tag is None and hasattr(e, "loop") and hasattr(e,
                                                             "vertices"):
                vs = [(v.x(), v.y(), v.z()) for v in e.vertices]
                if len(vs) >= 3 and max(v[2] for v in vs) - \
                        min(v[2] for v in vs) < 0.05:     # flat: a floor
                    areas.append(vs)
        if not rooms and not areas:
            self.flash("Select rooms' floor finishes, or a rectangle drawn "
                       "on the floor")
            return
        for rid in rooms:
            rec = PJ.room_record(doc, rid)
            if rec is not None:
                rec["fz"] = off
        made = 0
        elev = PJ.elevations(arch)
        for vs in areas:
            z = sum(v[2] for v in vs) / len(vs)
            lid = None
            for i, lv in enumerate(arch["levels"]):
                if elev[i] <= z + 0.5 and any(w["level"] == lv["id"]
                                               for w in arch["walls"]):
                    lid = lv["id"]
            lid = lid or self.level()[0]
            if PJ.sunk_area(doc, lid, [v[:2] for v in vs], off):
                made += 1
        what = []
        if rooms:
            what.append(f"{len(rooms)} room(s)")
        if made:
            what.append(f"{made} area(s)")
        self.commit(doc, f"{' and '.join(what)} "
                         f"{'sunk' if off < 0 else 'raised'} "
                         f"{len_txt(abs(off))}")

    def _auto_slabs(self):
        doc = self.doc()
        n = PJ.auto_slabs(doc, self.s_slab_t.value(),
                          self.s_slab_re.isChecked())
        if not n:
            self.flash("Every floor has its slab already (tick «Replace» "
                       "to make them again)")
            return
        self.commit(doc, f"{n} floor slabs made")

    # ---- 7. stairs, terraces, balconies -----------------------------------------
    def _stairs_part(self):
        box, body = _fold("7  Stairs, terraces and balconies", "stairs",
                          False)
        f = _form(body)
        self.st_info = QLabel("")
        self.st_info.setWordWrap(True)
        f.addRow(self.st_info)
        self.st_flip = QCheckBox("Start the flight on the other side")
        f.addRow(self.st_flip)
        from . import stairs as ST
        self.st_type = QComboBox()
        for k, label in ST.TYPES:
            self.st_type.addItem(label, k)
        f.addRow("Stair type", self.st_type)
        self.st_waist = _spin(0.05, 0.6, 0.1524, 0.0254)
        self.st_waist.setToolTip("Monolithic RCC: the waist slab's thickness "
                                 "under the steps (6\" = 152 mm)")
        f.addRow("Waist slab", self.st_waist)
        self.st_well = QComboBox()
        for k_, lab_ in ST.WELL_MODES:
            self.st_well.addItem(lab_, k_)
        self.st_well.setToolTip("The opening each stair cuts in the slab "
                                "above it (Stairs on all floors makes them "
                                "again)")
        f.addRow("Opening in the slab above", self.st_well)
        row = QHBoxLayout()
        self.st_riser = _spin(0.10, 0.25, 0.1778, 0.0127)     # 7"
        self.st_going = _spin(0.18, 0.45, 0.2794, 0.0127)     # 11"
        self.st_riser.setToolTip("Risers no higher than this: the number of "
                                 "steps follows the storey height")
        self.st_going.setToolTip("The tread (going) of a standard stair — "
                                 "less only where its well is too short")
        row.addWidget(self.st_riser)
        row.addWidget(self.st_going)
        f.addRow("Riser (max) / tread", row)
        self.st_nose = _spin(0.0, 0.1, 0.025, 0.005)
        f.addRow("Nosing", self.st_nose)
        self.st_tread = _spin(0.02, 0.2, 0.05, 0.005)
        f.addRow("Tread thickness (open / cantilever)", self.st_tread)
        from .engine import railings as RL_
        self.st_rail = QComboBox()
        self.st_rail.addItem("No railing", "none")
        for k, label in RL_.TYPES:
            self.st_rail.addItem(label, k)
        f.addRow("Stair railing", self.st_rail)
        row = QHBoxLayout()
        self.st_rail_h = _spin(0.6, 1.5, 0.9144, 0.0254)
        self.st_rail_sides = QComboBox()
        self.st_rail_sides.addItem("Inner side (by the well)", "inner")
        self.st_rail_sides.addItem("Outer side (by the wall)", "outer")
        self.st_rail_sides.addItem("Both sides", "both")
        self.st_rail_sides.addItem("No railing", "none")
        row.addWidget(self.st_rail_h)
        row.addWidget(self.st_rail_sides)
        f.addRow("Railing height / sides", row)
        row = QHBoxLayout()
        self.st_rail_off = _spin(0.0, 0.5, 0.05, 0.01)
        self.st_rail_off.setToolTip("How far in from the flight's edge the "
                                    "railing stands")
        self.st_rail_gap = _spin(0.0, 2.0, 0.0, 0.01)
        self.st_rail_gap.setToolTip("Baluster spacing (glass panels / posts "
                                    "for glass and pipe railings); 0 = the "
                                    "railing type's own")
        self.st_rail_ext = _spin(0.0, 1.0, 0.0, 0.05)
        self.st_rail_ext.setToolTip("The handrail run on level past the "
                                    "first and the last step")
        for w_ in (self.st_rail_off, self.st_rail_gap, self.st_rail_ext):
            row.addWidget(w_)
        f.addRow("Railing inset / spacing / run-on", row)
        f.addRow(_btn("Apply stair type and railing", self._stair_type,
                      "Remake the stairs there are with this type and "
                      "railing"))
        row = QHBoxLayout()
        row.addWidget(_btn("Stairs on all floors", self._stairs, "Each "
                           "level's stair well — from the CAD's stair layer, "
                           "else a room named STAIR…, else the floor "
                           "below's — gets a stair up to the next level, "
                           "and the well is cut in that level's slab",
                           primary=True))
        row.addWidget(_btn("Remove", self._stairs_remove))
        f.addRow(row)
        f.addRow(_btn("Flights, rotation and landings…",
                      lambda: self.stair_flights_dialog(),
                      "Lay a stair out by hand where the CAD was read "
                      "wrong: the flights, how each turns off its landing, "
                      "the whole stair turned — the landings and railings "
                      "follow (the selected stair, else this level's)"))
        f.addRow(QLabel("<i>Terraces (every upper floor):</i>"))
        row = QHBoxLayout()
        self.te_h = _spin(0, 3, 1.0)
        self.te_t = _spin(0.05, 1, 0.15)
        row.addWidget(self.te_h)
        row.addWidget(self.te_t)
        f.addRow("Parapet height / thickness", row)
        from .engine import railings as RL2_
        self.pa_rail = QComboBox()
        for k, label in RL2_.TYPES:
            self.pa_rail.addItem(label, k)
        self.pa_rail.setToolTip("What the parapets of terraces, the roof and "
                                "balconies are made of")
        f.addRow("Parapet / railing type", self.pa_rail)
        f.addRow(_btn("Apply to every parapet and balcony", self._parapet_rail,
                      "Terrace and roof parapets, balcony railings — on all "
                      "levels"))
        row = QHBoxLayout()
        self.t_mat = QComboBox()
        _lab = _ML.labels()
        for k_ in _ML.keys_for("terrace"):
            self.t_mat.addItem(_lab.get(k_, k_), k_)
        row.addWidget(self.t_mat, 1)
        row.addWidget(_btn("Apply", self._terrace_mat,
                           "The terraces' floors (the open terraces and the "
                           "roof terraces) in this IngeTrazo material"))
        f.addRow("Terrace floor material", row)
        self.t_rkind = QComboBox()
        self.t_rkind.addItem("3\" wall (plastered)", "wall3")
        self.t_rkind.addItem("Railing on a 3\" upstand", "railing")
        self.t_rkind.setToolTip("What the terraces' edges get: a 3\" thick "
                                "plastered wall, the railing's height "
                                "(default), or the railing type above on a "
                                "3\" × 6\" upstand")
        self.t_rkind.currentIndexChanged.connect(self._terrace_rkind)
        f.addRow("Terrace edge", self.t_rkind)
        f.addRow(_btn("Terrace railings from the CAD (this level)",
                      self._terrace_rails,
                      "Railings all round this level's terraces: along the "
                      "railing lines its CAD plan draws there (the terrace "
                      "slab stops at them — nothing beyond the railing) and "
                      "on every other open edge, each on a 3\" upstand"))
        f.addRow(_btn("Selected slab → roof terrace floor",
                      self._roof_terrace,
                      "Select a slab in the model first: it becomes a roof "
                      "terrace — a floor over it (a «Roof terrace» level "
                      "when there is none), railings on 3\" upstands along "
                      "its free edges with one post at each corner, "
                      "terrace tiles and rain-water outlets"))
        f.addRow(_btn("Terraces over the floors below", self._terrace,
                      "The part of the floor below's roof this floor leaves "
                      "open: a parapet on its open edges, joined clean at "
                      "the corners and into this floor's walls (with slabs "
                      "over each floor, the terrace is the slab below — "
                      "no slab over it)"))
        f.addRow(QLabel("<i>Balcony (select a wall in the model):</i>"))
        row = QHBoxLayout()
        self.ba_d = _spin(0.3, 5, 1.2)
        self.ba_w = _spin(0, 30, 0.0)
        self.ba_w.setToolTip("0 = the wall's whole length")
        row.addWidget(self.ba_d)
        row.addWidget(self.ba_w)
        f.addRow("Depth / width (0 = wall)", row)
        row = QHBoxLayout()
        self.ba_h = _spin(0.3, 2, 1.0)
        self.ba_t = _spin(0.03, 0.5, 0.10)
        row.addWidget(self.ba_h)
        row.addWidget(self.ba_t)
        f.addRow("Railing height / thickness", row)
        f.addRow(_btn("Balcony on the selected wall", self._balcony))
        self.lay.addWidget(box)

    def _parapet_rail(self):
        doc = self.doc()
        kind = self.pa_rail.currentData()
        doc["settings"]["parapet_rail"] = kind
        n = PJ.apply_parapet_rail(doc, kind)
        if not n:
            self.flash("No parapet to change (make terraces, a roof level or "
                       "a balcony first) — the type is kept for new ones")
            PJ.store_only(self.vp, doc)
            return
        self.commit(doc, f"{n} parapets: {self.pa_rail.currentText()}")

    def _fill_stairs(self, doc):
        from .host import len_txt
        stt = doc["settings"]
        for cb, key, dv in ((self.st_rail, "stair_rail", "ss_bars"),
                            (self.st_rail_sides, "stair_rail_sides", "inner"),
                            (self.pa_rail, "parapet_rail", "solid")):
            cb.blockSignals(True)
            cb.setCurrentIndex(max(cb.findData(stt.get(key, dv)), 0))
            cb.blockSignals(False)
        self.st_rail_h.setValue(float(stt.get("stair_rail_h", 0.9144)))
        self.st_rail_off.setValue(float(stt.get("stair_rail_off", 0.05)))
        self.st_rail_gap.setValue(float(stt.get("stair_rail_gap", 0.0)))
        self.st_rail_ext.setValue(float(stt.get("stair_rail_ext", 0.0)))
        self.st_type.setCurrentIndex(max(self.st_type.findData(
            stt.get("stair_type", "monolithic")), 0))
        self.st_waist.setValue(float(stt.get("stair_waist", 0.1524)))
        self.st_riser.setValue(float(stt.get("stair_riser", 0.1778)))
        self.st_going.setValue(float(stt.get("stair_going", 0.2794)))
        self.st_nose.setValue(float(stt.get("stair_nosing", 0.025)))
        self.st_tread.setValue(float(stt.get("stair_tread", 0.05)))
        n_cad = sum(len(v) for v in doc.get("stair_cad", {}).values())
        n = len(doc.get("stairs") or [])
        if n:
            s0 = doc["stairs"][0]
            self.st_info.setToolTip(f"riser {len_txt(s0['rise'])} · going "
                                    f"{len_txt(s0['going'])}")
        self.st_info.setText(
            f"{n} stair flights in the model" + (
                f" · {n_cad} stair wells found in the CAD plans" if n_cad
                else " · no stair layer in the plans (rooms named STAIR… "
                     "are used)"))

    def _stair_opts(self, doc):
        doc["settings"].update(stair_type=self.st_type.currentData(),
                               stair_waist=self.st_waist.value(),
                               stair_riser=self.st_riser.value(),
                               stair_going=self.st_going.value(),
                               stair_nosing=self.st_nose.value(),
                               stair_tread=self.st_tread.value(),
                               stair_rail=self.st_rail.currentData(),
                               stair_rail_h=self.st_rail_h.value(),
                               stair_rail_sides=self.st_rail_sides
                               .currentData(),
                               stair_rail_off=self.st_rail_off.value(),
                               stair_rail_gap=self.st_rail_gap.value(),
                               stair_rail_ext=self.st_rail_ext.value())

    def _stair_type(self):
        doc = self.doc()
        self._stair_opts(doc)
        self.commit(doc, f"Stairs: {self.st_type.currentText()}")

    def _stairs(self):
        from . import stairs as ST
        doc = self.doc()
        self._stair_opts(doc)
        doc["settings"]["stair_well"] = self.st_well.currentData() or \
            "railing"
        r = ST.auto(doc, flip=self.st_flip.isChecked())
        if not r["stairs"]:
            self.flash("No stair well found — draw it on a STAIR layer, or "
                       "name the room STAIRCASE", 9000)
            return
        self.commit(doc, f"{r['stairs']} stairs, {r['cuts']} wells cut in "
                         "the slabs")

    def _stairs_remove(self):
        from . import stairs as ST
        doc = self.doc()
        ST._uncut(doc)
        doc["stairs"] = []
        self.commit(doc, "Stairs removed")

    def _terrace(self):
        from . import stairs as ST
        doc = self.doc()
        done = ST.terraces_all(doc, self.te_h.value(), self.te_t.value())
        if not done:
            self.flash("No terrace — every upper floor covers the floor "
                       "below it (or there is no upper floor)", 9000)
            return
        self.commit(doc, "Terraces: " + ", ".join(
            f"{n} {area_txt(a)}" for n, a in done))

    def _balcony(self):
        from . import stairs as ST
        sel = self._selected()
        if not sel or sel[0] != "wall":
            self.flash("Select an outside wall first (click it in the model)")
            return
        doc = self.doc()
        r = ST.balcony(doc, sel[1], self.ba_d.value(), self.ba_w.value(),
                       None, self.ba_h.value(), self.ba_t.value(),
                       self.s_slab_t.value())
        if r.get("why"):
            self.flash(f"No balcony — {r['why']}", 8000)
            return
        self.commit(doc, f"Balcony {area_txt(r['area'])}")

    def _cad_columns(self, this_level=False):
        doc = self.doc()
        lid, _lv = self.level()
        if this_level and not lid:
            self.flash("Pick a level at the top first")
            return
        from PySide6.QtWidgets import QApplication as _QA
        _QA.setOverrideCursor(Qt.WaitCursor)
        try:
            r = PJ.redetect_columns(doc, [lid] if this_level else None)
        finally:
            _QA.restoreOverrideCursor()
        if not r:
            self.flash("No level imported from a CAD plan here", 8000)
            return
        names = {lv["id"]: lv["name"] for lv in doc["arch"]["levels"]}
        msg = ", ".join(f"{names.get(k, k)} {a}→{b}" for k, (a, b)
                        in r.items())
        self.commit(doc, f"Columns from the CAD: {msg}")

    def _corner_columns(self):
        doc = self.doc()
        lid, lv = self.level()
        n = PJ.add_corner_columns(doc, lid, self.s_col.value())
        self.commit(doc, f"{n} columns on «{lv['name']}»")

    def _beams(self, all_levels=False):
        doc = self.doc()
        st = doc["settings"]
        st["beam_w"] = self.s_bw.value()
        st["beam_h"] = self.s_bh.value()
        st["beam_on"] = self.s_bon.currentData() or "columns"
        st["beam_span"] = self.s_bspan.value()
        if all_levels:
            lids = [lv_["id"] for lv_ in doc["arch"]["levels"]]
        else:
            lid, lv = self.level()
            if not lid:
                self.flash("Pick a level at the top first")
                return
            lids = [lid]
        n, nocol = 0, []
        names = {lv_["id"]: lv_["name"] for lv_ in doc["arch"]["levels"]}
        for lid_ in lids:
            has_cols = any(e["type"] == "column" and e["level"] == lid_
                           for e in doc["arch"]["structure"])
            has_walls = any(w["level"] == lid_ for w in doc["arch"]["walls"])
            if st["beam_on"] == "columns":
                if has_cols:
                    n += PJ.add_beams_on_columns(doc, lid_, st["beam_w"],
                                                 st["beam_h"],
                                                 st["beam_span"])
                elif has_walls:
                    nocol.append(names.get(lid_, lid_))
            elif has_walls:
                n += PJ.add_beams_on_walls(doc, lid_, st["beam_w"],
                                           st["beam_h"])
        msg = f"{n} beams" + (" column to column" if st["beam_on"] ==
                              "columns" else " over the walls")
        if nocol:
            msg += " — no columns on " + ", ".join(nocol[:4]) + \
                (" …" if len(nocol) > 4 else "") + \
                " (add columns, or pick «Over the walls»)"
        self.commit(doc, msg)

    def _beams_cc(self, lid):
        doc = self.doc()
        st = doc["settings"]
        n = PJ.add_beams_on_columns(doc, lid, float(st.get("beam_w", 0.2032)),
                                    float(st.get("beam_h", 0.6096)),
                                    float(st.get("beam_span", 10.0)))
        self.commit(doc, f"{n} beams column to column")

    def _beam_z(self, b):
        doc = self.doc()
        el = PJ.elevations(doc["arch"])
        i = next(k for k, lv in enumerate(doc["arch"]["levels"])
                 if lv["id"] == b["level"])
        top = el[i + 1] if i + 1 < len(el) else el[i] + 3.0
        return top - float(b.get("h", 0.6))

    def _beam_pick(self, bid):
        """The beam's nearer end trimmed / extended to the point clicked."""
        from . import planedit as PE_
        b = PJ.find_record(self.doc(), "beam", bid)
        pe = getattr(self, "_planedit", None)
        if b is None or pe is None:
            return

        def done(p):
            doc = self.doc()
            ok, why = PE_.trim_extend_beam(doc, bid, "near", "point", pt=p)
            if not ok:
                self.flash(f"Not changed — {why}")
                return
            self.commit(doc, f"Beam trimmed / extended to the point "
                             f"({why} long)")
        pe.pick_point(self._beam_z(b), done,
                      "Click where the beam should end — its nearer end "
                      "moves there along its line (Esc cancels)")

    def beam_trim_dialog(self, bid):
        """A beam's end moved along its line: by a length, to a point, to
        the nearest column's face or the nearest beam / wall."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        from . import planedit as PE_
        doc = self.doc()
        b = PJ.find_record(doc, "beam", bid)
        if b is None:
            return
        L = math.dist(b["a"], b["b"])
        dlg = QDialog(self)
        dlg.setWindowTitle("Trim / extend beam — CAD2IngeTrazo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"<b>{b.get('name', 'Beam')}</b> · "
                             f"{len_txt(L)} long"))
        form = QFormLayout()
        lay.addLayout(form)
        end = QComboBox()
        end.addItem(f"Start ({b['a'][0]:.2f}, {b['a'][1]:.2f})", "a")
        end.addItem(f"End ({b['b'][0]:.2f}, {b['b'][1]:.2f})", "b")
        form.addRow("Which end", end)
        how = QComboBox()
        how.addItem("To the face of the nearest column in its line",
                    "column")
        how.addItem("To the nearest beam / wall in its line", "beam")
        how.addItem("By a length (+ extend, − trim)", "length")
        how.addItem("To a point I click in the model", "pick")
        form.addRow("Trim / extend", how)
        ln = _spin(-50.0, 50.0, 0.3048, 0.0254)
        form.addRow("Length (+ / −)", ln)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        if dlg.exec() != QDialog.Accepted:
            return
        mode = how.currentData()
        e_ = end.currentData()
        if mode == "pick":
            pe = getattr(self, "_planedit", None)
            if pe is None:
                return

            def done(p):
                d2 = self.doc()
                ok, why = PE_.trim_extend_beam(d2, bid, e_, "point", pt=p)
                if not ok:
                    self.flash(f"Not changed — {why}")
                    return
                self.commit(d2, f"Beam trimmed / extended ({why} long)")
            pe.pick_point(self._beam_z(b), done)
            return
        doc = self.doc()
        ok, why = PE_.trim_extend_beam(doc, bid, e_, mode, ln.value())
        if not ok:
            self.flash(f"Not changed — {why}", 8000)
            return
        self.commit(doc, f"Beam trimmed / extended ({why} long)")

    def _footings(self):
        doc = self.doc()
        doc["settings"]["found_level"] = self.s_found.value()
        kind = self.s_ftype.currentData() or "isolated_strip"
        doc["settings"]["raft_t"] = self.s_raft_t.value()
        doc["settings"]["raft_off"] = self.s_raft_o.value()
        n = PJ.add_footings(doc, self.s_pad.value(), None,
                            self.s_strip.value(), None, kind,
                            self.s_raft_t.value(), self.s_raft_o.value())
        lab = dict(PJ.FOUNDATION_TYPES).get(kind, kind).split(" (")[0]
        if not n:
            self.flash("No footings made — the lowest level needs columns "
                       "(isolated / combined) or walls (strip / raft)")
            return
        self.commit(doc, f"{lab}: {n} footing(s) down to "
                         f"{self.s_found.value():+.2f}")

    def _import_foundation(self, doc, path):
        doc["settings"].update(self._settings_from_ui())
        doc["settings"]["found_level"] = self.s_found.value()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rep = PJ.import_foundation(doc, path, self._how())
        except Exception as e:  # noqa: BLE001
            log_error("panel._import_foundation")
            self.i_report.setText(f"⚠ Not read — {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not rep["pads"] and not rep["strips"]:
            self.i_report.setText(
                "⚠ No footings found — they are read from closed outlines, "
                "circles and line pairs on the footing layers (Layers ▸ "
                "Footings)")
            return
        if self.i_auto.isChecked() and rep.get("roles"):
            self._show_roles(rep["roles"])
        if not self.commit(doc):
            return
        self.level_box.setCurrentIndex(self.level_box.findData(FOUNDATION))
        txt = (f"Foundation: {rep['pads']} pads, {rep['strips']} strips, "
               f"{rep['depth']:.2f} m deep (to {self.s_found.value():+.2f})")
        self.i_report.setText(txt)
        self.flash(txt + "  ·  Ctrl+Z undoes it", 8000)

    # ---- 5. roof -------------------------------------------------------------------
    def _roof_part(self):
        box, body = _fold("8  Roof", "roof", False)
        f = _form(body)
        self.r_kind = QComboBox()
        for k, label in (("hip", "Hip"), ("gable", "Gable"),
                         ("flat", "Flat with parapet"), ("none", "No roof")):
            self.r_kind.addItem(label, k)
        f.addRow("Type", self.r_kind)
        self.r_slope = _spin(5, 75, 25, 1, 1, " °")
        self.r_over = _spin(0, 3, 0.60)
        self.r_par = _spin(0, 3, 1.00)
        self.r_t = _spin(0.05, 1, 0.20)
        f.addRow("Slope", self.r_slope)
        f.addRow("Overhang", self.r_over)
        f.addRow("Parapet (flat)", self.r_par)
        f.addRow("Thickness", self.r_t)
        f.addRow(_btn("Roof over the top level", self._roof, primary=True))
        f.addRow(QLabel("<i>…or a roof level (flat terrace):</i>"))
        row = QHBoxLayout()
        self.rl_h = _spin(0.0, 3, 1.00)
        self.rl_t = _spin(0.05, 1, 0.15)
        row.addWidget(self.rl_h)
        row.addWidget(self.rl_t)
        f.addRow("Parapet height / thickness", row)
        f.addRow(_btn("Make the roof level (slab + parapet)",
                      self._roof_level, "A «Roof» level over the top floor: "
                      "its slab round the outside of the walls below, a "
                      "parapet wall on its edge — also in the Level list"))
        from . import ceilings as CE_
        f.addRow(QLabel("<i>False ceiling (every room of a level):</i>"))
        self.fc_kind = QComboBox()
        for k, lab, *_r in CE_.TYPES:
            self.fc_kind.addItem(lab, k)
        f.addRow("Type", self.fc_kind)
        self.fc_h = _spin(2.0, 8.0, CE_.DEFAULT_H, 0.0254)    # 8'-0"
        self.fc_h.setToolTip("The ceiling's underside over the finished "
                             "floor (8'-0\" by default)")
        f.addRow("Height from floor", self.fc_h)
        row = QHBoxLayout()
        row.addWidget(_btn("This level", lambda: self._ceiling(False),
                           "A false ceiling in every room of the level "
                           "picked at the top (a room can differ: Edit "
                           "properties of the room)", primary=True))
        row.addWidget(_btn("All levels", lambda: self._ceiling(True)))
        row.addWidget(_btn("Remove", self._ceiling_remove))
        f.addRow(row)
        self.lay.addWidget(box)

    def _ceiling(self, all_levels=False):
        from . import ceilings as CE
        doc = self.doc()
        arch = doc["arch"]
        if all_levels:
            lids = [lv["id"] for lv in arch["levels"]
                    if lv["name"].lower() != "roof"
                    and any(w["level"] == lv["id"] for w in arch["walls"])]
        else:
            lid, _lv = self.level()
            if not lid:
                self.flash("Pick a level at the top first")
                return
            lids = [lid]
        for lid in lids:
            CE.set_level(doc, lid, self.fc_kind.currentData(),
                         self.fc_h.value())
        from .host import len_txt
        self.commit(doc, f"False ceiling ({self.fc_kind.currentText()}, "
                         f"{len_txt(self.fc_h.value())} over the floor) on "
                         f"{len(lids)} level(s)")

    def _ceiling_remove(self):
        from . import ceilings as CE
        doc = self.doc()
        lid, _lv = self.level()
        if lid:
            CE.remove_level(doc, lid)
        self.commit(doc, "False ceiling removed")

    def _roof_level(self):
        doc = self.doc()
        why = PJ.add_roof_level(doc, self.rl_h.value(), self.rl_t.value(),
                                self.s_slab_t.value())
        if why:
            self.flash(f"No roof level — {why}")
            return
        if self.commit(doc, f"Roof level made — parapet "
                            f"{self.rl_h.value():.2f} m"):
            roof = next((lv["id"] for lv in self.doc()["arch"]["levels"]
                         if lv["name"] == "Roof"), None)
            if roof:
                self.level_box.setCurrentIndex(self.level_box.findData(roof))

    def _roof(self):
        doc = self.doc()
        kind = self.r_kind.currentData()
        ok = PJ.set_roof(doc, kind, self.r_slope.value(), self.r_over.value(),
                         self.r_par.value(), self.r_t.value())
        if not ok:
            self.flash("No roof — the top level has no walls yet")
            return
        self.commit(doc, "Roof removed" if kind == "none" else
                    f"{self.r_kind.currentText()} roof made")

    # ---- 6. rooms -------------------------------------------------------------------
    def _rooms_part(self):
        box, body = _fold("9  Rooms", "rooms", False)
        v = QVBoxLayout(body)
        row = QHBoxLayout()
        self.r_fin_on = QCheckBox("Floor finishes")
        self.r_fin_on.setToolTip("A finish layer (tiles, screed…) on each "
                                 "room's floor, of its own thickness")
        row.addWidget(self.r_fin_on)
        row.addWidget(QLabel("default"))
        self.r_fin_t = _spin(0.0, 0.3, 0.0508, 0.0127, 3)
        row.addWidget(self.r_fin_t)
        v.addLayout(row)
        row = QHBoxLayout()
        self.r_curt = QCheckBox("Curtains at windows")
        self.r_curt.setToolTip("A rod over each window and two pleated "
                               "curtains drawn open, on the room side (the "
                               "windows between two rooms left bare)")
        row.addWidget(self.r_curt)
        from . import curtains as _CT
        self.r_curt_col = QComboBox()
        for k_, lab_, _c in _CT.COLORS:
            self.r_curt_col.addItem(lab_, k_)
        row.addWidget(self.r_curt_col)
        self.r_curt_len = QComboBox()
        self.r_curt_len.addItem("to the floor", "floor")
        self.r_curt_len.addItem("under the sill", "sill")
        row.addWidget(self.r_curt_len)
        row.addWidget(_btn("Apply", self._curtains,
                           "Curtains on / off, colour and length — every "
                           "level"))
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Wall plaster (each face)"))
        self.r_plaster = _spin(0.0, 0.05, 0.0127, 0.0016, 4)
        self.r_plaster.setToolTip("The plaster coat on both faces of every "
                                  "wall, carried up over the slab's edge — "
                                  "no slab line on the elevations (0 = "
                                  "none)")
        row.addWidget(self.r_plaster)
        row.addWidget(_btn("Apply", self._plaster,
                           "Every wall plastered this thick, each face"))
        v.addLayout(row)
        self.rooms = QTableWidget(0, 4)
        self.rooms.setHorizontalHeaderLabels(["Name", "Area", "Finish",
                                              "Floor ±"])
        self.rooms.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.rooms.verticalHeader().setVisible(False)
        self.rooms.setMinimumHeight(160)
        self.rooms.setToolTip("Type each room's finish thickness and its "
                              "floor sunk (−) / raised (+): 2\", 50mm, "
                              "-6\", -0.15… — then «Save rooms»")
        v.addWidget(self.rooms)
        self.rooms_total = QLabel("")
        v.addWidget(self.rooms_total)
        row = QHBoxLayout()
        row.addWidget(_btn("Save rooms", self._save_rooms,
                           "Names, finishes and floor levels as typed",
                           primary=True))
        row.addWidget(_btn("Default finish → all rooms", self._finish_all,
                           "Every room of this level: the default finish"))
        v.addLayout(row)
        self.lay.addWidget(box)

    def _materials_part(self):
        box, body = _fold("Layers and materials (finishes)", "materials",
                          False)
        v = QVBoxLayout(body)
        v.addWidget(QLabel("<i>The CAD plan's layers and what each one makes "
                           "(change a role, then «Use these roles» and "
                           "«Update from CAD»):</i>"))
        self.ly_table = QTableWidget(0, 3)
        self.ly_table.setHorizontalHeaderLabels(["CAD layer", "Makes", "Lines"])
        self.ly_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.ly_table.verticalHeader().setVisible(False)
        self.ly_table.setMinimumHeight(140)
        v.addWidget(self.ly_table)
        row = QHBoxLayout()
        row.addWidget(_btn("Read layers", self._fill_layers))
        row.addWidget(_btn("Use these roles", self._use_roles))
        v.addLayout(row)
        v.addWidget(QLabel("<i>Materials (name and colour) of what the plugin "
                           "builds:</i>"))
        self.mt_table = QTableWidget(len(PJ.MATERIAL_KINDS), 3)
        self.mt_table.setHorizontalHeaderLabels(["Element", "Material",
                                                 "Colour"])
        self.mt_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.mt_table.verticalHeader().setVisible(False)
        self.mt_table.setMinimumHeight(200)
        self._mt_cols = {}
        for i, (k, label) in enumerate(PJ.MATERIAL_KINDS):
            it = QTableWidgetItem(label)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            it.setData(Qt.UserRole, k)
            self.mt_table.setItem(i, 0, it)
            self.mt_table.setItem(i, 1, QTableWidgetItem(""))
            b = QPushButton("")
            b.clicked.connect(lambda _c=False, k=k: self._pick_colour(k))
            self.mt_table.setCellWidget(i, 2, b)
        v.addWidget(self.mt_table)
        v.addWidget(_btn("Apply materials", self._apply_materials,
                         primary=True))
        self.lay.addWidget(box)

    def _fill_materials(self, doc):
        for i, (k, _l) in enumerate(PJ.MATERIAL_KINDS):
            m = PJ.material_of(doc, k)
            self._mt_cols[k] = list(m["color"])
            it = self.mt_table.item(i, 1)
            if it is not None and not self.mt_table.isPersistentEditorOpen(it):
                it.setText(m["name"])
            b = self.mt_table.cellWidget(i, 2)
            c = [int(255 * x) for x in m["color"]]
            b.setStyleSheet(f"background: rgb({c[0]},{c[1]},{c[2]});")

    def _pick_colour(self, k):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        c = self._mt_cols.get(k, [0.8, 0.8, 0.8])
        q = QColorDialog.getColor(QColor.fromRgbF(*c), self, "Colour")
        if not q.isValid():
            return
        self._mt_cols[k] = [q.redF(), q.greenF(), q.blueF()]
        i = [kk for kk, _l in PJ.MATERIAL_KINDS].index(k)
        b = self.mt_table.cellWidget(i, 2)
        b.setStyleSheet(f"background: {q.name()};")

    def _apply_materials(self):
        doc = self.doc()
        mats = {}
        for i, (k, _l) in enumerate(PJ.MATERIAL_KINDS):
            mats[k] = {"name": self.mt_table.item(i, 1).text().strip(),
                       "color": self._mt_cols.get(k)}
        doc["materials"] = mats
        self.commit(doc, "Materials applied")

    ROLE_CHOICES = ["—", "walls", "doors", "windows", "columns", "beams",
                    "slab", "holes", "text", "plot", "footings", "stairs",
                    "grid", "lift", "parking", "cars", "ramps"]

    def _fill_layers(self):
        path = self.i_file.text().strip()
        if not path:
            self.flash("Pick the CAD file first (part 1)")
            return
        how = self._how()
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            d = cadread.crop(cadread.read(path, how["unit"]), self._region)
        except Exception as e:  # noqa: BLE001
            self.flash(f"Not read — {e}", 8000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        P, _found = PJ.layer_patterns(d, how, PJ.DEFAULTS)
        counts = {}
        for s_ in d["segs"]:
            counts[s_[4]] = counts.get(s_[4], 0) + 1
        names = sorted(set(counts) | set(d["layers"]))
        self.ly_table.setRowCount(len(names))
        for i, n in enumerate(names):
            it = QTableWidgetItem(n)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.ly_table.setItem(i, 0, it)
            cb = QComboBox()
            cb.addItems(self.ROLE_CHOICES)
            role = next((k for k in self.ROLE_CHOICES[1:]
                         if k in P and PJ._match(n, P[k])), "—")
            cb.setCurrentText(role)
            self.ly_table.setCellWidget(i, 1, cb)
            c = QTableWidgetItem(str(counts.get(n, 0)))
            c.setFlags(c.flags() & ~Qt.ItemIsEditable)
            self.ly_table.setItem(i, 2, c)

    def _use_roles(self):
        from . import detect
        roles = {}
        for i in range(self.ly_table.rowCount()):
            n = self.ly_table.item(i, 0).text()
            r = self.ly_table.cellWidget(i, 1).currentText()
            if r != "—":
                roles.setdefault(r, []).append(n)
        if not roles:
            return
        for k, e in self.i_layers.items():
            e.setText(detect.as_patterns(roles.get(k, [])) or "")
        self.i_auto.setChecked(False)          # the roles as chosen
        self._save_prefs()
        self.flash("Roles set (automatic detection off) — «Update from CAD» "
                   "or Import to use them", 8000)

    def _fill_rooms(self, doc):
        lid, _lv = self.level()
        arch = doc["arch"]
        st = doc["settings"]
        self.r_fin_on.blockSignals(True)
        self.r_fin_on.setChecked(bool(st.get("finish_on", True)))
        self.r_fin_on.blockSignals(False)
        self.r_fin_t.setValue(float(st.get("finish_t", 0.0508)))
        self.r_curt.setChecked(bool(st.get("curtains")))
        self.r_plaster.setValue(float(st.get("plaster_t", 0.0127) or 0.0))
        if hasattr(self, "c_autoop"):
            self.c_autoop.blockSignals(True)
            self.c_autoop.setChecked(bool(st.get("auto_openings", True)))
            self.c_autoop.blockSignals(False)
        st_ = getattr(self.vp.scene, "display_style", None)
        for cb, nm in ((getattr(self, "c_edges", None), "edges"),
                       (getattr(self, "c_prof", None), "profiles")):
            if cb is not None and st_ is not None and hasattr(st_, nm):
                cb.blockSignals(True)
                cb.setChecked(bool(getattr(st_, nm)))
                cb.blockSignals(False)
        if hasattr(self, "c_furn"):
            self.c_furn.blockSignals(True)
            self.c_furn.setChecked(bool(st.get("cad_furniture", False)))
            self.c_furn.blockSignals(False)
        if hasattr(self, "t_rkind"):
            self.t_rkind.blockSignals(True)
            self.t_rkind.setCurrentIndex(max(self.t_rkind.findData(
                st.get("terrace_rail_kind", "wall3")), 0))
            self.t_rkind.blockSignals(False)
        if hasattr(self, "x_units"):
            self.x_units.blockSignals(True)
            self.x_units.setCurrentIndex(max(self.x_units.findData(
                st.get("sheet_units", "drawing")), 0))
            self.x_units.blockSignals(False)
        for k, sp in getattr(self, "x_pens", {}).items():
            sp.blockSignals(True)
            sp.setValue(float(st.get("sheet_pen_" + k, sp.value())
                              or sp.value()))
            sp.blockSignals(False)
        k_ = self.r_curt_col.findData(st.get("curtain_color", "cream"))
        self.r_curt_col.setCurrentIndex(max(k_, 0))
        k_ = self.r_curt_len.findData(st.get("curtain_len", "floor"))
        self.r_curt_len.setCurrentIndex(max(k_, 0))
        try:
            rooms = spaces.of_level(arch, lid)
        except Exception:  # noqa: BLE001
            rooms = []
        self._room_rows = rooms
        self.rooms.setRowCount(len(rooms))
        for i, r in enumerate(rooms):
            rec = r.get("rec") or {}
            self.rooms.setItem(i, 0, QTableWidgetItem(r["name"]))
            a = QTableWidgetItem(area_txt(r['area']))
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            self.rooms.setItem(i, 1, a)
            self.rooms.setItem(i, 2, QTableWidgetItem(
                len_txt(PJ.room_finish(doc, rec or None))))
            self.rooms.setItem(i, 3, QTableWidgetItem(
                len_txt(float(rec.get("fz", 0.0) or 0.0))))
        walls = [w for w in arch["walls"] if w["level"] == lid]
        net = sum(r["area"] for r in rooms)
        self.rooms_total.setText(
            f"Net {area_txt(net)}  ·  gross {area_txt(spaces.gross(walls))}"
            if rooms else "No rooms — walls enclose them")

    def _plaster(self):
        doc = self.doc()
        doc["settings"]["plaster_t"] = round(self.r_plaster.value(), 4)
        self.commit(doc, "Wall plaster " + (len_txt(
            doc["settings"]["plaster_t"]) if doc["settings"]["plaster_t"]
            else "off"))

    def _curtains(self):
        doc = self.doc()
        st = doc["settings"]
        st["curtains"] = self.r_curt.isChecked()
        st["curtain_color"] = self.r_curt_col.currentData()
        st["curtain_len"] = self.r_curt_len.currentData()
        self.commit(doc, "Curtains at the windows" if st["curtains"]
                    else "Curtains off")

    def _save_rooms(self):
        doc = self.doc()
        lid, lv = self.level()
        arch = doc["arch"]
        st = doc["settings"]
        st["finish_on"] = self.r_fin_on.isChecked()
        st["finish_t"] = round(self.r_fin_t.value(), 4)
        recs = [r for r in arch["rooms"] if r["level"] != lid]
        bad = []
        for i, room in enumerate(getattr(self, "_room_rows", [])):
            name = self.rooms.item(i, 0).text().strip()
            if not name:
                continue
            old = room.get("rec") or {}
            rec = {"id": old.get("id", ""), "level": lid,
                   "x": room["at"][0], "y": room["at"][1], "name": name}
            for col, key in ((2, "finish"), (3, "fz")):
                it = self.rooms.item(i, col)
                txt = it.text().strip() if it else ""
                if not txt:
                    continue
                v = parse_len(txt)
                if v is None:
                    bad.append(f"{name}: «{txt}»")
                    continue
                if key == "finish" and abs(v - st["finish_t"]) < 1e-4 \
                        and old.get("finish") is None:
                    continue                  # the default: follows it
                rec[key] = round(v, 4)
            recs.append(rec)
        arch["rooms"] = M._rooms(recs, {x["id"] for x in arch["levels"]})
        if bad:
            self.flash("Not a length — " + "; ".join(bad[:4]), 9000)
        self.commit(doc, f"Rooms of «{lv['name']}»: names, finishes and "
                         f"floor levels")

    def _finish_all(self):
        doc = self.doc()
        lid, lv = self.level()
        st = doc["settings"]
        st["finish_on"] = True
        st["finish_t"] = round(self.r_fin_t.value(), 4)
        for r in doc["arch"]["rooms"]:
            if r["level"] == lid:
                r.pop("finish", None)
        self.commit(doc, f"Rooms of «{lv['name']}»: finish "
                         f"{len_txt(st['finish_t'])}")

    # ---- 7. the selected element ------------------------------------------------
    def _selected_part(self):
        box, body = _fold("10  Selected element", "selected")
        self.sel_box = body
        v = QVBoxLayout(body)
        self.sel_title = QLabel("<i>Click a wall, door, window, column, beam, "
                                "slab, footing or roof in the model</i>")
        self.sel_title.setWordWrap(True)
        v.addWidget(self.sel_title)
        self.stf_box = QGroupBox("Flights, rotation and landings "
                                 "(this stair)")
        self.stf_box.setToolTip(
            "Lay the stair out by hand where the CAD plan was read wrong: "
            "how many flights, the risers in each, the way each flight "
            "turns off the landing before it, and the whole stair turned "
            "round its first step. The landings are made again to fit "
            "each turn and the well in the slab is cut again. Kept when "
            "the stairs are made again from the CAD.")
        self.stf_lay = QVBoxLayout(self.stf_box)
        self.stf_box.setVisible(False)
        v.addWidget(self.stf_box)
        self.sel_form_host = QWidget()
        self.sel_form = QFormLayout(self.sel_form_host)
        v.addWidget(self.sel_form_host)
        row = QHBoxLayout()
        self.sel_apply = _btn("Apply", self._apply_selected, primary=True)
        self.sel_flip = _btn("Flip hinge", self._flip)
        self.sel_del = _btn("Delete", self._delete_selected)
        self.sel_left = _btn("◀ 0.1", lambda: self._nudge_op(-0.1),
                             "Move the door / window along its wall")
        self.sel_right = _btn("0.1 ▶", lambda: self._nudge_op(0.1),
                              "Move the door / window along its wall")
        for b in (self.sel_apply, self.sel_flip, self.sel_del,
                  self.sel_left, self.sel_right):
            row.addWidget(b)
            b.setEnabled(False)
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(_btn("Selected walls → curtain wall",
                            lambda: self.convert_selected_walls("curtain"),
                            "Glass on an aluminium grid (mullions / transoms "
                            "spacing: «Selected element»)"))
        row2.addWidget(_btn("→ solid wall",
                            lambda: self.convert_selected_walls("solid")))
        v.addLayout(row2)
        v.addWidget(QLabel("<i>Right-click an element in the model: edit "
                           "its properties there, change a door's type, "
                           "head or frame, make a wall a curtain wall.</i>"))
        self._sel_widgets = {}
        self.lay.addWidget(box)

    def _selected_all(self) -> list:
        """[(kind, id)] of every CAD2IngeTrazo element selected."""
        out = []
        for e in list(self.vp.scene.selection):
            for g in (e, getattr(e, "owner", None)):
                tag = PJ.tag_of(g) if g is not None else None
                if tag and tag["type"] != "symbols":
                    k = (tag["type"], tag["id"])
                    if k not in out:
                        out.append(k)
                    break
        return out

    def _extend_to_selected(self, slab_id, wall_ids):
        from . import slabedges as SE
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id)
        if slab is None:
            self.flash("That slab is gone — pick it again")
            return
        n = SE.extend_to_selected(doc, slab, wall_ids)
        self._extend_pick = None
        if not n:
            self.flash("The slab already reaches those walls (or they are "
                       "more than 12 m away)")
            return
        self.commit(doc, f"Slab extended to {n} selected wall(s)")

    def _start_extend_pick(self, slab_id):
        self._extend_pick = slab_id
        self.flash("Now select the walls the slab should reach (Ctrl+click "
                   "for several), then right-click one ▸ CAD2IngeTrazo ▸ "
                   "«Extend the slab to the selected walls»", 15000)

    def _selected(self, fresh=False):
        """(kind, id) of the CAD2IngeTrazo element selected, or None. A
        whole floor selected («Floors as groups»): the element of that
        floor under the mouse — so a slab, a wall… keeps its commands
        (extend, shafts, edit) without opening the floor group first."""
        floor = False
        for e in list(self.vp.scene.selection):
            for g in (e, getattr(e, "owner", None)):
                tag = PJ.tag_of(g) if g is not None else None
                if tag and tag["type"] == "levelgroup":
                    floor = True
                    continue
                if tag and tag["type"] != "symbols":
                    self._sel_seg = tag.get("seg")
                    return tag["type"], tag["id"]
        if floor:
            # the element under the mouse when the floor was picked (a
            # right-click: where it is now)
            key_ = tuple(sorted(id(e) for e in self.vp.scene.selection))
            memo = getattr(self, "_floor_memo", None)
            if fresh or memo is None or memo[0] != key_:
                hit = self._under_cursor()
                if hit is None and memo is not None and memo[0] == key_:
                    hit = memo[1]
                self._floor_memo = (key_, hit)
            hit = self._floor_memo[1]
            if hit is not None:
                self._sel_seg = hit[2]
                return hit[0], hit[1]
        self._sel_seg = None
        return None

    def _under_cursor(self):
        """(kind, id, seg) of the CAD2IngeTrazo element under the mouse in
        the 3D view (inside the floor groups too), or None."""
        try:
            from PySide6.QtGui import QCursor
            vp = self.vp
            pos = vp.mapFromGlobal(QCursor.pos())
            if not vp.rect().contains(pos):
                return None
            pick = getattr(vp, "pick_face_placement", None)
            if pick is None:
                return None
            face, pl = pick(float(pos.x()), float(pos.y()))
            if face is None or pl is None:
                return self._ray_hit(pos)
            tag = PJ.tag_of(pl)
            if tag and tag["type"] not in ("symbols", "levelgroup"):
                return tag["type"], tag["id"], tag.get("seg")
            mesh = getattr(pl, "mesh", None)
            want = getattr(pl, "xform", None)
            best = None
            for g, xf in _walk_world(vp.scene.groups):
                if getattr(g, "mesh", None) is not mesh:
                    continue
                t = PJ.tag_of(g)
                if not t or t["type"] in ("symbols", "levelgroup"):
                    continue
                d = _xf_gap(xf, want)
                if best is None or d < best[0]:
                    best = (d, (t["type"], t["id"], t.get("seg")))
            return best[1] if best else self._ray_hit(pos)
        except Exception:  # noqa: BLE001
            log_error("panel._under_cursor")
            return None

    def _ray_hit(self, pos):
        """(kind, id, seg) of the CAD2IngeTrazo element the mouse ray meets
        first — our own ray cast through the elements' triangles (inside
        the floor groups too)."""
        import numpy as np
        vp = self.vp
        o, d = vp._pixel_to_ray(float(pos.x()), float(pos.y()))
        if o is None or d is None:
            return None
        sc = vp.scene
        key = (id(sc.groups), getattr(sc, "version", 0), len(sc.groups))
        cache = getattr(self, "_tri_cache", None)
        if cache is None or cache[0] != key:
            tris, owners, tags = [], [], []
            for g, xf in _walk_world(sc.groups):
                t = PJ.tag_of(g)
                m = getattr(g, "mesh", None)
                if not t or m is None or t["type"] in ("symbols",
                                                      "levelgroup"):
                    continue
                if getattr(g, "hidden", False):
                    continue
                k = len(tags)
                tags.append((t["type"], t["id"], t.get("seg")))
                for f in m.faces:
                    try:
                        for a, b, c in f.triangulate():
                            pts = []
                            for q in (a, b, c):
                                if xf is not None:
                                    q = xf.map(q)
                                pts.append((q.x(), q.y(), q.z()))
                            tris.append(pts)
                            owners.append(k)
                    except Exception:  # noqa: BLE001
                        continue
            cache = (key, np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3),
                     np.asarray(owners, dtype=np.int64), tags)
            self._tri_cache = cache
        _k, T, own, tags = cache
        if not len(T):
            return None
        O = np.array([o.x(), o.y(), o.z()])
        D = np.array([d.x(), d.y(), d.z()])
        v0, e1, e2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
        h = np.cross(D, e2)
        a = np.einsum("ij,ij->i", e1, h)
        ok = np.abs(a) > 1e-12
        f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
        sv = O - v0
        u = f * np.einsum("ij,ij->i", sv, h)
        q = np.cross(sv, e1)
        v = f * (q @ D)
        t = f * np.einsum("ij,ij->i", e2, q)
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
        if not hit.any():
            return None
        i = int(np.argmin(np.where(hit, t, np.inf)))
        return tags[int(own[i])]

    def _watch_selection(self):
        try:
            sel = self._selected()
        except Exception:  # noqa: BLE001
            sel = None
        if sel == self._sel_key:
            return
        self._sel_key = sel
        self._fill_selected()

    def _fill_selected(self):
        while self.sel_form.rowCount():
            self.sel_form.removeRow(0)
        self._sel_widgets = {}
        sel = self._sel_key
        rec = PJ.find_record(self.doc(), *sel) if sel else None
        for b in (self.sel_apply, self.sel_del):
            b.setEnabled(rec is not None)
        self.sel_flip.setEnabled(rec is not None and (
            sel[0] == "ramp" or (sel[0] == "opening"
                                 and rec.get("kind") == "door")))
        for b in (self.sel_left, self.sel_right):
            b.setEnabled(rec is not None and sel[0] == "opening")
        if rec is None:
            self.sel_title.setText("<i>Click a wall, door, window, column, "
                                   "beam, slab, footing or roof in the "
                                   "model</i>")
            return
        kind = sel[0] if sel[0] != "opening" else rec["kind"]
        self.sel_title.setText(f"<b>{rec.get('name', kind)}</b>")
        if sel[0] == "opening" and rec.get("kind") in ("door", "window"):
            from .engine import structure as S_
            rec = dict(rec)                  # the frame's own size shown
            _l, _c, fw_, fd_ = S_.frame_size(rec)
            rec.setdefault("frame_w", round(fw_, 4))
            rec.setdefault("frame_d", round(fd_, 4))
        self._sel_widgets = self._build_fields(self.sel_form, sel[0], rec)
        try:
            self._fill_stair_flights(rec if sel[0] in ("stair", "stairrail")
                                     else None)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_stair_flights")

    # ---- a stair's flights, turns and landings by hand ------------------------
    def _fill_stair_flights(self, st, counts=None, turns=None, rot=None,
                            ui=None):
        """The flights / turns / rotation controls of stair ``st`` into
        ``ui`` ({"lay", "box"}; the panel's own box by default)."""
        if ui is None:
            ui = getattr(self, "_stf_ui", None)
            if ui is None:
                ui = self._stf_ui = {"lay": self.stf_lay, "box": self.stf_box}
        lay, box = ui["lay"], ui.get("box")
        while lay.count():
            it = lay.takeAt(0)
            w_ = it.widget()
            if w_ is not None:
                w_.deleteLater()
            elif it.layout() is not None:
                l_ = it.layout()
                while l_.count():
                    i2 = l_.takeAt(0)
                    if i2.widget() is not None:
                        i2.widget().deleteLater()
        ui["state"] = None
        if st is None:
            if box is not None:
                box.setVisible(False)
            return
        from . import stairs as ST
        flights, _l = ST.as_flights(st)
        if not flights:
            if box is not None:
                box.setVisible(False)
            return
        if counts is None:
            counts = [len(f["lines"]) for f in flights]
        if turns is None:
            turns = list(st.get("turns") or ST.flight_turns(st))
        turns = (list(turns) + ["right"] * len(counts))[:len(counts) - 1]
        if rot is None:
            rot = float(st.get("rot") or 0.0)
        state = {"id": st["id"]}
        row = QHBoxLayout()
        row.addWidget(QLabel("Flights"))
        nf = QSpinBox()
        nf.setRange(1, 6)
        nf.setValue(len(counts))
        nf.setToolTip("The number of flights; the risers shared out again "
                      "(the storey height stays)")
        row.addWidget(nf)
        row.addWidget(QLabel(f"  risers in all: {sum(counts)}"))
        row.addStretch(1)
        lay.addLayout(row)

        def renum(n, _ui=ui):
            stt = _ui["state"]
            tot = sum(c.value() for c in stt["counts"])
            n = max(1, int(n))
            base = [tot // n + (1 if i < tot % n else 0) for i in range(n)]
            cur_t = [c.currentData() for c in stt["turns"]]
            self._fill_stair_flights(
                PJ.find_record(self.doc(), "stair", stt["id"]), base,
                cur_t, stt["rot"].value(), _ui)
        nf.valueChanged.connect(renum)
        cs, ts = [], []
        for i, n in enumerate(counts):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"Flight {i + 1}"))
            sp = QSpinBox()
            sp.setRange(2, 40)
            sp.setValue(int(n))
            sp.setSuffix(" risers")
            row.addWidget(sp)
            cs.append(sp)
            if i > 0:
                cb = QComboBox()
                for k, lab in ST.TURNS:
                    cb.addItem(lab, k)
                cb.setCurrentIndex(max(cb.findData(turns[i - 1]), 0))
                cb.setToolTip("Flight rotation: how this flight turns off "
                              "the landing before it (seen walking up); the "
                              "landing and the railing follow")
                row.addWidget(cb)
                ts.append(cb)
            else:
                row.addWidget(QLabel("from the floor"))
            row.addStretch(1)
            lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Rotate whole stair"))
        rs = QDoubleSpinBox()
        rs.setRange(-360.0, 360.0)
        rs.setDecimals(1)
        rs.setSingleStep(15.0)
        rs.setSuffix(" °")
        rs.setValue(float(rot))
        rs.setToolTip("Degrees, anticlockwise, round the middle of the first "
                      "step")
        row.addWidget(rs)
        row.addWidget(_btn("⟲ 90°", lambda _ui=ui: (
            rs.setValue(rs.value() + 90.0), self._stair_relay(_ui))))
        row.addWidget(_btn("⟳ 90°", lambda _ui=ui: (
            rs.setValue(rs.value() - 90.0), self._stair_relay(_ui))))
        row.addStretch(1)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_btn("Apply flights", lambda _ui=ui:
                           self._stair_relay(_ui),
                           "Lay the stair out as set above: the landings and "
                           "the railings follow the flights, the slab's "
                           "opening (and its railing upstairs) is made again",
                           primary=True))
        row.addWidget(_btn("Mirror turns", lambda _ui=ui:
                           self._stair_mirror(_ui),
                           "Every left turn made right and every right "
                           "turn left"))
        row.addWidget(_btn("Back to the CAD", lambda _ui=ui:
                           self._stair_unrelay(_ui),
                           "Forget the turns set by hand: the stair read "
                           "from the CAD plan again"))
        lay.addLayout(row)
        state.update(counts=cs, turns=ts, rot=rs)
        ui["state"] = state
        if box is not None:
            box.setVisible(True)

    def _stair_relay(self, ui=None):
        from . import stairs as ST
        ui = ui or getattr(self, "_stf_ui", None) or {}
        f = ui.get("state")
        if not f:
            return
        doc = self.doc()
        counts = [c.value() for c in f["counts"]]
        turns = [c.currentData() for c in f["turns"]]
        try:
            new = ST.restair(doc, f["id"], turns, f["rot"].value(), counts)
        except Exception as e:  # noqa: BLE001
            log_error("panel._stair_relay")
            self.flash(f"Stair not laid out — {e}", 8000)
            return
        names = dict(ST.TURNS)
        what = ", ".join(names.get(t, t).split(" (")[0].lower()
                         for t in turns) or "one flight"
        if self.commit(doc, f"Stair laid out: {len(counts)} flight"
                       f"{'s' if len(counts) > 1 else ''} ({what}), "
                       f"rotated {f['rot'].value():.0f}°, "
                       f"{new['risers']} risers of "
                       f"{new['rise'] * 1000:.0f} mm"):
            self._reselect(("stair", f["id"]))
            if ui.get("box") is None:          # a dialog: its controls again
                self._fill_stair_flights(
                    PJ.find_record(self.doc(), "stair", f["id"]), ui=ui)

    def _stair_mirror(self, ui=None):
        ui = ui or getattr(self, "_stf_ui", None) or {}
        f = ui.get("state")
        if not f:
            return
        sw = {"left": "right", "right": "left", "uleft": "uright",
              "uright": "uleft"}
        for cb in f["turns"]:
            k = cb.currentData()
            cb.setCurrentIndex(max(cb.findData(sw.get(k, k)), 0))
        self._stair_relay(ui)

    def _stair_unrelay(self, ui=None):
        from . import stairs as ST
        ui = ui or getattr(self, "_stf_ui", None) or {}
        f = ui.get("state")
        if not f:
            return
        doc = self.doc()
        ST.unstair(doc, f["id"])
        PJ.store_only(self.vp, doc)
        self._stairs()

    def stair_flights_dialog(self, sid=None):
        """The stair's flights, their rotation (turns) and the whole
        stair's rotation, in a dialog."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        if sid is None:
            sel = self._sel_key or self._selected()
            if not sel or sel[0] not in ("stair", "stairrail"):
                doc = self.doc()
                lid = self.level()[0]
                mine = [s_ for s_ in doc.get("stairs") or []
                        if s_["level"] == lid] or doc.get("stairs") or []
                if not mine:
                    self.flash("No stair in the model — «Stairs» first")
                    return
                sid = mine[0]["id"]
            else:
                sid = sel[1]
        st = PJ.find_record(self.doc(), "stair", sid)
        if st is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{st.get('name') or 'Stair'} — flights, "
                           "rotation and landings")
        v = QVBoxLayout(dlg)
        doc = self.doc()
        others = [s_ for s_ in doc.get("stairs") or []]
        if len(others) > 1:
            row = QHBoxLayout()
            row.addWidget(QLabel("Stair"))
            pick = QComboBox()
            names = {lv["id"]: lv["name"] for lv in doc["arch"]["levels"]}
            for i, s_ in enumerate(others):
                pick.addItem(f"Stair {i + 1} · {names.get(s_['level'], '')}",
                             s_["id"])
            pick.setCurrentIndex(max(pick.findData(sid), 0))
            row.addWidget(pick)
            row.addStretch(1)
            v.addLayout(row)
        host = QVBoxLayout()
        v.addLayout(host)
        ui = {"lay": host, "box": None}
        self._fill_stair_flights(st, ui=ui)
        if len(others) > 1:
            pick.currentIndexChanged.connect(
                lambda _i: self._fill_stair_flights(
                    PJ.find_record(self.doc(), "stair", pick.currentData()),
                    ui=ui))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.setModal(False)
        dlg.show()
        self._stf_dlg = dlg

    def _build_fields(self, form, kind, rec) -> dict:
        """The element's fields into ``form``: {key: (type, widget)}."""
        widgets = {}
        if kind in ("stair", "stairrail"):   # its own values, else defaults
            from . import stairs as ST
            rec = dict(rec, **ST.eff(rec, self.doc()["settings"]))
        if kind == "wall":                 # attached to the slabs or not
            rec = dict(rec, top_att="slab" if rec.get("height", "level") ==
                       "level" else "free",
                       bot_att="slab" if abs(float(rec.get("base", 0.0) or
                                                   0.0)) < 1e-4 else "free")
        for key, label, typ, opt in FIELDS.get(kind, []):
            if typ == "choice":
                w = QComboBox()
                w.addItems([CHOICE_LABELS.get(str(o), str(o)) for o in opt])
                w._opts = list(opt)
                if rec.get(key) in opt:
                    w.setCurrentIndex(list(opt).index(rec[key]))
            elif typ == "height":
                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(0, 0, 0, 0)
                cb = QCheckBox("Full storey")
                sp = _spin(opt[0], opt[1], 3.0)
                full = rec.get(key, "level") == "level"
                cb.setChecked(full)
                if not full:
                    sp.setValue(float(rec[key]))
                sp.setEnabled(not full)
                cb.toggled.connect(lambda on, s=sp: s.setEnabled(not on))
                h.addWidget(cb)
                h.addWidget(sp)
                w._cb, w._sp = cb, sp
            elif typ == "pct":
                w = QDoubleSpinBox()
                w.setRange(opt[0], opt[1])
                w.setDecimals(1)
                w.setSingleStep(0.5)
                w.setSuffix(" %")
                if key == "slope" and kind == "ramp":
                    run = float(rec.get("run") or 0.0) or 1.0
                    w.setValue(abs(float(rec.get("rise", 0.0))) / run * 100)
                else:
                    w.setValue(float(rec.get(key, 0.0) or 0.0))
                w._start = w.value()
            elif typ == "text":
                w = QLineEdit(str(rec.get(key, "") or ""))
            elif typ == "info":
                txt = ""
                if kind == "room" and key == "size":
                    sz = PJ.room_size(self.doc(), rec)
                    if sz:
                        from .host import area_txt
                        txt = f"{len_txt(sz[0])} × {len_txt(sz[1])}" \
                            f"  ({area_txt(sz[0] * sz[1])} bounding)"
                w = QLabel(txt or "—")
            elif typ == "int":
                from PySide6.QtWidgets import QSpinBox
                w = QSpinBox()
                w.setRange(int(opt[0]), int(opt[1]))
                w.setValue(int(rec.get(key, opt[0]) or opt[0]))
            else:
                suffix = " °" if typ == "deg" else " m"
                val = rec.get(key, 0.0)
                if kind == "room" and key == "finish" and val is None:
                    val = PJ.room_finish(self.doc(), None)
                if kind == "room" and key == "ceiling_h" and not val:
                    from . import ceilings as CE_
                    val = float(((self.doc().get("ceilings") or {}).get(
                        rec.get("level")) or {}).get("h", CE_.DEFAULT_H))
                w = _spin(opt[0], opt[1], float(val or 0.0),
                          1.0 if typ == "deg" else 0.05, 2, suffix)
                if kind == "room" and key == "finish":
                    w.setSingleStep(0.0127)        # ½"
            form.addRow(label, w)
            widgets[key] = (typ, w)
        return widgets

    def _apply_selected(self, widgets=None, sel=None):
        sel = sel or self._sel_key
        if not sel:
            return
        widgets = widgets if widgets is not None else self._sel_widgets
        doc = self.doc()
        rec = PJ.find_record(doc, *sel)
        if rec is None:
            return
        new = dict(rec)
        for key, (typ, w) in widgets.items():
            if typ == "info":
                continue
            if typ == "choice":
                new[key] = w._opts[w.currentIndex()]
            elif typ == "height":
                new[key] = "level" if w._cb.isChecked() else w._sp.value()
            elif typ == "text":
                new[key] = w.text().strip() or rec.get(key, "")
            elif typ == "pct":
                new[key] = round(w.value(), 2)
                new["_pct_changed_" + key] = abs(w.value() - w._start) > 0.05
            else:
                new[key] = round(w.value(), 4)
        if sel[0] == "opening":          # the frame's size left at its
            from .engine import structure as S_     # material's: not set
            base_ = {k_: v_ for k_, v_ in new.items()
                     if k_ not in ("frame_w", "frame_d")}
            _l, _c, fw_, fd_ = S_.frame_size(base_)
            for k_, dv_ in (("frame_w", fw_), ("frame_d", fd_)):
                if k_ in new and k_ not in rec and \
                        abs(float(new[k_]) - dv_) < 5e-4:
                    new.pop(k_)
        # a ramp's slope typed: its climb from its length (the way it
        # goes kept) — unless the climb itself was typed
        if sel[0] == "ramp" and new.pop("_pct_changed_slope", False) and \
                abs(float(new.get("rise", 0)) - float(rec.get("rise", 0))) \
                < 1e-4:
            run = float(rec.get("run") or 0.0)
            sign = -1.0 if float(rec.get("rise", 0)) < 0 else 1.0
            new["rise"] = round(sign * run * float(new["slope"]) / 100.0, 4)
        for k_ in [k_ for k_ in new if k_.startswith("_pct_changed_")]:
            new.pop(k_)
        new.pop("slope", None)
        if sel[0] == "wall":
            new = PJ.wall_attach(doc, rec, new.pop("top_att", None),
                                 new.pop("bot_att", None), new)
        if sel[0] == "opening" and new["kind"] != rec.get("kind"):
            # a door made a window (or back, or an opening one): that
            # type's own height, sill and type
            new = dict(PJ.opening_as(new, new["kind"], doc["settings"]),
                       w=new["w"], pos=new["pos"])
        if sel[0] == "opening" and new["kind"] == "door":
            new["sill"] = 0.0
        if sel[0] == "stair":           # riser / tread / steps re-laid
            from . import stairs as ST_
            new = ST_.redesign(rec, new)
        if sel[0] == "opening":
            PJ.fit_head(new)            # a transom / arch: a full leaf under
        why = PJ.check_record(doc, sel[0], new) if sel[0] != "opening" else \
            PJ.check_record(doc, "opening", dict(new, id=rec["id"]))
        if why:
            self.flash(f"Not changed — {why}")
            return
        if sel[0] == "ramp":
            PJ._ramp_uncut(doc, rec["level"])
        to_cw = sel[0] == "wall" and new.get("type") == "curtain" and \
            rec.get("type") != "curtain"
        rec.update(new)
        for k_ in ("mat_floor", "mat_wall", "mat_ceil"):
            if rec.get(k_) == "none":
                rec.pop(k_, None)
        if sel[0] == "room":      # the other rooms selected: same materials
            for k2, i2 in self._selected_all():
                if k2 != "room" or i2 == sel[1]:
                    continue
                r2 = PJ.room_record(doc, i2)
                if r2 is None:
                    continue
                for k_ in ("mat_floor", "mat_wall", "mat_ceil"):
                    if rec.get(k_):
                        r2[k_] = rec[k_]
                    else:
                        r2.pop(k_, None)
        if to_cw:                 # its windows go, its doors fitted
            PJ.to_curtain(doc, [rec["id"]])
        if sel[0] == "ramp":
            PJ._ramp_cut(doc, rec["level"])
        if self.commit(doc, f"{rec.get('name', sel[0])} changed"):
            self._reselect(sel)

    def _flip(self):
        sel = self._sel_key
        doc = self.doc()
        rec = PJ.find_record(doc, *sel) if sel else None
        if rec is None:
            return
        if sel[0] == "ramp":                 # the low end to the other end
            rec["sections"] = [[b, a] for a, b in reversed(rec["sections"])]
            if self.commit(doc, f"{rec['name']}: start at the other end"):
                self._reselect(sel)
            return
        rec["swing"] = "right" if rec.get("swing") == "left" else "left"
        if self.commit(doc, "Door hinge flipped"):
            self._reselect(sel)

    def _nudge_op(self, ds):
        """The selected door / window moved along its wall (with its
        opening in the wall)."""
        sel = self._sel_key
        doc = self.doc()
        rec = PJ.find_record(doc, *sel) if sel else None
        if rec is None or sel[0] != "opening":
            return
        new = dict(rec, pos=round(float(rec["pos"]) + ds, 4))
        why = PJ.check_record(doc, "opening", new)
        if why:
            self.flash(f"Not moved — {why}")
            return
        rec.update(new)
        if self.commit(doc, f"{rec['name']} moved {ds:+.2f} m"):
            self._reselect(sel)

    def _follow_moves(self, doc) -> bool:
        """A door / window moved with the Move tool: its opening in the
        wall moved with it (along the wall), the wall rebuilt."""
        tool = getattr(self.vp, "active_tool", None)
        pd = getattr(tool, "_preview_delta", None)
        if pd is not None and pd.length() > 1e-9:
            return False                       # still moving
        seen = getattr(self, "_moves_seen", None)
        if seen is None:
            seen = self._moves_seen = {}
        try:                           # furniture moved / turned: kept
            if PJ.moved_furniture(self.vp.scene, doc):
                PJ.store_only(self.vp, doc)
        except Exception:  # noqa: BLE001
            log_error("panel._follow_moves furniture")
        try:
            moves = PJ.moved_openings(self.vp.scene, doc, seen)
        except Exception:  # noqa: BLE001
            log_error("panel._follow_moves")
            return False
        done = []
        for rec, pos in moves:
            new = dict(rec, pos=pos)
            why = PJ.check_record(doc, "opening", new)
            if why:
                self.flash(f"{rec['name']} not moved — {why}")
                continue
            rec.update(new)
            done.append(rec)
        if not done:
            if moves:                          # back where the record says
                self.commit(doc, "Opening kept in place")
                return True
            return False
        name = done[0]["name"] if len(done) == 1 else f"{len(done)} openings"
        if self.commit(doc, f"{name} moved with its opening"):
            if len(done) == 1:
                self._reselect(("opening", done[0]["id"]))
        return True

    # ---- right-click: edit the element where it is ------------------------------
    def _selected_all(self):
        """Every CAD2IngeTrazo element selected: [(kind, id)] (a whole
        floor selected: the element of it under the mouse)."""
        out = []
        floor = False
        for e in list(self.vp.scene.selection):
            for g in (e, getattr(e, "owner", None)):
                tag = PJ.tag_of(g) if g is not None else None
                if tag and tag["type"] == "levelgroup":
                    floor = True
                    continue
                if tag and tag["type"] != "symbols" and \
                        (tag["type"], tag["id"]) not in out:
                    out.append((tag["type"], tag["id"]))
        if floor and not out:
            one = self._selected()
            if one:
                out.append(one)
        return out

    def context_menu(self, menu) -> None:
        """The right-click menu of a CAD2IngeTrazo element: its fields in a
        dialog, its quick changes, delete."""
        try:            # a rectangle drawn on a slab: open / close a shaft
            drawn = self._drawn_outlines()
        except Exception:  # noqa: BLE001
            drawn = []
        if drawn:
            m_ = menu.addMenu("CAD2IngeTrazo · Shaft (the rectangle drawn)")
            m_.addAction("Open a shaft here (this floor's slab)",
                         lambda d_=drawn: self._shaft_drawn(d_, False))
            m_.addAction("Open a shaft through every floor",
                         lambda d_=drawn: self._shaft_drawn(d_, True))
            m_.addAction("Close the shaft / opening here",
                         lambda d_=drawn: self._shaft_close_drawn(d_))
        sel = self._selected(fresh=True)
        if not sel:
            return
        doc = self.doc()
        rec = PJ.find_record(doc, *sel)
        if rec is None:
            return
        if sel != self._sel_key:
            self._sel_key = sel
            try:
                self._fill_selected()
            except Exception:  # noqa: BLE001
                pass
        self._sel_key = sel
        name = rec.get("name") or {"stair": "Stair",
                                   "stairrail": "Stair railing"}.get(
            sel[0], sel[0])
        menu.addSeparator()
        sub = menu.addMenu(f"CAD2IngeTrazo · {name}")
        try:                 # a slab and walls selected: the slab out to them
            all_ = self._selected_all()
            walls_ = [i for k, i in all_ if k == "wall"]
            slabs_ = [i for k, i in all_ if k == "slab"]
            target = slabs_[0] if slabs_ else getattr(self, "_extend_pick",
                                                      None)
            if walls_ and target:
                sub.addAction(f"Extend the slab to the selected walls "
                              f"({len(walls_)})",
                              lambda t=target, ws=list(walls_):
                              self._extend_to_selected(t, ws))
                sub.addSeparator()
        except Exception:  # noqa: BLE001
            log_error("panel extend-to-selected menu")
        if sel[0] in ("stair", "stairrail"):
            sub.addAction("Flights, rotation and landings…",
                          lambda: self.stair_flights_dialog(sel[1]))
        sub.addAction("Edit properties…", lambda: self.edit_dialog(sel))
        if sel[0] == "wall" and rec.get("type") == "curtain":
            sub.addAction("Add door in this curtain wall…",
                          lambda: self.cw_door_dialog(sel[1]))
        try:
            from . import components as CP
            tk = CP.key_of(doc, sel[0], rec)
            if tk:
                t = CP.catalogue(doc).get(tk)
                if t:
                    n = len(t["items"])
                    sub.addAction(f"Select all «{t['mark']}» ({n})",
                                  lambda k=tk: self.select_type([k]))
                    sub.addAction(f"Edit type «{t['mark']}» — all {n}…",
                                  lambda k=tk: self.edit_type(k))
                    sub.addAction(f"Replace «{t['mark']}» with a library "
                                  "component…",
                                  lambda k=tk: self.replace_type_dialog([k]))
                    mm = sub.addMenu(f"Mirror «{t['mark']}» — all {n}")
                    mir = t.get("mirror") or {}
                    for ax, lab_ in (("x", "Left ↔ right"),
                                     ("y", "Front ↔ back")):
                        a_ = mm.addAction(lab_, lambda k=tk, a=ax:
                                          self.mirror_type(k, a))
                        a_.setCheckable(True)
                        a_.setChecked(bool(mir.get(ax)))
        except Exception:  # noqa: BLE001
            log_error("panel.context_menu types")
        if sel[0] == "opening":
            from .engine import structure as S_
            mc = sub.addMenu("Make it a…")
            for k_, lab_ in (("door", "Door"), ("window", "Window"),
                             ("void", "Plain opening (no door / window)")):
                a_ = mc.addAction(lab_, lambda k_=k_: self._convert_opening(
                    sel, k_))
                a_.setCheckable(True)
                a_.setChecked(rec.get("kind") == k_)
            if rec["kind"] == "door":
                types = S_.DOOR_STYLES
            else:
                types = S_.WINDOW_STYLES
            mt = sub.addMenu("Type")
            for k, label in types:
                a = mt.addAction(label, lambda k=k: self._quick(sel, style=k))
                a.setCheckable(True)
                a.setChecked((rec.get("style") or "") == k)
            mh = sub.addMenu("Head")
            for k, label in S_.HEADS:
                a = mh.addAction(label, lambda k=k: self._quick(sel, head=k))
                a.setCheckable(True)
                a.setChecked((rec.get("head") or "flat") == k)
            mf = sub.addMenu("Frame")
            for k, label in [("auto", "Auto")] + [
                    (k, v[0]) for k, v in S_.FRAMES.items()]:
                a = mf.addAction(label, lambda k=k: self._quick(sel, frame=k))
                a.setCheckable(True)
                a.setChecked((rec.get("frame") or "auto") == k)
            if rec["kind"] == "door":
                ml = sub.addMenu("Leaves")
                for k, label in S_.LEAVES:
                    a = ml.addAction(label, lambda k=k: self._quick(
                        sel, leaves=k))
                    a.setCheckable(True)
                    a.setChecked(S_.leaves_of(rec) == k)
                sub.addAction("Flip hinge", self._flip)
                sub.addAction("Opens to the other side", lambda: self._quick(
                    sel, face=-int(rec.get("face", 1) or 1)))
            if rec["kind"] in ("window", "void"):
                ops = [i for k, i in self._selected_all() if k == "opening"] \
                    or [sel[1]]
                nsel = len(ops)
                sub.addAction("Replace with wall (close the opening)" if nsel
                              == 1 else f"Replace {nsel} openings with wall",
                              lambda o=ops: self.close_openings(o))
                try:
                    from . import components as CP_
                    tk_ = CP_.key_of(doc, "opening", rec)
                    t_ = CP_.catalogue(doc).get(tk_) if tk_ else None
                    if t_ and len(t_["items"]) > 1:
                        sub.addAction(
                            f"Replace every «{t_['mark']}» with wall "
                            f"({len(t_['items'])})",
                            lambda t=t_: self.close_openings(
                                [i for _k, i, _l in t["items"]]))
                except Exception:  # noqa: BLE001
                    log_error("panel.context_menu close")
            sub.addAction("Move ◀ 0.1 m", lambda: self._nudge_op(-0.1))
            sub.addAction("Move ▶ 0.1 m", lambda: self._nudge_op(0.1))
        if sel[0] == "wall":
            walls = [i for k, i in self._selected_all() if k == "wall"] \
                or [sel[1]]
            n = len(walls)
            what = f"{n} walls" if n > 1 else "the wall"
            if rec.get("kind", "line") == "line":
                sub.addAction("Edit part of this wall…",
                              lambda: self.split_wall_dialog(sel[1]))
            if rec.get("type") == "curtain":
                sub.addAction(f"Convert {what} to a solid wall",
                              lambda: self.convert_walls(walls, "solid"))
            else:
                sub.addAction(f"Convert {what} to a curtain wall",
                              lambda: self.convert_walls(walls, "curtain"))
        if sel[0] == "slab":
            sub.addAction("Open a shaft — draw a rectangle on this slab",
                          lambda: self.shaft_rect(sel[1], "open"))
            sub.addAction("Open a shaft through every floor — draw a "
                          "rectangle", lambda: self.shaft_rect(sel[1],
                                                               "through"))
            sub.addAction("Close a shaft / opening — draw a rectangle "
                          "round it", lambda: self.shaft_rect(sel[1],
                                                              "close"))
            sub.addAction("Add shaft / opening in this slab…",
                          lambda: self.shaft_dialog(sel[1]))
            sub.addAction("Edges, railing, sun shades, close openings…",
                          lambda: self.slab_edges_dialog(sel[1]))
            sub.addAction("Extend slab to the walls",
                          lambda: self._slab_extend(sel[1]))
            sub.addAction("Extend slab to walls I pick…",
                          lambda: self._start_extend_pick(sel[1]))
            sub.addAction("Extend slab up to the beams",
                          lambda: self._slab_to_beams(sel[1]))
            sub.addAction("Extend slab up to the columns",
                          lambda: self._slab_to_columns(sel[1]))
            sub.addAction("Make it a roof terrace floor",
                          lambda: self._roof_terrace(sel[1]))
            sub.addAction("Tidy the slab's edges",
                          lambda: self._slab_tidy(sel[1]))
            mine = [m for m in doc.get("man_shafts") or []
                    if any(h in (rec.get("man") or [])
                           for h in [m["pts"]]) or self._shaft_in(m, rec)]
            if mine:
                ms = sub.addMenu(f"Remove an opening drawn here "
                                 f"({len(mine)})")
                for m in mine:
                    xs = [p_[0] for p_ in m["pts"]]
                    ys = [p_[1] for p_ in m["pts"]]
                    ms.addAction(
                        f"{max(xs) - min(xs):.2f} × {max(ys) - min(ys):.2f} m"
                        f" at ({sum(xs) / len(xs):.2f}, "
                        f"{sum(ys) / len(ys):.2f})"
                        + (" · through all floors" if m.get("through")
                           else ""),
                        lambda i=m["id"]: self._shaft_remove(i))
        if sel[0] == "wall":
            walls_ = [i for k, i in self._selected_all() if k == "wall"] or \
                [sel[1]]
            am = sub.addMenu(f"Attach / detach ({len(walls_)} wall"
                             f"{'s' if len(walls_) > 1 else ''})")
            for lab_, ta, ba in (("Attach top to the slab above", "slab", None),
                                 ("Detach top (keep its height)", "free",
                                  None),
                                 ("Attach bottom to the floor slab", None,
                                  "slab"),
                                 ("Detach bottom (keep its base)", None,
                                  "free"),
                                 ("Attach top and bottom", "slab", "slab")):
                am.addAction(lab_, lambda t_=ta, b_=ba, ws_=walls_:
                             self._wall_attach(ws_, t_, b_))
        if sel[0] == "beam":
            sub.addAction("Trim / extend this beam…",
                          lambda: self.beam_trim_dialog(sel[1]))
            sub.addAction("Trim / extend to a point I click",
                          lambda: self._beam_pick(sel[1]))
        if sel[0] in ("beam", "column"):
            sub.addAction("Beams column to column on this level",
                          lambda: self._beams_cc(rec["level"]))
            am = sub.addMenu("Align beam(s) with the columns" if sel[0] ==
                             "beam" else "Align this column's beams")
            for how_, lab_ in (("left", "Left / top face of the columns"),
                               ("centre", "Centre of the columns"),
                               ("right", "Right / bottom face of the "
                                         "columns")):
                am.addAction(lab_, lambda h=how_, k=sel[0], i=sel[1]:
                             self._align_beams(k, i, h))
        if sel[0] == "ramp":
            sub.addAction("Start at the other end", self._flip)
        if sel[0] == "room":
            sub.addAction("Add furniture from the library…",
                          lambda: self.add_furniture_dialog(sel[1]))
        if sel[0] == "stairrail":
            sub.addAction("Put back the railing's deleted pieces",
                          lambda: self._rail_restore(sel[1]))
        sub.addAction("Not on this floor — keep out of 3D",
                      self._off3d_selected)
        sub.addSeparator()
        sub.addAction("Show in the panel", self._fill_selected)
        sub.addAction("Delete this railing piece" if sel[0] == "stairrail"
                      and getattr(self, "_sel_seg", None) is not None
                      else "Delete", self._delete_selected)

    def close_openings(self, ids):
        """Windows (or openings) taken out: the wall runs through solid."""
        doc = self.doc()
        ids = set(ids)
        n = sum(1 for o in doc["arch"]["openings"] if o["id"] in ids)
        if not n:
            return
        doc["arch"]["openings"] = [o for o in doc["arch"]["openings"]
                                   if o["id"] not in ids]
        self._sel_key = None
        self.commit(doc, f"{n} opening(s) replaced with wall")

    def _quick(self, sel, **changes):
        """One change to an element, from the right-click menu."""
        doc = self.doc()
        rec = PJ.find_record(doc, *sel)
        if rec is None:
            return
        new = dict(rec, **changes)
        if sel[0] == "opening":
            PJ.fit_head(new)
        why = PJ.check_record(doc, sel[0], dict(new, id=rec["id"]))
        if why:
            self.flash(f"Not changed — {why}")
            return
        rec.update(new)
        if self.commit(doc, f"{rec.get('name', sel[0])} changed"):
            self._reselect(sel)

    def convert_walls(self, ids, kind):
        """Walls made curtain walls (glass on a grid: their windows go,
        their doors fitted 4'–8' in an aluminium frame) — or solid again."""
        doc = self.doc()
        n = sum(1 for w in doc["arch"]["walls"] if w["id"] in ids)
        if not n:
            return
        if kind == "curtain":
            gone, fitted = PJ.to_curtain(doc, ids)
            msg = (f"{n} wall(s): curtain wall — {gone} window(s) removed, "
                   f"{fitted} door(s) fitted")
        else:
            for w in doc["arch"]["walls"]:
                if w["id"] in ids:
                    w["type"] = kind
            msg = f"{n} wall(s): {kind} wall"
        if self.commit(doc, msg):
            self._fill_selected()

    def convert_selected_walls(self, kind):
        walls = [i for k, i in self._selected_all() if k == "wall"]
        if not walls:
            self.flash("Select walls first (click, Shift+click)")
            return
        self.convert_walls(walls, kind)

    def edit_dialog(self, sel=None):
        """The element's fields in a small dialog by the cursor."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        sel = sel or self._selected()
        if not sel:
            return
        rec = PJ.find_record(self.doc(), *sel)
        if rec is None:
            return
        if sel[0] == "opening" and rec.get("kind") in ("door", "window"):
            from .engine import structure as S_
            rec = dict(rec)                  # the frame's own size shown
            _l, _c, fw_, fd_ = S_.frame_size(rec)
            rec.setdefault("frame_w", round(fw_, 4))
            rec.setdefault("frame_d", round(fd_, 4))
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{rec.get('name', sel[0])} — CAD2IngeTrazo")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        lay.addLayout(form)
        widgets = self._build_fields(form, sel[0], rec)
        if not widgets:
            form.addRow(QLabel("Nothing to edit here — use the panel"))
        if sel[0] in ("stair", "stairrail"):
            form.addRow(_btn("Flights, rotation and landings…",
                             lambda: (dlg.reject(),
                                      self.stair_flights_dialog(sel[1])),
                             primary=True))
        if sel[0] == "slab":
            row = QHBoxLayout()
            row.addWidget(_btn("Edges, railing, sun shades, openings…",
                               lambda: (dlg.reject(),
                                        self.slab_edges_dialog(sel[1]))))
            row.addWidget(_btn("Add shaft…",
                               lambda: (dlg.reject(),
                                        self.shaft_dialog(sel[1]))))
            row.addWidget(_btn("Extend to walls I pick…",
                               lambda: (dlg.reject(),
                                        self._start_extend_pick(sel[1]))))
            form.addRow(row)
            row = QHBoxLayout()
            row.addWidget(_btn("Extend slab to the walls",
                               lambda: (dlg.reject(),
                                        self._slab_extend(sel[1]))))
            row.addWidget(_btn("Extend slab up to the beams",
                               lambda: (dlg.reject(),
                                        self._slab_to_beams(sel[1]))))
            row.addWidget(_btn("… up to the columns",
                               lambda: (dlg.reject(),
                                        self._slab_to_columns(sel[1]))))
            form.addRow(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                              | QDialogButtonBox.Apply)
        lay.addWidget(bb)
        bb.accepted.connect(lambda: (self._apply_selected(widgets, sel),
                                     dlg.accept()))
        bb.rejected.connect(dlg.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(
            lambda: self._apply_selected(widgets, sel))
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        dlg.exec()

    def cw_door_dialog(self, wall_id):
        """A door for a curtain wall: its type, leaves, width (one bay or
        two by default) and where along the wall — set into the grid."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        doc = self.doc()
        w = PJ.find_record(doc, "wall", wall_id)
        if w is None:
            return
        from .engine import walls as W_
        L = float(W_.centre(w).L)
        dlg = QDialog(self)
        dlg.setWindowTitle("Door in the curtain wall — CAD2IngeTrazo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"<b>{w.get('name', 'Curtain wall')}</b> · "
                             f"{len_txt(L)} long, mullions about every "
                             f"{len_txt(float(w.get('grid', 1.5)))}"))
        form = QFormLayout()
        lay.addLayout(form)
        style = QComboBox()
        for k, label in PJ.CW_DOOR_STYLES:
            style.addItem(label, k)
        form.addRow("Door type", style)
        leaves = QComboBox()
        leaves.addItem("By its width (single up to 4'-0\")", 0)
        leaves.addItem("Single", 1)
        leaves.addItem("Double", 2)
        form.addRow("Leaves", leaves)
        width = _spin(0.0, 6.0, 0.0, 0.0254)
        width.setToolTip("0 = one bay of the grid (two when a bay is under "
                         "3'-0\"), kept between 4'-0\" and 8'-0\"")
        form.addRow("Width (0 = by the grid)", width)
        pos = _spin(0.0, 500.0, L / 2, 0.1)
        form.addRow("Centre from the wall's start", pos)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        if dlg.exec() != QDialog.Accepted:
            return
        doc = self.doc()
        rec, why = PJ.add_cw_door(doc, wall_id, style.currentData(),
                                  width.value() or None, pos.value(),
                                  leaves.currentData() or None)
        if why:
            self.flash(f"Not added — {why}")
            return
        self.commit(doc, f"{style.currentText()} added to the curtain wall")

    def split_wall_dialog(self, wall_id):
        """Part of a wall made its own wall (from / to along it), then its
        properties to edit — a part as curtain wall, railing, lower…"""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        doc = self.doc()
        w = PJ.find_record(doc, "wall", wall_id)
        if w is None:
            return
        from .engine import walls as W_
        L = float(W_.drawn(w).L)
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit part of the wall — CAD2IngeTrazo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"<b>{w.get('name', 'Wall')}</b> · {len_txt(L)} long<br><i>The "
            "part becomes a wall of its own (the rest stays as it is); a "
            "cut through a door or window moves to clear it.</i>"))
        form = QFormLayout()
        lay.addLayout(form)
        a = _spin(0.0, L, round(L / 3, 2), 0.1)
        b = _spin(0.0, L, round(2 * L / 3, 2), 0.1)
        form.addRow("From (m from the wall's start)", a)
        form.addRow("To", b)
        then = QComboBox()
        then.addItem("Then edit its properties…", "edit")
        then.addItem("Then make it a curtain wall", "curtain")
        then.addItem("Then make it a railing (balcony / parapet)", "rail")
        then.addItem("Just split it", "none")
        form.addRow("", then)
        start = QLabel(f"Start: ({w['a'][0]:.2f}, {w['a'][1]:.2f}) → end: "
                       f"({w['b'][0]:.2f}, {w['b'][1]:.2f})")
        start.setStyleSheet("color: gray;")
        lay.addWidget(start)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        if dlg.exec() != QDialog.Accepted:
            return
        doc = self.doc()
        pid, why = PJ.split_wall(doc, wall_id, a.value(), b.value())
        if why:
            self.flash(f"Not split — {why}")
            return
        what = then.currentData()
        msg = "Wall split — its part is a wall of its own"
        if what == "curtain":
            PJ.to_curtain(doc, [pid])
            msg = "Part of the wall made a curtain wall"
        elif what == "rail":
            part = PJ.find_record(doc, "wall", pid)
            part["rail"] = doc["settings"].get("parapet_rail") or "ss_bars"
            part["height"] = 1.0
            msg = "Part of the wall made a railing"
        if not self.commit(doc, msg):
            return
        self._reselect(("wall", pid))
        if what == "edit":
            self.edit_dialog(("wall", pid))

    @staticmethod
    def _shaft_in(m, slab) -> bool:
        try:
            from shapely.geometry import Polygon
            return Polygon(slab["corners"]).buffer(0).intersects(
                Polygon(m["pts"]).buffer(0).buffer(-0.02))
        except Exception:  # noqa: BLE001
            return False

    def _shaft_remove(self, sid):
        doc = self.doc()
        if PJ.remove_man_shaft(doc, sid):
            self.commit(doc, "Opening removed — the slab closed there")

    def shaft_dialog(self, slab_id=None):
        """A shaft or slab opening cut by hand: a rectangle W × D centred at
        X, Y (turned by an angle), or the outline selected in the model (a
        rectangle / shape drawn on the floor); in this floor only, or
        through every floor (a services / lift shaft)."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        doc = self.doc()
        arch = doc["arch"]
        slab = PJ.find_record(doc, "slab", slab_id) if slab_id else None
        # the floor this slab carries (cast over the floor below it)
        lid = None
        if slab is not None:
            lid = slab["level"]
            if slab.get("top"):
                el = PJ.elevations(arch)
                order = [arch["levels"][i]["id"] for i in
                         sorted(range(len(arch["levels"])),
                                key=lambda i: el[i])]
                k = order.index(lid)
                if k + 1 < len(order):
                    lid = order[k + 1]
        lid = lid or self.level()[0]
        if not lid:
            self.flash("Pick a level at the top first")
            return
        names = {lv["id"]: lv["name"] for lv in arch["levels"]}
        drawn = self._drawn_outlines()
        cx = cy = 0.0
        if slab is not None:
            cs = slab["corners"]
            cx = sum(p_[0] for p_ in cs) / len(cs)
            cy = sum(p_[1] for p_ in cs) / len(cs)
        dlg = QDialog(self)
        dlg.setWindowTitle("Shaft / slab opening — CAD2IngeTrazo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"<b>Floor of {names.get(lid, lid)}</b><br><i>"
                             "The opening stays through rebuilds and "
                             "re-imports of the slab.</i>"))
        form = QFormLayout()
        lay.addLayout(form)
        how = QComboBox()
        how.addItem("Rectangle W × D centred at X, Y", "rect")
        if drawn:
            how.addItem(f"The outline selected in the model ({len(drawn)})",
                        "sel")
            how.setCurrentIndex(1)
        form.addRow("Shape", how)
        row = QHBoxLayout()
        sx, sy = _spin(-1e5, 1e5, round(cx, 2), 0.1), \
            _spin(-1e5, 1e5, round(cy, 2), 0.1)
        row.addWidget(sx)
        row.addWidget(sy)
        form.addRow("Centre X, Y", row)
        row = QHBoxLayout()
        sw, sd = _spin(0.2, 50, 1.8, 0.05), _spin(0.2, 50, 2.1, 0.05)
        row.addWidget(sw)
        row.addWidget(sd)
        form.addRow("Width × depth", row)
        sa = _spin(-360, 360, 0.0, 5, 1, " °")
        form.addRow("Angle", sa)
        thr = QCheckBox("Through every floor (a shaft from bottom to top)")
        form.addRow(thr)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        if dlg.exec() != QDialog.Accepted:
            return
        doc = self.doc()
        shapes = []
        if how.currentData() == "sel":
            shapes = [[v[:2] for v in vs] for vs in drawn]
        else:
            a = math.radians(sa.value())
            c_, s_ = math.cos(a), math.sin(a)
            w2, d2 = sw.value() / 2, sd.value() / 2
            shapes = [[(sx.value() + px * c_ - py * s_,
                        sy.value() + px * s_ + py * c_)
                       for px, py in ((-w2, -d2), (w2, -d2), (w2, d2),
                                      (-w2, d2))]]
        made = sum(1 for sh in shapes
                   if PJ.add_man_shaft(doc, lid, sh, thr.isChecked()))
        if not made:
            self.flash("No opening made — it falls outside the slab", 8000)
            return
        self.commit(doc, f"{made} opening(s) cut in the floor of "
                         f"{names.get(lid, lid)}"
                         + (" and every floor" if thr.isChecked() else ""))

    def _slab_extend(self, slab_id):
        from . import slabedges as SE
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id)
        if slab is None:
            return
        if not SE.extend_to_walls(doc, slab):
            self.flash("The slab already reaches its walls")
            return
        self.commit(doc, "Slab extended to its walls")

    def _slab_to_beams(self, slab_id):
        from . import slabedges as SE
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id)
        if slab is None:
            return
        if not SE.beams_for(doc, slab):
            self.flash("No beams under this slab — add them in section 6 "
                       "(Beams run: Column to column)")
            return
        n = SE.extend_to_beams(doc, slab)
        if not n:
            self.flash("The slab already covers its beams")
            return
        self.commit(doc, f"Slab extended up to {n} beam(s)")

    def _slab_to_columns(self, slab_id):
        from . import slabedges as SE
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id)
        if slab is None:
            return
        from shapely.ops import unary_union
        others = [SE._poly(e["corners"]) for e in doc["arch"]["structure"]
                  if e["type"] == "slab" and e is not slab
                  and e["level"] == slab["level"] and e.get("corners")]
        n = SE.extend_to_columns(doc, slab, 4.0,
                                 unary_union(others) if others else None)
        if not n:
            self.flash("No column or pier off this slab within 4 m")
            return
        SE.tidy_slab(slab)
        self.commit(doc, f"Slab carried out over {n} column(s) / pier(s)")

    def _slab_tidy(self, slab_id):
        from . import slabedges as SE
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id)
        if slab is None:
            return
        n0 = len(slab.get("corners") or [])
        if not SE.tidy_slab(slab):
            self.flash("This slab's edges are already clean")
            return
        self.commit(doc, f"Slab edges tidied: {n0} → "
                         f"{len(slab['corners'])} corners")

    def _align_beams(self, kind, eid, how):
        """The beams selected (or the one clicked, or a column's beams)
        slid onto the columns' left / top face, centre or right / bottom
        face."""
        doc = self.doc()
        if kind == "column":
            ids = PJ.beams_at_column(doc, eid)
        else:
            ids = [i for k, i in self._selected_all() if k == "beam"] \
                if hasattr(self, "_selected_all") else []
            if eid not in ids:
                ids = [eid]
        n = sum(1 for i in ids if PJ.align_beam(doc, i, how))
        if not n:
            self.flash("No column at the beam's ends to align it with")
            return
        word = {"left": "left / top face", "centre": "centre",
                "right": "right / bottom face"}[how]
        self.commit(doc, f"{n} beam(s) on the columns' {word}")

    def slab_edges_dialog(self, slab_id):
        """A slab's edges: extended to its walls; a railing on its free
        edges (or taken off); sun shades over its floor's windows; its
        openings closed."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox,
                                       QListWidget, QListWidgetItem)

        from . import slabedges as SE
        from .engine import railings as RL
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id)
        if slab is None:
            return
        lid = SE.floor_level_of(doc, slab)
        names = {lv["id"]: lv["name"] for lv in doc["arch"]["levels"]}
        dlg = QDialog(self)
        dlg.setWindowTitle("Slab edges — CAD2IngeTrazo")
        lay = QVBoxLayout(dlg)
        free = SE.free_edges(doc, slab)
        lay.addWidget(QLabel(
            f"<b>{slab.get('name', 'Slab')}</b> · the floor of "
            f"{names.get(lid, lid)}<br><i>{len(free)} free edge(s) — "
            f"{sum(math.dist(a, b) for a, b in free):.1f} m with no wall on "
            "them.</i>"))
        form = QFormLayout()
        lay.addLayout(form)
        ext = QCheckBox("Extend the slab out to its walls' outer faces")
        form.addRow(ext)
        form.addRow(_btn("Extend to walls I pick in the model…",
                         lambda: (dlg.reject(),
                                  self._start_extend_pick(slab_id)),
                         "Close this, select the walls (Ctrl+click for "
                         "several), right-click one ▸ «Extend the slab to "
                         "the selected walls»"))
        rail = QComboBox()
        rail.addItem("— leave as it is —", "")
        for k, lab in RL.TYPES:
            rail.addItem(lab, k)
        rail.addItem("Take the railings off this slab's edge", "off")
        form.addRow("Railing on the free edges", rail)
        rh = _spin(0.3, 2.0, float(doc["settings"].get("rail_h", SE.RAIL_H)),
                   0.0254)
        form.addRow("Railing height", rh)
        cur = (doc.get("sunshades") or {}).get(lid)
        sun = QCheckBox("Sun shades (chajja) over the floor's outer windows")
        sun.setChecked(cur is not None)
        form.addRow(sun)
        row = QHBoxLayout()
        sd = _spin(0.15, 2.0, (cur or {}).get("d", 0.6096), 0.0254)
        sd.setToolTip("Projection (2'-0\" by default)")
        st_ = _spin(0.05, 0.3, (cur or {}).get("t", 0.1016), 0.0127)
        st_.setToolTip("Thickness (4\" by default)")
        se = _spin(0.0, 1.0, (cur or {}).get("ext", 0.1524), 0.0254)
        se.setToolTip("Past each side of the window (6\" by default)")
        for w_ in (sd, st_, se):
            row.addWidget(w_)
        form.addRow("Projection / thick / past jambs", row)
        holes = slab.get("holes") or []
        lst = None
        if holes:
            lay.addWidget(QLabel("<b>Close openings</b> (tick to close):"))
            lst = QListWidget()
            for k, h in enumerate(holes):
                xs = [p_[0] for p_ in h]
                ys = [p_[1] for p_ in h]
                it = QListWidgetItem(
                    f"{max(xs) - min(xs):.2f} × {max(ys) - min(ys):.2f} m at "
                    f"({sum(xs) / len(xs):.2f}, {sum(ys) / len(ys):.2f})")
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked)
                it.setData(Qt.UserRole, k)
                lst.addItem(it)
            lst.setMaximumHeight(140)
            lay.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        if dlg.exec() != QDialog.Accepted:
            return
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id)
        msgs = []
        if lst is not None:
            ks = sorted((lst.item(i).data(Qt.UserRole)
                         for i in range(lst.count())
                         if lst.item(i).checkState() == Qt.Checked),
                        reverse=True)
            n = sum(1 for k in ks if SE.close_hole(doc, slab, k))
            if n:
                msgs.append(f"{n} opening(s) closed")
        if ext.isChecked() and SE.extend_to_walls(doc, slab):
            msgs.append("slab extended to its walls")
        kind = rail.currentData()
        if kind == "off":
            msgs.append(f"{SE.remove_edge_rails(doc, slab)} railing(s) off")
        elif kind:
            doc["settings"]["rail_h"] = rh.value()
            SE.remove_edge_rails(doc, slab)
            n = SE.add_edge_rails(doc, slab, kind, rh.value())
            msgs.append(f"{n} railing(s) on the free edges")
        if sun.isChecked():
            SE.set_sunshades(doc, lid, sd.value(), st_.value(), se.value())
            msgs.append("sun shades over the windows")
        elif cur is not None:
            SE.remove_sunshades(doc, lid)
            msgs.append("sun shades off")
        if not msgs:
            self.flash("Nothing changed")
            return
        self.commit(doc, "Slab: " + ", ".join(msgs))

    def _level_at_z(self, doc, z):
        """The level whose floor a point at height ``z`` lies on (the
        nearest floor at or under it)."""
        arch = doc["arch"]
        el = PJ.elevations(arch)
        best = None
        for i, lv_ in enumerate(arch["levels"]):
            dz = z - el[i]
            if dz > -0.6 and (best is None or abs(dz) < abs(best[0])):
                best = (dz, lv_["id"])
        return best[1] if best else (arch["levels"][0]["id"]
                                    if arch["levels"] else None)

    def _shaft_drawn(self, drawn, through, lid0=None):
        doc = self.doc()
        names = {lv["id"]: lv["name"] for lv in doc["arch"]["levels"]}
        made, where = 0, set()
        for vs in drawn:
            z = sum(v[2] for v in vs) / len(vs)
            lid = lid0 or self._level_at_z(doc, z)
            if lid and PJ.add_man_shaft(doc, lid, [v[:2] for v in vs],
                                        through):
                made += 1
                where.add(names.get(lid, lid))
        if not made:
            self.flash("No shaft made — draw the rectangle on the slab "
                       "(inside it), select it, then right-click", 8000)
            return
        self.commit(doc, f"{made} shaft(s) opened in the floor of "
                         + ", ".join(sorted(where))
                         + (" and every floor" if through else "")
                         + " — the drawn rectangle can be deleted")

    def _wall_attach(self, ids, top, bot):
        doc = self.doc()
        n = 0
        for wid in ids:
            w = PJ.find_record(doc, "wall", wid)
            if w is None:
                continue
            new = PJ.wall_attach(doc, w, top, bot, dict(w))
            if new != w:
                w.update(new)
                n += 1
        if not n:
            self.flash("Nothing to change")
            return
        self.commit(doc, f"{n} wall(s): " + ", ".join(
            x for x in (("top attached" if top == "slab" else
                         "top detached") if top else "",
                        ("bottom attached" if bot == "slab" else
                         "bottom detached") if bot else "") if x))

    def _group_top_z(self, kind, eid):
        """The highest point of the element's groups in the model."""
        zs = []
        for g in PJ.all_groups(self.vp.scene):
            t = PJ.tag_of(g) or {}
            if t.get("type") != kind or t.get("id") != eid:
                continue
            m = getattr(g, "mesh", None)
            xf = getattr(g, "xform", None)
            for v in (m.vertices if m is not None else []):
                p = v.position
                if xf is not None:
                    p = xf.map(p)
                zs.append(p.z())
        return max(zs) if zs else None

    def shaft_rect(self, slab_id=None, mode="open"):
        """A shaft opened (or closed) where a rectangle is drawn on a slab:
        click two opposite corners on its top face. ``mode``: «open» (this
        floor), «through» (every floor), «close»."""
        pe = getattr(self, "_planedit", None)
        if pe is None:
            self.flash("Not available — restart IngeTrazo")
            return
        if slab_id is None:
            sel = self._selected()
            if sel and sel[0] == "slab":
                slab_id = sel[1]
        doc = self.doc()
        slab = PJ.find_record(doc, "slab", slab_id) if slab_id else None
        if slab is not None:
            z = self._group_top_z("slab", slab_id)
        else:
            lid, lv = self.level()
            if not lid:
                self.flash("Select a slab (or pick a level at the top) first")
                return
            el = PJ.elevations(doc["arch"])
            i = next(k for k, l_ in enumerate(doc["arch"]["levels"])
                     if l_["id"] == lid)
            z = el[i]
        if z is None:
            z = 0.0

        def done(a, b):
            if abs(b[0] - a[0]) < 0.1 or abs(b[1] - a[1]) < 0.1:
                self.flash("Too small — click two opposite corners")
                return
            vs = [(a[0], a[1], z), (b[0], a[1], z), (b[0], b[1], z),
                  (a[0], b[1], z)]
            lid0 = None
            if slab_id:
                from . import slabedges as SE
                s_ = PJ.find_record(self.doc(), "slab", slab_id)
                if s_ is not None:
                    lid0 = SE.floor_level_of(self.doc(), s_)
            if mode == "close":
                self._shaft_close_drawn([vs], lid0)
            else:
                self._shaft_drawn([vs], mode == "through", lid0)
        what = {"open": "open a shaft", "through": "open a shaft through "
                "every floor", "close": "close the opening"}[mode]
        pe.pick_rect(z, done, f"Click one corner, then the opposite corner "
                              f"on the slab to {what} (Esc cancels)")

    def _shaft_close_drawn(self, drawn, lid0=None):
        """The shafts / slab openings under the rectangle drawn closed:
        those drawn by hand forgotten, the slab's own holes filled."""
        from shapely.geometry import Polygon

        from . import slabedges as SE
        doc = self.doc()
        n = 0
        for vs in drawn:
            rp = Polygon([v[:2] for v in vs]).buffer(0)
            if rp.is_empty:
                continue
            z = sum(v[2] for v in vs) / len(vs)
            lid = lid0 or self._level_at_z(doc, z)
            before = len(doc.get("man_shafts") or [])
            doc["man_shafts"] = [
                m for m in doc.get("man_shafts") or []
                if not (Polygon(m["pts"]).buffer(0).intersects(rp) and
                        (m.get("through") or m.get("level") == lid))]
            n += before - len(doc["man_shafts"])
            PJ.apply_man_shafts(doc)
            for s_ in PJ._floor_slabs(doc, lid):
                for k in sorted(range(len(s_.get("holes") or [])),
                                reverse=True):
                    try:
                        hp = Polygon(s_["holes"][k]).buffer(0)
                    except Exception:  # noqa: BLE001
                        continue
                    if hp.intersects(rp) and \
                            hp.intersection(rp).area > 0.2 * min(
                                hp.area, rp.area):
                        if SE.close_hole(doc, s_, k):
                            n += 1
        if not n:
            self.flash("No shaft or opening under the rectangle drawn")
            return
        self.commit(doc, f"{n} shaft(s) / opening(s) closed — the drawn "
                         "rectangle can be deleted")

    def _auto_openings(self, doc) -> bool:
        """A rectangle, circle or any closed shape drawn (Rectangle / Circle
        / Line tools) flat on the face of a CAD2IngeTrazo wall or on a
        slab's top: made an opening there at once — a hole through the
        wall (round for a circle), a shaft through the slab — and the
        drawn shape taken away. True when the model was rebuilt."""
        if not doc["settings"].get("auto_openings", True):
            return False
        sc = self.vp.scene
        if getattr(sc, "edit_group", None) is not None:
            return False
        mesh = getattr(sc, "loose_mesh", None) or getattr(sc, "mesh", None)
        faces = list(getattr(mesh, "faces", []) or [])
        if not faces:
            if getattr(self, "_auto_seen", None) is None:
                self._auto_seen = set()
            return False
        seen = getattr(self, "_auto_seen", None)
        first = seen is None
        if first:                 # what was there before: left alone
            seen = self._auto_seen = set()
        todo = []
        for f in faces:
            vs = []
            for v in f.vertices:
                q = getattr(v, "position", v)
                if callable(q):
                    q = q()
                vs.append((float(q.x()), float(q.y()), float(q.z())))
            if len(vs) < 3:
                continue
            key = tuple(sorted((round(a, 3), round(b, 3), round(c, 3))
                               for a, b, c in vs))
            if key in seen:
                continue
            seen.add(key)
            todo.append((f, vs))
        if not todo or first:
            return False
        made, used = [], []
        arch = doc["arch"]
        el = PJ.elevations(arch)
        zof = {lv["id"]: el[i] for i, lv in enumerate(arch["levels"])}
        info = None
        for f, vs in todo:
            kind = _flat_shape(vs)
            if kind is None:
                continue
            if kind[0] == "h":                    # on a slab's top
                if self._shape_shaft(doc, vs):
                    made.append("shaft")
                    used.append(f)
                continue
            got = _wall_hit(arch, vs, zof, info)
            if got is None:
                continue
            w, seg, s0, s1, zb, zt = got
            z0 = zof.get(w["level"], 0.0)
            rnd = _is_circle(vs)
            if rnd:
                d_ = max(s1 - s0, zt - zb)
                sc_, zc = (s0 + s1) / 2, (zb + zt) / 2
                s0, s1 = sc_ - d_ / 2, sc_ + d_ / 2
                zb, zt = zc - d_ / 2, zc + d_ / 2
            if s1 - s0 < 0.05 or zt - zb < 0.05:
                continue
            rec = {"kind": "void", "wall": w["id"],
                   "pos": round((s0 + s1) / 2, 4),
                   "w": round(s1 - s0, 4), "h": round(zt - zb, 4),
                   "sill": round(max(zb - z0, 0.0), 4), "style": "",
                   "swing": "left", "leaves": 1, "face": 1, "head": "flat",
                   "frame": "auto"}
            if rnd:
                rec["shape"] = "round"
            arch["openings"] += M.new_openings(arch["openings"], [rec])
            made.append("round hole" if rnd else "opening")
            used.append(f)
        if not made:
            return False
        try:                                   # the drawn shapes away
            from core.history import CompoundCommand, DeleteEdgesCommand
            m = mesh
            edges = []
            for f in used:
                vv = list(f.vertices)
                for i in range(len(vv)):
                    a = m.vertex_at(getattr(vv[i], "position", vv[i]))
                    b = m.vertex_at(getattr(vv[(i + 1) % len(vv)],
                                            "position",
                                            vv[(i + 1) % len(vv)]))
                    e = m.find_edge(a, b) if a is not None and \
                        b is not None else None
                    if e is not None and e not in edges:
                        edges.append(e)
            if edges:
                self.vp.history.execute(CompoundCommand(
                    [DeleteEdgesCommand(edges)]))
        except Exception:  # noqa: BLE001
            log_error("panel._auto_openings delete")
        from collections import Counter
        what = ", ".join(f"{n} {k}{'s' if n > 1 else ''}"
                         for k, n in Counter(made).items())
        self.commit(doc, f"Drawn shape → {what}")
        return True

    def _shape_shaft(self, doc, vs) -> bool:
        """A flat shape on a slab's top face: a shaft cut through it."""
        from shapely.geometry import Point, Polygon

        from . import slabedges as SE
        z = sum(v[2] for v in vs) / len(vs)
        poly = Polygon([v[:2] for v in vs]).buffer(0)
        if poly.is_empty or poly.area < 0.04:
            return False
        c = poly.representative_point()
        cands = []
        el = PJ.elevations(doc["arch"])
        for s_ in doc["arch"]["structure"]:
            if s_["type"] != "slab" or not s_.get("corners"):
                continue
            try:
                if not Polygon(s_["corners"]).buffer(0).contains(
                        Point(c.x, c.y)):
                    continue
            except Exception:  # noqa: BLE001
                continue
            top = self._group_top_z("slab", s_["id"])
            if top is None:
                continue
            # on its top (or its finish): that slab; on a floor under it,
            # within the storey: the slab over that floor
            if -0.05 <= z - top <= 0.3:
                cands.append((0, abs(z - top), s_))
            elif 0.0 < top - z <= 6.0:
                cands.append((1, top - z, s_))
        if not cands:
            return False
        cands.sort(key=lambda t: (t[0], t[1]))
        s_ = cands[0][2]
        lid = SE.floor_level_of(doc, s_)
        ids = [lv["id"] for lv in doc["arch"]["levels"]]
        if lid not in ids:
            lid = s_["level"]
        del el
        pts = [list(q) for q in list(poly.exterior.coords)[:-1]]
        return bool(PJ.add_man_shaft(doc, lid, pts, False))

    def _drawn_outlines(self) -> list:
        """Flat faces selected in the model that are not CAD2IngeTrazo's
        (a rectangle drawn with the Rectangle tool): their corners."""
        out = []
        for e in list(self.vp.scene.selection):
            if any(PJ.tag_of(g) for g in (e, getattr(e, "owner", None))
                   if g is not None):
                continue
            if hasattr(e, "loop") and hasattr(e, "vertices"):
                vs = []
                for v in e.vertices:
                    q = getattr(v, "position", v)
                    if callable(q):
                        q = q()
                    vs.append((float(q.x()), float(q.y()), float(q.z())))
                if len(vs) >= 3 and max(v[2] for v in vs) - \
                        min(v[2] for v in vs) < 0.05:
                    out.append(vs)
        return out

    def _rail_restore(self, sid):
        doc = self.doc()
        s_ = PJ.find_record(doc, "stair", sid)
        if s_ is None:
            return
        s_.pop("rail_skip", None)
        if s_.get("rail") == "none":
            s_.pop("rail", None)
        self.commit(doc, "Stair railing: every piece back")

    def _delete_selected(self):
        sel = self._sel_key
        if not sel:
            return
        doc = self.doc()
        seg = getattr(self, "_sel_seg", None) if sel[0] == "stairrail" \
            else None
        PJ.delete_record(doc, *sel, seg=seg)
        self._sel_key = None
        self.commit(doc, "Railing piece deleted" if seg is not None
                    else "Deleted")
        self._fill_selected()

    def _reselect(self, sel):
        """The rebuilt element selected again, its fields shown."""
        sc = self.vp.scene
        g = next((g for g in sc.groups if PJ.tag_of(g)
                  and PJ.tag_of(g)["id"] == sel[1]), None)
        if g is not None:
            sc.selection.clear()
            sc.selection.add(g)
            self.vp.update()
        else:                     # inside a floor group: the floor, and it
            for top in sc.groups:
                if any((PJ.tag_of(c) or {}).get("id") == sel[1]
                       for c, _m in _walk_world(getattr(top, "children",
                                                        None))):
                    sc.selection.clear()
                    sc.selection.add(top)
                    key_ = tuple(sorted(id(e) for e in sc.selection))
                    self._floor_memo = (key_, (sel[0], sel[1], None))
                    self.vp.update()
                    break
        self._sel_key = sel
        self._fill_selected()

    # ---- components (types) -----------------------------------------------------------
    def _components_part(self):
        from . import components as CP
        box, body = _fold("12  Components (types)", "components", False)
        v = QVBoxLayout(body)
        v.addWidget(QLabel("<i>Every element by its type — doors, windows, "
                           "columns, walls, slabs, finishes. Select a type "
                           "in the model, edit it (all of it changes), or "
                           "rename it.</i>"))
        row = QHBoxLayout()
        self.cp_scope = QComboBox()
        self.cp_scope.addItem("All levels", "all")
        self.cp_scope.addItem("This level", "level")
        self.cp_kind = QComboBox()
        self.cp_kind.addItem("All kinds", "")
        for g in CP.ORDER:
            self.cp_kind.addItem(CP.KIND_LABEL[g], g)
        for cb in (self.cp_scope, self.cp_kind):
            cb.currentIndexChanged.connect(
                lambda _i: self._fill_components(self.doc()))
            row.addWidget(cb)
        v.addLayout(row)
        self.cp_table = QTableWidget(0, 3)
        self.cp_table.setHorizontalHeaderLabels(["Mark", "Name", "Count"])
        hh = self.cp_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.cp_table.setWordWrap(False)

        from PySide6.QtCore import QEvent, QObject

        class _OnShow(QObject):        # the list filled when it opens
            def eventFilter(s_, obj, ev):
                if ev.type() == QEvent.Show:
                    try:
                        self._fill_components(self.doc())
                    except Exception:  # noqa: BLE001
                        log_error("panel._fill_components")
                return False
        self._cp_show = _OnShow(self)
        self.cp_table.installEventFilter(self._cp_show)
        self.cp_table.verticalHeader().setVisible(False)
        self.cp_table.setMinimumHeight(220)
        self.cp_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cp_table.cellDoubleClicked.connect(
            lambda r, c: c != 1 and self._cp_select())
        v.addWidget(self.cp_table)
        row = QHBoxLayout()
        row.addWidget(_btn("Select in model", self._cp_select,
                           "Every element of the types picked in the list",
                           primary=True))
        row.addWidget(_btn("Edit type…", self._cp_edit,
                           "Change the type: every element of it changes"))
        row.addWidget(_btn("Replace with library…", self._cp_lib,
                           "Show every element of the type as an IngeTrazo "
                           "library component (Properties ▸ Components), "
                           "fitted to each element"))
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_btn("Save names", self._cp_save_names,
                           "The names typed in the list (an empty name: "
                           "back to the one made from its sizes)"))
        row.addWidget(_btn("Refresh", lambda: self._fill_components(
            self.doc())))
        v.addLayout(row)
        row = QHBoxLayout()
        self.c_furn = QCheckBox("Furniture && fixtures from the CAD")
        self.c_furn.setToolTip(
            "Off by default. On: the CAD plan's blocks — beds, WCs, "
            "basins, showers, sofas, chairs, tables, wardrobes, kitchen "
            "sinks, stoves, fridges, plants — placed as IngeTrazo library "
            "models where they are drawn (every imported floor, and again "
            "on each import / update). Off: the furniture taken from the "
            "CAD removed (pieces placed by hand stay).")
        self.c_furn.toggled.connect(self._furn_toggle)
        row.addWidget(self.c_furn)
        row.addStretch(1)
        row.addWidget(_btn("Place again", self._cad_furniture,
                           "Read the CAD's furniture and fixture blocks "
                           "again (replaces only its own pieces)"))
        v.addLayout(row)
        self._cp_keys = []
        self.lay.addWidget(box)

    def _furn_toggle(self, on):
        if self._building:
            return
        if on:
            self._cad_furniture()
        else:
            self._cad_furniture_off()
        doc = self.doc()
        self.c_furn.blockSignals(True)
        self.c_furn.setChecked(bool(doc["settings"].get("cad_furniture")))
        self.c_furn.blockSignals(False)

    def _fill_components(self, doc):
        from . import components as CP
        cat = CP.catalogue(doc)
        scope = self.cp_scope.currentData()
        kind = self.cp_kind.currentData()
        lid = self.level_box.currentData()
        rows = []
        for k, t in cat.items():
            if kind and t["group"] != kind:
                continue
            items = [i for i in t["items"]
                     if scope == "all" or i[2] == lid]
            if not items:
                continue
            rows.append((CP.ORDER.index(t["group"]), t["mark"], k, t,
                         len(items)))
        rows.sort(key=lambda r: (r[0], r[1]))
        self._cp_keys = [r[2] for r in rows]
        self.cp_table.setRowCount(len(rows))
        for i, (_o, mark, _k, t, n) in enumerate(rows):
            a = QTableWidgetItem(mark)
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            self.cp_table.setItem(i, 0, a)
            nm = QTableWidgetItem(t["name"])
            nm.setToolTip(f"{t['mark']} · {t['name']}\n{n} in the model"
                          + ("" if t["name"] == t["label"]
                             else f"\n({t['label']})"))
            self.cp_table.setItem(i, 1, nm)
            c = QTableWidgetItem(str(n))
            c.setFlags(c.flags() & ~Qt.ItemIsEditable)
            self.cp_table.setItem(i, 2, c)

    def _cp_picked(self) -> list:
        rows = sorted({ix.row() for ix in self.cp_table.selectedIndexes()})
        return [self._cp_keys[r] for r in rows if r < len(self._cp_keys)]

    def _cp_select(self):
        keys = self._cp_picked()
        if not keys:
            self.flash("Pick a type in the list")
            return
        self.select_type(keys, self.cp_scope.currentData() == "level")

    def select_type(self, keys, this_level=False):
        """Every element of the types ``keys`` selected in the model."""
        sc = self.vp.scene
        lid = self.level_box.currentData()
        want = set(keys)
        hits = [g for g in sc.groups if (PJ.tag_of(g) or {}).get("ctype")
                in want and (not this_level
                             or PJ.tag_of(g).get("level") == lid)]
        sc.selection.clear()
        for g in hits:
            sc.selection.add(g)
        self.vp.update()
        self.flash(f"{len(hits)} selected")

    def _cp_edit(self):
        keys = self._cp_picked()
        if not keys:
            self.flash("Pick a type in the list")
            return
        self.edit_type(keys[0])

    def _cp_lib(self):
        keys = self._cp_picked()
        if not keys:
            self.flash("Pick a type in the list")
            return
        self.replace_type_dialog(keys)

    def _pick_bike(self):
        e = self.library_picker("Motorbike model — CAD2IngeTrazo",
                                "The model put in every motorbike space "
                                "(as the cars in the bays).", "Vehicles")
        if e is not None:
            self._set_bike(e)

    def _set_bike(self, e):
        doc = self.doc()
        st = doc["settings"]
        if e is None:
            st["bike_lib"] = None
        else:
            st["bike_lib"] = {"key": e["key"], "name": e.get("name", ""),
                              "entry": e.get("entry")}
        st["bike_model"] = "lib"
        self.commit(doc, "Motorbike model: " +
                    (e.get("name", "") if e else "library (first found)"))

    def library_picker(self, title, info="", start_cat=""):
        """IngeTrazo's library (bundled + online catalogue) to pick one
        model from: its entry, or None."""
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QCursor, QIcon
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox,
                                       QListWidget, QListWidgetItem)

        from . import library as LB
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            comps = LB.list_entries()
        finally:
            QApplication.restoreOverrideCursor()
        if not comps:
            self.flash("No IngeTrazo library found (check the connection "
                       "once; it is cached after)", 9000)
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(540, 600)
        lay = QVBoxLayout(dlg)
        if info:
            lay.addWidget(QLabel(info))
        row = QHBoxLayout()
        catbox = QComboBox()
        catbox.addItem("All categories", "")
        for c_ in sorted({e["cat"] for e in comps},
                         key=lambda x: (x != LB.BUNDLED, x.lower())):
            catbox.addItem(c_, c_)
        if start_cat:
            catbox.setCurrentIndex(max(catbox.findData(start_cat), 0))
        row.addWidget(catbox)
        find = QLineEdit()
        find.setPlaceholderText("Search the library…")
        row.addWidget(find, 1)
        lay.addLayout(row)
        lst = QListWidget()
        lst.setIconSize(QSize(48, 48))
        items = []
        for e in comps:
            it = QListWidgetItem(e["name"])
            it.setData(Qt.UserRole, e)
            it.setToolTip(f"{e['cat']} · {e['name']}"
                          + (f"\n{e['tip']}" if e.get("tip") else ""))
            lst.addItem(it)
            items.append(it)

        def visible():
            return [it for it in items if not it.isHidden()]

        def icons():
            for it in visible()[:400]:
                if it.icon().isNull():
                    p_ = LB.thumbnail(it.data(Qt.UserRole))
                    if p_ is not None:
                        it.setIcon(QIcon(str(p_)))

        def filt(*_a):
            q = find.text().strip().lower()
            c_ = catbox.currentData()
            for it in items:
                e = it.data(Qt.UserRole)
                it.setHidden(not ((not c_ or e["cat"] == c_) and (
                    not q or q in e["name"].lower()
                    or q in e["cat"].lower())))
            LB.prefetch([it.data(Qt.UserRole) for it in visible()[:400]])
            icons()
        find.textChanged.connect(filt)
        catbox.currentIndexChanged.connect(filt)
        tick = QTimer(dlg)
        tick.setInterval(600)
        tick.timeout.connect(icons)
        tick.start()
        filt()
        if visible():
            lst.setCurrentItem(visible()[0])
        lay.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        _place_on_screen(dlg, QCursor.pos())
        ok = dlg.exec() == QDialog.Accepted
        tick.stop()
        if not ok or lst.currentItem() is None:
            return None
        return lst.currentItem().data(Qt.UserRole)

    def add_furniture_dialog(self, room_id):
        """A library model set in a room, at its middle, on its floor —
        then moved / turned with IngeTrazo's own tools (kept)."""
        doc = self.doc()
        rec = PJ.room_record(doc, room_id)
        if rec is None:
            return
        cat = "Living room"
        nm = str(rec.get("name", "")).upper()
        for k_, c_ in (("BED", "Bedroom"), ("KITCHEN", "Kitchen"),
                       ("BATH", "Bathroom"), ("TOILET", "Bathroom"),
                       ("W.C", "Bathroom"), ("OFFICE", "Office"),
                       ("STUDY", "Office"), ("DINING", "Living room"),
                       ("GARDEN", "Exterior"), ("LAWN", "Exterior"),
                       ("PARKING", "Vehicles"), ("PORCH", "Vehicles")):
            if k_ in nm:
                cat = c_
                break
        e = self.library_picker(
            f"Furniture for {rec.get('name', 'the room')} — CAD2IngeTrazo",
            f"<b>{rec.get('name', 'Room')}</b><br><i>The model is set in the "
            "middle of the room on its floor; move or turn it with IngeTrazo's "
            "Move / Rotate tools — it stays where you put it.</i>", cat)
        if not e:
            return
        from . import library as LB
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            pr = LB.proto(e["key"], e.get("entry"))
        finally:
            QApplication.restoreOverrideCursor()
        if pr is None:
            self.flash(f"Couldn't get «{e['name']}» — check the connection",
                       8000)
            return
        import uuid as _uuid
        doc["furniture"].append({
            "id": _uuid.uuid4().hex[:8], "level": rec["level"],
            "room": rec["id"], "key": e["key"], "name": e["name"],
            **({"entry": e["entry"]} if e.get("entry") else {}),
            "x": float(rec["x"]), "y": float(rec["y"]), "rot": 0.0})
        self.commit(doc, f"{e['name']} placed in {rec.get('name', 'the room')}")

    def replace_type_dialog(self, keys):
        """The types ``keys`` drawn as an IngeTrazo library component: the
        model picked (searchable), fitted to each element's box — or back
        to CAD2IngeTrazo's own model."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox,
                                       QListWidget, QListWidgetItem)

        from . import components as CP
        from . import library as LB
        doc = self.doc()
        cat = CP.catalogue(doc)
        keys = [k for k in keys if k in cat]
        if not keys:
            return
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication as _QA
        _QA.setOverrideCursor(Qt.WaitCursor)
        try:
            comps = LB.list_entries()
        finally:
            _QA.restoreOverrideCursor()
        if not comps:
            self.flash("No IngeTrazo library found — neither the bundled "
                       "components nor the online catalogue (check the "
                       "connection once; it is cached after)", 9000)
            return
        t0 = cat[keys[0]]
        now = (t0.get("lib") or {})
        dlg = QDialog(self)
        dlg.setWindowTitle("Replace with a library component — "
                           "CAD2IngeTrazo")
        dlg.resize(560, 640)
        lay = QVBoxLayout(dlg)
        n = sum(len(cat[k]["items"]) for k in keys)
        what = CP.display(t0) if len(keys) == 1 else f"{len(keys)} types"
        n_on = sum(1 for e in comps if e["src"] == "online")
        lay.addWidget(QLabel(
            f"<b>{what}</b> · {n} elements<br><i>Each is drawn as the "
            "library model, fitted to its own size; its record (opening in "
            "the wall, sizes, schedules) stays.</i><br>"
            f"<span style='color:gray'>{len(comps) - n_on} bundled + {n_on} "
            "from IngeTrazo's online library (More components…)</span>"))
        row = QHBoxLayout()
        catbox = QComboBox()
        catbox.addItem("All categories", "")
        for c_ in sorted({e["cat"] for e in comps},
                         key=lambda x: (x != LB.BUNDLED, x.lower())):
            catbox.addItem(c_, c_)
        # a door / window type opens on «Doors and windows»
        kind0 = t0["items"][0][0] if t0.get("items") else ""
        rec0 = PJ.find_record(doc, kind0, t0["items"][0][1]) \
            if t0.get("items") else None
        if kind0 == "opening" or (rec0 or {}).get("type") == "core":
            i_ = catbox.findData("Doors and windows")
            if i_ >= 0:
                catbox.setCurrentIndex(i_)
        elif kind0 in ("stair", "stairrail"):
            i_ = catbox.findData("Staircases")
            if i_ >= 0:
                catbox.setCurrentIndex(i_)
        row.addWidget(catbox)
        find = QLineEdit()
        find.setPlaceholderText("Search the library…")
        row.addWidget(find, 1)
        lay.addLayout(row)
        lst = QListWidget()
        lst.setIconSize(QSize(48, 48))
        lst.setMinimumHeight(320)
        it0 = QListWidgetItem("— CAD2IngeTrazo's own model (no library) —")
        it0.setData(Qt.UserRole, None)
        lst.addItem(it0)
        items = []
        for e in comps:
            it = QListWidgetItem(e["name"])
            it.setData(Qt.UserRole, e)
            it.setToolTip(f"{e['cat']} · {e['name']}"
                          + (f"\n{e['tip']}" if e.get("tip") else ""))
            lst.addItem(it)
            items.append(it)
            if e["key"] == now.get("key"):
                lst.setCurrentItem(it)
        if lst.currentItem() is None:
            lst.setCurrentRow(0)

        def visible():
            return [it for it in items if not it.isHidden()]

        def icons():
            for it in visible()[:400]:
                if it.icon().isNull():
                    p_ = LB.thumbnail(it.data(Qt.UserRole))
                    if p_ is not None:
                        it.setIcon(QIcon(str(p_)))

        def filt(*_a):
            q = find.text().strip().lower()
            c_ = catbox.currentData()
            for it in items:
                e = it.data(Qt.UserRole)
                ok = (not c_ or e["cat"] == c_) and (
                    not q or q in e["name"].lower() or q in e["cat"].lower())
                it.setHidden(not ok)
            LB.prefetch([it.data(Qt.UserRole) for it in visible()[:400]])
            icons()
        find.textChanged.connect(filt)
        catbox.currentIndexChanged.connect(filt)
        tick = QTimer(dlg)
        tick.setInterval(600)
        tick.timeout.connect(icons)
        tick.start()
        filt()
        lay.addWidget(lst)
        form = QFormLayout()
        lay.addLayout(form)
        fit = QComboBox()
        for k, label in LB.FITS:
            fit.addItem(label, k)
        fit.setCurrentIndex(max(fit.findData(now.get("fit", "stretch")), 0))
        form.addRow("Size", fit)
        rot = QComboBox()
        for a in (0, 90, 180, 270):
            rot.addItem(f"{a}°", a)
        rot.setCurrentIndex(max(rot.findData(int(now.get("rot", 0) or 0)),
                                0))
        form.addRow("Turn", rot)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        ok_ = dlg.exec() == QDialog.Accepted
        tick.stop()
        if not ok_ or lst.currentItem() is None:
            return
        e = lst.currentItem().data(Qt.UserRole)
        lk = e["key"] if e else None
        doc = self.doc()
        names = doc.setdefault("comp_names", {})
        CP.catalogue(doc)                      # every type has its entry
        if lk:
            from PySide6.QtWidgets import QApplication as _QA2
            _QA2.setOverrideCursor(Qt.WaitCursor)
            try:                               # downloaded once, then cached
                pr_ = LB.proto(lk, e.get("entry"))
            finally:
                _QA2.restoreOverrideCursor()
            if pr_ is None:
                self.flash(f"Couldn't get «{e['name']}» — check the "
                           "connection (online models download once)", 9000)
                return
        for k in keys:
            ent = names.setdefault(k, {})
            if lk:
                ent["lib"] = {"key": lk, "fit": fit.currentData(),
                              "rot": rot.currentData(), "name": e["name"],
                              **({"entry": e["entry"]} if e.get("entry")
                                 else {})}
            else:
                ent.pop("lib", None)
        lab = e["name"] if e else ""
        self.commit(doc, f"{what}: {lab}" if lk else
                    f"{what}: CAD2IngeTrazo's own model again")

    def mirror_type(self, key, axis, on=None):
        """Every element of the type ``key`` mirrored (or back) about its own
        middle: ``axis`` "x" left ↔ right, "y" front ↔ back."""
        from . import components as CP
        doc = self.doc()
        cat = CP.catalogue(doc)
        t = cat.get(key)
        if not t:
            return
        ent = doc.setdefault("comp_names", {}).setdefault(key, {})
        m = dict(ent.get("mirror") or {})
        m[axis] = (not m.get(axis)) if on is None else bool(on)
        m = {k: v for k, v in m.items() if v}
        if m:
            ent["mirror"] = m
        else:
            ent.pop("mirror", None)
        what = {"x": "left ↔ right", "y": "front ↔ back"}[axis]
        self.commit(doc, f"Type {t['mark']} ({len(t['items'])}): "
                         f"{'mirrored ' + what if m.get(axis) else 'mirror ' + what + ' off'}")

    def edit_type(self, key):
        """The type's fields (its first element's) in a dialog: what is
        changed there changes on EVERY element of the type."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        from . import components as CP
        doc = self.doc()
        t = CP.catalogue(doc).get(key)
        if not t or not t["items"]:
            return
        kind, rid, _lv = t["items"][0]
        rec = PJ.find_record(doc, kind, rid)
        if rec is None:
            return
        skip = {"pos", "name", "angle", "x", "y"}
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Type {CP.display(t)} — {len(t['items'])} "
                           "elements")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"<b>{CP.display(t)}</b><br><i>Changes go to "
                             f"all {len(t['items'])} elements of this "
                             "type.</i>"))
        form = QFormLayout()
        lay.addLayout(form)
        fk = "opening" if kind == "opening" else kind
        saved = FIELDS.get(fk, [])
        FIELDS[fk] = [f_ for f_ in saved if f_[0] not in skip]
        try:
            widgets = self._build_fields(form, fk, rec)
        finally:
            FIELDS[fk] = saved
        mir0 = t.get("mirror") or {}
        mx = QCheckBox("Left ↔ right")
        my = QCheckBox("Front ↔ back")
        mx.setChecked(bool(mir0.get("x")))
        my.setChecked(bool(mir0.get("y")))
        mrow = QHBoxLayout()
        mrow.addWidget(mx)
        mrow.addWidget(my)
        form.addRow("Mirror", mrow)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlg.adjustSize()
        _place_on_screen(dlg, QCursor.pos())
        if dlg.exec() != QDialog.Accepted:
            return
        new = self._values_of(widgets, rec)
        changed = {k: v for k, v in new.items() if v != rec.get(k)}
        mir1 = {k: True for k, w_ in (("x", mx), ("y", my))
                if w_.isChecked()}
        mir_changed = mir1 != {k: True for k, v in mir0.items() if v}
        if not changed and not mir_changed:
            return
        doc = self.doc()
        if mir_changed:
            ent = doc.setdefault("comp_names", {}).setdefault(key, {})
            if mir1:
                ent["mirror"] = mir1
            else:
                ent.pop("mirror", None)
        if not changed:
            self.commit(doc, f"Type {t['mark']}: mirror "
                             + (", ".join({"x": "left ↔ right",
                                           "y": "front ↔ back"}[k]
                                          for k in mir1) or "off"))
            return
        n, bad = 0, []
        for kind_, rid_, _l in t["items"]:
            r = PJ.find_record(doc, kind_, rid_)
            if r is None:
                continue
            nr = dict(r, **changed)
            if kind_ == "opening":
                if nr.get("kind") == "door":
                    nr["sill"] = 0.0
                PJ.fit_head(nr)
            why = PJ.check_record(doc, kind_, nr)
            if why:
                bad.append(why)
                continue
            r.update(nr)
            n += 1
        # the type's mark goes with its elements to their new type
        newkey = CP.key_of(doc, kind, PJ.find_record(doc, kind, rid))
        names = doc.setdefault("comp_names", {})
        if newkey and newkey != key and newkey not in names \
                and key in names:
            names[newkey] = dict(names[key])
            names.pop(key, None)
        msg = f"Type {t['mark']}: {n} changed"
        if bad:
            msg += f" ({len(bad)} not — {bad[0]})"
        self.commit(doc, msg)

    def _values_of(self, widgets, rec) -> dict:
        out = {}
        for key, (typ, w) in widgets.items():
            if typ == "info":
                continue
            if typ == "choice":
                out[key] = w._opts[w.currentIndex()]
            elif typ == "height":
                out[key] = "level" if w._cb.isChecked() else w._sp.value()
            elif typ == "text":
                out[key] = w.text().strip() or rec.get(key, "")
            elif typ == "pct":
                out[key] = round(w.value(), 2)
            else:
                v = round(w.value(), 4)
                old = rec.get(key)
                # untouched: the record's own value (no rounding drift)
                if isinstance(old, (int, float)) and abs(float(old) - v) \
                        < 5e-4:
                    v = old
                out[key] = v
        out.pop("slope", None)
        if "top_att" in out:             # a wall type edited: as attached
            out = PJ.wall_attach(self.doc(), rec, out.pop("top_att", None),
                                 out.pop("bot_att", None), out)
        return out

    def _cp_save_names(self):
        from . import components as CP
        doc = self.doc()
        cat = CP.catalogue(doc)
        names = doc.setdefault("comp_names", {})
        n = 0
        for i, k in enumerate(self._cp_keys):
            it = self.cp_table.item(i, 1)
            if it is None or k not in cat:
                continue
            txt = it.text().strip()
            v = names.setdefault(k, {"mark": cat[k]["mark"]})
            if not txt or txt == cat[k]["label"]:
                if v.pop("name", None) is not None:
                    n += 1
            elif txt != v.get("name"):
                v["name"] = txt[:80]
                n += 1
        if n:
            self.commit(doc, f"{n} component name(s) saved")

    # ---- 8. sheets & export -------------------------------------------------------
    def _sheets_part(self):
        box, body = _fold("11  Plans, sheets and export", "sheets")
        f = _form(body)
        self.c_dims = QCheckBox("Dimensions")
        self.c_roomlbl = QCheckBox("Room names + areas")
        self.c_texts = QCheckBox("CAD texts")
        f.addRow(QLabel("<i>In the plan views (never in 3D):</i>"))
        f.addRow(self.c_dims)
        f.addRow(self.c_roomlbl)
        f.addRow(self.c_texts)
        self.c_cadlines = QCheckBox("The CAD's linework (its line weights "
                                    "and line types)")
        self.c_cadlines.setChecked(True)
        self.c_cadlines.toggled.connect(self.set_cad_lines)
        f.addRow(self.c_cadlines)
        self.c_marks = QCheckBox("Floor level marks (FFL / the CAD's LEV.)")
        self.c_marks.setChecked(True)
        f.addRow(self.c_marks)
        self.c_cars = QCheckBox("Number the parking bays (P1, P2… and the "
                                "car count)")
        self.c_cars.setChecked(True)
        f.addRow(self.c_cars)
        from . import cars as CARS
        self.c_carlib = QCheckBox("A car in every parking bay (IngeTrazo "
                                  "library model, 3D and plan)")
        self.c_carlib.setChecked(True)
        self.c_carmodel = QComboBox()
        for k_, lab_ in CARS.MODELS:
            self.c_carmodel.addItem(lab_, k_)
        rowc = QHBoxLayout()
        rowc.addWidget(self.c_carlib, 1)
        rowc.addWidget(self.c_carmodel)
        f.addRow(rowc)
        rowb = QHBoxLayout()            # motorbikes: a library model too
        self.c_bikemodel = QLabel("Motorbike: library (first found)")
        self.c_bikemodel.setWordWrap(True)
        rowb.addWidget(self.c_bikemodel, 1)
        rowb.addWidget(_btn("Pick…", self._pick_bike,
                            "The motorbike model from IngeTrazo's library "
                            "(More components ▸ Vehicles…)"))
        rowb.addWidget(_btn("Auto", lambda: self._set_bike(None),
                            "The first motorbike / scooter in the library"))
        f.addRow(rowb)
        f.addRow(_btn("Update plans", lambda: self.commit(
            self.doc(), "Plans updated")))
        f.addRow(QLabel("<i>Column grid:</i>"))
        self.gr_on = QCheckBox("Column grid in the plans (1, 2, 3 / A, B, C)")
        f.addRow(self.gr_on)
        self.gr_src = QComboBox()
        for k, label in (("columns", "From the columns"),
                         ("corners", "From the wall corners"),
                         ("spacing", "Bays I type"),
                         ("cad", "As drawn in the CAD plan")):
            self.gr_src.addItem(label, k)
        f.addRow("Axes", self.gr_src)
        self.gr_xs = QLineEdit()
        self.gr_xs.setPlaceholderText("e.g. 4.2, 4.2, 3.6")
        self.gr_ys = QLineEdit()
        self.gr_ys.setPlaceholderText("e.g. 5, 4.5")
        f.addRow("Bays along X (m)", self.gr_xs)
        f.addRow("Bays along Y (m)", self.gr_ys)
        row = QHBoxLayout()
        self.gr_ox = _spin(-1e4, 1e4, 0.0, 0.1)
        self.gr_oy = _spin(-1e4, 1e4, 0.0, 0.1)
        row.addWidget(self.gr_ox)
        row.addWidget(self.gr_oy)
        f.addRow("First axes at X, Y", row)
        self.gr_ext = _spin(0.3, 10, 2.2)
        f.addRow("Axes beyond the building", self.gr_ext)
        f.addRow(_btn("Apply grid", self._grid, primary=True))
        self.x_paper = QComboBox()
        self.x_paper.addItems(["A3", "A2", "A1", "A4"])
        self.x_scale = QComboBox()
        for k in ("auto", "50", "75", "100", "125", "200"):
            self.x_scale.addItem("Auto" if k == "auto" else f"1:{k}", k)
        self.s_cut = _spin(0.3, 3.0, 1.20)
        self.x_elev = QCheckBox("Four elevations")
        self.x_sect = QCheckBox("Sections A-A, B-B")
        self.x_dims = QCheckBox("Dimensions on the plans")
        f.addRow("Paper", self.x_paper)
        f.addRow("Scale", self.x_scale)
        f.addRow("Plan cut height", self.s_cut)
        f.addRow(self.x_elev)
        f.addRow(self.x_sect)
        f.addRow(self.x_dims)
        self.x_units = QComboBox()
        self.x_units.addItem("As the drawing (its units)", "drawing")
        self.x_units.addItem("Metric (m, m²)", "metric")
        self.x_units.addItem("Imperial (ft-in, ft²)", "imperial")
        self.x_units.setToolTip("The dimensions and room areas on the "
                                "sheets: the drawing's own units (default), or metric / "
                                "imperial whatever the drawing is in")
        f.addRow("Sheet units", self.x_units)
        # the line weights of the sheets (paper mm)
        self.x_pens = {}
        rowp = QHBoxLayout()
        for k, lab, tip in (("cut", "Cut", "What the section plane cuts: "
                             "walls, columns in the plan"),
                            ("profile", "Profile", "Outlines and "
                             "silhouettes"),
                            ("edge", "Edge", "The plain edges seen beyond"),
                            ("dim", "Dim", "The dimension lines")):
            sp = _spin(0.05, 2.0, {"cut": 0.5, "profile": 0.35, "edge": 0.18,
                                   "dim": 0.18}[k], 0.05, 2, " mm")
            sp.setToolTip(f"{tip} — line weight on paper (mm)")
            rowp.addWidget(QLabel(lab))
            rowp.addWidget(sp)
            self.x_pens[k] = sp
        f.addRow("Line weights", rowp)
        f.addRow(_btn("Apply line weights to the sheets", self._sheet_pens,
                      "The sheets already made take the new line weights "
                      "(and «Make sheets» uses them from now on)"))
        f.addRow(_btn("Make sheets", self.make_sheets, "A plan per level, "
                      "elevations, sections, rooms, title blocks — made "
                      "again, it replaces only its own sheets", primary=True))
        row = QHBoxLayout()
        row.addWidget(_btn("Open", self.open_sheets))
        row.addWidget(_btn("PDF…", self.export_pdf))
        row.addWidget(_btn("DXF…", self.export_dxf))
        f.addRow(row)
        f.addRow(_btn("Export the model to SketchUp (.skp)…", self.export_skp,
                      "The whole 3D model — walls, slabs, doors and windows, "
                      "stairs, ramps, cars, landscape — as a SketchUp file "
                      "(IngeTrazo's own SKP writer; a Collada .dae for "
                      "SketchUp's importer when that writer is missing)"))
        self.lay.addWidget(box)

    def _grid(self):
        doc = self.doc()

        def nums(text):
            out = []
            for v in text.replace(";", ",").split(","):
                try:
                    out.append(float(v))
                except ValueError:
                    pass
            return out
        doc["grid"] = SITE_.load_grid({
            "lines": doc["grid"].get("lines") or [],
            "on": self.gr_on.isChecked(), "source": self.gr_src.currentData(),
            "xs": nums(self.gr_xs.text()), "ys": nums(self.gr_ys.text()),
            "ox": self.gr_ox.value(), "oy": self.gr_oy.value(),
            "ext": self.gr_ext.value()})
        if doc["grid"]["source"] == "cad":
            n = len(doc["grid"].get("lines") or [])
            if doc["grid"]["on"] and not n:
                self.flash("No grid in the CAD plans — its axes are read on "
                           "import from a GRID / AXIS layer", 9000)
                return
            self.commit(doc, f"Grid: {n} axes from the CAD plan")
            return
        xs, ys = SITE_.axes(doc["arch"], doc["grid"])
        if doc["grid"]["on"] and not xs and not ys:
            self.flash("No axes found — add columns, or type the bays")
            return
        self.commit(doc, f"Grid: {len(xs)} × {len(ys)} axes" if
                    doc["grid"]["on"] else "Grid off")

    def _fill_grid(self, doc):
        g = doc["grid"]
        self.gr_on.setChecked(g["on"])
        self.gr_src.setCurrentIndex(max(self.gr_src.findData(g["source"]), 0))
        if not self.gr_xs.hasFocus():
            self.gr_xs.setText(", ".join(f"{v:g}" for v in g["xs"]))
        if not self.gr_ys.hasFocus():
            self.gr_ys.setText(", ".join(f"{v:g}" for v in g["ys"]))
        self.gr_ox.setValue(g["ox"])
        self.gr_oy.setValue(g["oy"])
        self.gr_ext.setValue(g["ext"])

    def _sheet_opts(self):
        return {"paper": self.x_paper.currentText(),
                "scale": self.x_scale.currentData(),
                "cut": self.s_cut.value(),
                "elev": "yes" if self.x_elev.isChecked() else "no",
                "sect": "yes" if self.x_sect.isChecked() else "no",
                "dims": "yes" if self.x_dims.isChecked() else "no",
                "rooms": "yes", "prefix": "A-",
                "units": (self.x_units.currentData()
                          if hasattr(self, "x_units") else "drawing"),
                **{"pen_" + k: round(sp.value(), 3)
                   for k, sp in getattr(self, "x_pens", {}).items()}}

    def _pens_from_bar(self, pens, n):
        """The sheet window's line weights changed: kept, and shown here."""
        for k, sp in getattr(self, "x_pens", {}).items():
            if k in pens:
                sp.blockSignals(True)
                sp.setValue(float(pens[k]))
                sp.blockSignals(False)
        doc = self.doc()
        if any(doc["settings"].get("sheet_pen_" + k) != v
               for k, v in pens.items()):
            for k, v in pens.items():
                doc["settings"]["sheet_pen_" + k] = v
            PJ.store_only(self.vp, doc)

    def _sheet_pens(self):
        from . import sheets
        doc = self.doc()
        pens = sheets.pens_of(self._sheet_opts())
        for k, v in pens.items():
            doc["settings"]["sheet_pen_" + k] = v
        PJ.store_only(self.vp, doc)
        try:
            n = sheets.apply_pens(self.win, self.vp.scene, pens)
            sheets.sync_bar(self.win, pens)
        except Exception as e:  # noqa: BLE001
            log_error("panel.sheet_pens")
            self.flash(f"Line weights not applied — {e}", 8000)
            return
        self.flash(f"Line weights on {n} sheet(s): cut {pens['cut']} · "
                   f"profile {pens['profile']} · edge {pens['edge']} · "
                   f"dimensions {pens['dim']} mm" if n else
                   "Line weights kept — «Make sheets» will use them", 7000)

    def make_sheets(self):
        from . import sheets
        doc = self.doc()
        if hasattr(self, "x_units") and doc["settings"].get(
                "sheet_units", "drawing") != self.x_units.currentData():
            doc["settings"]["sheet_units"] = self.x_units.currentData()
            PJ.store_only(self.vp, doc)
            doc = self.doc()
        doc["arch"]["_plaster"] = float(doc["settings"].get("plaster_t",
                                                            0.0127) or 0.0)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            planes, views, sh = sheets.make(doc["arch"], M.elevations,
                                            self._sheet_opts())
            if not sh:
                self.flash("No walls yet — import a level first")
                return
            made, replaced = sheets.commit(self.vp, planes, views, sh)
            sheets.refresh_sheets(self.win)
        except Exception as e:  # noqa: BLE001
            log_error("panel.make_sheets")
            self.flash(f"Sheets not made — {e}", 9000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.flash(f"{made} sheets made" + (f" (in place of {replaced})"
                                            if replaced else "")
                   + "  ·  «Open» shows them  ·  Ctrl+Z undoes it", 8000)

    def open_sheets(self):
        from . import sheets
        sc = self.vp.scene
        first = next((i for i, c in enumerate(sc.compositions)
                      if sheets.is_ours(c)), None)
        if first is None:
            self.flash("No sheets yet — «Make sheets» first")
            return
        sheets.open_sheets(self.win, first)

    def export_pdf(self):
        from . import sheets
        if not any(sheets.is_ours(c) for c in self.vp.scene.compositions):
            self.flash("No sheets yet — «Make sheets» first")
            return
        name = (self.doc()["arch"].get("project") or {}).get("name") \
            or "CAD2IngeTrazo"
        start = os.path.join(os.path.expanduser("~"), "".join(
            ch for ch in name if ch not in '\\/:*?"<>|') + ".pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Export sheets to PDF",
                                              start, "PDF (*.pdf)")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            bad = sheets.export_pdf(self.win, path)
        finally:
            QApplication.restoreOverrideCursor()
        self.flash(f"PDF written: {path}" + (f" — could not draw: "
                                             f"{', '.join(bad)}" if bad
                                             else ""), 9000)

    def export_skp(self):
        """The model as ONE SketchUp .skp (components, groups, tags,
        colours) — written by CAD2IngeTrazo with the OpenSKP writer that
        ships inside IngeTrazo; nothing else is written beside it."""
        doc = self.doc()
        name = str((doc["arch"].get("project") or {}).get("name") or
                   "CAD2IngeTrazo model").strip() or "CAD2IngeTrazo model"
        start = os.path.join(os.path.expanduser("~"), name + ".skp")
        path, _f = QFileDialog.getSaveFileName(
            self, "Export the model to SketchUp", start,
            "SketchUp model (*.skp)")
        if not path:
            return
        if not path.lower().endswith(".skp"):
            path += ".skp"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            from . import skpwriter
            st = skpwriter.save_skp(self.vp.scene, path)
        except Exception as e:  # noqa: BLE001
            log_error("panel.export_skp")
            self.flash(f"SketchUp file not written — {e}", 12000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.flash(f"SketchUp model written: {path} — {st['definitions']} "
                   f"components ({st['instances']} placed), {st['groups']} "
                   f"groups, {st['faces']:,} faces", 12000)

    def export_dxf(self):
        from . import sheets, sheetsdxf
        if not any(sheets.is_ours(c) for c in self.vp.scene.compositions):
            self.flash("No sheets yet — «Make sheets» first")
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Export the drawings to DXF — a folder",
            os.path.expanduser("~"))
        if not folder:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            files = sheetsdxf.export_all(self.win, self.doc()["arch"],
                                         M.elevations, folder,
                                         self._sheet_opts())
        except Exception as e:  # noqa: BLE001
            log_error("panel.export_dxf")
            self.flash(f"DXF not written — {e}", 9000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.flash(f"{len(files)} DXF files written to {folder}", 9000)

    # ---- preferences and refresh ----------------------------------------------------
    def _settings_from_ui(self):
        return {"door_h": self.o_door_h.value(), "win_h": self.o_win_h.value(),
                "sill": self.o_sill.value(), "slab_on": self.s_slab.isChecked(),
                "slab_t": self.s_slab_t.value(), "beam_h": self.s_bh.value(),
                "tmin": self.i_tmin.value(), "tmax": self.i_tmax.value(),
                "win_style": self.o_wstyle.currentData(),
                "levels_cad": self.i_levels.isChecked(),
                "floor_h_v2": self.i_floor_h.value(),
                "door_style": self.o_dstyle.currentData(),
                "door2_style": self.o_d2style.currentData(),
                "door_head": self.o_dhead.currentData(),
                "win_head": self.o_whead.currentData(),
                "door_frame": self.o_dframe.currentData(),
                "win_frame": self.o_wframe.currentData(),
                **{k: e.text() for k, e in self.i_layers.items()}}

    def _load_prefs(self):
        s = _settings()
        d = PJ.DEFAULTS
        for k, e in self.i_layers.items():
            e.setText(str(s.value(f"layers/{k}", d[k])))
        g = lambda k, dv: float(s.value(k, dv))  # noqa: E731
        b = lambda k, dv: str(s.value(k, dv)).lower() in ("true", "1")  # noqa: E731
        self.i_tmin.setValue(g("tmin", d["tmin"]))
        self.i_tmax.setValue(g("tmax", d["tmax"]))
        self.o_door_h.setValue(g("door_h", d["door_h"]))
        self.i_floor_h.setValue(g("floor_h_v2", 3.048))
        self.o_win_h.setValue(g("win_h", d["win_h"]))
        self.o_sill.setValue(g("sill", d["sill"]))
        self.s_slab.setChecked(b("slab_on", d["slab_on"]))
        self.s_slab_t.setValue(g("slab_t", d["slab_t"]))
        self.i_file.setText(str(s.value("file", "")))
        k = self.o_wstyle.findData(str(s.value("win_style", "sliding")))
        self.o_wstyle.setCurrentIndex(max(k, 0))
        for cb_, key_, dv_ in ((self.o_dstyle, "door_style", "hinged"),
                               (self.o_d2style, "door2_style", "hinged"),
                               (self.o_dhead, "door_head", "flat"),
                               (self.o_whead, "win_head", "flat"),
                               (self.o_dframe, "door_frame", "auto"),
                               (self.o_wframe, "win_frame", "auto")):
            cb_.setCurrentIndex(max(cb_.findData(str(s.value(key_, dv_))), 0))
        self.i_munits.blockSignals(True)
        self.i_munits.setCurrentIndex(max(self.i_munits.findData(
            str(s.value("units_mode", "auto"))), 0))
        self.i_munits.blockSignals(False)
        k = self.g_mode.findData(str(s.value("ghost", "below")))
        self.g_mode.setCurrentIndex(max(k, 0))
        ghost.MODE = self.g_mode.currentData()
        for c, k in ((self.c_dims, "ann_dims"), (self.c_roomlbl, "ann_rooms"),
                     (self.c_texts, "ann_texts"), (self.x_elev, "x_elev"),
                     (self.x_sect, "x_sect"), (self.x_dims, "x_dims")):
            c.setChecked(b(k, True))

    def _save_prefs(self, how=None):
        s = _settings()
        for k, e in self.i_layers.items():
            s.setValue(f"layers/{k}", e.text())
        for k, v in self._settings_from_ui().items():
            if k not in self.i_layers:
                s.setValue(k, v)
        s.setValue("file", self.i_file.text())
        for c, k in ((self.c_dims, "ann_dims"), (self.c_roomlbl, "ann_rooms"),
                     (self.c_texts, "ann_texts"), (self.x_elev, "x_elev"),
                     (self.x_sect, "x_sect"), (self.x_dims, "x_dims")):
            s.setValue(k, c.isChecked())

    def refresh(self):
        """Read the document again (an edit, Ctrl+Z, New, Open)."""
        try:
            doc = self.doc()
        except Exception:  # noqa: BLE001
            log_error("panel.refresh")
            return
        if self._follow_moves(doc):
            return                     # rebuilt: refresh runs again
        try:                           # a shape drawn on a wall / slab face
            if self._auto_openings(doc):
                return                 # rebuilt: refresh runs again
        except Exception:  # noqa: BLE001
            log_error("panel._auto_openings")
        self._building = True
        try:
            for cb, key in ((self.c_marks, "marks_on"),
                            (self.c_cadlines, "cad_lines"),
                            (self.c_cars, "park_nums"),
                            (self.c_carlib, "cars_lib")):
                cb.blockSignals(True)
                cb.setChecked(bool(doc["settings"].get(key, True)))
                cb.blockSignals(False)
            for cb in (getattr(self, "c_cadlines_top", None),
                       getattr(self, "_tb_cad", None)):
                if cb is not None:
                    cb.blockSignals(True)
                    cb.setChecked(bool(doc["settings"].get("cad_lines",
                                                           True)))
                    cb.blockSignals(False)
            self.i_gffl.blockSignals(True)
            self.i_gffl.setValue(float(doc["settings"].get("ground_ffl", 0.6096)
                                       or 0.0))
            self.i_gffl.blockSignals(False)
            i_ = self.c_carmodel.findData(doc["settings"].get("car_model",
                                                              "suv"))
            self.c_carmodel.blockSignals(True)
            self.c_carmodel.setCurrentIndex(max(i_, 0))
            self.c_carmodel.blockSignals(False)
            bl_ = doc["settings"].get("bike_lib") or {}
            self.c_bikemodel.setText("Motorbike: " + (bl_.get("name") or
                                     "library (first found)"))
            cur = self.level_box.currentData()
            self.level_box.clear()
            read = [k for k in doc["imports"] if k not in VIRTUAL
                    and not k.startswith("__")]
            if read:                   # a plan read: the next floor offered
                self.level_box.addItem(f"＋ {self._next_name(doc)}  (new, "
                                       "above)", NEW)
            for lv in reversed(doc["arch"]["levels"]):
                mark = "  ✓" if lv["id"] in doc["imports"] else ""
                kind = "  · basement" if lv["kind"] == "basement" else ""
                self.level_box.addItem(lv["name"] + kind + mark, lv["id"])
            if read:
                roof = any(lv["name"] == "Roof" for lv in doc["arch"]["levels"])
                self.level_box.insertItem(
                    0, "＋ Roof level  (terrace, parapet)" if not roof
                    else "↻ Roof level  (make again)", ROOF_NEW)
                self.level_box.addItem("＋ Basement  (new, below)", NEW_BELOW)
                self.level_box.addItem(
                    "Foundation" + ("  ✓" if FOUNDATION in doc["imports"]
                                    else ""), FOUNDATION)
            self.level_box.addItem(
                "Site · ground (plot, boundary wall, gates)"
                + ("  ✓" if doc["arch"].get("plot") else ""), SITE_LV)
            ids = [self.level_box.itemData(i)
                   for i in range(self.level_box.count())]
            ground = next(lv["id"] for lv in doc["arch"]["levels"]
                          if lv["kind"] == "ground")
            self.level_box.setCurrentIndex(ids.index(cur) if cur in ids
                                           else ids.index(ground))
            proj = doc["arch"].get("project") or {}
            for e, k in ((self.p_name, "name"), (self.p_client, "client"),
                         (self.p_author, "author"), (self.p_loc, "location")):
                if not e.hasFocus():
                    e.setText(proj.get(k, "") or "")
            self._fill_levels(doc)
            self._fill_north(doc)
        finally:
            self._building = False
        self._fill_rooms(doc)
        try:
            if self.cp_table.isVisible():
                self._fill_components(doc)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_components")
        try:
            self._fill_materials(doc)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_materials")
        try:
            ch = PJ.cad_changed(doc)
            self.i_changed.setText(
                "⚠ The CAD plan changed since its import (" + ", ".join(ch)
                + ") — «Update from CAD»" if ch else "")
        except Exception:  # noqa: BLE001
            pass
        try:
            self._fill_stairs(doc)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_stairs")
        try:
            self._fill_grid(doc)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_grid")
        try:
            self._fill_overlap(doc)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_overlap")
        try:
            self._fill_plot(doc)
        except Exception:  # noqa: BLE001
            log_error("panel._fill_plot")
        self.s_found.setValue(float(doc["settings"].get("found_level", -1.5)))
        try:
            st_ = doc["settings"]
            self.s_rt.setValue(float(st_.get("retain_t", 0.3048)))
            self.c_lvgroups.blockSignals(True)
            self.c_lvgroups.setChecked(bool(st_.get("level_groups")))
            self.c_lvgroups.blockSignals(False)
            self.s_ftype.setCurrentIndex(max(self.s_ftype.findData(
                st_.get("found_type", "isolated_strip")), 0))
            self.s_raft_t.setValue(float(st_.get("raft_t", 0.6096)))
            self.s_raft_o.setValue(float(st_.get("raft_off", 0.6096)))
            self.st_well.setCurrentIndex(max(self.st_well.findData(
                st_.get("stair_well", "railing")), 0))
            self.s_bon.setCurrentIndex(max(self.s_bon.findData(
                st_.get("beam_on", "columns")), 0))
            self.s_bspan.setValue(float(st_.get("beam_span", 10.0)))
            self.s_sh.setChecked(bool(st_.get("shoring")))
            self.s_sh_kind.setCurrentIndex(max(self.s_sh_kind.findData(
                st_.get("shoring_type", "piles")), 0))
            self.s_sh_d.setValue(float(st_.get("shoring_d", 0.6096)))
            self.s_sh_on.setCurrentIndex(max(self.s_sh_on.findData(
                st_.get("shoring_on", "plot")), 0))
            self.s_sh_e.setValue(float(st_.get("shoring_embed", 3.048)))
        except Exception:  # noqa: BLE001
            log_error("panel shoring fill")
        self.s_slab_pos.blockSignals(True)
        self.s_slab_pos.setCurrentIndex(max(self.s_slab_pos.findData(
            doc["settings"].get("slab_pos", "top")), 0))
        self.s_slab_pos.blockSignals(False)
        if self._sel_key:
            self._fill_selected()
        self._show_portion()
        self.retune_units()
