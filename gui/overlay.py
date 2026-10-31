"""Small always-on-top pill shown over the game while the bot runs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setStyleSheet(
            "background: rgba(13,15,19,215); color: #ffffff; border: 1px solid #ff7a1a;"
            "border-radius: 14px; padding: 7px 16px; font-weight: 700; font-size: 12px;")
        lay.addWidget(self.label)

    def show_text(self, text: str):
        self.label.setText(text)
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + 12)
        self.show()
