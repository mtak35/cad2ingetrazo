# SPDX-License-Identifier: GPL-3.0-or-later
"""The model written as ONE SketchUp ``.skp`` file, with OpenSKP's own
pure-Python writer (``openskp.create``, shipped inside IngeTrazo) — no
Collada, no texture images beside it.

IngeTrazo 0.5.7's installer carries ``openskp`` but not the newer
``formats.skp_out`` exporter, so CAD2IngeTrazo writes the file itself:

* a component (groups sharing one mesh, placed by ``xform``) → ONE
  SketchUp component definition, placed by N instances (mirrored
  placements kept);
* any other group → a SketchUp group;
* the faces' colours (``attrs["color"]``, else the group's material) →
  SketchUp materials, with their opacity;
* IngeTrazo layers → SketchUp tags (hidden ones exported hidden);
* face holes kept (or, on an older writer, the face split into
  triangles).

Coordinates go out in inches (SketchUp's own unit).
"""
from __future__ import annotations

import inspect
import math

M_TO_IN = 39.37007874
ASCII = False        # names written in plain ASCII only (see _nm)


def _nm(s, n=80):
    """A name for SketchUp: no control characters; with ``ASCII`` only
    plain ASCII (· → -, ′ ″ → ' ", anything else dropped)."""
    s = str(s or "")
    s = "".join(c for c in s if c >= " " and c != "\x7f")
    if ASCII:
        s = (s.replace("\u00b7", "-").replace("\u2032", "'")
             .replace("\u2033", '"').replace("\u2014", "-")
             .replace("\u2013", "-").replace("\u00d7", "x")
             .replace("\u00b2", "2").replace("\u00b0", " deg"))
        s = s.encode("ascii", "ignore").decode("ascii")
    return s[:n]


def _kw(fn, **kw):
    """Only the keyword arguments ``fn`` takes (the writer's API grew over
    its versions)."""
    try:
        ps = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return kw
    return {k: v for k, v in kw.items() if k in ps and v is not None}


def _pt(v, m=None):
    if m is not None:
        v = m.map(v)
    return (round(v.x() * M_TO_IN, 4), round(v.y() * M_TO_IN, 4),
            round(v.z() * M_TO_IN, 4))


def _clean(pts, tol=0.01):
    """A loop (inches) without repeated points and without the points
    standing in a straight run (OpenSKP's writer writes a face with
    collinear vertices into a file SketchUp can't open —
    «unexpected file format»)."""
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > tol:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= tol:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            u = [b[k] - a[k] for k in range(3)]
            w = [c[k] - b[k] for k in range(3)]
            cr = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2],
                  u[0] * w[1] - u[1] * w[0])
            lu = math.sqrt(sum(x * x for x in u))
            lw = math.sqrt(sum(x * x for x in w))
            if lu < tol or lw < tol or \
                    math.sqrt(sum(x * x for x in cr)) / max(lu, lw) < tol:
                out.pop(i)
                changed = True
                break
    return out


def _rgba(col, opacity=1.0):
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in col[:3])
    return (r, g, b, max(0, min(255, int(round(255 * float(opacity))))))


def _walk(groups, parent=None, layer=None, paint=None):
    """(group, accumulated QMatrix4x4 | None, layer name, paint) for every
    group with a mesh, through the groups inside groups."""
    from PySide6.QtGui import QMatrix4x4
    for g in groups or []:
        xf = getattr(g, "xform", None)
        here = parent
        if xf is not None:
            here = (parent * xf) if parent is not None else QMatrix4x4(xf)
        lay = getattr(g, "layer", None) or layer
        mat = getattr(g, "material", None) or paint
        if getattr(g, "mesh", None) is not None:
            yield g, here, lay, mat
        yield from _walk(getattr(g, "children", None), here, lay, mat)


def _face_paint(face, mat):
    a = getattr(face, "attrs", None) or {}
    col = a.get("color")
    op = a.get("opacity", 1.0)
    if col is None and isinstance(mat, dict):
        col = mat.get("color")
        op = mat.get("opacity", 1.0) if a.get("opacity") is None else op
    if col is None:
        return None
    try:
        return _rgba(col, op if op is not None else 1.0)
    except (TypeError, ValueError):
        return None


def _faces(mesh):
    for f in getattr(mesh, "faces", None) or []:
        if getattr(f, "interior", False):
            continue
        loop = getattr(f, "loop", None) or []
        if len(loop) < 3:
            continue
        if getattr(f, "attrs", {}).get("hidden"):
            continue
        yield f


def _ensure_scaffold() -> None:
    """Some IngeTrazo installers ship openskp without its data folder
    (``_scaffold/blank_v17.skp``), so ``openskp.create()`` fails with a
    missing file. Our own copy of that MIT-licensed blank document (same
    bytes, checked against openskp's own hash) is handed to it then."""
    import hashlib
    import os
    import sys
    mod = sys.modules.get("openskp.create")
    if mod is None or getattr(mod, "_c2i_patched", False):
        return
    try:
        mod._load_scaffold()
        return                              # openskp has its own: fine
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001 — anything else: leave it to openskp
        return
    here = os.path.join(os.path.dirname(__file__), "_skp",
                        getattr(mod, "_SCAFFOLD_FILE", "blank_v17.skp"))
    with open(here, "rb") as f:
        data = f.read()
    want = getattr(mod, "_SCAFFOLD_SHA256", None)
    if want and hashlib.sha256(data).hexdigest() != want:
        raise RuntimeError("this IngeTrazo's OpenSKP expects a different "
                           "blank .skp than the one CAD2IngeTrazo carries")
    mod._load_scaffold = lambda: data
    mod._c2i_patched = True


# ---- the walls of a floor as ONE continuous body --------------------------
def _plane_of(pts):
    """(unit normal, d) of a planar loop (Newell), d = n·p."""
    nx = ny = nz = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    L = math.sqrt(nx * nx + ny * ny + nz * nz)
    if L < 1e-12:
        return None
    n = (nx / L, ny / L, nz / L)
    d = sum(n[k] * pts[0][k] for k in range(3))
    return n, d


def _basis(n):
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2],
         n[0] * a[1] - n[1] * a[0])
    L = math.sqrt(sum(c * c for c in u))
    u = tuple(c / L for c in u)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2],
         n[0] * u[1] - n[1] * u[0])
    return u, v


def merge_walls(items, doc) -> tuple:
    """The walls of each floor as one body, as a SketchUp user models them:
    their faces in each plane joined (a facade of five walls one face, the
    tops one face), the faces where two walls touch (an end against a
    side) taken out of both — the walls run on into each other, the
    openings stay cut. (consumed group ids, [(name, layer, [(loop m,
    [holes m], rgba)])])."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    try:
        from shapely import set_precision
    except Exception:  # noqa: BLE001
        set_precision = None
    from .host import KEY
    arch = doc["arch"]
    recs = {w["id"]: w for w in arch["walls"]}
    names = {lv["id"]: lv["name"] for lv in arch["levels"]}
    by_lv: dict = {}
    used = set()
    for g, m, lay, mat in items:
        t = ((getattr(g, "ext", None) or {}).get(KEY) or {})
        if t.get("type") != "wall" or t.get("part"):
            continue
        w = recs.get(t.get("id"))
        if w is None or w.get("rail") or w.get("type") == "curtain":
            continue
        by_lv.setdefault((t.get("level"), lay), []).append((g, m, mat))
        used.add(id(g))
    out = []
    for (lid, lay), its in by_lv.items():
        planes: dict = {}
        loose = []
        for g, m, mat in its:
            for f in _faces(g.mesh):
                pts = [_world(v.position, m) for v in f.loop]
                holes = [[_world(v.position, m) for v in h]
                         for h in getattr(f, "hole_loops", None) or []]
                rgba = _face_paint(f, mat)
                pl = _plane_of(pts)
                if pl is None:
                    continue
                n, d = pl
                sg = 1
                for c in n:                       # one key per plane, both
                    if abs(c) > 1e-6:             # facings under it
                        sg = 1 if c > 0 else -1
                        break
                key = (tuple(round(sg * c, 3) for c in n), round(sg * d, 3))
                planes.setdefault(key, []).append((sg, pts, holes, rgba))
        faces = []
        for (nk, dk), fl in planes.items():
            n = nk
            u, v = _basis(n)
            o = tuple(n[k] * dk for k in range(3))

            def to2(p):
                q = (p[0] - o[0], p[1] - o[1], p[2] - o[2])
                return (q[0] * u[0] + q[1] * u[1] + q[2] * u[2],
                        q[0] * v[0] + q[1] * v[1] + q[2] * v[2])

            def to3(xy):
                return tuple(o[k] + u[k] * xy[0] + v[k] * xy[1]
                             for k in range(3))
            if len(fl) == 1:
                sg, pts, holes, rgba = fl[0]
                faces.append((pts, holes, rgba))
                continue
            side = {1: {}, -1: {}}
            try:
                for sg, pts, holes, rgba in fl:
                    P = Polygon([to2(p) for p in pts],
                                [[to2(p) for p in h] for h in holes])
                    if not P.is_valid:
                        P = P.buffer(0)
                    if P.is_empty:
                        continue
                    side[sg].setdefault(rgba, []).append(P)
                U = {sg: {c: unary_union(ps) for c, ps in d_.items()}
                     for sg, d_ in side.items()}
                allp = {sg: unary_union(list(d_.values())) if d_ else None
                        for sg, d_ in U.items()}
                touch = None
                if allp[1] is not None and allp[-1] is not None:
                    touch = allp[1].intersection(allp[-1])
                    if touch.area < 1e-6:
                        touch = None
                for sg, d_ in U.items():
                    for rgba, geo in d_.items():
                        if touch is not None:
                            geo = geo.difference(touch)
                        if set_precision is not None:
                            try:
                                geo = set_precision(geo, 1e-4)
                            except Exception:  # noqa: BLE001
                                pass
                        for q in getattr(geo, "geoms", [geo]):
                            if q.geom_type != "Polygon" or q.area < 1e-5:
                                continue
                            q = q.simplify(0.0002)
                            ext = list(q.exterior.coords)[:-1]
                            # facing: CCW in (u, v) faces +n
                            ccw = Polygon(ext).exterior.is_ccw
                            if (sg > 0) != ccw:
                                ext = ext[::-1]
                            hs = []
                            for h in q.interiors:
                                hp = list(h.coords)[:-1]
                                hs.append([to3(x) for x in hp])
                            faces.append(([to3(x) for x in ext], hs, rgba))
            except Exception:  # noqa: BLE001 — that plane as it was
                for sg, pts, holes, rgba in fl:
                    faces.append((pts, holes, rgba))
        out.append((f"Walls · {names.get(lid, lid)}", lay, faces))
    return used, out


def _world(v, m):
    if m is not None:
        v = m.map(v)
    return (v.x(), v.y(), v.z())


WRITER = ""          # which writer made the last file


def new_builder():
    """A blank .skp builder: OpenSKP 1.3.0's writer carried in
    ``_openskp`` (IngeTrazo's own, older OpenSKP writes object references
    past 16,384 wrongly — SketchUp then refuses the file as «unexpected
    file format»); IngeTrazo's when ours can't load."""
    global WRITER
    try:
        from ._openskp import create as _create
        b = _create()
        WRITER = "openskp 1.3.0 (CAD2IngeTrazo)"
        return b
    except Exception:  # noqa: BLE001 — a dependency missing: theirs
        from .host import log_error
        log_error("skpwriter: bundled OpenSKP")
    try:
        import openskp
    except ImportError as exc:
        raise RuntimeError("OpenSKP is not in this IngeTrazo") from exc
    _ensure_scaffold()
    WRITER = "openskp %s (IngeTrazo)" % getattr(openskp, "__version__", "?")
    return openskp.create()


def save_skp(scene, path, progress=None, doc=None, merge=True) -> dict:
    """Write ``scene`` to ``path`` as a .skp. {"definitions", "instances",
    "groups", "faces"}; raises RuntimeError when OpenSKP is missing."""
    from PySide6.QtGui import QMatrix4x4

    b = new_builder()
    items = list(_walk(getattr(scene, "groups", [])))
    merged = []
    if doc is not None and merge:
        try:                       # the walls of each floor: one body
            used, merged = merge_walls(items, doc)
            items = [it for it in items if id(it[0]) not in used]
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("skpwriter.merge_walls")
            merged = []
    layers = {getattr(L, "name", ""): getattr(L, "visible", True)
              for L in getattr(scene, "layers", []) or []}

    # what is a component: groups placed by xform sharing one mesh
    by_mesh: dict = {}
    for g, m, lay, mat in items:
        if m is not None:
            by_mesh.setdefault(id(g.mesh), []).append((g, m, lay, mat))
    # (a floor group — «Floors as groups» — has no faces of its own: its
    # elements are written in their own right)
    defs = {k: v for k, v in by_mesh.items()
            if any(True for _f in _faces(v[0][0].mesh))}
    classic = [(g, m, lay, mat) for g, m, lay, mat in items if m is None]
    loose = getattr(scene, "mesh", None)

    # 1 materials (all before anything else)
    mats: dict = {}

    def need(rgba):
        if rgba is not None and rgba not in mats:
            name = "C2I %02X%02X%02X" % rgba[:3] + \
                ("" if rgba[3] >= 255 else " %d%%" % round(rgba[3] / 2.55))
            mats[rgba] = b.add_material(
                _nm(name), rgba[:3] if rgba[3] >= 255 else rgba,
                **_kw(b.add_material,
                      opacity=None if rgba[3] >= 255 else rgba[3] / 255.0))
    for g, m, lay, mat in items:
        for f in _faces(g.mesh):
            need(_face_paint(f, mat))
    if loose is not None:
        for f in _faces(loose):
            need(_face_paint(f, None))
    for _n, _lay, fs_ in merged:
        for _p, _h, rgba_ in fs_:
            need(rgba_)

    # 2 tags
    tags: dict = {}
    for lay in sorted({lay for _g, _m, lay, _mt in items if lay} |
                      {lay for _n, lay, _f in merged if lay}):
        tags[lay] = b.add_layer(_nm(lay) or "Tag", **_kw(b.add_layer,
                                           hidden=not layers.get(lay, True)))

    has_holes = "holes" in inspect.signature(b.add_face).parameters

    def put(sink, f, m, mat, layer):
        pts = _clean([_pt(v.position, m) for v in f.loop])
        if len(pts) < 3:
            return 0
        holes = [h_ for h_ in (_clean([_pt(v.position, m) for v in h])
                               for h in getattr(f, "hole_loops", None) or [])
                 if len(h_) >= 3]
        kw = dict(material=mats.get(_face_paint(f, mat)), layer=layer)
        try:
            if holes and not has_holes:
                raise ValueError("holes")
            sink.add_face(pts, **_kw(sink.add_face, holes=holes or None,
                                     auto_triangulate=True, **kw))
            return 1
        except Exception:  # noqa: BLE001 — a face the writer refuses:
            n = 0              # its triangles instead
            try:
                tris = f.triangulate()
            except Exception:  # noqa: BLE001
                return 0
            for t in tris or []:
                try:
                    tp = [_pt(q if hasattr(q, "x") else q.position, m)
                          for q in t]
                    if len(set(tp)) == 3:
                        sink.add_face(tp, **_kw(sink.add_face, **kw))
                        n += 1
                except Exception:  # noqa: BLE001
                    pass
            return n

    stats = {"definitions": 0, "instances": 0, "groups": 0, "faces": 0}
    # 3 component definitions, in their own frame
    built = {}
    for k, uses in defs.items():
        g0, _m0, lay0, mat0 = uses[0]
        name = str(getattr(g0, "name", "") or "Component").split(" · ")[0]
        name = (_nm(name, 60) or "Component") + f" #{len(built) + 1}"
        d = b.add_component_definition(name)
        with d:
            for f in _faces(g0.mesh):
                stats["faces"] += put(d, f, None, mat0, None)
        built[k] = d
        stats["definitions"] += 1
        if progress:
            progress(stats)

    # 4 the plain groups, in model coordinates
    for g, _m, lay, mat in classic:
        fs = list(_faces(g.mesh))
        if not fs:
            continue
        with b.add_group(**_kw(b.add_group,
                               name=_nm(getattr(g, "name", "")),
                               layer=tags.get(lay))) as gb:
            for f in fs:
                stats["faces"] += put(gb, f, None, mat, None)
        stats["groups"] += 1
    # 4b the walls of each floor, joined into one body
    for nm_, lay_, fs_ in merged:
        if not fs_:
            continue
        with b.add_group(**_kw(b.add_group, name=_nm(nm_),
                               layer=tags.get(lay_))) as gb:
            for pts, holes, rgba in fs_:
                P = _clean([tuple(round(c * M_TO_IN, 4) for c in p)
                            for p in pts])
                if len(P) < 3:
                    continue
                H = [h_ for h_ in (_clean([tuple(round(c * M_TO_IN, 4)
                                                 for c in p) for p in h])
                                   for h in holes) if len(h_) >= 3]
                kw = dict(material=mats.get(rgba), layer=None)
                try:
                    if H and not has_holes:
                        raise ValueError("holes")
                    gb.add_face(P, **_kw(gb.add_face, holes=H or None,
                                         auto_triangulate=True, **kw))
                    stats["faces"] += 1
                except Exception:  # noqa: BLE001
                    try:
                        gb.add_face(P, **_kw(gb.add_face,
                                             auto_triangulate=True, **kw))
                        stats["faces"] += 1
                    except Exception:  # noqa: BLE001
                        pass
        stats["groups"] += 1

    # 5 the instances (after every definition and group)
    for k, uses in defs.items():
        for g, m, lay, _mat in uses:
            r = [m(i, j) for i in range(3) for j in range(3)]
            t = (m(0, 3) * M_TO_IN, m(1, 3) * M_TO_IN, m(2, 3) * M_TO_IN)
            b.add_instance(built[k], **_kw(
                b.add_instance, name=_nm(getattr(g, "name", "")),
                translation=t, matrix3x3=tuple(r), layer=tags.get(lay)))
            stats["instances"] += 1

    if loose is not None:
        for f in _faces(loose):
            stats["faces"] += put(b, f, None, None, None)

    b.save(str(path))
    return stats


__all__ = ["save_skp", "M_TO_IN", "math"]
