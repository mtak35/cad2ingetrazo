# SPDX-License-Identifier: GPL-3.0-or-later
"""Walkthrough of the model, room by room (Extensions ▸ CAD2IngeTrazo ▸
Walkthrough).

Pick a room: the eye goes to it at eye height above its floor, looking
along the room's longest side, the floors above (and the roof) hidden so
the room is seen with its ceiling, and IngeTrazo's First Person tool takes
over — W/A/S/D or the arrows to walk, the mouse to look. «Next room» /
«Previous room» step through the level's rooms; «End walkthrough» puts
back the floors hidden and the camera as it was.

Community module (GPL-3.0-or-later).
"""
from __future__ import annotations

import math

#: the eye above the floor (the host's own default, 5' 6")
EYE = 1.68

_state = {"cam": None, "hidden": [], "rooms": [], "i": -1, "lid": None}


def _eye_h() -> float:
    try:
        from tools.walkthrough import eye_height
        return float(eye_height())
    except Exception:  # noqa: BLE001
        return EYE


def rooms(doc, lid) -> list:
    """[(name, polygon)] of the level's rooms, biggest first (the halls
    and bedrooms before the stores)."""
    from .engine import spaces
    out = []
    try:
        for r in spaces.of_level(doc["arch"], lid):
            p = r.get("poly")
            if p is None or p.is_empty or p.area < 2.0:
                continue
            import re
            if re.search(r"\b(VOID|DUCT|SHAFT|OTS|LIFT|OPEN\s*TO\s*SKY)\b",
                         str(r.get("name") or ""), re.I):
                continue                  # nothing to walk into
            out.append((str(r.get("name") or "Room"), p))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("walk.rooms")
    out.sort(key=lambda t: -t[1].area)
    return out


def _floor_z(panel, doc, lid) -> float:
    from . import project as PJ
    arch = doc["arch"]
    try:
        el = PJ.elevations(arch)
        k = [lv["id"] for lv in arch["levels"]].index(lid)
        return float(el[k])
    except Exception:  # noqa: BLE001
        return 0.0


def _hide_above(panel, lid):
    """The floors above ``lid`` and the roofs hidden (kept to put back)."""
    from . import project as PJ
    doc = panel.doc()
    arch = doc["arch"]
    try:
        el = PJ.elevations(arch)
        ids = [lv["id"] for lv in arch["levels"]]
        z0 = el[ids.index(lid)]
        above = {i for i, z in zip(ids, el) if z > z0 + 0.05}
    except Exception:  # noqa: BLE001
        above = set()
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


def _stand(panel, name, poly, lid):
    """The eye in the room ``poly``: at its middle (a point surely inside),
    looking along its longest side, toward the far end."""
    from PySide6.QtGui import QVector3D
    doc = panel.doc()
    c = poly.representative_point() if not poly.contains(poly.centroid) \
        else poly.centroid
    rr = poly.minimum_rotated_rectangle
    cs = list(rr.exterior.coords)[:4]
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    d = e1 if math.hypot(*e1) >= math.hypot(*e2) else e2
    L = math.hypot(*d) or 1.0
    d = (d[0] / L, d[1] / L)
    # step back toward one end so the room is in front of the eye
    back = min(L * 0.35, 2.5)
    ex, ey = c.x - d[0] * back, c.y - d[1] * back
    from shapely.geometry import Point
    if not poly.buffer(-0.3).contains(Point(ex, ey)):
        ex, ey = c.x, c.y
    z = _floor_z(panel, doc, lid) + _eye_h()
    cam = panel.vp.camera
    try:
        cam.perspective = True
        cam.fov_deg = max(float(getattr(cam, "fov_deg", 45.0)), 60.0)
    except Exception:  # noqa: BLE001
        pass
    cam.distance = 0.5
    cam.look_from(QVector3D(ex, ey, z), QVector3D(d[0], d[1], -0.08))
    panel.vp.update()
    try:
        panel.flash(f"Walkthrough · {name} — W/A/S/D or arrows to walk, "
                    "mouse to look; Esc ends the tool")
    except Exception:  # noqa: BLE001
        pass


def _first_person(panel):
    """IngeTrazo's First Person tool (else its Walk / Look Around)."""
    win = getattr(panel.app, "window", None)
    for key in ("first_person", "walk", "look_around"):
        try:
            if win is not None and key in getattr(win, "_tools", {}):
                win._activate_tool(key)
                return key
        except Exception:  # noqa: BLE001
            continue
    return None


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
    cam = panel.vp.camera
    if _state["cam"] is None:
        _state["cam"] = (QVector3D(cam.target), cam.distance, cam.yaw,
                         cam.pitch, getattr(cam, "fov_deg", 45.0),
                         getattr(cam, "perspective", True))
    if _state["lid"] != lid:
        _put_back()
        _state["hidden"] = _hide_above(panel, lid)
    _state.update(rooms=rs, lid=lid, i=index % len(rs))
    name, poly = rs[_state["i"]]
    _stand(panel, name, poly, lid)
    _first_person(panel)


def step(panel, k):
    if not _state["rooms"]:
        start(panel)
        return
    start(panel, _state["lid"], _state["i"] + k)


def end(panel):
    """The floors put back, the camera as before the walkthrough."""
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
    _state.update(cam=None, rooms=[], i=-1, lid=None)
    try:
        panel.app.window.activate_select_tool()
    except Exception:  # noqa: BLE001
        pass
    panel.vp.update()


def fill_menu(panel, menu):
    """The «Walkthrough» menu: the rooms of the level picked, next /
    previous, the end. Rebuilt each time it opens."""
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
    menu.addAction("Next room", lambda: step(panel, 1))
    menu.addAction("Previous room", lambda: step(panel, -1))
    menu.addSeparator()
    menu.addAction("End walkthrough (floors and camera back)",
                   lambda: end(panel))


__all__ = ["start", "step", "end", "rooms", "fill_menu"]
