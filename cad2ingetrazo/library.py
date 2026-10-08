# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo's own component library (``resources/components/*.igz`` —
the doors, windows, furniture, cars… of Properties ▸ Components) as the
model of a CAD2IngeTrazo component type: every element of the type shows
the library model instead, fitted to the element's own box (stretched to
it, or scaled evenly to fit inside it), turned as asked.

The choice lives on the type: ``doc["comp_names"][type key]["lib"] =
{"key": "doors/door_single", "fit": "stretch" | "keep", "rot": 0|90|180|270}``
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


def list_all() -> list:
    """[(key, label)] of every library component, by folder and name."""
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
        out = []
        for p in sorted(root.rglob("*.igz")):
            key = p.relative_to(root).with_suffix("").as_posix()
            nm, tip = names.get(key, (label_of(key), ""))
            out.append((key, f"{nm} — {tip}" if tip else nm))
        out.sort(key=lambda kv: kv[1].lower())
        return out
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("library.list_all")
        return []


def proto(key: str):
    """{"parts": [(mesh, QMatrix4x4 | None)], "box": (x0, y0, z0, x1, y1,
    z1)} of a library component, or None (missing / unreadable)."""
    if key in _PROTO:
        return _PROTO[key]
    rec = None
    try:
        from core.scene import Scene
        from formats import igz
        path = folder() / f"{key}.igz"
        if path.exists():
            tmp = Scene()
            igz.load_into(tmp, path)
            parts, lo, hi = [], [1e18] * 3, [-1e18] * 3
            for g in tmp.groups:
                m = getattr(g, "mesh", None)
                if m is None:
                    continue
                xf = getattr(g, "xform", None)
                for v in m.vertices:
                    p = v.position
                    if xf is not None:
                        p = xf.map(p)
                    for i, c in enumerate((p.x(), p.y(), p.z())):
                        lo[i] = min(lo[i], c)
                        hi[i] = max(hi[i], c)
                parts.append((m, xf))
            if parts and hi[0] > lo[0]:
                rec = {"parts": parts, "box": (*lo, *hi)}
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("library.proto")
        rec = None
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


def xforms(fr, lf, pr, how="stretch", rot=0.0) -> list:
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
    m.scale(sx, sy, sz)
    if rot:
        m.rotate(float(rot), 0.0, 0.0, 1.0)
    m.translate(-cx, -cy, -z0)
    out = []
    for _mesh, xf in pr["parts"]:
        out.append(m * xf if xf is not None else QMatrix4x4(m))
    return out


def groups_for(lib, fr, lf, name, layer, ext, ifc=None) -> list | None:
    """The library model's groups for one element (None: no model — the
    element is drawn as it is)."""
    if not lib or not lib.get("key"):
        return None
    pr = proto(lib["key"])
    if pr is None:
        return None
    from core.group import Group
    out = []
    for (mesh, _xf), xm in zip(pr["parts"], xforms(
            fr, lf, pr, lib.get("fit", "stretch"),
            float(lib.get("rot", 0.0) or 0.0))):
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
