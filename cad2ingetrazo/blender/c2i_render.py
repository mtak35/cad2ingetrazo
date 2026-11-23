# CAD2IngeTrazo 3.64.58 — runs INSIDE Blender, on top of IngeTrazo's own
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
            # a real lawn: deep and lighter greens with drier patches,
            # not one bright green
            els = ramp.color_ramp.elements
            els[0].color = (0.035, 0.075, 0.018, 1.0)
            els[1].color = (0.13, 0.19, 0.05, 1.0)
            els[1].position = 0.75
            mid = els.new(0.45)
            mid.color = (0.075, 0.13, 0.03, 1.0)
            nt.links.new(ramp.outputs["Color"], s)
            n2 = _noise(nt, obj, 160.0, 6.0)
            _bump(nt, bsdf, n2.outputs["Fac"], 0.8 * detail)
            _val(bsdf, ("Sheen Weight", "Sheen"), 0.25)   # blades' fuzz
            _val(bsdf, ("Sheen Tint",), (0.30, 0.45, 0.12, 1.0))
            _val(bsdf, ("Specular IOR Level", "Specular"), 0.2)
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
        if cat not in ("glow", "glass"):
            _albedo(mat)
        try:
            if make(mat, cat, opt, detail):
                counts[cat] = counts.get(cat, 0) + 1
        except Exception as e:  # noqa: BLE001 — a plainer material is fine
            say("material", mat.name, "kept:", e)
        if cat in ("wall", "stone", "concrete", "floor", "brick", "tiles",
                   "wood", "paving"):
            _bevel(mat)
    say("materials", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


def _albedo(mat, cap=0.74):
    """No plaster is whiter than ~60 %: a model's pure white renders as a
    blown-out glare. The colour kept, its brightness capped."""
    bsdf = _bsdf(mat)
    if bsdf is None:
        return
    sock = bsdf.inputs["Base Color"]
    if sock.links:
        return
    c = list(sock.default_value)
    m = max(c[:3])
    if m > cap:
        k = cap / m
        sock.default_value = (c[0] * k, c[1] * k, c[2] * k, c[3])


def _bevel(mat, radius=0.012):
    """Rounded edges in the shading (Cycles): the light catches each
    corner as on a real wall instead of a razor-sharp CG edge."""
    bsdf = _bsdf(mat)
    if bsdf is None:
        return
    nt = mat.node_tree
    try:
        bv = nt.nodes.new("ShaderNodeBevel")
    except RuntimeError:
        return
    _val(bv, ("Radius",), radius)
    if hasattr(bv, "samples"):
        bv.samples = 6
    n_in = bsdf.inputs["Normal"]
    if n_in.links:                       # a bump: the bevel under it
        src = n_in.links[0].from_node
        if src.type == "BUMP" and not src.inputs["Normal"].links:
            nt.links.new(bv.outputs["Normal"], src.inputs["Normal"])
    else:
        nt.links.new(bv.outputs["Normal"], n_in)


# ---- the environment -----------------------------------------------------------------
def _sun_dir(az_deg, el_deg):
    """Toward the sun: azimuth from north (+y) clockwise, elevation up."""
    a, e = math.radians(az_deg), math.radians(el_deg)
    return (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e),
            math.sin(e))


def _front_light(job, sun_dir, env):
    """3.64.93: a sun behind the building leaves the facade seen from the
    camera in shade — flat, grey. Unless the user set it, a sun that comes
    from the far side is turned to light the view from the front-side
    (35° off the camera's back, 38° up): lit planes, long side shadows."""
    if env.get("sun_custom"):
        return sun_dir
    cam = job.get("camera") or {}
    try:
        fx = cam["target"][0] - cam["eye"][0]
        fy = cam["target"][1] - cam["eye"][1]
    except (KeyError, IndexError, TypeError):
        return sun_dir
    L = math.hypot(fx, fy)
    if L < 1e-6 or sun_dir[2] <= 0 or sun_dir[2] > 0.95:
        return sun_dir
    fx, fy = fx / L, fy / L
    h = math.hypot(sun_dir[0], sun_dir[1]) or 1.0
    if (sun_dir[0] * fx + sun_dir[1] * fy) / h < 0.34:   # not from far side
        return sun_dir
    a = math.radians(-15.0)                # behind the camera, a little right
    bx, by = -fx, -fy
    cx = bx * math.cos(a) - by * math.sin(a)
    cy = bx * math.sin(a) + by * math.cos(a)
    e = math.radians(45.0)
    return (cx * math.cos(e), cy * math.cos(e), math.sin(e))


# ---- city / forest beyond the plot (3.64.96) ---------------------------------------
def _site_box(scene):
    """(cx, cy, radius) of the model — what stands on the plot."""
    xs, ys = [], []
    for o in scene.objects:
        if o.type != "MESH" or o.name.startswith("IngeTrazo ground"):
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            xs.append(w.x)
            ys.append(w.y)
    if not xs:
        return 0.0, 0.0, 30.0
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    r = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
    return cx, cy, max(r, 10.0)


def _cam_xy(scene):
    c = scene.camera
    if c is None:
        return None
    return c.matrix_world.translation.x, c.matrix_world.translation.y


def _pbr(name, col, rough=0.85):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = _bsdf(m)
    if b is not None:
        b.inputs["Base Color"].default_value = (*col, 1.0)
        b.inputs["Roughness"].default_value = rough
    return m


def _facade(name, col):
    """A building's wall with floors of windows: lit by the world's own
    coordinates (3 m bays, 3.2 m floors); the glass dark and glossy, the
    roofs plain."""
    m = _pbr(name, col)
    nt = m.node_tree
    b = _bsdf(m)
    try:
        N = nt.nodes

        def math_(op, a=None, b_=None, clamp=False):
            n = N.new("ShaderNodeMath")
            n.operation = op
            n.use_clamp = clamp
            if a is not None:
                n.inputs[0].default_value = a
            if b_ is not None:
                n.inputs[1].default_value = b_
            return n
        L = nt.links.new
        tc = N.new("ShaderNodeTexCoord")
        sp = N.new("ShaderNodeSeparateXYZ")
        L(tc.outputs["Object"], sp.inputs["Vector"])
        xy = math_("ADD")
        L(sp.outputs["X"], xy.inputs[0])
        L(sp.outputs["Y"], xy.inputs[1])
        fu = math_("FRACT")
        L(math_("DIVIDE", None, 3.0).outputs[0], fu.inputs[0]) \
            if False else None
        du = math_("DIVIDE", None, 3.0)
        L(xy.outputs[0], du.inputs[0])
        L(du.outputs[0], fu.inputs[0])
        dv = math_("DIVIDE", None, 3.2)
        L(sp.outputs["Z"], dv.inputs[0])
        fv = math_("FRACT")
        L(dv.outputs[0], fv.inputs[0])

        def band(src, lo, hi):
            g = math_("GREATER_THAN", None, lo)
            L(src.outputs[0], g.inputs[0])
            l = math_("LESS_THAN", None, hi)
            L(src.outputs[0], l.inputs[0])
            r = math_("MULTIPLY")
            L(g.outputs[0], r.inputs[0])
            L(l.outputs[0], r.inputs[1])
            return r
        wu, wv = band(fu, 0.18, 0.82), band(fv, 0.28, 0.80)
        win = math_("MULTIPLY")
        L(wu.outputs[0], win.inputs[0])
        L(wv.outputs[0], win.inputs[1])
        gn = N.new("ShaderNodeNewGeometry")
        sn = N.new("ShaderNodeSeparateXYZ")
        L(gn.outputs["Normal"], sn.inputs["Vector"])
        ab = math_("ABSOLUTE")
        L(sn.outputs["Z"], ab.inputs[0])
        wall = math_("LESS_THAN", None, 0.5)
        L(ab.outputs[0], wall.inputs[0])
        fin = math_("MULTIPLY")
        L(win.outputs[0], fin.inputs[0])
        L(wall.outputs[0], fin.inputs[1])
        mix = N.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = (*col, 1.0)
        mix.inputs["B"].default_value = (0.05, 0.09, 0.15, 1.0)
        L(fin.outputs[0], mix.inputs["Factor"])
        L(mix.outputs["Result"], b.inputs["Base Color"])
        rg = math_("SUBTRACT", 0.85)
        L(fin.outputs[0], rg.inputs[1])
        L(rg.outputs[0], b.inputs["Roughness"])
    except Exception:  # noqa: BLE001
        pass
    return m


def _join_boxes(name, boxes, mat):
    """boxes [(x, y, z0, sx, sy, h)] → one mesh object."""
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for x, y, z0, sx, sy, h in boxes:
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(sx, sy, h), verts=r["verts"])
        bmesh.ops.translate(bm, vec=(x, y, z0 + h / 2), verts=r["verts"])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    scene = bpy.context.scene
    scene.collection.objects.link(ob)
    return ob


def _tex_noise(nt, scale=2.0, detail=6.0):
    """A world-space noise node (Fac output) for colour variation."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    return nz


def _leaf_mat(name, col, var=0.35):
    """Foliage: the colour broken up by noise (light and dark leaf masses),
    rough, a little sheen."""
    m = _pbr(name, col, 0.7)
    nt = m.node_tree
    b = _bsdf(m)
    try:
        nz = _tex_noise(nt, 0.9, 8.0)
        cr = nt.nodes.new("ShaderNodeValToRGB")
        cr.color_ramp.elements[0].color = (col[0] * (1 - var),
                                           col[1] * (1 - var),
                                           col[2] * (1 - var), 1)
        cr.color_ramp.elements[1].color = (col[0] * (1 + var),
                                           col[1] * (1 + var * 1.2),
                                           col[2] * (1 + var * 0.6), 1)
        nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
        nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
    except Exception:  # noqa: BLE001
        pass
    return m


def _jitter(bm, verts, amt, rnd):
    for v in verts:
        v.co.x += (rnd.random() - 0.5) * amt
        v.co.y += (rnd.random() - 0.5) * amt
        v.co.z += (rnd.random() - 0.5) * amt


def _add_tree(trunk, crowns, x, y, z, h, rnd, kind="broad"):
    """One tree into the shared bmeshes: ``trunk`` and ``crowns`` (a list
    of bmeshes by leaf colour). kind: broad (3 jittered masses), conifer
    (stacked cones), palm (curved trunk, fronds)."""
    import bmesh
    cb = crowns[rnd.randrange(len(crowns))]
    if kind == "conifer":
        r = bmesh.ops.create_cone(trunk, cap_ends=True, segments=6,
                                  radius1=h * 0.02 + 0.08,
                                  radius2=h * 0.012 + 0.05, depth=h * 0.35)
        bmesh.ops.translate(trunk, vec=(x, y, z + h * 0.175),
                            verts=r["verts"])
        for lv in range(4):
            rad = h * (0.24 - 0.045 * lv)
            r = bmesh.ops.create_cone(cb, cap_ends=False, segments=9,
                                      radius1=rad, radius2=rad * 0.12,
                                      depth=h * 0.34)
            _jitter(cb, r["verts"], rad * 0.18, rnd)
            bmesh.ops.translate(cb, vec=(x, y, z + h * (0.30 + 0.17 * lv)),
                                verts=r["verts"])
        return
    if kind == "palm":
        lean = (rnd.random() - 0.5) * 0.18
        r = bmesh.ops.create_cone(trunk, cap_ends=True, segments=6,
                                  radius1=h * 0.028 + 0.08,
                                  radius2=h * 0.016 + 0.05, depth=h * 0.92)
        for v in r["verts"]:
            v.co.x += lean * max(0.0, v.co.z + h * 0.46) ** 1.3 * 0.12
        bmesh.ops.translate(trunk, vec=(x, y, z + h * 0.46),
                            verts=r["verts"])
        tx, ty, tz = x + lean * h ** 1.3 * 0.12 * 0.95, y, z + h * 0.92
        for k in range(9):          # fronds: tilted flat cones
            a = k / 9 * 2 * math.pi + rnd.random() * 0.3
            r = bmesh.ops.create_cone(cb, cap_ends=False, segments=3,
                                      radius1=h * 0.045, radius2=0.01,
                                      depth=h * 0.42)
            bmesh.ops.rotate(cb, cent=(0, 0, 0), verts=r["verts"],
                             matrix=__import__("mathutils").Matrix.Rotation(
                                 math.radians(80), 3, "Y"))
            bmesh.ops.rotate(cb, cent=(0, 0, 0), verts=r["verts"],
                             matrix=__import__("mathutils").Matrix.Rotation(
                                 a, 3, "Z"))
            for v in r["verts"]:
                v.co.z -= 0.0
            bmesh.ops.translate(cb, vec=(tx + math.cos(a) * h * 0.2,
                                         ty + math.sin(a) * h * 0.2,
                                         tz - h * 0.04), verts=r["verts"])
        return
    rc = h * (0.2 + 0.08 * rnd.random())
    r = bmesh.ops.create_cone(trunk, cap_ends=True, segments=7,
                              radius1=h * 0.032 + 0.1,
                              radius2=h * 0.018 + 0.06, depth=h * 0.55)
    bmesh.ops.translate(trunk, vec=(x, y, z + h * 0.275), verts=r["verts"])
    for lv in range(3):
        r = bmesh.ops.create_icosphere(cb, subdivisions=2,
                                       radius=rc * (0.7 + 0.35 *
                                                    rnd.random()))
        bmesh.ops.scale(cb, vec=(1.0, 1.0, 0.85), verts=r["verts"])
        _jitter(cb, r["verts"], rc * 0.35, rnd)
        bmesh.ops.translate(cb, vec=(
            x + (rnd.random() - 0.5) * rc * 1.2,
            y + (rnd.random() - 0.5) * rc * 1.2,
            z + h * (0.58 + 0.16 * lv) + rnd.random() * rc * 0.25),
            verts=r["verts"])


def _flush_trees(scene, name, trunk, crowns, tmat, lmats):
    import bmesh
    for nm, bm, mat in [(name + " trunks", trunk, tmat)] + [
            (name + " leaves %d" % i, b, lmats[i])
            for i, b in enumerate(crowns)]:
        me = bpy.data.meshes.new(nm)
        bm.to_mesh(me)
        bm.free()
        for p_ in me.polygons:
            p_.use_smooth = True
        ob = bpy.data.objects.new(nm, me)
        ob.data.materials.append(mat)
        scene.collection.objects.link(ob)


def city_view(scene, z, seed=7):
    """Blocks round the site: concrete blocks with windows, glass towers,
    stepped tops and roof plant; streets with lane marks; street trees."""
    import bmesh
    import random
    rnd = random.Random(seed)
    cx, cy, R = _site_box(scene)
    cam = _cam_xy(scene)
    r0 = R + 28.0
    pitch, street = 62.0, 16.0
    blk = pitch - street
    pal = [(0.62, 0.58, 0.50), (0.72, 0.70, 0.66), (0.50, 0.50, 0.52),
           (0.55, 0.36, 0.28), (0.78, 0.74, 0.64)]
    mats = [_facade("City %d" % i, c) for i, c in enumerate(pal)]
    glass = _pbr("City glass", (0.10, 0.20, 0.27), 0.12)
    try:
        _bsdf(glass).inputs["Metallic"].default_value = 0.85
    except Exception:  # noqa: BLE001
        pass
    roof_m = _pbr("City roof", (0.32, 0.31, 0.30), 0.9)
    pad_m = _pbr("City pavement", (0.50, 0.49, 0.47), 0.9)
    mark_m = _pbr("City lane mark", (0.85, 0.85, 0.80), 0.7)
    per = [[] for _ in pal]
    gl, roofs, pads, marks = [], [], [], []
    tr, cr = bmesh.new(), [bmesh.new(), bmesh.new()]
    n = int(480 / pitch) + 1
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = cx + i * pitch, cy + j * pitch
            d = math.hypot(x - cx, y - cy)
            if d < r0 + blk / 2 or d > 520:
                continue
            if cam and math.hypot(x - cam[0], y - cam[1]) < 60.0:
                continue                 # not round the camera
            pads.append((x, y, z, blk + 4, blk + 4, 0.2))
            k = rnd.randrange(1, 4)
            for _ in range(k):
                sx = blk * (0.35 + 0.4 * rnd.random())
                sy = blk * (0.35 + 0.4 * rnd.random())
                bx = x + (rnd.random() - 0.5) * (blk - sx) * 0.9
                by = y + (rnd.random() - 0.5) * (blk - sy) * 0.9
                lo = 9.0 + 0.04 * d
                h = lo + rnd.random() ** 2 * (28.0 + 0.12 * d)
                h = round(h / 3.2) * 3.2
                tower = h > 28 and rnd.random() < 0.55
                if tower:
                    gl.append((bx, by, z + 0.2, sx * 0.8, sy * 0.8, h))
                    top = z + 0.2 + h
                    gl.append((bx, by, top, sx * 0.5, sy * 0.5, 4.5))
                else:
                    per[rnd.randrange(len(pal))].append(
                        (bx, by, z + 0.2, sx, sy, h))
                    top = z + 0.2 + h
                    if rnd.random() < 0.6:     # roof plant / lift head
                        roofs.append((bx + (rnd.random() - 0.5) * sx * 0.4,
                                      by + (rnd.random() - 0.5) * sy * 0.4,
                                      top, sx * 0.25, sy * 0.25, 3.0))
                if rnd.random() < 0.15:        # a stepped podium
                    per[0].append((bx, by, z + 0.2, sx * 1.15, sy * 1.15,
                                   6.4))
            for t_ in range(3):               # street trees on the kerb
                a = rnd.random() * 2 * math.pi
                rr = blk / 2 + 4.5
                _add_tree(tr, cr, x + math.cos(a) * rr * (1 if t_ % 2 else
                          0.2) + (rnd.random() - 0.5) * blk,
                          y + math.sin(a) * rr, z, 6.0 + rnd.random() * 3,
                          rnd, "broad")
    # lane marks: dashed centre lines along the streets within 230 m
    for i in range(-4, 5):
        for j in range(-4, 5):
            for ax in (0, 1):
                gx = cx + (i + 0.5) * pitch if ax == 0 else cx + i * pitch
                gy = cy + j * pitch if ax == 0 else cy + (j + 0.5) * pitch
                for q in range(-4, 5):
                    px = gx if ax == 0 else gx + q * 6.5
                    py = gy + q * 6.5 if ax == 0 else gy
                    dd = math.hypot(px - cx, py - cy)
                    if dd < r0 + 10 or dd > 230:
                        continue
                    if cam and math.hypot(px - cam[0], py - cam[1]) < 30:
                        continue
                    marks.append((px, py, z + 0.01, 0.2 if ax == 0 else 3.0,
                                  3.0 if ax == 0 else 0.2, 0.01))
    _join_boxes("IngeTrazo city pads", pads, pad_m)
    if gl:
        _join_boxes("IngeTrazo city glass", gl, glass)
    if roofs:
        _join_boxes("IngeTrazo city roof plant", roofs, roof_m)
    if marks:
        _join_boxes("IngeTrazo city lane marks", marks, mark_m)
    for i, bx in enumerate(per):
        if bx:
            _join_boxes("IngeTrazo city %d" % i, bx, mats[i])
    _flush_trees(scene, "IngeTrazo city trees", tr, cr,
                 _pbr("City trunk", (0.2, 0.13, 0.08)),
                 [_leaf_mat("City leaf %d" % i, c) for i, c in enumerate(
                     [(0.12, 0.28, 0.08), (0.18, 0.32, 0.09)])])
    say("city view", sum(len(b) for b in per) + len(gl), "buildings")


def forest_view(scene, z, seed=11):
    """A wood round the site: broadleaf trees (jittered, noise-coloured
    crowns) mixed with conifers, denser and taller with distance; a mown
    clearing round the house."""
    import bmesh
    import random
    rnd = random.Random(seed)
    cx, cy, R = _site_box(scene)
    cam = _cam_xy(scene)
    r0 = R + 14.0
    greens = [(0.10, 0.25, 0.07), (0.14, 0.30, 0.08), (0.08, 0.20, 0.06),
              (0.22, 0.34, 0.09)]
    lm = [_leaf_mat("Forest leaf %d" % i, c) for i, c in enumerate(greens)]
    tm = _pbr("Forest trunk", (0.16, 0.10, 0.06), 0.9)
    con_m = [_leaf_mat("Forest conifer %d" % i, c, 0.25) for i, c in
             enumerate([(0.04, 0.14, 0.07), (0.06, 0.18, 0.08)])]
    trunk = bmesh.new()
    crowns = [bmesh.new() for _ in greens]
    ctr = bmesh.new()
    con = [bmesh.new() for _ in con_m]
    n = 0
    for _ in range(1500):
        a = rnd.random() * 2 * math.pi
        d = r0 + (rnd.random() ** 0.8) * (420.0 - r0)
        x, y = cx + d * math.cos(a), cy + d * math.sin(a)
        if cam and math.hypot(x - cam[0], y - cam[1]) < 14.0:
            continue
        h = (8.0 + rnd.random() * 10.0) * (1.0 + d / 500.0)
        if rnd.random() < 0.3:
            _add_tree(ctr, con, x, y, z, h * 1.15, rnd, "conifer")
        else:
            _add_tree(trunk, crowns, x, y, z, h, rnd, "broad")
        n += 1
    _flush_trees(scene, "IngeTrazo forest", trunk, crowns, tm, lm)
    _flush_trees(scene, "IngeTrazo forest conifers", ctr, con, tm, con_m)
    say("forest view", n, "trees")


def society_view(scene, z, seed=5):
    """A housing society: rows of two-storey houses with boundary walls and
    garages on a street grid, a park with trees every few blocks, street
    trees."""
    import bmesh
    import random
    rnd = random.Random(seed)
    cx, cy, R = _site_box(scene)
    cam = _cam_xy(scene)
    r0 = R + 22.0
    lot_w, lot_d, road = 13.0, 26.0, 12.0
    bw, bd = 6, 2          # lots per block side
    pitch_x = bw * lot_w + road
    pitch_y = bd * lot_d + road
    wall_cols = [(0.86, 0.83, 0.76), (0.90, 0.88, 0.84), (0.80, 0.72, 0.62),
                 (0.78, 0.76, 0.74)]
    fac = [_facade("Society %d" % i, c) for i, c in enumerate(wall_cols)]
    roof_m = _pbr("Society roof", (0.55, 0.28, 0.20), 0.85)
    flat_m = _pbr("Society flat roof", (0.45, 0.44, 0.42), 0.9)
    wall_m = _pbr("Society wall", (0.82, 0.80, 0.74), 0.9)
    lawn_m = _pbr("Society lawn", (0.14, 0.30, 0.08), 0.9)
    pad_m = _pbr("Society pavement", (0.50, 0.49, 0.47), 0.9)
    per = [[] for _ in wall_cols]
    walls, flats, lawns, pads, hip = [], [], [], [], []
    tr, cr = bmesh.new(), [bmesh.new(), bmesh.new()]
    n = 9
    nh = 0
    for bi in range(-n, n + 1):
        for bj in range(-n, n + 1):
            ox, oy = cx + bi * pitch_x, cy + bj * pitch_y
            d = math.hypot(ox - cx, oy - cy)
            if d < r0 + 40 or d > 520:
                continue
            if cam and math.hypot(ox - cam[0], oy - cam[1]) < 55.0:
                continue
            pads.append((ox, oy, z, bw * lot_w + 4, bd * lot_d + 4, 0.15))
            if rnd.random() < 0.09:        # a park
                lawns.append((ox, oy, z + 0.15, bw * lot_w - 2,
                              bd * lot_d - 2, 0.05))
                for _ in range(26):
                    _add_tree(tr, cr, ox + (rnd.random() - 0.5) * bw * lot_w
                              * 0.9, oy + (rnd.random() - 0.5) * bd * lot_d
                              * 0.9, z + 0.15, 7 + rnd.random() * 5, rnd,
                              "broad")
                continue
            for r_ in range(bd):
                for c_ in range(bw):
                    lx = ox - bw * lot_w / 2 + (c_ + 0.5) * lot_w
                    ly = oy - bd * lot_d / 2 + (r_ + 0.5) * lot_d
                    fw = lot_w * 0.72
                    fd = lot_d * 0.52
                    fl = 2 if rnd.random() < 0.8 else 1
                    h = 3.4 * fl
                    fy = ly + (lot_d * 0.5 - fd / 2 - 3.0) * (1 if r_ else
                                                              -1)
                    per[rnd.randrange(len(wall_cols))].append(
                        (lx, fy, z + 0.15, fw, fd, h))
                    if rnd.random() < 0.45:     # a hipped tiled roof
                        hip.append((lx, fy, z + 0.15 + h, fw * 1.04,
                                    fd * 1.04, 1.6))
                    else:
                        flats.append((lx, fy, z + 0.15 + h, fw * 1.02,
                                      fd * 1.02, 0.45))
                    # lot's boundary wall (four thin boxes)
                    for (wx, wy, sx, sy) in (
                            (lx, ly - lot_d / 2, lot_w, 0.2),
                            (lx, ly + lot_d / 2, lot_w, 0.2),
                            (lx - lot_w / 2, ly, 0.2, lot_d),
                            (lx + lot_w / 2, ly, 0.2, lot_d)):
                        walls.append((wx, wy, z + 0.15, sx, sy, 1.8))
                    lawns.append((lx, ly, z + 0.15, lot_w - 0.6,
                                  lot_d - 0.6, 0.04))
                    if rnd.random() < 0.5:
                        _add_tree(tr, cr, lx + (rnd.random() - 0.5) * 6, ly
                                  + (rnd.random() - 0.5) * 8, z + 0.15,
                                  5 + rnd.random() * 3, rnd, "broad")
                    nh += 1
    _join_boxes("IngeTrazo society pads", pads, pad_m)
    _join_boxes("IngeTrazo society lawns", lawns, lawn_m)
    _join_boxes("IngeTrazo society walls", walls, wall_m)
    if flats:
        _join_boxes("IngeTrazo society slabs", flats, flat_m)
    if hip:
        _join_boxes("IngeTrazo society roofs", hip, roof_m)
    for i, bx in enumerate(per):
        if bx:
            _join_boxes("IngeTrazo society houses %d" % i, bx, fac[i])
    _flush_trees(scene, "IngeTrazo society trees", tr, cr,
                 _pbr("Society trunk", (0.2, 0.13, 0.08)),
                 [_leaf_mat("Society leaf %d" % i, c) for i, c in enumerate(
                     [(0.12, 0.28, 0.08), (0.18, 0.32, 0.09)])])
    say("housing society", nh, "houses")


def sea_view(scene, z, seed=3):
    """The sea beyond the plot: a beach, a shoreline with foam, waves on
    the water to the horizon, palms on the sand. The sea lies on the far
    side of the house as the camera sees it."""
    import bmesh
    import random
    rnd = random.Random(seed)
    cx, cy, R = _site_box(scene)
    cam = _cam_xy(scene)
    if cam:
        fx, fy = cx - cam[0], cy - cam[1]
        L = math.hypot(fx, fy) or 1.0
        fx, fy = fx / L, fy / L
    else:
        fx, fy = 0.0, 1.0
    px, py = -fy, fx                     # along the shore
    shore = R + 55.0                     # shoreline distance beyond centre
    # the water: a big plane beyond the shoreline, waves by a bump
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, 0))
    w = bpy.context.active_object
    w.name = "IngeTrazo sea"
    w.scale = (4000.0, 2000.0, 1.0)
    ang = math.atan2(fy, fx) - math.pi / 2     # plane's Y along (fx, fy)
    w.rotation_euler = (0, 0, ang + math.pi / 2 * 0)
    w.rotation_euler = (0, 0, math.atan2(fy, fx))
    # plane local X -> (fx, fy): its half-length 2000 reaches the horizon
    w.location = (cx + fx * (shore + 2000.0), cy + fy * (shore + 2000.0),
                  z + 0.01)
    w.scale = (4000.0, 6000.0, 1.0)
    m = bpy.data.materials.new("IngeTrazo sea")
    m.use_nodes = True
    nt = m.node_tree
    b = _bsdf(m)
    N = nt.nodes
    L_ = nt.links.new
    b.inputs["Base Color"].default_value = (0.01, 0.16, 0.22, 1)
    b.inputs["Roughness"].default_value = 0.06
    for nm, v in (("Transmission Weight", 0.6), ("IOR", 1.333),
                  ("Specular IOR Level", 0.8)):
        try:
            b.inputs[nm].default_value = v
        except KeyError:
            pass
    try:
        tc = N.new("ShaderNodeTexCoord")
        mp = N.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (0.35, 0.8, 1.0)
        n1 = N.new("ShaderNodeTexNoise")
        n1.inputs["Scale"].default_value = 3.0
        n1.inputs["Detail"].default_value = 5.0
        n2 = N.new("ShaderNodeTexWave")
        n2.inputs["Scale"].default_value = 0.6
        n2.inputs["Distortion"].default_value = 4.0
        bm = N.new("ShaderNodeBump")
        bm.inputs["Strength"].default_value = 0.35
        bm.inputs["Distance"].default_value = 0.4
        L_(tc.outputs["Object"], mp.inputs["Vector"])
        L_(mp.outputs["Vector"], n1.inputs["Vector"])
        L_(mp.outputs["Vector"], n2.inputs["Vector"])
        mx = N.new("ShaderNodeMath")
        mx.operation = "ADD"
        L_(n1.outputs["Fac"], mx.inputs[0])
        L_(n2.outputs["Fac"], mx.inputs[1])
        L_(mx.outputs["Value"], bm.inputs["Height"])
        L_(bm.outputs["Normal"], b.inputs["Normal"])
        cr = N.new("ShaderNodeValToRGB")      # deeper / lighter water
        cr.color_ramp.elements[0].color = (0.005, 0.10, 0.16, 1)
        cr.color_ramp.elements[1].color = (0.03, 0.30, 0.34, 1)
        L_(n1.outputs["Fac"], cr.inputs["Fac"])
        L_(cr.outputs["Color"], b.inputs["Base Color"])
    except Exception:  # noqa: BLE001
        pass
    w.data.materials.append(m)
    # the beach: sand strip between the plot and the water, foam at the edge
    sand = _pbr("Sea sand", (0.72, 0.62, 0.44), 0.95)
    try:
        nz = _tex_noise(sand.node_tree, 6.0, 10.0)
        cr = sand.node_tree.nodes.new("ShaderNodeValToRGB")
        cr.color_ramp.elements[0].color = (0.62, 0.52, 0.36, 1)
        cr.color_ramp.elements[1].color = (0.80, 0.70, 0.52, 1)
        sand.node_tree.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
        sand.node_tree.links.new(cr.outputs["Color"],
                                 _bsdf(sand).inputs["Base Color"])
    except Exception:  # noqa: BLE001
        pass
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    bch = bpy.context.active_object
    bch.name = "IngeTrazo beach"
    bch.scale = (60.0, 6000.0, 1.0)
    bch.rotation_euler = (0, 0, math.atan2(fy, fx))
    bch.location = (cx + fx * (shore - 30.0), cy + fy * (shore - 30.0),
                    z + 0.004)
    bch.data.materials.append(sand)
    foam = bpy.data.materials.new("Sea foam")
    foam.use_nodes = True
    fnt = foam.node_tree
    for n_ in list(fnt.nodes):
        fnt.nodes.remove(n_)
    out = fnt.nodes.new("ShaderNodeOutputMaterial")
    mix = fnt.nodes.new("ShaderNodeMixShader")
    tr_ = fnt.nodes.new("ShaderNodeBsdfTransparent")
    df = fnt.nodes.new("ShaderNodeBsdfDiffuse")
    df.inputs["Color"].default_value = (0.95, 0.97, 0.97, 1)
    tcf = fnt.nodes.new("ShaderNodeTexCoord")
    nzf = fnt.nodes.new("ShaderNodeTexNoise")
    nzf.inputs["Scale"].default_value = 1.4
    nzf.inputs["Detail"].default_value = 8.0
    crf = fnt.nodes.new("ShaderNodeValToRGB")
    crf.color_ramp.elements[0].position = 0.5
    crf.color_ramp.elements[1].position = 0.72
    fnt.links.new(tcf.outputs["Object"], nzf.inputs["Vector"])
    fnt.links.new(nzf.outputs["Fac"], crf.inputs["Fac"])
    fnt.links.new(crf.outputs["Color"], mix.inputs["Fac"])
    fnt.links.new(tr_.outputs[0], mix.inputs[1])
    fnt.links.new(df.outputs[0], mix.inputs[2])
    fnt.links.new(mix.outputs[0], out.inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    fm = bpy.context.active_object
    fm.name = "IngeTrazo foam"
    fm.scale = (7.0, 6000.0, 1.0)
    fm.rotation_euler = (0, 0, math.atan2(fy, fx))
    fm.location = (cx + fx * (shore + 1.0), cy + fy * (shore + 1.0),
                   z + 0.016)
    fm.data.materials.append(foam)
    # palms on the sand, along the shore, and a few scrub bushes
    tr, cr = bmesh.new(), [bmesh.new()]
    n = 0
    for _ in range(70):
        along = (rnd.random() - 0.5) * 360.0
        back = shore - 5.0 - rnd.random() * 45.0
        x, y = cx + fx * back + px * along, cy + fy * back + py * along
        if math.hypot(x - cx, y - cy) < R + 10:
            continue
        if cam and math.hypot(x - cam[0], y - cam[1]) < 14.0:
            continue
        _add_tree(tr, cr, x, y, z, 7.0 + rnd.random() * 5.0, rnd, "palm")
        n += 1
    _flush_trees(scene, "IngeTrazo palms", tr, cr,
                 _pbr("Palm trunk", (0.30, 0.22, 0.13)),
                 [_leaf_mat("Palm frond", (0.10, 0.30, 0.07))])
    say("sea view", n, "palms, shore at %.0f m" % shore)


def environment(scene, job, c2i):
    env = c2i.get("env") or {}
    sky = env.get("sky", "day")
    sun_k = float(env.get("sun_k", 1.0))
    sky_k = float(env.get("sky_k", 1.0))
    # the job's sun (the Shadows panel) unless set here
    if env.get("sun_custom") or sky in ("golden", "blue") or \
            job.get("sun") is None:
        el = {"golden": 6.0, "blue": -4.0}.get(sky, float(
            env.get("sun_el", 36.0)))
        if env.get("sun_custom"):
            el = float(env.get("sun_el", el))
        sun_dir = _sun_dir(float(env.get("sun_az", 135.0)), el)
    else:
        sun_dir = tuple(job["sun"])
    sun_dir = _front_light(job, sun_dir, env)
    for o in list(scene.objects):          # the base script's sky lights
        if o.type == "LIGHT" and o.data.type == "SUN":
            bpy.data.objects.remove(o, do_unlink=True)
    lights_k = {"night": 1.0, "blue": 0.8, "golden": 0.3,
                "overcast": 0.15}.get(sky, 0.03)
    if sky.startswith("hdri"):
        path = env.get("hdri")
        builtin = bool(path and str(path).startswith("builtin:"))
        if builtin and not any(k in str(path) for k in ("night", "sunset",
                                                        "sunrise")):
            # 3.64.71: Blender's little studio HDRIs light a building flat
            # and dull: a clear day's physical sky and its sun instead
            path = None
        elif builtin:
            path = os.path.join(bpy.utils.system_resource(
                "DATAFILES", path="studiolights/world"),
                str(path).split(":", 1)[1] + ".exr")
        if path and os.path.isfile(path):
            low = os.path.basename(path).lower()
            night = "night" in low or "moon" in low
            dusk = any(k in low for k in ("sunset", "sunrise", "dusk",
                                          "dawn", "evening", "golden"))
            lights_k = 1.0 if night else (0.3 if dusk else 0.03)
            rot = float(env.get("h_rot", 0.0))
            img = bpy.data.images.load(path, check_existing=True)
            sun, peak = hdri_sun(img, rot)
            # Blender's own HDRIs are small and photographed close up: their
            # light only, a physical sky (with their sun) seen behind
            bg_mode = "hdri" if env.get("h_bg", True) and not builtin \
                else "sky"
            set_hdri(scene, img, (0.35 if night else 1.0) * sky_k, rot,
                     bg_mode, sun)
            if env.get("sun_custom"):
                add_sun(scene, _sun_dir(float(env.get("sun_az", 135.0)),
                                        float(env.get("sun_el", 40.0))),
                        4.0 * sun_k)
            elif not night and sun is not None and sun[2] > 0.02 and \
                    peak < 200.0:
                # its sun is clipped or soft: a lamp where it is, for crisp
                # shadows (an unclipped HDRI sun casts its own)
                s_ = add_sun(scene, sun, (2.0 if dusk else 3.5) * sun_k)
                if dusk:
                    s_.data.color = (1.0, 0.75, 0.5)
                say("hdri sun", "at %.0f° up, lamp added" %
                    math.degrees(math.asin(max(-1, min(1, sun[2])))))
            say("environment", "hdri", os.path.basename(path), bg_mode)
        else:
            say("environment", "hdri missing:", path, "- a physical sky")
            if sun_dir[2] < 0.35:           # (a clear day: the sun well up)
                sun_dir = _sun_dir(float(env.get("sun_az", 135.0)), 36.0)
            set_world(scene, sun_dir)
            if sun_dir[2] > 0:
                add_sun(scene, sun_dir, 3.6 * sun_k)
            lights_k = 0.03
    elif sky == "night":
        set_plain_world(scene, (0.008, 0.013, 0.03), 1.0 * sky_k, "night")
        add_moon(scene)
    elif sky == "overcast":
        set_plain_world(scene, (0.62, 0.66, 0.70), 1.0 * sky_k, "overcast")
    else:
        if sun_dir[2] > 0:
            s = add_sun(scene, sun_dir, {"golden": 2.5}.get(sky, 3.4)
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
    view_ = gnd if gnd in ("city", "forest", "society", "sea") else ""
    if view_:                       # 3.64.96: the view beyond the plot
        gnd = {"city": "asphalt", "society": "asphalt", "sea": "sand",
               "forest": "grass"}[view_]
    if gnd != "none":
        cols = {"grass": (0.07, 0.16, 0.04), "concrete": (0.45, 0.44, 0.42),
                "asphalt": (0.06, 0.06, 0.065), "plain": (0.42, 0.42, 0.40),
                "sand": (0.66, 0.56, 0.40)}
        for o in list(scene.objects):
            if o.name.startswith("IngeTrazo ground"):
                bpy.data.objects.remove(o, do_unlink=True)
        z = (job.get("ground") or {}).get("z", -0.002) - 0.01
        add_ground(scene, z, 2000.0, cols.get(gnd, cols["plain"]))
        go = bpy.context.active_object        # the plane just added
        g = go.active_material if go is not None else None
        if g is not None and gnd in ("grass", "concrete", "asphalt",
                                     "sand"):
            make(g, "grass" if gnd == "grass" else "concrete", {}, 1.0)
        try:
            if view_ == "city":
                city_view(scene, z)
            elif view_ == "forest":
                forest_view(scene, z)
            elif view_ == "society":
                society_view(scene, z)
            elif view_ == "sea":
                sea_view(scene, z)
        except Exception as e_:  # noqa: BLE001
            say("view", "skipped:", e_)
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
    vt_used = ""
    for vt_ in ("Khronos PBR Neutral", "AgX", "Filmic"):
        try:                       # 3.64.94: true-to-colour whites first
            view.view_transform = vt_
            vt_used = vt_
            break
        except TypeError:
            continue
    view.exposure = float(env.get("exposure", view.exposure))
    look = env.get("look") or "Medium High Contrast"
    if look and vt_used != "Khronos PBR Neutral":
        for name in (f"AgX - {look}", look):
            try:
                view.look = name
                break
            except TypeError:
                continue
    scene.render.film_transparent = bool(env.get("transparent", False))
    # the lamps for the hour: full at night, a glow by day (the lamps'
    # glass still shows lit)
    mode = env.get("lights_mode", "auto")
    k = {"auto": lights_k, "on": 1.0, "off": 0.0}.get(mode, lights_k)
    n = 0
    for o in scene.objects:
        if o.type == "LIGHT" and o.data.type != "SUN" and \
                not o.name.startswith("IngeTrazo moon"):
            o.data.energy *= k
            n += 1
            if k == 0.0:
                o.hide_render = True
    say("lamps", n, "at", "%.0f%%" % (k * 100))
    if env.get("bloom") and k >= 0.25:
        _bloom(scene)


def hdri_sun(img, rot_deg):
    """Where an HDRI's sun is: (direction toward it in the scene, its peak
    brightness) — the brightest spot of the upper half, read through the
    world's rotation. None when it has no clear sun."""
    try:
        import numpy as np
        w, h = img.size
        if w < 8 or h < 4:
            return None, 0.0
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        a = px.reshape(h, w, 4)[:, :, :3]
        lum = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        lum[: h // 2, :] = 0.0                     # rows go bottom → top
        idx = int(np.argmax(lum))
        peak = float(lum.flat[idx])
        med = float(np.median(lum[h // 2:, :]))
        if peak < max(3.0, med * 8.0):
            return None, peak
        y, x = divmod(idx, w)
        u, v = (x + 0.5) / w, (y + 0.5) / h
        phi = (u - 0.5) * 2.0 * math.pi
        th = (v - 0.5) * math.pi
        d = (-math.cos(phi) * math.cos(th), math.sin(phi) * math.cos(th),
             math.sin(th))
        # the mapping turns the lookup by +rot: the scene's direction is
        # the lookup turned back
        r = -math.radians(rot_deg)
        d = (d[0] * math.cos(r) - d[1] * math.sin(r),
             d[0] * math.sin(r) + d[1] * math.cos(r), d[2])
        return d, peak
    except Exception as e:  # noqa: BLE001
        say("hdri sun", "not read:", e)
        return None, 0.0


def set_hdri(scene, img, strength, rot_deg, bg_mode="hdri", sun=None):
    """A photographed sky: the HDR image all round lights the scene; seen
    behind it (bg_mode "hdri") or a physical sky with its sun ("sky")."""
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
    env.image = img
    tc = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    rot = mp.inputs.get("Rotation")
    if rot is not None:
        rot.default_value[2] = math.radians(rot_deg)
    links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    links.new(mp.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    if bg_mode == "hdri":
        links.new(bg.outputs[0], out.inputs["Surface"])
        return
    # its light only: the camera sees a physical sky
    sky_bg = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    for kind in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE",
                 "PREETHAM"):
        try:
            sky.sky_type = kind
            break
        except (TypeError, ValueError):
            continue
    d = sun if sun is not None and sun[2] > 0.02 else (0.4, -0.5, 0.75)
    ln = math.sqrt(sum(c * c for c in d)) or 1.0
    d = tuple(c / ln for c in d)
    if hasattr(sky, "sun_elevation"):
        sky.sun_elevation = math.asin(max(-1.0, min(1.0, d[2])))
    if hasattr(sky, "sun_rotation"):
        sky.sun_rotation = -math.atan2(d[0], d[1]) + math.pi / 2
    if hasattr(sky, "sun_direction"):
        sky.sun_direction = d
    if hasattr(sky, "sun_disc"):
        sky.sun_disc = False
    links.new(sky.outputs["Color"], sky_bg.inputs["Color"])
    sky_bg.inputs["Strength"].default_value = 0.35
    lp = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    links.new(bg.outputs[0], mix.inputs[1])
    links.new(sky_bg.outputs[0], mix.inputs[2])
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
def auto_exposure(scene, c2i):
    """Meter the shot like a camera: a small quick render, read in linear
    light, the exposure set so the house sits at mid-grey (centre-weighted;
    a night kept dark). The user's EV is added on top."""
    import numpy as np
    env = c2i.get("env") or {}
    if not env.get("auto_exposure", True):
        return
    sky = env.get("sky", "day")
    night = sky in ("night", "blue") or "night" in str(env.get("hdri", ""))
    r = scene.render
    keep = dict(pct=r.resolution_percentage, path=r.filepath,
                fmt=r.image_settings.file_format,
                comp=getattr(r, "use_compositing", None))
    cyc = scene.render.engine == "CYCLES"
    if cyc:
        keep["samples"] = scene.cycles.samples
    tmp = os.path.join(os.path.dirname(bpy.path.abspath(r.filepath)) or ".",
                       "c2i_meter.exr")
    try:
        r.resolution_percentage = max(5, min(100, int(36000 /
                                                      max(1, r.resolution_x))))
        r.image_settings.file_format = "OPEN_EXR"
        r.filepath = tmp
        if keep["comp"] is not None:
            r.use_compositing = False
        if cyc:
            scene.cycles.samples = 24
        say("metering", "the light")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp, check_existing=False)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        a = px.reshape(h, w, 4)[:, :, :3]
        lum = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        wgt = np.exp(-(((xx - w / 2) / (0.35 * w)) ** 2 +
                       ((yy - h / 2) / (0.35 * h)) ** 2))
        lavg = float(np.exp((wgt * np.log(lum + 1e-4)).sum() / wgt.sum()))
        key = 0.07 if night else 0.20
        ev = max(-5.0, min(4.0, math.log2(key / max(lavg, 1e-5))))
        scene.view_settings.exposure = ev + float(env.get("exposure", 0.0))
        say("exposure", "%.2f EV (metered %.3f)" % (ev, lavg))
        bpy.data.images.remove(img)
    except Exception as e:  # noqa: BLE001
        say("exposure", "kept:", e)
    finally:
        r.resolution_percentage = keep["pct"]
        r.filepath = keep["path"]
        r.image_settings.file_format = keep["fmt"]
        if keep["comp"] is not None:
            r.use_compositing = keep["comp"]
        if cyc:
            scene.cycles.samples = keep["samples"]
        try:
            os.remove(tmp)
        except OSError:
            pass


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
            c = scene.cycles
            c.use_denoising = True
            c.max_bounces = 8
            for attr, v in (("use_adaptive_sampling", True),
                            ("adaptive_threshold", 0.01),
                            ("sample_clamp_indirect", 8.0),
                            ("blur_glossy", 0.5),
                            ("caustics_reflective", False),
                            ("caustics_refractive", False),
                            ("use_light_tree", True),
                            ("denoiser", "OPENIMAGEDENOISE"),
                            ("denoising_input_passes", "RGB_ALBEDO_NORMAL"),
                            ("denoising_prefilter", "ACCURATE")):
                try:
                    setattr(c, attr, v)
                except (AttributeError, TypeError, ValueError):
                    pass
        except AttributeError:
            pass
    auto_exposure(scene, c2i)
    last = {"text": None}

    def _stats(text, *_a):
        text = str(text)
        if text != last["text"]:
            last["text"] = text
            say("stats", text.replace("\n", " "))

    if hasattr(bpy.app.handlers, "render_stats"):
        bpy.app.handlers.render_stats.append(_stats)
    if job.get("export_only"):          # 3.64.107: to open in Blender
        try:
            bpy.ops.file.pack_all()      # the textures travel in the file
        except Exception:                # noqa: BLE001
            pass
        bpy.ops.wm.save_as_mainfile(filepath=job["blend"])
        say("blend", job["blend"])
        say("done", job["blend"])
        return
    say("rendering", w, "x", h)
    bpy.ops.render.render(write_still=True)
    if job.get("blend"):
        bpy.ops.wm.save_as_mainfile(filepath=job["blend"])
        say("blend", job["blend"])
    say("done", job["output"])


c2i_main()
