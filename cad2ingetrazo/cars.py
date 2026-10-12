# SPDX-License-Identifier: GPL-3.0-or-later
"""Cars in the parking bays: IngeTrazo's own component library models
(the SUV and the pickup of Properties ▸ Components), one instance per
bay — they share one mesh, so a hundred cars cost one car."""
from __future__ import annotations

import math

#: the library's cars: key → (label)
MODELS = [("suv", "SUV"), ("pickup", "Pickup"), ("mixed", "Mixed (SUV, pickup)")]
_PROTO: dict = {}


def proto(key: str):
    """(mesh, (cx, cy, z0), length, width) of a library car, its length
    along +Y as the library has it; None when the file is missing."""
    if key in _PROTO:
        return _PROTO[key]
    try:
        from pathlib import Path

        from core.paths import app_root
        from core.scene import Scene
        from formats import igz
        path = Path(app_root()) / "resources" / "components" / f"{key}.igz"
        if not path.exists():
            _PROTO[key] = None
            return None
        tmp = Scene()
        igz.load_into(tmp, path)
        if not tmp.groups:
            _PROTO[key] = None
            return None
        mesh = tmp.groups[0].mesh
        vs = list(mesh.vertices)
        xs = [v.position.x() for v in vs]
        ys = [v.position.y() for v in vs]
        zs = [v.position.z() for v in vs]
        L, W = max(ys) - min(ys), max(xs) - min(xs)
        rec = (mesh, ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                      min(zs)), max(L, W), min(L, W), L >= W)
        _PROTO[key] = rec
        return rec
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("cars.proto")
        _PROTO[key] = None
        return None


def pick(model: str, k: int) -> str:
    if model == "mixed":
        return "pickup" if k % 4 == 3 else "suv"
    return model if model in ("suv", "pickup") else "suv"


def placement(stall: dict, z: float, pr) -> "QMatrix4x4":
    """The car's placement in its bay: centred, along the bay's length,
    scaled down when the model is longer than the bay (less 0.3 m)."""
    from PySide6.QtGui import QMatrix4x4
    _mesh, (cx, cy, cz), L, W, along_y = pr
    bayL = float(stall.get("L", 4.8))
    bayW = float(stall.get("W", 2.4))
    sc = min(1.0, (bayL - 0.3) / L, (bayW - 0.2) / W) if L > 0 else 1.0
    ang = float(stall.get("ang", 90.0)) - (90.0 if along_y else 0.0)
    m = QMatrix4x4()
    m.translate(float(stall["c"][0]), float(stall["c"][1]), z + 0.005)
    m.rotate(ang, 0.0, 0.0, 1.0)
    m.scale(sc)
    m.translate(-cx, -cy, -cz)
    return m


def groups(stalls, z, model, layer, tag_of_k, name_of_k) -> list:
    """One car instance per bay."""
    from core.group import Group
    out = []
    for k, sl in enumerate(stalls):
        pr = proto(pick(model, k))
        if pr is None:
            pr = proto("suv")
        if pr is None:
            return out
        g = Group(pr[0], name=name_of_k(k))
        g.xform = placement(sl, z, pr)
        g.component = True
        g.layer = layer
        g.ext = tag_of_k(k)
        out.append(g)
    return out


# ---- motorbikes: a model of IngeTrazo's library, as the cars --------------
_BIKE_RE = None
_BIKE_AUTO: dict = {}


def bike_entry(st) -> tuple | None:
    """(library key, catalogue entry, name) of the motorbike model: the one
    picked in the panel (``settings["bike_lib"]``), else the first motorbike
    / scooter in IngeTrazo's online catalogue; None (offline, none there)."""
    global _BIKE_RE
    lib = st.get("bike_lib") or {}
    if lib.get("key"):
        return lib["key"], lib.get("entry"), lib.get("name", "")
    if "auto" in _BIKE_AUTO:
        return _BIKE_AUTO["auto"]
    import re
    if _BIKE_RE is None:
        _BIKE_RE = re.compile(r"moto|bike|scooter|vespa|harley|ducati|"
                              r"yamaha|honda\s*cb|kawasaki", re.I)
    found = None
    try:
        from . import library as LB
        for e in LB.list_entries():
            txt = " ".join(str(e.get(k, "")) for k in ("name", "tip")) + \
                " " + " ".join(str((e.get("entry") or {}).get(k, ""))
                               for k in ("nombre", "nombre_en", "id"))
            if _BIKE_RE.search(txt) and not re.search(r"bicic|bicycle|cycl"
                                                       r"ist|ciclis", txt,
                                                       re.I):
                found = (e["key"], e.get("entry"), e.get("name", ""))
                break
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("cars.bike_entry")
    if found is not None:
        _BIKE_AUTO["auto"] = found
    return found


def bike_groups(stalls, z, st, layer, tag_of_k, name_of_k) -> list | None:
    """A library motorbike in every space (its parts shared by every
    instance), or None when there is no library model to use."""
    be = bike_entry(st)
    if be is None:
        return None
    from PySide6.QtGui import QMatrix4x4

    from core.group import Group

    from . import library as LB
    pr = LB.proto(be[0], be[1])
    if pr is None:
        return None
    x0, y0, z0, x1, y1, z1 = pr["box"]
    w, d = x1 - x0, y1 - y0
    along_y = d >= w
    L, W = max(w, d), min(w, d)
    if L <= 0:
        return None
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for k, sl in enumerate(stalls):
        bayL = float(sl.get("L", 2.0))
        bayW = float(sl.get("W", 0.9))
        # its real size (about 2 m): only made smaller to fit its space
        sc = min(1.0, max(bayL - 0.15, 0.8) / L, max(bayW - 0.05, 0.4) / W)
        if L < 1.0:                      # a model drawn in other units
            sc = 2.0 / L
        m = QMatrix4x4()
        m.translate(float(sl["c"][0]), float(sl["c"][1]), z + 0.005)
        m.rotate(float(sl.get("ang", 0.0)) - (90.0 if along_y else 0.0),
                 0.0, 0.0, 1.0)
        m.scale(sc)
        m.translate(-cx, -cy, -z0)
        for mesh, xf in pr["parts"]:
            g = Group(mesh, name=name_of_k(k))
            g.xform = m * xf if xf is not None else QMatrix4x4(m)
            g.component = True
            g.layer = layer
            g.ext = tag_of_k(k)
            out.append(g)
    return out
