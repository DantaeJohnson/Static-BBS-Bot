"""Template capture (drag a box around a button) and detection test dialogs."""
from __future__ import annotations

import os
import re

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QRubberBand, QVBoxLayout)

from bbsbot import paths
from bbsbot.story import stage_map
from bbsbot.templates import SPEC_BY_NAME, SPECS
from bbsbot.vision import BASE_H, BASE_W, Frame, TemplateLibrary, imwrite
from gui.widgets import bgr_to_pixmap

VIEW_W = 1120  # on-screen width of the screenshot inside dialogs


class SelectableImage(QLabel):
    """Shows an image; the user drags a rectangle to select a region."""
    selection_changed = Signal(QRect)

    def __init__(self, image: np.ndarray, parent=None):
        super().__init__(parent)
        self.image = image
        self.scale = VIEW_W / image.shape[1]
        pm = bgr_to_pixmap(image).scaled(QSize(VIEW_W, int(image.shape[0] * self.scale)),
                                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pm)
        self.setFixedSize(pm.size())
        self.setCursor(Qt.CrossCursor)
        self.band = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()
        self.selection = QRect()  # in image coordinates

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.origin = e.position().toPoint()
            self.band.setGeometry(QRect(self.origin, QSize()))
            self.band.show()

    def mouseMoveEvent(self, e):
        if not self.origin.isNull():
            self.band.setGeometry(QRect(self.origin, e.position().toPoint()).normalized())

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        r = self.band.geometry().intersected(self.rect())
        s = self.scale
        self.selection = QRect(int(r.x() / s), int(r.y() / s), int(r.width() / s), int(r.height() / s))
        self.origin = QPoint()
        self.selection_changed.emit(self.selection)

    def crop(self) -> np.ndarray | None:
        r = self.selection
        if r.width() < 8 or r.height() < 8:
            return None
        return self.image[r.y():r.y() + r.height(), r.x():r.x() + r.width()].copy()


class CaptureDialog(QDialog):
    """Save a region of a game screenshot as a template (user override)."""

    def __init__(self, frame: Frame, preset_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture template")
        self.saved_name = ""
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        tip = QLabel("Drag a tight box around the button or text the bot should recognise. "
                     "Avoid parts that change (numbers, timers, character art).")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.view = SelectableImage(frame.image)
        lay.addWidget(self.view, 0, Qt.AlignHCenter)

        row = QHBoxLayout()
        row.addWidget(QLabel("Save as"))
        self.name = QComboBox()
        self.name.setEditable(True)
        self.name.setMinimumWidth(260)
        for spec in SPECS:
            self.name.addItem(f"{spec.name}", spec.name)
        if preset_name:
            self.name.setCurrentText(preset_name)
        self.name.currentTextChanged.connect(self._describe)
        row.addWidget(self.name)
        self.desc = QLabel()
        self.desc.setObjectName("Muted")
        self.desc.setWordWrap(True)
        row.addWidget(self.desc, 1)
        self.preview = QLabel("No selection")
        self.preview.setObjectName("Muted")
        self.preview.setMinimumSize(160, 50)
        self.preview.setAlignment(Qt.AlignCenter)
        row.addWidget(self.preview)
        lay.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("Primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.view.selection_changed.connect(self._on_select)
        self._describe(self.name.currentText())

    def _describe(self, name: str):
        spec = SPEC_BY_NAME.get(name.strip())
        self.desc.setText(spec.description if spec else "Custom template name")

    def _on_select(self, r: QRect):
        crop = self.view.crop()
        if crop is None:
            self.preview.setText("Selection too small")
            return
        pm = bgr_to_pixmap(crop)
        if pm.width() > 220:
            pm = pm.scaledToWidth(220, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.setToolTip(f"{r.width()} x {r.height()} px")

    def _save(self):
        name = re.sub(r"[^a-z0-9_]+", "_", self.name.currentText().strip().lower()).strip("_")
        crop = self.view.crop()
        if not name:
            QMessageBox.warning(self, "Name needed", "Pick or type a template name.")
            return
        if crop is None:
            QMessageBox.warning(self, "No selection", "Drag a box around the button first (at least 8x8 px).")
            return
        path = os.path.join(paths.user_templates_dir(), f"{name}.png")
        if not imwrite(path, crop):
            QMessageBox.critical(self, "Save failed", f"Couldn't write {path}")
            return
        self.saved_name = name
        self.accept()


class DetectDialog(QDialog):
    """Show what the bot currently recognises on a screenshot."""

    def __init__(self, frame: Frame, lib: TemplateLibrary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detection test")
        lay = QHBoxLayout(self)
        lay.setSpacing(14)

        img = frame.image.copy()
        found = []
        scores = []
        for name in lib.names():
            m = lib.find(frame, name)
            sc = m.score if m else lib.score(frame, name)
            scores.append((sc, name, m is not None))
            if m:
                found.append(m)
        for m in found:
            cv2.rectangle(img, (m.x, m.y), (m.x + m.w, m.y + m.h), (26, 122, 255), 3)
            cv2.putText(img, f"{m.name} {m.score:.2f}", (m.x, max(14, m.y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (26, 122, 255), 2, cv2.LINE_AA)

        # Story map overlay: which stages the bot considers cleared / open / locked
        view = stage_map.analyse(lib, frame, lib.threshold)
        if view.is_map:
            target = view.playable[0] if view.playable else None
            for st in view.stages:
                color = (128, 128, 128) if st.cleared else (80, 80, 240) if st.locked else (80, 222, 74)
                label = "CLEAR" if st.cleared else "LOCKED" if st.locked else "OPEN"
                if st is target:
                    label = "NEXT >"
                    cv2.circle(img, st.click_point, 26, (26, 122, 255), 4)
                cv2.circle(img, (st.x, st.y), 10, color, -1)
                cv2.putText(img, label, (st.x - 30, st.y + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2,
                            cv2.LINE_AA)

        left = QVBoxLayout()
        summary = f"{len(found)} element(s) recognised  -  threshold {lib.threshold:.2f}"
        if view.is_map:
            summary += (f"  -  story map: {len(view.stages)} stage(s), "
                        f"{len(view.playable)} open" + ("" if view.playable else " (nothing to play)"))
        title = QLabel(summary)
        title.setObjectName("CardTitle")
        left.addWidget(title)
        pic = QLabel()
        pm = bgr_to_pixmap(img).scaledToWidth(VIEW_W - 180, Qt.SmoothTransformation)
        pic.setPixmap(pm)
        left.addWidget(pic)
        if not frame.aspect_ok:
            warn = QLabel(f"Warning: the game window is {frame.source_size[0]}x{frame.source_size[1]}, "
                          f"not 16:9. Resize it (e.g. 1600x900) for reliable matching.")
            warn.setStyleSheet("color: #fbbf24;")
            warn.setWordWrap(True)
            left.addWidget(warn)
        lay.addLayout(left)

        right = QVBoxLayout()
        lbl = QLabel("Best score per template")
        lbl.setObjectName("RowTitle")
        right.addWidget(lbl)
        lst = QListWidget()
        lst.setMinimumWidth(260)
        for sc, name, hit in sorted(scores, reverse=True):
            item = QListWidgetItem(f"{'●' if hit else '○'}  {name:<22} {sc:.2f}")
            item.setForeground(QColor("#4ade80") if hit else
                              QColor("#fbbf24") if sc > lib.threshold - 0.1 else QColor("#6b7280"))
            lst.addItem(item)
        right.addWidget(lst, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        right.addWidget(close)
        lay.addLayout(right)

