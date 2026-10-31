"""Main application window."""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import threading

from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
                               QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from bbsbot import APP_NAME, __version__
from bbsbot import logger as log
from bbsbot import paths
from bbsbot.controller import BotController
from bbsbot.device import make_device
from bbsbot.settings import (BACKEND_ADB, BACKEND_WINDOW, MODE_FARM, MODE_PROGRESS, OUT_OF_TICKETS_STOP, OUT_OF_TICKETS_WAIT,
                             Settings)
from bbsbot.templates import GROUPS, SPEC_BY_NAME, SPECS
from bbsbot.vision import Frame, TemplateLibrary, imread
from bbsbot.window import IS_WINDOWS, GameWindow
from gui.hotkeys import Hotkeys
from gui.overlay import Overlay
from gui.template_tools import CaptureDialog, DetectDialog
from gui.widgets import Card, SettingRow, StatTile, StatusDot, Toggle, bgr_to_pixmap, hline
from gui.worker import BotWorker, LogBridge

LEVEL_COLORS = {"DEBUG": "#6b7280", "INFO": "#c9ced8", "SUCCESS": "#4ade80",
                "WARNING": "#fbbf24", "ERROR": "#f87171"}


def page_header(title: str, subtitle: str) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    lay.setSpacing(4)
    t = QLabel(title)
    t.setObjectName("PageTitle")
    s = QLabel(subtitle)
    s.setObjectName("PageSubtitle")
    s.setWordWrap(True)
    lay.addWidget(t)
    lay.addWidget(s)
    return w


def scroll_page(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(content)
    return area


class StatusBridge(QObject):
    """Carries connection-status results from a background thread to the GUI."""
    status = Signal(str, str, object)  # colour, text, (w, h) or None


class ModeCard(QPushButton):
    def __init__(self, title: str, desc: str):
        super().__init__()
        self.setObjectName("ModeCard")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setStyleSheet("font-size: 16px; font-weight: 800; background: transparent;")
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet("color: #8b93a1; font-size: 12px; background: transparent;")
        for lbl in (t, d):
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(lbl)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        log.setup(self.settings.debug_logging)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1220, 820)
        self.setMinimumSize(1000, 680)

        self.controller = BotController()
        self.worker: BotWorker | None = None
        self.run_started = 0.0
        self.paused_total = 0.0
        self.paused_at = 0.0
        self.library = TemplateLibrary(self.settings.match_threshold, self.settings.fast_matching)
        self.game = GameWindow(self.settings.window_title)
        self._bindings: dict[str, list] = defaultdict(list)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.settings.save)

        self.bridge = LogBridge()
        self.bridge.message.connect(self._on_log)
        self.hotkeys = Hotkeys()
        self.hotkeys.pause_pressed.connect(self.toggle_pause)
        self.hotkeys.stop_pressed.connect(self.stop_bot)
        self.overlay = Overlay()

        self._build()
        self._register_hotkeys()
        self._update_orb_controls()

        self.adb_size = None
        self._adb_checking = False
        self._adb_last_check = 0.0
        self.status_bridge = StatusBridge()
        self.status_bridge.status.connect(self._show_game_status)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_game)
        self.poll_timer.start(1500)
        self._poll_game()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_runtime)
        self.clock_timer.start(1000)

        log.info(f"{APP_NAME} {__version__} ready. Log file: {log.log_file}")

    # =============================================================== layout
    def _build(self):
        root = QWidget()
        root.setObjectName("Root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        pages = [self._page_dashboard(), self._page_settings(), self._page_templates(),
                 self._page_logs(), self._page_help()]
        for p in pages:
            self.stack.addWidget(p)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.nav_buttons[0].setChecked(True)

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 22, 16, 18)
        lay.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(6)
        a = QLabel("STATIC")
        a.setObjectName("BrandAccent")
        b = QLabel("BBS BOT")
        b.setObjectName("Brand")
        brand.addWidget(a)
        brand.addWidget(b)
        brand.addStretch(1)
        lay.addLayout(brand)
        v = QLabel(f"Story automation  ·  v{__version__}")
        v.setObjectName("Version")
        lay.addWidget(v)
        lay.addSpacing(22)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for i, label in enumerate(["◆   Dashboard", "⚙   Settings", "▣   Templates", "≡   Logs", "?   Help"]):
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=i: self._go(idx))
            self.nav_group.addButton(btn, i)
            self.nav_buttons.append(btn)
            lay.addWidget(btn)
        lay.addStretch(1)

        box = QFrame()
        box.setObjectName("SidebarStatus")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 12, 14, 12)
        bl.setSpacing(8)
        cap = QLabel("GAME")
        cap.setObjectName("SidebarStatusTitle")
        bl.addWidget(cap)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.game_dot = StatusDot()
        self.game_label = QLabel("Checking...")
        self.game_label.setWordWrap(True)
        row.addWidget(self.game_dot, 0, Qt.AlignVCenter)
        row.addWidget(self.game_label, 1)
        bl.addLayout(row)
        cap2 = QLabel("BOT")
        cap2.setObjectName("SidebarStatusTitle")
        bl.addWidget(cap2)
        self.side_pill = QLabel("IDLE")
        self.side_pill.setObjectName("Pill")
        self.side_pill.setProperty("state", "idle")
        bl.addWidget(self.side_pill, 0, Qt.AlignLeft)
        self.hotkey_hint = QLabel()
        self.hotkey_hint.setObjectName("Muted")
        bl.addWidget(self.hotkey_hint)
        lay.addWidget(box)
        return side

    def _go(self, idx: int):
        self.stack.setCurrentIndex(idx)
        if idx == 2:
            self._refresh_templates()

    # ============================================================ bindings
    def _bind(self, w, key: str):
        self._bindings[key].append(w)
        if isinstance(w, QCheckBox):
            w.toggled.connect(lambda v, k=key: self._apply(k, bool(v)))
        elif isinstance(w, QDoubleSpinBox):
            w.valueChanged.connect(lambda v, k=key: self._apply(k, float(v)))
        elif isinstance(w, QSpinBox):
            w.valueChanged.connect(lambda v, k=key: self._apply(k, int(v)))
        elif isinstance(w, QComboBox):
            w.currentIndexChanged.connect(lambda i, k=key, c=w: self._apply(k, c.itemData(i)))
        elif isinstance(w, QLineEdit):
            w.editingFinished.connect(lambda k=key, e=w: self._apply(k, e.text().strip()))
        self._set_widget(w, getattr(self.settings, key))
        return w

    @staticmethod
    def _set_widget(w, value):
        w.blockSignals(True)
        if isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setValue(value)
        elif isinstance(w, QComboBox):
            i = w.findData(value)
            if i >= 0:
                w.setCurrentIndex(i)
        elif isinstance(w, QLineEdit):
            w.setText(str(value))
        w.blockSignals(False)
        w.update()

    def _apply(self, key: str, value):
        if getattr(self.settings, key) == value:
            return
        setattr(self.settings, key, value)
        for w in self._bindings[key]:
            self._set_widget(w, value)
        self._save_timer.start()
        if key in ("use_orbs", "max_orbs", "orbs_per_refill", "out_of_tickets",
                   "expand_roster", "max_roster_orbs"):
            self._update_orb_controls()
        elif key in ("pause_hotkey", "stop_hotkey"):
            self._register_hotkeys()
        elif key == "debug_logging":
            log.setup(bool(value))
        elif key == "window_title":
            self.game = GameWindow(value)
            self._poll_game()
        elif key in ("backend", "adb_serial", "adb_path"):
            self._adb_last_check = 0.0
            self._update_backend_rows()
            self._poll_game()
        elif key in ("match_threshold", "fast_matching"):
            self.library.threshold = self.settings.match_threshold
            self.library.fast = self.settings.fast_matching
        if self.worker is not None:
            self._notice("Settings changes apply the next time you press Start.", "#60a5fa")

    # -- small control factories ------------------------------------------
    def _toggle(self, key):
        return self._bind(Toggle(), key)

    def _spin(self, key, lo, hi, suffix="", zero_text=None, step=1):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        if suffix:
            s.setSuffix(suffix)
        if zero_text:
            s.setSpecialValueText(zero_text)
        return self._bind(s, key)

    def _dspin(self, key, lo, hi, step, decimals=2, suffix=""):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(decimals)
        if suffix:
            s.setSuffix(suffix)
        return self._bind(s, key)

    def _combo(self, key, items):
        c = QComboBox()
        for text, data in items:
            c.addItem(text, data)
        return self._bind(c, key)

    def _line(self, key):
        e = QLineEdit()
        e.setMinimumWidth(220)
        return self._bind(e, key)

    # ============================================================ dashboard
    def _page_dashboard(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(18)

        top = QHBoxLayout()
        top.addWidget(page_header("Dashboard",
                                  "Open Bleach: Brave Souls on the Story map (in BlueStacks or the PC game), pick a mode and press Start. "
                                  "In BlueStacks mode you can keep using your PC."), 1)
        self.pill = QLabel("IDLE")
        self.pill.setObjectName("Pill")
        self.pill.setProperty("state", "idle")
        top.addWidget(self.pill, 0, Qt.AlignTop)
        lay.addLayout(top)

        # Mode selection
        modes = QHBoxLayout()
        modes.setSpacing(14)
        self.mode_progress = ModeCard("Story Progress",
                                      "Finds the next uncleared stage, battles on AUTO, skips story scenes, "
                                      "then keeps going with Next Quest after every clear.")
        self.mode_farm = ModeCard("Farm Stage",
                                  "Repeats the stage you have open with Retry - for farming drops, EXP or "
                                  "missions. Start from the stage's party screen.")
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.mode_progress)
        self.mode_group.addButton(self.mode_farm)
        (self.mode_farm if self.settings.mode == MODE_FARM else self.mode_progress).setChecked(True)
        self.mode_progress.toggled.connect(
            lambda on: self._apply("mode", MODE_PROGRESS if on else MODE_FARM))
        modes.addWidget(self.mode_progress)
        modes.addWidget(self.mode_farm)
        lay.addLayout(modes)

        # Tickets & run options
        grid = QHBoxLayout()
        grid.setSpacing(14)

        orbs = Card("Soul Tickets & Spirit Orbs")
        orbs.add(SettingRow("Use Spirit Orbs to buy Soul Tickets",
                            "When tickets run out, refill them with orbs (up to your limit).",
                            self._toggle("use_orbs")))
        self.dash_max_orbs = SettingRow("Orb spending limit", "Never spends more than this per run.",
                                        self._spin("max_orbs", 0, 100000, " orbs", step=5))
        orbs.add(self.dash_max_orbs)
        orbs.add(SettingRow("When out of tickets", "",
                            self._combo("out_of_tickets", [("Wait for recharge", OUT_OF_TICKETS_WAIT),
                                                           ("Stop the bot", OUT_OF_TICKETS_STOP)])))
        orbs.add(SettingRow("Expand a full character box",
                            "Spend 5 orbs for 5 more slots when the box is full. Off = stop the run.",
                            self._toggle("expand_roster")))
        self.orb_summary = QLabel()
        self.orb_summary.setObjectName("Muted")
        self.orb_summary.setWordWrap(True)
        orbs.add(self.orb_summary)
        grid.addWidget(orbs, 1)

        run = Card("This run")
        run.add(SettingRow("Stop after", "Number of quest clears (0 = no limit).",
                           self._spin("max_clears", 0, 9999, " clears", zero_text="No limit")))
        run.add(SettingRow("Use Revive Candles", "If off, the bot quits a lost quest instead.",
                           self._toggle("use_revive_candles")))
        run.add(SettingRow("Skip story scenes", "Presses Skip on dialogue and cutscenes.",
                           self._toggle("skip_cutscenes")))
        grid.addWidget(run, 1)
        lay.addLayout(grid)

        # Controls
        ctr = QHBoxLayout()
        ctr.setSpacing(10)
        self.btn_start = QPushButton("▶  Start")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setMinimumWidth(180)
        self.btn_start.clicked.connect(self.start_bot)
        self.btn_pause = QPushButton("❚❚  Pause")
        self.btn_pause.setObjectName("Ghost")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("Danger")
        self.btn_stop.clicked.connect(self.stop_bot)
        ctr.addWidget(self.btn_start)
        ctr.addWidget(self.btn_pause)
        ctr.addWidget(self.btn_stop)
        ctr.addSpacing(10)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        ctr.addWidget(self.notice, 1)
        lay.addLayout(ctr)

        # Stats
        stats = QGridLayout()
        stats.setSpacing(12)
        self.tiles = {
            "cleared": StatTile("Quests cleared"),
            "started": StatTile("Quests started"),
            "orbs_spent": StatTile("Orbs spent"),
            "refills": StatTile("Ticket refills"),
            "runtime": StatTile("Runtime", "0:00:00"),
            "screen": StatTile("Current screen", "-"),
        }
        for i, t in enumerate(self.tiles.values()):
            stats.addWidget(t, 0, i)
        self.tiles["screen"].value.setStyleSheet("font-size: 14px;")
        lay.addLayout(stats)

        # Live log
        logcard = Card("Live activity")
        self.dash_log = QPlainTextEdit()
        self.dash_log.setObjectName("Log")
        self.dash_log.setReadOnly(True)
        self.dash_log.setMaximumBlockCount(400)
        self.dash_log.setMinimumHeight(170)
        logcard.add(self.dash_log)
        lay.addWidget(logcard, 1)

        self._set_running_ui(False)
        return scroll_page(page)

    # ============================================================= settings
    def _page_settings(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(16)
        lay.addWidget(page_header("Settings", "Changes save automatically and apply the next time you press Start."))

        c = Card("Connection",
                 "BlueStacks mode sends taps through ADB inside the emulator, so your mouse and keyboard "
                 "stay free. PC mode drives the Steam game window with real mouse clicks.")
        c.add(SettingRow("Play on", "",
                         self._combo("backend", [("BlueStacks (ADB) - PC stays usable", BACKEND_ADB),
                                                 ("PC game window (uses your mouse)", BACKEND_WINDOW)])))
        r1 = SettingRow("ADB address",
                        "Shown in BlueStacks → Settings → Advanced under Android Debug Bridge "
                        "(usually 127.0.0.1:5555). Leave blank to auto-detect.", self._line("adb_serial"))
        r2 = SettingRow("adb.exe location", "Leave blank: the bot finds BlueStacks' own adb or downloads one.",
                        self._line("adb_path"))
        r3 = SettingRow("Game window title", "PC mode: part of the game window's title.", self._line("window_title"))
        r4 = SettingRow("Bring game to front", "PC mode: focus the game before clicking.",
                        self._toggle("auto_focus_game"))
        for r in (r1, r2, r3, r4):
            c.add(r)
        self.adb_rows, self.window_rows = [r1, r2], [r3, r4]
        test_row = QHBoxLayout()
        b_test = QPushButton("Test connection")
        b_test.setObjectName("Primary")
        b_test.clicked.connect(self._test_connection)
        test_row.addWidget(b_test)
        self.conn_result = QLabel("")
        self.conn_result.setWordWrap(True)
        test_row.addWidget(self.conn_result, 1)
        c.add_layout(test_row)
        lay.addWidget(c)
        self._update_backend_rows()

        c = Card("Soul Tickets & Spirit Orbs",
                 "Spirit Orbs are premium currency. The bot only spends them if you switch this on, "
                 "and never past the limit you set.")
        c.add(SettingRow("Use Spirit Orbs to buy Soul Tickets", "", self._toggle("use_orbs")))
        self.set_max_orbs = SettingRow("Orb spending limit per run", "Hard cap; the bot stops buying once reached.",
                                       self._spin("max_orbs", 0, 100000, " orbs", step=5))
        c.add(self.set_max_orbs)
        self.set_per_refill = SettingRow("Orbs per refill", "What one Soul Ticket refill costs in your game.",
                                         self._spin("orbs_per_refill", 1, 1000, " orbs"))
        c.add(self.set_per_refill)
        c.add(hline())
        c.add(SettingRow("When out of tickets (and not buying)", "",
                         self._combo("out_of_tickets", [("Wait for recharge", OUT_OF_TICKETS_WAIT),
                                                        ("Stop the bot", OUT_OF_TICKETS_STOP)])))
        c.add(SettingRow("Recharge wait", "How long to wait before trying again.",
                         self._spin("recharge_wait_minutes", 1, 600, " min")))
        lay.addWidget(c)

        c = Card("Character box full",
                 "Shown after Start Quest when you've reached the maximum number of characters.")
        c.add(SettingRow("Expand with Spirit Orbs",
                         "On: press Expand Roster and confirm (5 orbs for 5 slots), then keep playing. "
                         "Off: press Close and end the run.",
                         self._toggle("expand_roster")))
        self.set_roster_orbs = SettingRow("Orb limit for character slots",
                                          "Separate from the ticket limit. 25 orbs = up to 25 extra slots.",
                                          self._spin("max_roster_orbs", 0, 100000, " orbs", step=5))
        c.add(self.set_roster_orbs)
        lay.addWidget(c)

        c = Card("Battle")
        c.add(SettingRow("Keep AUTO battle on", "Switches AUTO on if it's off.", self._toggle("ensure_auto")))
        c.add(SettingRow("Skip story scenes", "Presses Skip on dialogue and cutscenes.",
                         self._toggle("skip_cutscenes")))
        c.add(SettingRow("Use Revive Candles",
                         "Revive when the team falls (max once per quest, 5 per run). Only turn this on if you "
                         "have candles - with none left the game may offer to continue with Spirit Orbs.",
                         self._toggle("use_revive_candles")))
        c.add(SettingRow("Stop after losses in a row", "Stops if a quest is too hard for your team.",
                         self._spin("max_failures_per_quest", 1, 20, " losses")))
        lay.addWidget(c)

        c = Card("Limits")
        c.add(SettingRow("Stop after clears", "", self._spin("max_clears", 0, 9999, " clears", zero_text="No limit")))
        c.add(SettingRow("Stop after time", "", self._spin("max_runtime_minutes", 0, 6000, " min",
                                                            zero_text="No limit")))
        lay.addWidget(c)


        c = Card("Farm Stage mode")
        c.add(SettingRow("Set Boost to max", "Raises Boost on the party screen before each run "
                         "(uses more tickets per run).", self._toggle("auto_boost_max")))
        lay.addWidget(c)

        c = Card("Detection & timing", "Only change these if the bot misses or mis-clicks buttons.")
        c.add(SettingRow("Match confidence", "Higher = stricter. 0.85 works for most setups.",
                         self._dspin("match_threshold", 0.6, 0.99, 0.01)))
        c.add(SettingRow("Fast matching", "Coarse-to-fine search (much faster, same accuracy).",
                         self._toggle("fast_matching")))
        c.add(SettingRow("Scan interval", "Pause between screen checks.",
                         self._dspin("scan_interval", 0.1, 5.0, 0.1, 1, " s")))
        c.add(SettingRow("Delay after clicks", "Gives the game time to react.",
                         self._dspin("action_delay", 0.2, 5.0, 0.1, 1, " s")))
        c.add(SettingRow("Tap to advance", "Taps the screen when an unknown screen appears mid-quest.",
                         self._toggle("tap_to_advance")))
        c.add(SettingRow("Stuck timeout", "Stops (and saves a screenshot) if nothing is recognised this long.",
                         self._spin("stuck_timeout_seconds", 30, 3600, " s")))
        c.add(SettingRow("Save debug screenshots", "When stuck or on errors (logs/screenshots).",
                         self._toggle("save_debug_screenshots")))
        c.add(SettingRow("Save unrecognised screens", "One picture of each new unknown screen "
                         "(logs/unknown_screens) - use them on the Templates page.",
                         self._toggle("save_unknown_screens")))
        lay.addWidget(c)

        c = Card("Hotkeys & interface")
        c.add(SettingRow("Pause / resume hotkey", "e.g. f8", self._line("pause_hotkey")))
        c.add(SettingRow("Stop hotkey", "e.g. f9", self._line("stop_hotkey")))
        c.add(SettingRow("On-screen overlay", "Small banner over the game while running.",
                         self._toggle("show_overlay")))
        c.add(SettingRow("Verbose logging", "Log every click and screen change.", self._toggle("debug_logging")))
        lay.addWidget(c)

        reset = QPushButton("Restore defaults")
        reset.clicked.connect(self._restore_defaults)
        lay.addWidget(reset, 0, Qt.AlignLeft)
        lay.addStretch(1)
        return scroll_page(page)

    def _restore_defaults(self):
        if QMessageBox.question(self, "Restore defaults", "Reset every setting to its default?") \
                != QMessageBox.Yes:
            return
        defaults = Settings()
        for key in list(self._bindings):
            self._apply(key, getattr(defaults, key))
        self._apply("mode", defaults.mode)
        self.mode_progress.setChecked(True)

    def _update_orb_controls(self):
        on = self.settings.use_orbs
        for row in (self.dash_max_orbs, self.set_max_orbs, self.set_per_refill):
            row.setEnabled(on)
        s = self.settings
        if on:
            refills = s.max_orbs // max(1, s.orbs_per_refill)
            txt = (f"Up to <b>{s.max_orbs}</b> orbs (<b>{refills}</b> refill{'s' if refills != 1 else ''} "
                   f"at {s.orbs_per_refill} each).")
            if refills == 0:
                txt += " <span style='color:#fbbf24'>Limit is below one refill - nothing will be bought.</span>"
        else:
            action = "wait for tickets to recharge" if s.out_of_tickets == OUT_OF_TICKETS_WAIT else "stop"
            txt = f"Orbs are safe: when tickets run out the bot will <b>{action}</b>."
        self.set_roster_orbs.setEnabled(s.expand_roster)
        if s.expand_roster:
            txt += (f"<br>Full character box: expand, up to <b>{s.max_roster_orbs}</b> orbs "
                    f"(<b>{s.max_roster_orbs // 5}</b>×5 slots).")
        else:
            txt += "<br>Full character box: <b>stop the run</b>."
        self.orb_summary.setText(txt)

    # ============================================================ templates
    def _page_templates(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(14)
        lay.addWidget(page_header(
            "Templates",
            "These are the images the bot looks for. If it misses a button in your game, open that screen "
            "in the game, click Capture and drag a box around the button. Your captures override the defaults."))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        b_cap = QPushButton("Capture from game")
        b_cap.setObjectName("Primary")
        b_cap.clicked.connect(lambda: self._capture(self._selected_template()))
        b_load = QPushButton("Capture from image...")
        b_load.clicked.connect(self._capture_from_file)
        b_test = QPushButton("Test detection")
        b_test.clicked.connect(self._test_detection)
        b_folder = QPushButton("Open my captures")
        b_folder.clicked.connect(lambda: self._open_folder(paths.user_templates_dir()))
        b_reload = QPushButton("Reload")
        b_reload.clicked.connect(self._refresh_templates)
        for b in (b_cap, b_load, b_test, b_folder, b_reload):
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.tpl_table = QTableWidget(0, 5)
        self.tpl_table.setHorizontalHeaderLabels(["", "Template", "Group", "What it is", "Source"])
        self.tpl_table.verticalHeader().setVisible(False)
        self.tpl_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tpl_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tpl_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tpl_table.setShowGrid(False)
        hh = self.tpl_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tpl_table.itemSelectionChanged.connect(self._show_template_preview)
        self.tpl_table.doubleClicked.connect(lambda _: self._capture(self._selected_template()))
        body.addWidget(self.tpl_table, 1)

        side = Card("Preview")
        side.setFixedWidth(300)
        self.tpl_preview = QLabel("Select a template")
        self.tpl_preview.setAlignment(Qt.AlignCenter)
        self.tpl_preview.setMinimumHeight(110)
        self.tpl_preview.setStyleSheet("background: #0a0c10; border-radius: 8px;")
        side.add(self.tpl_preview)
        self.tpl_info = QLabel()
        self.tpl_info.setObjectName("Muted")
        self.tpl_info.setWordWrap(True)
        side.add(self.tpl_info)
        b_re = QPushButton("Re-capture this one")
        b_re.clicked.connect(lambda: self._capture(self._selected_template()))
        side.add(b_re)
        self.b_reset_tpl = QPushButton("Remove my capture")
        self.b_reset_tpl.clicked.connect(self._remove_user_template)
        side.add(self.b_reset_tpl)
        side.body.addStretch(1)
        body.addWidget(side)
        lay.addLayout(body, 1)
        self.tpl_summary = QLabel()
        self.tpl_summary.setObjectName("Muted")
        lay.addWidget(self.tpl_summary)
        return page

    def _refresh_templates(self):
        self.library.reload()
        keep = self._selected_template()
        names = [s.name for s in SPECS] + [n for n in self.library.names() if n not in SPEC_BY_NAME]
        self.tpl_table.setRowCount(len(names))
        missing_required = 0
        for r, name in enumerate(names):
            spec = SPEC_BY_NAME.get(name)
            info = self.library.info(name)
            if info:
                mark, color = "✓", "#4ade80"
            elif spec and spec.required:
                mark, color = "✗", "#f87171"
                missing_required += 1
            else:
                mark, color = "–", "#6b7280"
            cells = [mark, name, spec.group if spec else "Custom",
                     (spec.description if spec else "Your custom template") +
                     ("" if (spec is None or spec.required) else "  (optional)"),
                     ("Your capture" if info.user else "Default") if info else "Missing"]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setForeground(self._qcolor(color))
                    item.setTextAlignment(Qt.AlignCenter)
                if c == 4 and info and info.user:
                    item.setForeground(self._qcolor("#ff9a4d"))
                item.setData(Qt.UserRole, name)
                self.tpl_table.setItem(r, c, item)
            if name == keep:
                self.tpl_table.selectRow(r)
        total = len(self.library.names())
        self.tpl_summary.setText(
            f"{total} templates loaded  ·  "
            + (f"<span style='color:#f87171'>{missing_required} required missing</span>"
               if missing_required else "all required templates present"))

    @staticmethod
    def _qcolor(c):
        return QColor(c)

    def _selected_template(self) -> str:
        items = self.tpl_table.selectedItems() if hasattr(self, "tpl_table") else []
        return items[0].data(Qt.UserRole) if items else ""

    def _show_template_preview(self):
        name = self._selected_template()
        info = self.library.info(name) if name else None
        spec = SPEC_BY_NAME.get(name)
        if info:
            pm = bgr_to_pixmap(info.full)
            if pm.width() > 260:
                pm = pm.scaledToWidth(260, Qt.SmoothTransformation)
            self.tpl_preview.setPixmap(pm)
            h, w = info.full.shape[:2]
            src = "your capture" if info.user else "default"
            self.tpl_info.setText(f"<b>{name}</b> · {w}×{h}px · {src}<br>{spec.description if spec else ''}")
        else:
            self.tpl_preview.setPixmap(QPixmap())
            self.tpl_preview.setText("Not captured yet")
            self.tpl_info.setText(f"<b>{name}</b><br>{spec.description if spec else ''}" if name else "")
        self.b_reset_tpl.setEnabled(bool(info and info.user))

    def _grab_game_frame(self) -> Frame | None:
        frame, err, dev = None, "", None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            st = self.settings.copy()
            st.auto_focus_game = False
            dev = make_device(st)
            frame = dev.grab() or dev.grab()
        except Exception as e:
            err = str(e)
        finally:
            if dev is not None:
                dev.close()
            QApplication.restoreOverrideCursor()
        if frame is None:
            where = ("BlueStacks over ADB (Settings → Connection → Test connection)"
                     if self.settings.backend == BACKEND_ADB
                     else f"a window titled “{self.settings.window_title}”")
            QMessageBox.warning(self, "Game not found",
                                f"Couldn't capture {where}.\n\n{err}\n\nYou can also use "
                                "“Capture from image…” with a screenshot.")
        return frame

    def _capture(self, preset: str = ""):
        frame = self._grab_game_frame()
        if frame is not None:
            self._open_capture(frame, preset)

    def _capture_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a game screenshot", paths.screenshots_dir(),
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        img = imread(path)
        if img is None:
            QMessageBox.warning(self, "Can't open image", path)
            return
        h, w = img.shape[:2]
        if abs(w / h - 16 / 9) > 0.03:
            QMessageBox.information(self, "Heads up",
                                    "This image isn't 16:9. Crop it to just the game area for accurate templates.")
        self._open_capture(Frame(img, (w, h)), self._selected_template())

    def _open_capture(self, frame: Frame, preset: str):
        dlg = CaptureDialog(frame, preset, self)
        if dlg.exec() and dlg.saved_name:
            log.success(f"Saved template '{dlg.saved_name}'.")
            self._refresh_templates()

    def _test_detection(self):
        frame = self._grab_game_frame()
        if frame is None:
            return
        self.library.reload()
        self.library.threshold = self.settings.match_threshold
        DetectDialog(frame, self.library, self).exec()

    def _remove_user_template(self):
        name = self._selected_template()
        info = self.library.info(name)
        if not info or not info.user:
            return
        try:
            os.remove(info.path)
            log.info(f"Removed your capture of '{name}'.")
        except OSError as e:
            QMessageBox.warning(self, "Couldn't remove", str(e))
        self._refresh_templates()
        self._show_template_preview()

    # ================================================================= logs
    def _page_logs(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(14)
        lay.addWidget(page_header("Logs", "Everything the bot did this session. Full logs are saved to disk."))
        bar = QHBoxLayout()
        b1 = QPushButton("Open logs folder")
        b1.clicked.connect(lambda: self._open_folder(paths.logs_dir()))
        b2 = QPushButton("Open screenshots")
        b2.clicked.connect(lambda: self._open_folder(paths.screenshots_dir()))
        b3 = QPushButton("Clear view")
        bar.addWidget(b1)
        bar.addWidget(b2)
        bar.addWidget(b3)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.full_log = QPlainTextEdit()
        self.full_log.setObjectName("Log")
        self.full_log.setReadOnly(True)
        self.full_log.setMaximumBlockCount(5000)
        b3.clicked.connect(self.full_log.clear)
        lay.addWidget(self.full_log, 1)
        return page

    def _on_log(self, level: str, msg: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        color = LEVEL_COLORS.get(level, "#c9ced8")
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"<span style='color:#4b5563'>{stamp}</span>&nbsp;&nbsp;<span style='color:{color}'>{safe}</span>"
        self.full_log.appendHtml(html)
        if level != "DEBUG":
            self.dash_log.appendHtml(html)

    # ================================================================= help
    def _page_help(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(16)
        lay.addWidget(page_header("Help", "Getting set up and getting the most out of the bot."))

        def card(title, html):
            c = Card(title)
            l = QLabel(html)
            l.setWordWrap(True)
            l.setTextFormat(Qt.RichText)
            l.setOpenExternalLinks(True)
            l.setStyleSheet("color: #c9ced8; line-height: 150%;")
            c.add(l)
            lay.addWidget(c)

        card("Quick start", """
            <b>BlueStacks (recommended - your PC stays usable)</b>
            <ol>
            <li>In BlueStacks: <i>Settings → Display</i>: <b>1600×900, landscape</b>.
                <i>Settings → Advanced</i>: turn on <b>Android Debug Bridge</b> and note the address
                under it (usually 127.0.0.1:5555). Save.</li>
            <li>Here: <i>Settings → Connection</i> → Play on <b>BlueStacks (ADB)</b>, enter the address,
                press <b>Test connection</b> (it downloads adb the first time if needed).</li>
            <li>Open the game's Story map in BlueStacks, pick a mode and press <b>Start</b>.
                BlueStacks can sit in the background or be minimised - the bot doesn't use your mouse.</li>
            </ol>
            <b>PC (Steam) game</b>
            <ol>
            <li>Run the PC version of Bleach: Brave Souls <b>windowed at 1600×900</b> (any 16:9 size works;
                1600×900 matches the default templates best). Keep it visible: it can't be minimised or covered.</li>
            <li><b>Story Progress:</b> open <i>Story → MAIN</i> (or SIDE) on the part you're playing, so the
                stage map is showing.<br>
                <b>Farm Stage:</b> open the stage you want to repeat, up to its party / <i>Start Quest</i> screen.</li>
            <li>Choose the mode and your Spirit Orb preference on the Dashboard, then press <b>Start</b>.</li>
            <li>Leave the mouse alone while it runs. <b>F8</b> pauses, <b>F9</b> stops. Moving the mouse into a
                screen corner is an emergency stop.</li>
            </ol>""")
        card("If the bot misses a button", """
            Your game's language, version or graphics can make a button look different from the default image.
            Go to <b>Templates</b>, open that screen in the game and press <b>Test detection</b> to see what the
            bot recognises. Then press <b>Capture from game</b>, drag a tight box around the button and save it
            under the matching name. On the story map the bot relies on <b>story_clear</b> (the CLEAR label),
            <b>story_stars_empty</b> (grey stars of an unplayed battle) and <b>story_node</b> (blue pedestal of a
            cutscene stage). Test detection on the map marks each stage CLEAR / OPEN / LOCKED and shows which
            one it will open next.<br><br>
            When the bot gets stuck it stops and saves a screenshot to <i>logs/screenshots</i>. Use
            <b>Capture from image…</b> to cut the missing button out of it.""")
        card("How it works", """
            Every half-second the bot takes a screenshot, works out which screen it's on (battle, results,
            story scene, quest list, party screen, ticket popup…) and does the single action that screen needs.
            On the story map, a stage with a <b>CLEAR</b> label under its number is done; one without it is new.
            Locked stages are drawn darker, so their number is grey instead of white. The bot opens the left-most
            stage that's new and unlocked (Message → <b>Prepare for Quest</b> → <b>Start Quest</b>). After each
            clear it presses <b>Next Quest</b> on the results screen, which goes straight to the next stage;
            cutscene stages play and are skipped automatically. If there's no Next Quest (after a defeat, or at
            the end of a part) it presses <b>Story</b> to go back to the map and carries on from there.""")
        card("Credits & disclaimer", """
            Default button images and the original approach come from
            <a style='color:#ff9a4d' href='https://github.com/xJohnnyrl/bbs-auto-farmer'>bbs-auto-farmer</a>
            by xJohnnyrl (MIT License). Bleach: Brave Souls belongs to KLab / Shueisha. This is an unofficial tool;
            automating a game may break its terms of service. Use it at your own risk.""")
        lay.addStretch(1)
        return scroll_page(page)

    # ============================================================ run control
    def _notice(self, text: str, color: str = "#8b93a1"):
        self.notice.setText(text)
        self.notice.setStyleSheet(f"color: {color};")

    def start_bot(self):
        if self.worker is not None:
            return
        if self.settings.backend == BACKEND_ADB:
            from bbsbot.adb import find_adb
            if not find_adb(self.settings.adb_path):
                QMessageBox.warning(self, "ADB needed",
                                    "The bot talks to BlueStacks through ADB, which isn't installed yet.\n\n"
                                    "Go to Settings → Connection and press “Test connection” - it can "
                                    "download it for you.")
                return
            size = self.adb_size
        else:
            if not IS_WINDOWS:
                QMessageBox.warning(self, "Windows only", "PC-window mode needs the Windows game.")
                return
            self.game = GameWindow(self.settings.window_title)
            rect = self.game.client_rect()
            if rect is None:
                QMessageBox.warning(self, "Game not found",
                                    f"Couldn't find an open window titled “{self.settings.window_title}”.\n\n"
                                    "Start the game (windowed, not minimised) and try again, or switch to "
                                    "BlueStacks under Settings → Connection.")
                return
            size = (rect.width, rect.height)
        if size and abs(size[0] / max(1, size[1]) - 16 / 9) > 0.03:
            if QMessageBox.question(
                    self, "Screen shape",
                    f"The game screen is {size[0]}×{size[1]}, which isn't 16:9 landscape. Buttons may not "
                    f"be recognised. Use 1600×900 (BlueStacks: Settings → Display) for best results.\n\n"
                    f"Start anyway?") != QMessageBox.Yes:
                return
        self.library.reload()
        missing = [s.name for s in SPECS if s.required and not self.library.has(s.name)]
        if missing:
            log.warning(f"Missing templates: {', '.join(missing)} (see the Templates page).")
        spend = []
        if self.settings.use_orbs and self.settings.max_orbs >= self.settings.orbs_per_refill:
            spend.append(f"up to {self.settings.max_orbs} orbs on Soul Tickets")
        if self.settings.expand_roster and self.settings.max_roster_orbs >= 5:
            spend.append(f"up to {self.settings.max_roster_orbs} orbs on character slots")
        if spend:
            if QMessageBox.question(
                    self, "Spirit Orbs",
                    f"This run may spend {' and '.join(spend)}.\n\nContinue?") != QMessageBox.Yes:
                return

        self.settings.save()
        self.controller.reset()
        self.worker = BotWorker(self.settings, self.controller, self)
        self.worker.stats_changed.connect(self._on_stats)
        self.worker.finished_with.connect(self._on_finished)
        self.run_started = time.monotonic()
        self.paused_total = 0.0
        self.paused_at = 0.0
        for t in ("cleared", "started", "orbs_spent", "refills"):
            self.tiles[t].set("0")
        self.tiles["screen"].set("-")
        self.worker.start()
        self._set_running_ui(True)
        if self.settings.backend == BACKEND_ADB:
            self._notice("Running in BlueStacks - your PC is free to use (don't close BlueStacks).",
                         "#4ade80")
        else:
            self._notice("Running - keep the game window visible and leave the mouse alone.", "#4ade80")
            self.game.focus()

    def toggle_pause(self):
        if self.worker is None:
            return
        paused = self.controller.toggle_pause()
        if paused:
            self.paused_at = time.monotonic()
            log.warning("Paused.")
            self._set_pill("PAUSED", "paused")
            self.btn_pause.setText("▶  Resume")
        else:
            if self.paused_at:
                self.paused_total += time.monotonic() - self.paused_at
                self.paused_at = 0.0
            log.info("Resumed.")
            self._set_pill("RUNNING", "running")
            self.btn_pause.setText("❚❚  Pause")
        self._update_overlay()

    def stop_bot(self):
        if self.worker is None:
            return
        self._notice("Stopping...", "#fbbf24")
        self.controller.stop()

    def _on_stats(self, d: dict):
        for key in ("cleared", "started", "orbs_spent", "refills"):
            self.tiles[key].set(str(d.get(key, 0)))
        self.tiles["screen"].set(d.get("screen", "-"))
        status = d.get("status", "")
        if self.worker is not None and not self.controller.paused:
            if status.startswith("Waiting"):
                self._set_pill("WAITING", "waiting")
                self._notice(status + " - you can leave it running.", "#60a5fa")
            elif status == "Running":
                self._set_pill("RUNNING", "running")

    def _on_finished(self, reason: str):
        if self.worker is not None:
            self.worker.wait(3000)
            self.worker.deleteLater()
        self.worker = None
        self._set_running_ui(False)
        color = "#f87171" if reason.startswith(("Error", "Stuck")) else "#c9ced8"
        self._notice(f"Finished: {reason}", color)
        self.overlay.hide()
        QApplication.alert(self)
        self.raise_()

    def _tick_runtime(self):
        if self.worker is None:
            return
        paused = self.paused_total + (time.monotonic() - self.paused_at if self.paused_at else 0)
        secs = int(time.monotonic() - self.run_started - paused)
        self.tiles["runtime"].set(f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}")

    def _set_running_ui(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_stop.setEnabled(running)
        self.btn_pause.setText("❚❚  Pause")
        self.mode_progress.setEnabled(not running)
        self.mode_farm.setEnabled(not running)
        self._set_pill("RUNNING" if running else "IDLE", "running" if running else "idle")
        self._update_overlay()

    def _set_pill(self, text: str, state: str):
        for pill in (self.pill, getattr(self, "side_pill", None)):
            if pill is None:
                continue
            pill.setText(text)
            pill.setProperty("state", state)
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _update_overlay(self):
        if not hasattr(self, "overlay"):
            return
        if self.worker is None or not self.settings.show_overlay or self.settings.backend == BACKEND_ADB:
            self.overlay.hide()  # BlueStacks mode: you're using the PC, no banner in your way
            return
        keys = []
        if self.hotkeys.available:
            keys.append(f"{self.settings.pause_hotkey.upper()} pause")
            keys.append(f"{self.settings.stop_hotkey.upper()} stop")
        state = "Paused" if self.controller.paused else "Static BBS Bot running"
        self.overlay.show_text(f"●  {state}" + (f"   ·   {'  ·  '.join(keys)}" if keys else ""))

    def _register_hotkeys(self):
        ok = self.hotkeys.register(self.settings.pause_hotkey, self.settings.stop_hotkey)
        if ok:
            self.hotkey_hint.setText(f"{self.settings.pause_hotkey.upper()} pause · "
                                     f"{self.settings.stop_hotkey.upper()} stop")
        else:
            self.hotkey_hint.setText("Hotkeys unavailable")

    def _poll_game(self):
        if self.settings.backend == BACKEND_ADB:
            if self._adb_checking or (self.worker is not None) or time.monotonic() - self._adb_last_check < 5:
                return
            self._adb_checking = True
            self._adb_last_check = time.monotonic()
            threading.Thread(target=self._check_adb, daemon=True).start()
            return
        if not IS_WINDOWS:
            self.game_dot.set_color("#6b7280")
            self.game_label.setText("Windows only")
            return
        rect = self.game.client_rect()
        if rect is None:
            self.game_dot.set_color("#f87171")
            self.game_label.setText("Not found")
        elif abs(rect.width / max(1, rect.height) - 16 / 9) > 0.03:
            self.game_dot.set_color("#fbbf24")
            self.game_label.setText(f"{rect.width}×{rect.height} (not 16:9)")
        else:
            self.game_dot.set_color("#4ade80")
            self.game_label.setText(f"Found · {rect.width}×{rect.height}")

    def _check_adb(self):
        """Background thread: is BlueStacks reachable over ADB? (never blocks the GUI)"""
        from bbsbot.adb import AdbClient, AdbError, find_adb
        try:
            path = find_adb(self.settings.adb_path)
            if not path:
                self.status_bridge.status.emit("#f87171", "ADB not installed (Settings → Connection)", None)
                return
            c = AdbClient(path, self.settings.adb_serial)
            if c.state() != "device" and ":" in c.serial:
                try:
                    c._run(["connect", c.serial], serial=False, timeout=4)
                except AdbError:
                    pass
            if c.state() != "device":
                self.status_bridge.status.emit("#f87171", f"BlueStacks not connected ({c.serial or 'auto'})", None)
                return
            out = c._run(["shell", "wm", "size"], timeout=5)
            size = None
            for line in out.splitlines():
                if "size" in line and "x" in line:
                    w, h = line.split(":")[-1].strip().split("x")
                    size = (int(w), int(h))
            if size and size[1] > size[0]:
                size = (size[1], size[0])  # wm size reports the natural (portrait) orientation
            label = f"BlueStacks · {size[0]}×{size[1]}" if size else "BlueStacks connected"
            ok = size is None or abs(size[0] / size[1] - 16 / 9) < 0.03
            self.status_bridge.status.emit("#4ade80" if ok else "#fbbf24",
                                           label + ("" if ok else " (not 16:9)"), size)
        except Exception as e:
            self.status_bridge.status.emit("#f87171", f"ADB error: {e}"[:60], None)
        finally:
            self._adb_checking = False

    def _show_game_status(self, color: str, text: str, size):
        self.game_dot.set_color(color)
        self.game_label.setText(text)
        if size:
            self.adb_size = size

    def _test_connection(self):
        """Settings → Connection → Test connection (downloads adb if missing)."""
        from bbsbot.adb import AdbError, download_platform_tools, find_adb
        if self.settings.backend != BACKEND_ADB:
            frame = self._grab_game_frame()
            if frame is not None:
                w, h = frame.source_size
                self.conn_result.setText(f"✓ Game window found ({w}×{h}).")
            return
        path = find_adb(self.settings.adb_path)
        if not path:
            if QMessageBox.question(
                    self, "Download ADB?",
                    "ADB (Android Debug Bridge) isn't installed. Download Google's official "
                    "platform-tools (about 10 MB) into the bot's tools folder now?") != QMessageBox.Yes:
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                path = download_platform_tools()
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, "Download failed", f"{e}\n\nYou can also install platform-tools "
                                     "yourself and set its adb.exe path here.")
                return
            QApplication.restoreOverrideCursor()
        frame = self._grab_game_frame()
        if frame is None:
            self.conn_result.setText("✗ Couldn't reach BlueStacks. Check that it's running and that "
                                     "Android Debug Bridge is ON (BlueStacks Settings → Advanced).")
            self.conn_result.setStyleSheet("color: #f87171;")
            return
        w, h = frame.source_size
        self.adb_size = (w, h)
        good = abs(w / h - 16 / 9) < 0.03
        self.conn_result.setText(f"✓ Connected to BlueStacks - screen {w}×{h}."
                                 + ("" if good else " Not 16:9: set BlueStacks to 1600×900 landscape."))
        self.conn_result.setStyleSheet(f"color: {'#4ade80' if good else '#fbbf24'};")
        self._adb_last_check = 0.0
        self._poll_game()

    def _update_backend_rows(self):
        adb = self.settings.backend == BACKEND_ADB
        for row in getattr(self, "adb_rows", []):
            row.setVisible(adb)
        for row in getattr(self, "window_rows", []):
            row.setVisible(not adb)

    @staticmethod
    def _open_folder(path: str):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def closeEvent(self, e):
        if self.worker is not None:
            self.controller.stop()
            self.worker.wait(5000)
        self.hotkeys.unregister()
        self.overlay.close()
        self.settings.save()
        e.accept()


def dark_palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: "#0d0f13", QPalette.WindowText: "#e6e8ec",
        QPalette.Base: "#0f1217", QPalette.AlternateBase: "#151920",
        QPalette.Text: "#e6e8ec", QPalette.Button: "#1d222b", QPalette.ButtonText: "#e6e8ec",
        QPalette.Highlight: "#ff7a1a", QPalette.HighlightedText: "#140a02",
        QPalette.ToolTipBase: "#1d222b", QPalette.ToolTipText: "#e6e8ec",
        QPalette.PlaceholderText: "#6b7280", QPalette.Link: "#ff9a4d",
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor("#555c68"))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#555c68"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#555c68"))
    return p


def run() -> int:
    # Qt 6 makes the process per-monitor DPI aware by itself, so window
    # coordinates, screenshots and clicks all use physical pixels.
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    try:
        with open(paths.theme_path(), "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except OSError:
        pass
    win = MainWindow()
    win.show()
    return app.exec()
