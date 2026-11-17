"""3.64.44: the «Reference elevations / perspectives» window — pictures or
drawings of each side of the building (image, PDF, DXF / DWG) the model
follows, and perspectives to compare it with (see refelev.py)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QScrollArea,
                               QSpinBox, QTableWidget, QVBoxLayout)

from . import refelev as RE

FILTER = ("Elevations / perspectives (*.png *.jpg *.jpeg *.bmp *.tif *.tiff "
          "*.webp *.pdf *.dxf *.dwg);;All files (*)")


class _Viewer(QDialog):
    """A picture kept open beside the model (a perspective to compare)."""

    def __init__(self, parent, title, img):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.setModal(False)
        self._pix = QPixmap.fromImage(img)
        lay = QVBoxLayout(self)
        self._lab = QLabel()
        self._lab.setAlignment(Qt.AlignCenter)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self._lab)
        lay.addWidget(sc)
        self.resize(900, 650)
        self._fit()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        w, h = max(self.width() - 40, 50), max(self.height() - 40, 50)
        self._lab.setPixmap(self._pix.scaled(w, h, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))


class RefElevDialog(QDialog):
    COLS = ("File", "Shows", "Page", "Follow", "Show", "Result")

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle("Reference elevations / perspectives")
        self.setModal(False)
        self._viewers = []
        lay = QVBoxLayout(self)
        info = QLabel(
            "Add the elevations of each side (a picture, a PDF page or a "
            "DXF / DWG) and any perspective. <b>Follow</b> finds each "
            "elevation's scale and side by its windows and doors and sets "
            "every opening's sill and head as drawn — and again at every "
            "«Update from CAD», so all sides keep to them. <b>Show</b> stands "
            "each elevation beside its side of the model, half see-through, "
            "to compare. A <b>perspective</b> (a photo or render of the "
            "house wanted) gives its <b>look</b>: Follow takes its colours "
            "and its style — clay-tile hip roofs, arched windows, iron "
            "railings when it shows them — onto the model, sizes kept; "
            "«Open picture» keeps it open beside the model.<br>"
            "Clean elevations work best (lines on white, no shadows). "
            "Set the side when «Auto» picks the wrong one; set the storey "
            "heights in «Floor height» — a picture has no level notes.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #8a94a3;")
        lay.addWidget(info)
        self.tab = QTableWidget(0, len(self.COLS))
        self.tab.setHorizontalHeaderLabels(self.COLS)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = self.tab.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        for c_, w_ in ((1, 200), (2, 60), (3, 60), (4, 60)):
            hh.setSectionResizeMode(c_, QHeaderView.Interactive)
            hh.resizeSection(c_, w_)
        lay.addWidget(self.tab, 1)
        row = QHBoxLayout()
        for text, fn, tip in (
                ("Add…", self._add, "Pick elevation pictures, PDFs or "
                 "DXF / DWG files (several at once)"),
                ("Remove", self._remove, "Take the selected reference out"),
                ("Follow now", self._follow, "Set the openings' sills and "
                 "heads from the elevations (Ctrl+Z undoes it)"),
                ("Show beside model", self._show, "Stand each followed "
                 "elevation beside its side of the model"),
                ("Hide", self._hide, "Take the shown elevations away"),
                ("Open picture", self._view, "Open the selected reference "
                 "(a perspective) in its own window")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, f=fn: f())
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        lay.addLayout(row)
        self.resize(980, 380)
        self._load()

    # ---- rows ----------------------------------------------------------------
    def _doc(self):
        return self.panel.doc()

    def _load(self):
        self.tab.setRowCount(0)
        for r in self._doc().get("ref_elev") or []:
            self._row(r)

    def _row(self, r, result=""):
        i = self.tab.rowCount()
        self.tab.insertRow(i)
        lab = QLabel(os.path.basename(r["file"]))
        lab.setToolTip(r["file"])
        lab.setProperty("path", r["file"])
        self.tab.setCellWidget(i, 0, lab)
        cb = QComboBox()
        for k in RE.SIDES:
            cb.addItem(RE.SIDE_LABELS[k], k)
        cb.setCurrentIndex(max(RE.SIDES.index(r.get("side", "auto"))
                               if r.get("side") in RE.SIDES else 0, 0))
        self.tab.setCellWidget(i, 1, cb)
        sp = QSpinBox()
        sp.setRange(1, 999)
        sp.setValue(int(r.get("page", 1) or 1))
        sp.setEnabled(RE.kind_of(r["file"]) == "pdf")
        self.tab.setCellWidget(i, 2, sp)
        for c, key in ((3, "follow"), (4, "show")):
            ch = QCheckBox()
            ch.setChecked(bool(r.get(key, True)))
            self.tab.setCellWidget(i, c, ch)
        fit = r.get("fit") or {}
        res = QLabel(result or (f"{fit['side']} side, {fit['score']:.2f}"
                                if fit else ""))
        res.setWordWrap(True)
        self.tab.setCellWidget(i, 5, res)

    def _rows(self) -> list:
        old = {r["file"] + "|" + str(r.get("page", 1)): r
               for r in self._doc().get("ref_elev") or []}
        out = []
        for i in range(self.tab.rowCount()):
            path = self.tab.cellWidget(i, 0).property("path")
            side = self.tab.cellWidget(i, 1).currentData()
            page = self.tab.cellWidget(i, 2).value()
            r = {"file": path, "page": page, "side": side,
                 "follow": self.tab.cellWidget(i, 3).isChecked(),
                 "show": self.tab.cellWidget(i, 4).isChecked()}
            o = old.get(path + "|" + str(page))
            if o and o.get("fit") and o.get("side") == side:
                r["fit"] = o["fit"]
            out.append(r)
        return out

    def _store(self, msg="Reference elevations stored", doc=None):
        doc = doc or self._doc()
        doc["ref_elev"] = self._rows()
        self.panel.commit(doc, msg)
        return doc

    # ---- actions -------------------------------------------------------------
    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Reference elevations / perspectives", "", FILTER)
        for f in files:
            if not RE.kind_of(f):
                continue
            self._row({"file": f, "page": 1, "side": "auto", "show": True,
                       "follow": True})
        if files:
            self._store()

    def _remove(self):
        rows = sorted({ix.row() for ix in self.tab.selectedIndexes()},
                      reverse=True)
        for i in rows:
            self.tab.removeRow(i)
        if rows:
            self._store()

    def _follow(self):
        doc = self._doc()
        doc["ref_elev"] = self._rows()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            out = RE.follow_all(doc)
        finally:
            QApplication.restoreOverrideCursor()
        self.panel.commit(doc, "Openings set from the reference elevations")
        msgs, by_row = {}, {}
        for name, rep in out:
            if rep.get("error"):
                m = "Not followed — " + rep["error"]
            elif rep.get("look"):
                from .lookstyle import STYLES
                m = (f"Look applied: {STYLES.get(rep['look'], rep['look'])}"
                     + (f" · {rep['roofs']} tiled hip roofs"
                        if rep.get("roofs") else "")
                     + (f" · {rep['arched']} arched" if rep.get("arched")
                        else "")
                     + (f" · {rep['grilles']} grilles" if rep.get("grilles")
                        else "")
                     + (f" · {rep['rails']} iron railings" if rep.get("rails")
                        else "")
                     + f" · colours: {rep.get('colours', '')}")
            elif rep.get("skipped"):
                m = "Shown only — open it with «Open picture»"
            else:
                m = (f"{rep['side']} side · {rep['jambs']} openings "
                     f"line up · {rep.get('openings', 0)} set"
                     + (f" · {rep['note']}" if rep.get("note") else ""))
            msgs[name] = m
            by_row[rep.get("_i", -1)] = m
        self._load()
        for i in range(self.tab.rowCount()):
            if i in by_row:
                self.tab.cellWidget(i, 5).setText(by_row[i])
        self._show(quiet=True)
        try:
            self.panel.flash("Reference elevations followed: " + "; ".join(
                f"{k}: {v}" for k, v in msgs.items()), 12000)
        except Exception:  # noqa: BLE001
            pass

    def _show(self, quiet=False):
        doc = self._store("Reference elevations shown") if not quiet \
            else self._doc()
        try:
            shown = RE.show(doc, self.panel.vp.scene)
        except Exception as e:  # noqa: BLE001
            from .host import log_error
            log_error("refui.show")
            self.panel.flash(f"Not shown — {e}", 8000)
            return
        self.panel.vp.update()
        if not quiet:
            self.panel.flash(
                "Shown beside the model: " + ", ".join(
                    f"{n} ({d})" for n, d in shown) if shown else
                "Nothing to show yet — «Follow now» first (it finds each "
                "elevation's side and scale)", 8000)

    def _hide(self):
        RE.hide(self.panel.vp.scene)
        self.panel.vp.update()

    def _view(self):
        rows = sorted({ix.row() for ix in self.tab.selectedIndexes()})
        if not rows:
            rows = [i for i in range(self.tab.rowCount())
                    if self.tab.cellWidget(i, 1).currentData() ==
                    "perspective"]
        for i in rows:
            path = self.tab.cellWidget(i, 0).property("path")
            try:
                src = RE.source(path, self.tab.cellWidget(i, 2).value())
            except Exception as e:  # noqa: BLE001
                self.panel.flash(f"{os.path.basename(path)}: {e}", 8000)
                continue
            v = _Viewer(self, os.path.basename(path), src["img"])
            v.show()
            self._viewers.append(v)


def refresh_shown(panel) -> None:
    """After a rebuild: the shown elevations stood again where they go."""
    doc = panel.doc()
    if any(r.get("show", True) and r.get("fit")
           for r in doc.get("ref_elev") or []):
        try:
            RE.show(doc, panel.vp.scene)
            panel.vp.update()
        except Exception:  # noqa: BLE001
            from .host import log_error
            log_error("refui.refresh_shown")
