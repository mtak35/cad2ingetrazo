# SPDX-License-Identifier: GPL-3.0-or-later
"""Every element as a COMPONENT TYPE: a mark and a name («D-01 · Hinged
door, single · 3'0" × 7'0"»), so the doors, windows, columns, walls…
of one type are selected together by name and changed together.

The type is the element's own parameters (a door: its kind, leaves,
head, frame, width and height — never where it stands). Marks are kept
in ``doc["comp_names"]`` ({type key: {"mark", "name"}}): a mark once
given stays (a new type takes the next number), and a name typed by
the architect replaces the one made from the parameters.

The model is built from them too (project._groups): elements of the
same geometry share ONE definition mesh placed by instances — like a
component in SketchUp (and ten times quicker to build on a tower).
"""
from __future__ import annotations

import math
import re

from .engine import structure as S

#: the mark's letters, per kind of type
PREFIX = {"door": "D", "window": "W", "void": "V", "column": "C",
          "beam": "B", "wall": "WL", "curtain": "CW", "railing": "RL",
          "slab": "SL",
          "core": "LC", "footing": "F", "roof": "R", "room": "FF",
          "stair": "ST"}
#: the order types are listed in
ORDER = ["door", "window", "void", "column", "beam", "wall", "curtain",
         "railing", "stair", "core", "slab", "footing", "roof", "room"]
KIND_LABEL = {"door": "Doors", "window": "Windows", "void": "Openings",
              "column": "Columns", "beam": "Beams", "wall": "Walls",
              "curtain": "Curtain walls", "railing": "Railings",
              "stair": "Staircases",
              "core": "Lift cores",
              "slab": "Slabs", "footing": "Footings", "roof": "Roofs",
              "room": "Floor finishes"}

DOOR_NAMES = {"hinged": "Hinged door", "main": "Main door",
              "glass": "Glass door", "alu_glass": "Glass door, alu frame",
              "louvre": "Louvred alu door", "glazed": "Glazed door",
              "sliding": "Sliding door", "pocket": "Pocket door",
              "folding": "Folding door", "rolling": "Rolling shutter",
              "garage": "Garage door", "double": "Hinged door",
              "french": "Glazed door"}
WINDOW_NAMES = {"casement": "Casement window", "sliding": "Sliding window",
                "fixed": "Fixed window", "louvre": "Louvre window",
                "top-hung": "Top-hung window", "awning": "Top-hung window"}


def _mm(v) -> int:
    try:
        return int(round(float(v) * 1000))
    except (TypeError, ValueError):
        return 0


def _len(m) -> str:
    from .host import len_txt
    return len_txt(float(m))


def type_of(kind: str, rec: dict, walls: dict | None = None):
    """(group, key, label) of an element's type — ``group`` one of
    ``ORDER``; ``key`` a string, the same for every element of the
    type; ``label`` its description. None when it has none."""
    if kind == "opening":
        k = rec.get("kind")
        w, h = _mm(rec.get("w")), _mm(rec.get("h"))
        size = f"{_len(rec['w'])} × {_len(rec['h'])}"
        head = rec.get("head") or "flat"
        hd = "" if head == "flat" else f", {head} head"
        if k == "door":
            st = rec.get("style") or "hinged"
            lv = S.leaves_of(rec) if hasattr(S, "leaves_of") else \
                int(rec.get("leaves", 1) or 1)
            fr = S.frame_of(rec)
            two = ", double" if lv == 2 and st not in ("sliding", "rolling",
                                                      "garage", "folding") \
                else (", single" if st in S.HINGED_TYPES else "")
            label = f"{DOOR_NAMES.get(st, st.title() + ' door')}{two}{hd}" \
                    f" · {size} · {S.FRAMES[fr][0].split(' (')[0]} frame"
            return "door", f"door|{st}|{lv}|{head}|{fr}|{w}|{h}", label
        if k == "window":
            st = rec.get("style") or "sliding"
            fr = S.frame_of(rec)
            sill = _mm(rec.get("sill"))
            label = f"{WINDOW_NAMES.get(st, st.title() + ' window')}{hd}" \
                    f" · {size} · sill {_len(rec.get('sill', 0))}"
            return "window", f"window|{st}|{head}|{fr}|{w}|{h}|{sill}", label
        return "void", f"void|{w}|{h}|{_mm(rec.get('sill'))}", \
            f"Opening · {size}"
    if kind == "wall" and rec.get("rail"):
        from .engine import railings as RL
        h = rec.get("height", 1.0)
        h = 1.0 if h == "level" else float(h)
        return "railing", f"railing|{rec['rail']}|{_mm(h)}", \
            f"{RL.LABEL.get(rec['rail'], rec['rail'])} · {_len(h)} high"
    if kind == "wall":
        t = _mm(rec.get("t"))
        if rec.get("type") == "curtain":
            return "curtain", f"curtain|{t}", \
                f"Curtain wall · {_len(rec['t'])}"
        nm = str(rec.get("name", ""))
        what = "Parapet" if nm.startswith("Terrace") else "Wall"
        return "wall", f"wall|{what}|{t}", f"{what} {_len(rec['t'])}"
    if kind == "column":
        if rec.get("shape") == "poly":
            sig = ",".join(f"{_mm(p[0])}:{_mm(p[1])}"
                           for p in rec.get("pts") or [])
            n = len(rec.get("pts") or [])
            what = {6: "L", 8: "T / C"}.get(n, "shaped")
            return "column", f"column|poly|{_mm(rec.get('angle', 0))}|{sig}", \
                f"Column, {what} section {_len(rec['w'])} × {_len(rec['d'])}"
        if rec.get("shape") == "round":
            return "column", f"column|round|{_mm(rec['w'])}", \
                f"Round column Ø{_len(rec['w'])}"
        a, b = sorted((_mm(rec["w"]), _mm(rec["d"])))
        return "column", f"column|rect|{a}|{b}", \
            f"Column {_len(a / 1000)} × {_len(b / 1000)}"
    if kind == "beam":
        return "beam", f"beam|{_mm(rec['w'])}|{_mm(rec['h'])}", \
            f"Beam {_len(rec['w'])} × {_len(rec['h'])}"
    if kind == "slab":
        part = "roof slab" if rec.get("roof") else \
            ("floor part" if rec.get("user") or rec.get("zone") else "slab")
        return "slab", f"slab|{part}|{_mm(rec['t'])}", \
            f"{part.capitalize()} {_len(rec['t'])}"
    if kind == "core":
        return "core", "core", "Lift core (RCC)"
    if kind == "footing":
        fk = rec.get("kind", "pad")
        return "footing", f"footing|{fk}|{_mm(rec.get('w'))}|" \
            f"{_mm(rec.get('d'))}", \
            f"{fk.capitalize()} footing {_len(rec.get('w', 0))}"
    if kind == "roof":
        return "roof", f"roof|{rec.get('kind', 'flat')}", \
            f"{str(rec.get('kind', 'flat')).capitalize()} roof"
    if kind == "stair":
        from . import stairs as ST
        fl, _lg = ST.as_flights(rec)
        n = int(rec.get("risers") or 0)
        w = max((float(f.get("w", 0) or 0) for f in fl), default=0.0)
        shape = {1: "Straight", 2: "Dog-leg", 3: "Three-flight"}.get(
            len(fl), f"{len(fl)}-flight")
        stype = rec.get("stype", "monolithic")
        what = {"monolithic": "RCC", "solid": "solid", "open": "open riser",
                "cantilever": "cantilever"}.get(stype, stype)
        return "stair", f"stair|{stype}|{len(fl)}|{n}|{_mm(rec.get('rise'))}" \
            f"|{_mm(w)}", f"{shape} stair, {what} · {n} risers of " \
            f"{_len(rec.get('rise', 0))} · {_len(w)} wide"
    if kind == "stairrail":
        from .engine import railings as RL
        r_ = rec.get("rail", "ss_bars")
        if not r_ or r_ == "none":
            return None
        h = float(rec.get("rail_h") or 0.9)
        sd = rec.get("rail_sides", "inner")
        if sd == "none":
            return None
        off = float(rec.get("rail_off") or 0.0)
        gap = float(rec.get("rail_gap") or 0.0)
        ext = float(rec.get("rail_ext") or 0.0)
        side = {"inner": "well side", "outer": "wall side",
                "both": "both sides"}.get(sd, sd)
        extra = (f" · balusters @ {_len(gap)}" if gap else "") + \
            (f" · run-on {_len(ext)}" if ext else "")
        return "railing", f"srail|{r_}|{_mm(h)}|{sd}|{_mm(off)}|{_mm(gap)}" \
            f"|{_mm(ext)}", \
            f"Stair railing · {RL.LABEL.get(r_, r_)} · {_len(h)} · " \
            f"{side}{extra}"
    if kind == "room":
        return "room", f"room|{_mm(rec.get('finish_t', 0))}", \
            f"Floor finish {_len(rec.get('finish_t', 0))}"
    return None


def _mark_num(m: str) -> int:
    g = re.search(r"(\d+)$", m or "")
    return int(g.group(1)) if g else 0


def sync(doc, found: dict) -> dict:
    """Marks for the types ``found`` ({key: (group, label)}): kept from
    before, a new type the next number of its letters. Returns
    {key: {"mark", "name", "label", "group"}}."""
    names = doc.setdefault("comp_names", {})
    out = {}
    taken = {}
    for k, v in names.items():
        p = v.get("mark", "").split("-")[0]
        taken.setdefault(p, set()).add(_mark_num(v.get("mark", "")))
    for grp in ORDER:
        new = sorted((lab, k) for k, (g, lab) in found.items()
                     if g == grp and k not in names)
        p = PREFIX[grp]
        used = taken.setdefault(p, set())
        n = max(used, default=0)
        for _lab, k in new:
            n += 1
            used.add(n)
            names[k] = {"mark": f"{p}-{n:02d}"}
    for k, (g, lab) in found.items():
        v = names[k]
        out[k] = {"mark": v["mark"], "name": v.get("name") or lab,
                  "label": lab, "group": g, "lib": v.get("lib")}
    return out


def display(t: dict) -> str:
    return f"{t['mark']} · {t['name']}"


def catalogue(doc) -> dict:
    """{type key: {"mark", "name", "label", "group", "items": [(kind,
    id, level)]}} — every element of the building by its type."""
    arch = doc["arch"]
    walls = {w["id"]: w for w in arch["walls"]}
    found, items = {}, {}

    def add(kind, rec):
        t = type_of(kind, rec, walls)
        if t is None:
            return
        g, k, lab = t
        found.setdefault(k, (g, lab))
        lv = rec.get("level") or (walls.get(rec.get("wall")) or {}).get(
            "level")
        items.setdefault(k, []).append((kind, rec["id"], lv))
    for w in arch["walls"]:
        add("wall", w)
    for o in arch["openings"]:
        add("opening", o)
    for e in arch["structure"]:
        add(e["type"], e)
    from . import stairs as ST
    stt = doc.get("settings") or {}
    for s_ in doc.get("stairs") or []:
        r_ = dict(s_, **ST.eff(s_, stt))
        add("stair", r_)
        add("stairrail", r_)
    if (doc.get("settings") or {}).get("finish_on", True):
        from . import project as PJ
        from .engine import spaces
        for lv in arch["levels"]:
            lid = lv["id"]
            if not any(w["level"] == lid for w in arch["walls"]):
                continue
            for room in spaces.of_level(arch, lid):
                if room["area"] < 1.0:
                    continue
                f = PJ.room_finish(doc, room.get("rec"))
                if f < 0.001:
                    continue
                add("room", {"id": PJ.room_key(lid, room), "level": lid,
                             "finish_t": f})
    out = sync(doc, found)
    for k, v in out.items():
        v["items"] = items.get(k, [])
    return out


def key_of(doc, kind, rec):
    if kind in ("stair", "stairrail"):
        from . import stairs as ST
        rec = dict(rec, **ST.eff(rec, doc.get("settings") or {}))
    t = type_of(kind, rec, {w["id"]: w for w in doc["arch"]["walls"]})
    return t[1] if t else None


# ---- shared definitions: elements of one geometry, ONE mesh ---------------------
def frame_of_element(e, arch, walls, z0) -> tuple:
    """(ox, oy, oz, angle°) the element's geometry is taken into before it
    is compared: a door / window on its wall's line at its centre, a
    column on its point and angle, anything else at the plan's origin on
    its level (the same wall on two typical floors is ONE shape)."""
    if e["kind"] == "opening":
        o = next((x for x in arch["openings"] if x["id"] == e["id"]), None)
        w = walls.get(o["wall"]) if o else None
        if w is not None and w.get("kind", "line") == "line":
            from .engine import walls as W
            seg = W.centre(w)
            if hasattr(seg, "u") and hasattr(seg, "p0"):
                u = seg.u
                pos = float(o["pos"])
                return (seg.p0[0] + u[0] * pos, seg.p0[1] + u[1] * pos, z0,
                        math.degrees(math.atan2(u[1], u[0])))
    if e["kind"] == "column":
        c = next((x for x in arch["structure"] if x["id"] == e["id"]), None)
        if c is not None:
            return (float(c["x"]), float(c["y"]), z0,
                    float(c.get("angle", 0.0) or 0.0))
    return (0.0, 0.0, z0, 0.0)


def local_faces(faces, fr):
    """The faces in the frame ``fr``: [(loop, holes, colour)]."""
    ox, oy, oz, ang = fr
    a = math.radians(ang)
    c, s = math.cos(a), math.sin(a)

    def L(q):
        x, y = q[0] - ox, q[1] - oy
        return (x * c + y * s, -x * s + y * c, q[2] - oz)
    out = []
    for f in faces:
        if isinstance(f, dict):
            out.append(([L(q) for q in f["loop"]],
                        [[L(q) for q in h] for h in f.get("holes") or []],
                        tuple(f["color"]) if f.get("color") is not None
                        else None))
        else:
            out.append(([L(q) for q in f], [], None))
    return out


def shape_key(lf) -> int:
    """The same for two elements of the same geometry (to the mm)."""
    def r(q):
        return (round(q[0], 3), round(q[1], 3), round(q[2], 3))
    return hash(tuple((tuple(r(q) for q in lp),
                       tuple(tuple(r(q) for q in h) for h in hs), col)
                      for lp, hs, col in lf))


def placement(fr):
    from PySide6.QtGui import QMatrix4x4
    m = QMatrix4x4()
    m.translate(fr[0], fr[1], fr[2])
    if abs(fr[3]) > 1e-9:
        m.rotate(fr[3], 0.0, 0.0, 1.0)
    return m
