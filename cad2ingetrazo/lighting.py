"""3.64.56–57: lights, materials and a real (HDRI) environment for the whole model, rendered with IngeTrazo's own
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
                 "down-lights)", 120.0, 2700),
    ("rooms", "Every room lit from its ceiling (windows glow at night)",
     300.0, 3000),
    ("wash", "Facades washed by ground up-lights", 900.0, 3000),
    ("grazers", "Wall grazers under every roof and terrace edge", 250.0,
     3000),
    ("terraces", "Porches and terraces lit from above", 300.0, 3000),
    ("garden", "Garden: bollards along the paths and lawns", 25.0, 2700),
    ("pillars", "Boundary and gate pillars: lamps on their tops", 120.0,
     2700),
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


def _grazers(doc, step=2.0) -> list:
    """Spots under every roof / terrace edge, a hand out from the wall and
    aimed down it: [(pos, dir)]."""
    from . import modern as MD
    look = doc.get("look") or {}
    fh = float(look.get("fascia_h", MD.FASCIA_H) or MD.FASCIA_H) \
        if look.get("fascia") else 0.0
    out = []
    for i, p, q, u, n, L, zt, kind in MD.tops(doc):
        if L < 1.0:
            continue
        z = zt - (fh + 0.08 if kind == "roof" else 0.45)
        k = max(1, int(L / step))
        for j in range(k):
            s = L * (j + 0.5) / k
            pos = (p[0] + u[0] * s + n[0] * 0.25, p[1] + u[1] * s +
                   n[1] * 0.25, z)
            d = (-n[0] * 0.12, -n[1] * 0.12, -1.0)
            ln = math.sqrt(sum(v * v for v in d))
            out.append((pos, [v / ln for v in d]))
    return out


def _garden(doc, every=4) -> list:
    """Bollards: one at every few stepping stones and along the lawns'
    edges — [pos] at knee height."""
    from shapely.geometry import Polygon
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    z = el[g] + 0.6
    out = []
    for lid, polys in (doc.get("pavers") or {}).items():
        cs = []
        for pts in polys or []:
            try:
                P_ = Polygon([tuple(c[:2]) for c in pts])
                cs.append(P_.centroid)
            except Exception:  # noqa: BLE001
                continue
        for k, c in enumerate(cs):
            if k % every == 0:
                out.append([c.x + 0.45, c.y, z])
    for lid, polys in (doc.get("landscape") or {}).items():
        for pts in polys or []:
            try:
                P_ = Polygon([tuple(c[:2]) for c in pts]).buffer(0)
            except Exception:  # noqa: BLE001
                continue
            if P_.is_empty or P_.area < 6.0:
                continue
            ring = P_.exterior if P_.geom_type == "Polygon" else \
                max(P_.geoms, key=lambda x: x.area).exterior
            n = max(2, int(ring.length / 7.0))
            for k in range(n):
                c = ring.interpolate(ring.length * k / n)
                # a step inside the lawn
                ins = P_.buffer(-0.3)
                if not ins.is_empty:
                    c = ins.exterior.interpolate(ins.exterior.project(c)) \
                        if ins.geom_type == "Polygon" else c
                out.append([c.x, c.y, z])
    keep = []                       # not crowded: 2.5 m apart at least
    for p in out:
        if all(math.dist(p[:2], q[:2]) >= 2.5 for q in keep):
            keep.append(p)
    return keep


def _pillars(scene) -> list:
    """The tops of the boundary's and gates' pillars: [pos]."""
    out = []
    for g, m in scene.placements():
        nm = (getattr(g, "name", "") or "").lower()
        if not (nm.startswith("pillar") or nm.startswith("gate pillar")):
            continue
        vs = [v.position for v in g.mesh.vertices]
        if m is not None:
            vs = [m.map(v) for v in vs]
        if not vs:
            continue
        x = (min(v.x() for v in vs) + max(v.x() for v in vs)) / 2
        y = (min(v.y() for v in vs) + max(v.y() for v in vs)) / 2
        z = max(v.z() for v in vs)
        out.append([x, y, z + 0.3])
    return out


def build(doc, scene, chosen: dict) -> list:
    """Our lights, by set: chosen = {set: (on, power scale, kelvin)}."""
    out = []
    gain = float(chosen.pop("_gain", (True, 1.0, 0))[1]) \
        if "_gain" in chosen else 1.0

    def add(kind, pos, d, power, kelvin, name, angle=60.0):
        out.append({"kind": kind, "pos": [float(v) for v in pos],
                    "dir": [float(v) for v in d], "kelvin": int(kelvin),
                    "power": float(power) * gain, "angle": float(angle),
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
                add("spot", pos, (0, 0, -1), p0, kelvin,
                    f"Porch · light {n}", 90.0)
        elif key == "grazers":
            for n, (pos, d) in enumerate(_grazers(doc), 1):
                add("spot", pos, d, p0, kelvin, f"Grazer · {n}", 50.0)
        elif key == "garden":
            for n, pos in enumerate(_garden(doc), 1):
                add("point", pos, (0, 0, -1), p0, kelvin, f"Garden · {n}")
        elif key == "pillars":
            for n, pos in enumerate(_pillars(scene), 1):
                if any(math.dist(pos, lt["pos"]) < 0.8 for lt in out):
                    continue                     # it has its lamp already
                add("point", pos, (0, 0, -1), p0, kelvin, f"Pillar · {n}")
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


# ---- the lights' markers in the model ------------------------------------------------
MARKERS_KEY = "cad2ingetrazo/render/markers"


def markers_mode() -> str:
    """"all" (shown), "hide_ours", "hide_all" — the bulbs the Render tab
    draws over the model; the lights themselves always render."""
    try:
        from PySide6.QtCore import QSettings
        v = QSettings("CAD2IngeTrazo", "render").value(MARKERS_KEY, "all")
        return v if v in ("all", "hide_ours", "hide_all") else "all"
    except Exception:  # noqa: BLE001
        return "all"


def set_markers_mode(mode, viewport=None) -> None:
    from PySide6.QtCore import QSettings
    QSettings("CAD2IngeTrazo", "render").setValue(MARKERS_KEY, mode)
    install_marker_filter()
    if viewport is not None:
        viewport.update()


def install_marker_filter() -> bool:
    """Wrap the Render tab's marker drawing (once) so its bulbs follow
    markers_mode(); its lights, list and render are untouched."""
    import sys
    mod = None
    for name in ("ingetrazo_plugin_render_blender", "plugins.render_blender"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "draw_lights"):
            break
        mod = None
    if mod is None:
        return False
    if getattr(mod, "_c2i_wrapped", False):
        return True
    orig = mod.draw_lights

    def draw_lights(app, panel, viewport, painter, _orig=orig, _mod=mod):
        mode = markers_mode()
        if mode == "hide_all":
            return None
        if mode == "hide_ours":
            st0 = _mod._state

            def _state(a, _st0=st0):
                st = _st0(a)
                st["lights"] = [lt for lt in st["lights"] if not ours(lt)]
                return st
            _mod._state = _state
            try:
                return _orig(app, panel, viewport, painter)
            finally:
                _mod._state = st0
        return _orig(app, panel, viewport, painter)
    mod.draw_lights = draw_lights
    mod._c2i_wrapped = True
    return True


# ---- the materials: what each colour of the model is ---------------------------------
#: the categories the Blender side knows, and the choices offered for each
MATERIALS = (
    ("wall", "Walls, slabs, columns", (
        ("paint", "Smooth paint"), ("plaster", "Textured plaster"),
        ("concrete", "Exposed concrete"), ("asis", "As modelled"))),
    ("floor", "Floors inside", (
        ("marble", "Polished marble"), ("tiles", "Matte tiles"),
        ("wood", "Oak wood"), ("asis", "As modelled"))),
    ("paving", "Paving, drive, walkways", (
        ("pavers", "Stone pavers"), ("asis", "As modelled"))),
    ("stone", "Stone, cladding, steps", (
        ("asis_stone", "Its own colour"), ("sandstone", "Sandstone"),
        ("granite", "Granite"), ("limestone", "Limestone"))),
    ("wood", "Doors, timber, shutters", (
        ("own", "Its own colour"), ("teak", "Teak"), ("walnut", "Walnut"),
        ("oak", "Oak"))),
    ("metal", "Frames, railings, gates", (
        ("powder", "Powder-coated (its colour)"), ("black", "Black "
                                                   "powder-coat"),
        ("steel", "Brushed steel"), ("iron", "Wrought iron"))),
    ("glass", "Glass", (
        ("clear", "Clear"), ("tinted", "Tinted blue"),
        ("reflective", "Reflective"), ("frosted", "Frosted"))),
    ("tiles", "Roof tiles", (
        ("own", "Its own colour"), ("clay", "Clay"), ("slate", "Slate"),
        ("concrete_tile", "Concrete tiles"))),
    ("grass", "Lawn", (("lawn", "Grass (textured)"), ("plain", "Plain"))),
)


def _cat(t, name, rgba):
    """One face's material category from its element (tag type, name) and
    colour."""
    r, g, b = (float(v) for v in rgba[:3])
    a = float(rgba[3]) if len(rgba) > 3 else 1.0
    if any(all(abs(c - k) < 0.015 for c, k in zip((r, g, b), gl))
           for gl in GLOWS):
        return "glow"
    if a < 0.9 or (abs(r - 0.62) < 0.02 and abs(g - 0.80) < 0.02 and
                   abs(b - 0.90) < 0.02):
        return "glass"
    n = (name or "").lower()
    t = (t or "").lower()
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    warm = r > g + 0.08 and g > b
    if t == "car" or "car p" in n or "figure" in n:
        return None
    if "brick" in n:
        return "brick"
    if any(k in n for k in ("timber", "shutter")) or (
            t == "opening" and warm and lum < 0.5):
        return "wood"
    if t in ("stairrail", "rail") or any(k in n for k in (
            "rail", "grill", "gate", "lantern", "sconce", "metal", "steel",
            "iron")) or (t == "opening" and not warm):
        return "metal"
    if t == "curtain":
        return "fabric"
    if t == "roof" or "roof tile" in n or (t == "look_roof"):
        return "tiles"
    if t == "landscape":
        if g > r + 0.1:
            return "grass"
        if warm and lum < 0.45:
            return "soil"
        return "paving"
    if "walkway" in n or "paving" in n or "paver" in n or "drive" in n:
        return "paving"
    if t in ("threshold", "coping") or any(k in n for k in (
            "clad", "inclined", "stone", "plinth", "quoin", "granite",
            "steps")):
        return "stone"
    if t in ("room", "finish_edge") or "floor finish" in n:
        return "floor"
    if "foundation" in n or "pcc" in n:
        return "concrete"
    return "wall"


def material_map(scene, look=None) -> dict:
    """{"colors": [[r, g, b, cat]], "textures": {name: cat}} — each
    exported colour's commonest category (by surface area)."""
    import collections
    from . import project as PJ
    votes = collections.defaultdict(collections.Counter)
    tex = collections.defaultdict(collections.Counter)
    for g, _m in scene.placements():
        t = (PJ.tag_of(g) or {}).get("type") or ""
        nm = getattr(g, "name", "") or ""
        gm = getattr(g, "material", None) or {}
        for f in g.mesh.faces:
            c = f.attrs.get("color") or gm.get("color")
            if c is None:
                continue
            cat = _cat(t, nm, tuple(c) + ((gm.get("opacity", 1.0),)
                                          if len(c) == 3 else ()))
            if cat is None:
                continue
            key = tuple(round(float(v), 3) for v in tuple(c)[:3])
            try:                        # by area: a wall outweighs a lattice
                a_ = float(f.area())
            except Exception:  # noqa: BLE001
                a_ = 0.01
            votes[key][cat] += a_ + 1e-4
            tx = f.attrs.get("texture") or gm.get("texture")
            path = tx.get("path") if isinstance(tx, dict) else tx
            if path:
                import os
                tex[os.path.splitext(os.path.basename(str(path)))[0]
                    .lower()][cat] += 1
    # the look's own colours know what they are
    if look:
        for k_, cat in (("roof_c", "tiles"), ("clad", "stone"),
                        ("stone", "stone")):
            c = look.get(k_)
            if c and look.get("style"):
                key = tuple(round(float(v), 3) for v in c[:3])
                votes[key][cat] += 10 ** 6 if k_ == "roof_c" else 0
    cols = [[*k, v.most_common(1)[0][0]] for k, v in votes.items() if v]
    return {"colors": cols,
            "textures": {k: v.most_common(1)[0][0] for k, v in tex.items()}}


# ---- the render: IngeTrazo's export and camera, our Blender script -------------------
def script_path():
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "blender", "c2i_render.py")


def prepare(app, settings: dict):
    """Export the model and write the job (IngeTrazo's Render with Blender
    does that part: core.render_blender.write_job), then our "c2i" part and
    the scripts beside it. Returns (argv, job path, work dir)."""
    import json
    import shutil
    import time
    from pathlib import Path

    from core import render_blender as rb
    found = rb.find_blender(settings.get("blender") or None)
    if found is None:
        raise RuntimeError("Blender was not found. Install it (blender.org) "
                           "or point the Render tab to it.")
    scene, vp = app.viewport.scene, app.viewport
    st = state(scene)
    lights = rb.clean_lights(st["lights"])
    work = rb.work_base() / ("c2i-" + time.strftime("%Y%m%d-%H%M%S"))
    sky = settings["env"].get("sky", "night")
    amb = {"night": "night", "overcast": "overcast"}.get(sky, "day")
    q = int(settings.get("quality", 1))
    eng = settings.get("engine", "cycles")
    job = rb.write_job(
        scene, vp.camera, work, engine=eng, quality=q,
        width=int(settings.get("width", 1600)),
        height=int(settings.get("height", 900)),
        ground=False, keep_blend=bool(settings.get("blend")),
        ambience=amb, lights=lights, sun_scale=float(st["sun_scale"]))
    data = json.loads(Path(job).read_text(encoding="utf-8"))
    data["c2i"] = {"env": settings["env"], "materials": settings["mats"],
                   **material_map(scene, settings.get("look"))}
    data["ground"] = {"z": -0.002, "size": 2000.0,
                      "color": [0.42, 0.42, 0.40]}
    Path(job).write_text(json.dumps(data), encoding="utf-8")
    shutil.copyfile(rb.render_script(), Path(job).parent /
                    "render_scene_base.py")
    ours_ = Path(job).parent / "c2i_render.py"
    shutil.copyfile(script_path(), ours_)
    argv = [*found.command, "-b", "--factory-startup", "--python",
            str(ours_), "--", str(job)]
    return argv, Path(job), work, found


# ---- the environment: real HDR skies --------------------------------------------------
#: Blender's own HDR environments (they ship with every Blender, offline)
BUILTIN_HDRI = (("courtyard", "Courtyard — bright day"),
                ("city", "City — overcast street"),
                ("forest", "Forest — dappled day"),
                ("sunrise", "Sunrise — low warm sun"),
                ("sunset", "Sunset — golden evening"),
                ("night", "Night — city at night"))
#: Poly Haven's free (CC0) HDRIs offered first; the full list comes from
#: their site when asked
POLYHAVEN = (("kloofendal_48d_partly_cloudy_puresky",
              "Partly cloudy — clear blue sky"),
             ("kloppenheim_06_puresky", "Clear evening sky"),
             ("venice_sunset", "Venice sunset"),
             ("spruit_sunrise", "Sunrise over the veld"),
             ("rooitou_park", "Park — afternoon"),
             ("potsdamer_platz", "City square — day"),
             ("dikhololo_night", "Night — starry"),
             ("satara_night", "Night — dusk glow"))
UA = {"User-Agent": "CAD2IngeTrazo (IngeTrazo extension)"}


def hdri_dir():
    import os
    base = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    d = os.path.join(base, "ingetrazo", "c2i_hdri")
    os.makedirs(d, exist_ok=True)
    return d


def hdri_cached(asset, res="2k"):
    import os
    p = os.path.join(hdri_dir(), f"{asset}_{res}.hdr")
    return p if os.path.isfile(p) and os.path.getsize(p) > 1000 else None


def polyhaven_list(timeout=20) -> list:
    """Poly Haven's outdoor HDRIs: [(id, name)] — from their site."""
    import json
    import urllib.request
    req = urllib.request.Request(
        "https://api.polyhaven.com/assets?type=hdris&categories=outdoor",
        headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = [(k, str(v.get("name") or k)) for k, v in data.items()]
    out.sort(key=lambda kv: kv[1].lower())
    return out


def polyhaven_fetch(asset, res="2k", progress=None, timeout=60) -> str:
    """Download one HDRI (.hdr) into the cache: its path."""
    import json
    import os
    import urllib.request
    have = hdri_cached(asset, res)
    if have:
        return have
    req = urllib.request.Request(f"https://api.polyhaven.com/files/{asset}",
                                 headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        files = json.loads(r.read().decode("utf-8"))
    hd = files.get("hdri") or {}
    pick = hd.get(res) or hd.get("2k") or hd.get("1k") or {}
    url = (pick.get("hdr") or {}).get("url")
    if not url:
        raise RuntimeError(f"{asset}: no .hdr at {res}")
    dst = os.path.join(hdri_dir(), f"{asset}_{res}.hdr")
    tmp = dst + ".part"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, \
            open(tmp, "wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            fh.write(b)
            got += len(b)
            if progress and total:
                progress(got / total)
    os.replace(tmp, dst)
    return dst


# ---- the dialog --------------------------------------------------------------------
def _dialog_class():
    from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                   QDoubleSpinBox, QFileDialog, QFormLayout,
                                   QGridLayout, QHBoxLayout, QLabel,
                                   QProgressBar, QPushButton, QSpinBox,
                                   QTabWidget, QVBoxLayout, QWidget)

    SK = "cad2ingetrazo/render/"

    class LightingDialog(QDialog):
        """Lights, materials, environment and the Blender render — one
        place."""

        def __init__(self, panel):
            super().__init__(panel)
            self.panel = panel
            self.setWindowTitle("Lighting, materials, environment — Blender "
                                "render")
            self._qs = QSettings("CAD2IngeTrazo", "render")
            self._proc = None
            self._out = None
            v = QVBoxLayout(self)
            self.where = QLabel("")
            self.where.setWordWrap(True)
            self.where.setStyleSheet("color: #8a94a3;")
            v.addWidget(self.where)
            self.tabs = QTabWidget()
            v.addWidget(self.tabs, 1)
            self._lights_tab()
            self._mats_tab()
            self._env_tab()
            self._render_tab()
            b = QHBoxLayout()
            self.note = QLabel("")
            self.note.setWordWrap(True)
            b.addWidget(self.note, 1)
            close = QPushButton("Close")
            close.clicked.connect(self.close)
            b.addWidget(close)
            v.addLayout(b)
            self.resize(860, 640)
            self._refresh()

        # ---- tabs
        def _lights_tab(self):
            w = QWidget()
            v = QVBoxLayout(w)
            intro = QLabel(
                "Lights made from the model, kept in the document with "
                "IngeTrazo's <b>Render with Blender</b> (its Render tab "
                "shows and edits them too). Making them again replaces only "
                "these («C2I · …») — lights you placed yourself stay.")
            intro.setWordWrap(True)
            v.addWidget(intro)
            grid = QGridLayout()
            grid.addWidget(QLabel("<b>Light set</b>"), 0, 0)
            grid.addWidget(QLabel("<b>Power ×</b>"), 0, 1)
            grid.addWidget(QLabel("<b>Colour (K)</b>"), 0, 2)
            self.rows = {}
            for r, (key, label, _p, kelvin) in enumerate(SETS, 1):
                cb = QCheckBox(label)
                cb.setChecked(self._qs.value(SK + "on_" + key, "1") == "1")
                sc = QDoubleSpinBox()
                sc.setRange(0.1, 10.0)
                sc.setSingleStep(0.1)
                sc.setValue(float(self._qs.value(SK + "k_" + key, 1.0)))
                kv = QSpinBox()
                kv.setRange(1800, 8000)
                kv.setSingleStep(100)
                kv.setValue(int(self._qs.value(SK + "K_" + key, kelvin)))
                grid.addWidget(cb, r, 0)
                grid.addWidget(sc, r, 1)
                grid.addWidget(kv, r, 2)
                self.rows[key] = (cb, sc, kv)
            grid.setColumnStretch(0, 1)
            v.addLayout(grid)
            f = QFormLayout()
            self.gain = QDoubleSpinBox()
            self.gain.setRange(0.1, 10.0)
            self.gain.setSingleStep(0.25)
            self.gain.setValue(float(self._qs.value(SK + "gain", 1.5)))
            f.addRow("Overall brightness ×", self.gain)
            self.markers = QComboBox()
            for k, lab in (("all", "Show every light's bulb"),
                           ("hide_ours", "Hide the bulbs of these lights "
                                         "(«C2I · …»)"),
                           ("hide_all", "Hide all the bulbs")):
                self.markers.addItem(lab, k)
            self.markers.setCurrentIndex(max(0, self.markers.findData(
                markers_mode())))
            self.markers.currentIndexChanged.connect(
                lambda _i: set_markers_mode(self.markers.currentData(),
                                            self._vp()))
            f.addRow("In the model (the render keeps them all)", self.markers)
            install_marker_filter()
            v.addLayout(f)
            b = QHBoxLayout()
            for text, fn in (("Put the lights in", self._put),
                             ("Remove ours", self._remove),
                             ("Open IngeTrazo's Render tab", self._open)):
                btn = QPushButton(text)
                btn.clicked.connect(fn)
                b.addWidget(btn)
            b.addStretch(1)
            v.addLayout(b)
            v.addStretch(1)
            self.tabs.addTab(w, "Lights")

        def _mats_tab(self):
            w = QWidget()
            v = QVBoxLayout(w)
            intro = QLabel(
                "Each surface of the model gets a real material in Blender "
                "by what it is (walls, floors, paving, stone, wood, metal, "
                "glass, roof tiles, lawn) — patterns and relief made in "
                "Blender, the model's colours kept unless you choose "
                "another.")
            intro.setWordWrap(True)
            v.addWidget(intro)
            f = QFormLayout()
            self.mat = {}
            for key, label, choices in MATERIALS:
                cb = QComboBox()
                for k, lab in choices:
                    cb.addItem(lab, k)
                i = cb.findData(self._qs.value(SK + "m_" + key, ""))
                cb.setCurrentIndex(max(0, i))
                f.addRow(label, cb)
                self.mat[key] = cb
            self.detail = QDoubleSpinBox()
            self.detail.setRange(0.0, 3.0)
            self.detail.setSingleStep(0.25)
            self.detail.setValue(float(self._qs.value(SK + "detail", 1.0)))
            f.addRow("Relief (texture depth) ×", self.detail)
            self.glow = QDoubleSpinBox()
            self.glow.setRange(0.0, 100.0)
            self.glow.setSingleStep(2.0)
            self.glow.setValue(float(self._qs.value(SK + "glow", 12.0)))
            f.addRow("Lamps' glass glow", self.glow)
            v.addLayout(f)
            v.addStretch(1)
            self.tabs.addTab(w, "Materials")

        def _env_tab(self):
            w = QWidget()
            f = QFormLayout(w)
            self.sky = QComboBox()
            self.sky.addItem("— Real HDR skies (photographed) —", None)
            self.sky.addItem("HDRI · Poly Haven (free, downloaded, sharp)",
                             "hdri_ph")
            for k, lab in BUILTIN_HDRI:
                self.sky.addItem(f"HDRI · Blender's own · {lab}",
                                 "hdri_bl:" + k)
            self.sky.addItem("HDRI · my own file (.hdr / .exr)…",
                             "hdri_file")
            self.sky.addItem("— Made skies —", None)
            for k, lab in (("night", "Night — the lights under a dark sky"),
                           ("blue", "Blue hour — dusk, lights on"),
                           ("golden", "Golden hour — low warm sun"),
                           ("day", "Clear day — physical sky"),
                           ("overcast", "Overcast — soft even light")):
                self.sky.addItem(lab, k)
            for i in range(self.sky.count()):          # the headings
                if self.sky.itemData(i) is None:
                    it = self.sky.model().item(i)
                    if it is not None:
                        it.setEnabled(False)
            self.sky.setCurrentIndex(max(0, self.sky.findData(
                self._qs.value(SK + "sky", "hdri_ph"))))
            self.sky.currentIndexChanged.connect(self._sky_changed)
            f.addRow("Environment", self.sky)
            # Poly Haven: the HDRI, its size, the download
            ph = QHBoxLayout()
            self.ph = QComboBox()
            self.ph.setEditable(False)
            saved = self._qs.value(SK + "ph", POLYHAVEN[0][0])
            for k, lab in POLYHAVEN:
                self.ph.addItem(lab, k)
            if self.ph.findData(saved) < 0:
                self.ph.addItem(saved, saved)
            self.ph.setCurrentIndex(max(0, self.ph.findData(saved)))
            ph.addWidget(self.ph, 1)
            self.ph_res = QComboBox()
            for r in ("1k", "2k", "4k", "8k"):
                self.ph_res.addItem(r, r)
            self.ph_res.setCurrentIndex(max(0, self.ph_res.findData(
                self._qs.value(SK + "ph_res", "4k"))))
            ph.addWidget(self.ph_res)
            more = QPushButton("More…")
            more.setToolTip("List all of Poly Haven's outdoor HDRIs")
            more.clicked.connect(self._ph_more)
            ph.addWidget(more)
            self.ph_get = QPushButton("Download")
            self.ph_get.clicked.connect(self._ph_download)
            ph.addWidget(self.ph_get)
            self.ph_row = QWidget()
            self.ph_row.setLayout(ph)
            ph.setContentsMargins(0, 0, 0, 0)
            f.addRow("Poly Haven HDRI", self.ph_row)
            # my own file
            fr = QHBoxLayout()
            self.hfile = QLabel(self._qs.value(SK + "hfile", "") or
                                "(none chosen)")
            self.hfile.setWordWrap(True)
            fr.addWidget(self.hfile, 1)
            pick = QPushButton("Choose…")
            pick.clicked.connect(self._pick_hdri)
            fr.addWidget(pick)
            self.file_row = QWidget()
            self.file_row.setLayout(fr)
            fr.setContentsMargins(0, 0, 0, 0)
            f.addRow("HDR file", self.file_row)
            self.h_rot = QDoubleSpinBox()
            self.h_rot.setRange(-360, 360)
            self.h_rot.setSingleStep(15)
            self.h_rot.setSuffix(" °")
            self.h_rot.setValue(float(self._qs.value(SK + "h_rot", 0)))
            f.addRow("HDRI rotation (turns its sun)", self.h_rot)
            self.h_bg = QCheckBox("Show the HDRI behind the house (else "
                                  "only its light)")
            self.h_bg.setChecked(self._qs.value(SK + "h_bg", "1") == "1")
            f.addRow(self.h_bg)
            self.sun_custom = QCheckBox(
                "Add / set the sun here (else the Shadows panel's sun; "
                "with an HDRI: a sun lamp for crisp shadows)")
            self.sun_custom.setChecked(
                self._qs.value(SK + "sun_custom", "0") == "1")
            f.addRow(self.sun_custom)
            self.sun_az = QDoubleSpinBox()
            self.sun_az.setRange(0, 360)
            self.sun_az.setSuffix(" ° from north")
            self.sun_az.setValue(float(self._qs.value(SK + "sun_az", 135)))
            f.addRow("Sun azimuth", self.sun_az)
            self.sun_el = QDoubleSpinBox()
            self.sun_el.setRange(-10, 90)
            self.sun_el.setSuffix(" °")
            self.sun_el.setValue(float(self._qs.value(SK + "sun_el", 40)))
            f.addRow("Sun elevation", self.sun_el)
            self.sun_k = QDoubleSpinBox()
            self.sun_k.setRange(0.0, 5.0)
            self.sun_k.setSingleStep(0.1)
            self.sun_k.setValue(float(self._qs.value(SK + "sun_k", 1.0)))
            f.addRow("Sun strength ×", self.sun_k)
            self.sky_k = QDoubleSpinBox()
            self.sky_k.setRange(0.0, 5.0)
            self.sky_k.setSingleStep(0.1)
            self.sky_k.setValue(float(self._qs.value(SK + "sky_k", 1.0)))
            f.addRow("Sky strength ×", self.sky_k)
            self.ground = QComboBox()
            for k, lab in (("grass", "Grass"), ("concrete", "Concrete"),
                           ("asphalt", "Asphalt road"), ("sand", "Sand"),
                           ("plain", "Plain grey"), ("none", "None")):
                self.ground.addItem(lab, k)
            self.ground.setCurrentIndex(max(0, self.ground.findData(
                self._qs.value(SK + "ground", "grass"))))
            f.addRow("Ground beyond the plot", self.ground)
            self.haze = QDoubleSpinBox()
            self.haze.setRange(0.0, 10.0)
            self.haze.setSingleStep(0.5)
            self.haze.setValue(float(self._qs.value(SK + "haze", 0.0)))
            f.addRow("Atmospheric haze (Cycles)", self.haze)
            self.exposure = QDoubleSpinBox()
            self.exposure.setRange(-5.0, 5.0)
            self.exposure.setSingleStep(0.1)
            self.exposure.setValue(float(self._qs.value(SK + "exposure",
                                                        0.0)))
            f.addRow("Exposure (EV)", self.exposure)
            self.auto_ev = QCheckBox("Auto exposure — meter the shot like a "
                                     "camera (the EV above is added)")
            self.auto_ev.setChecked(self._qs.value(SK + "auto_ev", "1")
                                    == "1")
            f.addRow(self.auto_ev)
            self.look = QComboBox()
            for k, lab in (("Medium High Contrast", "Medium-high contrast"),
                           ("Base Contrast", "Natural"),
                           ("High Contrast", "High contrast"),
                           ("Punchy", "Punchy"),
                           ("Medium Low Contrast", "Soft")):
                self.look.addItem(lab, k)
            self.look.setCurrentIndex(max(0, self.look.findData(
                self._qs.value(SK + "look", "Medium High Contrast"))))
            f.addRow("Contrast", self.look)
            self.lmode = QComboBox()
            for k, lab in (("auto", "By the hour — full at night, dimmed at "
                                    "dusk, only their glow by day"),
                           ("on", "Always full"), ("off", "Off")):
                self.lmode.addItem(lab, k)
            self.lmode.setCurrentIndex(max(0, self.lmode.findData(
                self._qs.value(SK + "lmode", "auto"))))
            f.addRow("Lamps", self.lmode)
            self.bloom = QCheckBox("Soft glow round the lamps (bloom)")
            self.bloom.setChecked(self._qs.value(SK + "bloom", "1") == "1")
            f.addRow(self.bloom)
            self.transp = QCheckBox("Transparent background (PNG)")
            self.transp.setChecked(self._qs.value(SK + "transp", "0") == "1")
            f.addRow(self.transp)
            self.tabs.addTab(w, "Environment")
            self._sky_changed()

        # ---- the HDRIs
        def _sky_changed(self, *_a):
            k = self.sky.currentData() or ""
            self.ph_row.setEnabled(k == "hdri_ph")
            self.file_row.setEnabled(k == "hdri_file")
            hd = k.startswith("hdri")
            self.h_rot.setEnabled(hd)
            self.h_bg.setEnabled(hd)

        def _pick_hdri(self):
            path, _f = QFileDialog.getOpenFileName(
                self, "An HDR environment", "",
                "HDR images (*.hdr *.exr)")
            if path:
                self.hfile.setText(path)
                self._qs.setValue(SK + "hfile", path)

        def _ph_more(self):
            from PySide6.QtWidgets import QApplication
            self.note.setText("Asking Poly Haven for its HDRIs…")
            QApplication.processEvents()
            try:
                items = polyhaven_list()
            except Exception as e:  # noqa: BLE001
                self.note.setText(f"Poly Haven could not be reached: {e}")
                return
            cur = self.ph.currentData()
            have = {self.ph.itemData(i) for i in range(self.ph.count())}
            for k, lab in items:
                if k not in have:
                    self.ph.addItem(lab, k)
            self.ph.setCurrentIndex(max(0, self.ph.findData(cur)))
            self.note.setText(f"{len(items)} outdoor HDRIs from Poly Haven "
                              "(free, CC0) — choose one, then Download.")

        def _ph_download(self, *_a, quiet=False):
            """Download the chosen HDRI (kept for next time): its path."""
            from PySide6.QtWidgets import QApplication
            asset, res = self.ph.currentData(), self.ph_res.currentData()
            have = hdri_cached(asset, res)
            if have:
                if not quiet:
                    self.note.setText(f"Already here: {have}")
                return have
            self.bar.setVisible(True)
            self.note.setText(f"Downloading {asset} ({res}) from Poly "
                              "Haven…")
            QApplication.processEvents()

            def prog(x):
                self.bar.setValue(int(x * 100))
                QApplication.processEvents()
            try:
                p = polyhaven_fetch(asset, res, prog)
            except Exception as e:  # noqa: BLE001
                self.note.setText(f"<b>The download failed:</b> {e}")
                self.bar.setVisible(False)
                return None
            self.bar.setVisible(False)
            self.note.setText(f"HDRI ready: {p}")
            return p

        def _render_tab(self):
            w = QWidget()
            v = QVBoxLayout(w)
            f = QFormLayout()
            self.engine = QComboBox()
            self.engine.addItem("Cycles — realistic (slower)", "cycles")
            self.engine.addItem("EEVEE — fast", "eevee")
            self.engine.setCurrentIndex(max(0, self.engine.findData(
                self._qs.value(SK + "engine", "cycles"))))
            f.addRow("Engine", self.engine)
            self.quality = QComboBox()
            for lab in ("Draft", "Good", "High"):
                self.quality.addItem(lab)
            self.quality.setCurrentIndex(int(self._qs.value(SK + "quality",
                                                           1)))
            f.addRow("Quality", self.quality)
            self.width = QSpinBox()
            self.width.setRange(320, 7680)
            self.width.setSingleStep(160)
            self.width.setValue(int(self._qs.value(SK + "width", 1600)))
            f.addRow("Width (px; height from the view)", self.width)
            self.blend = QCheckBox("Also save the .blend (to open in "
                                   "Blender)")
            self.blend.setChecked(self._qs.value(SK + "blend", "1") == "1")
            f.addRow(self.blend)
            v.addLayout(f)
            b = QHBoxLayout()
            self.go = QPushButton("Render the current view")
            self.go.setDefault(True)
            self.go.clicked.connect(self._render)
            b.addWidget(self.go)
            self.stop = QPushButton("Stop")
            self.stop.clicked.connect(self._stop)
            self.stop.setEnabled(False)
            b.addWidget(self.stop)
            self.save = QPushButton("Save image…")
            self.save.clicked.connect(self._save)
            self.save.setEnabled(False)
            b.addWidget(self.save)
            self.inbl = QPushButton("Open in Blender")
            self.inbl.clicked.connect(self._open_blend)
            self.inbl.setEnabled(False)
            b.addWidget(self.inbl)
            b.addStretch(1)
            v.addLayout(b)
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            self.bar.setVisible(False)
            v.addWidget(self.bar)
            self.status = QLabel("")
            self.status.setWordWrap(True)
            v.addWidget(self.status)
            self.preview = QLabel("The image appears here.")
            self.preview.setAlignment(Qt.AlignCenter)
            self.preview.setMinimumHeight(260)
            self.preview.setStyleSheet("background: #1b1f24; color: #8a94a3;")
            v.addWidget(self.preview, 1)
            self.tabs.addTab(w, "Render")

        # ---- state
        def _vp(self):
            return self.panel.app.viewport

        def _remember(self):
            q = self._qs
            for k, (cb, sc, kv) in self.rows.items():
                q.setValue(SK + "on_" + k, "1" if cb.isChecked() else "0")
                q.setValue(SK + "k_" + k, sc.value())
                q.setValue(SK + "K_" + k, kv.value())
            q.setValue(SK + "gain", self.gain.value())
            for k, cb in self.mat.items():
                q.setValue(SK + "m_" + k, cb.currentData())
            for k, wd in (("detail", self.detail), ("glow", self.glow),
                          ("sun_az", self.sun_az), ("sun_el", self.sun_el),
                          ("sun_k", self.sun_k), ("sky_k", self.sky_k),
                          ("haze", self.haze), ("exposure", self.exposure),
                          ("width", self.width), ("h_rot", self.h_rot)):
                q.setValue(SK + k, wd.value())
            for k, wd in (("sky", self.sky), ("ground", self.ground),
                          ("look", self.look), ("engine", self.engine),
                          ("ph", self.ph), ("ph_res", self.ph_res),
                          ("lmode", self.lmode)):
                q.setValue(SK + k, wd.currentData())
            q.setValue(SK + "quality", self.quality.currentIndex())
            for k, wd in (("sun_custom", self.sun_custom),
                          ("bloom", self.bloom), ("transp", self.transp),
                          ("auto_ev", self.auto_ev),
                          ("blend", self.blend), ("h_bg", self.h_bg)):
                q.setValue(SK + k, "1" if wd.isChecked() else "0")

        def _refresh(self):
            st = state(self._vp().scene)
            n_ours = sum(1 for lt in st["lights"] if ours(lt))
            n_hand = len(st["lights"]) - n_ours
            try:
                from core import render_blender as rb
                found = rb.find_blender()
                bl = (f"Blender: {found.where}" if found else
                      "Blender was not found — install it from blender.org "
                      "(the Render tab can point to it).")
            except Exception:  # noqa: BLE001
                bl = "Blender: as the Render tab finds it."
            self.where.setText(
                bl + f" · In the document: {n_ours} lights of ours, "
                f"{n_hand} of yours.")

        def _chosen(self):
            out = {k: (cb.isChecked(), sc.value(), kv.value())
                   for k, (cb, sc, kv) in self.rows.items()}
            out["_gain"] = (True, self.gain.value(), 0)
            return out

        def _settings(self):
            vp = self._vp()
            w_ = self.width.value()
            asp = max(0.2, vp.width() / max(1, vp.height()))
            mats = {k: cb.currentData() for k, cb in self.mat.items()}
            mats["detail"] = self.detail.value()
            mats["glow"] = self.glow.value()
            return {
                "engine": self.engine.currentData(),
                "quality": self.quality.currentIndex(),
                "width": w_, "height": max(2, round(w_ / asp)),
                "blend": self.blend.isChecked(),
                "look": self.panel.doc().get("look") or {},
                "mats": mats,
                "env": {"sky": self.sky.currentData() or "day",
                        "hdri": self._hdri_path(),
                        "h_rot": self.h_rot.value(),
                        "h_bg": self.h_bg.isChecked(),
                        "sun_custom": self.sun_custom.isChecked(),
                        "sun_az": self.sun_az.value(),
                        "sun_el": self.sun_el.value(),
                        "sun_k": self.sun_k.value(),
                        "sky_k": self.sky_k.value(),
                        "ground": self.ground.currentData(),
                        "haze": self.haze.value(),
                        "exposure": self.exposure.value(),
                        "auto_exposure": self.auto_ev.isChecked(),
                        "look": self.look.currentData(),
                        "bloom": self.bloom.isChecked(),
                        "lights_mode": self.lmode.currentData(),
                        "transparent": self.transp.isChecked()}}

        def _hdri_path(self):
            k = self.sky.currentData() or ""
            if k == "hdri_ph":
                have = hdri_cached(self.ph.currentData(),
                                   self.ph_res.currentData())
                if have:
                    return have
                # 3.64.71: not downloaded yet — fetched now (2k is quick);
                # offline: the physical clear-day sky, not Blender's dull
                # little studio HDRI
                for res_ in (self.ph_res.currentData(), "2k"):
                    try:
                        return polyhaven_fetch(self.ph.currentData(), res_,
                                               timeout=25)
                    except Exception:  # noqa: BLE001
                        continue
                return None
            if k == "hdri_file":
                t = self.hfile.text()
                import os
                return t if os.path.isfile(t) else None
            if k.startswith("hdri_bl:"):
                return "builtin:" + k.split(":", 1)[1]
            return None

        # ---- lights
        def _put(self):
            self._remember()
            vp = self._vp()
            doc = self.panel.doc()
            st = state(vp.scene)
            new = build(doc, vp.scene, self._chosen())
            st["lights"] = [lt for lt in st["lights"] if not ours(lt)] + new
            sky = self.sky.currentData()
            st["ambience"] = {"night": "night", "blue": "night",
                              "overcast": "overcast",
                              "hdri_bl:night": "night"}.get(sky or "",
                                                            "day")
            store(vp, st)
            by = {}
            for lt in new:
                w = lt["name"][len(TAG):].split(" · ")[0].lower()
                by[w] = by.get(w, 0) + 1
            self.note.setText(
                f"<b>{len(new)} lights</b> in: " + ", ".join(
                    f"{n} {w}" for w, n in sorted(by.items())) +
                ". Ctrl+Z takes them back.")
            self._refresh()
            try:
                p = render_panel(self.panel.app.window)
                if p is not None:
                    p.refresh_lights()
            except Exception:  # noqa: BLE001
                pass

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
                self.note.setText("IngeTrazo's Render with Blender "
                                  "extension is not loaded.")

        # ---- render
        def _render(self):
            if self._proc is not None:
                return
            self._remember()
            k = self.sky.currentData() or ""
            if k == "hdri_ph" and not hdri_cached(
                    self.ph.currentData(), self.ph_res.currentData()):
                if not self._ph_download(quiet=True):
                    self.status.setText("Poly Haven could not be reached — "
                                        "rendering with Blender's own "
                                        "courtyard HDRI instead.")
            if k == "hdri_file" and not self._hdri_path():
                self.status.setText("<b>Choose an HDR file</b> first "
                                    "(Environment tab).")
                return
            st = state(self._vp().scene)
            if not any(ours(lt) for lt in st["lights"]):
                self._put()                 # the lights first
            try:
                from core import render_blender as rb
                argv, job, work, found = prepare(self.panel.app,
                                                 self._settings())
            except Exception as e:  # noqa: BLE001
                self.status.setText(f"<b>Could not start:</b> {e}")
                return
            self._job, self._work = job, work
            import json
            data = json.loads(job.read_text(encoding="utf-8"))
            self._out = data["output"]
            self._blend = data.get("blend")
            self._found = found
            proc = QProcess(self)
            env = QProcessEnvironment()
            for k, v in rb.clean_env().items():
                env.insert(k, v)
            proc.setProcessEnvironment(env)
            proc.setProcessChannelMode(QProcess.MergedChannels)
            proc.readyReadStandardOutput.connect(self._read)
            proc.finished.connect(self._finished)
            self._proc = proc
            self._log = []
            self.bar.setVisible(True)
            self.bar.setValue(0)
            self.go.setEnabled(False)
            self.stop.setEnabled(True)
            self.status.setText("Blender is preparing the scene… (the "
                                "first Cycles render on a graphics card "
                                "can take a few minutes)")
            proc.start(argv[0], argv[1:])

        def _read(self):
            from core import render_blender as rb
            txt = bytes(self._proc.readAllStandardOutput()).decode(
                "utf-8", "replace")
            for line in txt.splitlines():
                self._log.append(line)
                if "INGETRAZO" not in line:
                    continue
                p = rb.progress_of(line)
                if p is not None:
                    self.bar.setValue(int(p * 100))
                what = line.split("INGETRAZO", 1)[1].strip()
                if not what.startswith("stats"):
                    self.status.setText(what[:160])

        def _finished(self, code, _st):
            import os
            self._proc = None
            self.go.setEnabled(True)
            self.stop.setEnabled(False)
            self.bar.setVisible(False)
            if self._out and os.path.exists(self._out):
                pm = QPixmap(self._out)
                self.preview.setPixmap(pm.scaled(
                    self.preview.width(), self.preview.height(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.status.setText(f"Done — {self._out}")
                self.save.setEnabled(True)
                self.inbl.setEnabled(bool(self._blend and
                                          os.path.exists(self._blend)))
                self.tabs.setCurrentIndex(3)
            else:
                tail = "<br>".join(self._log[-8:])
                self.status.setText(f"<b>Blender stopped</b> (code {code})."
                                    f"<br><small>{tail}</small>")

        def _stop(self):
            if self._proc is not None:
                self._proc.kill()

        def _save(self):
            import shutil
            if not self._out:
                return
            path, _f = QFileDialog.getSaveFileName(
                self, "Save the render", "render.png", "PNG (*.png)")
            if path:
                shutil.copyfile(self._out, path)
                self.status.setText(f"Saved — {path}")

        def _open_blend(self):
            if self._blend:
                QProcess.startDetached(self._found.command[0],
                                       [*self._found.command[1:],
                                        self._blend])

        def closeEvent(self, ev):
            self._remember()
            super().closeEvent(ev)

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
