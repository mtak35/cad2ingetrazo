# SPDX-License-Identifier: GPL-3.0-or-later
"""Shoring along the plot limits for a basement dig: a row of bored piles
(contiguous or secant) with an RCC capping beam over them, or steel sheet
piles — from the ground down past the lowest basement by an embedment.

Settings: ``shoring`` (on/off), ``shoring_type`` («piles», «secant»,
«sheet»), ``shoring_d`` (the pile's diameter), ``shoring_embed`` (how far
under the lowest basement's floor it goes).
"""
from __future__ import annotations

import math

TYPES = [("piles", "Contiguous bored piles + capping beam"),
         ("secant", "Secant piles + capping beam"),
         ("sheet", "Steel sheet piles")]
LABELS = dict(TYPES)
PILE = (0.62, 0.62, 0.60, 1.0)
CAP = (0.70, 0.71, 0.72, 1.0)
STEEL = (0.42, 0.44, 0.47, 1.0)


def _ring(plot_pts, inset):
    """The plot outline moved in by ``inset``: [(x, y)] counter-clockwise."""
    from shapely.geometry import Polygon
    p = Polygon(plot_pts)
    if not p.is_valid:
        p = p.buffer(0)
    q = p.buffer(-inset, join_style=2)
    if q.is_empty:
        return []
    if q.geom_type != "Polygon":
        q = max(q.geoms, key=lambda g: g.area)
    pts = list(q.exterior.coords)[:-1]
    a = sum(p_[0] * n[1] - n[0] * p_[1] for p_, n in zip(pts, pts[1:] + pts[:1]))
    return pts if a > 0 else pts[::-1]


def _prism(loop, z0, z1, col):
    fs = [{"loop": [(x, y, z0) for x, y in reversed(loop)], "holes": [],
           "color": col},
          {"loop": [(x, y, z1) for x, y in loop], "holes": [], "color": col}]
    for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1]):
        fs.append({"loop": [(x0, y0, z0), (x1, y1, z0), (x1, y1, z1),
                            (x0, y0, z1)], "holes": [], "color": col})
    return fs


def _circle(c, r, n=12):
    return [(c[0] + r * math.cos(2 * math.pi * k / n),
             c[1] + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _band(a, b, w):
    """A strip ``w`` wide along a→b (on its left: inside the ccw ring)."""
    L = math.dist(a, b)
    if L < 1e-6:
        return None
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    nx, ny = -uy, ux
    return [a, b, (b[0] + nx * w, b[1] + ny * w), (a[0] + nx * w, a[1] + ny * w)]


def sides(plot_pts, z_top, z_bot, kind="piles", d=0.6096,
          out_=False) -> list:
    """[(side no, length, [faces])] — the shoring along each side of
    ``plot_pts``: inside it (the plot limits), or just outside it
    (``out_``: round the basement's outer walls)."""
    sg = -1.0 if out_ else 1.0
    d = min(max(float(d), 0.3), 1.5)
    out = []
    if z_top - z_bot < 0.5 or not plot_pts or len(plot_pts) < 3:
        return out
    if kind == "sheet":
        ring = _ring(plot_pts, sg * 0.15)
        for k, (a, b) in enumerate(zip(ring, ring[1:] + ring[:1]), 1):
            L = math.dist(a, b)
            if L < 0.3:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            nx, ny = -uy, ux
            n = max(1, int(L / 0.6))
            fs = []
            for i in range(n):          # trapezoid pans, in and out
                s0, s1 = i * L / n, (i + 1) * L / n
                off = 0.0 if i % 2 == 0 else 0.15
                p0 = (a[0] + ux * s0 + nx * off, a[1] + uy * s0 + ny * off)
                p1 = (a[0] + ux * s1 + nx * off, a[1] + uy * s1 + ny * off)
                band = _band(p0, p1, 0.012)
                if band:
                    fs += _prism(band, z_bot, z_top, STEEL)
                if i:                   # the web between two pans
                    q0 = (a[0] + ux * s0, a[1] + uy * s0)
                    q1 = (q0[0] + nx * 0.15, q0[1] + ny * 0.15)
                    web = _band(q0, q1, 0.012)
                    if web:
                        fs += _prism(web, z_bot, z_top, STEEL)
            out.append((k, L, fs))
        return out
    step = d * (0.8 if kind == "secant" else 1.05)
    ring = _ring(plot_pts, sg * (d / 2 + 0.05))
    capw = d + 0.15
    for k, (a, b) in enumerate(zip(ring, ring[1:] + ring[:1]), 1):
        L = math.dist(a, b)
        if L < d:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        n = max(1, int(round(L / step)))
        fs = []
        for i in range(n):
            s = (i + 0.5) * L / n
            c = (a[0] + ux * s, a[1] + uy * s)
            fs += _prism(_circle(c, d / 2), z_bot, z_top - 0.6, PILE)
        nx, ny = -uy, ux                 # the capping beam over them
        a2 = (a[0] - nx * capw / 2, a[1] - ny * capw / 2)
        b2 = (b[0] - nx * capw / 2, b[1] - ny * capw / 2)
        band = _band(a2, b2, capw)
        if band:
            fs += _prism(band, z_top - 0.6, z_top, CAP)
        out.append((k, L, fs))
    return out


def build(doc, elevations_) -> list:
    """[(side no, length, faces, lowest basement id)] or [] (no shoring, no
    basement or no plot)."""
    st = doc["settings"]
    arch = doc["arch"]
    if not st.get("shoring"):
        return []
    levels = arch["levels"]
    bs = [i for i, lv in enumerate(levels) if lv.get("kind") == "basement"]
    if not bs:
        return []
    low = min(bs, key=lambda i: elevations_[i])
    along = st.get("shoring_on", "plot")
    pts = []
    if along == "walls":            # round the basement's outer (RCC) walls
        from . import slabedges as SE
        ws = [w for w in arch["walls"]
              if w["level"] in {levels[i]["id"] for i in bs}]
        fp = SE._footprint(ws)
        if fp is not None and not fp.is_empty:
            g_ = max(getattr(fp, "geoms", [fp]), key=lambda q: q.area)
            pts = [tuple(p) for p in list(g_.exterior.coords)[:-1]]
    else:
        plot = arch.get("plot") or {}
        pts = [tuple(p[:2]) for p in plot.get("corners") or []]
    if not pts:
        return []
    g = next((i for i, lv in enumerate(levels) if lv.get("kind") == "ground"),
             None)
    # the natural ground (0.0), or the ground floor when it sits lower
    z_top = min(elevations_[g], 0.0) if g is not None else 0.0
    z_bot = elevations_[low] - float(st.get("shoring_embed", 3.048))
    return [(k, L, fs, levels[low]["id"]) for k, L, fs in
            sides(pts, z_top, z_bot, st.get("shoring_type", "piles"),
                  st.get("shoring_d", 0.6096), along == "walls")]
