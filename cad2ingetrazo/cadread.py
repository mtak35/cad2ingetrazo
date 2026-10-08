# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a CAD floor plan: every line, closed outline, circle and text of
a DXF / DWG, placed on the model by an insertion point, in METRES.

``read(path, unit=None)`` → a drawing in its own units (cached by file);
``place(drawing, base, insert, rot)`` → the same, moved onto the model:

    {"segs":  [[x0, y0, x1, y1, layer_index]…],
     "loops": [{"layer", "pts": [[x, y]…]}],      closed polylines
     "circles": [{"layer", "c": [x, y], "r"}],
     "texts": [{"layer", "text", "x", "y", "h", "rot"}],
     "layers": [names], "unit": m per drawing unit,
     "insbase": [x, y], "extents": [x0, y0, x1, y1]}   (drawing units)
"""
from __future__ import annotations

import math
from pathlib import Path

_INSUNITS_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0,
               7: 1000.0, 10: 0.9144}
SAGITTA_M = 0.01

#: where the drawing's base point is taken from
BASE_MODES = [("origin", "Drawing origin (0,0)"),
              ("insbase", "Drawing base point ($INSBASE)"),
              ("extents_ll", "Extents — lower-left"),
              ("extents_c", "Extents — centre"),
              ("custom", "A point you give (e.g. grid A/1)")]
UNITS = [("auto", "Auto (header, checked)", None), ("mm", "Millimetres", 0.001),
         ("cm", "Centimetres", 0.01), ("m", "Metres", 1.0),
         ("in", "Inches", 0.0254), ("ft", "Feet", 0.3048)]


class CadError(Exception):
    pass


def _open(path: Path):
    import logging                 # the reader's notes on AutoCAD-only
    logging.getLogger("ezdxf").setLevel(logging.ERROR)   # objects: quiet
    try:
        from formats.dxf_in import open_document
        return open_document(path)
    except ImportError:
        import ezdxf
        from ezdxf import recover
        try:
            return ezdxf.readfile(str(path))
        except ezdxf.DXFStructureError:
            return recover.readfile(str(path))[0]


def _unit(doc, forced):
    if forced:
        return float(forced), "set by you"
    try:
        from formats.dxf_in import suggest_unit_scale
        scale, code = suggest_unit_scale(doc)
        if scale:
            return float(scale), f"auto ($INSUNITS={code}, checked)"
    except ImportError:
        pass
    code = int(doc.header.get("$INSUNITS", 0) or 0)
    if code in _INSUNITS_M:
        return _INSUNITS_M[code], f"header $INSUNITS={code}"
    return 0.001, "no units in the file — millimetres assumed"


_cache: dict = {}


def _sibling_dxf(path: Path):
    """A DXF beside a DWG, the same name (AutoCAD: SAVEAS → DXF)."""
    for suf in (".dxf", ".DXF", ".Dxf"):
        q = path.with_suffix(suf)
        if q.is_file():
            return q
    return None


def _acad_console():
    """AutoCAD's console engine (accoreconsole.exe), newest installed."""
    import glob
    import os
    hits = []
    for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 r"C:\Program Files"):
        hits += glob.glob(os.path.join(root, "Autodesk", "*",
                                       "accoreconsole.exe"))
    return sorted(set(hits))[-1] if hits else None


def _dxf_cache_dir() -> Path:
    import os
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") \
        or os.path.expanduser("~")
    d = Path(base) / "ingetrazo" / "c2i_dxf"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _acad_dxf(path: Path):
    """The DWG saved as DXF by AutoCAD's own engine (no window opens):
    kept in a cache, made again only when the DWG changes. None without
    AutoCAD or when it fails."""
    import hashlib
    import shutil
    import subprocess
    import tempfile
    exe = _acad_console()
    if not exe:
        return None
    st = path.stat()
    key = hashlib.md5(f"{path.resolve()}|{st.st_mtime}|{st.st_size}"
                      .encode("utf-8")).hexdigest()[:16]
    dst = _dxf_cache_dir() / f"{path.stem[:40]}_{key}.dxf"
    if dst.is_file() and dst.stat().st_size > 1000:
        return dst
    with tempfile.TemporaryDirectory(prefix="c2i_acc_") as wd:
        dwg = Path(wd) / "in.dwg"
        out = Path(wd) / "out.dxf"
        shutil.copy2(path, dwg)
        scr = Path(wd) / "conv.scr"
        scr.write_text('FILEDIA 0\n_.DXFOUT\n"%s"\n_V\n2018\n16\n'
                       % str(out).replace("\\", "/"), encoding="ascii")
        subprocess.run([exe, "/i", str(dwg), "/s", str(scr),
                        "/l", "en-US"], capture_output=True, timeout=900,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW",
                                             0))
        if not out.is_file() or out.stat().st_size < 1000:
            return None
        shutil.move(str(out), str(dst))
    for old in _dxf_cache_dir().glob(f"{path.stem[:40]}_*.dxf"):
        if old != dst:                     # an older version of this DWG
            try:
                old.unlink()
            except OSError:
                pass
    return dst


def _oda_exe():
    """The free ODA File Converter, when installed (Windows)."""
    import glob
    import os
    for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)",
                                r"C:\Program Files (x86)")):
        hits = sorted(glob.glob(os.path.join(root, "ODA", "*",
                                             "ODAFileConverter.exe")))
        if hits:
            return hits[-1]
    return None


def _oda_dxf(path: Path):
    """The DWG converted by the ODA File Converter into a DXF beside it
    (<name>.dxf) — the DWGs LibreDWG cannot read. None when it is not
    installed or fails."""
    exe = _oda_exe()
    if not exe:
        return None
    import shutil
    import subprocess
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as ind, \
                tempfile.TemporaryDirectory() as outd:
            shutil.copy2(path, Path(ind) / "in.dwg")
            subprocess.run([exe, ind, outd, "ACAD2018", "DXF", "0", "1",
                            "in.dwg"], timeout=600,
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
            got = Path(outd) / "in.dxf"
            if not got.is_file() or got.stat().st_size < 1000:
                return None
            dst = path.with_suffix(".dxf")
            shutil.copy2(got, dst)
            return dst
    except Exception:  # noqa: BLE001
        return None


def read(path, unit=None) -> dict:
    """The drawing in its own units; DWG through the host's converter —
    and when the converter cannot read it (a DWG saved by a newer
    AutoCAD), the DXF saved beside it."""
    path = Path(path)
    if path.suffix.lower() == ".dwg":
        try:
            res = _read(path, unit)
            if len(res["segs"]) < 10 and path.stat().st_size > 200_000:
                # a big DWG read as (almost) nothing: the converter failed
                raise CadError("the DWG converter gave an empty drawing")
            return res
        except Exception as e:  # noqa: BLE001
            # converted by AutoCAD itself (its console engine, no window),
            # else the ODA converter, else a DXF saved beside it
            for conv in (_acad_dxf, _oda_dxf, _sibling_dxf):
                try:
                    alt = conv(path)
                except Exception:  # noqa: BLE001
                    alt = None
                if alt is not None:
                    try:
                        res = _read(alt, unit)
                    except Exception:  # noqa: BLE001
                        continue
                    if len(res["segs"]) >= 10:
                        return res
            raise CadError(
                f"This DWG could not be read ({e.__class__.__name__}): "
                "IngeTrazo's DWG converter (LibreDWG) does not read every "
                "DWG, and AutoCAD could not convert it here either. In "
                "AutoCAD: RECOVER, then SAVEAS → «AutoCAD 2018 DXF», "
                f"same name, beside it ({path.with_suffix('.dxf').name}) — "
                "the plugin then reads that DXF by itself. (Or install the "
                "free ODA File Converter — the plugin then converts "
                "such DWGs itself.)") from e
    return _read(path, unit)


def _read(path, unit=None) -> dict:
    path = Path(path)
    if not path.is_file():
        raise CadError(f"File not found: {path}")
    key = (str(path), path.stat().st_mtime, unit)
    if key in _cache:
        return _cache[key]
    tmp = None
    if path.suffix.lower() == ".dwg":
        try:
            from formats import dwg_bridge
        except ImportError:
            raise CadError("No DWG support in this IngeTrazo — save the plan "
                           "as DXF")
        if not dwg_bridge.have_dwg_support():
            raise CadError("DWG needs the LibreDWG converter (dwg2dxf) — "
                           "install it, or save the plan as DXF")
        tmp = dwg_bridge.dwg_to_dxf(path)
    try:
        doc = _open(tmp or path)
        k, note = _unit(doc, unit)
        out = {"segs": [], "loops": [], "circles": [], "texts": [],
               "inserts": [], "unit": k, "unit_note": note,
               "seg_style": [], "styles": [], "hidden_layers": []}
        _style_ctx(doc, out)
        sag = SAGITTA_M / k
        for e in doc.modelspace():
            _safe(_emit, e, None, 0, sag, out)
        out.pop("_ctx", None)
        ib = doc.header.get("$INSBASE", (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0)
        out["insbase"] = [float(ib[0]), float(ib[1])]
    finally:
        if tmp is not None:
            try:
                from formats import dwg_bridge
                dwg_bridge.discard_temp_dxf(tmp)
            except Exception:  # noqa: BLE001
                pass
    xs = [v for s in out["segs"] for v in (s[0], s[2])]
    ys = [v for s in out["segs"] for v in (s[1], s[3])]
    out["extents"] = ([min(xs), min(ys), max(xs), max(ys)] if xs
                      else [0.0, 0.0, 0.0, 0.0])
    out["layers"] = sorted({s[4] for s in out["segs"]}
                           | {t["layer"] for t in out["texts"]}
                           | {lp["layer"] for lp in out["loops"]})
    if len(_cache) > 8:
        _cache.clear()
    _cache[key] = out
    return out


# ---- line weights and line types (the plan's linework, as the CAD plots it) --
def _style_ctx(doc, out) -> None:
    """The layers' weights and types, the line types' dash patterns and
    the drawing's LTSCALE, for ``_style_of``."""
    lays = {}
    hidden = []
    for L in doc.layers:
        try:
            name = L.dxf.name
            lays[name] = (int(L.dxf.get("lineweight", -3)),
                          str(L.dxf.get("linetype", "CONTINUOUS")).upper())
            if (hasattr(L, "is_off") and L.is_off()) or \
                    (hasattr(L, "is_frozen") and L.is_frozen()):
                hidden.append(name)
        except Exception:  # noqa: BLE001
            continue
    pats = {}
    for lt in doc.linetypes:
        try:
            tags = getattr(lt, "pattern_tags", None)
            vals = [float(t.value) for t in (getattr(tags, "tags", None) or [])
                    if getattr(t, "code", None) == 49]
            pats[str(lt.dxf.name).upper()] = vals
        except Exception:  # noqa: BLE001
            continue
    try:
        lts = float(doc.header.get("$LTSCALE", 1.0) or 1.0)
    except Exception:  # noqa: BLE001
        lts = 1.0
    out["hidden_layers"] = hidden
    out["_ctx"] = {"layers": lays, "pats": pats, "lts": lts, "block": [],
                   "index": {}}


def _style_of(e, lay, out) -> int:
    """The index (in ``out["styles"]``) of the entity's (weight mm, dash
    pattern in drawing units) — BYLAYER / BYBLOCK resolved."""
    ctx = out.get("_ctx")
    if ctx is None:
        return -1
    lw = int(e.dxf.get("lineweight", -1))
    lt = str(e.dxf.get("linetype", "BYLAYER")).upper()
    blk = ctx["block"][-1] if ctx["block"] else (25, "CONTINUOUS")
    lay_lw, lay_lt = ctx["layers"].get(lay, (-3, "CONTINUOUS"))
    if lw == -1:
        lw = lay_lw
    elif lw == -2:
        lw = blk[0]
    if lw < 0:
        lw = 25                                  # the default, 0.25 mm
    if lt == "BYLAYER":
        lt = lay_lt
    elif lt == "BYBLOCK":
        lt = blk[1]
    scale = ctx["lts"] * float(e.dxf.get("ltscale", 1.0) or 1.0)
    pat = tuple(round(v * scale, 6) for v in ctx["pats"].get(lt, ())
                ) if lt not in ("CONTINUOUS", "") else ()
    if pat and not any(abs(v) > 1e-9 for v in pat):
        pat = ()
    key = (lw, pat)
    i = ctx["index"].get(key)
    if i is None:
        i = ctx["index"][key] = len(out["styles"])
        out["styles"].append([lw / 100.0, list(pat)])
    return i


def _seg(out, seg, st) -> None:
    out["segs"].append(seg)
    out["seg_style"].append(st)


def _safe(fn, *a) -> None:
    try:
        fn(*a)
    except Exception:  # noqa: BLE001 — one bad entity never stops the read
        pass


def _emit(e, inherit, depth, sag, out) -> None:
    t = e.dxftype()
    lay = e.dxf.get("layer", "0") or "0"
    if lay == "0" and inherit:
        lay = inherit
    st = _style_of(e, lay, out) if t != "INSERT" else -1
    if t == "INSERT":
        if depth < 8:
            n0 = len(out["segs"])
            ctx = out.get("_ctx")
            if ctx is not None:            # BYBLOCK inside: the insert's
                i_ = _style_of(e, lay, out)
                w_, p_ = out["styles"][i_]
                lt_ = str(e.dxf.get("linetype", "BYLAYER")).upper()
                if lt_ == "BYLAYER":
                    lt_ = ctx["layers"].get(lay, (-3, "CONTINUOUS"))[1]
                ctx["block"].append((int(round(w_ * 100)), lt_))
            try:
                for v in e.virtual_entities():
                    _safe(_emit, v, lay, depth + 1, sag, out)
                for a in getattr(e, "attribs", []) or []:
                    _safe(_emit, a, lay, depth + 1, sag, out)
            finally:
                if ctx is not None and ctx["block"]:
                    ctx["block"].pop()
            mine = out["segs"][n0:]
            if mine:                   # a block: doors and windows often are
                xs = [v for s in mine for v in (s[0], s[2])]
                ys = [v for s in mine for v in (s[1], s[3])]
                ins = e.dxf.insert
                out["inserts"].append({
                    "name": e.dxf.name, "layer": lay,
                    "x": ins[0], "y": ins[1],
                    "rot": float(e.dxf.get("rotation", 0.0)),
                    "box": [min(xs), min(ys), max(xs), max(ys)],
                    "segs": len(mine), "depth": depth})
    elif t == "LINE":
        a, b = e.dxf.start, e.dxf.end
        _seg(out, (a[0], a[1], b[0], b[1], lay), st)
    elif t in ("LWPOLYLINE", "POLYLINE"):
        if t == "POLYLINE" and (e.is_poly_face_mesh or e.is_polygon_mesh):
            return
        if e.is_closed:
            try:
                from ezdxf import path as ezpath
                pts = [(p[0], p[1]) for p in
                       ezpath.make_path(e).flattening(sag)]
            except Exception:  # noqa: BLE001
                pts = []
            if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-9:
                pts = pts[:-1]
            if len(pts) >= 3:
                out["loops"].append({"layer": lay, "pts": pts})
        for v in e.virtual_entities():
            _safe(_emit, v, lay, depth, sag, out)
    elif t == "CIRCLE":
        c = e.ocs().to_wcs(e.dxf.center)
        out["circles"].append({"layer": lay, "c": (c[0], c[1]),
                               "r": e.dxf.radius})
        pts = list(e.flattening(sag))
        for p, q in zip(pts, pts[1:]):
            _seg(out, (p[0], p[1], q[0], q[1], lay), st)
    elif t in ("ARC", "ELLIPSE", "SPLINE"):
        pts = list(e.flattening(sag))
        for p, q in zip(pts, pts[1:]):
            _seg(out, (p[0], p[1], q[0], q[1], lay), st)
    elif t in ("TEXT", "ATTRIB"):
        txt = e.plain_text().strip()
        if txt:
            h, v = e.dxf.get("halign", 0), e.dxf.get("valign", 0)
            ins = e.dxf.align_point if (h or v) and \
                e.dxf.hasattr("align_point") else e.dxf.insert
            p = e.ocs().to_wcs(ins)
            out["texts"].append({"layer": lay, "text": txt, "x": p[0],
                                 "y": p[1], "h": e.dxf.get("height", 2.5),
                                 "rot": e.dxf.get("rotation", 0.0)})
    elif t == "MTEXT":
        txt = e.plain_text(split=False).strip()
        if txt:
            p = e.dxf.insert
            out["texts"].append({"layer": lay, "text": txt, "x": p[0],
                                 "y": p[1], "h": e.dxf.get("char_height", 2.5),
                                 "rot": e.get_rotation()
                                 if hasattr(e, "get_rotation") else 0.0})


def base_point(drawing: dict, mode: str, custom=(0.0, 0.0)):
    """The drawing point (its units) that lands on the insertion point."""
    x0, y0, x1, y1 = drawing["extents"]
    if mode == "insbase":
        return tuple(drawing["insbase"])
    if mode == "extents_ll":
        return (x0, y0)
    if mode == "extents_c":
        return ((x0 + x1) / 2, (y0 + y1) / 2)
    if mode == "custom":
        return (float(custom[0]), float(custom[1]))
    return (0.0, 0.0)


def place(drawing: dict, base, insert=(0.0, 0.0), rot_deg: float = 0.0,
          only=None) -> dict:
    """The drawing on the model, in metres: ``model = R(rot)·(p − base)·k
    + insert``. ``only``: a layer filter ``fn(name) → bool``."""
    k = drawing["unit"]
    bx, by = base
    ix, iy = insert
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))

    def T(x, y):
        dx, dy = (x - bx) * k, (y - by) * k
        return [round(c * dx - s * dy + ix, 5), round(s * dx + c * dy + iy, 5)]

    keep = only or (lambda _n: True)
    layers = [n for n in drawing["layers"] if keep(n)]
    index = {n: i for i, n in enumerate(layers)}
    segs = []
    sty_in = drawing.get("seg_style") or []
    has_sty = len(sty_in) == len(drawing["segs"])
    sty_out = []
    for i, (x0, y0, x1, y1, lay) in enumerate(drawing["segs"]):
        if lay not in index:
            continue
        a, b = T(x0, y0), T(x1, y1)
        if math.dist(a, b) > 1e-6:
            segs.append(a + b + [index[lay]])
            if has_sty:
                sty_out.append(sty_in[i])
    # which lines are dashed (a hidden / dashed line type): by segment
    styles = drawing.get("styles") or []
    dashed = [bool(styles[i][1]) if 0 <= i < len(styles) else False
              for i in sty_out] if has_sty else []
    def box(b):
        pts = [T(b[0], b[1]), T(b[2], b[1]), T(b[2], b[3]), T(b[0], b[3])]
        return pts

    inserts = [dict(i, x=T(i["x"], i["y"])[0], y=T(i["x"], i["y"])[1],
                    rot=i["rot"] + rot_deg, corners=box(i["box"]))
               for i in drawing.get("inserts", ())]
    return {"segs": segs, "layers": layers, "inserts": inserts,
            "dashed": dashed,
            "loops": [{"layer": lp["layer"], "pts": [T(*p) for p in lp["pts"]]}
                      for lp in drawing["loops"] if lp["layer"] in index],
            "circles": [{"layer": ci["layer"], "c": T(*ci["c"]),
                         "r": ci["r"] * k}
                        for ci in drawing["circles"] if ci["layer"] in index],
            "texts": [dict(t, x=T(t["x"], t["y"])[0], y=T(t["x"], t["y"])[1],
                           h=t["h"] * k, rot=t["rot"] + rot_deg)
                      for t in drawing["texts"] if t["layer"] in index]}


def far_from_base(drawing: dict, base) -> float:
    """How far (m) the drawing lies from its base point — a survey drawing
    placed by its origin lands kilometres away."""
    x0, y0, x1, y1 = drawing["extents"]
    k = drawing["unit"]
    return max(abs(x0 - base[0]), abs(x1 - base[0]),
               abs(y0 - base[1]), abs(y1 - base[1])) * k


def crop(drawing: dict, region) -> dict:
    """Only the part of the drawing inside ``region`` = (x0, y0, x1, y1),
    drawing units — one floor of a sheet that holds them all. A line is
    kept when its middle lies inside; outlines, circles and texts by their
    centre / insertion point."""
    if not region:
        return drawing
    x0, y0, x1, y1 = (float(v) for v in region)
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    key = (id(drawing), x0, y0, x1, y1)
    hit = _crops.get(key)
    if hit is not None and hit[0] is drawing:
        return hit[1]

    def inside(x, y):
        return x0 <= x <= x1 and y0 <= y <= y1

    sty_all = drawing.get("seg_style") or []
    keep_i = [i for i, s in enumerate(drawing["segs"])
              if inside((s[0] + s[2]) / 2, (s[1] + s[3]) / 2)]
    segs = [drawing["segs"][i] for i in keep_i]
    seg_style = [sty_all[i] for i in keep_i] if len(sty_all) == len(
        drawing["segs"]) else []
    loops = [lp for lp in drawing["loops"]
             if inside(sum(p[0] for p in lp["pts"]) / len(lp["pts"]),
                       sum(p[1] for p in lp["pts"]) / len(lp["pts"]))]
    circles = [c for c in drawing["circles"] if inside(*c["c"])]
    texts = [t for t in drawing["texts"] if inside(t["x"], t["y"])]
    inserts = [i for i in drawing.get("inserts", ())
               if inside((i["box"][0] + i["box"][2]) / 2,
                         (i["box"][1] + i["box"][3]) / 2)]
    xs = [v for s in segs for v in (s[0], s[2])]
    ys = [v for s in segs for v in (s[1], s[3])]
    out = dict(drawing, segs=segs, seg_style=seg_style, loops=loops,
               circles=circles, texts=texts,
               inserts=inserts,
               extents=([min(xs), min(ys), max(xs), max(ys)] if xs
                        else [x0, y0, x1, y1]),
               layers=sorted({s[4] for s in segs} | {t["layer"] for t in texts}
                             | {lp["layer"] for lp in loops}),
               region=[x0, y0, x1, y1])
    if len(_crops) > 16:
        _crops.clear()
    _crops[key] = (drawing, out)
    return out


_crops: dict = {}


def to_model(drawing: dict, base, insert=(0.0, 0.0), rot_deg: float = 0.0,
             pts=()) -> list:
    """Drawing points → model metres, the way ``place`` moves them."""
    k = drawing["unit"]
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    out = []
    for x, y in pts:
        dx, dy = (x - base[0]) * k, (y - base[1]) * k
        out.append([round(c * dx - s * dy + insert[0], 4),
                    round(s * dx + c * dy + insert[1], 4)])
    return out
