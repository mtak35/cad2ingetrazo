"""3.64.56: lights for the whole model, rendered by IngeTrazo's own
«Render with Blender» extension (plugins/render_blender.py: the Render tab
of the side tray).

That extension keeps its lights and ambience in the document
(``scene.plugin_data["render_blender"] = {"ambience", "sun_scale",
"lights"}``) and hands them to Blender with the model. This dialog makes
those lights from the model, each set its own choice:

- the light fittings the model already shows (wall sconces and lanterns,
  the down-lights of canopies and frames, pillar lamps): found by their
  warm glass in the scene, so whatever draws them counts;
- every room lit from its ceiling (so the windows glow at night);
- the facades washed by ground up-lights along every outside wall;
- the terraces and porches lit from above.

Ours are named «C2I · …»: making them again replaces only them, never the
lights placed by hand in the Render tab. Then «Open the Render tab» or
«Render now» — Blender does the rest (Day: the Shadows panel's sun; Night:
these lights under a dark sky; Overcast: an even sky).
"""
from __future__ import annotations

import math

KEY = "render_blender"
TAG = "C2I · "
#: the glows the model's fittings are drawn with (ornament / modern:
#: sconces and down-lights; siteorn.LAMP_GLASS: lanterns, pillar lamps)
GLOWS = ((1.0, 0.86, 0.55), (0.98, 0.93, 0.70))

SETS = (
    ("fittings", "Light fittings on the model (wall lights, lanterns, "
                 "down-lights, pillar lamps)", 60.0, 2700),
    ("rooms", "Every room lit from its ceiling (windows glow at night)",
     150.0, 3000),
    ("wash", "Facades washed by ground up-lights", 600.0, 3000),
    ("terraces", "Terraces and porches lit from above", 120.0, 3000),
)


# ---- the document's render data ----------------------------------------------------
def state(scene) -> dict:
    data = getattr(scene, "plugin_data", {}) or {}
    raw = data.get(KEY) or {}
    if not isinstance(raw, dict):
        raw = {}
    return {"ambience": raw.get("ambience", "day"),
            "sun_scale": float(raw.get("sun_scale", 1.0) or 1.0),
            "lights": list(raw.get("lights") or [])}


def store(viewport, st) -> None:
    """Write the render data back: one undo step, as the Render tab does."""
    from core.history import SetPluginDataCommand
    viewport.history.execute(SetPluginDataCommand(KEY, st))
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    viewport.update()


def ours(lt) -> bool:
    return str(lt.get("name", "")).startswith(TAG)


# ---- what the model shows ----------------------------------------------------------
def fixtures(scene) -> list:
    """The light fittings the scene draws: [{"pos", "kind": "point" |
    "spot", "what"}] — clusters of faces in a fitting's warm glass."""
    pts = []
    for f, m in scene.iter_world_faces():
        c = (getattr(f, "attrs", None) or {}).get("color")
        if c is None or len(c) < 3:
            continue
        hit = None
        for k, g in enumerate(GLOWS):
            if all(abs(float(c[i]) - g[i]) < 0.015 for i in range(3)):
                hit = k
                break
        if hit is None:
            continue
        vs = [v.position for v in f.loop]
        if m is not None:
            vs = [m.map(v) for v in vs]
        if not vs:
            continue
        x = sum(v.x() for v in vs) / len(vs)
        y = sum(v.y() for v in vs) / len(vs)
        z = sum(v.z() for v in vs) / len(vs)
        pts.append((x, y, z, hit))
    # cluster: a fitting's faces lie within a few decimetres
    pts.sort()
    groups = []
    for p in pts:
        for g in groups:
            q = g["c"]
            if abs(p[0] - q[0]) < 0.35 and abs(p[1] - q[1]) < 0.35 and \
                    abs(p[2] - q[2]) < 0.45 and p[3] == g["k"]:
                g["p"].append(p)
                n = len(g["p"])
                g["c"] = tuple(sum(v[i] for v in g["p"]) / n
                               for i in range(3))
                break
        else:
            groups.append({"c": p[:3], "p": [p], "k": p[3]})
    out = []
    for g in groups:
        zs = [v[2] for v in g["p"]]
        x, y, z = g["c"]
        if g["k"] == 0 and max(zs) - min(zs) < 0.06:
            out.append({"pos": [x, y, z - 0.03], "kind": "spot",
                        "what": "down-light"})
        elif g["k"] == 0:
            out.append({"pos": [x, y, z], "kind": "point",
                        "what": "wall light"})
        else:
            out.append({"pos": [x, y, z], "kind": "point",
                        "what": "lantern"})
    return out


def _rooms(doc) -> list:
    """A light at every room's ceiling: [(pos, name)]."""
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    idx = {lv["id"]: i for i, lv in enumerate(levels)}
    out = []
    for r in arch.get("rooms") or []:
        i = idx.get(r.get("level"))
        if i is None or "x" not in r:
            continue
        h = float(levels[i]["height"])
        name = str(r.get("name") or "room")
        open_ = "terrace" in name.lower() or "roof" in name.lower()
        z = el[i] + (2.6 if open_ else max(2.2, h - 0.45))
        out.append(([float(r["x"]), float(r["y"]), z], name))
    return out


def _wash(doc, step=3.0) -> list:
    """Ground up-lights along every outside wall of the ground floor:
    [(pos, dir)] — each a little out from the face, aimed up it."""
    from . import stylekit as SK
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    out = []
    for fc in SK.faces_of(doc):
        if fc["i"] != g or fc["L"] < 1.0:
            continue
        f, L, face = fc["f"], fc["L"], fc["face"]
        n = max(1, int(L / step))
        for k in range(n):
            s = L * (k + 0.5) / n
            # not in front of a door
            if any(a - 0.2 < s < b + 0.2 and kind == "door"
                   for a, b, _za, _zb, kind, _o in fc["ops"]):
                continue
            p = f.P(s, face + 0.45, el[g] + 0.08)
            top = f.P(s, face, el[g] + 4.0)
            d = (top[0] - p[0], top[1] - p[1], top[2] - p[2])
            ln = math.sqrt(sum(v * v for v in d)) or 1.0
            out.append((list(p), [v / ln for v in d]))
    return out


def _terraces(doc) -> list:
    """Lights over the terraces and porches: the parking (car porch) and
    the roof terraces under a slab — [pos]."""
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    out = []
    for pk in (doc.get("parking") or {}).values():
        cars = pk.get("cars") or []
        for c in cars:
            cc = c.get("c")
            if cc:
                out.append([float(cc[0]), float(cc[1]),
                            el[g] + float(levels[g]["height"]) - 0.4])
    return out


def build(doc, scene, chosen: dict) -> list:
    """Our lights, by set: chosen = {set: (on, power scale, kelvin)}."""
    out = []

    def add(kind, pos, d, power, kelvin, name, angle=60.0):
        out.append({"kind": kind, "pos": [float(v) for v in pos],
                    "dir": [float(v) for v in d], "kelvin": int(kelvin),
                    "power": float(power), "angle": float(angle),
                    "on": True, "name": TAG + name})

    base = {k: (p, kv) for k, _l, p, kv in SETS}
    for key, (on, scale, kelvin) in chosen.items():
        if not on:
            continue
        p0 = base[key][0] * scale
        if key == "fittings":
            for n, fx in enumerate(fixtures(scene), 1):
                if fx["kind"] == "spot":
                    add("spot", fx["pos"], (0, 0, -1), p0 * 2.5, kelvin,
                        f"Fittings · {fx['what']} {n}", 70.0)
                else:
                    add("point", fx["pos"], (0, 0, -1),
                        p0 * (1.5 if fx["what"] == "lantern" else 1.0),
                        kelvin, f"Fittings · {fx['what']} {n}")
        elif key == "rooms":
            for n, (pos, name) in enumerate(_rooms(doc), 1):
                add("point", pos, (0, 0, -1), p0, kelvin,
                    f"Rooms · {name.title()} {n}")
        elif key == "wash":
            for n, (pos, d) in enumerate(_wash(doc), 1):
                add("spot", pos, d, p0, kelvin, f"Facade · up-light {n}", 45.0)
        elif key == "terraces":
            for n, pos in enumerate(_terraces(doc), 1):
                add("spot", pos, (0, 0, -1), p0 * 2.0, kelvin,
                    f"Porch · light {n}", 90.0)
    return out


# ---- the Render tab ----------------------------------------------------------------
def render_dock(window):
    from PySide6.QtWidgets import QDockWidget
    for d in window.findChildren(QDockWidget):
        if d.objectName().startswith("extension_" + KEY):
            return d
    return None


def render_panel(window):
    d = render_dock(window)
    if d is None:
        return None
    from PySide6.QtWidgets import QWidget
    for w in d.findChildren(QWidget):
        if type(w).__name__ == "RenderPanel":
            return w
    return None


def show_render_tab(window) -> bool:
    d = render_dock(window)
    if d is None:
        return False
    d.show()
    d.raise_()
    return True


# ---- the dialog --------------------------------------------------------------------
def _dialog_class():
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                   QDoubleSpinBox, QGridLayout, QHBoxLayout,
                                   QLabel, QPushButton, QSpinBox,
                                   QVBoxLayout)

    class LightingDialog(QDialog):
        """Lights for the whole model, rendered by Blender."""

        def __init__(self, panel):
            super().__init__(panel)
            self.panel = panel
            self.setWindowTitle("Lighting and Blender render")
            v = QVBoxLayout(self)
            intro = QLabel(
                "Lights made from the model for IngeTrazo's <b>Render with "
                "Blender</b> (the Render tab). Each set below is its own "
                "choice; making them again replaces only these "
                "(named «C2I · …») — lights you placed yourself stay.")
            intro.setWordWrap(True)
            v.addWidget(intro)
            self.where = QLabel("")
            self.where.setWordWrap(True)
            self.where.setStyleSheet("color: #8a94a3;")
            v.addWidget(self.where)
            row = QHBoxLayout()
            row.addWidget(QLabel("Ambience"))
            self.amb = QComboBox()
            for k, lab in (("night", "Night — the lights under a dark sky"),
                           ("day", "Day — the Shadows panel's sun (lights "
                                   "add a glow)"),
                           ("overcast", "Overcast — an even sky")):
                self.amb.addItem(lab, k)
            row.addWidget(self.amb, 1)
            v.addLayout(row)
            grid = QGridLayout()
            grid.addWidget(QLabel("<b>Light set</b>"), 0, 0)
            grid.addWidget(QLabel("<b>Power ×</b>"), 0, 1)
            grid.addWidget(QLabel("<b>Colour (K)</b>"), 0, 2)
            self.rows = {}
            for r, (key, label, _p, kelvin) in enumerate(SETS, 1):
                cb = QCheckBox(label)
                cb.setChecked(True)
                sc = QDoubleSpinBox()
                sc.setRange(0.1, 5.0)
                sc.setSingleStep(0.1)
                sc.setValue(1.0)
                kv = QSpinBox()
                kv.setRange(1800, 8000)
                kv.setSingleStep(100)
                kv.setValue(kelvin)
                grid.addWidget(cb, r, 0)
                grid.addWidget(sc, r, 1)
                grid.addWidget(kv, r, 2)
                self.rows[key] = (cb, sc, kv)
            grid.setColumnStretch(0, 1)
            v.addLayout(grid)
            self.note = QLabel("")
            self.note.setWordWrap(True)
            v.addWidget(self.note)
            b = QHBoxLayout()
            for text, fn, tip in (
                    ("Put the lights in", self._put,
                     "Make the lights and store them in the Render tab"),
                    ("Remove ours", self._remove,
                     "Take away the «C2I · …» lights (yours stay)"),
                    ("Open the Render tab", self._open,
                     "Bring IngeTrazo's Render with Blender tab forward"),
                    ("Render now", self._render,
                     "Put the lights in and render the current view in "
                     "Blender")):
                btn = QPushButton(text)
                btn.setToolTip(tip)
                btn.clicked.connect(fn)
                b.addWidget(btn)
            b.addStretch(1)
            close = QPushButton("Close")
            close.clicked.connect(self.close)
            b.addWidget(close)
            v.addLayout(b)
            self.resize(720, 420)
            self._refresh()

        # -- helpers
        def _vp(self):
            return self.panel.app.viewport

        def _refresh(self):
            st = state(self._vp().scene)
            amb = st["ambience"] if any(ours(lt) for lt in st["lights"]) \
                else "night"          # lights are seen best at night
            i = self.amb.findData(amb)
            if i >= 0:
                self.amb.setCurrentIndex(i)
            n_ours = sum(1 for lt in st["lights"] if ours(lt))
            n_hand = len(st["lights"]) - n_ours
            try:
                from core import render_blender as rb
                found = rb.find_blender()
                bl = (f"Blender: {found.where}" if found else
                      "Blender was not found — the Render tab says how to "
                      "get it or where to point it.")
            except Exception:  # noqa: BLE001
                bl = "Blender: as the Render tab finds it."
            tab = render_dock(self.panel.app.window)
            self.where.setText(
                bl + ("" if tab is not None else
                      "<br><b>The Render with Blender extension is not "
                      "loaded</b> — turn it on in Extensions.") +
                f"<br>In the document now: {n_ours} lights of ours, "
                f"{n_hand} of yours.")

        def _chosen(self):
            return {k: (cb.isChecked(), sc.value(), kv.value())
                    for k, (cb, sc, kv) in self.rows.items()}

        # -- actions
        def _put(self):
            vp = self._vp()
            doc = self.panel.doc()
            st = state(vp.scene)
            new = build(doc, vp.scene, self._chosen())
            st["lights"] = [lt for lt in st["lights"] if not ours(lt)] + new
            st["ambience"] = self.amb.currentData()
            store(vp, st)
            by = {}
            for lt in new:
                w = lt["name"][len(TAG):].split(" · ")[0].lower()
                by[w] = by.get(w, 0) + 1
            self.note.setText(
                f"<b>{len(new)} lights</b> put in the Render tab: " +
                ", ".join(f"{n} {w}" for w, n in sorted(by.items())) +
                ". Ctrl+Z takes them back.")
            self._refresh()
            try:
                p = render_panel(self.panel.app.window)
                if p is not None:
                    p.refresh_lights()
            except Exception:  # noqa: BLE001
                pass
            return True

        def _remove(self):
            vp = self._vp()
            st = state(vp.scene)
            n = sum(1 for lt in st["lights"] if ours(lt))
            st["lights"] = [lt for lt in st["lights"] if not ours(lt)]
            store(vp, st)
            self.note.setText(f"{n} lights of ours taken away.")
            self._refresh()

        def _open(self):
            if not show_render_tab(self.panel.app.window):
                self.note.setText("The Render with Blender extension is "
                                  "not loaded (Extensions ▸ manage).")

        def _render(self):
            self._put()
            self._open()
            p = render_panel(self.panel.app.window)
            if p is None:
                return
            try:
                p._start()
                self.note.setText(self.note.text() + "<br>Blender is "
                                  "rendering the current view — the Render "
                                  "tab shows its progress and the image.")
            except Exception as e:  # noqa: BLE001
                self.note.setText(f"Could not start the render: {e}")

    return LightingDialog


def open_dialog(panel):
    cls = _dialog_class()
    dlg = getattr(panel, "_light_dlg", None)
    try:
        if dlg is None or not dlg.isVisible():
            dlg = cls(panel)
            panel._light_dlg = dlg
        dlg.show()
        dlg.raise_()
    except RuntimeError:
        panel._light_dlg = cls(panel)
        panel._light_dlg.show()
