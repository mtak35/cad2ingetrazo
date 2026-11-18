# CAD2IngeTrazo 3.64.57 — runs INSIDE Blender, on top of IngeTrazo's own
# «Render with Blender» script (resources/blender/render_scene.py, copied
# next to the job as render_scene_base.py): everything it does — the model,
# the camera, the finishes, the lights, the engine — and then the job's
# "c2i" part: real materials by what each surface is, and the environment
# (sky and time of day, sun, ground beyond the plot, haze, exposure,
# contrast, glow round the lamps).
#
#   blender -b --factory-startup --python c2i_render.py -- job.json
import json
import math
import os
import sys

import bpy
from mathutils import Vector

_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.join(_HERE, "render_scene_base.py")
_src = open(_BASE, encoding="utf-8").read()
# its functions without its main() call (the file ends by calling it)
_lines = _src.rstrip().splitlines()
if _lines and _lines[-1].strip() == "main()":
    _lines = _lines[:-1]
exec(compile("\n".join(_lines), _BASE, "exec"))   # noqa: S102


# ---- node helpers --------------------------------------------------------------
def _bsdf(mat):
    if not mat.node_tree:
        return None
    return next((n for n in mat.node_tree.nodes
                 if n.type == "BSDF_PRINCIPLED"), None)


def _inp(node, *names):
    for n in names:
        s = node.inputs.get(n)
        if s is not None:
            return s
    return None


def _val(node, names, v):
    s = _inp(node, *names)
    if s is None:
        return
    try:
        s.default_value = v
    except (TypeError, ValueError):
        pass


def _unlink(sock):
    for l in list(sock.links):
        sock.id_data.links.remove(l)


def _coords(nt):
    """Object coordinates (metres: the model comes in unscaled) folded so a
    pattern runs on walls along x and along y alike: (x + y, z, 0)."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    nt.links.new(sep.outputs[0], add.inputs[0])
    nt.links.new(sep.outputs[1], add.inputs[1])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(add.outputs[0], comb.inputs[0])
    nt.links.new(sep.outputs[2], comb.inputs[1])
    return tc.outputs["Object"], comb.outputs[0]


def _bump(nt, bsdf, height_out, strength, dist=0.01):
    b = nt.nodes.new("ShaderNodeBump")
    _val(b, ("Strength",), strength)
    _val(b, ("Distance",), dist)
    nt.links.new(height_out, b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])


def _noise(nt, vec, scale, detail=4.0):
    n = nt.nodes.new("ShaderNodeTexNoise")
    nt.links.new(vec, n.inputs["Vector"])
    _val(n, ("Scale",), scale)
    _val(n, ("Detail",), detail)
    return n


def _vary(nt, bsdf, base, vec, scale, amount):
    """The base colour varied by noise: lighter and darker patches."""
    sock = bsdf.inputs["Base Color"]
    if sock.links:
        return
    n = _noise(nt, vec, scale, 6.0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    lo = [max(0.0, c * (1 - amount)) for c in base[:3]]
    hi = [min(1.0, c * (1 + amount * 0.6)) for c in base[:3]]
    ramp.color_ramp.elements[0].color = (*lo, 1.0)
    ramp.color_ramp.elements[1].color = (*hi, 1.0)
    nt.links.new(ramp.outputs["Color"], sock)


def _set_base(bsdf, rgb):
    s = bsdf.inputs["Base Color"]
    _unlink(s)
    s.default_value = (*rgb, 1.0)


# ---- the materials -----------------------------------------------------------------
PRESET_RGB = {
    "teak": (0.42, 0.24, 0.11), "walnut": (0.22, 0.13, 0.08),
    "oak": (0.62, 0.45, 0.28),
    "sandstone": (0.72, 0.60, 0.45), "granite": (0.30, 0.30, 0.32),
    "limestone": (0.82, 0.79, 0.72),
    "clay": (0.62, 0.27, 0.16), "slate": (0.20, 0.21, 0.23),
    "concrete_tile": (0.45, 0.44, 0.42),
    "black": (0.03, 0.03, 0.035), "steel": (0.62, 0.63, 0.65),
    "iron": (0.06, 0.06, 0.06),
}


def make(mat, cat, opt, detail):
    bsdf = _bsdf(mat)
    if bsdf is None:
        return False
    nt = mat.node_tree
    base = tuple(bsdf.inputs["Base Color"].default_value)[:3]
    obj, wall = _coords(nt)
    choice = opt.get(cat, "")
    if choice == "asis":
        return False
    rough = ("Roughness",)
    if cat == "wall":
        _val(bsdf, rough, 0.85)
        _val(bsdf, ("Specular IOR Level", "Specular"), 0.25)
        if choice == "concrete":
            _vary(nt, bsdf, base, obj, 3.0, 0.18)
            n = _noise(nt, obj, 60.0, 8.0)
            _bump(nt, bsdf, n.outputs["Fac"], 0.12 * detail)
        elif choice == "plaster":
            n = _noise(nt, obj, 35.0, 10.0)
            _bump(nt, bsdf, n.outputs["Fac"], 0.25 * detail)
            _vary(nt, bsdf, base, obj, 2.0, 0.05)
        else:                                   # smooth paint
            n = _noise(nt, obj, 80.0, 4.0)
            _bump(nt, bsdf, n.outputs["Fac"], 0.04 * detail)
    elif cat == "concrete":
        _val(bsdf, rough, 0.88)
        _vary(nt, bsdf, base, obj, 3.0, 0.2)
        n = _noise(nt, obj, 50.0, 8.0)
        _bump(nt, bsdf, n.outputs["Fac"], 0.15 * detail)
    elif cat == "brick":
        br = nt.nodes.new("ShaderNodeTexBrick")
        nt.links.new(wall, br.inputs["Vector"])
        _val(br, ("Scale",), 2.2)
        _val(br, ("Mortar Size",), 0.008)
        _val(br, ("Row Height",), 0.16)
        _val(br, ("Brick Width",), 0.5)
        c1 = base if sum(base) > 0.2 else (0.55, 0.25, 0.17)
        _val(br, ("Color1",), (*c1, 1.0))
        _val(br, ("Color2",), (*[c * 0.78 for c in c1], 1.0))
        _val(br, ("Mortar",), (0.72, 0.70, 0.66, 1.0))
        s = bsdf.inputs["Base Color"]
        _unlink(s)
        nt.links.new(br.outputs["Color"], s)
        _val(bsdf, rough, 0.85)
        _bump(nt, bsdf, br.outputs["Fac"], 0.35 * detail)
    elif cat == "stone":
        rgb = PRESET_RGB.get(choice)
        if rgb:
            _set_base(bsdf, rgb)
            base = rgb
        _val(bsdf, rough, 0.45 if choice == "granite" else 0.7)
        _vary(nt, bsdf, base, obj, 6.0, 0.22)
        v = nt.nodes.new("ShaderNodeTexVoronoi")
        nt.links.new(obj, v.inputs["Vector"])
        _val(v, ("Scale",), 12.0)
        _bump(nt, bsdf, v.outputs["Distance"], 0.2 * detail)
    elif cat == "floor":
        if choice == "marble":
            _val(bsdf, rough, 0.08)
            _vary(nt, bsdf, base, obj, 1.5, 0.08)
        elif choice == "wood":
            make_wood(nt, bsdf, obj, PRESET_RGB["oak"], detail)
        else:
            _val(bsdf, rough, 0.35)
    elif cat == "paving":
        _val(bsdf, rough, 0.75)
        if not bsdf.inputs["Base Color"].links:
            _vary(nt, bsdf, base, obj, 4.0, 0.15)
        n = _noise(nt, obj, 25.0, 6.0)
        _bump(nt, bsdf, n.outputs["Fac"], 0.2 * detail)
    elif cat == "wood":
        rgb = PRESET_RGB.get(choice) or base
        make_wood(nt, bsdf, obj, rgb, detail)
    elif cat == "metal":
        rgb = PRESET_RGB.get(choice)
        if rgb:
            _set_base(bsdf, rgb)
        if choice == "steel":
            _val(bsdf, ("Metallic",), 1.0)
            _val(bsdf, rough, 0.28)
        else:                                  # powder-coat / iron
            _val(bsdf, ("Metallic",), 0.3)
            _val(bsdf, rough, 0.45)
    elif cat == "glass":
        _val(bsdf, rough, 0.0)
        _val(bsdf, ("IOR",), 1.45)
        _val(bsdf, ("Alpha",), 1.0)
        if choice == "reflective":
            _set_base(bsdf, (0.10, 0.14, 0.18))
            _val(bsdf, ("Metallic",), 0.7)
            _val(bsdf, rough, 0.03)
        else:
            tint = {"tinted": (0.55, 0.70, 0.80), "frosted": (0.92, 0.94,
                                                                0.95)}.get(
                choice, (0.92, 0.96, 0.97))
            _set_base(bsdf, tint)
            _val(bsdf, ("Transmission Weight", "Transmission"), 1.0)
            if choice == "frosted":
                _val(bsdf, rough, 0.35)
        for attr, value in (("blend_method", "OPAQUE"),
                            ("use_raytrace_refraction", True),
                            ("use_screen_refraction", True)):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, value)
                except (TypeError, ValueError):
                    pass
    elif cat == "tiles":
        rgb = PRESET_RGB.get(choice)
        if rgb:
            _set_base(bsdf, rgb)
            base = rgb
        w = nt.nodes.new("ShaderNodeTexWave")
        nt.links.new(obj, w.inputs["Vector"])
        try:
            w.bands_direction = "Z"
        except (TypeError, AttributeError):
            pass
        _val(w, ("Scale",), 3.0)
        _val(w, ("Distortion",), 0.0)
        _vary(nt, bsdf, base, obj, 5.0, 0.18)
        _val(bsdf, rough, 0.6)
        _bump(nt, bsdf, w.outputs["Fac"], 0.5 * detail, 0.03)
    elif cat == "grass":
        _val(bsdf, rough, 0.95)
        if choice != "plain":
            s = bsdf.inputs["Base Color"]
            _unlink(s)
            n = _noise(nt, obj, 9.0, 12.0)
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
            ramp.color_ramp.elements[0].color = (0.06, 0.16, 0.03, 1.0)
            ramp.color_ramp.elements[1].color = (0.22, 0.38, 0.08, 1.0)
            nt.links.new(ramp.outputs["Color"], s)
            n2 = _noise(nt, obj, 120.0, 4.0)
            _bump(nt, bsdf, n2.outputs["Fac"], 0.6 * detail)
    elif cat == "soil":
        _val(bsdf, rough, 0.95)
        _vary(nt, bsdf, base, obj, 8.0, 0.3)
        n = _noise(nt, obj, 40.0, 8.0)
        _bump(nt, bsdf, n.outputs["Fac"], 0.5 * detail)
    elif cat == "fabric":
        _val(bsdf, rough, 0.95)
        _val(bsdf, ("Sheen Weight", "Sheen"), 0.4)
    elif cat == "glow":
        strength = float(opt.get("glow", 12.0))
        s_c = _inp(bsdf, "Emission Color", "Emission")
        if s_c is not None:
            _unlink(s_c)
            s_c.default_value = (1.0, 0.78, 0.45, 1.0)
        _val(bsdf, ("Emission Strength",), strength)
    else:
        return False
    return True


def make_wood(nt, bsdf, obj, rgb, detail):
    s = bsdf.inputs["Base Color"]
    _unlink(s)
    w = nt.nodes.new("ShaderNodeTexWave")
    nt.links.new(obj, w.inputs["Vector"])
    try:
        w.wave_type = "RINGS"
    except (TypeError, AttributeError):
        pass
    _val(w, ("Scale",), 4.0)
    _val(w, ("Distortion",), 8.0)
    _val(w, ("Detail",), 3.0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(w.outputs["Fac"], ramp.inputs["Fac"])
    ramp.color_ramp.elements[0].color = (*[c * 0.7 for c in rgb], 1.0)
    ramp.color_ramp.elements[1].color = (*[min(1, c * 1.15) for c in rgb],
                                         1.0)
    nt.links.new(ramp.outputs["Color"], s)
    _val(bsdf, ("Roughness",), 0.45)
    _bump(nt, bsdf, w.outputs["Fac"], 0.05 * detail)


def _cat_of(mat, cmap, tmap):
    """What a material is: by its image's name, else by its colour (the
    map IngeTrazo's side made from the model's elements)."""
    bsdf = _bsdf(mat)
    if bsdf is None:
        return None
    sock = bsdf.inputs["Base Color"]
    if sock.links:
        node = sock.links[0].from_node
        img = getattr(node, "image", None)
        name = os.path.basename(getattr(img, "filepath", "") or
                                getattr(img, "name", "") or "").lower()
        for key, cat in tmap.items():
            if key and key in name:
                return cat
        for kw, cat in (("grass", "grass"), ("lawn", "grass"),
                        ("paver", "paving"), ("paving", "paving"),
                        ("brick", "brick"), ("wood", "wood"),
                        ("marble", "floor"), ("tile", "floor"),
                        ("stone", "stone"), ("granite", "stone")):
            if kw in name:
                return cat
        return None
    c = tuple(sock.default_value)[:3]
    best, bd = None, 0.02
    for r, g, b, cat in cmap:
        d = max(abs(c[0] - r), abs(c[1] - g), abs(c[2] - b))
        if d < bd:
            best, bd = cat, d
    return best


def apply_materials(c2i):
    cmap = c2i.get("colors") or []
    tmap = c2i.get("textures") or {}
    opt = c2i.get("materials") or {}
    detail = float(opt.get("detail", 1.0))
    counts = {}
    for mat in list(bpy.data.materials):
        if mat.name.startswith("IngeTrazo ground"):
            continue
        cat = _cat_of(mat, cmap, tmap)
        if cat is None:
            continue
        try:
            if make(mat, cat, opt, detail):
                counts[cat] = counts.get(cat, 0) + 1
        except Exception as e:  # noqa: BLE001 — a plainer material is fine
            say("material", mat.name, "kept:", e)
    say("materials", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


# ---- the environment -----------------------------------------------------------------
def _sun_dir(az_deg, el_deg):
    """Toward the sun: azimuth from north (+y) clockwise, elevation up."""
    a, e = math.radians(az_deg), math.radians(el_deg)
    return (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e),
            math.sin(e))


def environment(scene, job, c2i):
    env = c2i.get("env") or {}
    sky = env.get("sky", "day")
    sun_k = float(env.get("sun_k", 1.0))
    sky_k = float(env.get("sky_k", 1.0))
    # the job's sun (the Shadows panel) unless set here
    if env.get("sun_custom") or sky in ("golden", "blue") or \
            job.get("sun") is None:
        el = {"golden": 6.0, "blue": -4.0}.get(sky, float(
            env.get("sun_el", 45.0)))
        if env.get("sun_custom"):
            el = float(env.get("sun_el", el))
        sun_dir = _sun_dir(float(env.get("sun_az", 135.0)), el)
    else:
        sun_dir = tuple(job["sun"])
    for o in list(scene.objects):          # the base script's sky lights
        if o.type == "LIGHT" and o.data.type == "SUN":
            bpy.data.objects.remove(o, do_unlink=True)
    if sky.startswith("hdri"):
        path = env.get("hdri")
        if path and str(path).startswith("builtin:"):
            path = os.path.join(bpy.utils.system_resource(
                "DATAFILES", path="studiolights/world"),
                str(path).split(":", 1)[1] + ".exr")
        if path and os.path.isfile(path):
            night = "night" in os.path.basename(path).lower()
            set_hdri(scene, path, (0.35 if night else 1.0) * sky_k,
                     float(env.get("h_rot", 0.0)),
                     bool(env.get("h_bg", True)))
            if env.get("sun_custom"):
                s = add_sun(scene, _sun_dir(float(env.get("sun_az", 135.0)),
                                            float(env.get("sun_el", 40.0))),
                            4.0 * sun_k)
            say("environment", "hdri", os.path.basename(path))
        else:
            say("environment", "hdri missing:", path, "- a physical sky")
            set_world(scene, sun_dir)
            if sun_dir[2] > 0:
                add_sun(scene, sun_dir, 4.0 * sun_k)
    elif sky == "night":
        set_plain_world(scene, (0.008, 0.013, 0.03), 1.0 * sky_k, "night")
        add_moon(scene)
    elif sky == "overcast":
        set_plain_world(scene, (0.62, 0.66, 0.70), 1.0 * sky_k, "overcast")
    else:
        if sun_dir[2] > 0:
            s = add_sun(scene, sun_dir, {"golden": 2.5}.get(sky, 4.0)
                        * sun_k)
            if sky == "golden":
                s.data.color = (1.0, 0.72, 0.45)
        set_world(scene, sun_dir)
        bg = scene.world.node_tree.nodes.get("Background")
        if bg is not None:
            bg.inputs["Strength"].default_value *= sky_k * (
                {"golden": 1.4, "blue": 3.0}.get(sky, 1.0))
    if not sky.startswith("hdri"):
        say("environment", sky)
    # the ground beyond the plot
    gnd = env.get("ground", "grass")
    if gnd != "none":
        cols = {"grass": (0.07, 0.16, 0.04), "concrete": (0.45, 0.44, 0.42),
                "asphalt": (0.06, 0.06, 0.065), "plain": (0.42, 0.42, 0.40),
                "sand": (0.66, 0.56, 0.40)}
        for o in list(scene.objects):
            if o.name.startswith("IngeTrazo ground"):
                bpy.data.objects.remove(o, do_unlink=True)
        z = (job.get("ground") or {}).get("z", -0.002) - 0.01
        add_ground(scene, z, 2000.0, cols.get(gnd, cols["plain"]))
        g = bpy.data.materials.get("IngeTrazo ground")
        if g is not None:
            make(g, "grass" if gnd == "grass" else "concrete", {}, 1.0)
    # haze: a thin volume in the world (Cycles)
    haze = float(env.get("haze", 0.0))
    if haze > 0 and scene.world and scene.world.node_tree:
        nt = scene.world.node_tree
        vol = nt.nodes.new("ShaderNodeVolumeScatter")
        _val(vol, ("Density",), 0.0015 * haze)
        out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None)
        if out is not None:
            nt.links.new(vol.outputs[0], out.inputs["Volume"])
    # exposure and contrast
    view = scene.view_settings
    view.exposure = float(env.get("exposure", view.exposure))
    look = env.get("look")
    if look:
        for name in (f"AgX - {look}", look):
            try:
                view.look = name
                break
            except TypeError:
                continue
    scene.render.film_transparent = bool(env.get("transparent", False))
    if env.get("bloom"):
        _bloom(scene)


def set_hdri(scene, path, strength, rot_deg, show_bg=True):
    """A photographed sky: the HDR image all round, lighting the scene (and
    seen behind it, or only its light with a plain sky behind)."""
    world = bpy.data.worlds.new("C2I HDRI")
    scene.world = world
    if hasattr(world, "use_nodes"):
        world.use_nodes = True
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links
    bg = nodes.get("Background") or nodes.new("ShaderNodeBackground")
    out = next((n for n in nodes if n.type == "OUTPUT_WORLD"), None) or \
        nodes.new("ShaderNodeOutputWorld")
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(path, check_existing=True)
    tc = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    rot = mp.inputs.get("Rotation")
    if rot is not None:
        rot.default_value[2] = math.radians(rot_deg)
    links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    links.new(mp.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    if show_bg:
        links.new(bg.outputs[0], out.inputs["Surface"])
        return
    # only its light: the camera sees a plain sky
    plain = nodes.new("ShaderNodeBackground")
    plain.inputs["Color"].default_value = (0.55, 0.68, 0.85, 1.0)
    plain.inputs["Strength"].default_value = 1.0
    lp = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    links.new(bg.outputs[0], mix.inputs[1])
    links.new(plain.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])


def _bloom(scene):
    """A soft glow round the lamps (the compositor's Glare, fog glow)."""
    try:
        if hasattr(scene, "compositing_node_group"):     # Blender 5
            tree = bpy.data.node_groups.new("C2I glow",
                                            "CompositorNodeTree")
            scene.compositing_node_group = tree
            inp = tree.nodes.new("NodeGroupInput")
            out = tree.nodes.new("NodeGroupOutput")
            tree.interface.new_socket("Image", in_out="INPUT",
                                      socket_type="NodeSocketColor")
            tree.interface.new_socket("Image", in_out="OUTPUT",
                                      socket_type="NodeSocketColor")
            rl = tree.nodes.new("CompositorNodeRLayers")
            gl = tree.nodes.new("CompositorNodeGlare")
            for attr, v in (("glare_type", "FOG_GLOW"), ("quality", "HIGH"),
                            ("size", 7)):
                try:
                    setattr(gl, attr, v)
                except (TypeError, AttributeError, ValueError):
                    pass
            for nm, v in (("Type", "Fog Glow"), ("Threshold", 1.0),
                          ("Size", 0.6)):
                s = gl.inputs.get(nm)
                if s is not None:
                    try:
                        s.default_value = v
                    except (TypeError, ValueError):
                        pass
            tree.links.new(rl.outputs["Image"], gl.inputs["Image"])
            tree.links.new(gl.outputs["Image"], out.inputs[0])
            del inp
        else:
            scene.use_nodes = True
            tree = scene.node_tree
            rl = tree.nodes.get("Render Layers") or tree.nodes.new(
                "CompositorNodeRLayers")
            comp = tree.nodes.get("Composite") or tree.nodes.new(
                "CompositorNodeComposite")
            gl = tree.nodes.new("CompositorNodeGlare")
            gl.glare_type = "FOG_GLOW"
            gl.size = 7
            tree.links.new(rl.outputs["Image"], gl.inputs["Image"])
            tree.links.new(gl.outputs["Image"], comp.inputs["Image"])
        say("glow", "on")
    except Exception as e:  # noqa: BLE001
        say("glow", "off:", e)


# ---- main ---------------------------------------------------------------------------
def c2i_main():
    job = load_job()
    c2i = job.get("c2i") or {}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    import_model(job["glb"])
    apply_finishes()
    apply_materials(c2i)
    figures = find_figures()
    w, h = int(job["width"]), int(job["height"])
    set_camera(scene, job["camera"], w, h)
    face_figures(figures, job["camera"])
    if job.get("ground"):
        g = job["ground"]
        add_ground(scene, g["z"], g["size"], g["color"])
    add_lights(scene, job.get("lights") or [])
    set_engine(scene, job.get("engine", "cycles"), int(job.get("samples", 64)))
    r = scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
    r.image_settings.file_format = "PNG"
    r.filepath = job["output"]
    view = scene.view_settings
    view.exposure = float(job.get("exposure", -0.6))
    environment(scene, job, c2i)
    if scene.render.engine == "CYCLES":
        try:
            scene.cycles.use_denoising = True
            scene.cycles.max_bounces = 8
        except AttributeError:
            pass
    last = {"text": None}

    def _stats(text, *_a):
        text = str(text)
        if text != last["text"]:
            last["text"] = text
            say("stats", text.replace("\n", " "))

    if hasattr(bpy.app.handlers, "render_stats"):
        bpy.app.handlers.render_stats.append(_stats)
    say("rendering", w, "x", h)
    bpy.ops.render.render(write_still=True)
    if job.get("blend"):
        bpy.ops.wm.save_as_mainfile(filepath=job["blend"])
        say("blend", job["blend"])
    say("done", job["output"])


c2i_main()
