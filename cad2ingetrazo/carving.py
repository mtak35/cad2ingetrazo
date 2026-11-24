"""3.64.130: carved trims and crowns round the windows, doors and arches — a
design element of «Design the elevations» (``doc["look"]``: ``carving``,
``carving_on``, ``carving_where``, ``carving_col``). Drawn again at every
rebuild by stylekit.faces, on the wall faces it already knows (the openings
as the plan draws them, arched ones as their arch).

Styles: a stepped moulded frame; a frame with a carved rosette band; a frame,
band and a carved crown (cartouche with a shell medallion and leaf scrolls)
over the opening; a frame with a big carved keystone."""
from __future__ import annotations

import math

CARVINGS = [("none", "None"),
            ("frame", "Moulded frame (stepped architrave)"),
            ("relief", "Frame with a carved rosette band"),
            ("crown", "Frame, rosette band and a carved crown"),
            ("keystone", "Frame with a carved keystone")]
CARVE_ON = [("all", "Windows, doors and arches"),
            ("windows", "Windows only"),
            ("doors", "Doors only"),
            ("arches", "Arched openings only")]
CARVE_WHERE = [("front", "Front elevation only"),
               ("all", "Every outside wall")]
CARVE_COL = [("trim", "The trim colour"), ("stone", "The stone colour"),
             ("accent", "The design's accent colour")]
MAX_FACES = 60000


def _ellipse(cx, cz, rx, rz, ang=0.0):
    from shapely import affinity
    from shapely.geometry import Point
    return affinity.rotate(affinity.scale(Point(cx, cz).buffer(1.0, 4), rx, rz),
                           ang, origin=(cx, cz))


def _rosette(cx, cz, r):
    """A little rosette: four crossed petals and a centre."""
    from shapely.ops import unary_union
    ps = [_ellipse(cx, cz, r, r * 0.38, a) for a in (0, 45, 90, 135)]
    return unary_union(ps)


def _grown(a, b, za, zb, zsp, style, g, bottom):
    """The opening grown by ``g`` as a closed shape in (s, z): square or
    arched at the top (its own arch, widened), the bottom at ``bottom``."""
    from shapely.geometry import Polygon
    from .engine import structure as S_
    if zsp < zb - 0.02:
        arc = S_.arch_pts(a - g, b + g, zsp, zb + g, 16, style)
        top = list(reversed(arc))                 # left spring → right spring
        pts = [(a - g, bottom)] + top + [(b + g, bottom)]
    else:
        pts = [(a - g, bottom), (a - g, zb + g), (b + g, zb + g),
               (b + g, bottom)]
    return Polygon(pts).buffer(0)


def _opening_faces(fc, op, kind, look, cols, budget):
    from shapely.geometry import LineString, box
    from .engine import structure as S_
    a, b, za, zb, k_, o = op
    f, face = fc["f"], fc["face"]
    trim, shade, relief = cols
    w = b - a
    arched = o.get("head") == "arch"
    rise = min(S_.head_size(o), zb - za - 0.05) if arched else 0.0
    if arched and rise <= 0.02:
        arched = False
    zsp = zb - rise if arched else zb
    sty = o.get("arch") or "semi"
    door = k_ == "door"
    g0 = 0.14 if look.get("surrounds") and look.get("style") not in (
        None, "", "none") else 0.02          # clear of the plain surround
    bw = min(max(0.10 + 0.045 * w, 0.14), 0.26)
    bottom = (za - 1.0) if door else (za - g0 - 0.02 - bw - 0.12)
    out = []
    s_mid = (a + b) / 2

    def ring(g_in, g_out, p0, p1, col):
        shp = _grown(a, b, za, zb, zsp, sty, g_out, bottom).difference(
            _grown(a, b, za, zb, zsp, sty, g_in, bottom))
        if door:                              # open at the floor
            shp = shp.intersection(box(a - 5, za, b + 5, zb + 5))
        elif shp.is_empty:
            return []
        return f.holed(shp, face + p0, face + p1, col)
    # the stepped frame: a thin inner moulding, then the wide band
    out += ring(g0, g0 + bw * 0.38, 0.0, 0.09, trim)
    out += ring(g0 + bw * 0.38, g0 + bw, 0.0, 0.05, trim)
    out += ring(g0 + bw, g0 + bw + 0.05, 0.0, 0.085, trim)
    top_z = (zb + g0 + bw + 0.05) if not arched else \
        (zb + g0 + bw + 0.05)
    if kind in ("relief", "crown"):
        mid = _grown(a, b, za, zb, zsp, sty, g0 + bw * 0.69, bottom)
        line = LineString(list(mid.exterior.coords))
        pitch = max(0.26, bw * 1.6)
        n = max(int(line.length / pitch), 4)
        r = bw * 0.27
        placed = 0
        for i in range(n):
            pt = line.interpolate((i + 0.5) * line.length / n)
            x, z = pt.x, pt.y
            if z < za + 0.12 and not door:
                continue                      # the sill line, left plain
            if door and z < za + 0.2:
                continue
            if placed >= 48:
                break
            out += f.holed(_rosette(x, z, r), face + 0.05, face + 0.085,
                           relief)
            placed += 1
        if not arched and w > 0.5:            # corner blocks at the head
            for sx in (a - g0 - bw * 0.5, b + g0 + bw * 0.5):
                out += f.box(sx - bw * 0.62, sx + bw * 0.62, face,
                             face + 0.11, zb + g0 - bw * 0.12,
                             zb + g0 + bw * 1.12, trim)
                out += f.holed(_rosette(sx, zb + g0 + bw * 0.5, bw * 0.42),
                               face + 0.11, face + 0.14, relief)
    if kind == "keystone":
        kz0 = zb + g0 - 0.02
        kz1 = zb + g0 + bw + 0.30 + 0.05 * w
        kw = 0.12 + 0.05 * w
        ks = [(s_mid - kw * 0.8, kz0), (s_mid + kw * 0.8, kz0),
              (s_mid + kw * 1.15, kz1), (s_mid - kw * 1.15, kz1)]
        from shapely.geometry import Polygon
        out += f.holed(Polygon(ks), face, face + 0.16, trim)
        out += f.holed(_rosette(s_mid, (kz0 + kz1) / 2, kw * 0.7),
                       face + 0.16, face + 0.19, relief)
        out += f.box(s_mid - kw * 1.35, s_mid + kw * 1.35, face, face + 0.17,
                     kz1, kz1 + 0.05, trim)
    if kind == "crown":
        sc = min(max(w / 1.2, 0.8), 1.7)
        z0 = top_z - 0.02
        base_w = 0.42 * sc
        out += f.box(s_mid - base_w, s_mid + base_w, face, face + 0.12, z0,
                     z0 + 0.07 * sc, trim)
        from shapely.geometry import Polygon
        out += f.holed(Polygon([(s_mid - base_w * 0.8, z0 + 0.07 * sc),
                                (s_mid + base_w * 0.8, z0 + 0.07 * sc),
                                (s_mid + base_w * 0.35, z0 + 0.30 * sc),
                                (s_mid - base_w * 0.35, z0 + 0.30 * sc)]),
                       face, face + 0.13, trim)
        # the shell medallion on it
        cz = z0 + 0.31 * sc
        out += f.holed(_ellipse(s_mid, cz, 0.2 * sc, 0.2 * sc),
                       face, face + 0.15, trim)
        shell = None
        from shapely.ops import unary_union
        fan = [_ellipse(s_mid + 0.1 * sc * math.cos(t),
                        cz + 0.1 * sc * math.sin(t), 0.075 * sc, 0.03 * sc,
                        math.degrees(t))
               for t in (math.radians(v) for v in range(20, 170, 28))]
        shell = unary_union(fan)
        out += f.holed(shell, face + 0.15, face + 0.185, relief)
        out += f.holed(_ellipse(s_mid, cz, 0.07 * sc, 0.07 * sc),
                       face + 0.15, face + 0.19, relief)
        # leaf scrolls either side, a finial over it
        for sg in (-1, 1):
            for j, (dx, dz, rx, ang) in enumerate(((0.36, 0.02, 0.22, 10),
                                                   (0.62, 0.10, 0.17, 28),
                                                   (0.82, 0.02, 0.12, -10))):
                out += f.holed(_ellipse(s_mid + sg * dx * sc,
                                        z0 + (0.14 + dz) * sc, rx * sc,
                                        0.045 * sc, sg * ang),
                               face, face + 0.10, trim)
        out += f.box(s_mid - 0.045 * sc, s_mid + 0.045 * sc, face, face + 0.10,
                     cz + 0.2 * sc, cz + 0.36 * sc, trim)
        out += f.holed(_ellipse(s_mid, cz + 0.42 * sc, 0.06 * sc, 0.06 * sc),
                       face, face + 0.10, relief)
    return out


def carving_faces(doc, fcs, look, trim, stone, accent) -> list:
    kind = look.get("carving") or "none"
    if kind in ("none", ""):
        return []
    on = look.get("carving_on") or "all"
    where = look.get("carving_where") or "front"
    ck = look.get("carving_col") or "trim"
    base = {"trim": trim, "stone": stone, "accent": accent}.get(ck, trim)
    cols = (base, tuple(max(0.0, min(1.0, v * 0.9)) for v in base[:3]) + (1.0,),
            accent if ck != "accent" else tuple(
                max(0.0, min(1.0, v * 0.85)) for v in base[:3]) + (1.0,))
    out, budget = [], MAX_FACES
    for fc in fcs:
        if where == "front" and not fc.get("front"):
            continue
        for op in fc["ops"]:
            a, b, za, zb, k_, o = op
            if k_ not in ("window", "door") or o.get("vent") or \
                    o.get("arcade"):
                continue
            if b - a < (0.5 if k_ == "window" else 0.7):
                continue
            arched = o.get("head") == "arch"
            if on == "windows" and k_ != "window":
                continue
            if on == "doors" and k_ != "door":
                continue
            if on == "arches" and not arched:
                continue
            if budget <= 0:
                return out
            fs = _opening_faces(fc, op, kind, look, cols, budget)
            budget -= len(fs)
            out += fs
    return out
