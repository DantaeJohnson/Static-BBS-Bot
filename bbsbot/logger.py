"""Logging to a timestamped file, plus listeners (the GUI log panel)."""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Callable

from bbsbot import paths

_listeners: list[Callable[[str, str], None]] = []
_lock = threading.Lock()
_logger = logging.getLogger("bbsbot")
_configured = False
_gui_debug = False
log_file = ""


def setup(debug: bool = False) -> str:
    global _configured, log_file
    global _gui_debug
    _gui_debug = debug
    if _configured:
        return log_file
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(paths.logs_dir(), f"run_{stamp}.log")
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.DEBUG)  # the file always gets every click, for troubleshooting
    _logger.propagate = False
    _configured = True
    _prune_old_logs()
    return log_file


def _prune_old_logs(keep: int = 30) -> None:
    try:
        d = paths.logs_dir()
        logs = sorted(f for f in os.listdir(d) if f.startswith("run_") and f.endswith(".log"))
        for f in logs[:-keep]:
            os.remove(os.path.join(d, f))
    except OSError:
        pass


def add_listener(fn: Callable[[str, str], None]) -> None:
    with _lock:
        _listeners.append(fn)


def remove_listener(fn: Callable[[str, str], None]) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def _emit(level: str, msg: str) -> None:
    getattr(_logger, level.lower() if level != "SUCCESS" else "info")(msg)
    if level == "DEBUG" and not _gui_debug:  # GUI shows clicks only with Verbose logging
        return
    with _lock:
        listeners = list(_listeners)
    for fn in listeners:
        try:
            fn(level, msg)
        except Exception:
            pass


def debug(msg: str) -> None:
    _emit("DEBUG", msg)


def info(msg: str) -> None:
    _emit("INFO", msg)


def success(msg: str) -> None:
    _emit("SUCCESS", msg)


def warning(msg: str) -> None:
    _emit("WARNING", msg)


def error(msg: str) -> None:
    _emit("ERROR", msg)
