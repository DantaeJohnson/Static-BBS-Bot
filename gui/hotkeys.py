"""Global hotkeys (work even while the game has focus).

Uses the `keyboard` package. If it isn't available or can't hook the keyboard,
the GUI buttons still work - hotkeys are a convenience.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from bbsbot import logger as log


class Hotkeys(QObject):
    pause_pressed = Signal()
    stop_pressed = Signal()

    def __init__(self):
        super().__init__()
        self._handles = []
        self.available = False

    def register(self, pause_key: str, stop_key: str) -> bool:
        self.unregister()
        try:
            import keyboard
        except Exception:
            log.warning("Hotkeys unavailable (the 'keyboard' package isn't installed).")
            return False
        try:
            if pause_key:
                self._handles.append(keyboard.add_hotkey(pause_key, self.pause_pressed.emit))
            if stop_key:
                self._handles.append(keyboard.add_hotkey(stop_key, self.stop_pressed.emit))
            self.available = True
            return True
        except Exception as e:
            log.warning(f"Couldn't register hotkeys ({e}). Use the on-screen buttons instead.")
            self.available = False
            return False

    def unregister(self):
        if not self._handles:
            return
        try:
            import keyboard
            for h in self._handles:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
        except Exception:
            pass
        self._handles = []
