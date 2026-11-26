"""3.64.44: reference elevations and perspectives — pictures or drawings of
the building's sides the model follows and keeps to.

Each reference is a file (an image — PNG / JPG / BMP / TIF —, a PDF page,
or a DXF / DWG) with the side it shows (north / south / east / west, or
«auto»: the side whose openings it matches best) or «perspective» (only
shown, for comparison). They are kept in ``doc["ref_elev"]``:

    {"file", "page", "side", "show", "follow", "fit"}

**Follow** reads the picture's lines (a PDF's own vectors, a picture's
long straight ink runs) and slides and scales them along the model's side
until the plan's window and door jambs fall on the drawn frame lines —
the drawing's scale and position are found, not asked for. Then each
opening seen on that side takes its sill and head from the frame drawn
over it (``elevread._apply_view``). Every «Update from CAD» follows them
again, so the elevations keep to them.

**Show** stands each picture beside its side of the model, at that scale,
half see-through — a reference image (IngeTrazo's own), on the layer
«C2I reference elevations» — to compare the model against.
"""
from __future__ import annotations

import math
import os

SIDES = ("auto", "north", "south", "east", "west", "perspective")
SIDE_LABELS = {"auto": "Auto (the side it matches)", "north": "North side",
               "south": "South side", "east": "East side",
               "west": "West side", "perspective": "Perspective (its look)"}
IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
REF_LAYER = "C2I reference elevations"
REF_NAME = "C2I reference"
MAX_PX = 3000                      # a picture read at most this wide/high


# ---- the reference's picture and its lines ----------------------------------
def kind_of(path) -> str:
    e = os.path.splitext(str(path))[1].lower()
    if e == ".pdf":
        return "pdf"
    if e in (".dxf", ".dwg"):
        return "cad"
    return "image" if e in IMG_EXT else ""


def _qimage_of_pdf(path, page):
    """The PDF page as a picture through Qt's own PDF module, when the
    IngeTrazo build carries it (else None)."""
    try:
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtCore import QSize
    except Exception:  # noqa: BLE001
        return None
    try:
        doc = QPdfDocument()
        doc.load(str(path))
        if doc.pageCount() < 1:
            return None
        i = min(max(page, 1), doc.pageCount()) - 1
        sz = doc.pagePointSize(i)
        k = MAX_PX / max(sz.width(), sz.height(), 1.0)
        img = doc.render(i, QSize(int(sz.width() * k), int(sz.height() * k)))
        return img if not img.isNull() else None
    except Exception:  # noqa: BLE001
        return None


def _paint(segs, w, h, px_w):
    """Lines drawn into a white picture ``px_w`` wide (the reference shown
    when the file is no picture itself): (QImage, scale px per unit)."""
    from PySide6.QtCore import QLineF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
    k = px_w / max(w, 1e-9)
    W, H = max(int(w * k), 8), max(int(h * k), 8)
    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor(20, 20, 20), 1.2, Qt.SolidLine))
    for a, b, c, d in segs:
        p.drawLine(QLineF(a * k, H - b * k, c * k, H - d * k))
    p.end()
    return img, k


def source(path, page=1, unit=None) -> dict:
    """The reference read: {"img": QImage (shown), "segs": [(x1, y1, x2,
    y2)] and "arcs": [(x0, y0, x1, y1)] in the picture's pixels, y up from
    its bottom, "w", "h" (pixels), "m_per_px": known scale or None,
    "pages"}. Raises ValueError when nothing can be read."""
    from PySide6.QtGui import QImage
    k = kind_of(path)
    if not os.path.isfile(str(path)):
        raise ValueError(f"File not found: {path}")
    if k == "image":
        img = QImage(str(path))
        if img.isNull():
            raise ValueError("This picture could not be opened")
        if max(img.width(), img.height()) > MAX_PX:
            from PySide6.QtCore import Qt
            img = img.scaled(MAX_PX, MAX_PX, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
        segs = raster_segs(img)
        return {"img": img, "segs": segs, "arcs": [], "w": img.width(),
                "h": img.height(), "m_per_px": None, "pages": 1,
                "arcs_known": False}
    if k == "pdf":
        from . import pdfvec
        vec = pdfvec.page_lines(path, page)
        img = _qimage_of_pdf(path, page)
        if vec and len(vec["segs"]) >= 40:
            if img is None:
                img, _k = _paint(vec["segs"], vec["w"], vec["h"], MAX_PX)
            kx = img.width() / max(vec["w"], 1e-9)
            segs = [(a * kx, b * kx, c * kx, d * kx)
                    for a, b, c, d in vec["segs"]]
            arcs = [(a * kx, b * kx, c * kx, d * kx)
                    for a, b, c, d in vec["arcs"]]
            return {"img": img, "segs": segs, "arcs": arcs,
                    "w": img.width(), "h": img.height(), "m_per_px": None,
                    "pages": vec.get("pages", 1), "arcs_known": True}
        if img is None:
            raise ValueError(
                "This PDF holds no drawing lines this reader can follow (a "
                "scan, or an encrypted file) — save the page as a picture "
                "(PNG / JPG) and pick that")
        return {"img": img, "segs": raster_segs(img), "arcs": [],
                "w": img.width(), "h": img.height(), "m_per_px": None,
                "pages": (vec or {}).get("pages", 1), "arcs_known": False}
    if k == "cad":
        from . import cadread
        raw = cadread.read(path, unit)
        ex = raw["extents"]
        segs = [(s[0] - ex[0], s[1] - ex[1], s[2] - ex[0], s[3] - ex[1])
                for s in raw["segs"]]
        w, h = ex[2] - ex[0], ex[3] - ex[1]
        img, kp = _paint(segs, w, h, MAX_PX)
        segs = [(a * kp, b * kp, c * kp, d * kp) for a, b, c, d in segs]
        arcs = []
        for a in raw.get("arcs", []):
            xs = [p[0] for p in (a["p0"], a["p1"], a["pm"])]
            ys = [p[1] for p in (a["p0"], a["p1"], a["pm"])]
            arcs.append(((min(xs) - ex[0]) * kp, (min(ys) - ex[1]) * kp,
                         (max(xs) - ex[0]) * kp, (max(ys) - ex[1]) * kp))
        return {"img": img, "segs": segs, "arcs": arcs, "w": img.width(),
                "h": img.height(), "m_per_px": float(raw["unit"]) / kp,
                "pages": 1, "arcs_known": True, "raw": raw}
    raise ValueError("Pick a picture (PNG / JPG / BMP / TIF), a PDF or a "
                     "DXF / DWG")


def raster_segs(img) -> list:
    """The long straight ink runs of a picture (an elevation's lines): the
    vertical and horizontal ones, as segments in pixels, y up."""
    import numpy as np
    from PySide6.QtGui import QImage
    im = img.convertToFormat(QImage.Format_RGB32)
    w, h = im.width(), im.height()
    ptr = im.constBits()
    a = np.frombuffer(ptr, dtype=np.uint8, count=im.sizeInBytes()).reshape(
        h, im.bytesPerLine())[:, :w * 4].reshape(h, w, 4)[:, :, :3]
    lum = a.mean(axis=2)
    if lum.mean() < 100:             # a dark drawing screen: light ink
        ink = a.max(axis=2) > 90
    else:
        ink = (255 - a.min(axis=2)) > 70
    min_len = max(10, int(0.012 * max(w, h)))
    out = []

    def runs(mask):
        """[(line index, start, end)] of runs along axis 1 of mask."""
        m = mask.astype(np.int8)
        d = np.diff(m, axis=1, prepend=0, append=0)
        rs, cs = np.nonzero(d == 1)
        re_, ce = np.nonzero(d == -1)
        keep = (ce - cs) >= min_len
        return rs[keep], cs[keep], ce[keep]
    # horizontal runs: rows
    r, s, e = runs(ink)
    hs = sorted(zip(r.tolist(), s.tolist(), e.tolist()))
    # vertical runs: columns
    c, s2, e2 = runs(ink.T)
    vs = sorted(zip(c.tolist(), s2.tolist(), e2.tolist()))

    def merge(items):
        """Runs in neighbouring lines that overlap (a thick line): one."""
        out_ = []
        last = {}
        for ln, a0, a1 in items:
            key = None
            for k_ in (ln - 1, ln - 2):
                for j in last.get(k_, ()):
                    b0, b1 = out_[j][1], out_[j][2]
                    if min(a1, b1) - max(a0, b0) > 0.7 * min(a1 - a0,
                                                             b1 - b0):
                        key = j
                        break
                if key is not None:
                    break
            if key is not None:
                l0, b0, b1, n = out_[key]
                out_[key] = (l0, min(a0, b0), max(a1, b1), n + 1)
                last.setdefault(ln, []).append(key)
            else:
                out_.append((ln, a0, a1, 1))
                last.setdefault(ln, []).append(len(out_) - 1)
        return [(l0 + (n - 1) / 2.0, a0, a1) for l0, a0, a1, n in out_]
    for y, x0, x1 in merge(hs):
        out.append((float(x0), float(h - y), float(x1), float(h - y)))
    for x, y0, y1 in merge(vs):
        out.append((float(x), float(h - y1), float(x), float(h - y0)))
    return out


# ---- matching a picture to a side ---------------------------------------------
def _xs_cluster(vals, tol):
    vals = sorted(vals)
    out = []
    for v in vals:
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(c) / len(c) for c in out]


def _verticals(src):
    """The picture's vertical lines [(x, y0, y1)], sorted by x (text and
    hatch strokes left out: shorter than 2 % of the picture)."""
    tall = 0.02 * max(src["w"], src["h"])
    out = []
    for a, b, c, d in src["segs"]:
        if abs(a - c) < 0.6 and abs(d - b) > tall:
            out.append(((a + c) / 2, min(b, d), max(b, d)))
    out.sort()
    return out


def _frames(V, k=6):
    """The picture's frames: two vertical lines side by side, of one height
    (a window's or a door's jambs) — [(centre x, width, y0, y1)]."""
    out = []
    n = len(V)
    for i in range(n):
        xa, a0, a1 = V[i]
        m = 0
        for j in range(i + 1, n):
            xb, b0, b1 = V[j]
            if xb - xa < 3.0:
                continue
            ov = min(a1, b1) - max(a0, b0)
            if ov > 0.8 * min(a1 - a0, b1 - b0) and \
                    abs((a1 - a0) - (b1 - b0)) < 0.25 * max(a1 - a0, b1 - b0):
                out.append(((xa + xb) / 2, xb - xa, max(a0, b0), min(a1, b1)))
                m += 1
                if m >= k:
                    break
    out.sort()
    return out


def _score(ops, F, fx, s, t, tol=0.09):
    """How many openings stand on a frame of the picture: its centre on
    the opening's (± tol), about its width, a storey's height at most.
    (n, [(opening item, frame)])."""
    import bisect
    n, got = 0, []
    tp = tol / s
    for op in ops:
        u0, u1 = op[2], op[3]
        c = ((u0 + u1) / 2 - t) / s
        w = (u1 - u0) / s
        i = bisect.bisect_left(fx, c - tp)
        j = bisect.bisect_right(fx, c + tp)
        best = None
        for fr in F[i:j]:
            if 0.55 * w <= fr[1] <= 1.7 * w and \
                    0.3 <= (fr[3] - fr[2]) * s <= 4.6:
                d = abs(fr[0] - c)
                if best is None or d < best[0]:
                    best = (d, fr)
        if best:
            n += 1
            got.append((op, best[1]))
    return n, got


def fit_side(arch, D, src, fixed_s=None):
    """How the picture lies on side D: (score, n, s m/px, t m, ops, seen,
    n openings, matches) with u (model, along the side) = s·x + t — the
    scale and slide that stand the most of the side's openings on a frame
    of the picture each (centre on centre: a drawn frame may be wider
    than the plan's opening)."""
    import numpy as np
    from . import elevread as EV
    ops, seen = EV._visible(arch, D)
    ops = [o for o in ops if o[3] - o[2] > 0.25]
    if len(ops) < 2:
        return None
    V = _verticals(src)
    if len(V) < 4:
        return None
    F = _frames(V)
    if len(F) < 2:
        return None
    fx = [f[0] for f in F]
    W_m = (max(u1 for _w, _u0, u1, _d in seen) -
           min(u0 for _w, u0, _u1, _d in seen)) if seen else 10.0
    cen = np.array(sorted({round((o[2] + o[3]) / 2, 3) for o in ops}))
    if fixed_s:
        cands = [fixed_s]
    else:
        smin = W_m / max(src["w"], 1) * 0.6
        smax = W_m / (0.08 * max(src["w"], 1))
        dm = (cen[None, :] - cen[:, None])
        dm = np.unique(np.round(dm[dm > 0.3], 2))
        FX = np.array(_xs_cluster(fx, 2.0))
        dp = FX[None, :] - FX[:, None]
        dp = dp[dp > 3.0]
        if not len(dm) or not len(dp):
            return None
        cs = (dm[:, None] / dp[None, :]).ravel()
        cs = cs[(cs > smin) & (cs < smax)]
        if not len(cs):
            return None
        bw = math.log(1.01)
        bins = np.floor(np.log(cs) / bw).astype(np.int64)
        u_, cnt = np.unique(bins, return_counts=True)
        c2 = cnt.astype(float).copy()
        idx = {int(b): i for i, b in enumerate(u_)}
        for i, b in enumerate(u_):
            for nb in (b - 1, b + 1):
                j = idx.get(int(nb))
                if j is not None:
                    c2[i] += 0.5 * cnt[j]
        top = u_[np.argsort(-c2)[:40]]
        cands = [math.exp((b + 0.5) * bw) for b in top]
    FXa = np.array(fx)
    best = None
    for s in cands:
        T = (cen[:, None] - s * FXa[None, :]).ravel()
        tb = np.floor(T / 0.05).astype(np.int64)
        u_, cnt = np.unique(tb, return_counts=True)
        for b in u_[np.argsort(-cnt)[:8]]:
            t = (b + 0.5) * 0.05
            n, got = _score(ops, F, fx, s, t)
            if n >= 2 and (best is None or n > best[0]):
                best = (n, s, t, got)
    if best is None:
        return None
    n, s, t, got = best
    # s and t together, least squares over the matched centres
    if len(got) >= 3:
        A = np.array([[fr[0], 1.0] for _op, fr in got])
        y = np.array([(op[2] + op[3]) / 2 for op, _fr in got])
        sol = np.linalg.lstsq(A, y, rcond=None)[0]
        s2, t2 = float(sol[0]), float(sol[1])
        if fixed_s:
            s2, t2 = fixed_s, float(np.mean(y - fixed_s * A[:, 0]))
        n2, got2 = _score(ops, F, fx, s2, t2)
        if n2 >= n:
            s, t, n, got = s2, t2, n2, got2
    # how much of what the picture draws on that side the openings explain
    # (a wrong side lines up some openings by chance, and leaves most of
    # the picture's frames unexplained)
    umin = min(u0 for _w, u0, _u1, _d in seen) if seen else -1e9
    umax = max(u1 for _w, _u0, u1, _d in seen) if seen else 1e9
    cl = []
    for fr in F:
        u = s * fr[0] + t
        if not (umin - 0.1 <= u <= umax + 0.1):
            continue
        if not (0.6 <= (fr[3] - fr[2]) * s <= 4.6 and
                0.3 <= fr[1] * s <= 6.0):
            continue
        if cl and u - cl[-1] < 0.25:
            continue
        cl.append(u)
    mc = [((op[2] + op[3]) / 2) for op, _fr in got]
    hit = sum(1 for u in cl if any(abs(u - c) < 0.3 for c in mc))
    prec = hit / len(cl) if cl else 0.0
    rec = n / len(ops)
    # the building's two ends: a tall line (a storey and more) at each
    ends = 0
    for ue in (umin, umax):
        xe = (ue - t) / s
        if any(abs(v[0] - xe) * s < 0.35 and (v[2] - v[1]) * s > 2.4
               for v in V):
            ends += 1
    sc = rec + 0.5 * prec + 0.4 * ends + 0.05 * n
    return (sc, n, s, t, ops, seen, len(ops), got)


def _ground_y(src, s, t, ops, seen, arch, D, el, g):
    """The picture's height of the ground floor's finished level (pixels,
    y up): from its doors' feet when the ground floor's doors are found,
    else from the lowest long line under the building (the ground) and
    the plinth over it."""
    gid = arch["levels"][g]["id"]
    feet = []
    for o, w, u0, u1, dep, br in ops:
        if o["kind"] != "door" or w["level"] != gid:
            continue
        lo, hi = (u0 - 0.06 - t) / s, (u1 + 0.06 - t) / s
        ys = [min(sg[1], sg[3]) for sg in src["segs"]
              if abs(sg[0] - sg[2]) < 0.5 and lo <= sg[0] <= hi and
              abs(sg[3] - sg[1]) * s > 1.2]
        if ys:
            feet.append(min(ys))
    if feet:
        feet.sort()
        return feet[len(feet) // 2], el[g]
    umin = min(u0 for _w, u0, _u1, _d in seen)
    umax = max(u1 for _w, _u0, u1, _d in seen)
    span = (umax - umin) / s
    x0, x1 = (umin - t) / s, (umax - t) / s
    ys = [sg[1] for sg in src["segs"] if abs(sg[1] - sg[3]) < 0.5 and
          min(sg[2], sg[0]) < x0 + 0.3 * span and
          max(sg[2], sg[0]) > x1 - 0.3 * span]
    if not ys:
        return None
    return min(ys), 0.0                 # the ground line: N.G.L. (0)


# ---- 3.64.153: the blocks of the site (A, B…) --------------------------------
def blocks_of(doc) -> list:
    """The blocks of the site — the built pieces of the ground floor
    (the walls' contour and the slabs, as the dialog's map draws them):
    [(letter, polygon)], the largest first (Block A)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    arch = doc["arch"]
    g = next((lv["id"] for lv in arch["levels"] if lv["kind"] == "ground"),
             None)
    poly = None
    try:
        from . import lookstyle as LS
        poly, _ws = LS._outline(arch, g)
    except Exception:  # noqa: BLE001
        poly = None
    try:
        sl = [Polygon(e["corners"]).buffer(0) for e in arch["structure"]
              if e.get("type") == "slab" and e.get("level") == g
              and len(e.get("corners") or []) >= 3]
        if sl:
            u = unary_union(sl).buffer(0.3, join_style=2).buffer(
                -0.3, join_style=2)
            if not u.is_empty and (poly is None or u.area > poly.area):
                poly = u
    except Exception:  # noqa: BLE001
        pass
    if poly is None:
        return []
    ps = sorted([q for q in getattr(poly, "geoms", [poly])
                 if q.geom_type == "Polygon" and q.area > 4.0],
                key=lambda q: -q.area)
    return [(chr(65 + n) if n < 26 else str(n + 1), q)
            for n, q in enumerate(ps)]


def block_of(ref) -> str:
    return str(ref.get("block", "all") or "all")


def _arch_for(doc, ref):
    """The model's data seen as one block's (the walls, openings and
    structure standing in it) — the whole model for «all» (the elements
    are the same dicts: what is set on them is set on the model)."""
    arch = doc["arch"]
    b = block_of(ref)
    if b == "all":
        return arch
    from shapely.geometry import Point
    blk = next((p for k, p in blocks_of(doc) if k == b), None)
    if blk is None:
        return arch
    P = blk.buffer(0.6)
    ws = [w for w in arch["walls"] if "a" in w and P.contains(Point(
        (w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2))]
    ids = {w["id"] for w in ws}
    out = dict(arch)
    out["walls"] = ws
    out["openings"] = [o for o in arch["openings"] if o["wall"] in ids]

    def _in(e):
        if e.get("x") is not None:
            return P.contains(Point(e["x"], e["y"]))
        cs = e.get("corners")
        if cs:
            return P.contains(Point(sum(c[0] for c in cs) / len(cs),
                                    sum(c[1] for c in cs) / len(cs)))
        return False
    out["structure"] = [e for e in arch["structure"] if _in(e)]
    # a block standing turned (the hall at 50°): its own north / south /
    # east / west are along its own walls
    try:
        mr = blk.minimum_rotated_rectangle
        cs = list(mr.exterior.coords)
        e0 = max(((cs[i], cs[i + 1]) for i in range(4)),
                 key=lambda ab: math.dist(ab[0], ab[1]))
        th = math.degrees(math.atan2(e0[1][1] - e0[0][1],
                                     e0[1][0] - e0[0][0])) % 90.0
        if th > 45.0:
            th -= 90.0
        if abs(th) > 3.0:
            c_, s_ = math.cos(math.radians(th)), math.sin(math.radians(th))
            from . import elevread as EV_

            def rot(v):
                return (v[0] * c_ - v[1] * s_, v[0] * s_ + v[1] * c_)
            out["_dirs"] = {k: (rot(fv), rot(rv))
                            for k, (fv, rv) in EV_.DIRS.items()}
    except Exception:  # noqa: BLE001
        pass
    return out


def follow(doc, ref, src=None, used=()) -> dict:
    """One reference followed: its side found (or as given), its scale and
    position, then the openings set from it. The fit is stored in
    ``ref["fit"]`` (for «Show»). A report."""
    from . import elevread as EV
    from . import project as PJ
    arch = _arch_for(doc, ref)
    if effective_side(ref) == "perspective":   # 3.64.45: its look
        from . import lookstyle
        return lookstyle.apply(doc, ref, src)
    if src is None:
        src = source(ref["file"], int(ref.get("page", 1) or 1))
    sides = [ref["side"]] if ref.get("side") in EV.DIRS else \
        [d for d in EV.DIRS if d not in used] or list(EV.DIRS)
    fits = []
    for D in sides:
        r_ = fit_side(arch, D, src, fixed_s=src.get("m_per_px"))
        if r_:
            fits.append((r_[0], r_[1], D) + r_[2:])
    if not fits:
        ref.pop("fit", None)
        return {"error": "its lines match no side of the model (are the "
                "plans imported? is it an elevation?)"}
    fits.sort(key=lambda f: (-f[0], -f[1]))
    sc, n, D, s, t, ops, seen, ne, got = fits[0]
    ops, seen = EV._visible(arch, D)
    if n < 3 or n < 0.35 * ne:
        ref.pop("fit", None)
        return {"error": f"too few jambs line up ({n} of {ne}) — set its "
                "side, or use a cleaner elevation (no hatch / shadows)"}
    levels = arch["levels"]
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    el = PJ.elevations(arch)
    gy = _ground_y(src, s, t, ops, seen, arch, D, el, g)
    if gy is None:
        return {"error": "its ground line was not found"}
    y0, z0 = gy

    def Z(y):
        return z0 + s * (y - y0)
    vert, horiz = [], []
    for a, b, c, d in src["segs"]:
        if abs(a - c) < 0.5:
            za, zb = sorted((Z(b), Z(d)))
            vert.append((s * a + t, za, zb))
        elif abs(b - d) < 0.5:
            ua, ub = sorted((s * a + t, s * c + t))
            horiz.append((ua, ub, Z(b)))
    arcs = [(s * a + t, s * c + t, Z(b), Z(d))
            for a, b, c, d in src.get("arcs") or []
            if (c - a) * s > 0.15]
    # the floors the picture draws (its doors' feet) against the model's
    notes = []
    for i_, lv in enumerate(levels):
        if i_ == g or el[i_] <= el[g]:
            continue
        feet = []
        for o, w, u0, u1, dep, br in ops:
            if o["kind"] != "door" or w["level"] != lv["id"] or br:
                continue
            lo, hi = (u0 - 0.06 - t) / s, (u1 + 0.06 - t) / s
            ys = [min(sg[1], sg[3]) for sg in src["segs"]
                  if abs(sg[0] - sg[2]) < 0.5 and lo <= sg[0] <= hi and
                  abs(sg[3] - sg[1]) * s > 1.2 and
                  el[i_] - 0.8 < Z(min(sg[1], sg[3])) < el[i_] + 0.8]
            if ys:
                feet.append(Z(min(ys)))
        if feet:
            zf = sorted(feet)[len(feet) // 2]
            if abs(zf - el[i_]) > 0.1:
                from .host import len_txt
                notes.append(f"{lv['name']} drawn at {len_txt(zf - el[g])} "
                             f"over the ground floor (model "
                             f"{len_txt(el[i_] - el[g])}) — set «Floor "
                             "height»")
    bands = EV._bands(arch, [], el)
    # frames drawn taller than their storey: the picture's storey is higher
    tall_ = {}
    for op, fr in got:
        z0_, z1_ = bands.get(op[1]["level"], (None, None))
        if z0_ is not None and Z(fr[3]) > z1_ - 0.1 and Z(fr[2]) < z1_:
            lvn = next((lv["name"] for lv in levels
                        if lv["id"] == op[1]["level"]), "")
            tall_[lvn] = max(tall_.get(lvn, 0.0), Z(fr[3]) - z0_)
    for lvn, h_ in tall_.items():
        from .host import len_txt
        notes.append(f"{lvn}: openings drawn up to {len_txt(h_)} — taller "
                     "than its storey: set «Floor height»")
    st = EV.new_stats()
    EV._apply_view(doc, arch, D, ops, seen, vert, horiz, arcs, [], {},
                   bands, st, know_arcs=bool(src.get("arcs_known")),
                   careful=not src.get("arcs_known"))
    rep = {"side": D, "jambs": f"{n} of {ne}",
           "scale": f"1 px = {s * 1000:.1f} mm"}
    if notes:
        rep["note"] = "; ".join(notes)
    EV.finish_stats(arch, st, rep)
    ref["fit"] = {"side": D, "block": block_of(ref),
                  "s": round(s, 6), "t": round(t, 4),
                  "y0": round(y0, 2), "z0": round(z0, 4),
                  "w": src["w"], "h": src["h"], "score": round(sc, 3)}
    return rep


def follow_all(doc, panel=None) -> list:
    """Every reference marked to be followed, followed: [(file name,
    report)]. The sides set by hand first, then the «auto» ones on the
    sides left."""
    out = []
    refs = [r for r in doc.get("ref_elev") or [] if r.get("follow", True)]
    if (doc.get("look") or {}).get("manual"):
        # 3.64.51: the elevations designed by hand: the design again
        from .lookstyle import apply_kit
        out.append(("Elevation design", apply_kit(doc, doc["look"])))
        refs = [r for r in refs if effective_side(r) != "perspective"]
    elif not any(effective_side(r) == "perspective" for r in refs):
        doc["look"] = {}             # 3.64.46: no perspective: no look
        from .lookstyle import is_look_roof
        doc["arch"]["structure"] = [e for e in doc["arch"]["structure"]
                                    if not is_look_roof(e)]
    # the sides set by hand first, then «auto»; the perspectives last
    refs.sort(key=lambda r: (effective_side(r) == "perspective",
                             r.get("side") == "auto"))
    used_by = {}
    for r in refs:
        name = os.path.basename(r["file"]) + (
            f" (Block {block_of(r)})" if block_of(r) != "all" else "")
        used = used_by.setdefault(block_of(r), set())
        try:
            rep = follow(doc, r, used=used)
        except Exception as e:  # noqa: BLE001
            from .host import log_error
            log_error("refelev.follow")
            rep = {"error": str(e)}
        if rep.get("side"):
            used.add(rep["side"])
        rep["_i"] = next((i for i, x in enumerate(doc.get("ref_elev") or [])
                          if x is r), -1)
        out.append((name, rep))
    return out


# ---- showing them beside the model ----------------------------------------------
def _cached_png(img, name) -> str:
    """The picture in IngeTrazo's texture cache (where reference images
    live): its path."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    data = bytes(ba)
    try:
        from core.texture import cache_image
        return str(cache_image(data, name + ".png", "imported"))
    except Exception:  # noqa: BLE001
        import hashlib
        import tempfile
        p = os.path.join(tempfile.gettempdir(), "c2i_ref_" +
                         hashlib.sha1(data).hexdigest()[:12] + ".png")
        with open(p, "wb") as f:
            f.write(data)
        return p


def hide(scene) -> int:
    planes = getattr(scene, "image_planes", None)
    if planes is None:
        return 0
    keep = [p for p in planes if not str(getattr(p, "name", "") or "")
            .startswith(REF_NAME)]
    n = len(planes) - len(keep)
    planes[:] = keep
    if n:
        scene.version += 1
    return n


def show(doc, scene, opacity=0.55, gap=0.8) -> list:
    """Each followed reference stood beside its side of the model (gap m
    out from it), at the scale found, half see-through. [(name, side)]."""
    from PySide6.QtGui import QVector3D
    from . import elevread as EV
    hide(scene)
    try:
        from core.image_plane import ImagePlane
        from core.layers import Layer
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in doc.get("ref_elev") or []:
        arch = _arch_for(doc, r)
        fit = r.get("fit")
        if not r.get("show", True) or not fit or \
                r.get("side") == "perspective":
            continue
        try:
            src = source(r["file"], int(r.get("page", 1) or 1))
        except Exception:  # noqa: BLE001
            continue
        D = fit["side"]
        f, rv = EV.dirs_of(arch)[D]
        s, t = fit["s"], fit["t"]
        k_ = src["w"] / max(fit["w"], 1)        # (the picture re-read)
        s, y0 = s / k_, fit["y0"] * k_
        ops, seen = EV._visible(arch, D)
        if not seen:
            continue
        dmin = min(d for _w, _a, _b, d in seen)
        d = dmin - gap
        u0 = t                        # the picture's left edge (x = 0)
        z_bot = fit["z0"] + s * (0.0 - y0)
        Wm, Hm = s * src["w"], s * src["h"]
        org = QVector3D(u0 * rv[0] + d * f[0], u0 * rv[1] + d * f[1], z_bot)
        uu = QVector3D(rv[0] * Wm, rv[1] * Wm, 0.0)
        vv = QVector3D(0.0, 0.0, Hm)
        bk_ = block_of(r)
        path = _cached_png(src["img"], "c2i_ref_" + D + (
            "_" + bk_ if bk_ != "all" else ""))
        name = f"{REF_NAME} — {D} — " + (f"Block {bk_} — " if bk_ != "all"
                                         else "") + os.path.basename(r['file'])
        im = ImagePlane(path, org, uu, vv, aspect=Hm / max(Wm, 1e-9),
                        name=name, opacity=opacity, layer=REF_LAYER,
                        locked=True)
        if scene.layer(REF_LAYER) is None:
            scene.layers.append(Layer(REF_LAYER))
        scene.image_planes.append(im)
        out.append((os.path.basename(r["file"]) + (
            f" (Block {bk_})" if bk_ != "all" else ""), D))
    if out:
        scene.version += 1
    return out


_EFF = {}


def is_photo(img) -> bool:
    """A photo or a render (most of it coloured, little white paper) —
    not a line drawing."""
    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    im = img.convertToFormat(QImage.Format_RGB32)
    if im.width() > 400:
        im = im.scaledToWidth(400, Qt.FastTransformation)
    w, h = im.width(), im.height()
    a = np.frombuffer(im.constBits(), dtype=np.uint8,
                      count=im.sizeInBytes()).reshape(
        h, im.bytesPerLine())[:, :w * 4].reshape(h, w, 4)[:, :, :3]
    a = a.astype(np.int16)
    mx, mn = a.max(axis=2), a.min(axis=2)
    paper = (mn > 225)
    sat = (mx - mn) > 40
    if paper.mean() < 0.45 and sat.mean() > 0.15:
        return True
    # (a render under a white sky: many colours all the same — a drawing
    # has a handful)
    q = (a // 16).reshape(-1, 3)
    n_col = len(np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]))
    return n_col > 450


def effective_side(ref) -> str:
    """The side a reference shows; «auto» on a photo or a render: a
    perspective (its look is what it gives)."""
    side = ref.get("side", "auto")
    if side != "auto" or kind_of(ref.get("file", "")) != "image":
        return side
    key = (ref["file"], os.path.getmtime(ref["file"])
           if os.path.isfile(ref["file"]) else 0)
    if key not in _EFF:
        try:
            from PySide6.QtGui import QImage
            img = QImage(ref["file"])
            _EFF[key] = "perspective" if not img.isNull() and \
                is_photo(img) else "auto"
        except Exception:  # noqa: BLE001
            _EFF[key] = "auto"
    return _EFF[key]


# ---- 3.64.50: the sides named on the model --------------------------------------
MARK_NAME = "C2I side mark"


def side_roles(doc) -> dict:
    """{side: "Front" / "Back" / "Left" / "Right"} — as seen standing at the
    front (where the cars drive in; else the main door's side)."""
    from . import elevread as EV
    try:
        from . import lookstyle as LS
        fr, _w, _o = LS.front_side(doc)
    except Exception:  # noqa: BLE001
        fr = None
    out = {}
    if fr is None:
        return out
    # standing in front, looking at the house (along -fr): the right hand
    rt = (-fr[1], fr[0])
    for D, (f, _r) in EV.DIRS.items():
        o = (-f[0], -f[1])                    # the side's outward way
        d = o[0] * fr[0] + o[1] * fr[1]
        if d > 0.7:
            out[D] = "Front"
        elif d < -0.7:
            out[D] = "Back"
        else:
            out[D] = "Right" if o[0] * rt[0] + o[1] * rt[1] > 0 else "Left"
    return out


def side_label(doc, D) -> str:
    r = side_roles(doc).get(D)
    base = SIDE_LABELS.get(D, D)
    return f"{base} ({r})" if r else base


def _mark_img(text):
    """The words of a side mark, with an arrow pointing at the house."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPen,
                               QPolygonF)
    W, H = 1400, 360
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(255, 255, 255, 235))
    p.setPen(QPen(QColor(200, 40, 40), 10))
    p.drawRoundedRect(QRectF(10, 10, W - 20, H - 20), 40, 40)
    # the arrow: pointing up the picture (towards the house)
    p.setBrush(QColor(200, 40, 40))
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(110, 60), QPointF(190, 200),
                             QPointF(140, 200), QPointF(140, 300),
                             QPointF(80, 300), QPointF(80, 200),
                             QPointF(30, 200)]))
    from PySide6.QtGui import QFontMetrics
    f = QFont("Arial", 1)
    f.setBold(True)
    px = 130
    while px > 40:                      # the words fit the box
        f.setPixelSize(px)
        if QFontMetrics(f).horizontalAdvance(text) <= W - 270:
            break
        px -= 6
    p.setFont(f)
    p.setPen(QColor(30, 30, 30))
    p.drawText(QRectF(220, 20, W - 240, H - 40),
               Qt.AlignVCenter | Qt.AlignLeft, text)
    p.end()
    return img


def hide_marks(scene) -> int:
    planes = getattr(scene, "image_planes", None)
    if planes is None:
        return 0
    keep = [p for p in planes if not str(getattr(p, "name", "") or "")
            .startswith(MARK_NAME)]
    n = len(planes) - len(keep)
    planes[:] = keep
    if n:
        scene.version += 1
    return n


def show_marks(doc, scene, gap=2.0) -> int:
    """Each side named on the ground beside it — «NORTH ELEVATION ·
    FRONT» with an arrow at the house — readable standing on that side
    (and in the plan). How many."""
    from PySide6.QtGui import QVector3D
    from . import elevread as EV
    hide_marks(scene)
    try:
        from core.image_plane import ImagePlane
        from core.layers import Layer
    except Exception:  # noqa: BLE001
        return 0
    arch = doc["arch"]
    xs = [v for w in arch["walls"] if "a" in w
          for v in (w["a"][0], w["b"][0])]
    ys = [v for w in arch["walls"] if "a" in w
          for v in (w["a"][1], w["b"][1])]
    if not xs:
        return 0
    from . import project as PJ
    el = PJ.elevations(arch)
    g = next((i for i, lv in enumerate(arch["levels"])
              if lv["kind"] == "ground"), 0)
    z = min(el[g], 0.0) + 0.03
    roles = side_roles(doc)
    n = 0
    for D, (f, r) in EV.DIRS.items():
        us = [x * r[0] + y * r[1] for x in (min(xs), max(xs))
              for y in (min(ys), max(ys))]
        ds = [x * f[0] + y * f[1] for x in (min(xs), max(xs))
              for y in (min(ys), max(ys))]
        uc = (min(us) + max(us)) / 2
        dfront = min(ds) - gap               # out from the house that way
        text = f"{D.upper()} ELEVATION" + (f" · {roles[D].upper()}"
                                           if D in roles else "")
        img = _mark_img(text)
        Wm = min(9.0, max(4.5, (max(us) - min(us)) * 0.6))
        Hm = Wm * img.height() / img.width()
        # bottom-left corner: on the far edge (away from the house),
        # the picture's «up» towards the house
        u0 = uc - Wm / 2
        d0 = dfront - Hm
        org = QVector3D(u0 * r[0] + d0 * f[0], u0 * r[1] + d0 * f[1], z)
        uu = QVector3D(r[0] * Wm, r[1] * Wm, 0.0)
        vv = QVector3D(f[0] * Hm, f[1] * Hm, 0.0)
        path = _cached_png(img, "c2i_mark_" + D)
        im = ImagePlane(path, org, uu, vv, aspect=Hm / Wm,
                        name=f"{MARK_NAME} — {D}", opacity=1.0,
                        layer=REF_LAYER, locked=True)
        if scene.layer(REF_LAYER) is None:
            scene.layers.append(Layer(REF_LAYER))
        scene.image_planes.append(im)
        n += 1
    if n:
        scene.version += 1
    return n


def side_map(doc, size=270):
    """A small plan of the ground floor with its four sides named (for
    the window): QImage."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, \
        QPolygonF
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    arch = doc["arch"]
    g = next((lv["id"] for lv in arch["levels"] if lv["kind"] == "ground"),
             None)
    try:
        from . import lookstyle as LS
        poly, _ws = LS._outline(arch, g)
    except Exception:  # noqa: BLE001
        poly = None
    try:        # 3.64.152: the whole built floor — every slab of the ground
        # level (the walls' contour alone gave one closed piece: the
        # ablution block, not the hall)
        from shapely.geometry import Polygon as _Pg
        from shapely.ops import unary_union as _uu
        sl_ = [_Pg(e_["corners"]).buffer(0) for e_ in arch["structure"]
               if e_.get("type") == "slab" and e_.get("level") == g
               and len(e_.get("corners") or []) >= 3]
        if sl_:
            u_ = _uu(sl_).buffer(0.3, join_style=2).buffer(-0.3,
                                                           join_style=2)
            if not u_.is_empty and (poly is None or u_.area > poly.area):
                poly = u_
    except Exception:  # noqa: BLE001
        pass
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    f = QFont("Arial", 1)
    f.setPixelSize(13)
    f.setBold(True)
    p.setFont(f)
    # 3.64.153: the site plan — the plot's outline and every block on it
    # (the built pieces of the ground floor, the largest «Block A», then
    # B, C …), each outlined and named
    plot_ = None
    try:
        from shapely.geometry import Polygon as _Pg2
        pc_ = [(q[0], q[1]) for q in
               ((arch.get("plot") or {}).get("corners") or [])
               if isinstance(q, (list, tuple)) and len(q) >= 2]
        if len(pc_) >= 3:
            plot_ = _Pg2(pc_).buffer(0)
    except Exception:  # noqa: BLE001
        plot_ = None
    blocks_ = []
    if poly is not None:
        blocks_ = sorted([q_ for q_ in getattr(poly, "geoms", [poly])
                          if q_.geom_type == "Polygon" and q_.area > 4.0],
                         key=lambda q_: -q_.area)
    if blocks_ or plot_ is not None:
        from shapely.ops import unary_union as _uu2
        allp_ = _uu2(blocks_ + ([plot_] if plot_ is not None
                                and not plot_.is_empty else []))
        x0, y0, x1, y1 = allp_.bounds
        k = (size - 150) / max(x1 - x0, y1 - y0, 1e-6)
        ox = (size - (x1 - x0) * k) / 2
        oy = (size - (y1 - y0) * k) / 2

        def T(x, y):
            return QPointF(ox + (x - x0) * k, size - (oy + (y - y0) * k))
        if plot_ is not None and not plot_.is_empty and \
                plot_.geom_type == "Polygon":
            p.setBrush(QColor(238, 242, 232))
            pen_ = QPen(QColor(110, 130, 100), 1.5)
            pen_.setStyle(Qt.DashLine)
            p.setPen(pen_)
            p.drawPolygon(QPolygonF([T(x, y) for x, y in
                                     list(plot_.exterior.coords)[:-1]]))
        lf = QFont("Arial", 1)
        lf.setPixelSize(11)
        lf.setBold(True)
        for n_, q_ in enumerate(blocks_):
            p.setBrush(QColor(225, 220, 205))
            p.setPen(QPen(QColor(60, 60, 60), 2))
            p.drawPolygon(QPolygonF([T(x, y) for x, y in
                                     list(q_.exterior.coords)[:-1]]))
            c_ = q_.representative_point()
            p.setFont(lf)
            p.setPen(QColor(30, 30, 30))
            nm_ = "Block " + (chr(65 + n_) if n_ < 26 else str(n_ + 1))
            pt_ = T(c_.x, c_.y)
            p.drawText(QRectF(pt_.x() - 36, pt_.y() - 8, 72, 16),
                       Qt.AlignCenter, nm_)
        p.setFont(f)
    roles = side_roles(doc)
    p.setPen(QColor(190, 30, 30))
    for D, (rect, al) in {
            "north": (QRectF(0, 4, size, 40), Qt.AlignHCenter | Qt.AlignTop),
            "south": (QRectF(0, size - 44, size, 40),
                      Qt.AlignHCenter | Qt.AlignBottom),
            "west": (QRectF(2, 0, 90, size), Qt.AlignVCenter | Qt.AlignLeft),
            "east": (QRectF(size - 92, 0, 90, size),
                     Qt.AlignVCenter | Qt.AlignRight)}.items():
        t = D.upper() + ("\n" + roles[D] if D in roles else "")
        p.drawText(rect, al | Qt.TextWordWrap, t)
    # the north arrow
    p.setBrush(QColor(30, 30, 30))
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(size - 22, 8), QPointF(size - 30, 30),
                             QPointF(size - 14, 30)]))
    p.end()
    return img
