# SPDX-License-Identifier: GPL-3.0-or-later
"""CAD2IngeTrazo 2.0 — CAD floor plans to a BIM model, level by level.

A tab in IngeTrazo's side tray laid out as the workflow (ArchXQ style):
Project & levels → Import CAD plan → Openings → Structure → Roof → Rooms →
Selected element → Plans, sheets & export.

The modelling engine (walls, openings, structure, roofs, rooms) comes from
ArchXQ IT Lite (c) Orlando Souza / XQ, GPL-3.0-or-later.
``setup(app)`` is the IngeTrazo entry point (plugin API v2).
"""
from __future__ import annotations

__version__ = "3.11"
TITLE = "CAD2IngeTrazo"

_panel = None


def setup(app) -> None:
    global _panel
    from PySide6.QtCore import QTimer

    from . import sheets
    from .host import log_error
    from .panel import Panel

    try:
        sheets.full_geometry(app.viewport, True)    # sheets: the whole model
    except Exception:  # noqa: BLE001
        log_error("setup.full_geometry")

    _panel = Panel(app)
    dock = app.add_panel(TITLE, _panel)

    def show():
        try:
            app.show_panel(dock)
        except Exception:  # noqa: BLE001
            pass
        _panel.refresh()

    try:
        menu = app.add_menu(TITLE)
        if menu is None:
            raise RuntimeError("no Extensions menu")
        try:
            from . import toolbar as _tb
            menu.setIcon(_tb.icon())
            menu.addAction(_tb.icon(), "Open the CAD2IngeTrazo panel", show)
        except Exception:  # noqa: BLE001
            menu.addAction("Open the CAD2IngeTrazo panel", show)
        menu.addSeparator()
        menu.addAction("3D view (whole model, clean)", _panel.show_3d)
        menu.addAction("Plan of the current level", _panel.show_plan)
        menu.addAction("Site plan (plot and setbacks)", _panel.show_site)
        menu.addAction("Make sheets", _panel.make_sheets)
        menu.addAction("Open sheets", _panel.open_sheets)
        menu.addAction("Export sheets to PDF…", _panel.export_pdf)
        menu.addAction("Export sheets to DXF…", _panel.export_dxf)
        menu.addSeparator()
        menu.addAction(f"About CAD2IngeTrazo {__version__}",
                       lambda: _about(app))
    except Exception:  # noqa: BLE001 — older hosts: one action
        app.add_menu_action("CAD2IngeTrazo panel…", show,
                            tip="CAD plan to BIM, level by level")

    try:                                  # its own toolbar button
        from . import toolbar
        toolbar.install(app, dock, _panel)
    except Exception:  # noqa: BLE001
        log_error("setup.toolbar")

    # Leaving a plan / elevation / section view gives the clean 3D back.
    from . import ghost, labels

    def overlay(viewport, painter):
        try:
            sheets.tidy_3d(viewport)
        except Exception:  # noqa: BLE001
            pass
        try:
            ghost.draw(viewport, painter)        # other floors, greyed
        except Exception:  # noqa: BLE001
            log_error("ghost.draw")
        try:
            labels.draw(viewport, painter)       # plan texts to scale
        except Exception:  # noqa: BLE001
            log_error("labels.draw")

    app.add_overlay(overlay)

    # A document opened, undone, redone: the panel reads it again (once).
    timer = QTimer(_panel)
    timer.setSingleShot(True)
    timer.setInterval(250)
    timer.timeout.connect(_panel.refresh)
    try:
        app.on_document_changed(lambda *a: timer.start())
    except Exception:  # noqa: BLE001
        pass

    try:
        app.add_context_menu(lambda menu, sel: _context(menu, sel))
    except Exception:  # noqa: BLE001
        pass


def _context(menu, selection) -> None:
    """Right-click on a CAD2IngeTrazo element: edit it there (its fields in
    a dialog, quick changes, convert a wall, delete)."""
    if _panel is None or not selection:
        return
    try:
        _panel.context_menu(menu)
    except Exception:  # noqa: BLE001
        from .host import log_error
        log_error("context_menu")


def _about(app) -> None:
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.about(
        app.window, f"{TITLE} {__version__}",
        f"<b>{TITLE} {__version__}</b><br>CAD floor plans (DXF/DWG) to a "
        "BIM model, level by level — walls, doors, windows, slabs, columns, "
        "beams, footings, roofs, rooms — with plans, elevations and "
        "sections on sheets (PDF, DXF).<br><br>Modelling engine from "
        "<i>ArchXQ IT Lite</i> © Orlando Souza / XQ.<br>"
        "License: GPL-3.0-or-later.")
