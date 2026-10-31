"""Runs the bot on a background thread so the GUI never freezes."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from bbsbot import logger as log
from bbsbot.controller import BotController
from bbsbot.device import make_device
from bbsbot.settings import Settings
from bbsbot.story.bot import StoryBot
from bbsbot.vision import TemplateLibrary


class LogBridge(QObject):
    """Forwards log lines from any thread to the GUI thread."""
    message = Signal(str, str)

    def __init__(self):
        super().__init__()
        log.add_listener(self._on_log)

    def _on_log(self, level: str, msg: str):
        self.message.emit(level, msg)


class BotWorker(QThread):
    stats_changed = Signal(object)
    finished_with = Signal(str)

    def __init__(self, settings: Settings, controller: BotController, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()  # snapshot: edits mid-run don't race the bot
        self.controller = controller

    def run(self):
        reason = "Stopped"
        try:
            lib = TemplateLibrary(self.settings.match_threshold, self.settings.fast_matching)
            device = make_device(self.settings)
            bot = StoryBot(self.settings, lib, device, self.controller,
                           on_stats=self.stats_changed.emit)
            reason = bot.run()
        except Exception as e:  # never let the thread die silently
            reason = f"Error: {e}"
            log.error(reason)
        self.finished_with.emit(reason)
