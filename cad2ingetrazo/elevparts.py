"""3.64.119: pergolas over the terraces and louvers on the windows — two
more design elements of «Design the elevations» (``doc["look"]``:
``pergola``, ``pergola_h``, ``pergola_col``; ``louver``, ``louver_where``,
``louver_col``). Drawn again at every rebuild (ornament.faces), so they
follow the plans: a pergola stands over each room the plan names TERRACE /
BALCONY / SIT-OUT / DECK / PATIO / ROOF GARDEN; louvers go in front of the
windows the plan draws."""
from __future__ import annotations

import math

PERGOLAS = [("none", "None"),
            ("slats", "Timber slats (posts, beams, cross-slats)"),
            ("lattice", "Lattice (slats both ways)"),
            ("louvered", "Louvered roof (blades)"),
            ("steel", "Steel frame (slim posts, wide spacing)")]
LOUVERS = [("none", "None"),
           ("horizontal", "Horizontal blades over the windows"),
           ("vertical", "Vertical fins over the windows"),
           ("shutters", "Louvred shutters (open, either side)")]
LOUVER_WHERE = [("front", "Front elevation only"),
                ("all", "Every outside wall")]
COLOURS = [("timber", "Timber"), ("dark", "Dark metal"),
           ("white", "White"), ("accent", "The design's accent colour")]
_COL = {"timber": (0.45, 0.30, 0.18, 1.0), "dark": (0.12, 0.12, 0.13, 1.0),
        "white": (0.95, 0.95, 0.93, 1.0)}
MAX_BOXES = 5000


def _colour(look, key, dflt):
    k = look.get(key) or dflt
    if k == "accent":
        a = list(look.get("accent") or (0.24, 0.16, 0.10))[:3]
        return (float(a[0]), float(a[1]), float(a[2]), 1.0)
    return _COL.get(k, _COL[dflt])


# ---- the pergolas ------------------------------------------------------------
def _terraces(doc):
    """[(level index, polygon)] — the open rooms the plan names."""
    from . import project as PJ
    from .engine import spaces as SP
    arch = doc["arch"]
    out = []
    for i, lv in enumerate(arch["levels"]):
        try:
            rooms = SP.of_level(arch, lv["id"])
        except Exception:  # noqa: BLE001
            continue
        for r in rooms:
            if not PJ.TERRACE_WORDS.search(str(r.get("name") or "")):
                continue
            p = r["poly"]
            if p.is_empty or p.area < 4.0:
                continue
            out.append((i, p))
    return out


def _rect(c, u, v, s0, s1, t0, t1):
    from shapely.geometry import Polygon
    return Polygon([(c[0] + u[0] * s + v[0] * t, c[1] + u[1] * s + v[1] * t)
                    for s, t in ((s0, t0), (s1, t0), (s1, t1), (s0, t1))])


def _frame_of(poly):
    """Centre, long axis u, short axis v and the half sizes (a, b)."""
    r = poly.minimum_rotated_rectangle
    pts = list(r.exterior.coords)[:4]
    e0 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    e1 = (pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])
    L0, L1 = math.hypot(*e0), math.hypot(*e1)
    if L0 < 1e-6 or L1 < 1e-6:
        return None
    if L0 >= L1:
        u, v, A, B = (e0[0] / L0, e0[1] / L0), (e1[0] / L1, e1[1] / L1), L0, L1
    else:
        u, v, A, B = (e1[0] / L1, e1[1] / L1), (e0[0] / L0, e0[1] / L0), L1, L0
    c = r.centroid
    return (c.x, c.y), u, v, A / 2, B / 2


def pergola_faces(doc) -> list:
    look = doc.get("look") or {}
    kind = look.get("pergola") or "none"
    if kind in ("none", "") or look.get("style") in (None, "", "none"):
        return []
    from shapely.geometry import Point

    from . import modern as MD
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    col = _colour(look, "pergola_col", "timber")
    H = min(max(float(look.get("pergola_h", 2.7) or 2.7), 2.2), 4.5)
    by_lv, budget = {}, MAX_BOXES
    steel = kind == "steel"
    for i, poly in _terraces(doc):
        fr = _frame_of(poly)
        if fr is None:
            continue
        c, u, v, a, b = fr
        if b < 0.75 or a < 1.0:
            continue
        try:
            zf = el[i] + float(PJ.open_offset(doc, levels[i]["id"])) + 0.05
        except Exception:  # noqa: BLE001
            zf = el[i] + 0.05
        a2, b2 = a - 0.12, b - 0.12          # posts a little inside the edge
        pw = 0.10 if steel else 0.15
        bw, bd = (0.10, 0.16) if steel else (0.12, 0.20)
        # posts: the corners, and every ~3.2 m along the long sides
        ns = max(1, int(math.ceil(2 * a2 / 3.2)))
        ss = [-a2 + k * (2 * a2 / ns) for k in range(ns + 1)]
        fs = []
        for s in ss:
            for t in (-b2, b2):
                pt = (c[0] + u[0] * s + v[0] * t, c[1] + u[1] * s + v[1] * t)
                if not poly.buffer(0.15).contains(Point(pt)):
                    continue
                fs += MD._solid(_rect(c, u, v, s - pw / 2, s + pw / 2,
                                      t - pw / 2, t + pw / 2),
                                zf, zf + H, col)
                budget -= 1
        zb0, zb1 = zf + H, zf + H + bd
        # two main beams along the long axis (on the post lines)
        for t in (-b2, b2):
            fs += MD._solid(_rect(c, u, v, -a2 - 0.25, a2 + 0.25,
                                  t - bw / 2, t + bw / 2), zb0, zb1, col)
            budget -= 1
        clip = poly.buffer(0.45)
        zr0, zr1 = zb1, zb1 + (0.05 if steel else 0.06)
        if kind in ("slats", "steel", "lattice"):
            pitch = 0.60 if steel else 0.32
            wd = 0.05 if steel else 0.07
            n = int(2 * a2 / pitch)
            for k in range(n + 1):
                s = -a2 + k * (2 * a2 / max(n, 1))
                r_ = _rect(c, u, v, s - wd / 2, s + wd / 2, -b2 - 0.35,
                           b2 + 0.35).intersection(clip)
                if budget <= 0:
                    break
                fs += MD._solid(r_, zr0, zr1 + 0.06, col)
                budget -= 1
            if kind == "lattice":
                m = int(2 * b2 / 0.30)
                for k in range(m + 1):
                    t = -b2 + k * (2 * b2 / max(m, 1))
                    r_ = _rect(c, u, v, -a2 - 0.25, a2 + 0.25, t - 0.025,
                               t + 0.025).intersection(clip)
                    if budget <= 0:
                        break
                    fs += MD._solid(r_, zr1 + 0.06, zr1 + 0.10, col)
                    budget -= 1
        elif kind == "louvered":
            pitch, wd = 0.20, 0.15       # blades across the short axis
            n = int(2 * a2 / pitch)
            for k in range(n + 1):
                s = -a2 + k * (2 * a2 / max(n, 1))
                r_ = _rect(c, u, v, s - wd / 2, s + wd / 2, -b2 - 0.15,
                           b2 + 0.15).intersection(clip)
                if budget <= 0:
                    break
                fs += MD._solid(r_, zb1, zb1 + 0.03, col)
                budget -= 1
        if fs:
            by_lv.setdefault(i, []).extend(fs)
    return [(f"Look pergola · {levels[i]['name']}", fs)
            for i, fs in by_lv.items()]


# ---- the louvers -------------------------------------------------------------
def _blades_h(fr, a, b, z0, z1, col, budget):
    """Horizontal blades over the box (s a..b, z z0..z1) + a frame."""
    fs = []
    for s0, s1 in ((a, a + 0.05), (b - 0.05, b)):
        fs += fr.box(s0, s1, 0.04, 0.10, z0, z1, col)
    for z in (z0, z1 - 0.05):
        fs += fr.box(a, b, 0.04, 0.10, z, z + 0.05, col)
    n = max(int((z1 - z0 - 0.1) / 0.075), 1)
    for k in range(n):
        z = z0 + 0.05 + k * ((z1 - z0 - 0.15) / n)
        fs += fr.box(a + 0.05, b - 0.05, 0.04, 0.095, z, z + 0.035, col)
    return fs, n + 4


def _fins_v(fr, a, b, z0, z1, col, budget):
    fs = []
    for z in (z0, z1 - 0.05):
        fs += fr.box(a, b, 0.04, 0.10, z, z + 0.05, col)
    n = max(int((b - a) / 0.12), 1)
    for k in range(n + 1):
        s = a + k * ((b - a - 0.03) / n)
        fs += fr.box(s, s + 0.03, 0.04, 0.14, z0 + 0.05, z1 - 0.05, col)
    return fs, n + 3


def _shutters(fr, a, b, z0, z1, col, room_l, room_r):
    """Two open louvred leaves flat against the wall, one each side."""
    fs, n = [], 0
    w = (b - a) / 2
    for side, room in ((-1, room_l), (1, room_r)):
        if room < w + 0.10:
            continue
        s0 = a - 0.04 - w if side < 0 else b + 0.04
        s1 = s0 + w
        for t0, t1 in ((s0, s0 + 0.05), (s1 - 0.05, s1)):
            fs += fr.box(t0, t1, 0.03, 0.08, z0, z1, col)
        for z in (z0, z1 - 0.05):
            fs += fr.box(s0, s1, 0.03, 0.08, z, z + 0.05, col)
        m = max(int((z1 - z0 - 0.1) / 0.07), 1)
        for k in range(m):
            z = z0 + 0.05 + k * ((z1 - z0 - 0.15) / m)
            fs += fr.box(s0 + 0.05, s1 - 0.05, 0.03, 0.075, z, z + 0.03, col)
        n += m + 4
    return fs, n


def louver_faces(doc) -> list:
    look = doc.get("look") or {}
    kind = look.get("louver") or "none"
    if kind in ("none", "") or look.get("style") in (None, "", "none"):
        return []
    from . import lookstyle as LS
    from . import modern as MD
    from . import wallpanels as WP
    arch, levels, el, order, g, polys = MD._ctx(doc)
    col = _colour(look, "louver_col", "timber")
    fr_dir = None
    if look.get("louver_where", "front") == "front":
        try:
            fr_dir, _w, _o = LS.front_side(doc, LS._outer_walls(arch))
        except Exception:  # noqa: BLE001
            fr_dir = None
        if fr_dir is None:
            return []
    out, budget = [], MAX_BOXES
    for i, poly in polys.items():
        fs = []
        for p, q, u, n, L in MD._edges(poly):
            if L < 1.0:
                continue
            if fr_dir is not None and n[0] * fr_dir[0] + n[1] * fr_dir[1] \
                    < 0.85:
                continue
            fr = MD._Frame(p, u, n)
            ops = WP._openings(arch, levels, i, p, q, u, n, recs=True)
            for a, b, z0, z1, o in ops:
                if o is None or o.get("kind") != "window" or o.get("vent"):
                    continue
                if b - a < 0.5 or budget <= 0:
                    continue
                za, zb = el[i] + z0 - 0.05, el[i] + z1 + 0.05
                if zb - za < 0.4:
                    continue
                if kind == "horizontal":
                    f_, nb = _blades_h(fr, a - 0.06, b + 0.06, za, zb, col,
                                       budget)
                elif kind == "vertical":
                    f_, nb = _fins_v(fr, a - 0.06, b + 0.06, za, zb, col,
                                     budget)
                else:
                    left = a - max([b2 for a2, b2, _z0, _z1, _o in ops
                                    if b2 <= a + 1e-6] or [0.0])
                    right = min([a2 for a2, b2, _z0, _z1, _o in ops
                                 if a2 >= b - 1e-6] or [L]) - b
                    f_, nb = _shutters(fr, a, b, za, zb, col, left, right)
                fs += f_
                budget -= nb
        if fs:
            out.append((f"Look louvers · {levels[i]['name']}", fs))
    return out


def faces(doc) -> list:
    """[(name, faces)] — the pergolas and the louvers."""
    out = []
    for fn in (pergola_faces, louver_faces):
        try:
            out += fn(doc)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("elevparts." + fn.__name__)
    return out
