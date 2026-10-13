# SPDX-License-Identifier: GPL-3.0-or-later
"""Section box (as Revit's): the 3D model cut to a box — what lies outside
it not shown, what crosses it cut at its faces — to look into a floor, a
stair, a corner.

``doc["settings"]["section_box"]`` = [x0, y0, z0, x1, y1, z1] (metres) or
None. The cut is made when the model is made again (every group's faces
clipped to the box; groups wholly outside emptied), so it is undoable and
saved with the project; the box's edges are drawn over the 3D view.
"""
from __future__ import annotations

import math

EDGE = (230, 120, 20)


def _newell(pts):
    nx = ny = nz = 0.0
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    L = math.sqrt(nx * nx + ny * ny + nz * nz)
    return None if L < 1e-12 else (nx / L, ny / L, nz / L)


def _basis(n):
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = (n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2],
          n[0] * a[1] - n[1] * a[0])
    L = math.sqrt(sum(c * c for c in e1))
    e1 = tuple(c / L for c in e1)
    e2 = (n[1] * e1[2] - n[2] * e1[1], n[2] * e1[0] - n[0] * e1[2],
          n[0] * e1[1] - n[1] * e1[0])
    return e1, e2


def _half(poly, a, b, c, R):
    """``poly`` ∩ {a·u + b·v + c ≥ 0} (shapely)."""
    from shapely.geometry import Polygon
    L2 = a * a + b * b
    if L2 < 1e-18:
        return poly if c >= -1e-9 else None
    L = math.sqrt(L2)
    nu, nv = a / L, b / L
    p = (-c * a / L2, -c * b / L2)
    d = (-nv, nu)
    hp = Polygon([(p[0] + d[0] * R, p[1] + d[1] * R),
                  (p[0] - d[0] * R, p[1] - d[1] * R),
                  (p[0] - d[0] * R + nu * R, p[1] - d[1] * R + nv * R),
                  (p[0] + d[0] * R + nu * R, p[1] + d[1] * R + nv * R)])
    out = poly.intersection(hp)
    return None if out.is_empty else out


def clip_face(loop, holes, box):
    """[(loop, holes)] — the planar face cut to the box (world coords)."""
    from shapely.geometry import Polygon
    x0, y0, z0, x1, y1, z1 = box
    xs = [q[0] for q in loop]
    ys = [q[1] for q in loop]
    zs = [q[2] for q in loop]
    if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1 or \
            max(zs) < z0 or min(zs) > z1:
        return []
    if min(xs) >= x0 and max(xs) <= x1 and min(ys) >= y0 and \
            max(ys) <= y1 and min(zs) >= z0 and max(zs) <= z1:
        return [(loop, holes)]
    n = _newell(loop)
    if n is None:
        return []
    e1, e2 = _basis(n)
    O = loop[0]

    def to2(q):
        d = (q[0] - O[0], q[1] - O[1], q[2] - O[2])
        return (d[0] * e1[0] + d[1] * e1[1] + d[2] * e1[2],
                d[0] * e2[0] + d[1] * e2[1] + d[2] * e2[2])

    def to3(p):
        return (O[0] + e1[0] * p[0] + e2[0] * p[1],
                O[1] + e1[1] * p[0] + e2[1] * p[1],
                O[2] + e1[2] * p[0] + e2[2] * p[1])
    try:
        poly = Polygon([to2(q) for q in loop], [[to2(q) for q in h]
                                                for h in holes or []])
        if not poly.is_valid:
            poly = poly.buffer(0)
    except Exception:  # noqa: BLE001
        return [(loop, holes)]
    R = 1e4
    # each box face: s·(P − plane) ≥ 0 inside; P = O + u e1 + v e2
    for k, (lo, hi) in enumerate(((x0, x1), (y0, y1), (z0, z1))):
        for val, sg in ((lo, 1.0), (hi, -1.0)):
            a = sg * e1[k]
            b = sg * e2[k]
            c = sg * (O[k] - val)
            poly = _half(poly, a, b, c, R)
            if poly is None:
                return []
    out = []
    for g in getattr(poly, "geoms", [poly]):
        if g.geom_type != "Polygon" or g.area < 1e-8:
            continue
        out.append(([to3(p) for p in list(g.exterior.coords)[:-1]],
                    [[to3(p) for p in list(r.coords)[:-1]]
                     for r in g.interiors]))
    return out


def _group_faces(g):
    """[(loop, holes, attrs)] in world coords."""
    M = getattr(g, "xform", None)
    out = []
    mesh = getattr(g, "mesh", None)
    if mesh is None:
        return out
    for f in list(getattr(mesh, "faces", []) or []):
        def W(v):
            q = M.map(v) if M is not None else v
            return (q.x(), q.y(), q.z())
        try:
            out.append(([W(v) for v in f.vertices],
                        [[W(v) for v in h] for h in (f.holes or [])],
                        dict(getattr(f, "attrs", {}) or {})))
        except Exception:  # noqa: BLE001
            continue
    return out


def _bounds(fs):
    pts = [q for lp, _h, _a in fs for q in lp]
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            min(p[2] for p in pts), max(p[0] for p in pts),
            max(p[1] for p in pts), max(p[2] for p in pts))


def _inside(bb, box):
    return bb[0] >= box[0] and bb[1] >= box[1] and bb[2] >= box[2] and \
        bb[3] <= box[3] and bb[4] <= box[4] and bb[5] <= box[5]


def _outside(bb, box):
    return bb[3] < box[0] or bb[0] > box[3] or bb[4] < box[1] or \
        bb[1] > box[4] or bb[5] < box[2] or bb[2] > box[5]


def cut(groups, box) -> list:
    """The groups cut to ``box``: inside ones as they are, outside ones
    hidden, crossing ones made again from their clipped faces (in world
    coordinates, no longer shared components)."""
    from PySide6.QtGui import QVector3D

    from core.mesh import Mesh
    for g in groups:
        # a door / window remembers where it was built, to follow a Move of
        # it: cut, it is no longer where it was — that is no move
        try:
            for v in (getattr(g, "ext", None) or {}).values():
                if isinstance(v, dict):
                    v.pop("at", None)
        except Exception:  # noqa: BLE001
            pass
        kids = list(getattr(g, "children", None) or [])
        if kids:
            cut(kids, box)
        fs = _group_faces(g)
        bb = _bounds(fs)
        if bb is None:
            continue
        if _inside(bb, box):
            continue
        if _outside(bb, box):            # emptied, not hidden («Show
            g.mesh = Mesh()              # all» must not bring it back)
            g.xform = None
            continue
        mesh = Mesh()
        for lp, hs, at in fs:
            for L2, H2 in clip_face(lp, hs, box):
                if len(L2) < 3:
                    continue
                face = mesh.add_face([QVector3D(*q) for q in L2],
                                     [[QVector3D(*q) for q in h]
                                      for h in H2 if len(h) >= 3])
                if face is not None and at:
                    face.attrs.update(at)
        g.mesh = mesh
        g.xform = None
        try:
            g.component = False
        except Exception:  # noqa: BLE001
            pass
    return groups


def model_bounds(groups):
    bbs = [b for b in (_bounds(_group_faces(g)) for g in groups) if b]
    if not bbs:
        return None
    return [round(min(b[0] for b in bbs), 3), round(min(b[1] for b in bbs), 3),
            round(min(b[2] for b in bbs), 3), round(max(b[3] for b in bbs), 3),
            round(max(b[4] for b in bbs), 3), round(max(b[5] for b in bbs), 3)]


def draw(vp, painter, box) -> None:
    """The box's twelve edges over the 3D view."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPen, QVector3D
    if not box:
        return
    x0, y0, z0, x1, y1, z1 = box
    P = {}
    for i, x in enumerate((x0, x1)):
        for j, y in enumerate((y0, y1)):
            for k, z in enumerate((z0, z1)):
                P[(i, j, k)] = vp._world_to_pixel(QVector3D(x, y, z))
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(*EDGE), 1.6, Qt.DashLine))
    for a in P:
        for ax in range(3):
            if a[ax] == 0:
                b = list(a)
                b[ax] = 1
                pa, pb = P[a], P[tuple(b)]
                if pa and pb:
                    painter.drawLine(QPointF(pa[0], pa[1]),
                                     QPointF(pb[0], pb[1]))
    painter.restore()
