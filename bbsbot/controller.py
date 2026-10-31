"""Thread-safe stop / pause control shared by the GUI, hotkeys and the bot."""
from __future__ import annotations

import threading
import time


class StopRequested(Exception):
    """Raised inside the bot when the user stops it."""


class BotController:
    def __init__(self):
        self._stop = threading.Event()
        self._running = threading.Event()  # set = not paused
        self._running.set()

    def reset(self) -> None:
        self._stop.clear()
        self._running.set()

    def stop(self) -> None:
        self._stop.set()
        self._running.set()  # wake a paused bot so it can exit

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def toggle_pause(self) -> bool:
        """Returns True if now paused."""
        if self._running.is_set():
            self.pause()
            return True
        self.resume()
        return False

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def checkpoint(self) -> None:
        """Block while paused; raise if stopped."""
        while not self._running.is_set():
            self._running.wait(0.2)
        if self._stop.is_set():
            raise StopRequested()

    def wait(self, seconds: float) -> None:
        """Interruptible sleep; returns early (by raising) when stopped."""
        end = time.monotonic() + seconds
        while True:
            self.checkpoint()
            left = end - time.monotonic()
            if left <= 0:
                return
            if self._stop.wait(min(0.1, left)):
                raise StopRequested()
