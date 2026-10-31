"""Where things live on disk.

Running from source, everything (config, logs, captured templates) stays inside
the project folder so it's easy to find. When frozen with PyInstaller, writable
data goes to %APPDATA%/Static BBS Bot instead.
"""
import os
import sys

from bbsbot import APP_NAME


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> str:
    """Read-only resources (bundled templates, theme)."""
    if _is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root() -> str:
    """Writable data (settings, logs, user-captured templates)."""
    if _is_frozen():
        base = os.getenv("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, APP_NAME)
    return app_root()


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def bundled_templates_dir() -> str:
    return os.path.join(app_root(), "assets", "templates")


def user_templates_dir() -> str:
    return _ensure(os.path.join(data_root(), "user_templates"))


def config_dir() -> str:
    return _ensure(os.path.join(data_root(), "config"))


def settings_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def logs_dir() -> str:
    return _ensure(os.path.join(data_root(), "logs"))


def screenshots_dir() -> str:
    return _ensure(os.path.join(logs_dir(), "screenshots"))


def theme_path() -> str:
    return os.path.join(app_root(), "gui", "theme.qss")
