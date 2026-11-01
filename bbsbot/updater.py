"""Automatic updates from the GitHub repository.

On start-up the app reads `version.txt` from the repo. If it's newer than the
local one, it downloads the repo ZIP and replaces the bot's own files, keeping
the user's settings, logs, captured buttons and installed packages. If
requirements.txt changed it installs the new packages, then restarts.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from bbsbot import logger as log
from bbsbot import paths

REPO = "DantaeJohnson/Static-BBS-Bot"
BRANCH = "main"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/version.txt"
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"

# Never touched by an update: the user's own stuff.
KEEP_TOP = {"config", "logs", ".venv", "tools", "user_templates", ".git", "tests"}
# Folders fully owned by the bot: files that disappeared from the repo are removed here.
MANAGED_DIRS = ("bbsbot", "gui", "assets")
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class UpdateError(Exception):
    pass


def parse(v: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", v or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def local_version(root: str | None = None) -> str:
    root = root or paths.app_root()
    try:
        with open(os.path.join(root, "version.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


_zip_cache: bytes | None = None   # set when the version had to be read from the ZIP


def remote_version(timeout: float = 8.0) -> str:
    """Newest version on GitHub. Reads version.txt directly; if that address is blocked
    on this network, falls back to reading it from the repository ZIP."""
    global _zip_cache
    try:
        req = urllib.request.Request(VERSION_URL, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace").strip()
    except Exception:
        data = _fetch_zip(60.0)
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        prefix = names[0].split("/")[0] + "/"
        v = z.read(prefix + "version.txt").decode("utf-8", "replace").strip()
        _zip_cache = data
        return v


def can_update(root: str | None = None) -> bool:
    """Only plain downloaded copies update themselves (not packaged .exe builds or git checkouts)."""
    root = root or paths.app_root()
    return (not getattr(sys, "frozen", False)
            and os.path.isfile(os.path.join(root, "version.txt"))
            and not os.path.isdir(os.path.join(root, ".git")))


def check(root: str | None = None) -> tuple[str, str, bool]:
    local = local_version(root)
    remote = remote_version()
    return local, remote, parse(remote) > parse(local)


def _fetch_zip(timeout: float) -> bytes:
    with urllib.request.urlopen(ZIP_URL, timeout=timeout) as r:
        return r.read()


def download(timeout: float = 60.0) -> bytes:
    global _zip_cache
    if _zip_cache is not None:          # already downloaded while checking the version
        data, _zip_cache = _zip_cache, None
        return data
    return _fetch_zip(timeout)


def install(data: bytes, root: str | None = None, run_pip: bool = True) -> list[str]:
    """Apply an update ZIP to `root`. Returns the list of files written."""
    root = os.path.abspath(root or paths.app_root())
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UpdateError("The downloaded update is damaged.")
    names = [n for n in z.namelist() if not n.endswith("/")]
    if not names:
        raise UpdateError("The update is empty.")
    prefix = names[0].split("/")[0] + "/"            # GitHub wraps everything in <repo>-<branch>/
    files: dict[str, str] = {}
    for n in names:
        if not n.startswith(prefix):
            continue
        rel = n[len(prefix):]
        parts = rel.split("/")
        if not rel or parts[0] in KEEP_TOP or ".." in parts or rel.startswith("/"):
            continue
        files[rel] = n
    for must in ("main.py", "version.txt", "bbsbot/__init__.py"):
        if must not in files:
            raise UpdateError(f"The update is missing {must} - not installing it.")

    old_req = _read(os.path.join(root, "requirements.txt"))
    written = []
    for rel, member in files.items():
        dest = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".updating"
        with open(tmp, "wb") as f:
            f.write(z.read(member))
        os.replace(tmp, dest)
        written.append(rel)

    # Remove bot files that no longer exist in the repo (e.g. a retired button image).
    for d in MANAGED_DIRS:
        base = os.path.join(root, d)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
                if rel not in files:
                    try:
                        os.remove(os.path.join(dirpath, fn))
                    except OSError:
                        pass

    if run_pip and _read(os.path.join(root, "requirements.txt")) != old_req:
        _pip_install(root)
    return written


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _pip_install(root: str) -> None:
    exe_dir = os.path.dirname(sys.executable)
    py = os.path.join(exe_dir, "python.exe" if sys.platform == "win32" else "python")
    if not os.path.isfile(py):
        py = sys.executable
    log.info("The update needs new packages - installing them...")
    p = subprocess.run([py, "-m", "pip", "install", "-r", os.path.join(root, "requirements.txt")],
                       capture_output=True, creationflags=_NO_WINDOW, timeout=1800)
    if p.returncode != 0:
        raise UpdateError("Installing the update's packages failed. Check your internet and "
                          "re-open the bot.")


def restart(root: str | None = None) -> None:
    """Start a fresh copy of the bot (the caller then closes this one)."""
    root = root or paths.app_root()
    flags = 0x00000008 if sys.platform == "win32" else 0  # DETACHED_PROCESS
    subprocess.Popen([sys.executable, os.path.join(root, "main.py")], cwd=root,
                     creationflags=flags, close_fds=True)
