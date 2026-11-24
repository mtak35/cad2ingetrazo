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

ROOFS = [("reference", "As the reference elevations draw it"),
         ("asdrawn", "As drawn (flat roof, parapets)"),
         ("hip", "Tiled hip roofs over every block"),
         ("gable", "Tiled gable roofs over every block (steep: Tudor, "
          "Cape Cod)"),
         ("pyramid", "Pyramid roofs (the hips meet at one point)"),
         ("dutch", "Dutch gable (hip with a gablet on top)"),
         ("jerkinhead", "Jerkinhead (clipped gable ends)"),
         ("gambrel", "Gambrel (barn roof)"),
         ("saltbox", "Saltbox (long and short slopes)"),
         ("butterfly", "Butterfly (V, valley in the middle)"),
         ("shed", "Shed / mono-pitch"),
         ("bonnet", "Bonnet (flared eaves)"),
         ("m_roof", "M roof (twin gables, valley between)"),
         ("arched", "Arched (barrel vault)"),
         ("clerestory", "Clerestory (raised centre between lower slopes)")]
HEADS = [("asdrawn", "As drawn"), ("arch", "Arched (semicircle)"),
         ("flat", "Flat")]
FRAMES = [("asdrawn", "As drawn"), ("upvc", "uPVC, white"),
          ("wood", "Wood"), ("black", "Black aluminium"),
          ("aluminium", "Aluminium"), ("steel", "Steel")]
RAILS = [("asdrawn", "As drawn"), ("ms_grill", "Wrought iron"),
         ("glass_post", "Glass panels between posts"),
         ("glass", "Frameless glass"),
         ("ss_bars", "Stainless steel balusters"),
         ("wood", "Timber balusters"), ("solid", "Solid parapet"),
         ("baluster", "Stone balustrade (turned balusters, newel posts)"),
         ("baluster_vase", "Stone balustrade — fat vase balusters, piers"),
         ("baluster_pier", "Stone balustrade — ball-topped piers"),
         ("baluster_panel", "Stone balustrade — panelled piers, pyramid caps"),
         ("iron_belly", "Wrought iron — belly (lens) bars"),
         ("iron_wave", "Wrought iron — wavy scroll bars"),
         ("iron_mesh", "Square mesh screen (dark steel)"),
         ("iron_geo", "Geometric nested-square panels (dark steel)"),
         ("panel_diamond", "Solid panel with diamond inlays"),
         ("alu_bars", "Grey aluminium flat bars")]
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
          ("Window detail", [
              ("sills_lintels", "Projecting sills and lintels on every "
               "window"),
              ("brise_soleil", "Vertical louvre fins (brise-soleil) in "
               "front of windows"),
              ("jali", "Jali / lattice screens over windows"),
              ("pilasters", "Pilasters between the front's windows")]),
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
               "eaves"),
              ("arch_panels", "Moorish / Gulf: carved panels round the big "
               "arched doors and windows")])]
COLOURS = [("wall", "Walls"), ("trim", "Mouldings / trims"),
           ("stone", "Stone (plinth, quoins, door cladding)"),
           ("clad", "Cladding panels"), ("roof_c", "Roof tiles"),
           ("accent", "Accent (timber, shutters, Deco metal)"),
           ("metal", "Metal (railings, lanterns)")]


#: 3.64.97 — the finishes that suit each elevation type (material keys of
#: finishes.FLOOR_GROUPS; boundary wall designs / finishes of site.py)
_F = {  # family: (terrace, car porch, entrance landing, front wall design,
        #          side wall design, front finish, side finish)
    "mediterranean": ("finish/botticino_marble.jpg", "floor/paving_stone.jpg",
                      "finish/carrara_marble.jpg", "stone_piers", "piers",
                      "stone", "plaster"),
    "classic": ("finish/botticino_marble.jpg", "finish/sandstone_cladding.jpg",
                "finish/statuario_marble.jpg", "stone_piers", "piers",
                "white", "white"),
    "modern": ("finish/porcelain_grey.jpg", "finish/porcelain_grey.jpg",
               "finish/marquina_marble.jpg", "coping", "coping", "white",
               "white"),
    "raw": ("finish/slate_tiles.jpg", "floor/paving_stone.jpg",
            "finish/slate_tiles.jpg", "plain", "plain", "concrete",
            "concrete"),
    "brick": ("floor/brown_terrace_tiles.jpg", "floor/paving_stone.jpg",
              "finish/slate_tiles.jpg", "piers", "piers", "brick", "brick"),
    "cottage": ("floor/brown_terrace_tiles.jpg", "floor/paving_stone.jpg",
                "finish/sandstone_cladding.jpg", "coping", "coping",
                "white", "white"),
    "timber": ("finish/oak_planks.jpg", "finish/sandstone_cladding.jpg",
               "finish/oak_planks.jpg", "wood_screen", "plain", "plaster",
               "plaster"),
    "gulf": ("finish/botticino_marble.jpg", "finish/sandstone_cladding.jpg",
             "finish/carrara_marble.jpg", "stone_piers", "coping", "stone",
             "plaster"),
}
_FAMILY = {"classical": "classic", "neoclassical": "classic",
           "royal": "classic", "royal_villa": "classic",
           "italianate": "mediterranean", "mediterranean": "mediterranean",
           "modern": "modern", "minimalist": "modern",
           "contemporary": "modern", "bauhaus": "modern",
           "hightech": "modern", "artdeco": "modern", "midcentury": "timber",
           "brutalist": "raw", "industrial": "raw", "tudor": "brick",
           "georgian": "brick", "victorian": "brick", "capecod": "cottage",
           "farmhouse": "cottage", "tropical": "timber", "arabian": "gulf", "gulf_palace": "gulf"}
FIN_KEYS = ("fin_terrace", "fin_porch", "fin_entrance", "bw_front_style",
            "bw_style", "bw_front_finish", "bw_finish")


def suggest(style) -> dict:
    fam = _FAMILY.get(style, "gulf" if str(style).startswith("mosque")
                      else "mediterranean")
    d = dict(zip(FIN_KEYS, _F[fam]))
    d["bw_front_finish"] = d["bw_finish"] = "match"   # 3.64.98: as the house
    return d


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
        self.auto = QCheckBox("Apply to the model as soon as the style is "
                              "chosen")
        self.auto.setChecked(True)
        self.auto.setToolTip("Off: the style only fills the choices, "
                             "«Apply design» puts it on the model")
        f0.addRow(self.auto)
        self.showall = QCheckBox("Show every element (unlock the greyed "
                                 "ones)")
        self.showall.setToolTip("Elements that do not belong to the "
                                "chosen style are greyed out")
        self.showall.toggled.connect(lambda _c: self._relevance())
        f0.addRow(self.showall)
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
        self.keep_roof = QCheckBox("Keep the roof structure as built (the "
                                   "design does not touch the roof)")
        self.keep_roof.setChecked(False)
        self.keep_roof.setToolTip("Ticked: the roof, parapets and roof "
                                  "slab stay as imported. Unticked: the "
                                  "roof below is built — «As the reference "
                                  "elevations draw it» reads the form "
                                  "from the elevations.")
        self.keep_roof.toggled.connect(lambda _c: self._relevance())
        f1.addRow(self.keep_roof)
        f1.addRow("Roof", self.roof)
        self.roof.currentIndexChanged.connect(lambda _i: self._relevance())
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
        # 3.64.113: the parapet cornice, the geometrical wall panels
        from . import project as PJ_
        from . import wallpanels as WP
        self.pstyle = _combo(PJ_.PARAPET_STYLES)
        self.pstyle.setToolTip(
            "The cornice / coping on every solid parapet wall: the "
            "terraces', the balconies', the roof's (set the railings to "
            "«Solid parapet» to have the walls)")
        f2.addRow("Parapet cornice (terraces, balconies)", self.pstyle)
        self.geo = _combo(WP.PATTERNS)
        self.geo.setToolTip("A raised geometric pattern over the blank "
                            "stretches of the outside walls (clear of the "
                            "windows, doors and corners)")
        f2.addRow("Geometric wall panels", self.geo)
        self.geo_where = _combo(WP.WHERE)
        f2.addRow("… on", self.geo_where)
        self.geo_size = QDoubleSpinBox()
        self.geo_size.setRange(0.12, 1.0)
        self.geo_size.setSingleStep(0.05)
        self.geo_size.setSuffix(" m")
        f2.addRow("… cell size", self.geo_size)
        # 3.64.119: pergolas and louvers
        from . import elevparts as EP
        self.pergola = _combo(EP.PERGOLAS)
        self.pergola.setToolTip("A pergola over every terrace / balcony / "
                                "sit-out the plan names (posts, beams, "
                                "slats or blades)")
        f2.addRow("Pergola (over terraces)", self.pergola)
        self.pergola_h = QDoubleSpinBox()
        self.pergola_h.setRange(2.2, 4.5)
        self.pergola_h.setSingleStep(0.1)
        self.pergola_h.setSuffix(" m")
        f2.addRow("… height above the floor", self.pergola_h)
        self.pergola_col = _combo(EP.COLOURS)
        f2.addRow("… colour", self.pergola_col)
        self.louver = _combo(EP.LOUVERS)
        self.louver.setToolTip("Louvers in front of the windows: blades, "
                               "fins or open shutters")
        f2.addRow("Louvers (windows)", self.louver)
        self.louver_where = _combo(EP.LOUVER_WHERE)
        f2.addRow("… on", self.louver_where)
        self.louver_col = _combo(EP.COLOURS)
        f2.addRow("… colour ", self.louver_col)
        from . import stylekit as SK_
        self.crown = _combo(SK_.CROWNS)
        self.crown.setToolTip("A crown on the roof line over the main "
                              "entrance: stepped block, arched / triangular "
                              "/ curved pediment")
        f2.addRow("Entrance crown (roof)", self.crown)
        from . import carving as CV_
        self.carve = _combo(CV_.CARVINGS)
        self.carve.setToolTip("Carved trims and crowns round the windows, "
                              "doors and arches: a stepped frame, a "
                              "rosette band, a carved crown or a keystone; or a full order: classic hood, pilastered, baroque")
        f2.addRow("Carving / crown (openings)", self.carve)
        self.carve_on = _combo(CV_.CARVE_ON)
        f2.addRow("… on", self.carve_on)
        self.carve_where = _combo(CV_.CARVE_WHERE)
        f2.addRow("… where", self.carve_where)
        self.carve_col = _combo(CV_.CARVE_COL)
        f2.addRow("… colour  ", self.carve_col)
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
        # 3.64.97: finishes by area, to suit the elevation type
        from . import finishes as FN
        from .site import WALL_FINISHES, WALL_STYLES
        flo = [("keep", "— leave as built —"),
               ("plain", "Plain (concrete / the default)")]
        try:
            for title, ks in FN.groups_menu(floor=True):
                flo += [(m_, f"{title} · {l_}") for m_, l_ in ks]
        except Exception:  # noqa: BLE001
            pass
        gf = QGroupBox("Finishes by area (suit the elevation type — «Style "
                       "suggests» fills them)")
        ff = QFormLayout(gf)
        self.fin = {}
        for key, lab in (("fin_terrace", "Terraces and balconies — floor"),
                         ("fin_porch", "Car porch — floor"),
                         ("fin_entrance", "Main entrance — landing floor")):
            self.fin[key] = _combo(flo)
            ff.addRow(lab, self.fin[key])
        wst = [("keep", "— leave as built —")]
        self.fin["bw_front_style"] = _combo(
            wst + [("", "Same as the sides")] + list(WALL_STYLES))
        ff.addRow("Boundary wall — front design",
                  self.fin["bw_front_style"])
        self.fin["bw_style"] = _combo(wst + list(WALL_STYLES))
        ff.addRow("Boundary wall — sides / back design",
                  self.fin["bw_style"])
        wfn = [(k, v[0]) for k, v in WALL_FINISHES.items()]
        self.fin["bw_front_finish"] = _combo(
            wst + [("", "Same as the sides")] + wfn)
        ff.addRow("Boundary wall — front finish",
                  self.fin["bw_front_finish"])
        self.fin["bw_finish"] = _combo(wst + wfn)
        ff.addRow("Boundary wall — sides / back finish",
                  self.fin["bw_finish"])
        sg = QPushButton("Style suggests")
        sg.setToolTip("Fill these from the chosen elevation type (marble "
                      "for classical, porcelain for modern, brick for "
                      "Tudor…) — then change what you like")
        sg.clicked.connect(lambda _c=False: self._suggest_fin())
        ff.addRow(sg)
        grid.addWidget(gf, r_ + 1, 0, 1, 2)
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
        # 3.64.101: the roof follows the reference elevations unless the
        # saved design chose another form
        _set(self.roof, "reference")
        self._roof_set = True
        # 3.64.99: the roof is kept unless the saved design made one
        self.keep_roof.setChecked(False)

    # ---- the fields ------------------------------------------------------------
    def _fill(self, k):
        _set(self.style, k.get("style", "mediterranean"))
        _set(self.front, k.get("front", "auto"))
        if not getattr(self, "_roof_set", False) or \
                k.get("roof") == "reference":
            _set(self.roof, k.get("roof", "hip"))   # (a preset leaves the
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
        try:                       # 3.64.113 (None: the model's own)
            _set(self.pstyle, k.get("parapet_style") or self.panel.doc()
                 ["settings"].get("parapet_style", "coping"))
        except Exception:  # noqa: BLE001
            pass
        _set(self.geo, k.get("geo_panel", "none"))
        _set(self.geo_where, k.get("geo_where", "front"))
        self.geo_size.setValue(float(k.get("geo_size", 0.30) or 0.30))
        _set(self.pergola, k.get("pergola", "none"))
        self.pergola_h.setValue(float(k.get("pergola_h", 2.7) or 2.7))
        _set(self.pergola_col, k.get("pergola_col", "timber"))
        _set(self.louver, k.get("louver", "none"))
        _set(self.louver_where, k.get("louver_where", "front"))
        _set(self.louver_col, k.get("louver_col", "timber"))
        _set(self.crown, k.get("entrance_crown", "none"))
        _set(self.carve, k.get("carving", "none"))
        _set(self.carve_on, k.get("carving_on", "all"))
        _set(self.carve_where, k.get("carving_where", "front"))
        _set(self.carve_col, k.get("carving_col", "trim"))
        for key, ch in self.checks.items():
            ch.setChecked(bool(k.get(key, LS.KIT_DEFAULT.get(key, True))))
        self._relevance()
        for key in FIN_KEYS:               # (older designs: as built)
            _set(self.fin[key], k.get(key, "keep"))
        for key, (b, _c) in self.cols.items():
            c = list(k.get(key) or LS.KIT_DEFAULT[key])
            self.cols[key] = (b, c)
            q = QColor.fromRgbF(*[min(max(float(v), 0.0), 1.0)
                                  for v in c[:3]])
            b.setStyleSheet(f"background: {q.name()};")

    def _relevance(self):
        """Grey out what the chosen style does not use (3.64.75)."""
        st = self.style.currentData()
        unlock = self.showall.isChecked()
        for key, ch in self.checks.items():
            ok = unlock or LS.relevant(st, key)
            ch.setEnabled(ok)
            ch.setToolTip("" if ok else "Not part of this style — tick "
                          "«Show every element» to use it anyway")
        keep_ = self.keep_roof.isChecked()
        self.roof.setEnabled(not keep_)
        tiled = self.roof.currentData() in LS.PITCHED and not keep_
        for w in (self.slope, self.eave, self.annex):
            w.setEnabled(tiled or (unlock and not keep_))
        flat = keep_ or self.roof.currentData() == "asdrawn"
        for w in (self.fd, self.fh):
            w.setEnabled(flat or unlock)
        arch = LS.PRESETS.get(st, ("", {}))[1]
        self.head.setEnabled(unlock or not arch.get("mosque"))

    def _kit(self) -> dict:
        k = {"style": self.style.currentData(),
             "front": self.front.currentData(),
             "roof": "asdrawn" if self.keep_roof.isChecked()
             else self.roof.currentData(),
             "roof_keep": self.keep_roof.isChecked(),
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
             "parapet_style": self.pstyle.currentData(),
             "geo_panel": self.geo.currentData(),
             "geo_where": self.geo_where.currentData(),
             "geo_size": round(self.geo_size.value(), 3),
             "pergola": self.pergola.currentData(),
             "pergola_h": round(self.pergola_h.value(), 2),
             "pergola_col": self.pergola_col.currentData(),
             "louver": self.louver.currentData(),
             "louver_where": self.louver_where.currentData(),
             "louver_col": self.louver_col.currentData(),
             "entrance_crown": self.crown.currentData(),
             "carving": self.carve.currentData(),
             "carving_on": self.carve_on.currentData(),
             "carving_where": self.carve_where.currentData(),
             "carving_col": self.carve_col.currentData(),
             "manual": True}
        for key in FIN_KEYS:
            k[key] = self.fin[key].currentData()
        for key, ch in self.checks.items():
            k[key] = ch.isChecked()
        for key, (_b, c) in self.cols.items():
            k[key] = [round(float(v), 3) for v in c[:3]]
        # 3.64.72: what the dialog has no field for comes from the style
        # (a mosque's domes, minarets, tiers stay: «mosque» was dropped)
        base = {kk: v for kk, v in LS.preset(k["style"]).items()
                if kk not in k}
        return dict(base, **k)

    def _suggest_fin(self):
        for key, v in suggest(self.style.currentData()).items():
            _set(self.fin[key], v)

    def _load_preset(self):
        self._fill(LS.preset(self.style.currentData()))
        self._suggest_fin()
        if self.auto.isChecked():
            self._apply()

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
            kit_ = self._kit()
            rep = LS.apply_kit(doc, kit_)
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
        # 3.64.106: only what the design itself did is taken off; the
        # plans are NOT read again, so everything edited by hand stays
        LS.remove_kit(doc)
        self.panel.commit(doc, "Elevation design removed")
        self.panel.flash("Design removed — your own edits are kept", 8000)

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
