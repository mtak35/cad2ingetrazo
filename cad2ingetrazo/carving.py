"""3.64.130: carved trims and crowns round the windows, doors and arches — a
design element of «Design the elevations» (``doc["look"]``: ``carving``,
``carving_on``, ``carving_where``, ``carving_col``). Drawn again at every
rebuild by stylekit.faces, on the wall faces it already knows (the openings
as the plan draws them, arched ones as their arch).

Styles: a stepped moulded frame; a frame with a carved rosette band; a frame,
band and a carved crown (cartouche with a shell medallion and leaf scrolls)
over the opening; a frame with a big carved keystone.

3.64.131 adds three full architectural orders after stone-carved window
catalogues: «classic» (moulded frame, cornice hood, triangular crest,
keystone, bracketed sill), «pilaster» (pilasters with capitals and bases, an
entablature with a cartouche frieze and dentilled cornice, apron, corbels)
and «baroque» (carved jambs, acanthus capitals, cartouche and scroll frieze,
crest over the cornice, carved apron and pendant corbels)."""
from __future__ import annotations

import math

CARVINGS = [("none", "None"),
            ("classic", "Classic - cornice hood, keystone, bracketed sill"),
            ("pilaster", "Pilastered - pilasters, cartouche frieze, corbels"),
            ("baroque", "Baroque - carved jambs, frieze, crest, apron"),
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
MAX_FACES = 90000


def _ellipse(cx, cz, rx, rz, ang=0.0):
    from shapely import affinity
    from shapely.geometry import Point
    return affinity.rotate(affinity.scale(Point(cx, cz).buffer(1.0, 3), rx, rz),
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
    if kind in ("pilaster", "baroque"):
        g0_ = 0.14 if look.get("surrounds") and look.get("style") not in (
            None, "", "none") else 0.02
        return _order_faces(fc, op, kind, cols, g0_)
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
    if kind == "classic":
        out += _classic_extras(fc, op, cols, g0, bw)
    return out


# ---------------------------------------------------------------- 3.64.131
class _Em:
    """Emits shapes on one wall face: ``box`` in (s, p, z), ``shp`` a (s, z)
    shape from p0 to p1 out of the face."""

    def __init__(self, f, face, cols):
        self.f, self.face = f, face
        self.t, self.sh, self.rl = cols
        self.out = []

    def box(self, s0, s1, p0, p1, z0, z1, col=None):
        self.out += self.f.box(s0, s1, self.face + p0, self.face + p1, z0, z1,
                               col or self.t)

    def shp(self, g, p0, p1, col=None):
        if g is not None and not g.is_empty:
            self.out += self.f.holed(g, self.face + p0, self.face + p1,
                                     col or self.t)


def _head(op):
    from .engine import structure as S_
    a, b, za, zb, k_, o = op
    arched = o.get("head") == "arch"
    rise = min(S_.head_size(o), zb - za - 0.05) if arched else 0.0
    if arched and rise <= 0.02:
        arched = False
    return arched, (zb - rise if arched else zb), (o.get("arch") or "semi")


def _curl(cx, cz, r):
    """A volute: a ring with an eye."""
    from shapely.geometry import Point
    return Point(cx, cz).buffer(r, 3).difference(
        Point(cx, cz).buffer(r * 0.5, 3)).union(
        Point(cx, cz).buffer(r * 0.22, 3))


def _acanthus(em, cx, cz, sc, p0, up=True):
    """A fan of five leaves with a bud, rising (or hanging) from a point."""
    d = 1 if up else -1
    ls = []
    for ang in (-64, -32, 0, 32, 64):
        r = 0.17 * sc * (1.0 - 0.2 * abs(ang) / 64.0)
        t = math.radians(90 - ang)
        ls.append(_ellipse(cx + 0.55 * r * math.cos(t),
                           cz + d * 0.55 * r * math.sin(t), 0.55 * r,
                           0.05 * sc, d * (90 - ang)))
    from shapely.ops import unary_union
    em.shp(unary_union(ls), p0, p0 + 0.035)
    em.shp(_ellipse(cx, cz + d * 0.04 * sc, 0.035 * sc, 0.05 * sc),
           p0 + 0.035, p0 + 0.06, em.rl)


def _wing(em, cx, cz, sc, sg, p0):
    """A leaf scroll reaching out sideways from (cx, cz)."""
    em.shp(_curl(cx + sg * 0.27 * sc, cz + 0.02 * sc, 0.075 * sc), p0,
           p0 + 0.04)
    em.shp(_ellipse(cx + sg * 0.14 * sc, cz - 0.01 * sc, 0.15 * sc,
                    0.028 * sc), p0, p0 + 0.035)
    em.shp(_ellipse(cx + sg * 0.17 * sc, cz + 0.07 * sc, 0.10 * sc,
                    0.03 * sc, sg * 32), p0, p0 + 0.035)
    em.shp(_ellipse(cx + sg * 0.15 * sc, cz - 0.07 * sc, 0.10 * sc,
                    0.03 * sc, -sg * 30), p0, p0 + 0.035)


def _cartouche(em, cx, cz, sc, p0):
    """An oval shield with a rosette, leaf scrolls either side and a leaf
    fan over it."""
    em.shp(_ellipse(cx, cz, 0.16 * sc, 0.12 * sc), p0, p0 + 0.05)
    em.shp(_ellipse(cx, cz, 0.105 * sc, 0.075 * sc), p0 + 0.05, p0 + 0.075,
           em.sh)
    em.shp(_rosette(cx, cz, 0.055 * sc), p0 + 0.075, p0 + 0.095, em.rl)
    for sg in (-1, 1):
        _wing(em, cx + sg * 0.12 * sc, cz, sc * 0.8, sg, p0)
    _acanthus(em, cx, cz + 0.1 * sc, 0.7 * sc, p0)


def _bracket(em, s, zt, h, w, d):
    """A corbel hanging under ``zt``: tapering block, volute and a leaf."""
    from shapely.geometry import Polygon
    em.shp(Polygon([(s - w / 2, zt), (s + w / 2, zt), (s + w * 0.2, zt - h),
                    (s - w * 0.2, zt - h)]), 0.0, d)
    em.shp(Polygon([(s - w * 0.36, zt - 0.03), (s + w * 0.36, zt - 0.03),
                    (s + w * 0.12, zt - h * 0.92),
                    (s - w * 0.12, zt - h * 0.92)]), d, d + 0.03, em.sh)
    em.shp(_curl(s, zt - h * 0.8, w * 0.17), d + 0.03, d + 0.06)
    _acanthus(em, s, zt - 0.05, h * 1.5, d + 0.03, up=False)


def _cornice(em, s0, s1, z, proj, h, dentils=False):
    """A stepped projecting cornice from z up by h."""
    em.box(s0, s1, 0, 0.08, z, z + 0.4 * h)
    if dentils:
        n = min(max(int((s1 - s0) / 0.12), 4), 26)
        dw = (s1 - s0) / n
        for i in range(n):
            if i % 2 == 0:
                em.box(s0 + i * dw, s0 + (i + 1) * dw, 0.04, 0.15,
                       z + 0.4 * h - 0.05, z + 0.4 * h)
    em.box(s0 - 0.04, s1 + 0.04, 0, proj * 0.6, z + 0.4 * h, z + 0.62 * h)
    em.box(s0 - 0.08, s1 + 0.08, 0, proj, z + 0.62 * h, z + 0.84 * h)
    em.box(s0 - 0.10, s1 + 0.10, 0, proj * 1.05, z + 0.84 * h, z + h)


def _pilaster(em, s_in, sg, pw, z0, z1, rich):
    s0, s1 = sorted((s_in, s_in + sg * pw))
    sm = (s0 + s1) / 2
    if z1 - z0 < 0.55:
        em.box(s0, s1, 0, 0.08, z0, z1)
        return
    bh, ch = 0.16 + 0.2 * pw, 0.20 + 0.3 * pw
    em.box(s0 - 0.04, s1 + 0.04, 0, 0.13, z0, z0 + bh)
    em.box(s0 - 0.02, s1 + 0.02, 0, 0.115, z0 + bh, z0 + bh + 0.04)
    zs0, zs1 = z0 + bh + 0.04, z1 - ch - 0.04
    em.box(s0, s1, 0, 0.08, zs0, zs1)
    em.box(s0 + 0.14 * pw, s1 - 0.14 * pw, 0.08, 0.10, zs0 + 0.08, zs1 - 0.08,
           em.sh if rich else None)
    if rich:                                   # carved drops down the shaft
        n = min(max(int((zs1 - zs0 - 0.2) / 0.2), 2), 9)
        for i in range(n):
            zc = zs0 + 0.1 + (i + 0.5) * (zs1 - zs0 - 0.2) / n
            if i % 3 == 1:
                em.shp(_rosette(sm, zc, pw * 0.2), 0.10, 0.13, em.rl)
            else:
                em.shp(_ellipse(sm, zc, pw * 0.09, pw * 0.2), 0.10, 0.13,
                       em.rl)
    em.box(s0 - 0.02, s1 + 0.02, 0, 0.115, z1 - ch - 0.04, z1 - ch)
    em.box(s0 - 0.05, s1 + 0.05, 0, 0.16, z1 - ch, z1 - 0.05)
    em.box(s0 - 0.07, s1 + 0.07, 0, 0.19, z1 - 0.05, z1)
    _acanthus(em, sm, z1 - ch * 0.95, max(0.8, pw * 2.4), 0.16)
    if rich:
        for x in (s0 + 0.03, s1 - 0.03):
            em.shp(_curl(x, z1 - 0.1, 0.055), 0.16, 0.2)


def _order_faces(fc, op, kind, cols, g0):
    """«pilaster» and «baroque»: pilasters (carved jambs), an entablature or
    an archivolt over the opening, a sill with apron and corbels."""
    from shapely.geometry import Polygon, LineString, box as sbox
    a, b, za, zb, k_, o = op
    arched, zsp, sty = _head(op)
    em = _Em(fc["f"], fc["face"], cols)
    w = b - a
    door = k_ == "door"
    smid = (a + b) / 2
    gnd = fc.get("z0") or 0.0
    rich = kind == "baroque"
    pw = min(max(0.14 + 0.07 * w, 0.2), 0.40) * (1.12 if rich else 1.0)
    im = 0.06
    sl, sr = a - g0 - im, b + g0 + im
    zi = zb + g0
    zs = za - g0 - 0.02
    cs = min(max(w / 1.1, 0.75), 1.5)
    ah = 0.0 if door else 0.30 + 0.04 * cs
    z_pb = za if door else zs - 0.07 - ah
    # the opening's inner moulding
    for s0_, s1_ in ((sl, a - g0), (b + g0, sr)):
        em.box(s0_, s1_, 0, 0.05, za if door else zs,
               zsp if arched else zi + im)
    # -- head
    if arched:
        aw = pw + im
        gi, go = g0, g0 + aw
        gm = g0 + aw / 2
        sh_ = lambda g: _grown(a, b, za, zb, zsp, sty, g, za - 1.0)
        cut = sbox(a - 6, zsp, b + 6, zb + 6)
        em.shp(sh_(g0 + im).difference(sh_(g0)).intersection(cut), 0, 0.05)
        em.shp(sh_(go).difference(sh_(g0 + im)).intersection(cut), 0, 0.08)
        em.shp(sh_(go + 0.05).difference(sh_(go)).intersection(cut), 0, 0.11)
        if rich:
            line = LineString(list(sh_(gm).exterior.coords))
            line = line.intersection(sbox(a - 6, zsp + 0.05, b + 6, zb + 6))
            parts = getattr(line, "geoms", [line])
            ln = sum(p.length for p in parts if p.geom_type == "LineString")
            n = min(max(int(ln / 0.24), 3), 26)
            k = 0
            for p in parts:
                if p.geom_type != "LineString" or p.length < 0.2:
                    continue
                m = max(int(p.length / (ln / n)), 1)
                for i in range(m):
                    q = p.interpolate((i + 0.5) * p.length / m)
                    if abs(q.x - smid) < 0.2:
                        continue
                    em.shp(_rosette(q.x, q.y, pw * 0.2), 0.08, 0.115, em.rl)
                    k += 1
        kt = zb + g0 + aw + 0.18
        kw = 0.09 + 0.04 * w
        em.shp(Polygon([(smid - kw * 0.9, zb + g0 + 0.02),
                        (smid + kw * 0.9, zb + g0 + 0.02),
                        (smid + kw * 1.3, kt), (smid - kw * 1.3, kt)]), 0,
               0.17)
        em.shp(_rosette(smid, kt - 0.17, kw * 0.75), 0.17, 0.2, em.rl)
        em.box(smid - kw * 1.55, smid + kw * 1.55, 0, 0.19, kt, kt + 0.06)
        z_top = kt + 0.06
        if rich:
            _wing(em, smid, z_top + 0.05, cs * 1.3, 1, 0.0)
            _wing(em, smid, z_top + 0.05, cs * 1.3, -1, 0.0)
            _cartouche(em, smid, z_top + 0.17 * cs, cs * 0.9, 0.0)
        else:
            _acanthus(em, smid, z_top, 1.0 * cs, 0.0)
        z_pt = zsp
    else:
        zh = zi + im
        em.box(sl, sr, 0, 0.05, zi, zh)
        fh = (0.30 if rich else 0.22) + 0.05 * min(w, 2.0)
        z_pt = zh + 0.10 + fh
        em.box(sl - pw, sr + pw, 0, 0.07, zh, zh + 0.10)
        em.box(sl - pw, sr + pw, 0, 0.05, zh + 0.10, z_pt)
        zfm = zh + 0.10 + fh / 2
        fs = min(fh / 0.30, 1.4)
        _cartouche(em, smid, zfm, fs, 0.05)
        half = (sr - sl) / 2 + pw - 0.25
        x = 0.30 * fs + 0.4 * fs + 0.1
        k = 0
        while x < half and k < 5:
            for sg in (-1, 1):
                em.shp(_rosette(smid + sg * x, zfm, fh * 0.2), 0.05, 0.085,
                       em.rl)
            x += 0.36
            k += 1
        _cornice(em, sl - pw, sr + pw, z_pt, 0.24, 0.22, dentils=True)
        zc0 = z_pt + 0.22
        em.box(smid - 0.3 * cs, smid + 0.3 * cs, 0, 0.14, zc0, zc0 + 0.07)
        if rich:
            _wing(em, smid, zc0 + 0.13, cs * 1.5, 1, 0.0)
            _wing(em, smid, zc0 + 0.13, cs * 1.5, -1, 0.0)
            _cartouche(em, smid, zc0 + 0.07 + 0.14 * cs, cs * 0.95, 0.0)
        else:
            _acanthus(em, smid, zc0 + 0.07, 1.0 * cs, 0.0)
    # -- the pilasters
    _pilaster(em, sl, -1, pw, z_pb, z_pt, rich)
    _pilaster(em, sr, 1, pw, z_pb, z_pt, rich)
    # -- sill, apron, corbels
    if not door:
        em.box(sl - pw - 0.08, sr + pw + 0.08, 0, 0.20, zs - 0.07, zs)
        em.box(sl - pw - 0.04, sr + pw + 0.04, 0, 0.12, zs - 0.10, zs - 0.07)
        em.box(sl - pw, sr + pw, 0, 0.06, z_pb, zs - 0.10)
        em.box(sl - pw + 0.14, sr + pw - 0.14, 0.06, 0.085, z_pb + 0.06,
               zs - 0.16, em.sh)
        zam = (z_pb + zs - 0.10) / 2
        if rich and (sr - sl) > 0.9:
            _cartouche(em, smid, zam, min(ah / 0.30, 1.1), 0.085)
        elif (sr - sl) > 0.9:
            em.shp(_rosette(smid, zam, ah * 0.28), 0.085, 0.115, em.rl)
        if z_pb - 0.34 > gnd + 0.05:
            for sx in (sl - pw / 2, sr + pw / 2):
                _bracket(em, sx, z_pb, 0.32, pw * 0.95, 0.16)
    return em.out


def _classic_extras(fc, op, cols, g0, bw):
    """«classic»: on top of the stepped frame, a cornice hood with a
    triangular crest (flat heads) or imposts, a keystone and a crest (arched
    heads), and a sill with brackets."""
    from shapely.geometry import Polygon
    a, b, za, zb, k_, o = op
    arched, zsp, sty = _head(op)
    em = _Em(fc["f"], fc["face"], cols)
    w = b - a
    door = k_ == "door"
    smid = (a + b) / 2
    gnd = fc.get("z0") or 0.0
    sl, sr = a - g0 - bw, b + g0 + bw
    top = zb + g0 + bw + 0.05
    cs = min(max(w / 1.1, 0.75), 1.5)
    if arched:
        for sx0, sx1 in ((sl - 0.07, a - g0 + 0.03), (b + g0 - 0.03,
                                                      sr + 0.07)):
            em.box(sx0, sx1, 0, 0.13, zsp - 0.06, zsp + 0.06)
        kw = 0.08 + 0.035 * w
        kt = top + 0.16
        em.shp(Polygon([(smid - kw * 0.85, zb + g0), (smid + kw * 0.85,
                                                       zb + g0),
                        (smid + kw * 1.25, kt), (smid - kw * 1.25, kt)]), 0,
               0.15)
        em.shp(Polygon([(smid - kw * 1.5, kt), (smid + kw * 1.5, kt),
                        (smid, kt + 0.14 + 0.05 * cs)]), 0, 0.13)
    else:
        _cornice(em, sl - 0.04, sr + 0.04, top, 0.2, 0.16)
        kt = top + 0.16
        kw = 0.10 + 0.04 * w
        em.shp(Polygon([(smid - kw, kt), (smid + kw, kt),
                        (smid, kt + 0.16 + 0.06 * cs)]), 0, 0.12)
        em.box(smid - kw * 0.55, smid + kw * 0.55, 0.0, 0.14,
               top - 0.12, top)
    if not door:
        zs = za - g0 - 0.02
        em.box(sl - 0.10, sr + 0.10, 0, 0.20, zs - 0.07, zs)
        if w >= 0.9 and zs - 0.07 - 0.28 > gnd + 0.05:
            n = 2 if w < 1.6 else 3
            for i in range(n):
                sx = sl + 0.06 + (sr - sl - 0.12) * i / (n - 1)
                _bracket(em, sx, zs - 0.07, 0.26, 0.14, 0.16)
    return em.out


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
    if kind in ("classic", "pilaster", "baroque"):
        # stone carving reads in the stone's own tone, a shade deeper
        cols = (base, tuple(max(0.0, min(1.0, v * 0.93)) for v in base[:3])
                + (1.0,), tuple(max(0.0, min(1.0, v * 0.84))
                                for v in base[:3]) + (1.0,))
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
