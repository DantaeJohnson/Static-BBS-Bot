"""BlueStacks (or any Android emulator/device) over ADB.

Screenshots come from `adb exec-out screencap` and taps/swipes go through
`adb shell input`, so the bot never touches your mouse or keyboard and the PC
stays usable. Same three methods as the desktop device: grab(), click(), drag().

Robustness (from the playbook):
* adb sometimes drops the device: reconnect, and restart the adb server if needed.
* raw screencap is used (fast); PNG is the fallback.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

import cv2
import numpy as np

from bbsbot import logger as log
from bbsbot import paths
from bbsbot.vision import BASE_H, BASE_W, Frame

PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
COMMON_PORTS = [5555, 5565, 5575, 5585, 5595]  # BlueStacks instances 1..5
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: no console flashes


class AdbError(Exception):
    pass


def bundled_adb_path() -> str:
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    return os.path.join(paths.data_root(), "tools", "platform-tools", exe)


def find_adb(configured: str = "") -> str | None:
    """Configured path -> our downloaded copy -> PATH -> BlueStacks' own HD-Adb.exe."""
    candidates = [configured, bundled_adb_path(), shutil.which("adb") or ""]
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for folder in ("BlueStacks_nxt", "BlueStacks_msi5", "BlueStacks"):
                candidates.append(os.path.join(base, folder, "HD-Adb.exe"))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def download_platform_tools(progress=None) -> str:
    """Download Google's official platform-tools (adb) into the bot's tools folder."""
    dest = os.path.join(paths.data_root(), "tools")
    os.makedirs(dest, exist_ok=True)
    log.info("Downloading Android platform-tools (adb) from Google...")
    with urllib.request.urlopen(PLATFORM_TOOLS_URL, timeout=60) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(dest)
    path = bundled_adb_path()
    if not os.path.isfile(path):
        raise AdbError("Download finished but adb wasn't found in it.")
    log.success(f"adb installed: {path}")
    return path


class AdbClient:
    def __init__(self, adb_path: str, serial: str):
        self.adb = adb_path
        self.serial = serial.strip()
        self._lock = threading.Lock()

    # -- low level -----------------------------------------------------------
    def _run(self, args, timeout=10.0, binary=False, serial=True):
        cmd = [self.adb] + (["-s", self.serial] if serial and self.serial else []) + list(args)
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise AdbError(f"adb timed out: {' '.join(args)}")
        except OSError as e:
            raise AdbError(f"Can't run adb ({e}).")
        if p.returncode != 0:
            err = (p.stderr or p.stdout).decode(errors="replace").strip()
            raise AdbError(err or f"adb failed: {' '.join(args)}")
        return p.stdout if binary else p.stdout.decode(errors="replace")

    def devices(self) -> list[tuple[str, str]]:
        out = self._run(["devices"], serial=False)
        rows = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                rows.append((parts[0], parts[1]))
        return rows

    def state(self) -> str:
        for s, st in self.devices():
            if s == self.serial:
                return st
        return "missing"

    # -- connection ----------------------------------------------------------
    def connect(self) -> bool:
        """Make sure `serial` is online. Tries `adb connect`, then an adb server restart.
        If no serial is configured, picks the first emulator found (auto-detect)."""
        with self._lock:
            for attempt in range(2):
                try:
                    if not self.serial:
                        self.serial = self._autodetect()
                        if not self.serial:
                            raise AdbError("No emulator found.")
                    if self.state() == "device":
                        return True
                    if ":" in self.serial:
                        self._run(["connect", self.serial], serial=False, timeout=8)
                        time.sleep(0.5)
                        if self.state() == "device":
                            return True
                except AdbError:
                    pass
                if attempt == 0:
                    log.warning("ADB lost the emulator - restarting the adb server...")
                    try:
                        self._run(["kill-server"], serial=False, timeout=8)
                        self._run(["start-server"], serial=False, timeout=15)
                    except AdbError:
                        pass
            return False

    def _autodetect(self) -> str:
        for s, st in self.devices():
            if st == "device":
                return s
        for port in COMMON_PORTS:
            addr = f"127.0.0.1:{port}"
            try:
                self._run(["connect", addr], serial=False, timeout=4)
            except AdbError:
                continue
            for s, st in self.devices():
                if s == addr and st == "device":
                    return addr
        return ""

    # -- I/O -----------------------------------------------------------------
    def screencap(self) -> np.ndarray:
        raw = self._run(["exec-out", "screencap"], binary=True, timeout=10)
        img = _decode_raw(raw)
        if img is None:  # some images/devices only support PNG
            png = self._run(["exec-out", "screencap", "-p"], binary=True, timeout=10)
            img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise AdbError("Couldn't read the emulator screen.")
        return img

    def tap(self, x: int, y: int) -> None:
        self._run(["shell", "input", "tap", str(x), str(y)], timeout=8)

    def swipe(self, x1, y1, x2, y2, ms: int) -> None:
        self._run(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms)], timeout=10)


def _decode_raw(raw: bytes):
    """screencap raw format: u32 width, u32 height, u32 format [, u32 colorspace] + RGBA."""
    if len(raw) < 16:
        return None
    w = int.from_bytes(raw[0:4], "little")
    h = int.from_bytes(raw[4:8], "little")
    if not (100 < w < 10000 and 100 < h < 10000):
        return None
    for header in (16, 12):
        if len(raw) - header == w * h * 4:
            rgba = np.frombuffer(raw, np.uint8, count=w * h * 4, offset=header).reshape(h, w, 4)
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    return None


class AdbDevice:
    """Bot device backed by ADB. Coordinates in = base (1600x900) coords."""

    def __init__(self, adb_path: str, serial: str):
        self.client = AdbClient(adb_path, serial)
        self.size: tuple[int, int] | None = None  # emulator screen (w, h)
        self._fail_since: float | None = None

    @property
    def serial(self) -> str:
        return self.client.serial

    def grab(self) -> Frame | None:
        try:
            img = self.client.screencap()
            self._fail_since = None
        except AdbError as e:
            if self._fail_since is None:
                self._fail_since = time.monotonic()
                log.warning(f"Emulator screenshot failed ({e}) - reconnecting...")
            self.client.connect()
            return None
        h, w = img.shape[:2]
        if h > w:
            log.warning("The emulator is in portrait. Set BlueStacks to landscape (1600x900).")
        self.size = (w, h)
        return Frame(img, (w, h))

    def _to_device(self, bx: float, by: float) -> tuple[int, int]:
        w, h = self.size or (BASE_W, BASE_H)
        return int(round(bx * w / BASE_W)), int(round(by * h / BASE_H))

    def click(self, bx: float, by: float, double: bool = False) -> None:
        x, y = self._to_device(bx, by)
        self._retry(lambda: self.client.tap(x, y))
        if double:
            time.sleep(0.3)
            self._retry(lambda: self.client.tap(x, y))

    def drag(self, bx1, by1, bx2, by2, duration: float = 0.6) -> None:
        x1, y1 = self._to_device(bx1, by1)
        x2, y2 = self._to_device(bx2, by2)
        self._retry(lambda: self.client.swipe(x1, y1, x2, y2, int(duration * 1000) + 200))

    def _retry(self, fn) -> None:
        try:
            fn()
        except AdbError:
            if self.client.connect():
                fn()
            else:
                raise

    def close(self) -> None:
        pass
