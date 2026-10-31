"""The bot's eyes and hands: capture the game and click on it.

`GameDevice` is the real implementation (Windows). Tests swap in a fake with
the same three methods: grab(), click(), drag().
"""
from __future__ import annotations

import time

import numpy as np

from bbsbot.vision import BASE_H, BASE_W, Frame
from bbsbot.window import GameWindow, Rect


class WindowNotFound(Exception):
    pass


class GameDevice:
    def __init__(self, title: str, auto_focus: bool = True):
        self.window = GameWindow(title)
        self.auto_focus = auto_focus
        self._sct = None  # mss must be created on the thread that uses it
        self._rect: Rect | None = None

    # -- capture -------------------------------------------------------------
    def grab(self) -> Frame | None:
        rect = self.window.client_rect()
        if rect is None or not rect.valid:
            self._rect = None
            return None
        if self._sct is None:
            import mss
            self._sct = mss.mss()
        shot = self._sct.grab({"left": rect.left, "top": rect.top,
                               "width": rect.width, "height": rect.height})
        img = np.asarray(shot)[:, :, :3]  # BGRA -> BGR
        self._rect = rect
        return Frame(np.ascontiguousarray(img), (rect.width, rect.height))

    @property
    def rect(self) -> Rect | None:
        return self._rect

    def _to_screen(self, bx: float, by: float) -> tuple[int, int]:
        rect = self._rect or self.window.client_rect()
        if rect is None:
            raise WindowNotFound("Game window not found")
        sx = rect.left + bx * rect.width / BASE_W
        sy = rect.top + by * rect.height / BASE_H
        return int(round(sx)), int(round(sy))

    def _prepare(self):
        import pyautogui
        pyautogui.FAILSAFE = True  # slam mouse into a screen corner = emergency stop
        pyautogui.PAUSE = 0.02
        if self.auto_focus and not self.window.is_foreground():
            self.window.focus()
        return pyautogui

    # -- input ---------------------------------------------------------------
    def click(self, bx: float, by: float, double: bool = False) -> None:
        pg = self._prepare()
        x, y = self._to_screen(bx, by)
        pg.click(x, y)
        if double:
            time.sleep(0.35)
            pg.click(x, y)

    def drag(self, bx1: float, by1: float, bx2: float, by2: float, duration: float = 0.6) -> None:
        """Swipe (used to scroll quest lists)."""
        pg = self._prepare()
        x1, y1 = self._to_screen(bx1, by1)
        x2, y2 = self._to_screen(bx2, by2)
        pg.moveTo(x1, y1)
        pg.mouseDown()
        steps = 12
        for i in range(1, steps + 1):
            pg.moveTo(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
            time.sleep(duration / steps)
        time.sleep(0.15)  # hold so the list doesn't fling
        pg.mouseUp()

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None


def make_device(settings):
    """The device the settings ask for: BlueStacks over ADB, or the PC game window."""
    from bbsbot.settings import BACKEND_ADB
    if settings.backend == BACKEND_ADB:
        from bbsbot.adb import AdbDevice, AdbError, find_adb
        path = find_adb(settings.adb_path)
        if not path:
            raise AdbError("adb wasn't found. Use Settings > Connection > 'Test connection' "
                           "to download it automatically.")
        dev = AdbDevice(path, settings.adb_serial)
        if not dev.client.connect():
            raise AdbError(f"Couldn't connect to the emulator at '{settings.adb_serial or 'auto'}'. "
                           "Is BlueStacks running with Android Debug Bridge turned on?")
        return dev
    return GameDevice(settings.window_title, settings.auto_focus_game)
