"""User settings: a dataclass persisted as JSON.

Unknown keys in the file are ignored and missing keys fall back to defaults, so
old settings files keep working after updates.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields

from bbsbot import paths

MODE_PROGRESS = "progress"   # clear NEW quests in order
MODE_FARM = "farm"           # retry the current stage

BACKEND_ADB = "adb"          # BlueStacks / Android emulator via ADB (PC stays usable)
BACKEND_WINDOW = "window"    # PC (Steam) game window, real mouse clicks

OUT_OF_TICKETS_WAIT = "wait"
OUT_OF_TICKETS_STOP = "stop"


@dataclass
class Settings:
    # --- Run mode -----------------------------------------------------------
    mode: str = MODE_PROGRESS

    # --- Connection ---------------------------------------------------------
    backend: str = BACKEND_ADB
    adb_serial: str = "127.0.0.1:5555"  # shown in BlueStacks Settings > Advanced; blank = auto-detect
    adb_path: str = ""                   # blank = auto (downloaded copy, PATH, or BlueStacks HD-Adb.exe)

    # --- Soul Tickets & Spirit Orbs ----------------------------------------
    use_orbs: bool = False              # spend Spirit Orbs to refill Soul Tickets?
    max_orbs: int = 50                  # hard cap on orbs spent per run
    orbs_per_refill: int = 10           # orbs one refill costs (as shown in game)
    out_of_tickets: str = OUT_OF_TICKETS_WAIT
    # --- Character box full ("maximum number of characters") -----------------
    expand_roster: bool = False         # spend 5 orbs for +5 slots, or stop the run
    max_roster_orbs: int = 25           # separate hard cap for roster expansions per run
    recharge_wait_minutes: int = 15

    # --- Battle -------------------------------------------------------------
    ensure_auto: bool = True
    skip_cutscenes: bool = True
    use_revive_candles: bool = False
    max_failures_per_quest: int = 2
    auto_boost_max: bool = False        # Farm mode only

    # --- Limits (0 = no limit) ---------------------------------------------
    max_clears: int = 0
    max_runtime_minutes: int = 0

    # --- Advanced -----------------------------------------------------------
    window_title: str = "Bleach: Brave Souls"
    match_threshold: float = 0.85
    fast_matching: bool = True
    scan_interval: float = 0.6
    action_delay: float = 0.9
    tap_to_advance: bool = True
    stuck_timeout_seconds: int = 180
    auto_focus_game: bool = True
    save_debug_screenshots: bool = True
    save_unknown_screens: bool = True   # keep a picture of every new unrecognised screen
    pause_hotkey: str = "f8"
    stop_hotkey: str = "f9"
    show_overlay: bool = True
    debug_logging: bool = False

    # ------------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        path = path or paths.settings_path()
        s = cls()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                s.update(data)
            except (OSError, ValueError):
                pass  # corrupt file -> defaults
        return s

    def save(self, path: str | None = None) -> None:
        path = path or paths.settings_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)

    def update(self, data: dict) -> None:
        valid = {f.name: f for f in fields(self)}
        for key, value in data.items():
            if key not in valid:
                continue
            default = getattr(self, key)
            try:
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, int):
                    value = int(value)
                elif isinstance(default, float):
                    value = float(value)
                elif isinstance(default, str):
                    value = str(value)
            except (TypeError, ValueError):
                continue
            setattr(self, key, value)

    def copy(self) -> "Settings":
        s = Settings()
        s.update(asdict(self))
        return s

    def to_dict(self) -> dict:
        return asdict(self)
