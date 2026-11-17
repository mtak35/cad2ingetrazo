"""3.64.55: the elements of the world's major elevation styles, made from
the model at every rebuild (they follow the plans), each behind its own
switch in ``doc["look"]``:

- Classical / Neoclassical: a pediment on an entablature with pilasters
  over the main door; small pediments over the front's upper windows
  (``pediment``);
- Art Deco: vertical fins up the front, stepped at the top
  (``deco_fins``); three speed bands under the roof (``deco_bands``); a
  stepped crown over the entrance (``deco_crown``);
- Brutalist: deep concrete boxes round the windows (``window_boxes``);
  its heavy fascia: modern.py with ``fascia_d`` / ``fascia_h``;
- Tudor: half-timbering — rails, studs, braces — on the upper floors
  (``half_timber``); a brick ground floor (``gf_clad``);
- Cape Cod: shutters by every window (``shutters``); clapboard siding
  (``siding``);
- Italianate: paired brackets under the wide eaves (``eave_brackets``).

Colours: ``trim`` (mouldings, concrete), ``accent`` (timber, shutters,
Deco metal), ``stone`` (brick), ``wall``.
"""
from __future__ import annotations

import math

from .modern import _c4, _Frame, _prism


def _shade(c, k):
    return _c4([min(1.0, max(0.0, float(v) * k)) for v in list(c)[:3]])


# ---- the model's outside wall faces -------------------------------------------------
def faces_of(doc) -> list:
    """Every outside wall face: [{"w", "f" (frame: s along, a out from the
    wall's centre), "face" (t/2), "L", "i" (level index), "z0", "z1",
    "ops": [(s0, s1, z0, z1, kind, o)], "front": bool}]."""
    from shapely.geometry import Point

    from . import lookstyle as LS
    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    from .engine import walls as W
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    try:
        info = S.levels_info(arch, M.elevations)
    except Exception:  # noqa: BLE001
        info = {}
    idx = {lv["id"]: k for k, lv in enumerate(levels)}
    outer = LS._outer_walls(arch)
    try:
        fr, _w, _o = LS.front_side(doc, outer)
    except Exception:  # noqa: BLE001
        fr = None
    polys = {}
    ops_by = {}
    for o in arch["openings"]:
        ops_by.setdefault(o["wall"], []).append(o)
    out = []
    for w in arch["walls"]:
        if w["id"] not in outer or w.get("rail") or "a" not in w or \
                str(w.get("name", "")).lower().startswith(
                    ("corner", "roof parapet", "roof edge")):
            continue
        i = idx.get(w["level"])
        if i is None:
            continue
        seg = W.centre(w)
        if seg.kind != "line" or seg.L < 0.4:
            continue
        if i not in polys:
            polys[i] = LS._outline(arch, w["level"])[0]
        poly = polys[i]
        if poly is None:
            continue
        t = float(w["t"])
        u = seg.u
        nl = (-u[1], u[0])
        mid = seg.at(0.5)
        probe = (mid[0] + nl[0] * (t / 2 + 0.25), mid[1] + nl[1] *
                 (t / 2 + 0.25))
        n = (-nl[0], -nl[1]) if poly.buffer(-0.05).contains(Point(probe)) \
            else nl
        z0 = el[i]
        li = info.get(w["level"]) or {}
        z1 = float(li.get("under", z0 + float(levels[i]["height"])))
        ops = []
        for o in ops_by.get(w["id"], []):
            zs = z0 + float(o.get("sill", 0.0) or 0.0)
            s_ = float(o["pos"])
            hw = float(o["w"]) / 2
            ops.append((s_ - hw, s_ + hw, zs, zs + float(o["h"]),
                        o["kind"], o))
        out.append({"w": w, "f": _Frame(seg.p0, u, n), "face": t / 2,
                    "L": seg.L, "i": i, "z0": z0, "z1": z1, "ops": ops,
                    "front": fr is not None and
                    n[0] * fr[0] + n[1] * fr[1] > 0.85})
    return out


def _op_holes(fc, grow=0.0):
    from shapely.geometry import box
    from shapely.ops import unary_union
    hs = [box(a - grow, za - grow, b + grow, zb + grow)
          for a, b, za, zb, _k, _o in fc["ops"]]
    return unary_union(hs) if hs else None


def _cut(shape, fc, grow=0.0):
    h = _op_holes(fc, grow)
    return shape.difference(h) if h is not None else shape


def _ctx(doc):
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    return arch, levels, el, g


# ---- Tudor ----------------------------------------------------------------------
def _half_timber(doc, fcs, timber) -> list:
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    arch, levels, el, g = _ctx(doc)
    upper = [fc for fc in fcs if fc["i"] != g]
    if not upper:                    # one storey: its upper half
        upper = [dict(fc, z0=fc["z0"] + (fc["z1"] - fc["z0"]) * 0.45)
                 for fc in fcs]
    out = []
    M_ = 0.16
    for fc in upper:
        L, z0, z1 = fc["L"], fc["z0"], fc["z1"]
        if z1 - z0 < 1.0:
            continue
        parts = [box(0, z0, L, z0 + M_ + 0.02), box(0, z1 - M_, L, z1)]
        # the openings' frames
        for a, b, za, zb, _k, _o in fc["ops"]:
            parts.append(box(a - M_, max(z0, za - M_), b + M_,
                             min(z1, zb + M_)))
        # the studs
        n = max(2, int(L / 0.6) + 1)
        xs = [0.05 + (L - 0.10 - M_) * k / (n - 1) for k in range(n)]
        for x in xs:
            parts.append(box(x, z0, x + M_, z1))
        # a brace in every third blank bay, leaning alternately
        holes = _op_holes(fc, 0.2)
        for k in range(0, len(xs) - 2, 3):
            xa, xb = xs[k] + M_, xs[k + 2]
            bay = box(xa, z0 + M_, xb, z1 - M_)
            if holes is not None and bay.intersects(holes):
                continue
            pts = [(xa, z0 + M_), (xb, z1 - M_)] if (k // 3) % 2 == 0 \
                else [(xa, z1 - M_), (xb, z0 + M_)]
            parts.append(LineString(pts).buffer(0.07, cap_style=2)
                         .intersection(bay))
        shape = _cut(unary_union(parts).intersection(box(0, z0, L, z1)), fc)
        out += fc["f"].holed(shape, fc["face"] - 0.004, fc["face"] + 0.03,
                             timber)
    return out


def _gf_clad(doc, fcs, brick) -> list:
    from shapely.geometry import box
    arch, levels, el, g = _ctx(doc)
    out = []
    mort = _shade(brick, 1.35)
    for fc in fcs:
        if fc["i"] != g:
            continue
        L, z0, z1 = fc["L"], fc["z0"] - 0.3, fc["z1"]
        shape = _cut(box(-0.0, z0, L, z1), fc)
        out += fc["f"].holed(shape, fc["face"] - 0.004, fc["face"] + 0.025,
                             brick)
        # brick courses: a fine mortar line every 0.3 m
        z = z0 + 0.3
        lines = []
        while z < z1 - 0.05:
            lines.append(box(0.0, z, L, z + 0.012))
            z += 0.3
        if lines:
            from shapely.ops import unary_union
            out += fc["f"].holed(_cut(unary_union(lines), fc),
                                 fc["face"] + 0.025, fc["face"] + 0.029,
                                 mort)
    return out


# ---- Cape Cod ---------------------------------------------------------------------
def _shutters(doc, fcs, col) -> list:
    out = []
    dark = _shade(col, 0.75)
    for fc in fcs:
        f, L, face = fc["f"], fc["L"], fc["face"]
        for a, b, za, zb, kind, o in fc["ops"]:
            if kind != "window" or b - a < 0.5 or zb - za < 0.7 or \
                    o.get("arcade"):
                continue
            sw = min(0.7, (b - a) / 2)
            for s0, s1 in ((a - 0.04 - sw, a - 0.04), (b + 0.04,
                                                       b + 0.04 + sw)):
                if s0 < 0.02 or s1 > L - 0.02 or any(
                        s1 > a2 and s0 < b2 for a2, b2, *_r in fc["ops"]):
                    continue
                out += f.box(s0, s1, face, face + 0.04, za, zb, col)
                # its louvres: three rails and a stile frame
                for zz in (za + 0.06, (za + zb) / 2 - 0.03, zb - 0.12):
                    out += f.box(s0 + 0.04, s1 - 0.04, face + 0.04,
                                 face + 0.055, zz, zz + 0.06, dark)
    return out


def _siding(doc, fcs, wall, skip_ground=False) -> list:
    from shapely.geometry import box
    from shapely.ops import unary_union
    arch, levels, el, g = _ctx(doc)
    out = []
    col = _shade(wall, 0.86)
    for fc in fcs:
        if skip_ground and fc["i"] == g:
            continue
        L = fc["L"]
        z = fc["z0"] + 0.22
        lines = []
        while z < fc["z1"] - 0.05:
            lines.append(box(0.0, z, L, z + 0.025))
            z += 0.22
        if not lines:
            continue
        shape = _cut(unary_union(lines), fc, 0.06)
        out += fc["f"].holed(shape, fc["face"] - 0.002, fc["face"] + 0.018,
                             col)
    return out


# ---- Brutalist --------------------------------------------------------------------
def _window_boxes(doc, fcs, concrete) -> list:
    from shapely.geometry import box
    out = []
    for fc in fcs:
        for a, b, za, zb, kind, o in fc["ops"]:
            if kind != "window" or b - a < 0.45:
                continue
            ring = box(a - 0.15, za - 0.15, b + 0.15, zb + 0.15).difference(
                box(a, za, b, zb))
            out += fc["f"].holed(ring, fc["face"] - 0.004,
                                 fc["face"] + 0.45, concrete)
    return out


# ---- Classical ---------------------------------------------------------------------
def _main_door(doc, fcs):
    from . import lookstyle as LS
    try:
        _fr, w, o = LS.front_side(doc, LS._outer_walls(doc["arch"]))
    except Exception:  # noqa: BLE001
        return None, None
    if w is None:
        return None, None
    for fc in fcs:
        if fc["w"]["id"] == w["id"]:
            for op in fc["ops"]:
                if op[5] is o:
                    return fc, op
    return None, None


def _pediments(doc, fcs, trim) -> list:
    out = []
    fc, op = _main_door(doc, fcs)
    if fc is not None:
        f, face = fc["f"], fc["face"]
        a, b, za, zb = op[:4]
        s = (a + b) / 2
        W_ = (b - a) + 1.4
        room = fc["z1"] - zb - 0.05
        if room > 0.5:
            e0, e1 = zb + 0.12, zb + min(0.40, room * 0.35)
            h = min(W_ * 0.22, room - (e1 - zb) - 0.02)
            # the pilasters
            for x in (a - 0.45, b + 0.15):
                out += f.box(x, x + 0.30, face, face + 0.12, fc["z0"],
                             e0, trim)
                out += f.box(x - 0.04, x + 0.34, face, face + 0.16,
                             e0 - 0.10, e0, trim)   # its capital
            # the entablature and its cornice
            out += f.box(s - W_ / 2, s + W_ / 2, face, face + 0.20, e0, e1,
                         trim)
            out += f.box(s - W_ / 2 - 0.08, s + W_ / 2 + 0.08, face,
                         face + 0.28, e1 - 0.06, e1, trim)
            if h > 0.15:
                tri = [(s - W_ / 2 - 0.08, e1), (s + W_ / 2 + 0.08, e1),
                       (s, e1 + h)]
                out += f.plate(tri, face, face + 0.22, trim)
                # its tympanum recessed: the inner triangle a shade darker
                k = 0.16
                inner = [(s - W_ / 2 + 0.25, e1 + 0.06),
                         (s + W_ / 2 - 0.25, e1 + 0.06),
                         (s, e1 + h - k)]
                out += f.plate(inner, face + 0.22, face + 0.225,
                               _shade(trim, 0.9))
    # small pediments over the front's upper windows
    arch, levels, el, g = _ctx(doc)
    for fc in fcs:
        if not fc["front"] or fc["i"] == g:
            continue
        f, face = fc["f"], fc["face"]
        for a, b, za, zb, kind, o in fc["ops"]:
            if kind != "window" or b - a < 0.6 or o.get("arcade"):
                continue
            room = fc["z1"] - zb
            if room < 0.35:
                continue
            Wd = (b - a) + 0.3
            s = (a + b) / 2
            out += f.box(s - Wd / 2, s + Wd / 2, face, face + 0.14, zb + 0.04,
                         zb + 0.14, trim)
            h = min(Wd * 0.18, room - 0.2)
            if h > 0.1:
                out += f.plate([(s - Wd / 2, zb + 0.14), (s + Wd / 2,
                                                         zb + 0.14),
                                (s, zb + 0.14 + h)], face, face + 0.14,
                               trim)
    return out


# ---- Art Deco ---------------------------------------------------------------------
def _deco_fins(doc, fcs, wall, accent) -> list:
    from shapely.geometry import Point
    from . import modern as MD
    arch, levels, el, g = _ctx(doc)
    regs = MD._regions(doc)
    fin_c = _shade(wall, 1.05)
    out = []
    for fc in fcs:
        if not fc["front"]:
            continue
        f, L, face = fc["f"], fc["L"], fc["face"]
        xs = [0.2, L - 0.2]
        spans = sorted((a, b) for a, b, *_r in fc["ops"])
        for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
            if a2 - b1 >= 0.55:
                xs.append((b1 + a2) / 2)
        xs = sorted(x for x in xs if 0.15 <= x <= L - 0.15 and not any(
            a - 0.2 < x < b + 0.2 for a, b in spans))
        # the top of this volume: nothing of the house above here
        mid = f.P(L / 2, -fc["face"] - 0.2, 0.0)
        top = not any(el[k] > el[fc["i"]] + 0.5 and r.contains(
            Point(mid[0], mid[1])) for k, r in regs.items())
        for x in xs:
            out += f.box(x - 0.15, x + 0.15, face - 0.004, face + 0.20,
                         fc["z0"], fc["z1"], fin_c)
            out += f.box(x - 0.03, x + 0.03, face + 0.20, face + 0.215,
                         fc["z0"] + 0.4, fc["z1"], _c4(accent))
            if top:                       # stepped above the roof
                zt = fc["z1"]
                for k, (hw, dz) in enumerate(((0.15, 1.0), (0.10, 1.45),
                                              (0.05, 1.75))):
                    z_a = zt if k == 0 else zt + (1.0, 1.45)[k - 1]
                    out += f.box(x - hw, x + hw, face - 0.004,
                                 face + 0.20 - 0.04 * k, z_a, zt + dz,
                                 fin_c)
    return out


def _deco_bands(doc, trim) -> list:
    """Three thin speed bands round the top roof, under its edge — one
    mitred solid each, so they join at the corners."""
    from . import modern as MD
    out = []
    for part, zt, kind in MD.ring_parts(doc, 0.05, roof_only=True):
        for k in range(3):
            z = zt - 0.30 - k * 0.16
            out += MD._solid(part, z, z + 0.06, trim)
    return out


def _deco_crown(doc, fcs, wall, accent) -> list:
    from . import modern as MD
    fc, op = _main_door(doc, fcs)
    from . import lookstyle as LS
    try:
        fr, _w, _o = LS.front_side(doc, LS._outer_walls(doc["arch"]))
    except Exception:  # noqa: BLE001
        return []
    if fr is None:
        return []
    edges = MD._front_edges(doc, fr)
    if not edges:
        return []
    if fc is not None:
        c = fc["f"].P((op[0] + op[1]) / 2, 0.0, 0.0)
    else:
        c = None

    def score(e):
        i, p, q, u, n, L, zt = e
        if c is None:
            return -L
        s = (c[0] - p[0]) * u[0] + (c[1] - p[1]) * u[1]
        off = max(0.0, -s, s - L)
        return off
    i, p, q, u, n, L, zt = min(edges, key=score)
    f = _Frame(p, u, n)
    if c is not None:
        s = (c[0] - p[0]) * u[0] + (c[1] - p[1]) * u[1]
        s = min(max(s, 0.6), L - 0.6)
    else:
        s = L / 2
    out = []
    col = _shade(wall, 1.05)
    z = zt
    for wdt in (min(3.2, L), min(2.2, L * 0.7), min(1.2, L * 0.4)):
        a, b = max(0.0, s - wdt / 2), min(L, s + wdt / 2)
        out += f.box(a, b, -0.25, 0.12, z, z + 0.45, col)
        out += f.box(a, b, 0.12, 0.14, z + 0.38, z + 0.43, _c4(accent))
        z += 0.45
    # a sunray: three accent rays fanning over the top step
    for ang in (-35.0, 0.0, 35.0):
        r = math.radians(ang)
        x0, z0 = s, zt + 0.1
        x1, z1 = s + math.sin(r) * 1.1, zt + 0.1 + math.cos(r) * 1.1
        nx, nz = (z1 - z0), -(x1 - x0)
        ln = math.hypot(nx, nz) or 1.0
        nx, nz = nx / ln * 0.03, nz / ln * 0.03
        out += f.plate([(x0 - nx, z0 - nz), (x0 + nx, z0 + nz),
                        (x1 + nx, z1 + nz), (x1 - nx, z1 - nz)], 0.12, 0.15,
                       _c4(accent))
    return out


# ---- Italianate --------------------------------------------------------------------
def _eave_brackets(doc, trim) -> list:
    from . import project as PJ
    from .engine import model as M
    from .engine import structure as S
    from .lookstyle import is_look_roof
    arch = doc["arch"]
    try:
        info = S.levels_info(arch, M.elevations)
    except Exception:  # noqa: BLE001
        return []
    del PJ
    out = []
    for r in arch["structure"]:
        if not is_look_roof(r) or r.get("kind") not in ("hip", "gable"):
            continue
        li = info.get(r["level"])
        if li is None or len(r.get("corners") or []) != 4:
            continue
        base = float(li["under"])
        o = float(r.get("overhang", 0.0))
        if o < 0.25:
            continue
        tan = math.tan(math.radians(float(r.get("slope", 30.0))))
        cs = [tuple(c[:2]) for c in r["corners"]]
        area = 0.5 * sum(p[0] * q[1] - q[0] * p[1]
                         for p, q in zip(cs, cs[1:] + cs[:1]))
        if area < 0:
            cs = cs[::-1]
        for k in range(4):
            p, q = cs[k], cs[(k + 1) % 4]
            L = math.dist(p, q)
            if L < 1.0:
                continue
            u = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
            n = (u[1], -u[0])                     # outward (CCW)
            f = _Frame(p, u, n)
            reach = o * 0.85
            zt_out = base - reach * tan          # the soffit at its tip
            n_ = max(1, int((L - 0.6) / 1.5))
            for j in range(n_ + 1):
                sc = 0.3 + (L - 0.6) * j / max(n_, 1)
                for d_ in (-0.14, 0.14):          # paired
                    sa, sb = sc + d_ - 0.05, sc + d_ + 0.05
                    if sa < 0.05 or sb > L - 0.05:
                        continue
                    # a scroll bracket: deep at the wall, thin at its tip,
                    # its top under the soffit's slope
                    prof = [(0.0, base - 0.55), (0.0, base - 0.02),
                            (reach, zt_out - 0.02), (reach, zt_out - 0.12),
                            (reach * 0.35, base - 0.40)]
                    loop = [f.P(sa, a, z) for a, z in prof]
                    out += _prism(loop, (u[0] * (sb - sa), u[1] * (sb - sa),
                                         0.0), trim)
    return out


# ---- all of it ---------------------------------------------------------------------
def faces(doc) -> list:
    look = doc.get("look") or {}
    if not look or look.get("style") in (None, "", "none"):
        return []
    keys = ("pediment", "deco_fins", "deco_bands", "deco_crown",
            "window_boxes", "half_timber", "gf_clad", "shutters", "siding",
            "eave_brackets")
    if not any(look.get(k) for k in keys):
        return []
    from .host import log_error
    trim = _c4(look.get("trim"), (0.95, 0.93, 0.88))
    wall = look.get("wall") or (0.9, 0.9, 0.88)
    stone = _c4(look.get("stone"), (0.58, 0.28, 0.20))
    accent = look.get("accent") or (0.24, 0.16, 0.10)
    try:
        fcs = faces_of(doc)
    except Exception:  # noqa: BLE001
        log_error("stylekit.faces_of")
        return []
    out = []
    for key, name, fn in (
            ("half_timber", "Look half-timbering",
             lambda: _half_timber(doc, fcs, _c4(accent))),
            ("gf_clad", "Look brick ground floor",
             lambda: _gf_clad(doc, fcs, stone)),
            ("siding", "Look clapboard siding",
             lambda: _siding(doc, fcs, wall,
                             skip_ground=bool(look.get("gf_clad")))),
            ("shutters", "Look shutters",
             lambda: _shutters(doc, fcs, _c4(accent))),
            ("window_boxes", "Look window boxes",
             lambda: _window_boxes(doc, fcs, trim)),
            ("pediment", "Look pediments",
             lambda: _pediments(doc, fcs, trim)),
            ("deco_fins", "Look Deco fins",
             lambda: _deco_fins(doc, fcs, wall, accent)),
            ("deco_bands", "Look Deco speed bands",
             lambda: _deco_bands(doc, trim)),
            ("deco_crown", "Look Deco crown",
             lambda: _deco_crown(doc, fcs, wall, accent)),
            ("eave_brackets", "Look eave brackets",
             lambda: _eave_brackets(doc, trim))):
        if not look.get(key):
            continue
        try:
            fs = fn()
            if fs:
                out.append((name, fs))
        except Exception:  # noqa: BLE001
            log_error("stylekit." + key)
    return out
