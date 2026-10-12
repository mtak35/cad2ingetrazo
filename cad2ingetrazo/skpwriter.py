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


def save_skp(scene, path, progress=None) -> dict:
    """Write ``scene`` to ``path`` as a .skp. {"definitions", "instances",
    "groups", "faces"}; raises RuntimeError when OpenSKP is missing."""
    try:
        import openskp
    except ImportError as exc:
        raise RuntimeError("OpenSKP is not in this IngeTrazo") from exc
    from PySide6.QtGui import QMatrix4x4

    _ensure_scaffold()
    b = openskp.create()
    items = list(_walk(getattr(scene, "groups", [])))
    layers = {getattr(L, "name", ""): getattr(L, "visible", True)
              for L in getattr(scene, "layers", []) or []}

    # what is a component: groups placed by xform sharing one mesh
    by_mesh: dict = {}
    for g, m, lay, mat in items:
        if m is not None:
            by_mesh.setdefault(id(g.mesh), []).append((g, m, lay, mat))
    defs = {k: v for k, v in by_mesh.items()}
    classic = [(g, m, lay, mat) for g, m, lay, mat in items if m is None]
    loose = getattr(scene, "mesh", None)

    # 1 materials (all before anything else)
    mats: dict = {}

    def need(rgba):
        if rgba is not None and rgba not in mats:
            name = "C2I %02X%02X%02X" % rgba[:3] + \
                ("" if rgba[3] >= 255 else " %d%%" % round(rgba[3] / 2.55))
            mats[rgba] = b.add_material(
                name, rgba[:3] if rgba[3] >= 255 else rgba,
                **_kw(b.add_material,
                      opacity=None if rgba[3] >= 255 else rgba[3] / 255.0))
    for g, m, lay, mat in items:
        for f in _faces(g.mesh):
            need(_face_paint(f, mat))
    if loose is not None:
        for f in _faces(loose):
            need(_face_paint(f, None))

    # 2 tags
    tags: dict = {}
    for lay in sorted({lay for _g, _m, lay, _mt in items if lay}):
        tags[lay] = b.add_layer(lay, **_kw(b.add_layer,
                                           hidden=not layers.get(lay, True)))

    has_holes = "holes" in inspect.signature(b.add_face).parameters

    def put(sink, f, m, mat, layer):
        pts = [_pt(v.position, m) for v in f.loop]
        holes = [[_pt(v.position, m) for v in h]
                 for h in getattr(f, "hole_loops", None) or []]
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
        name = (name[:60] or "Component") + f" #{len(built) + 1}"
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
                               name=str(getattr(g, "name", "") or "")[:80],
                               layer=tags.get(lay))) as gb:
            for f in fs:
                stats["faces"] += put(gb, f, None, mat, None)
        stats["groups"] += 1
    # 5 the instances (after every definition and group)
    for k, uses in defs.items():
        for g, m, lay, _mat in uses:
            r = [m(i, j) for i in range(3) for j in range(3)]
            t = (m(0, 3) * M_TO_IN, m(1, 3) * M_TO_IN, m(2, 3) * M_TO_IN)
            b.add_instance(built[k], **_kw(
                b.add_instance, name=str(getattr(g, "name", "") or "")[:80],
                translation=t, matrix3x3=tuple(r), layer=tags.get(lay)))
            stats["instances"] += 1

    if loose is not None:
        for f in _faces(loose):
            stats["faces"] += put(b, f, None, None, None)

    b.save(str(path))
    return stats


__all__ = ["save_skp", "M_TO_IN", "math"]
