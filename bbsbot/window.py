"""Find the game window and work with its *client area* (no title bar/borders).

Uses plain ctypes so there are no extra dependencies. All coordinates are in
physical screen pixels; call `enable_dpi_awareness()` once at startup so
Windows display scaling (125%, 150% ...) doesn't shift clicks.
"""
from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def valid(self) -> bool:
        return self.width > 50 and self.height > 50


def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _window_text(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def list_window_titles() -> list[str]:
    """Visible top-level window titles (used for the 'window not found' hint)."""
    if not IS_WINDOWS:
        return []
    titles: list[str] = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            t = _window_text(hwnd)
            if t:
                titles.append(t)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return titles


class GameWindow:
    """Locates the game by (case-insensitive, partial) title match."""

    def __init__(self, title: str = "Bleach: Brave Souls"):
        self.title = title
        self.hwnd = None

    def find(self) -> bool:
        if not IS_WINDOWS:
            return False
        want = self.title.lower().strip()
        own_pid = ctypes.windll.kernel32.GetCurrentProcessId()
        found = []

        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            text = _window_text(hwnd)
            if text and want in text.lower():
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value != own_pid:  # never match our own GUI
                    found.append(hwnd)
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        self.hwnd = found[0] if found else None
        return self.hwnd is not None

    def exists(self) -> bool:
        if self.hwnd and IS_WINDOWS and user32.IsWindow(self.hwnd):
            return True
        return self.find()

    def is_minimized(self) -> bool:
        return bool(self.hwnd and user32.IsIconic(self.hwnd))

    def client_rect(self) -> Rect | None:
        if not self.exists() or self.is_minimized():
            return None
        rc = wintypes.RECT()
        if not user32.GetClientRect(self.hwnd, ctypes.byref(rc)):
            return None
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        return Rect(pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top)

    def is_foreground(self) -> bool:
        return bool(self.hwnd and user32.GetForegroundWindow() == self.hwnd)

    def focus(self) -> bool:
        """Bring the game to the front (needed for clicks to land)."""
        if not self.exists():
            return False
        if self.is_foreground():
            return True
        SW_RESTORE = 9
        if self.is_minimized():
            user32.ShowWindow(self.hwnd, SW_RESTORE)
        # Windows blocks SetForegroundWindow from background processes unless
        # a key event was just sent; tapping ALT is the standard workaround.
        VK_MENU, KEYUP = 0x12, 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYUP, 0)
        user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.25)
        return self.is_foreground()
