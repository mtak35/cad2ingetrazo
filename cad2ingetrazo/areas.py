"""3.64.77 — the outside / semi-outside areas by their own names.

A terrace, the car porch, the entrance lobby, a verandah are not «rooms»:
they are named in the plan, in the outliner and in the right-click menu by
what they are («Terrace», «Car porch», «Entrance lobby», «Verandah»)."""
from __future__ import annotations

import re

#: (key, label, regex) — the order matters (a «car porch» before a «porch»)
KINDS = [
    ("porch", "Car porch",
     r"CAR\s*PORCH|CAR\s*PORT|CARPORT|PORCH|GARAGE|CAR\s*PARK"),
    ("entrance", "Entrance lobby",
     r"ENTRANCE|LOBBY|FOYER|ENTRY"),
    ("veranda", "Verandah",
     r"VERANDA|VERANDAH|PORTICO|SIT[\s-]*OUT|ARCADE"),
    ("terrace", "Terrace",
     r"TERRACE|BALCON|DECK|PATIO|COURT\s*YARD|ROOF\s*GARDEN"),
]
_RX = [(k, lab, re.compile(rx, re.I)) for k, lab, rx in KINDS]


def kind_of(name) -> tuple | None:
    """(key, label) of an outside area from its name, else None. A name
    «Master bedroom balcony» is a terrace too; «Entrance» alone a lobby."""
    s = str(name or "")
    if not s.strip():
        return None
    for k, lab, rx in _RX:
        if rx.search(s):
            return k, lab
    return None


def title(name, kind_word="Room") -> str:
    """«Car porch · CAR PORCH» — or the name alone when it says it."""
    kd = kind_of(name)
    if not kd:
        return str(name or kind_word)
    nm = str(name).strip()
    if nm.lower() == kd[1].lower():
        return nm
    return f"{kd[1]} · {nm}"
