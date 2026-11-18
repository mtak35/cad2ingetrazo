# SPDX-License-Identifier: GPL-3.0-or-later
"""The kind of building (3.64.67): what the drawing is, so the extension
reads and dresses it the right way — a villa's look (arcades, porch
canopy, lanterns, grilles) is no mosque's, no warehouse's.

``doc["settings"]["building_type"]``: one of TYPES' keys; «auto» reads it
from the drawing's room names. ``effective(doc)`` → the kind used.
``STYLE_OF``: the elevation style a perspective gives each kind (None: the
picture's own — a villa's Mediterranean / modern).
"""
from __future__ import annotations

import re

TYPES = [("auto", "Auto (from the drawing's room names)"),
         ("villa", "Villa / house"),
         ("apartment", "Apartment / residential building"),
         ("commercial", "Commercial / office building"),
         ("mosque", "Mosque"),
         ("community", "Community centre / hall"),
         ("school", "School / institute"),
         ("hospital", "Hospital / clinic"),
         ("industrial", "Industrial building / warehouse")]
LABEL = dict(TYPES)
STYLE_OF = {"villa": None, "apartment": "contemporary",
            "commercial": "modern", "mosque": "mosque",
            "community": "contemporary", "school": "contemporary",
            "hospital": "minimalist", "industrial": "industrial"}
NOTE = {
    "villa": "The perspective's own look: clay-tile roofs, arches, iron, "
             "mouldings (Mediterranean) or glass and dark frames (modern).",
    "apartment": "Contemporary: bands, glass railings, no villa "
                 "ornament (no arcades, porch canopy, lanterns).",
    "commercial": "Modern: big glass, dark frames, deep fascias.",
    "mosque": "Mosque: white, every opening arched, the plan's domes, "
              "slim minarets at the prayer hall, lattice boundary wall.",
    "community": "Contemporary: plain bands, glass, an entrance canopy.",
    "school": "Contemporary: plain bands, glass, no villa ornament.",
    "hospital": "Minimalist: white, flat, large glass.",
    "industrial": "Industrial: grey metal-clad walls, flat roofs, plain "
                  "openings, a plain boundary wall."}

_RX = [("mosque", None),
       ("industrial", re.compile(r"WARE\s*HOUSE|FACTORY|INDUSTR|GODOWN|"
                                 r"\bPLANT\b|WORKSHOP|PRODUCTION|LOADING\s+"
                                 r"BAY|STORAGE\s+HALL", re.I)),
       ("hospital", re.compile(r"HOSPITAL|\bWARD\b|\bOPD\b|\bICU\b|CLINIC|"
                               r"OPERATION\s+THEAT|EMERGENCY", re.I)),
       ("school", re.compile(r"CLASS\s*ROOM|SCHOOL|\bLAB\b|LIBRARY|STAFF\s+"
                             r"ROOM|PRINCIPAL", re.I)),
       ("community", re.compile(r"COMMUNITY|BANQUET|MULTI\s*PURPOSE|"
                                r"AUDITORIUM|ASSEMBLY\s+HALL|CLUB\s*HOUSE",
                                re.I)),
       ("commercial", re.compile(r"\bOFFICE|\bSHOPS?\b|RETAIL|\bMALL\b|"
                                 r"SHOWROOM|FOOD\s+COURT|\bBANK\b", re.I)),
       ("apartment", re.compile(r"\bFLAT\b|APARTMENT|TYPICAL\s+FLOOR|"
                                r"\bUNIT\s*[-#]?\s*\d", re.I))]


def detect(doc) -> str:
    """The kind of building its drawing's room names say (else villa)."""
    from . import mosque as MQ
    if MQ.is_mosque(doc):
        return "mosque"
    texts = [str(t.get("text", "")) for t in doc.get("texts") or []]
    for key, rx in _RX[1:]:
        n = sum(1 for t in texts if rx.search(t))
        if n >= (3 if key in ("commercial", "apartment") else 2):
            return key
    floors = sum(1 for lv in doc["arch"]["levels"] if lv["kind"] == "floor")
    return "apartment" if floors >= 4 else "villa"


def chosen(doc) -> str:
    v = (doc.get("settings") or {}).get("building_type") or "auto"
    return v if v in LABEL else "auto"


def effective(doc) -> str:
    v = chosen(doc)
    return detect(doc) if v == "auto" else v
