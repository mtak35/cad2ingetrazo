# SPDX-License-Identifier: GPL-3.0-or-later
"""Domes: a mosque's, a shrine's, a pavilion's — of their kind and size,
on a drum, with a finial, over a room or at a point, on top of a level.

``doc["domes"]``: [{"id", "level" (it stands on that level's top), "x",
"y", "d" (diameter, m), "kind", "rise" (its height over the diameter, 0 =
the kind's own), "drum" (drum height, m), "finial" (bool), "color"}].
``groups(doc)`` builds them (a solid of revolution each, low-poly unless
«High poly»).
"""
from __future__ import annotations

import math
import uuid

#: (key, label, rise / diameter)
KINDS = [("hemi", "Hemispherical", 0.50),
         ("onion", "Onion (Mughal)", 1.05),
         ("pointed", "Pointed / ogival (Fatimid, Gothic)", 0.75),
         ("bulbous", "Bulbous (Persian / Timurid)", 0.85),
         ("saucer", "Shallow saucer (Ottoman)", 0.28),
         ("ribbed", "Ribbed (melon, Timurid)", 0.55),
         ("conical", "Conical / tented (Seljuk)", 0.70)]
RISE = {k: r for k, _l, r in KINDS}

#: (key, label, rgb)
FINISHES = [("white", "White plaster / marble", (0.95, 0.94, 0.91)),
            ("gold", "Gold", (0.86, 0.69, 0.25)),
            ("green", "Green tiles", (0.18, 0.52, 0.36)),
            ("blue", "Blue tiles (Persian)", (0.15, 0.42, 0.66)),
            ("copper", "Copper (patina)", (0.36, 0.62, 0.55)),
            ("stone", "Sandstone", (0.82, 0.68, 0.50))]
COLOR = {k: c for k, _l, c in FINISHES}


def _smooth(ctrl, n=40):
    """A smooth curve through control points (s, r) — Catmull-Rom."""
    pts = [ctrl[0]] + list(ctrl) + [ctrl[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        k = max(2, n // (len(ctrl) - 1))
        for j in range(k):
            t = j / k
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * t +
                                    (2 * p0[c] - 5 * p1[c] + 4 * p2[c] -
                                     p3[c]) * t2 +
                                    (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c])
                                    * t3) for c in (0, 1)))
    out.append(ctrl[-1])
    return out


def profile(kind, R, H, k=24):
    """The dome's outline [(r, z)] from its spring (R, 0) to its top
    (0, H)."""
    if kind in ("hemi", "ribbed"):
        return [(R * math.cos(math.pi / 2 * i / k),
                 H * math.sin(math.pi / 2 * i / k)) for i in range(k + 1)]
    if kind == "saucer":
        Rs = (R * R + H * H) / (2 * H)
        zc = H - Rs
        a0 = math.asin(max(-1.0, min(1.0, R / Rs)))
        return [(Rs * math.sin(a0 * (1 - i / k)),
                 zc + Rs * math.cos(a0 * (1 - i / k))) for i in range(k + 1)]
    if kind == "pointed":
        if H <= R:
            return profile("hemi", R, H, k)
        e = (H * H - R * R) / (2 * R)
        Rr = R + e
        a1 = math.atan2(H, e)
        return [(Rr * math.cos(a1 * i / k) - e, Rr * math.sin(a1 * i / k))
                for i in range(k + 1)]
    if kind == "conical":
        return [(R * (1 - i / k), H * (i / k) ** 1.15) for i in range(k + 1)]
    ctrl = {"onion": [(0.0, 1.0), (0.10, 1.10), (0.28, 1.17), (0.46, 1.05),
                      (0.62, 0.72), (0.76, 0.38), (0.88, 0.16),
                      (0.95, 0.07), (1.0, 0.0)],
            "bulbous": [(0.0, 1.0), (0.18, 1.07), (0.40, 1.02),
                        (0.62, 0.74), (0.80, 0.42), (0.93, 0.15),
                        (1.0, 0.0)]}.get(kind)
    if ctrl is None:
        return profile("hemi", R, H, k)
    return [(R * max(r_, 0.0), H * s) for s, r_ in _smooth(ctrl, 2 * k)]


def _lathe(prof, z0, cx, cy, n, color, ribs=0, closed_bottom=True):
    """Faces of ``prof`` [(r, z)] turned round the vertical at (cx, cy)."""
    out = []
    rings = []
    for r, z in prof:
        ring = []
        for j in range(n):
            th = 2 * math.pi * j / n
            rr = r
            if ribs:
                rr = r * (1.0 + 0.035 * max(0.0, math.cos(ribs * th)) ** 6)
            ring.append((cx + rr * math.cos(th), cy + rr * math.sin(th),
                         z0 + z))
        rings.append((r, ring))
    for (ra, A), (rb, B) in zip(rings, rings[1:]):
        for j in range(n):
            j2 = (j + 1) % n
            if rb < 1e-6 and ra < 1e-6:
                continue
            if rb < 1e-6:                    # to the tip: triangles
                loop = [A[j], A[j2], B[0]]
            elif ra < 1e-6:
                loop = [A[0], B[j2], B[j]]
            else:
                loop = [A[j], A[j2], B[j2], B[j]]
            out.append({"loop": loop, "holes": [], "color": color})
    if closed_bottom and prof[0][0] > 1e-6:
        out.append({"loop": list(reversed(rings[0][1])), "holes": [],
                    "color": color})
    return _outward(out, cx, cy)


def _outward(faces, cx, cy):
    """Every face turned to look out: the sides away from the axis, the
    near-flat ones up at the top and down at the bottom."""
    zs = [p[2] for f in faces for p in f["loop"]]
    if not zs:
        return faces
    zm = (min(zs) + max(zs)) / 2
    for f in faces:
        lp = f["loop"]
        n = [0.0, 0.0, 0.0]
        for i in range(len(lp)):
            a, b = lp[i], lp[(i + 1) % len(lp)]
            n[0] += (a[1] - b[1]) * (a[2] + b[2])
            n[1] += (a[2] - b[2]) * (a[0] + b[0])
            n[2] += (a[0] - b[0]) * (a[1] + b[1])
        L = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
        c = [sum(p[k] for p in lp) / len(lp) for k in range(3)]
        if abs(n[2]) > 0.9 * L:
            want_up = c[2] > zm
            flip = (n[2] > 0) != want_up
        else:
            flip = n[0] * (c[0] - cx) + n[1] * (c[1] - cy) < 0
        if flip:
            f["loop"] = list(reversed(lp))
    return faces


def build(dome, z_base, hi=False):
    """[(part name, faces, rgb)] of one dome standing at ``z_base``."""
    R = max(float(dome.get("d", 6.0)), 0.5) / 2
    kind = dome.get("kind", "hemi")
    rise = float(dome.get("rise") or 0.0) or RISE.get(kind, 0.5)
    H = max(rise * 2 * R, 0.2)
    n = 64 if hi else 32
    col = COLOR.get(dome.get("color", "white"), COLOR["white"])
    trim = (0.93, 0.92, 0.88)
    cx, cy = float(dome["x"]), float(dome["y"])
    parts = []
    z = z_base
    # a square base block and stepped tiers over it (the dome raised over
    # the roof, its tiers set back), as the elevations draw them
    base_h = max(float(dome.get("base_h", 0.0) or 0.0), 0.0)
    nst = int(dome.get("steps", 0) or 0)
    if base_h > 0.01 or nst:
        from shapely.geometry import box as _box

        from . import project as PJ_
        from shapely import affinity as _af
        rot_ = float(dome.get("rot", 0.0) or 0.0)

        def _sq(w_):                  # the block / a tier, turned to the building
            b_ = _box(cx - w_ / 2, cy - w_ / 2, cx + w_ / 2, cy + w_ / 2)
            return _af.rotate(b_, rot_, origin=(cx, cy)) if rot_ else b_
        bw = 2 * R * float(dome.get("base_w", 1.45) or 1.45)
        if base_h > 0.01:
            parts.append(("base", [dict(f, color=trim) for f in PJ_._prism(
                _sq(bw), z, z + base_h, 1e-5)], trim))
            z += base_h
        sh = float(dome.get("step_h", 0.45) or 0.45)
        for i in range(nst):
            w_ = bw - (i + 1) * (bw - 2.05 * R) / max(nst, 1)
            parts.append(("tier", [dict(f, color=trim) for f in PJ_._prism(
                _sq(w_), z, z + sh, 1e-5)], trim))
            z += sh
    drum = max(float(dome.get("drum", 0.0) or 0.0), 0.0)
    if drum > 0.01:                          # the drum, a band round its top
        parts.append(("drum", _lathe([(R * 1.02, 0.0), (R * 1.02, drum)],
                                     z, cx, cy, n, trim), trim))
        parts.append(("cornice", _lathe([(R * 1.08, 0.0), (R * 1.08, 0.12),
                                         (R * 1.02, 0.18)], z + drum - 0.18,
                                        cx, cy, n, trim), trim))
        z += drum
    k = 32 if hi else 18
    prof = profile(kind, R, H, k)
    parts.append(("dome", _lathe(prof, z, cx, cy, n, col,
                                 ribs=16 if kind == "ribbed" else 0), col))
    if dome.get("finial", True):             # a finial (kalash, rod, moon)
        fh = min(max(0.18 * 2 * R, 0.6), 3.0)
        fr = fh * 0.12
        ztop = z + prof[-1][1]
        if kind in ("hemi", "ribbed", "saucer"):
            ztop -= 0.02
        fp = [(fr * 0.9, 0.0), (fr * 1.4, fh * 0.12), (fr * 0.5, fh * 0.24),
              (fr * 1.1, fh * 0.36), (fr * 1.2, fh * 0.44),
              (fr * 0.35, fh * 0.56), (fr * 0.8, fh * 0.66),
              (fr * 0.18, fh * 0.74), (fr * 0.12, fh * 0.97), (0.0, fh)]
        parts.append(("finial", _lathe(fp, ztop, cx, cy, 16 if not hi else 24,
                                       COLOR["gold"]), COLOR["gold"]))
    return parts


def new(doc, level, x, y, d, kind="hemi", rise=0.0, drum=0.0, finial=True,
        color="white") -> dict:
    rec = {"id": uuid.uuid4().hex[:8], "level": level, "x": round(x, 4),
           "y": round(y, 4), "d": round(max(d, 0.5), 3), "kind": kind,
           "rise": round(rise, 3), "drum": round(drum, 3),
           "finial": bool(finial), "color": color}
    doc.setdefault("domes", []).append(rec)
    return rec


def over_room(doc, lid, pt=None):
    """(x, y, diameter) for a dome over the room at ``pt`` (else the
    level's biggest room): its centre, the biggest circle in it."""
    from shapely.geometry import Point
    from shapely.ops import polylabel

    from .engine import spaces
    rooms = spaces.of_level(doc["arch"], lid)
    if not rooms:
        return None
    room = None
    if pt is not None:
        room = next((r for r in rooms if r["poly"].contains(Point(pt))),
                    None)
    room = room or max(rooms, key=lambda r: r["area"])
    c = polylabel(room["poly"], tolerance=0.05)
    rad = room["poly"].exterior.distance(c)
    return c.x, c.y, round(2 * rad, 2)


def load(raw) -> list:
    out = []
    for d in raw or []:
        if not isinstance(d, dict) or d.get("kind") not in RISE:
            continue
        try:
            out.append({"id": str(d.get("id") or uuid.uuid4().hex[:8]),
                        "level": str(d["level"]), "x": float(d["x"]),
                        "y": float(d["y"]),
                        "d": min(max(float(d["d"]), 0.5), 80.0),
                        "kind": d["kind"],
                        "rise": min(max(float(d.get("rise") or 0.0), 0.0),
                                    3.0),
                        "drum": min(max(float(d.get("drum") or 0.0), 0.0),
                                    20.0),
                        "finial": bool(d.get("finial", True)),
                        "base_h": min(max(float(d.get("base_h") or 0.0), 0.0),
                                      30.0),
                        "steps": min(max(int(d.get("steps") or 0), 0), 6),
                        "step_h": min(max(float(d.get("step_h") or 0.45),
                                          0.05), 3.0),
                        "base_w": min(max(float(d.get("base_w") or 1.45),
                                          1.0), 3.0),
                        "rot": float(d.get("rot") or 0.0) % 360.0,
                        "color": d.get("color") if d.get("color") in COLOR
                        else "white"})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def groups(doc):
    """The domes' groups (one per dome, on its level's layer)."""
    from core.group import Group

    from . import project as PJ
    from .host import KEY, level_layer
    arch = doc["arch"]
    elev = PJ.elevations(arch)
    idx = {lv["id"]: i for i, lv in enumerate(arch["levels"])}
    hi = bool(doc["settings"].get("hi_poly", False))
    slab_t = float(doc["settings"].get("slab_t", 0.1016) or 0.1016)
    out = []
    for k, dm in enumerate(doc.get("domes") or [], 1):
        i = idx.get(dm["level"])
        if i is None:
            continue
        lv = arch["levels"][i]
        z0 = elev[i] + float(lv["height"]) + slab_t
        faces = []
        for _nm, fs, _c in build(dm, z0, hi):
            faces += fs
        if not faces:
            continue
        label = dict((a, b) for a, b, _r in KINDS).get(dm["kind"], "Dome")
        g = Group(PJ._mesh_of(faces),
                  name=f"Dome {k} · {label} Ø{dm['d']:.2f} m · {lv['name']}")
        g.component = False
        g.material = {"color": COLOR.get(dm.get("color"), COLOR["white"]),
                      "opacity": 1.0}
        g.layer = level_layer(lv["name"])
        g.ifc = {"class": "IfcRoof", "name": f"Dome {k}"}
        g.ext = {KEY: {"type": "dome", "id": dm["id"], "level": dm["level"]}}
        out.append(g)
    return out
