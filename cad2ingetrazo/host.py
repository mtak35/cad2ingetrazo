# SPDX-License-Identifier: GPL-3.0-or-later
"""The few names CAD2IngeTrazo shares across its modules — its key in the
document and the layers it owns."""
from __future__ import annotations

KEY = "cad2ingetrazo"
LAYER_PREFIX = "C2I · "
SYMBOL_LAYER = LAYER_PREFIX + "Plan symbols"
TERRAIN_LAYER = LAYER_PREFIX + "Plot"     # the ground plate
BOUNDARY_LAYER = LAYER_PREFIX + "Boundary wall and gates"
PREFIX_PLAN_CUT = LAYER_PREFIX + "Plan cut · "   # a plan's section plane
ANN_SUFFIX = " · Annotations"
TXT_SUFFIX = " · Texts"
DIM_SUFFIX = " · Dimensions"
SITE = "Site"                             # the plot's notes: ann_layer(SITE)
FOUNDATION = "__foundation__"             # the foundation plan's import key


def level_layer(name: str) -> str:
    return LAYER_PREFIX + name


def ann_layer(name: str) -> str:
    """A level's dimensions and texts: shown by its plan only."""
    return LAYER_PREFIX + name + ANN_SUFFIX


def text_layer(name: str) -> str:
    """A level's room names and CAD texts: its plan only — on the sheets
    as labels, in the model drawn to scale by the overlay (labels.py)."""
    return LAYER_PREFIX + name + TXT_SUFFIX


def dim_layer(name: str) -> str:
    """A level's dimension chains: its plan only, and only while the
    zoom leaves room for their figures (labels.py)."""
    return LAYER_PREFIX + name + DIM_SUFFIX


def is_ann_layer(name: str) -> bool:
    return name.startswith(LAYER_PREFIX) and (name.endswith(ANN_SUFFIX)
                                              or name.endswith(TXT_SUFFIX)
                                              or name.endswith(DIM_SUFFIX))


def log_error(where: str) -> None:
    """The current traceback, to cad2ingetrazo_errors.log beside the
    plugin (the plugins folder)."""
    import datetime
    import traceback
    from pathlib import Path
    try:
        path = Path(__file__).resolve().parent.parent / \
            "cad2ingetrazo_errors.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] "
                    f"{where}\n{traceback.format_exc()}")
    except Exception:  # noqa: BLE001
        pass


def refresh_host_layers(viewport) -> None:
    """The host's Layers and Scenes trays read the document again."""
    try:
        win = viewport.window()
        tray = getattr(win, "tray", None)
        for name in ("layers", "scenes"):
            panel = getattr(tray, name, None)
            if panel is not None and hasattr(panel, "refresh"):
                panel.refresh()
    except Exception:  # noqa: BLE001 — the trays catch up on their own
        pass


# ---- units: the document's (core.units), set from the CAD plan --------------------
#: drawing unit (m per unit) → the units the model is shown in
UNIT_OF_CAD = [(0.0254, "ft-in", 0), (0.3048, "ft-in", 0), (0.001, "mm", 0),
               (0.01, "cm", 1), (1.0, "m", 2)]
UNIT_CHOICES = [("auto", "Auto — as the CAD plan"), ("m", "Metres"),
                ("cm", "Centimetres"), ("mm", "Millimetres"),
                ("ft-in", "Feet and inches"), ("in", "Inches")]


def units_for_cad(k: float):
    """(units, precision) for a drawing unit of ``k`` m."""
    for kk, u, p in UNIT_OF_CAD:
        if abs(k - kk) / kk < 0.01:
            return u, p
    return "m", 2


def set_units(scene, unit: str, precision=None) -> None:
    try:
        from core.units import apply_units
    except ImportError:
        return
    if precision is None:
        precision = {"m": 2, "cm": 1, "mm": 0, "ft-in": 0, "in": 1}.get(unit, 2)
    apply_units(scene, {"length": unit, "precision": precision})


def unit() -> str:
    try:
        from core.units import model_unit
        return model_unit()
    except Exception:  # noqa: BLE001
        return "m"


def imperial() -> bool:
    return unit() in ("in", "ft", "ft-in", "in-frac", "ft-in-frac")


def len_txt(m: float) -> str:
    try:
        from core.units import fmt_len
        return fmt_len(m)
    except Exception:  # noqa: BLE001
        return f"{m:.2f} m"


def area_txt(a: float) -> str:
    if imperial():
        return f"{a / 0.09290304:,.1f} ft²"
    u = unit()
    if u in ("cm", "mm"):
        return f"{a:,.2f} m²"              # rooms read in m² whatever the mm
    return f"{a:,.2f} m²"


def parse_len(text: str):
    """A typed length in metres: 2.1 · 2.1m · 210cm · 6'6" · 6'-6" · 78" ·
    6.5' — a bare number in the model's unit. None when not a length."""
    t = str(text or "").strip().replace("'-", "'").replace("' ", "'")
    t = t.replace("ft", "'").replace("in", '"') if any(
        c.isdigit() for c in t) and ("ft" in t or "in" in t) else t
    try:
        from views.viewport import _parse_length_field
        v = _parse_length_field(t)
        if v is not None:
            return v
    except Exception:  # noqa: BLE001
        pass
    try:
        return float(t.rstrip("m ").strip())
    except ValueError:
        return None
