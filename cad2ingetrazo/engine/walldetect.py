# SPDX-License-Identifier: GPL-3.0-or-later
# Wall / opening detection from DXF lines (written for the ArchXQ Community
# build, reused by CAD2IngeTrazo).
"""Walls from a DXF plan — read a CAD drawing onto a level as a reference,
then raise ArchXQ walls (and their openings) from its parallel lines.

Community module (GPL-3.0-or-later): the Lite ships without ``importdxf``;
this one is written for the calls ``ui.py`` makes:

- ``read(path)``      the drawing's lines, in drawing units, + its unit;
- ``placed(data)``    → ``{"segs": [[x0, y0, x1, y1, layer_index]…] (m),
                        "layers": [names], "unit": m per unit, "shift"}``;
- ``walls_from(segs, tmin, tmax)`` → ``(walls, openings)``:
  walls ``[(a, b, t)]`` — centre lines in metres, ends meeting at the
  centre-line crossings so ``walls.plan`` joins them by itself — and
  openings ``[(wall_index, pos, width, kind)]``, ``pos`` the opening's
  middle in metres from the wall's ``a``, ``kind`` «door» | «window» (read
  from the swing arc / glazing lines in the gap, else from the width);
- ``DOOR_MAX``        an opening up to this wide is made a door.

How the walls are found (the usual CAD reading): two parallel lines a wall
thickness apart (between Min and Max) with nothing parallel between them
are the two faces of one wall; collinear pieces of the same thickness are
one wall; a gap between them filled by a crossing wall is a junction, a
gap of an opening's size is an OPENING in that wall. Pure Python, no Qt.
"""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

#: An opening this wide or narrower becomes a door, wider a window.
DOOR_MAX = 1.20
#: A gap in a run of wall read as an opening (m).
OPEN_MIN, OPEN_MAX = 0.45, 4.0

ANG_TOL = 1.0          # degrees: parallel
PAR_TOL = 0.005        # m: drafting tolerance
MIN_LEN = 0.10         # m: a wall piece shorter than this is noise
MIN_RUN = 0.35         # m: a whole wall shorter than this is a column's
                       #    cut or a sliver between two drawings, not a wall
SAGITTA = 0.01         # m: how finely arcs are flattened
FAR = 10_000.0         # m from the origin: a survey drawing, moved home

_INSUNITS_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0,
               7: 1000.0, 10: 0.9144}


# ---- reading ------------------------------------------------------------------
def _open(path: Path):
    try:
        from formats.dxf_in import open_document        # the host's reader
        return open_document(path)
    except ImportError:
        import ezdxf
        from ezdxf import recover
        try:
            return ezdxf.readfile(str(path))
        except ezdxf.DXFStructureError:
            return recover.readfile(str(path))[0]


def _unit(doc) -> float:
    """Metres per drawing unit: the header, vetoed by the drawing's own
    sizes when it lies (the host's rule — offices copy templates)."""
    try:
        from formats.dxf_in import suggest_unit_scale
        scale, _code = suggest_unit_scale(doc)
        if scale:
            return float(scale)
    except ImportError:
        pass
    code = int(doc.header.get("$INSUNITS", 0) or 0)
    return _INSUNITS_M.get(code, 0.001)          # unitless: millimetres


def read(path) -> dict:
    """Every line of the drawing's model space — lines, polylines, arcs and
    circles flattened, blocks exploded (their layer-0 contents take the
    block's layer) — in DRAWING units: ``{"segs": [(x0, y0, x1, y1,
    layer)], "unit": m per unit}``."""
    path = Path(path)
    doc = _open(path)
    unit = _unit(doc)
    sag = SAGITTA / unit
    segs: list = []

    def emit(e, inherit, depth):
        t = e.dxftype()
        lay = e.dxf.get("layer", "0") or "0"
        if lay == "0" and inherit:
            lay = inherit
        if t == "INSERT":
            if depth < 8:
                for v in e.virtual_entities():
                    _safe(emit, v, lay, depth + 1)
        elif t == "LINE":
            a, b = e.dxf.start, e.dxf.end
            segs.append((a[0], a[1], b[0], b[1], lay))
        elif t in ("LWPOLYLINE", "POLYLINE"):
            if t == "POLYLINE" and (e.is_poly_face_mesh or e.is_polygon_mesh):
                return
            for v in e.virtual_entities():
                _safe(emit, v, lay, depth)
        elif t in ("ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
            pts = list(e.flattening(sag))
            for p, q in zip(pts, pts[1:]):
                segs.append((p[0], p[1], q[0], q[1], lay))

    for e in doc.modelspace():
        _safe(emit, e, None, 0)
    return {"segs": segs, "unit": unit}


def _safe(fn, *args) -> None:
    try:
        fn(*args)
    except Exception:  # noqa: BLE001 — one bad entity never stops the read
        pass


def placed(data: dict) -> dict:
    """The drawing in METRES, ready for a level: layers indexed, a
    survey-coordinate drawing (km from the origin) moved to it."""
    k = float(data.get("unit") or 0.001)
    raw = data.get("segs") or []
    layers = sorted({s[4] for s in raw})
    index = {n: i for i, n in enumerate(layers)}
    segs = []
    for x0, y0, x1, y1, lay in raw:
        if abs(x1 - x0) * k < 1e-6 and abs(y1 - y0) * k < 1e-6:
            continue
        segs.append([x0 * k, y0 * k, x1 * k, y1 * k, index[lay]])
    shift = (0.0, 0.0)
    if segs:
        xs = [v for s in segs for v in (s[0], s[2])]
        ys = [v for s in segs for v in (s[1], s[3])]
        if max(map(abs, xs + ys)) > FAR:
            shift = (min(xs), min(ys))
            for s in segs:
                s[0] -= shift[0]
                s[2] -= shift[0]
                s[1] -= shift[1]
                s[3] -= shift[1]
    segs = [[round(v, 5) for v in s[:4]] + [s[4]] for s in segs]
    return {"segs": segs, "layers": layers, "unit": k, "shift": shift}


# ---- 2D helpers (metres) ------------------------------------------------------
def _sub(a, b): return (a[0] - b[0], a[1] - b[1])
def _add(a, b): return (a[0] + b[0], a[1] + b[1])
def _mul(a, k): return (a[0] * k, a[1] * k)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1]
def _len(a): return math.hypot(a[0], a[1])
def _perp(u): return (-u[1], u[0])


def _unit_v(a):
    L = _len(a)
    return (a[0] / L, a[1] / L) if L > 1e-12 else (1.0, 0.0)


def _ang(u): return math.degrees(math.atan2(u[1], u[0])) % 180.0


def _angdiff(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _canon(u):
    if u[1] < -1e-12 or (abs(u[1]) <= 1e-12 and u[0] < 0):
        return (-u[0], -u[1])
    return u


def _cross_pt(p, u, q, w):
    den = u[0] * w[1] - u[1] * w[0]
    if abs(den) < 1e-12:
        return None
    d = _sub(q, p)
    s = (d[0] * w[1] - d[1] * w[0]) / den
    return _add(p, _mul(u, s))


# ---- walls: pairs of parallel lines ---------------------------------------------
def _pairs(lines, tmin, tmax):
    """Centre-line pieces {"p", "q", "t"} from pairs of facing lines."""
    nb = max(3, int(math.ceil(180.0 / ANG_TOL)))
    S = []
    for p, q in lines:
        L = _len(_sub(q, p))
        if L < PAR_TOL:
            continue
        u = _unit_v(_sub(q, p))
        a = _ang(u)
        S.append((p, q, u, L, a, int(a / ANG_TOL) % nb))
    buckets = defaultdict(list)
    for i, s in enumerate(S):
        buckets[s[5]].append(i)
    out = []
    for i, (p, q, u, L, a, b) in enumerate(S):
        n = _perp(u)
        near = [j for kk in {(b - 1) % nb, b, (b + 1) % nb}
                for j in buckets[kk]]
        for j in near:
            if j <= i:
                continue
            p2, q2, _u2, _L2, a2, _ = S[j]
            if _angdiff(a, a2) > ANG_TOL:
                continue
            s1, s2 = _dot(_sub(p2, p), n), _dot(_sub(q2, p), n)
            if abs(s1 - s2) > PAR_TOL:
                continue
            s = (s1 + s2) / 2.0
            t = abs(s)
            if t < tmin - PAR_TOL or t > tmax + PAR_TOL:
                continue
            t1, t2 = _dot(_sub(p2, p), u), _dot(_sub(q2, p), u)
            o0, o1 = max(0.0, min(t1, t2)), min(L, max(t1, t2))
            if o1 - o0 < MIN_LEN:
                continue
            if _blocked(S, near, i, j, p, u, n, s, o0, o1, a):
                continue
            off = _mul(n, s / 2.0)
            out.append({"p": _add(_add(p, _mul(u, o0)), off),
                        "q": _add(_add(p, _mul(u, o1)), off), "t": t})
    return out


def _blocked(S, near, i, j, p, u, n, s, o0, o1, a) -> bool:
    """Another parallel line between the two: a finish line, or two walls
    side by side — not one wall."""
    lo, hi = min(0.0, s) + PAR_TOL, max(0.0, s) - PAR_TOL
    for k in near:
        if k in (i, j):
            continue
        p3, q3, _u, _L, a3, _ = S[k]
        if _angdiff(a, a3) > ANG_TOL:
            continue
        s1, s2 = _dot(_sub(p3, p), n), _dot(_sub(q3, p), n)
        if not (lo < s1 < hi and lo < s2 < hi):
            continue
        t1, t2 = _dot(_sub(p3, p), u), _dot(_sub(q3, p), u)
        if min(o1, max(t1, t2)) - max(o0, min(t1, t2)) > 0.5 * (o1 - o0):
            return True
    return False


# ---- walls: one run per line of wall, its gaps read -------------------------------
def _crossed(u, n, c, t, g0, g1, pieces) -> bool:
    """A non-parallel wall fills the gap [g0, g1] of the run (a T or a
    cross), so the run goes on through it."""
    p = _mul(n, c)
    for w in pieces:
        u2 = _unit_v(_sub(w["q"], w["p"]))
        if _angdiff(_ang(u), _ang(u2)) < 10.0 or g1 - g0 > w["t"] + 4 * PAR_TOL:
            continue
        X = _cross_pt(p, u, w["p"], u2)
        if X is None:
            continue
        tx = _dot(X, u)
        s = _dot(_sub(X, w["p"]), u2)
        L2 = _len(_sub(w["q"], w["p"]))
        if g0 - PAR_TOL <= tx <= g1 + PAR_TOL and -t - PAR_TOL <= s <= L2 + t + PAR_TOL:
            return True
    return False


def _runs(pieces):
    """Collinear pieces of one thickness → runs ``{"p", "q", "t",
    "gaps": [(t0, t1)]}`` (gaps along u, absolute) bridging junctions and
    opening-sized gaps."""
    groups = []
    for w in sorted(pieces, key=lambda x: -_len(_sub(x["q"], x["p"]))):
        u = _canon(_unit_v(_sub(w["q"], w["p"])))
        a = _ang(u)
        for g in groups:
            if _angdiff(g["a"], a) > ANG_TOL or abs(g["t"] - w["t"]) > 2 * PAR_TOL:
                continue
            if abs(_dot(w["p"], g["n"]) - g["c"]) > 2 * PAR_TOL \
                    or abs(_dot(w["q"], g["n"]) - g["c"]) > 2 * PAR_TOL:
                continue
            g["members"].append(w)
            break
        else:
            n = _perp(u)
            groups.append({"u": u, "n": n, "a": a, "c": _dot(w["p"], n),
                           "t": w["t"], "members": [w]})
    out = []
    for g in groups:
        u, n, c, t = g["u"], g["n"], g["c"], g["t"]
        ivs = sorted((min(_dot(w["p"], u), _dot(w["q"], u)),
                      max(_dot(w["p"], u), _dot(w["q"], u)))
                     for w in g["members"])
        cur = [ivs[0][0], ivs[0][1], []]
        runs = []
        for a0, a1 in ivs[1:]:
            gap = a0 - cur[1]
            if gap <= PAR_TOL or _crossed(u, n, c, t, cur[1], a0, pieces):
                cur[1] = max(cur[1], a1)
            elif OPEN_MIN <= gap <= OPEN_MAX:
                cur[2].append((cur[1], a0))          # an opening
                cur[1] = max(cur[1], a1)
            else:
                runs.append(cur)
                cur = [a0, a1, []]
        runs.append(cur)
        base = _mul(n, c)
        for t0, t1, gaps in runs:
            # longer than thick: a cut column (a square) is not a wall
            if t1 - t0 >= max(MIN_RUN, 1.5 * t):
                out.append({"p": _add(base, _mul(u, t0)),
                            "q": _add(base, _mul(u, t1)), "t": t,
                            "gaps": [(_add(base, _mul(u, (a + b) / 2)), b - a)
                                     for a, b in gaps]})
    return out


def _extend(runs):
    """Each free end to the crossing of its centre line with a nearby
    non-parallel wall's: the walls meet, ``walls.plan`` joins them."""
    out = []
    for i, w in enumerate(runs):
        p, q = w["p"], w["q"]
        u = _unit_v(_sub(q, p))
        ends = [p, q]
        for e in (0, 1):
            best = None
            for j, w2 in enumerate(runs):
                if j == i:
                    continue
                u2 = _unit_v(_sub(w2["q"], w2["p"]))
                if _angdiff(_ang(u), _ang(u2)) < 10.0:
                    continue
                X = _cross_pt(p, u, w2["p"], u2)
                if X is None:
                    continue
                d = _len(_sub(X, (p, q)[e]))
                if d > w2["t"] + PAR_TOL:
                    continue
                s = _dot(_sub(X, w2["p"]), u2)
                L2 = _len(_sub(w2["q"], w2["p"]))
                if not (-w["t"] - PAR_TOL <= s <= L2 + w["t"] + PAR_TOL):
                    continue
                if best is None or d < best[0]:
                    best = (d, X)
            if best:
                ends[e] = best[1]
        out.append(dict(w, p=ends[0], q=ends[1]))
    return out


def _gap_kind(mid, width, u, t, context):
    """«door» | «window» | None — what the drawing shows in an opening.
    A door: its swing, pieces lying on a circle of the opening's width
    round one jamb (the hinge). A window: glazing lines along the wall,
    inside its band, across the gap. Nothing of either: unknown."""
    if not context:
        return None
    n = _perp(u)
    half = width / 2.0
    hinges = [_add(_add(mid, _mul(u, sa * half)), _mul(n, sb * t / 2))
              for sa in (-1, 1) for sb in (-1, 0, 1)]
    swing = [0.0] * len(hinges)
    face = [0.0] * len(hinges)          # which side of the wall it sweeps
    glaze = 0.0
    for s in context:
        a, b = (s[0], s[1]), (s[2], s[3])
        d = _sub(b, a)
        L = _len(d)
        if L < 1e-6:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        along = _dot(_sub(m, mid), u)
        across = _dot(_sub(m, mid), n)
        par = abs(_dot(_unit_v(d), u)) > math.cos(math.radians(ANG_TOL * 3))
        if par and abs(along) <= half + PAR_TOL \
                and abs(across) < t / 2 + PAR_TOL:
            glaze += L
            continue
        if par:
            continue
        # a swing sweeps OUTSIDE the wall, over the opening — never across
        # the wall's band (jambs, frames) nor beyond the span (columns)
        if abs(across) <= t / 2 + 0.02 or abs(along) > half + PAR_TOL:
            continue
        for k, H in enumerate(hinges):          # a chord of that circle:
            ra, rb = _len(_sub(a, H)), _len(_sub(b, H))   # both ends on it,
            if not (0.8 * width <= ra <= 1.2 * width):    # square to its
                continue                                   # radius
            if abs(ra - rb) > 0.03 * width + 0.005:
                continue
            if abs(_dot(_unit_v(d), _unit_v(_sub(m, H)))) > 0.2:
                continue
            swing[k] += L
            face[k] += L if across > 0 else -L
    if max(swing) >= 0.6 * width:       # a swing first: a door's closed leaf
        k = max(range(len(swing)), key=lambda i: swing[i])  # also lies along
        hinge = -1 if k < 3 else 1                           # the wall
        return ("door", hinge, 1 if face[k] >= 0 else -1)
    if glaze >= 0.8 * width:
        return ("window", 0, 0)
    return None


def walls_from(segs, tmin: float = 0.08, tmax: float = 0.40, context=None):
    """``(walls, openings)`` from a level's lines (metres) — see the module
    docstring. ``context``: every line of the drawing (all layers), read to
    tell a door (its swing) from a window (its glazing) in each opening;
    each opening is then ``(wall_index, pos, width, kind)``."""
    lines = [((float(s[0]), float(s[1])), (float(s[2]), float(s[3])))
             for s in segs]
    tmin, tmax = sorted((float(tmin), float(tmax)))
    runs = _extend(_runs(_pairs(lines, tmin, tmax)))
    walls, ops = [], []
    for w in runs:
        a, b = w["p"], w["q"]
        L = _len(_sub(b, a))
        if L < MIN_LEN:
            continue
        u = _unit_v(_sub(b, a))
        k = len(walls)
        walls.append((a, b, w["t"]))
        for mid, width in w["gaps"]:
            pos = _dot(_sub(mid, a), u)
            if width / 2 + 0.05 <= pos <= L - width / 2 - 0.05:
                g = _gap_kind(mid, width, u, w["t"], context)
                if g is None:
                    # nothing drawn in it: an opening down to the floor —
                    # a glass sliding door (or, without context, by width)
                    g = ("sliding", 0, 0) if context else (
                        ("door", -1, 1) if width <= DOOR_MAX
                        else ("window", 0, 0))
                ops.append((k, pos, width, g[0], g[1], g[2]))
    return walls, ops
