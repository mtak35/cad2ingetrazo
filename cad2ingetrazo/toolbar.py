# SPDX-License-Identifier: GPL-3.0-or-later
"""CAD2IngeTrazo's own toolbar in IngeTrazo's window: one button with the
plugin's icon that opens (or brings forward) the panel, and the views
beside it."""
from __future__ import annotations

import os

NAME = "toolbar_cad2ingetrazo"
ICON = os.path.join(os.path.dirname(__file__), "icon.svg")


def icon():
    from PySide6.QtGui import QIcon
    return QIcon(ICON)


def install(app, dock, panel) -> None:
    """The toolbar (made once; a reload re-wires its actions)."""
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QToolBar

    win = app.window
    tb = win.findChild(QToolBar, NAME)
    if tb is None:
        tb = QToolBar("CAD2IngeTrazo", win)
        tb.setObjectName(NAME)
        tb.setIconSize(QSize(24, 24))
        win.addToolBar(Qt.TopToolBarArea, tb)
    tb.clear()

    def open_panel():
        try:
            if dock is not None:
                app.show_panel(dock)
                dock.raise_()
        except Exception:  # noqa: BLE001
            pass
        panel.refresh()

    a = QAction(icon(), "CAD2IngeTrazo", tb)
    a.setToolTip("CAD2IngeTrazo — open the panel (CAD plan to BIM, level "
                 "by level)")
    a.setStatusTip("Open the CAD2IngeTrazo panel")
    a.triggered.connect(lambda _c=False: open_panel())
    tb.addAction(a)
    for text, fn, tip in (("3D", panel.show_3d, "Whole model, clean 3D"),
                          ("Plan", panel.show_plan,
                           "Plan of the current level"),
                          ("Sheets", panel.make_sheets, "Make the sheets"),
                          ("SketchUp", panel.export_skp,
                           "Export the model to SketchUp (.skp)")):
        b = QAction(text, tb)
        b.setToolTip(tip)
        b.triggered.connect(lambda _c=False, f=fn: f())
        tb.addAction(b)
    # the CAD plan's own lines in the plan views: on / off in one click
    tb.addSeparator()
    c = QAction("CAD lines", tb)
    c.setCheckable(True)
    c.setToolTip("Show / hide the CAD plan's linework in the plan views "
                 "(the model stays)")
    try:
        c.setChecked(bool(panel.doc()["settings"].get("cad_lines", True)))
    except Exception:  # noqa: BLE001
        c.setChecked(True)
    c.toggled.connect(lambda on: panel.set_cad_lines(on))
    tb.addAction(c)
    panel._tb_cad = c
    tb.show()
    try:
        dock.setWindowIcon(icon())
    except Exception:  # noqa: BLE001
        pass
