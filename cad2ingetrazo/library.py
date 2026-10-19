# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo's own component library (``resources/components/*.igz`` —
the doors, windows, furniture, cars… of Properties ▸ Components) as the
model of a CAD2IngeTrazo component type: every element of the type shows
the library model instead, fitted to the element's own box (stretched to
it, or scaled evenly to fit inside it), turned as asked.

The choice lives on the type: ``doc["comp_names"][type key]["lib"] =
{"key": "suv" | "online:<id>", "fit": "stretch" | "keep" | "native",
"rot": 0|90|180|270, "name", "entry": the online catalogue's record}`` —
the bundled models and IngeTrazo's whole online catalogue («More
components…», doors, windows, kitchen, bathroom, furniture…).
— the CAD2IngeTrazo element stays the record (its wall opening, its
dimensions, its schedule); only what is drawn changes.
"""
from __future__ import annotations

import math

_PROTO: dict = {}
FITS = [("stretch", "Stretch to the element's size"),
        ("keep", "Keep its proportions (fit inside)"),
        ("native", "Its own size (centred on the element)")]


def folder():
    from pathlib import Path

    from core.paths import app_root
    return Path(app_root()) / "resources" / "components"


def label_of(key: str) -> str:
    stem = key.replace("\\", "/").split("/")[-1]
    words = stem.replace("_", " ").replace("-", " ").split()
    head = key.replace("\\", "/").split("/")[:-1]
    return (" / ".join(h.title() for h in head) + " · " if head else "") + \
        " ".join(w.capitalize() for w in words)


#: The online catalogue's categories (they arrive in Spanish) in English —
#: as IngeTrazo's own library dialog says them.
CATEGORY_EN = {
    "Cocina": "Kitchen", "Cuarto de Baño": "Bathroom",
    "Dormitorio": "Bedroom", "Escaleras": "Staircases",
    "Exterior": "Exterior", "Iluminación": "Lights", "Oficina": "Office",
    "Personajes": "People", "Puertas y Ventanas": "Doors and windows",
    "Salón": "Living room", "Varios": "Miscellaneous",
    "Vehículos": "Vehicles"}
BUNDLED = "Bundled with IngeTrazo"


def bundled() -> list:
    """The models that ship in ``resources/components`` (the tray's grid):
    [{"key", "name", "tip", "cat", "src": "igz"}]."""
    out = []
    try:
        root = folder()
        if not root.exists():
            return []
        names = {}
        try:                           # the library's own names and notes
            import json
            for e in json.loads((root / "components.json").read_text(
                    encoding="utf-8")):
                names[str(e["key"])] = (str(e.get("name") or e["key"]),
                                        str(e.get("tip") or ""))
        except Exception:  # noqa: BLE001
            pass
        for p in sorted(root.rglob("*.igz")):
            key = p.relative_to(root).with_suffix("").as_posix()
            nm, tip = names.get(key, (label_of(key), ""))
            out.append({"key": key, "name": nm, "tip": tip, "cat": BUNDLED,
                        "src": "igz"})
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("library.bundled")
    return out


def online(refresh: bool = False) -> list:
    """The whole online catalogue — IngeTrazo's «More components…»
    (``core.library``: ~1500 models, cached after the first read):
    [{"key": "online:<id>", "name", "tip", "cat", "src": "online",
    "entry": the catalogue's own record}]."""
    try:
        from core import library as CL
    except Exception:  # noqa: BLE001 — an IngeTrazo without the library
        return []
    out = []
    try:
        for e in CL.index(refresh):
            ident = str(e.get("id") or "")
            if not ident:
                continue
            nm = e.get("nombre_en") or e.get("nombre") or ident
            cat = CATEGORY_EN.get(e.get("categoria", ""),
                                  e.get("categoria", "") or "Miscellaneous")
            cm = e.get("cm") or ()
            tip = ""
            try:
                tip = " × ".join(f"{float(v) / 100:.2f}" for v in cm) + " m"
            except (TypeError, ValueError):
                pass
            if e.get("licencia_nombre") or e.get("licencia"):
                tip += f" · {e.get('licencia_nombre') or e.get('licencia')}"
            out.append({"key": f"online:{ident}", "name": str(nm),
                        "tip": tip, "cat": cat, "src": "online",
                        "entry": e})
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("library.online")
    return out


def list_entries(refresh: bool = False) -> list:
    """Everything that can stand in for a component type: the bundled
    models, then the online catalogue, sorted by category and name."""
    on = online(refresh)
    on.sort(key=lambda e: (e["cat"].lower(), e["name"].lower()))
    return bundled() + on


def list_all() -> list:
    """[(key, label)] — kept for older callers."""
    return [(e["key"], f"{e['cat']} · {e['name']}") for e in list_entries()]


def thumbnail(entry: dict):
    """A preview image path for an entry when there is one on disk (never
    blocks: online previews are fetched by :func:`prefetch`)."""
    try:
        if entry.get("src") == "igz":
            p = folder() / "thumbs" / f"{entry['key']}.png"
            return p if p.is_file() else None
        from core import library as CL
        return CL.cached_thumbnail(entry["entry"].get("id", ""))
    except Exception:  # noqa: BLE001
        return None


def prefetch(entries) -> None:
    """Fetch the online previews of ``entries`` in the background."""
    try:
        from core import library as CL
        CL.prefetch_thumbnails([e["entry"].get("id") for e in entries
                                if e.get("src") == "online"])
    except Exception:  # noqa: BLE001
        pass


def _collect(scene):
    """[(mesh, QMatrix4x4 | None)] of every piece in ``scene`` — its loose
    geometry, each group, and the groups inside groups (a model written as
    parts), each with its placement."""
    from PySide6.QtGui import QMatrix4x4
    parts = []
    m0 = getattr(scene, "mesh", None)
    if m0 is not None and getattr(m0, "faces", None):
        parts.append((m0, None))

    def walk(g, parent):
        xf = getattr(g, "xform", None)
        here = parent
        if xf is not None:
            here = (parent * xf) if parent is not None else QMatrix4x4(xf)
        m = getattr(g, "mesh", None)
        if m is not None and getattr(m, "faces", None):
            parts.append((m, here))
        for kid in getattr(g, "children", None) or []:
            walk(kid, here)
    for g in getattr(scene, "groups", []) or []:
        walk(g, None)
    return parts


def _boxed(parts):
    lo, hi = [1e18] * 3, [-1e18] * 3
    for m, xf in parts:
        for v in m.vertices:
            p = v.position
            if xf is not None:
                p = xf.map(p)
            for i, c in enumerate((p.x(), p.y(), p.z())):
                lo[i] = min(lo[i], c)
                hi[i] = max(hi[i], c)
    if not parts or hi[0] <= lo[0]:
        return None
    return {"parts": parts, "box": (*lo, *hi)}


#: furniture, fixtures and cars light (a few hundred faces each) while
#: modelling; the full models for rendering («High poly»)
LOWPOLY = [True]
_LOW: dict = {}


_TEXCOL: dict = {}


def _tex_colour(path):
    """A texture's mean colour (r, g, b 0–1) — a light model's face paint
    in place of the picture — or None."""
    if not path:
        return None
    if path in _TEXCOL:
        return _TEXCOL[path]
    col = None
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        img = QImage(str(path))
        if not img.isNull():           # the opaque pixels only (leaves on
            sm = img.scaled(24, 24, Qt.IgnoreAspectRatio,   # a clear ground)
                            Qt.SmoothTransformation)
            r = g = b = wsum = 0.0
            for y in range(sm.height()):
                for x in range(sm.width()):
                    c = sm.pixelColor(x, y)
                    a = c.alphaF()
                    if a < 0.4:
                        continue
                    r += c.redF() * a
                    g += c.greenF() * a
                    b += c.blueF() * a
                    wsum += a
            if wsum > 0:
                col = (r / wsum, g / wsum, b / wsum)
    except Exception:  # noqa: BLE001
        col = None
    _TEXCOL[path] = col
    return col


def decimate(parts, cells: int = 16):
    """ONE light mesh of the model ``parts`` [(mesh, xform)]: its points
    gathered on a grid (``cells`` across its largest size), the triangles
    left whole kept — the shape, the colours, a fraction of the faces."""
    from PySide6.QtGui import QVector3D

    from core.mesh import Mesh
    tris = []
    lo, hi = [1e18] * 3, [-1e18] * 3
    for m, xf in parts:
        for f in m.faces:
            pts = []
            for v in f.loop:
                p = v.position
                if xf is not None:
                    p = xf.map(p)
                pts.append((p.x(), p.y(), p.z()))
            if len(pts) < 3:
                continue
            col = f.attrs.get("color")
            if col is None and f.attrs.get("texture"):
                col = _tex_colour((f.attrs["texture"] or {}).get("path"))
            for i in range(1, len(pts) - 1):
                tris.append((pts[0], pts[i], pts[i + 1], col))
            for q in pts:
                for i in range(3):
                    lo[i] = min(lo[i], q[i])
                    hi[i] = max(hi[i], q[i])
    if not tris:
        return None
    size = max(hi[i] - lo[i] for i in range(3))
    cell = max(size / float(cells), 0.015)
    acc = {}

    def key(q):
        return (int((q[0] - lo[0]) // cell), int((q[1] - lo[1]) // cell),
                int((q[2] - lo[2]) // cell))
    for a, b, c, _col in tris:
        for q in (a, b, c):
            k = key(q)
            s_ = acc.get(k)
            if s_ is None:
                acc[k] = [q[0], q[1], q[2], 1]
            else:
                s_[0] += q[0]
                s_[1] += q[1]
                s_[2] += q[2]
                s_[3] += 1
    rep = {k: (v[0] / v[3], v[1] / v[3], v[2] / v[3]) for k, v in acc.items()}
    seen = set()
    mesh = Mesh()
    for a, b, c, col in tris:
        ka, kb, kc = key(a), key(b), key(c)
        if ka == kb or kb == kc or ka == kc:
            continue
        sk = tuple(sorted((ka, kb, kc)))
        if sk in seen:
            continue
        seen.add(sk)
        try:
            f = mesh.add_face([QVector3D(*rep[ka]), QVector3D(*rep[kb]),
                               QVector3D(*rep[kc])])
        except Exception:  # noqa: BLE001
            continue
        if f is not None and col is not None:
            f.attrs["color"] = col
    if not mesh.faces:
        return None
    try:                         # no lines across the curved surfaces
        from formats.fuse import soften_smooth_edges
        soften_smooth_edges(mesh, cos_threshold=0.55)
    except Exception:  # noqa: BLE001
        pass
    return mesh


def proto(key: str, entry: dict | None = None):
    """The model as used: light (``LOWPOLY``) or full — see ``proto_full``."""
    full = proto_full(key, entry)
    if full is None or not LOWPOLY[0]:
        return full
    hit = _LOW.get(key)
    if hit is None:
        try:
            nf = sum(len(m.faces) for m, _x in full["parts"])
            mesh = decimate(full["parts"]) if nf > 400 else None
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("library.decimate")
            mesh = None
        hit = {"parts": [(mesh, None)], "box": full["box"]} \
            if mesh is not None else full
        _LOW[key] = hit
    return hit


def proto_full(key: str, entry: dict | None = None):
    """{"parts": [(mesh, QMatrix4x4 | None)], "box": (x0, y0, z0, x1, y1,
    z1)} of a library model, or None (missing / unreadable / offline).
    ``online:<id>`` keys are downloaded once (IngeTrazo's own cache) and
    sized as the catalogue declares them."""
    if key in _PROTO:
        return _PROTO[key]
    rec = None
    try:
        from core.scene import Scene
        tmp = Scene()
        if key.startswith("online:"):
            from core import library as CL
            from formats import obj as OBJ
            if entry is None:
                ident = key.split(":", 1)[1]
                entry = next((e for e in CL.index()
                              if str(e.get("id")) == ident), None)
            path = CL.model_file(entry) if entry else None
            if path is not None:
                OBJ.load_obj(tmp, path, matrix=CL.model_matrix(entry, path))
                try:
                    from formats.fuse import soften_smooth_edges
                    for m, _x in _collect(tmp):
                        soften_smooth_edges(m, cos_threshold=0.55)
                except Exception:  # noqa: BLE001
                    pass
                rec = _boxed(_collect(tmp))
        else:
            from formats import igz
            path = folder() / f"{key}.igz"
            if path.exists():
                igz.load_into(tmp, path)
                rec = _boxed(_collect(tmp))
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("library.proto")
        rec = None
    if rec is not None:                 # a failed download is tried again
        _PROTO[key] = rec
    return rec


def box_of(lf) -> tuple:
    """(x0, y0, z0, x1, y1, z1) of local faces [(loop, holes, colour)]."""
    xs, ys, zs = [], [], []
    for lp, _hs, _c in lf:
        for q in lp:
            xs.append(q[0])
            ys.append(q[1])
            zs.append(q[2])
    if not xs:
        return (0, 0, 0, 0, 0, 0)
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def fit(box, pr, how="stretch", rot=0.0) -> tuple:
    """(scale x, y, z, turn °, move) — the library model ``pr`` turned by
    ``rot`` and scaled to sit in ``box`` (the element's, in its frame):
    centred in plan, standing on its bottom."""
    bx0, by0, bz0, bx1, by1, bz1 = box
    x0, y0, z0, x1, y1, z1 = pr["box"]
    w, d, h = x1 - x0, y1 - y0, z1 - z0
    if int(round(rot / 90.0)) % 2:          # turned a quarter: W ↔ D
        w, d = d, w
    W_, D_, H_ = bx1 - bx0, by1 - by0, bz1 - bz0
    eps = 1e-6
    if how == "native":
        sx = sy = sz = 1.0
    elif how == "keep":
        k = min(W_ / max(w, eps) if W_ > 0.01 else 1e9,
                D_ / max(d, eps) if D_ > 0.01 else 1e9,
                H_ / max(h, eps) if H_ > 0.01 else 1e9)
        k = 1.0 if k >= 1e8 else k
        sx = sy = sz = k
    else:
        sx = W_ / max(w, eps) if W_ > 0.01 else 1.0
        sy = D_ / max(d, eps) if D_ > 0.01 else 1.0
        sz = H_ / max(h, eps) if H_ > 0.01 else 1.0
    return sx, sy, sz


def xforms(fr, lf, pr, how="stretch", rot=0.0, mirror=(False, False)) -> list:
    """The QMatrix4x4 of each part of ``pr`` placed on the element (its
    frame ``fr``, its local faces ``lf``)."""
    from PySide6.QtGui import QMatrix4x4
    box = box_of(lf)
    sx, sy, sz = fit(box, pr, how, rot)
    x0, y0, z0, x1, y1, z1 = pr["box"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    m = QMatrix4x4()
    m.translate(fr[0], fr[1], fr[2])
    if abs(fr[3]) > 1e-9:
        m.rotate(fr[3], 0.0, 0.0, 1.0)
    m.translate((box[0] + box[3]) / 2, (box[1] + box[4]) / 2, box[2])
    m.scale(sx * (-1 if mirror[0] else 1), sy * (-1 if mirror[1] else 1),
            sz)
    if rot:
        m.rotate(float(rot), 0.0, 0.0, 1.0)
    m.translate(-cx, -cy, -z0)
    out = []
    for _mesh, xf in pr["parts"]:
        out.append(m * xf if xf is not None else QMatrix4x4(m))
    return out


def groups_for(lib, fr, lf, name, layer, ext, ifc=None,
               mirror=(False, False)) -> list | None:
    """The library model's groups for one element (None: no model — the
    element is drawn as it is)."""
    if not lib or not lib.get("key"):
        return None
    pr = proto(lib["key"], lib.get("entry"))
    if pr is None:
        return None
    from core.group import Group
    out = []
    for (mesh, _xf), xm in zip(pr["parts"], xforms(
            fr, lf, pr, lib.get("fit", "stretch"),
            float(lib.get("rot", 0.0) or 0.0), mirror)):
        g = Group(mesh, name=name)
        g.xform = xm
        g.component = True
        g.layer = layer
        if ifc:
            g.ifc = dict(ifc)
        g.ext = {k: dict(v) for k, v in ext.items()}
        out.append(g)
    return out


def clear_cache():
    _PROTO.clear()
    _LOW.clear()
