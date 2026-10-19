# SPDX-License-Identifier: GPL-3.0-or-later
"""The panel in the world's ten most spoken languages: the language picked
beside the extension's name swaps the words of every section title,
button, check box and field label (the tooltips stay in English). The
choice is remembered."""
from __future__ import annotations

import importlib
import re

#: (code, the language's own name)
LANGS = [("en", "English"), ("zh", "中文"), ("hi", "हिन्दी"),
         ("es", "Español"), ("fr", "Français"), ("ar", "العربية"),
         ("bn", "বাংলা"), ("pt", "Português"), ("ru", "Русский"),
         ("ur", "اردو")]
RTL = {"ar", "ur"}
_tables: dict = {}
_NUM = re.compile(r"^(\d+(?:\.\d+)?\s+)(.*)$", re.S)


def table(code: str) -> dict:
    """{English: translated} for ``code`` ({} for English / unknown)."""
    if code in _tables:
        return _tables[code]
    out = {}
    if code and code != "en":
        try:
            from .keys import KEYS
            mod = importlib.import_module(f"{__name__}.{code}")
            out = {k: v for k, v in zip(KEYS, mod.T) if v}
        except Exception:  # noqa: BLE001
            out = {}
    _tables[code] = out
    return out


def tr(text: str, code: str) -> str:
    """``text`` in ``code`` (a section number kept in front); as it is when
    there is no translation."""
    if not text or code == "en":
        return text
    t = table(code)
    if text in t:
        return t[text]
    m = _NUM.match(text)
    if m and m.group(2) in t:
        return m.group(1) + t[m.group(2)]
    if "&&" in text and text.replace("&&", "&") in t:
        return t[text.replace("&&", "&")].replace("&", "&&")
    return text


def apply(root, code: str) -> int:
    """Every label, button, check box and section title under ``root`` in
    ``code`` (their English kept, so they switch back). How many changed."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QCheckBox, QLabel, QPushButton,
                                   QRadioButton, QToolButton)
    n = 0
    for cls in (QLabel, QPushButton, QCheckBox, QToolButton, QRadioButton):
        for w in root.findChildren(cls):
            if w.property("c2i_notr"):
                continue
            cur = w.text()
            en = w.property("c2i_en")
            last = w.property("c2i_tr")
            if en is None or (cur != en and cur != last):
                en = cur                 # new words since: they are the
            if not en or en.lstrip().startswith("<"):   # English now
                continue
            new = tr(en, code)
            w.setProperty("c2i_en", en)
            w.setProperty("c2i_tr", new)
            if new != cur:
                w.setText(new)
                n += 1
    try:
        root.setLayoutDirection(Qt.RightToLeft if code in RTL
                                else Qt.LeftToRight)
    except Exception:  # noqa: BLE001
        pass
    return n
