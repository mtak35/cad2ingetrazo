# SPDX-License-Identifier: GPL-3.0-or-later
"""The CAD plan's own linework in the plan views: every line of the level's
CAD floor, drawn over the cut model with the line weight and line type the
CAD gives it (by entity, by layer or by block; LTSCALE applied) — the plan
reads as the drawing it came from. Layers turned off or frozen in the CAD
stay out. Only in a level's plan view, never in 3D."""
from __future__ import annotations

import math

from .host import KEY, PREFIX_PLAN_CUT

_cache: dict = {}
INK = (25, 27, 30)


def _level_of(doc, name):
    for lv in doc["arch"]["levels"]:
        if lv["name"] == name:
            return lv
    return None


def lines_of(doc, lid):
    """[(weight mm, pattern m [dash, −gap…], N×4 array of x0 y0 x1 y1)] of
    the level's CAD floor, on the model (metres)."""
    import numpy as np

    from . import cadread
    how = doc["imports"].get(lid)
    if not how or not how.get("file"):
        return []
    raw = cadread.read(how["file"], how.get("unit"))
    if not raw.get("seg_style"):
        return []
    region = how.get("region")
    base = cadread.base_point(cadread.crop(raw, region),
                              how.get("base", "origin"),
                              (how.get("bx", 0.0), how.get("by", 0.0)))
    k = raw["unit"]
    bx, by = base
    ix, iy = how.get("ix", 0.0), how.get("iy", 0.0)
    rot = math.radians(float(how.get("rot", 0.0)))
    c, s = math.cos(rot), math.sin(rot)
    hidden = set(raw.get("hidden_layers") or ())
    if doc["settings"].get("cars_lib", True):
        # the library's cars stand in the bays: the CAD's car symbols go
        import re
        rx = re.compile(r"(^|[^A-Z])CARS?($|[^A-Z])|VEHIC", re.I)
        hidden |= {n for n in raw.get("layers") or () if rx.search(n)}
    segs = np.array([sg[:4] for sg in raw["segs"]], dtype=float)
    sty = np.array(raw["seg_style"], dtype=int)
    keep = np.array([sg[4] not in hidden for sg in raw["segs"]], dtype=bool)
    if region:
        x0, y0, x1, y1 = (float(v) for v in region)
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        mx = (segs[:, 0] + segs[:, 2]) / 2
        my = (segs[:, 1] + segs[:, 3]) / 2
        keep &= (mx >= x0) & (mx <= x1) & (my >= y0) & (my <= y1)
    segs, sty = segs[keep], sty[keep]

    def T(x, y):
        dx, dy = (x - bx) * k, (y - by) * k
        return c * dx - s * dy + ix, s * dx + c * dy + iy
    ax, ay = T(segs[:, 0], segs[:, 1])
    bx2, by2 = T(segs[:, 2], segs[:, 3])
    pts = np.stack([ax, ay, bx2, by2], axis=1)
    out = []
    for i, (w, pat) in enumerate(raw["styles"]):
        m = sty == i
        if m.any():
            out.append((float(w), [float(v) * k for v in pat], pts[m]))
    return out


def _pattern(pat, ppm, width):
    """A Qt dash pattern (in pen widths) from a CAD one (metres), or None
    for a solid line (no pattern, or too fine to see at this zoom)."""
    if not pat:
        return None
    seq = []
    for v in pat:
        L = abs(v) * ppm
        seq.append((v >= 0, max(L, 1.0)))
    if sum(L for _d, L in seq) < 6.0:
        return None
    out = []
    want_dash = True
    for dash, L in seq:
        if dash != want_dash:                 # two dashes / gaps in a row
            out.append(1.0 / width)
            want_dash = not want_dash
        out.append(L / width)
        want_dash = not want_dash
    if len(out) % 2:
        out.append(1.0 / width)
    return out


def draw(viewport, painter) -> None:
    scene = viewport.scene
    sp = scene.active_section() if hasattr(scene, "active_section") else None
    name = str(getattr(sp, "name", "") or "")
    if not name.startswith(PREFIX_PLAN_CUT):
        return
    name = name[len(PREFIX_PLAN_CUT):]
    raw = (getattr(scene, "plugin_data", {}) or {}).get(KEY)
    if not raw:
        return
    from . import project as PJ
    doc = PJ.load(raw)
    if not doc["settings"].get("cad_lines", True):
        return
    lv = _level_of(doc, name)
    if lv is None:
        return
    how = doc["imports"].get(lv["id"]) or {}
    key = (lv["id"], bool(doc["settings"].get("cars_lib", True)),
           str(how.get("file")), str(how.get("region")),
           how.get("bx"), how.get("by"), how.get("ix"), how.get("iy"),
           how.get("rot"), how.get("mtime"))
    if key not in _cache:
        if len(_cache) > 8:
            _cache.clear()
        try:
            _cache[key] = lines_of(doc, lv["id"])
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("linework.lines_of")
            _cache[key] = []
    sets = _cache[key]
    if not sets:
        return
    import numpy as np
    from PySide6.QtCore import QLineF, Qt
    from PySide6.QtGui import QColor, QPen
    elev = PJ.elevations(doc["arch"])
    z = next((elev[i] for i, l_ in enumerate(doc["arch"]["levels"])
              if l_["id"] == lv["id"]), 0.0) + 0.03
    # pixels per metre here (for the dash lengths)
    pr = np.array([[0.0, 0.0, z], [1.0, 0.0, z]])
    px, py, ok = viewport._project_px(pr)
    ppm = float(math.hypot(px[1] - px[0], py[1] - py[0])) if ok.all() else 0
    W, H = viewport.width(), viewport.height()
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    for w_mm, pat, arr in sets:
        n = len(arr)
        P = np.empty((2 * n, 3))
        P[0::2, 0], P[0::2, 1] = arr[:, 0], arr[:, 1]
        P[1::2, 0], P[1::2, 1] = arr[:, 2], arr[:, 3]
        P[:, 2] = z
        X, Y, OK = viewport._project_px(P)
        X, Y, OK = X.reshape(-1, 2), Y.reshape(-1, 2), OK.reshape(-1, 2)
        vis = OK.all(axis=1) & ~(((X < 0).all(axis=1)) | ((X > W).all(axis=1))
                                 | ((Y < 0).all(axis=1)) | ((Y > H).all(axis=1)))
        if not vis.any():
            continue
        width = max(0.5, w_mm * 4.0)
        pen = QPen(QColor(*INK), width)
        pen.setCapStyle(Qt.FlatCap)
        dp = _pattern(pat, ppm, width)
        if dp:
            pen.setDashPattern(dp)
        painter.setPen(pen)
        Xv, Yv = X[vis], Y[vis]
        painter.drawLines([QLineF(float(a), float(b), float(c_), float(d))
                           for a, b, c_, d in zip(Xv[:, 0], Yv[:, 0],
                                                  Xv[:, 1], Yv[:, 1])])
    painter.restore()
