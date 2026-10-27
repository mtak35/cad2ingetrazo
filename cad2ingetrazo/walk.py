# SPDX-License-Identifier: GPL-3.0-or-later
"""Walkthrough of the model, room by room (the toolbar's «Walkthrough»
button, or Extensions ▸ CAD2IngeTrazo ▸ Walkthrough).

Pick a room (a click on the button: the biggest room of the level picked):
the eye goes into it at eye height, looking along the room, the floors
above (and the roofs) hidden so the room is seen under its own ceiling.
Then the walkthrough is its own mode until **Esc**:

* W / S or ↑ / ↓ — forward / back;  A / D — sideways;  ← / → — turn;
  Shift — faster.
* drag with the mouse (either button) — look round; the eye stays put.
* the wheel — the angle of view (wide angle up to 120°); 1 / 2 / 3 / 4 —
  60° / 75° / 90° / 110°.
* PgUp / PgDn — the floor above / below, at the same place.
* walls are no obstacle: you walk through them from room to room.
* the eye stays at eye level (no climbing, no falling, no flying out) and
  nothing else moves the camera away — zoom, orbit and the view buttons
  are held off — until Esc puts back the floors and the camera as they
  were.

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

import math

#: the eye above the floor (the host's own default, 5' 6")
EYE = 1.68
#: the angle of view when it starts (and with «Wide angle» on)
FOV = 75.0
WIDE = 100.0
WALK_SPEED = 1.4             # m/s
RUN = 3.0
TURN_SPEED = 90.0            # °/s with the arrows
LOOK_PER_PX = 0.25           # ° per pixel of drag

_state = {"cam": None, "hidden": [], "rooms": [], "i": -1, "lid": None,
          "on": False, "x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0,
          "pitch": 0.0, "fov": FOV, "wide": False, "held": set(),
          "drag": None, "filter": None, "timer": None, "panel": None,
          "last": None}


def _eye_h() -> float:
    try:
        from tools.walkthrough import eye_height
        return float(eye_height())
    except Exception:  # noqa: BLE001
        return EYE


def rooms(doc, lid) -> list:
    """[(name, polygon)] of the level's rooms, biggest first (the halls
    and bedrooms before the stores)."""
    import re

    from .engine import spaces
    out = []
    try:
        for r in spaces.of_level(doc["arch"], lid):
            p = r.get("poly")
            if p is None or p.is_empty or p.area < 2.0:
                continue
            if re.search(r"\b(VOID|DUCT|SHAFT|OTS|LIFT|OPEN\s*TO\s*SKY)\b",
                         str(r.get("name") or ""), re.I):
                continue                  # nothing to walk into
            out.append((str(r.get("name") or "Room"), p))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("walk.rooms")
    out.sort(key=lambda t: -t[1].area)
    return out


def _levels(doc):
    """[(id, name, elevation)] low to high."""
    from . import project as PJ
    arch = doc["arch"]
    try:
        el = PJ.elevations(arch)
    except Exception:  # noqa: BLE001
        el = [0.0] * len(arch["levels"])
    out = [(lv["id"], str(lv.get("name") or lv["id"]), float(z))
           for lv, z in zip(arch["levels"], el)]
    out.sort(key=lambda t: t[2])
    return out


def _floor_z(doc, lid) -> float:
    for i, _n, z in _levels(doc):
        if i == lid:
            return z
    return 0.0


def _hide_above(panel, lid):
    """The floors above ``lid`` and the roofs hidden (kept to put back)."""
    from . import project as PJ
    doc = panel.doc()
    z0 = _floor_z(doc, lid)
    above = {i for i, _n, z in _levels(doc) if z > z0 + 0.05}
    hid = []
    for g in PJ.all_groups(panel.vp.scene):
        t = PJ.tag_of(g) or {}
        if t.get("level") in above or t.get("type") == "roof":
            if not getattr(g, "hidden", False):
                g.hidden = True
                hid.append(g)
    return hid


def _put_back():
    for g in _state["hidden"]:
        try:
            g.hidden = False
        except Exception:  # noqa: BLE001
            pass
    _state["hidden"] = []


# ---- the camera ---------------------------------------------------------
def _apply(force=False):
    """The camera put where the walk says (every tick: whatever else moved
    it is undone, so the eye never leaves the building)."""
    from PySide6.QtGui import QVector3D
    p = _state["panel"]
    if p is None:
        return
    cam = p.vp.camera
    s = _state
    cy, sy = math.cos(math.radians(s["yaw"])), math.sin(math.radians(s["yaw"]))
    cp, sp = math.cos(math.radians(s["pitch"])), \
        math.sin(math.radians(s["pitch"]))
    pose = (round(s["x"], 4), round(s["y"], 4), round(s["z"], 4),
            round(s["yaw"], 3), round(s["pitch"], 3), round(s["fov"], 2))
    try:
        e = cam.eye()
        moved = abs(e.x() - s["x"]) + abs(e.y() - s["y"]) + \
            abs(e.z() - s["z"]) > 1e-3 or \
            abs(float(cam.fov_deg) - s["fov"]) > 0.01 or \
            not cam.perspective or abs(cam.distance - 0.3) > 1e-6
    except Exception:  # noqa: BLE001
        moved = True
    if not force and not moved and pose == s["last"]:
        return
    try:
        cam.perspective = True
        if getattr(cam, "two_point", False):
            cam.two_point = False
    except Exception:  # noqa: BLE001
        pass
    cam.fov_deg = s["fov"]
    cam.distance = 0.3
    cam.look_from(QVector3D(s["x"], s["y"], s["z"]),
                  QVector3D(cp * cy, cp * sy, sp))
    s["last"] = pose
    p.vp.update()


def _hint():
    p = _state["panel"]
    try:
        p.flash(f"Walkthrough — W/A/S/D or arrows, drag to look, wheel "
                f"= angle ({_state['fov']:.0f}°), PgUp/PgDn floors; "
                "Esc to come out")
    except Exception:  # noqa: BLE001
        pass


# ---- keys, mouse, the tick ----------------------------------------------
def _keys():
    from PySide6.QtCore import Qt
    return {Qt.Key_W, Qt.Key_S, Qt.Key_A, Qt.Key_D, Qt.Key_Up, Qt.Key_Down,
            Qt.Key_Left, Qt.Key_Right, Qt.Key_Shift}


def _tick():
    s = _state
    if not s["on"]:
        return
    from PySide6.QtCore import Qt
    dt = 0.016
    h = s["held"]
    run = RUN if Qt.Key_Shift in h else 1.0
    f = (1 if (Qt.Key_W in h or Qt.Key_Up in h) else 0) - \
        (1 if (Qt.Key_S in h or Qt.Key_Down in h) else 0)
    r = (1 if Qt.Key_D in h else 0) - (1 if Qt.Key_A in h else 0)
    t = (1 if Qt.Key_Right in h else 0) - (1 if Qt.Key_Left in h else 0)
    if t:
        s["yaw"] -= t * TURN_SPEED * dt
    if f or r:
        cy, sy = math.cos(math.radians(s["yaw"])), \
            math.sin(math.radians(s["yaw"]))
        v = WALK_SPEED * run * dt
        # level: the eye keeps its height whatever the head's tilt
        s["x"] += (f * cy + r * sy) * v
        s["y"] += (f * sy - r * cy) * v
    _apply()


def _change_floor(k):
    s = _state
    p = s["panel"]
    doc = p.doc()
    lv = _levels(doc)
    ids = [i for i, _n, _z in lv]
    if s["lid"] not in ids:
        return
    j = ids.index(s["lid"]) + k
    if not 0 <= j < len(ids):
        return
    _put_back()
    s["lid"] = ids[j]
    s["hidden"] = _hide_above(p, s["lid"])
    s["z"] = lv[j][2] + _eye_h()
    s["rooms"] = rooms(doc, s["lid"])
    _apply(True)
    try:
        p.flash(f"Walkthrough — {lv[j][1]}")
    except Exception:  # noqa: BLE001
        pass


def _make_filter():
    from PySide6.QtCore import QEvent, QObject, Qt

    class _Walk(QObject):
        def eventFilter(self, obj, ev):          # noqa: N802 (Qt)
            s = _state
            if not s["on"]:
                return False
            t = ev.type()
            vp = s["panel"].vp
            if t == QEvent.ShortcutOverride:
                k = ev.key()
                if k in _keys() or k in (Qt.Key_Escape, Qt.Key_PageUp,
                                         Qt.Key_PageDown, Qt.Key_1, Qt.Key_2,
                                         Qt.Key_3, Qt.Key_4):
                    if not ev.modifiers() & Qt.ControlModifier:
                        ev.accept()
                        return True
                return False
            if t == QEvent.KeyPress:
                if obj is not vp and k_text_input(obj):
                    return False
                k = ev.key()
                if k == Qt.Key_Escape:
                    end(s["panel"])
                    return True
                if ev.modifiers() & Qt.ControlModifier:
                    return False
                if k in _keys():
                    s["held"].add(k)
                    return True
                if k == Qt.Key_PageUp:
                    _change_floor(1)
                    return True
                if k == Qt.Key_PageDown:
                    _change_floor(-1)
                    return True
                fv = {Qt.Key_1: 60.0, Qt.Key_2: 75.0, Qt.Key_3: 90.0,
                      Qt.Key_4: 110.0}.get(k)
                if fv:
                    s["fov"] = fv
                    _apply(True)
                    _hint()
                    return True
                return obj is vp            # no tool shortcut meanwhile
            if t == QEvent.KeyRelease:
                k = ev.key()
                if k in _keys():
                    if not ev.isAutoRepeat():
                        s["held"].discard(k)
                    return True
                return obj is vp
            if obj is not vp:
                return False
            if t == QEvent.MouseButtonPress:
                s["drag"] = ev.position()
                vp.setFocus()
                return True
            if t == QEvent.MouseMove:
                if s["drag"] is not None:
                    q = ev.position()
                    dx, dy = q.x() - s["drag"].x(), q.y() - s["drag"].y()
                    s["drag"] = q
                    s["yaw"] -= dx * LOOK_PER_PX
                    s["pitch"] = max(-80.0, min(80.0, s["pitch"] -
                                                dy * LOOK_PER_PX))
                    _apply()
                return True
            if t in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
                s["drag"] = None
                return True
            if t == QEvent.Wheel:
                d = ev.angleDelta().y()
                s["fov"] = max(35.0, min(120.0, s["fov"] -
                                         (5.0 if d > 0 else -5.0)))
                _apply(True)
                _hint()
                return True
            if t == QEvent.ContextMenu:
                return True
            if t == QEvent.FocusOut:
                s["held"].clear()
            return False

    return _Walk()


def k_text_input(obj) -> bool:
    """A field being typed into (its keys are its own)."""
    try:
        from PySide6.QtWidgets import (QAbstractSpinBox, QLineEdit,
                                       QPlainTextEdit, QTextEdit)
        return isinstance(obj, (QLineEdit, QTextEdit, QPlainTextEdit,
                                QAbstractSpinBox))
    except Exception:  # noqa: BLE001
        return False


def _engage(panel):
    """The walk mode on: the events of the viewport (and Esc anywhere)
    are the walk's, the tick keeps the camera where the walk says."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    s = _state
    if s["on"]:
        return
    try:                                   # no host tool in the way
        panel.app.window.activate_select_tool()
    except Exception:  # noqa: BLE001
        pass
    f = _make_filter()
    s["filter"] = f
    panel.vp.installEventFilter(f)
    QApplication.instance().installEventFilter(f)
    tm = QTimer(panel.vp)
    tm.setInterval(16)
    tm.timeout.connect(_tick)
    tm.start()
    s["timer"] = tm
    s["on"] = True
    try:
        panel.vp.setFocus()
    except Exception:  # noqa: BLE001
        pass


def _disengage(panel):
    from PySide6.QtWidgets import QApplication
    s = _state
    s["on"] = False
    s["held"].clear()
    s["drag"] = None
    if s["timer"] is not None:
        try:
            s["timer"].stop()
        except Exception:  # noqa: BLE001
            pass
        s["timer"] = None
    if s["filter"] is not None:
        try:
            panel.vp.removeEventFilter(s["filter"])
            QApplication.instance().removeEventFilter(s["filter"])
        except Exception:  # noqa: BLE001
            pass
        s["filter"] = None


# ---- start / step / end -------------------------------------------------
def _stand(panel, name, poly, lid):
    """The eye in the room ``poly``: at its middle (a point surely inside),
    looking along its longest side, toward the far end."""
    from shapely.geometry import Point
    doc = panel.doc()
    c = poly.centroid if poly.contains(poly.centroid) else \
        poly.representative_point()
    rr = poly.minimum_rotated_rectangle
    cs = list(rr.exterior.coords)[:4]
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    d = e1 if math.hypot(*e1) >= math.hypot(*e2) else e2
    L = math.hypot(*d) or 1.0
    d = (d[0] / L, d[1] / L)
    back = min(L * 0.35, 2.5)              # back toward one end
    ex, ey = c.x - d[0] * back, c.y - d[1] * back
    if not poly.buffer(-0.3).contains(Point(ex, ey)):
        ex, ey = c.x, c.y
    s = _state
    s.update(x=ex, y=ey, z=_floor_z(doc, lid) + _eye_h(),
             yaw=math.degrees(math.atan2(d[1], d[0])), pitch=-3.0)
    _apply(True)
    try:
        panel.flash(f"Walkthrough · {name} — W/A/S/D or arrows, drag to "
                    "look, wheel = angle of view; Esc to come out")
    except Exception:  # noqa: BLE001
        pass


def start(panel, lid=None, index=0):
    """The walkthrough on level ``lid`` (the level picked at the top when
    None), in its room number ``index`` (biggest first)."""
    from PySide6.QtGui import QVector3D
    doc = panel.doc()
    if lid is None:
        lid, _lv = panel.level()
    if not lid:
        lid = (doc["arch"]["levels"] or [{}])[0].get("id")
    rs = rooms(doc, lid)
    if not rs:
        panel.flash("No rooms on this level to walk through")
        return
    s = _state
    s["panel"] = panel
    cam = panel.vp.camera
    if s["cam"] is None:
        s["cam"] = (QVector3D(cam.target), cam.distance, cam.yaw,
                    cam.pitch, getattr(cam, "fov_deg", 45.0),
                    getattr(cam, "perspective", True))
        s["fov"] = WIDE if s["wide"] else FOV
    if s["lid"] != lid:
        _put_back()
        s["hidden"] = _hide_above(panel, lid)
    s.update(rooms=rs, lid=lid, i=index % len(rs))
    name, poly = rs[s["i"]]
    _engage(panel)
    _stand(panel, name, poly, lid)


def step(panel, k):
    if not _state["rooms"]:
        start(panel)
        return
    start(panel, _state["lid"], _state["i"] + k)


def set_wide(panel, on):
    s = _state
    s["wide"] = bool(on)
    s["fov"] = WIDE if on else FOV
    if s["on"]:
        _apply(True)
        _hint()


def end(panel):
    """Out of the walkthrough: the floors put back, the camera as before."""
    _disengage(panel)
    _put_back()
    c = _state["cam"]
    if c is not None:
        cam = panel.vp.camera
        cam.target, cam.distance, cam.yaw, cam.pitch = c[0], c[1], c[2], c[3]
        try:
            cam.fov_deg = c[4]
            cam.perspective = c[5]
        except Exception:  # noqa: BLE001
            pass
    _state.update(cam=None, rooms=[], i=-1, lid=None, last=None)
    try:
        panel.flash("Walkthrough ended")
    except Exception:  # noqa: BLE001
        pass
    panel.vp.update()


def fill_menu(panel, menu):
    """The «Walkthrough» menu: the rooms of the level picked, other levels,
    wide angle, next / previous, the end. Rebuilt each time it opens."""
    menu.clear()
    doc = panel.doc()
    lid, lv = panel.level()
    if not lid:
        lid = (doc["arch"]["levels"] or [{}])[0].get("id")
        lv = (doc["arch"]["levels"] or [{}])[0]
    menu.addAction("Walk inside — the biggest room of "
                   f"{(lv or {}).get('name', lid)}",
                   lambda: start(panel, lid, 0))
    sub = menu.addMenu("Walk into a room…")
    for k, (name, poly) in enumerate(rooms(doc, lid)):
        sub.addAction(f"{name}  ({poly.area:.0f} m²)",
                      lambda kk=k: start(panel, lid, kk))
    lm = menu.addMenu("On another level…")
    for lv_ in doc["arch"]["levels"]:
        lm.addAction(str(lv_.get("name") or lv_["id"]),
                     lambda i_=lv_["id"]: start(panel, i_, 0))
    menu.addSeparator()
    a = menu.addAction(f"Wide angle ({WIDE:.0f}° view; the wheel sets "
                       "any angle)")
    a.setCheckable(True)
    a.setChecked(bool(_state["wide"]))
    a.toggled.connect(lambda on: set_wide(panel, on))
    menu.addSeparator()
    menu.addAction("Next room", lambda: step(panel, 1))
    menu.addAction("Previous room", lambda: step(panel, -1))
    menu.addSeparator()
    menu.addAction("End walkthrough (Esc)", lambda: end(panel))


__all__ = ["start", "step", "end", "rooms", "fill_menu", "set_wide"]
