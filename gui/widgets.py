"""Small reusable widgets: cards, stat tiles, toggle switch, setting rows."""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

ACCENT = "#ff7a1a"
ACCENT_DIM = "#3a2414"
TRACK_OFF = "#2a2f3a"


class Card(QFrame):
    """Rounded panel with an optional title and subtitle."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 18)
        self.body.setSpacing(12)
        if title:
            t = QLabel(title)
            t.setObjectName("CardTitle")
            self.body.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("Muted")
            s.setWordWrap(True)
            self.body.addWidget(s)

    def add(self, w):
        self.body.addWidget(w)
        return w

    def add_layout(self, layout):
        self.body.addLayout(layout)
        return layout


class StatTile(QFrame):
    def __init__(self, label: str, value: str = "0", parent=None):
        super().__init__(parent)
        self.setObjectName("StatTile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        cap = QLabel(label.upper())
        cap.setObjectName("StatLabel")
        lay.addWidget(self.value)
        lay.addWidget(cap)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set(self, text: str):
        self.value.setText(text)


class Toggle(QCheckBox):
    """iOS-style switch. Behaves like a QCheckBox (toggled signal, isChecked)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self.setText("")

    def sizeHint(self):
        return QSize(46, 26)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        enabled = self.isEnabled()
        track = QColor(ACCENT if on else TRACK_OFF)
        if not enabled:
            track.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        r = QRectF(1, 3, 44, 20)
        p.drawRoundedRect(r, 10, 10)
        knob = QColor("#ffffff" if enabled else "#9aa0aa")
        p.setBrush(knob)
        x = 23 if on else 3
        p.drawEllipse(QRectF(x, 1, 24, 24).adjusted(2, 2, -2, -2))
        p.end()


class SettingRow(QWidget):
    """Label + help text on the left, a control on the right."""

    def __init__(self, title: str, help_text: str, control: QWidget, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("RowTitle")
        text.addWidget(t)
        if help_text:
            h = QLabel(help_text)
            h.setObjectName("Muted")
            h.setWordWrap(True)
            text.addWidget(h)
        lay.addLayout(text, 1)
        lay.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.control = control


class StatusDot(QWidget):
    def __init__(self, color: str = "#6b7280", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(12, 12)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        glow = QColor(self._color)
        glow.setAlpha(70)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(0, 0, 12, 12)
        p.setBrush(self._color)
        p.drawEllipse(3, 3, 6, 6)
        p.end()


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    f.setFixedHeight(1)
    return f


def bgr_to_pixmap(img: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)
