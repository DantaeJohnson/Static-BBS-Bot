"""Static BBS Bot - story-mode automation for Bleach: Brave Souls."""
import os as _os


def _read_version() -> str:
    try:
        here = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        with open(_os.path.join(here, "version.txt"), encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


__version__ = _read_version()   # single source of truth: version.txt (the updater compares it)
APP_NAME = "Static BBS Bot"
