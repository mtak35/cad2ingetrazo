"""3.64.36: the window designs (from his pictures) — glazing bars and
lights inside a window's frame: double-hung, colonial grid, grid
casement, prairie, diamond lattice, X-pattern transom, sunburst fanlight,
gothic Y-tracery, and the modern black ones (side lights, top transoms,
glass over a bottom panel, a black grid of lights)."""
from __future__ import annotations

import math

#: the modern slim black aluminium designs (their frame: black)
MODERN_WINDOWS = ("side_lights", "transom_top", "bottom_panel",
                  "modern_grid")
#: the traditional ones with glazing bars (their frame: white uPVC)
GRID_WINDOWS = ("double_hung", "colonial", "grid", "diamond", "x_transom",
                "sunburst", "gothic", "prairie")
DESIGNS = [("double_hung", "Double-hung (two sashes)"),
           ("colonial", "Colonial — six over six (glazing bars)"),
           ("grid", "Grid casement (glazing bars)"),
           ("prairie", "Prairie (border lights)"),
           ("diamond", "Diamond lattice"),
           ("x_transom", "Casement + X-pattern transom"),
           ("sunburst", "Casement + sunburst fanlight"),
           ("gothic", "Gothic (Y-tracery, lancet grid)"),
           ("side_lights", "Modern — picture window + side lights"),
           ("transom_top", "Modern — casements + top transoms"),
           ("bottom_panel", "Modern — glass over a bottom panel"),
           ("modern_grid", "Modern — black grid of lights")]
BAR_W = 0.022                  # m: a glazing bar's face (muntin)


def _box(p0, u, n, sa, sb, ca, cb, za, zb, color):
    from .structure import _box as B
    return B(p0, u, n, sa, sb, ca, cb, za, zb, color)


def _bar(p0, u, n, sa, za, sb, zb, wd, ca, cb, color) -> list:
    """A bar from (sa, za) to (sb, zb) in the wall's plane — at any slope
    (a diagonal glazing bar), wd wide, ca..cb across."""
    ds, dz = sb - sa, zb - za
    L = math.hypot(ds, dz)
    if L < 1e-4:
        return []
    qs, qz = -dz / L * wd / 2, ds / L * wd / 2

    def P(i, c, j):
        s_ = sa + ds * i + qs * (2 * j - 1)
        z_ = za + dz * i + qz * (2 * j - 1)
        return (p0[0] + u[0] * s_ + n[0] * c, p0[1] + u[1] * s_ + n[1] * c,
                z_)
    c = [P(0, ca, 0), P(1, ca, 0), P(1, cb, 0), P(0, cb, 0),
         P(0, ca, 1), P(1, ca, 1), P(1, cb, 1), P(0, cb, 1)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    return [{"loop": [c[i] for i in q], "holes": [], "color": color}
            for q in quads]


def _grid(p0, u, n, x0, x1, za, zb, cols, rows, F, c=0.0) -> list:
    """Glazing bars dividing a light into cols × rows panes."""
    out = []
    for i in range(1, cols):
        x = x0 + (x1 - x0) * i / cols
        out.append(_box(p0, u, n, x - BAR_W / 2, x + BAR_W / 2,
                        c - 0.012, c + 0.012, za, zb, F))
    for j in range(1, rows):
        z = za + (zb - za) * j / rows
        out.append(_box(p0, u, n, x0, x1, c - 0.012, c + 0.012,
                        z - BAR_W / 2, z + BAR_W / 2, F))
    return out


def _sash(p0, u, n, a0, a1, za, zb, c, F, G, r=0.045) -> list:
    """A sash: its rails and stiles round a pane, at c across."""
    return [_box(p0, u, n, a0, a1, c - 0.015, c + 0.015, za, za + r, F),
            _box(p0, u, n, a0, a1, c - 0.015, c + 0.015, zb - r, zb, F),
            _box(p0, u, n, a0, a0 + r, c - 0.015, c + 0.015, za + r, zb - r,
                 F),
            _box(p0, u, n, a1 - r, a1, c - 0.015, c + 0.015, za + r, zb - r,
                 F),
            _box(p0, u, n, a0 + r, a1 - r, c - 0.004, c + 0.004, za + r,
                 zb - r, G)]


def _clip_line(x0, x1, zb, zt, xi, m):
    """The piece of the line z = zb + m·(x − xi) inside the light."""
    pts = []
    for x in (x0, x1):
        z = zb + m * (x - xi)
        if zb - 1e-6 <= z <= zt + 1e-6:
            pts.append((x, z))
    for z in (zb, zt):
        x = xi + (z - zb) / m
        if x0 - 1e-6 <= x <= x1 + 1e-6:
            pts.append((x, z))
    pts = sorted({(round(a, 5), round(b, 5)) for a, b in pts})
    if len(pts) >= 2 and math.dist(pts[0], pts[-1]) > 0.03:
        return pts[0], pts[-1]
    return None


def window_design(style, p0, u, n, x0, x1, zb, zt2, F, G) -> list:
    """The parts (boxes: lists of faces) of a window design inside its
    frame x0..x1, zb..zt2. [] for a style it doesn't draw."""
    W_, H_ = x1 - x0, zt2 - zb
    if W_ < 0.1 or H_ < 0.1:
        return []
    mid = (x0 + x1) / 2
    out = []
    if style in ("double_hung", "colonial"):
        zm = zb + H_ / 2
        out += _sash(p0, u, n, x0, x1, zb, zm + 0.02, 0.018, F, G)
        out += _sash(p0, u, n, x0, x1, zm - 0.02, zt2, -0.018, F, G)
        if style == "colonial":      # six over six
            cols = 3 if W_ > 0.75 else 2
            out += _grid(p0, u, n, x0 + 0.045, x1 - 0.045, zb + 0.045,
                         zm - 0.025, cols, 2, F, 0.018)
            out += _grid(p0, u, n, x0 + 0.045, x1 - 0.045, zm + 0.025,
                         zt2 - 0.045, cols, 2, F, -0.018)
        return out
    if style == "grid":              # two casements, each 2 × n panes
        for a0, a1 in ((x0, mid), (mid, x1)):
            out += _sash(p0, u, n, a0, a1, zb, zt2, 0.0, F, G, 0.04)
            out += _grid(p0, u, n, a0 + 0.04, a1 - 0.04, zb + 0.04,
                         zt2 - 0.04, 2, max(2, int(round(H_ / 0.4))), F)
        return out
    if style == "prairie":           # a border of narrow lights
        out.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zb, zt2, G))
        e = min(0.12, W_ / 6, H_ / 6)
        for x in (x0 + e, x1 - e):
            out.append(_box(p0, u, n, x - BAR_W / 2, x + BAR_W / 2, -0.012,
                            0.012, zb, zt2, F))
        for z in (zb + e, zt2 - e):
            out.append(_box(p0, u, n, x0, x1, -0.012, 0.012,
                            z - BAR_W / 2, z + BAR_W / 2, F))
        return out
    if style == "diamond":           # a diamond lattice over fixed glass
        out.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zb, zt2, G))
        k = max(2, int(round(W_ / 0.22)))
        dx = W_ / k
        m = 1.4
        span = int(math.ceil(H_ / (dx * m))) + k + 1
        for sg in (1, -1):
            for i in range(-span, span + 1):
                seg_ = _clip_line(x0, x1, zb, zt2, x0 + i * dx, m * sg)
                if seg_:
                    (sa, za), (sb, zb_) = seg_
                    out.append(_bar(p0, u, n, sa, za, sb, zb_, 0.016,
                                    -0.01, 0.01, F))
        return out
    if style in ("x_transom", "sunburst", "transom_top"):
        zt_ = zt2 - min(0.45, H_ * 0.3)          # the transom bar
        out.append(_box(p0, u, n, x0, x1, -0.03, 0.03, zt_ - 0.025,
                        zt_ + 0.025, F))
        for a0, a1 in ((x0, mid), (mid, x1)):    # casements below
            out += _sash(p0, u, n, a0, a1, zb, zt_ - 0.025, 0.0, F, G,
                         0.04 if style != "transom_top" else 0.035)
        za_ = zt_ + 0.025
        out.append(_box(p0, u, n, x0, x1, -0.005, 0.005, za_, zt2, G))
        if style == "x_transom":
            k = max(1, int(round(W_ / 0.9)))
            for i in range(k):
                a0 = x0 + W_ * i / k
                a1 = x0 + W_ * (i + 1) / k
                if i:
                    out.append(_box(p0, u, n, a0 - 0.02, a0 + 0.02, -0.012,
                                    0.012, za_, zt2, F))
                out.append(_bar(p0, u, n, a0, za_, a1, zt2, 0.02, -0.01,
                                0.01, F))
                out.append(_bar(p0, u, n, a0, zt2, a1, za_, 0.02, -0.01,
                                0.01, F))
        elif style == "sunburst":    # rays from the bar's middle
            out.append(_box(p0, u, n, mid - 0.08, mid + 0.08, -0.012, 0.012,
                            za_, za_ + 0.06, F))
            for i in range(1, 6):
                ang = math.pi * i / 6
                dxs, dzs = math.cos(ang), math.sin(ang)
                tt = min((W_ / 2) / abs(dxs) if abs(dxs) > 1e-6 else 9.0,
                         (zt2 - za_) / dzs)
                out.append(_bar(p0, u, n, mid, za_, mid + dxs * tt,
                                za_ + dzs * tt, 0.02, -0.01, 0.01, F))
        else:                        # modern: the top lights in three
            for i in (1, 2):
                x = x0 + W_ * i / 3
                out.append(_box(p0, u, n, x - 0.02, x + 0.02, -0.02, 0.02,
                                za_, zt2, F))
        return out
    if style == "gothic":            # Y-tracery: two lights, crossing bars
        out.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zb, zt2, G))
        zy = max(zt2 - W_ / 2, zb + H_ / 3)
        out.append(_box(p0, u, n, mid - 0.02, mid + 0.02, -0.014, 0.014, zb,
                        zy, F))
        out.append(_bar(p0, u, n, mid, zy, x0, zt2, 0.03, -0.014, 0.014, F))
        out.append(_bar(p0, u, n, mid, zy, x1, zt2, 0.03, -0.014, 0.014, F))
        out += _grid(p0, u, n, x0, x1, zb, zy, 4,
                     max(2, int(round((zy - zb) / 0.3))), F)
        return out
    if style == "side_lights":       # a picture light, side casements
        e = min(max(W_ * 0.22, 0.3), 0.6, W_ / 3)
        for x in (x0 + e, x1 - e):
            out.append(_box(p0, u, n, x - 0.025, x + 0.025, -0.03, 0.03, zb,
                            zt2, F))
        out.append(_box(p0, u, n, x0 + e, x1 - e, -0.005, 0.005, zb, zt2,
                        G))
        for a0, a1 in ((x0, x0 + e - 0.025), (x1 - e + 0.025, x1)):
            out += _sash(p0, u, n, a0, a1, zb, zt2, 0.0, F, G, 0.035)
        return out
    if style == "bottom_panel":      # glass over a solid bottom panel
        zp = zb + min(0.6, H_ * 0.3)
        out.append(_box(p0, u, n, x0, x1, -0.02, 0.02, zb, zp, F))
        out.append(_box(p0, u, n, x0, x1, -0.03, 0.03, zp, zp + 0.04, F))
        zt_ = zt2 - min(0.4, H_ * 0.22)
        out.append(_box(p0, u, n, x0, x1, -0.03, 0.03, zt_ - 0.02,
                        zt_ + 0.02, F))
        out.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zp + 0.04,
                        zt_ - 0.02, G))
        out.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zt_ + 0.02, zt2,
                        G))
        if W_ > 1.0:
            out.append(_box(p0, u, n, mid - 0.02, mid + 0.02, -0.03, 0.03,
                            zp + 0.04, zt2, F))
        return out
    if style == "modern_grid":       # a black grid of lights
        out.append(_box(p0, u, n, x0, x1, -0.005, 0.005, zb, zt2, G))
        cols = max(2, int(round(W_ / 0.55)))
        rows = max(2, int(round(H_ / 0.55)))
        for i in range(1, cols):
            x = x0 + W_ * i / cols
            out.append(_box(p0, u, n, x - 0.02, x + 0.02, -0.025, 0.025, zb,
                            zt2, F))
        for j in range(1, rows):
            z = zb + H_ * j / rows
            out.append(_box(p0, u, n, x0, x1, -0.025, 0.025, z - 0.02,
                            z + 0.02, F))
        return out
    return []
