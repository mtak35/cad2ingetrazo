# SPDX-License-Identifier: GPL-3.0-or-later
"""3.64.36: the boundary wall designs from his pictures — built along the
wall's centre line, bay by bay between the piers:

- «picket»: brick piers, a low wall, timber picket panels with an arched
  top in each bay;
- «spear»: a low wall with a wrought-iron spear-top railing;
- «lamp_piers»: a low wall, a wrought-iron crest railing (scrolls on top)
  and a lamp on each pillar;
- «scallop»: the wall's top dipping in a curve between the piers;
- «cement_rings» / «cement_sunburst» / «cement_lattice»: ornamental
  cement panels — a raised frame in each bay round a motif, both faces;
- «brick_panels»: exposed brick panels in plastered frames.
"""
from __future__ import annotations

import math

from .engine import windesign as WD
from .engine.structure import _box

#: the designs with something over a low wall (their own parts, not the
#: railing kinds)
OVER_CUSTOM = ("picket", "spear", "lamp_piers")
#: the designs that put piers along the wall
PIER_STYLES = ("picket", "spear", "lamp_piers", "scallop", "cement_rings",
               "cement_sunburst", "cement_lattice", "brick_panels")
STYLES = [("picket", "Brick piers + timber picket panels (arched)"),
          ("spear", "Low wall + wrought-iron spear railing"),
          ("lamp_piers", "Lamp pillars + wrought-iron crest railing"),
          ("scallop", "Scalloped wall dipping between piers"),
          ("cement_rings", "Ornamental cement panels — rings"),
          ("cement_sunburst", "Ornamental cement panels — sunburst"),
          ("cement_lattice", "Ornamental cement panels — lattice"),
          ("brick_panels", "Brick panels in plastered frames")]
WOOD = (0.55, 0.37, 0.21)
IRON = (0.08, 0.08, 0.09)
TRIM = (0.90, 0.89, 0.86)
BRICK = (0.66, 0.36, 0.27)
LAMP_GLASS = (0.98, 0.93, 0.70)


def _flat(parts):
    return [f for p in parts for f in p]


def _bays(L, gap):
    """The bays of a straight run L long (as the piers are set out)."""
    k_ = int(L // gap)
    nb = max(k_ + (1 if L % gap > 0.6 else 0), 1)
    return [(L * i / nb, L * (i + 1) / nb) for i in range(nb)]


def _runs(line):
    """(p0, u, n, L) of each straight piece of the centre line."""
    out = []
    for ln in getattr(line, "geoms", [line]):
        if ln.geom_type != "LineString":
            continue
        cs = list(ln.coords)
        for a, b in zip(cs, cs[1:]):
            L = math.dist(a[:2], b[:2])
            if L < 0.3:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            out.append(((a[0], a[1]), u, (-u[1], u[0]), L))
    return out


def ornaments(style, line, z0, ztop, h, t, gap, pier) -> list:
    """[(name, faces, colour)] of the design along ``line`` (the wall's
    centre): ztop the low wall's top (with its coping), h the wall's
    full height over z0, pier the pillar's size (kept clear)."""
    out = []
    for k, (p0, u, n, L) in enumerate(_runs(line)):
        for j, (s0, s1) in enumerate(_bays(L, gap)):
            a = s0 + pier / 2 + 0.03      # clear of the pillars (and
            b = s1 - pier / 2 - 0.03      # the gates' at the run's ends)
            if b - a < 0.3:
                continue
            nm = f"Boundary {style} {k + 1}.{j + 1}"
            try:
                parts = _bay(style, p0, u, n, a, b, z0, ztop, h, t)
            except Exception:  # noqa: BLE001
                parts = []
            for col, ps in parts:
                if ps:
                    out.append((nm, _flat(ps), col))
    return out


def _bay(style, p0, u, n, a, b, z0, ztop, h, t):
    """[(colour, parts)] of one bay a..b along the run."""
    W_ = b - a
    top = z0 + h
    if style == "picket":
        rise = min(0.35, W_ * 0.15)
        base = top - rise - 0.05
        rails = [_box(p0, u, n, a, b, -0.03, 0.03, ztop + 0.12,
                      ztop + 0.19, WOOD),
                 _box(p0, u, n, a, b, -0.03, 0.03, base - 0.25,
                      base - 0.18, WOOD)]
        pk = []
        k = max(int(W_ / 0.11), 2)
        for i in range(k):
            s = a + (i + 0.5) * W_ / k
            zt_ = base + rise * math.sin(math.pi * (s - a) / W_)
            pk.append(_box(p0, u, n, s - 0.035, s + 0.035, 0.0, 0.022,
                           ztop, zt_, WOOD))
        return [(WOOD, rails + pk)]
    if style in ("spear", "lamp_piers"):
        zr = top - (0.25 if style == "lamp_piers" else 0.12)
        rails = [_box(p0, u, n, a, b, -0.015, 0.015, ztop + 0.08,
                      ztop + 0.11, IRON),
                 _box(p0, u, n, a, b, -0.015, 0.015, zr - 0.03, zr, IRON)]
        bars = []
        k = max(int(W_ / 0.12), 2)
        for i in range(k):
            s = a + (i + 0.5) * W_ / k
            tip = top if style == "spear" else zr + 0.10
            bars.append(_box(p0, u, n, s - 0.01, s + 0.01, -0.01, 0.01,
                             ztop + 0.02, tip - 0.06, IRON))
            # the spear head: a diamond in the wall's plane
            bars += [WD._bar(p0, u, n, s - 0.025, tip - 0.06, s, tip, 0.012,
                             -0.008, 0.008, IRON),
                     WD._bar(p0, u, n, s + 0.025, tip - 0.06, s, tip, 0.012,
                             -0.008, 0.008, IRON),
                     _box(p0, u, n, s - 0.025, s + 0.025, -0.01, 0.01,
                          tip - 0.075, tip - 0.06, IRON)]
        if style == "lamp_piers":      # the crest: scrolls over the rail
            for i in range(max(int(W_ / 0.5), 1)):
                c_ = a + (i + 0.5) * W_ / max(int(W_ / 0.5), 1)
                r_ = 0.09
                m_ = 12
                pts = [(c_ + r_ * math.cos(math.pi * q / m_),
                        zr + 0.02 + r_ * math.sin(math.pi * q / m_))
                       for q in range(m_ + 1)]
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    bars.append(WD._bar(p0, u, n, x1, y1, x2, y2, 0.015,
                                        -0.008, 0.008, IRON))
        return [(IRON, rails + bars)]
    if style == "scallop":
        dip = min(0.45, W_ * 0.18)
        k = max(int(W_ / 0.08), 4)
        ps = []
        for i in range(k):
            s_a = a + W_ * i / k
            s_b = a + W_ * (i + 1) / k
            sm = (s_a + s_b) / 2
            zt_ = top - dip * math.sin(math.pi * (sm - a) / W_)
            ps.append(_box(p0, u, n, s_a, s_b, -t / 2, t / 2, ztop, zt_,
                           None))
            ps.append(_box(p0, u, n, s_a, s_b, -t / 2 - 0.03, t / 2 + 0.03,
                           zt_, zt_ + 0.06, None))
        return [(None, ps)]
    if style.startswith("cement_") or style == "brick_panels":
        za, zb = z0 + 0.35, top - 0.25
        if zb - za < 0.4:
            return []
        out = []
        frame = []
        for c0, c1 in ((t / 2, t / 2 + 0.025), (-t / 2 - 0.025, -t / 2)):
            fw = 0.07
            frame += [_box(p0, u, n, a + 0.08, b - 0.08, c0, c1, za, za + fw,
                           TRIM),
                      _box(p0, u, n, a + 0.08, b - 0.08, c0, c1, zb - fw, zb,
                           TRIM),
                      _box(p0, u, n, a + 0.08, a + 0.08 + fw, c0, c1,
                           za + fw, zb - fw, TRIM),
                      _box(p0, u, n, b - 0.08 - fw, b - 0.08, c0, c1,
                           za + fw, zb - fw, TRIM)]
        out.append((TRIM, frame))
        x0, x1 = a + 0.08 + 0.07, b - 0.08 - 0.07
        y0, y1 = za + 0.07, zb - 0.07
        if style == "brick_panels":
            out.append((BRICK, [
                _box(p0, u, n, x0, x1, t / 2, t / 2 + 0.008, y0, y1, BRICK),
                _box(p0, u, n, x0, x1, -t / 2 - 0.008, -t / 2, y0, y1,
                     BRICK)]))
            return out
        mot = []
        cx, cz = (x0 + x1) / 2, (y0 + y1) / 2
        r = min(x1 - x0, y1 - y0) / 2 - 0.05
        for c0, c1 in ((t / 2, t / 2 + 0.02), (-t / 2 - 0.02, -t / 2)):
            if style == "cement_rings":   # a big ring, small ones round it
                rb = r * 0.85
                rings = [(cx, cz, rb)]
                sm = min(r * 0.45, ((x1 - x0) / 2 - rb - 0.12) / 2)
                if sm > 0.08:
                    for sx in (-1, 1):
                        rings.append((cx + sx * (rb + 0.06 + sm), cz, sm))
                for (rx, rz, rr) in rings:
                    m_ = 28
                    pts = [(rx + rr * math.cos(2 * math.pi * q / m_),
                            rz + rr * math.sin(2 * math.pi * q / m_))
                           for q in range(m_ + 1)]
                    for (s1_, z1_), (s2_, z2_) in zip(pts, pts[1:]):
                        e_ = 0.012 / max(math.dist((s1_, z1_),
                                                   (s2_, z2_)), 1e-6)
                        mot.append(WD._bar(    # (a touch long: no gaps)
                            p0, u, n, s1_ - (s2_ - s1_) * e_,
                            z1_ - (z2_ - z1_) * e_, s2_ + (s2_ - s1_) * e_,
                            z2_ + (z2_ - z1_) * e_, 0.05, c0, c1, TRIM))
            elif style == "cement_sunburst":   # rays from the foot
                hub = (cx, y0)
                for i in range(1, 10):
                    ang = math.pi * i / 10
                    dx_, dz_ = math.cos(ang), math.sin(ang)
                    tt = min((x1 - x0) / 2 / abs(dx_) if abs(dx_) > 1e-6
                             else 9.0, (y1 - y0) / dz_)
                    mot.append(WD._bar(p0, u, n, hub[0], hub[1],
                                       hub[0] + dx_ * tt, hub[1] + dz_ * tt,
                                       0.05, c0, c1, TRIM))
                m_ = 10
                pts = [(cx + 0.2 * math.cos(math.pi * q / m_),
                        y0 + 0.2 * math.sin(math.pi * q / m_))
                       for q in range(m_ + 1)]
                for (s1_, z1_), (s2_, z2_) in zip(pts, pts[1:]):
                    mot.append(WD._bar(p0, u, n, s1_, z1_, s2_, z2_, 0.05,
                                       c0, c1, TRIM))
            else:                          # a diagonal lattice
                dx = 0.25
                m = 1.0
                span = int((x1 - x0 + y1 - y0) / dx) + 2
                for sg in (1, -1):
                    for i in range(-span, span + 1):
                        seg_ = WD._clip_line(x0, x1, y0, y1, x0 + i * dx,
                                             m * sg)
                        if seg_:
                            (sa, za_), (sb, zb_) = seg_
                            mot.append(WD._bar(p0, u, n, sa, za_, sb, zb_,
                                               0.04, c0, c1, TRIM))
        out.append((TRIM, mot))
        return out
    return []


def lamp(c, z, s) -> list:
    """A lantern on a pillar's cap at c (its top z), s the pillar size."""
    p0, u, n = (c[0], c[1]), (1.0, 0.0), (0.0, 1.0)
    w = min(0.22, s * 0.6)
    parts = [_box(p0, u, n, -0.03, 0.03, -0.03, 0.03, z, z + 0.12, IRON),
             _box(p0, u, n, -w / 2, w / 2, -w / 2, w / 2, z + 0.12,
                  z + 0.15, IRON),
             _box(p0, u, n, -w / 2 + 0.02, w / 2 - 0.02, -w / 2 + 0.02,
                  w / 2 - 0.02, z + 0.15, z + 0.42, LAMP_GLASS),
             _box(p0, u, n, -w / 2 - 0.02, w / 2 + 0.02, -w / 2 - 0.02,
                  w / 2 + 0.02, z + 0.42, z + 0.46, IRON),
             _box(p0, u, n, -0.04, 0.04, -0.04, 0.04, z + 0.46, z + 0.55,
                  IRON)]
    glass = [parts.pop(2)]
    return [(_flat(parts), IRON), (_flat(glass), LAMP_GLASS)]
