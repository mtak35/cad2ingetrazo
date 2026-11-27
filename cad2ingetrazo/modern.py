"""3.64.53: the modern massing of a perspective, made from the model at
every rebuild (so it follows the plans):

- a deep fascia at the true top of every volume (up to its parapet's top),
  one solid per height so its corners are mitred and join; the edges of
  the terraces as thick light slab edges;
- a projecting dark frame (a "C" frame: the top slab and two legs) round
  the front's foremost upper bay, with down-lights in its soffit;
- an inclined cladding panel on a front corner: full height, carried above
  the roof, its inner edge raked (wider at the top) with a dark reveal
  along the rake — the inclined corner of a modern front;
- the main door's bay clad (warm stone / timber) up its full height, and a
  dark slab canopy with down-lights over the door when nothing covers it.

Switches in ``doc["look"]``: fascia, slab_edges, frame_box, incline_panel,
entry_clad; colours trim (dark), clad (panel), stone (warm), wall.
"""
from __future__ import annotations

import math

FASCIA_D = 0.30        # the fascia's projection
FASCIA_H = 0.55        # … its depth (height)
EDGE_D = 0.12          # a terrace's slab edge
EDGE_H = 0.40
FRAME_D = 0.75         # the dark frame's projection
FRAME_T = 0.30         # … its legs' width
PANEL_D = 0.36         # the inclined panel's projection (before the fascia)
PANEL_UP = 0.60        # … carried above the roof
CLAD_D = 0.05
CANOPY_D = 1.20
GLOW = (1.0, 0.86, 0.55, 1.0)


def _c4(c, dflt=(0.5, 0.5, 0.5)):
    c = list(c or dflt)[:3]
    return (float(c[0]), float(c[1]), float(c[2]), 1.0)


# ---- solids -------------------------------------------------------------------
def _orient(faces, centre):
    """Faces of a convex-ish solid turned outward (away from its centre)."""
    out = []
    for f in faces:
        loop = f["loop"]
        n = [0.0, 0.0, 0.0]
        for p, q in zip(loop, loop[1:] + loop[:1]):
            n[0] += (p[1] - q[1]) * (p[2] + q[2])
            n[1] += (p[2] - q[2]) * (p[0] + q[0])
            n[2] += (p[0] - q[0]) * (p[1] + q[1])
        c = [sum(p[k] for p in loop) / len(loop) for k in range(3)]
        if sum(n[k] * (c[k] - centre[k]) for k in range(3)) < 0:
            f = dict(f, loop=list(reversed(loop)))
        out.append(f)
    return out


def _prism(loop, v, col) -> list:
    """A convex loop (3D points) swept by vector v: its faces, outward."""
    a = list(loop)
    b = [(p[0] + v[0], p[1] + v[1], p[2] + v[2]) for p in a]
    fs = [{"loop": a, "holes": [], "color": col},
          {"loop": b, "holes": [], "color": col}]
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        fs.append({"loop": [a[i], a[j], b[j], b[i]], "holes": [],
                   "color": col})
    pts = a + b
    cen = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    return _orient(fs, cen)


class _Frame:
    """A wall's frame: origin, u along, n outward (both unit, in plan)."""

    def __init__(self, p, u, n):
        self.p, self.u, self.n = p, u, n

    def P(self, s, a, z):
        return (self.p[0] + self.u[0] * s + self.n[0] * a,
                self.p[1] + self.u[1] * s + self.n[1] * a, z)

    def box(self, s0, s1, a0, a1, z0, z1, col) -> list:
        if s1 - s0 < 1e-3 or a1 - a0 < 1e-3 or z1 - z0 < 1e-3:
            return []
        loop = [self.P(s0, a0, z0), self.P(s1, a0, z0), self.P(s1, a1, z0),
                self.P(s0, a1, z0)]
        return _prism(loop, (0.0, 0.0, z1 - z0), col)

    def plate(self, quad_sz, a0, a1, col) -> list:
        """A flat convex shape in the wall's plane ((s, z) points), a0..a1
        out from it."""
        loop = [self.P(s, a0, z) for s, z in quad_sz]
        return _prism(loop, (self.n[0] * (a1 - a0), self.n[1] * (a1 - a0),
                             0.0), col)

    def holed(self, poly_sz, a0, a1, col) -> list:
        """A flat shape with holes in the wall's plane (a shapely polygon in
        (s, z)), a0..a1 out from it."""
        from shapely.geometry.polygon import orient

        from .engine import walls as W
        out = []
        for g in getattr(poly_sz, "geoms", [poly_sz]):
            if g.geom_type != "Polygon" or g.area < 1e-4:
                continue
            g = orient(g, 1.0)
            piece = {"outer": [tuple(c) for c in g.exterior.coords[:-1]],
                     "holes": [[tuple(c) for c in h.coords[:-1]]
                               for h in g.interiors]}
            # (x, y, z) of solid() = (s, z, a); (u, Z, n) handedness decides
            # whether the loops stay outward
            ux, uy = self.u
            nx, ny = self.n
            flip = (ux * ny - uy * nx) > 0   # u × Z = n ⇔ u × n points down
            for f in W.solid(piece, a0, a1):
                d = dict(f) if isinstance(f, dict) else {"loop": f,
                                                         "holes": []}

                def mp(loop):
                    pts = [self.P(x, zz, y) for x, y, zz in loop]
                    return list(reversed(pts)) if flip else pts
                out.append({"loop": mp(d["loop"]),
                            "holes": [mp(h) for h in d.get("holes") or []],
                            "color": col})
        return out


def _solid(poly, z0, z1, col) -> list:
    """A plan shape (shapely) raised z0..z1."""
    from shapely.geometry.polygon import orient

    from .engine import walls as W
    out = []
    for g in getattr(poly, "geoms", [poly]):
        if g.geom_type != "Polygon" or g.area < 2e-3:
            continue
        g = orient(g.simplify(0.003), 1.0)
        piece = {"outer": [tuple(c) for c in g.exterior.coords[:-1]],
                 "holes": [[tuple(c) for c in h.coords[:-1]]
                           for h in g.interiors]}
        for f in W.solid(piece, z0, z1):
            d = dict(f) if isinstance(f, dict) else {"loop": f, "holes": []}
            d["color"] = col
            out.append(d)
    return out


def _lights(fr, s_list, a, z, r=0.07) -> list:
    """Down-lights: small warm discs under a soffit at z."""
    out = []
    for s in s_list:
        c = fr.P(s, a, z)
        ring = [(c[0] + r * math.cos(2 * math.pi * k / 10),
                 c[1] + r * math.sin(2 * math.pi * k / 10), z - 0.012)
                for k in range(10)]
        out += _prism(ring, (0.0, 0.0, 0.012), GLOW)
    return out


# ---- the model's volumes ------------------------------------------------------------
def _ctx(doc):
    from . import lookstyle as LS
    from . import project as PJ
    arch = doc["arch"]
    levels = arch["levels"]
    el = PJ.elevations(arch)
    order = sorted(range(len(levels)), key=lambda i: el[i])
    g = next((i for i, lv in enumerate(levels) if lv["kind"] == "ground"), 0)
    polys = {}
    for i in order:
        if el[i] < el[g] - 1e-6:
            continue
        p, _ws = LS._outline(arch, levels[i]["id"])
        if p is not None and not p.is_empty:
            polys[i] = p
    return arch, levels, el, order, g, polys


def _regions(doc) -> dict:
    """3.64.54: every volume's top as the roof slab over it draws it (its
    slab on the level above, out to the walls' outer face), small notches
    closed — a clean outline, so the fascia runs round it unbroken; the
    walls' contour where no slab is drawn."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    arch, levels, el, order, g, polys = _ctx(doc)
    out = {}
    for i, poly in polys.items():
        above = [j for j in order if el[j] > el[i] + 0.5]
        reg = None
        if above:
            jid = levels[above[0]]["id"]
            ps = []
            for e in arch["structure"]:
                if e.get("type") != "slab" or e.get("level") != jid or \
                        len(e.get("corners") or []) < 3:
                    continue
                try:
                    p = Polygon([tuple(c[:2]) for c in e["corners"]],
                                [[tuple(c[:2]) for c in h]
                                 for h in e.get("holes") or []
                                 if len(h) >= 3]).buffer(0)
                except Exception:  # noqa: BLE001
                    continue
                if p.area > 1.0:
                    ps.append(Polygon(p.exterior) if p.geom_type ==
                              "Polygon" else p)
            if ps:
                # out to the walls' outer face (a slab stops at their
                # centre or inner face)
                reg = unary_union(ps).buffer(0.12, join_style=2)
                # only where this volume stands (a slab of the floor above
                # may run past it: that part is not this volume's top)
                # 3.64.101: the top roof slab is the roof: its own
                # outline (it may run out past the walls), the fascia
                # follows it; a lower volume's top stays by its walls
                reach = 2.5 if len(above) == 1 else 0.35
                reg = reg.intersection(poly.buffer(reach, join_style=2))
        if reg is None or reg.is_empty or reg.area < 1.0:
            reg = poly
        reg = reg.buffer(0.25, join_style=2).buffer(-0.25, join_style=2)
        reg = reg.buffer(-0.25, join_style=2).buffer(0.25, join_style=2)
        if reg.geom_type == "MultiPolygon":
            reg = unary_union([Polygon(p.exterior) for p in reg.geoms
                               if p.area > 1.0])
        elif reg.geom_type == "Polygon":
            reg = Polygon(reg.exterior)
        if not reg.is_empty:
            out[i] = reg
    return out


def _edges(poly) -> list:
    """The outline's edges, CCW: [(p, q, u, n_out, L)]."""
    from shapely.geometry.polygon import orient
    out = []
    for g in getattr(poly, "geoms", [poly]):
        if g.geom_type != "Polygon":
            continue
        g = orient(g.simplify(0.05), 1.0)
        pts = list(g.exterior.coords)[:-1]
        for k in range(len(pts)):
            p, q = pts[k], pts[(k + 1) % len(pts)]
            L = math.dist(p, q)
            if L < 0.2:
                continue
            u = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
            out.append((p, q, u, (u[1], -u[0]), L))   # right of CCW: out
    return out


def _parapet_h(arch, levels, j, p, q) -> float:
    """The parapet standing on an edge (on the level above it, j): its
    height, or 0."""
    from shapely.geometry import LineString
    if j is None:
        return 0.0
    ln = LineString([p, q])
    best = 0.0
    for w in arch["walls"]:
        if w["level"] != levels[j]["id"] or "a" not in w or w.get("rail"):
            continue
        if not str(w.get("name", "")).lower().startswith(("roof parapet",
                                                          "roof edge")):
            continue
        m = LineString([w["a"][:2], w["b"][:2]])
        if m.length < 0.3 or ln.distance(m.interpolate(0.5, True)) > 0.35:
            continue
        h = w.get("height")
        h = float(h) if isinstance(h, (int, float)) else 1.0
        best = max(best, h)
    return best


def _railed(arch, levels, j, p, q) -> bool:
    from shapely.geometry import LineString
    if j is None:
        return False
    ln = LineString([p, q])
    return any(w["level"] == levels[j]["id"] and w.get("rail") and "a" in w
               and ln.distance(LineString([w["a"][:2], w["b"][:2]])
                               .interpolate(0.5, True)) < 0.5
               for w in arch["walls"])


def tops(doc) -> list:
    """Every volume's exposed top edge: [(i, p, q, u, n, L, z_top, kind)] —
    kind "roof" (a fascia: up to its parapet's top) or "terrace" (a railed
    slab edge)."""
    from shapely.ops import unary_union
    from .lookstyle import is_look_roof
    arch, levels, el, order, g, polys = _ctx(doc)
    roofed = {e["level"] for e in arch["structure"]
              if is_look_roof(e) and not e.get("annex")}
    regs = _regions(doc)
    out = []
    for i, poly in regs.items():
        if levels[i]["id"] in roofed:
            continue
        above = [j for j in order if el[j] > el[i] + 0.5]
        j = above[0] if above else None
        up = unary_union([polys[k] for k in above if k in polys]) \
            if any(k in polys for k in above) else None
        z1 = el[i] + float(levels[i]["height"])
        mine = []
        for p, q, u, n, L in _edges(poly):
            mid = ((p[0] + q[0]) / 2 + n[0] * 0.05,
                   (p[1] + q[1]) / 2 + n[1] * 0.05)
            if up is not None:
                from shapely.geometry import LineString, Point
                # covered: the volume above stands on this edge
                ln = LineString([(p[0] - n[0] * 0.08, p[1] - n[1] * 0.08),
                                 (q[0] - n[0] * 0.08, q[1] - n[1] * 0.08)])
                cov = ln.intersection(up.buffer(0.02)).length / max(L, 1e-9)
                if cov > 0.5 or up.contains(Point(mid)):
                    continue
            ph = _parapet_h(arch, levels, j, p, q)
            if up is not None:
                # 3.64.54: a lower volume's top (a terrace, a low roof):
                # all of it one light slab edge, at its parapet's top
                zt = z1 if _railed(arch, levels, j, p, q) else z1 + ph
                try:        # 3.64.103: down to the floor finish there
                    from .project import floor_offset_at
                    off = float(floor_offset_at(doc, levels[j]["id"], mid))
                    if off < 0 and ph <= 0.05:
                        zt = el[j] + off
                except Exception:  # noqa: BLE001
                    pass
                out.append((i, p, q, u, n, L, zt, "terrace"))
            else:
                mine.append((i, p, q, u, n, L, z1 + ph, "roof", ph))
        # the top roof: an edge without a parapet where the rest has one
        # is a stair core's or a court's side (no fascia: it would float)
        if mine:
            walled = sum(e[5] for e in mine if e[8] > 0.05)
            total = sum(e[5] for e in mine)
            for e in mine:
                if e[8] <= 0.05 and walled > 0.5 * total and e[5] < 4.0:
                    continue
                out.append(e[:8])
    return out


def ring_parts(doc, d_roof, d_edge=EDGE_D, roof_only=False,
               slab_edges=True) -> list:
    """The bands round the volumes' tops, d out from their faces: one
    mitred plan shape per volume and height, so the corners join —
    [(shape, z_top, kind)]."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    arch, levels, el, order, g, polys = _ctx(doc)
    regs = _regions(doc)
    groups = {}
    for i, p, q, u, n, L, zt, kind in tops(doc):
        if kind == "terrace" and (roof_only or not slab_edges):
            continue
        d = d_roof if kind == "roof" else d_edge
        R = d + 0.35        # across: the band and a margin
        E = d + 0.02         # along: just the mitred corner, no stub
        zone = Polygon([(p[0] - u[0] * E, p[1] - u[1] * E),
                        (q[0] + u[0] * E, q[1] + u[1] * E),
                        (q[0] + u[0] * E + n[0] * R,
                         q[1] + u[1] * E + n[1] * R),
                        (p[0] - u[0] * E + n[0] * R,
                         p[1] - u[1] * E + n[1] * R)])
        key = (i, kind, round(zt / 0.05) * 0.05)
        groups.setdefault(key, []).append(zone)
    out = []
    taken = {}
    for (i, kind, zt), zones in sorted(groups.items(),
                                       key=lambda kv: -kv[0][2]):
        poly = regs[i]
        d = d_roof if kind == "roof" else d_edge
        band = poly.buffer(d, join_style=2, mitre_limit=4.0).difference(
            poly.buffer(-0.01, join_style=2))
        # what stands above it is not its top
        above = [k for k in polys if el[k] > el[i] + 0.5]
        if above:
            band = band.difference(unary_union(
                [polys[k] for k in above]).buffer(0.02, join_style=2))
        part = band.intersection(unary_union(zones))
        if taken.get(i) is not None:
            part = part.difference(taken[i])
        if part.is_empty:
            continue
        taken[i] = part if taken.get(i) is None else taken[i].union(part)
        out.append((part, zt, kind))
    return out


def _fascias(doc, dark, light, slab_edges) -> list:
    """The fascias (dark, at each volume's top) and slab edges (light):
    one mitred solid per height, so their corners join."""
    look = doc.get("look") or {}
    FD = float(look.get("fascia_d", FASCIA_D) or FASCIA_D)
    FH = float(look.get("fascia_h", FASCIA_H) or FASCIA_H)
    out = []
    st_ = doc.get("settings") or {}
    # 3.64.102: the bands stop at the top of the floor finish (not 2" /
    # 4" over it)
    ft = float(st_.get("finish_t", 0.0508) or 0.0) \
        if st_.get("finish_on", True) else 0.0
    for part, zt, kind in ring_parts(doc, FD, slab_edges=slab_edges):
        if kind == "roof":
            out += _solid(part, zt - FH, zt + ft, dark)
        else:
            out += _solid(part, zt - EDGE_H + ft, zt + ft, light)
    return out


# ---- the front ---------------------------------------------------------------------
def _front_edges(doc, fr):
    """The top-most volumes' edges facing the front, with their tops:
    [(i, p, q, u, n, L, z_top)]."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    _a, _l, _e, _o, _g, polys = _ctx(doc)
    body = unary_union(list(polys.values())) if polys else None
    out = []
    for i, p, q, u, n, L, zt, kind in tops(doc):
        if kind != "roof" or L < 1.0:
            continue
        if n[0] * fr[0] + n[1] * fr[1] < 0.85:
            continue
        # seen from the front: nothing of the house stands before it
        if body is not None and any(LineString([
                (x + fr[0] * 0.3, y + fr[1] * 0.3),
                (x + fr[0] * 40.0, y + fr[1] * 40.0)]).intersects(body)
                for x, y in ((p[0] * (1 - t) + q[0] * t,
                              p[1] * (1 - t) + q[1] * t)
                             for t in (0.25, 0.5, 0.75))):
            continue
        out.append((i, p, q, u, n, L, zt))
    return out


def _openings_on(arch, p, q, u, levels_ids=None) -> list:
    """The openings in walls along an edge: [(s0, s1)] along it."""
    from shapely.geometry import LineString

    from .engine import walls as W
    ln = LineString([p, q])
    ws = {w["id"]: w for w in arch["walls"]}
    out = []
    for o in arch["openings"]:
        w = ws.get(o["wall"])
        if w is None or "a" not in w or (levels_ids and
                                         w["level"] not in levels_ids):
            continue
        m = LineString([w["a"][:2], w["b"][:2]])
        if ln.distance(m.interpolate(0.5, True)) > float(w["t"]) + 0.3:
            continue
        seg = W.centre(w)
        if seg.kind != "line":
            continue
        c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
        s = (c[0] - p[0]) * u[0] + (c[1] - p[1]) * u[1]
        hw = float(o["w"]) / 2
        out.append((s - hw, s + hw))
    for w in arch["walls"]:              # a corner window's glazed legs
        if "a" not in w or not str(w.get("name", "")).lower().startswith(
                "corner window") or (levels_ids and
                                     w["level"] not in levels_ids):
            continue
        m = LineString([w["a"][:2], w["b"][:2]])
        if ln.distance(m.interpolate(0.5, True)) > float(w["t"]) + 0.3:
            continue
        sa = [(x - p[0]) * u[0] + (y - p[1]) * u[1]
              for x, y in (w["a"][:2], w["b"][:2])]
        out.append((min(sa) - 0.1, max(sa) + 0.1))
    return out


def _frame_box(doc, fr, dark) -> tuple:
    """The dark "C" frame round the front's foremost upper bay."""
    from shapely.geometry import Point
    arch, levels, el, order, g, polys = _ctx(doc)
    cands = [e for e in _front_edges(doc, fr) if e[0] != g and
             2.0 <= e[5] <= 9.0]
    if not cands:
        cands = [e for e in _front_edges(doc, fr) if 2.0 <= e[5] <= 9.0]
    if not cands:
        return [], None
    best = max(cands, key=lambda e: ((e[1][0] + e[2][0]) * fr[0] +
                                     (e[1][1] + e[2][1]) * fr[1]) / 2)
    i, p, q, u, n, L, zt = best
    f = _Frame(p, u, n)
    poly = _regions(doc).get(i, polys[i])
    z0 = el[i] - 0.25
    out = []
    legs = []
    for s_end, sg in ((0.0, -1.0), (L, 1.0)):
        # a convex end: the leg wraps the corner (outside the edge); a
        # concave one: it stands on the edge
        probe = f.P(s_end + sg * 0.2, -0.2, 0.0)
        concave = poly.contains(Point(probe[0], probe[1]))
        if concave:
            a, b = (s_end, s_end + FRAME_T) if sg < 0 else \
                (s_end - FRAME_T, s_end)
        else:
            a, b = (s_end - FRAME_T, s_end) if sg < 0 else \
                (s_end, s_end + FRAME_T)
        legs.append((a, b))
        out += f.box(a, b, -0.02, FRAME_D, z0, zt + 0.05, dark)
    s0, s1 = min(legs[0][0], legs[1][0]), max(legs[0][1], legs[1][1])
    out += f.box(s0, s1, -0.02, FRAME_D, zt - FASCIA_H - 0.05, zt + 0.05,
                 dark)
    k = max(1, int((L - 0.6) / 1.1))
    out += _lights(f, [0.3 + (L - 0.6) * (j + 0.5) / k for j in range(k)],
                   FRAME_D * 0.55, zt - FASCIA_H - 0.05)
    return out, best


def _incline_panel(doc, fr, clad, dark, skip=None) -> list:
    """An inclined cladding panel on a front corner, from the ground to
    above the roof, its inner edge raked."""
    from shapely.geometry import Point
    arch, levels, el, order, g, polys = _ctx(doc)
    gpoly = polys.get(g)
    if gpoly is None:
        return []
    gedge = gpoly.boundary
    regs = _regions(doc)
    cands = []
    for e in _front_edges(doc, fr):
        i, p, q, u, n, L, zt = e
        if skip is not None and e[:3] == skip[:3]:
            continue
        # it stands on the ground: the ground floor's face runs under it
        on = all(gedge.distance(Point(p[0] + u[0] * L * t,
                                      p[1] + u[1] * L * t)) < 0.25
                 for t in (0.15, 0.5, 0.85)) if i != g else True
        if not on:
            continue
        ops = _openings_on(arch, p, q, u)
        for s_end, inward in ((0.0, 1.0), (L, -1.0)):
            probe = (p[0] + u[0] * (s_end - inward * 0.2) - n[0] * 0.2,
                     p[1] + u[1] * (s_end - inward * 0.2) - n[1] * 0.2)
            if regs.get(i, polys[i]).contains(Point(probe)):
                continue                       # a concave end
            free = L
            for a, b in ops:
                d_ = (a - s_end) if inward > 0 else (s_end - b)
                if d_ > -0.05:
                    free = min(free, max(0.0, d_ - 0.15))
                elif (a < s_end < b):
                    free = 0.0
            if free < 0.55:
                continue
            far = ((p[0] + q[0]) * fr[0] + (p[1] + q[1]) * fr[1]) / 2
            cands.append((free, far, e, s_end, inward))
    if not cands:
        return []
    free, _far, e, s_end, inward = max(cands, key=lambda c: (
        min(c[0], 1.6), c[2][5]))
    i, p, q, u, n, L, zt = e
    corner = (p[0] + u[0] * s_end, p[1] + u[1] * s_end)
    v = (u[0] * inward, u[1] * inward)        # from the corner inwards
    f = _Frame(corner, v, n)
    wt = min(1.6, free)
    wb = max(0.45, wt * 0.55)
    z0, z1 = el[g], zt + PANEL_UP
    out = f.plate([(0.0, z0), (wb, z0), (wt, z1), (0.0, z1)], -0.01,
                  PANEL_D, clad)
    # its stone courses: a fine joint every 0.6 m
    jc = _c4([c * 0.78 for c in clad[:3]])
    z = z0 + 0.6
    while z < z1 - 0.1:
        w_ = wb + (wt - wb) * (z - z0) / (z1 - z0)
        out += f.plate([(0.0, z), (w_, z), (w_, z + 0.02), (0.0, z + 0.02)],
                       PANEL_D - 0.002, PANEL_D + 0.006, jc)
        z += 0.6
    # the dark reveal along the rake
    rk = [(wb, z0), (wb + 0.07, z0), (wt + 0.07, z1), (wt, z1)]
    out += f.plate(rk, -0.01, PANEL_D * 0.6, dark)
    # it wraps the corner: a return on the side face
    side = _Frame(corner, (-n[0], -n[1]), (-v[0], -v[1]))
    out += side.box(-PANEL_D, 0.30, -0.01, 0.12, z0, z1, clad)
    return out


def _entry(doc, fr, warm, dark, canopy=True) -> list:
    """The main door's bay clad up its height; a slab canopy over it."""
    from shapely.geometry import LineString, Point, box as sbox

    from . import lookstyle as LS
    from .engine import walls as W
    arch, levels, el, order, g, polys = _ctx(doc)
    _fr, w, o = LS.front_side(doc, LS._outer_walls(arch))
    if w is None or g not in polys:
        return []
    seg = W.centre(w)
    if seg.kind != "line":
        return []
    t = float(w["t"])
    u = seg.u
    nl = (-u[1], u[0])
    c = seg.at(float(o["pos"]) / max(seg.L, 1e-9))
    probe = (c[0] + nl[0] * (t / 2 + 0.25), c[1] + nl[1] * (t / 2 + 0.25))
    n = (-nl[0], -nl[1]) if polys[g].buffer(-0.05).contains(Point(probe)) \
        else nl
    f = _Frame(seg.p0, u, n)
    s = float(o["pos"])
    hw = float(o["w"]) / 2
    zs = el[g] + float(o.get("sill", 0.0) or 0.0)
    zh = zs + float(o["h"])
    # up to the top of what stands on this face
    z1 = el[g] + float(levels[g]["height"])
    for i in order:
        if i in polys and el[i] > el[g] + 0.5 and \
                polys[i].boundary.distance(Point(c)) < t + 0.3:
            z1 = el[i] + float(levels[i]["height"])
    s0, s1 = max(0.0, s - hw - 0.6), min(seg.L, s + hw + 0.6)
    pan = sbox(s0, el[g], s1, z1).difference(
        sbox(s - hw, zs, s + hw, zh))
    # the windows of the bay stay open
    for o2 in arch["openings"]:
        w2 = next((x for x in arch["walls"] if x["id"] == o2["wall"]), None)
        if w2 is None or o2 is o or "a" not in w2:
            continue
        seg2 = W.centre(w2)
        if seg2.kind != "line" or LineString([seg.p0, seg.p1]).distance(
                Point(seg2.at(float(o2["pos"]) / max(seg2.L, 1e-9)))) > 0.3:
            continue
        c2 = seg2.at(float(o2["pos"]) / max(seg2.L, 1e-9))
        s2 = (c2[0] - seg.p0[0]) * u[0] + (c2[1] - seg.p0[1]) * u[1]
        lv = next((k for k, lv_ in enumerate(levels)
                   if lv_["id"] == w2["level"]), g)
        z2 = el[lv] + float(o2.get("sill", 0.0) or 0.0)
        pan = pan.difference(sbox(s2 - float(o2["w"]) / 2, z2,
                                  s2 + float(o2["w"]) / 2,
                                  z2 + float(o2["h"])))
    out = f.holed(pan, t / 2 - 0.005, t / 2 + CLAD_D, warm)
    if canopy:
        from .ornament import _covered
        if not _covered(arch, w, o, polys[g], el, g):
            a0, a1 = t / 2, t / 2 + CANOPY_D
            out += f.box(s - hw - 0.5, s + hw + 0.5, a0, a1, zh + 0.35,
                         zh + 0.55, dark)
            out += _lights(f, [s - hw * 0.5, s + hw * 0.5], a0 + 0.7,
                           zh + 0.35)
    return out


def faces(doc) -> list:
    """The modern massing's pieces: [(name, faces)]."""
    look = doc.get("look") or {}
    if not look or look.get("style") in (None, "", "none"):
        return []
    from .host import log_error
    dark = _c4(look.get("trim"), (0.25, 0.25, 0.27))
    wall = look.get("wall") or (0.92, 0.92, 0.90)
    light = _c4([min(1.0, float(v) * 1.05 + 0.02) for v in wall[:3]])
    clad = _c4(look.get("clad"), (0.80, 0.80, 0.78))
    warm = _c4(look.get("stone"), (0.62, 0.52, 0.40))
    out = []
    try:
        # 3.64.165: a mosque built to its elevations has NO slab edge /
        # fascia standing out of the wall at the floor lines (the drawn
        # elevations show none: one plain face from floor to floor)
        if (look.get("fascia") or look.get("slab_edges")) \
                and not look.get("mosque"):
            fs = _fascias(doc, dark, light, bool(look.get("slab_edges")))
            if not look.get("fascia"):
                fs = [f for f in fs if f["color"] != dark]
            if fs:
                out.append(("Look fascias", fs))
    except Exception:  # noqa: BLE001
        log_error("modern._fascias")
    from . import lookstyle as LS
    try:
        fr, _w, _o = LS.front_side(doc, LS._outer_walls(doc["arch"]))
    except Exception:  # noqa: BLE001
        fr = None
    if fr is None:
        return out
    used = None
    if look.get("frame_box"):
        try:
            fs, used = _frame_box(doc, fr, dark)
            if fs:
                out.append(("Look front frame", fs))
        except Exception:  # noqa: BLE001
            log_error("modern._frame_box")
    if look.get("incline_panel"):
        try:
            fs = _incline_panel(doc, fr, clad, dark, skip=used)
            if fs:
                out.append(("Look inclined corner", fs))
        except Exception:  # noqa: BLE001
            log_error("modern._incline_panel")
    if look.get("entry_clad"):
        try:
            fs = _entry(doc, fr, warm, dark,
                        canopy=look.get("entrance_canopy", True) or
                        look.get("style") == "modern")
            if fs:
                out.append(("Look entrance cladding", fs))
        except Exception:  # noqa: BLE001
            log_error("modern._entry")
    return out


# ---- the picture -------------------------------------------------------------------
def has_inclines(img) -> bool:
    """Does the perspective show raked (inclined) edges — long straight
    lines leaning 4..15° off the vertical (a raked fin, a sloped panel)?"""
    import numpy as np
    from PySide6.QtGui import QImage
    im = img.convertToFormat(QImage.Format_RGB32)
    w, h = im.width(), im.height()
    if w < 50 or h < 50:
        return False
    k = max(1, int(max(w, h) / 600))
    a = np.frombuffer(im.constBits(), dtype=np.uint8,
                      count=im.sizeInBytes()).reshape(
        h, im.bytesPerLine())[:, :w * 4].reshape(h, w, 4)[::k, ::k, :3]
    lum = a.astype(np.float32).mean(axis=2)
    H, Wd = lum.shape
    gx = np.abs(np.diff(lum, axis=1))[:-1, :]
    gy = np.abs(np.diff(lum, axis=0))[:, :-1]
    edge = (gx > 28) & (gx > 1.5 * gy)
    ys = np.arange(edge.shape[0])

    def best(tan_):
        sh = np.round(ys * tan_).astype(int)
        acc = np.zeros(Wd + 2 * H + 4, dtype=np.int32)
        r, c = np.nonzero(edge)
        np.add.at(acc, c - sh[r] + H + 2, 1)
        # a straight run is a column (± 1) in the sheared picture
        return int(np.convolve(acc, np.ones(2, dtype=np.int32),
                               "same").max())
    base = best(0.0)
    # a raked line stands out of the picture's texture: a sharp peak at one
    # lean among the leans round it (a busy picture scores alike at all)
    for sg in (1, -1):
        vs = [best(sg * math.tan(math.radians(d)))
              for d in (4, 5, 6, 7, 8, 10, 12, 15)]
        med = sorted(vs)[len(vs) // 2]
        top = max(vs)
        if top >= 0.15 * H and top >= 0.3 * base and top >= 1.35 * med:
            return True
    return False
