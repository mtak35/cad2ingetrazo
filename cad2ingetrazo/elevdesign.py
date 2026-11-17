"""3.64.51: «Design the elevations» — the elevations made by hand, element
by element, without any picture: a style to start from, then every part
its own choice (roofs, window heads and frames, grilles, arcades,
railings, columns, mouldings, the front's details, the colours). The
design is kept in ``doc["look"]`` (``manual``) and made again at every
«Update from CAD» (lookstyle.apply_kit; its mouldings: ornament.py)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog,
                               QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import lookstyle as LS

ROOFS = [("asdrawn", "As drawn (flat roof, parapets)"),
         ("hip", "Tiled hip roofs over every block"),
         ("gable", "Tiled gable roofs over every block (steep: Tudor, "
          "Cape Cod)")]
HEADS = [("asdrawn", "As drawn"), ("arch", "Arched (semicircle)"),
         ("flat", "Flat")]
FRAMES = [("asdrawn", "As drawn"), ("upvc", "uPVC, white"),
          ("wood", "Wood"), ("black", "Black aluminium"),
          ("aluminium", "Aluminium"), ("steel", "Steel")]
RAILS = [("asdrawn", "As drawn"), ("ms_grill", "Wrought iron"),
         ("glass_post", "Glass panels between posts"),
         ("glass", "Frameless glass"),
         ("ss_bars", "Stainless steel balusters"),
         ("wood", "Timber balusters"), ("solid", "Solid parapet")]
COLUMNS = [("asdrawn", "As drawn"), ("tuscan", "Tuscan"),
           ("doric", "Doric"), ("ionic", "Ionic"),
           ("corinthian", "Corinthian"), ("composite", "Composite"),
           ("round_smooth", "Round, smooth"),
           ("square_smooth", "Square pier")]
FRONTS = [("auto", "Auto (where the cars drive in)"), ("north", "North"),
          ("south", "South"), ("east", "East"), ("west", "West")]
CHECKS = [("Mouldings", [("plinth", "Stone plinth round the ground floor"),
                         ("bands", "Floor bands (string courses)"),
                         ("cornice", "Cornice under the eaves"),
                         ("fascia", "Thick fascia band round a flat roof"),
                         ("quoins", "Quoins on the corners"),
                         ("surrounds", "Window and door surrounds "
                          "(hoods, sills, keystones)")]),
          ("Windows and doors", [
              ("gf_grille", "Grilles on the ground floor's windows"),
              ("door_arch", "Outside doors arched"),
              ("arcades", "Front's wide upper windows as arcades")]),
          ("Front details", [
              ("corbels", "Corbels under balconies and terraces"),
              ("porch_canopy", "Clay-tile roof along the terrace over the "
               "car porch"),
              ("entrance_canopy", "Tiled canopy over the main door"),
              ("medallions", "Medallions on blank upper walls"),
              ("lanterns", "Wall lanterns (main door, windows)")]),
          ("Modern massing", [
              ("slab_edges", "Thick light slab edges on the terraces"),
              ("frame_box", "Projecting dark frame round the front's upper "
               "bay (down-lights)"),
              ("incline_panel", "Inclined cladding panel on a front corner "
               "(raked, above the roof)"),
              ("entry_clad", "Main door's bay clad full height, slab "
               "canopy")]),
          ("Style elements", [
              ("pediment", "Classical: pediments (main door, upper "
               "windows)"),
              ("deco_fins", "Art Deco: vertical fins up the front, stepped "
               "above the roof"),
              ("deco_bands", "Art Deco: three speed bands under the roof"),
              ("deco_crown", "Art Deco: stepped crown and sunrays over the "
               "entrance"),
              ("window_boxes", "Brutalist: deep concrete boxes round the "
               "windows"),
              ("half_timber", "Tudor: half-timbering on the upper floors"),
              ("gf_clad", "Brick ground floor (Tudor, traditional)"),
              ("shutters", "Cape Cod: shutters by every window"),
              ("siding", "Cape Cod: clapboard siding"),
              ("eave_brackets", "Italianate: paired brackets under the "
               "eaves")])]
COLOURS = [("wall", "Walls"), ("trim", "Mouldings / trims"),
           ("stone", "Stone (plinth, quoins, door cladding)"),
           ("clad", "Cladding panels"), ("roof_c", "Roof tiles"),
           ("accent", "Accent (timber, shutters, Deco metal)"),
           ("metal", "Metal (railings, lanterns)")]


def _combo(items):
    cb = QComboBox()
    for k, label in items:
        cb.addItem(label, k)
    return cb


def _set(cb, key):
    i = cb.findData(key)
    cb.setCurrentIndex(max(i, 0))


class ElevationDesigner(QDialog):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle("Design the elevations")
        self.setModal(False)
        self.cols = {}
        outer = QVBoxLayout(self)
        info = QLabel(
            "Design every side of the house yourself — no picture needed. "
            "Start from a style, then choose each part. <b>Apply</b> puts "
            "it on the model as the plans draw it (sizes and positions "
            "stay); every «Update from CAD» makes it again. Ctrl+Z undoes "
            "it.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #8a94a3;")
        outer.addWidget(info)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        sc.setWidget(body)
        outer.addWidget(sc, 1)
        # style and front
        g0 = QGroupBox("Start from")
        f0 = QFormLayout(g0)
        self.style = QComboBox()
        for k, (label, _d) in LS.PRESETS.items():
            self.style.addItem(label, k)
        self.style.activated.connect(lambda _i: self._load_preset())
        f0.addRow("Style", self.style)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #8a94a3;")
        f0.addRow(self.note)
        self.front = _combo(FRONTS)
        self.front.setToolTip("The side the front details go on (the "
                              "arcades, the porch roof, the canopy, the "
                              "medallions, the lanterns)")
        f0.addRow("Front of the house", self.front)
        grid.addWidget(g0, 0, 0)
        # roofs
        g1 = QGroupBox("Roofs")
        f1 = QFormLayout(g1)
        self.roof = _combo(ROOFS)
        f1.addRow("Roof", self.roof)
        self.slope = QDoubleSpinBox()
        self.slope.setRange(10.0, 60.0)
        self.slope.setSuffix(" °")
        f1.addRow("Slope", self.slope)
        self.eave = QDoubleSpinBox()
        self.eave.setRange(0.0, 1.5)
        self.eave.setSingleStep(0.05)
        self.eave.setSuffix(" m")
        f1.addRow("Eaves out", self.eave)
        self.annex = QCheckBox("Single-storey blocks under tiles too")
        f1.addRow(self.annex)
        self.fd = QDoubleSpinBox()
        self.fd.setRange(0.02, 1.2)
        self.fd.setSingleStep(0.05)
        self.fd.setSuffix(" m")
        f1.addRow("Flat roof's fascia out", self.fd)
        self.fh = QDoubleSpinBox()
        self.fh.setRange(0.08, 1.5)
        self.fh.setSingleStep(0.05)
        self.fh.setSuffix(" m")
        f1.addRow("… its depth", self.fh)
        grid.addWidget(g1, 0, 1)
        # windows, railings, columns
        g2 = QGroupBox("Windows, railings, columns")
        f2 = QFormLayout(g2)
        self.head = _combo(HEADS)
        f2.addRow("Upper windows' heads", self.head)
        self.frame = _combo(FRAMES)
        f2.addRow("Window frames", self.frame)
        from .engine.windesign import DESIGNS as WDS
        self.wstyle = _combo([("asdrawn", "As drawn")] + list(WDS))
        f2.addRow("Window design", self.wstyle)
        self.light = _combo([("lantern", "Classical lanterns"),
                             ("sconce", "Modern up / down sconces")])
        f2.addRow("Wall lights", self.light)
        self.rail = _combo(RAILS)
        f2.addRow("Railings", self.rail)
        self.columns = _combo(COLUMNS)
        self.columns.setToolTip("The outside free-standing columns (a "
                                "porch's, a veranda's)")
        f2.addRow("Columns", self.columns)
        self.gate = QComboBox()
        from .site import GATE_COLORS
        for k, (label, _c) in GATE_COLORS.items():
            self.gate.addItem(label, k)
        f2.addRow("Gate colour", self.gate)
        grid.addWidget(g2, 1, 0)
        # the check groups
        self.checks = {}
        r_, c_ = 1, 1
        for title, items in CHECKS:
            g = QGroupBox(title)
            v = QVBoxLayout(g)
            for k, label in items:
                ch = QCheckBox(label)
                v.addWidget(ch)
                self.checks[k] = ch
            grid.addWidget(g, r_, c_)
            c_ += 1
            if c_ > 1:
                r_, c_ = r_ + 1, 0
        # colours
        g5 = QGroupBox("Colours")
        f5 = QFormLayout(g5)
        for k, label in COLOURS:
            b = QPushButton()
            b.setFixedWidth(110)
            b.clicked.connect(lambda _c=False, kk=k: self._pick(kk))
            self.cols[k] = (b, [0.8, 0.8, 0.8])
            f5.addRow(label, b)
        grid.addWidget(g5, r_, c_)
        # buttons
        row = QHBoxLayout()
        for text, fn, tip in (
                ("Take from perspective", self._from_picture,
                 "Fill the choices from a perspective added in «Elevations "
                 "/ perspectives to follow…» (its style and colours)"),
                ("Remove design", self._remove,
                 "Back to the elevations as the plans draw them"),):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, f=fn: f())
            row.addWidget(b)
        row.addStretch(1)
        ap = QPushButton("Apply design")
        ap.setDefault(True)
        ap.setStyleSheet("font-weight: bold;")
        ap.clicked.connect(lambda _c=False: self._apply())
        row.addWidget(ap)
        cl = QPushButton("Close")
        cl.clicked.connect(self.close)
        row.addWidget(cl)
        outer.addLayout(row)
        self.resize(980, 720)
        look = self.panel.doc().get("look") or {}
        self._fill(dict(LS.KIT_DEFAULT, **look) if look.get("manual")
                   or look.get("style") else LS.preset("mediterranean"))

    # ---- the fields ------------------------------------------------------------
    def _fill(self, k):
        _set(self.style, k.get("style", "mediterranean"))
        _set(self.front, k.get("front", "auto"))
        _set(self.roof, k.get("roof", "hip"))
        self.slope.setValue(float(k.get("roof_slope", LS.SLOPE)))
        self.eave.setValue(float(k.get("roof_eave", LS.EAVE)))
        self.annex.setChecked(bool(k.get("annex_roof", True)))
        self.fd.setValue(float(k.get("fascia_d", 0.30) or 0.30))
        self.fh.setValue(float(k.get("fascia_h", 0.55) or 0.55))
        self.note.setText(LS.STYLE_NOTES.get(k.get("style"), ""))
        _set(self.head, k.get("win_head", "arch"))
        _set(self.frame, k.get("win_frame", "upvc"))
        _set(self.wstyle, k.get("win_style", "asdrawn"))
        _set(self.light, k.get("light_style", "lantern"))
        _set(self.rail, k.get("rail", "ms_grill"))
        _set(self.columns, k.get("columns", "ionic"))
        _set(self.gate, k.get("gate_color", "black"))
        for key, ch in self.checks.items():
            ch.setChecked(bool(k.get(key, LS.KIT_DEFAULT.get(key, True))))
        for key, (b, _c) in self.cols.items():
            c = list(k.get(key) or LS.KIT_DEFAULT[key])
            self.cols[key] = (b, c)
            q = QColor.fromRgbF(*[min(max(float(v), 0.0), 1.0)
                                  for v in c[:3]])
            b.setStyleSheet(f"background: {q.name()};")

    def _kit(self) -> dict:
        k = {"style": self.style.currentData(),
             "front": self.front.currentData(),
             "roof": self.roof.currentData(),
             "roof_slope": round(self.slope.value(), 2),
             "roof_eave": round(self.eave.value(), 3),
             "annex_roof": self.annex.isChecked(),
             "fascia_d": round(self.fd.value(), 3),
             "fascia_h": round(self.fh.value(), 3),
             "win_head": self.head.currentData(),
             "win_frame": self.frame.currentData(),
             "win_style": self.wstyle.currentData(),
             "light_style": self.light.currentData(),
             "rail": self.rail.currentData(),
             "columns": self.columns.currentData(),
             "gate_color": self.gate.currentData(),
             "manual": True}
        for key, ch in self.checks.items():
            k[key] = ch.isChecked()
        for key, (_b, c) in self.cols.items():
            k[key] = [round(float(v), 3) for v in c[:3]]
        return k

    def _load_preset(self):
        self._fill(LS.preset(self.style.currentData()))

    def _pick(self, key):
        b, c = self.cols[key]
        q = QColorDialog.getColor(QColor.fromRgbF(*c[:3]), self, "Colour")
        if q.isValid():
            self.cols[key] = (b, [q.redF(), q.greenF(), q.blueF()])
            b.setStyleSheet(f"background: {q.name()};")

    # ---- actions -----------------------------------------------------------------
    def _apply(self):
        doc = self.panel.doc()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rep = LS.apply_kit(doc, self._kit())
            doc["look"]["manual"] = True
        except Exception as e:  # noqa: BLE001
            from .host import log_error
            log_error("elevdesign.apply")
            QApplication.restoreOverrideCursor()
            self.panel.flash(f"Not applied — {e}", 9000)
            return
        QApplication.restoreOverrideCursor()
        self.panel.commit(doc, "Elevations designed")
        bits = [f"{rep[k]} {t}" for k, t in (
            ("roofs", "tiled roofs"), ("arched", "arched"),
            ("grilles", "grilles"), ("arcades", "arcades"),
            ("rails", "railings"), ("columns", "columns")) if rep.get(k)]
        self.panel.flash("Elevations designed" + (": " + ", ".join(bits)
                                                  if bits else ""), 9000)

    def _remove(self):
        from . import project as PJ
        doc = self.panel.doc()
        LS.remove_kit(doc)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:              # the windows, railings … as the plans draw them
            PJ.update_from_cad(doc, as_cad=False)
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("elevdesign.remove")
        finally:
            QApplication.restoreOverrideCursor()
        self.panel.commit(doc, "Elevation design removed")
        self.panel.flash("Elevation design removed — the elevations as the "
                         "plans draw them", 8000)

    def _from_picture(self):
        from . import refelev as RE
        doc = self.panel.doc()
        ref = next((r for r in doc.get("ref_elev") or []
                    if RE.effective_side(r) == "perspective"), None)
        if ref is None:
            self.panel.flash("No perspective added — add one in «Elevations "
                             "/ perspectives to follow…»", 8000)
            return
        try:
            src = RE.source(ref["file"], int(ref.get("page", 1) or 1))
            k = LS.kit_from_picture(LS.palette(src["img"]))
        except Exception as e:  # noqa: BLE001
            self.panel.flash(f"Not read — {e}", 8000)
            return
        k["front"] = self.front.currentData()
        self._fill(k)
