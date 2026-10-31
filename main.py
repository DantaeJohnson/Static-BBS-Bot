"""Static BBS Bot - entry point.

    python main.py
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _report_crash(exc_text: str) -> None:
    """Write crashes to logs/crash.log and show a message box (pythonw has no console)."""
    try:
        from bbsbot import paths
        path = os.path.join(paths.logs_dir(), "crash.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(exc_text + "\n")
    except Exception:
        path = "(could not write crash.log)"
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, f"Static BBS Bot hit an error and has to close.\n\n{exc_text[-800:]}\n\nDetails: {path}",
            "Static BBS Bot", 0x10)
    except Exception:
        print(exc_text, file=sys.stderr)


def main() -> int:
    try:
        from gui.main_window import run
    except ImportError as e:
        _report_crash(f"Missing a required package: {e}\n\n"
                      "Run 'Start Static BBS Bot.bat' (it installs everything), or:\n"
                      "    pip install -r requirements.txt")
        return 1
    try:
        return run()
    except Exception:
        _report_crash(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
