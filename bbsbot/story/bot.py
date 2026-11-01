"""Story-mode bot: a screen-recognition loop.

Instead of a fixed script, every tick the bot takes a screenshot, works out
which screen it is looking at (by checking rules in priority order) and does
the one action that screen needs. Anything unexpected - a cutscene, a reward
popup, a chapter-unlock message - is handled the same way, so the bot can
recover from wherever it happens to be.

Modes
-----
progress : clear quests marked NEW in order (story progression)
farm     : press Retry after every clear (repeat one stage)
"""
from __future__ import annotations

import csv
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable

from bbsbot import logger as log
from bbsbot import paths
from bbsbot.controller import BotController, StopRequested
from bbsbot.settings import MODE_FARM, MODE_PROGRESS, OUT_OF_TICKETS_STOP, Settings
from bbsbot.story import stage_map
from bbsbot.templates import AREA_RETURN, NEW_BADGES, START_BUTTONS
from bbsbot.vision import BASE_H, BASE_W, Frame, Match, TemplateLibrary, imwrite


class BotFinished(Exception):
    """Normal end of a run (limit reached, nothing left to do...)."""


@dataclass
class Stats:
    started: int = 0
    cleared: int = 0
    failed: int = 0
    orbs_spent: int = 0
    refills: int = 0
    revives: int = 0
    start_time: float = field(default_factory=time.time)
    screen: str = "-"
    status: str = "Starting"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["runtime"] = time.time() - self.start_time
        return d


class StoryBot:
    TAP_POINT = (BASE_W // 2, int(BASE_H * 0.45))  # neutral tap to advance dialogue

    def __init__(self, settings: Settings, library: TemplateLibrary, device,
                 controller: BotController | None = None,
                 on_stats: Callable[[dict], None] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.s = settings
        self.lib = library
        self.dev = device
        self.ctl = controller or BotController()
        self.on_stats = on_stats
        self.clock = clock
        self.stats = Stats()

        now = self.clock()
        self.run_started = now
        self.last_progress = now          # last time we recognised a screen
        self.unknown_since: float | None = None
        self.last_tap = 0.0
        self.window_missing_since: float | None = None

        self.quest_active = False         # a quest was started and not yet resolved
        self.clear_counted = False
        self.post_battle_until = 0.0      # results-flow window (area buttons valid)
        self.in_battle = False
        self.battle_started = 0.0
        self.failures_in_row = 0
        self.boost_done = False
        self.revived_this_quest = False
        self.last_start_click = -1e9
        self.last_stage_click = -1e9
        self.quest_started_at: float | None = None
        self.unknown_saved: list = []          # thumbnails of unknown screens already saved
        self.last_thumb = None                 # frozen-screen detection (paused emulator)
        self.same_since = 0.0
        self.frozen_warned = False
        self.ticket_orbs = 0             # orbs spent on Soul Tickets (own cap)
        self.roster_orbs = 0             # orbs spent on character slots (own cap)
        self.slot_buy_at = -1e9
        self.map_swipes = 0
        self.part_switches = 0                 # parts entered via Select Part this run
        self.part_pick: dict | None = None     # progress of picking the next part
        self.part_from_map = False             # the bot itself opened Select Part (part finished)
        self.part_rewind: dict | None = None   # progress of going back to Part 1
        self.fresh_part = False                # a part was just opened, no stage clicked yet
        self.left_scrolls = 0
        self.nav_at = -1e9                     # last home -> Solo -> Story navigation tap
        self.back_presses = 0                  # Back presses while finding the way to story
        self.no_next_logged = False

        self.no_new_frames = 0
        self.map_empty_since = 0.0
        self.scrolls = 0
        self.ignored_spots: dict[tuple[int, int], float] = {}
        self.last_action: tuple | None = None
        self.repeat_count = 0

    # ===================================================================== run
    def run(self) -> str:
        mode = "Story Progress" if self.s.mode == MODE_PROGRESS else "Farm Stage"
        log.info(f"Starting {mode} mode.")
        if self.s.use_orbs:
            log.info(f"Spirit Orbs: ON (cap {self.s.max_orbs} orbs, {self.s.orbs_per_refill} per refill).")
        else:
            policy = "wait for recharge" if self.s.out_of_tickets != OUT_OF_TICKETS_STOP else "stop"
            log.info(f"Spirit Orbs: OFF - when out of Soul Tickets the bot will {policy}.")
        self._set_status("Running")
        reason = "Stopped"
        try:
            while True:
                self.ctl.checkpoint()
                self._tick()
                self.ctl.wait(self.s.scan_interval)
        except StopRequested:
            reason = "Stopped by user"
            log.warning(reason)
        except BotFinished as e:
            reason = str(e)
            log.success(reason)
            if not reason.startswith(("Reached the", "Out of Soul", "Story complete")):
                self._save_screenshot("stopped")  # what the bot saw when it decided to stop
        except Exception as e:  # pragma: no cover - surfaced in the GUI
            if type(e).__name__ == "FailSafeException":
                reason = "Emergency stop (mouse moved to a screen corner)"
                log.warning(reason)
            else:
                reason = f"Error: {e}"
                log.error(reason)
                self._save_screenshot("error")
        finally:
            self._set_status("Finished")
            close = getattr(self.dev, "close", None)
            if close:
                close()
        s = self.stats
        log.info(f"Run summary - cleared {s.cleared}, started {s.started}, failed {s.failed}, "
                 f"orbs spent {s.orbs_spent}.")
        return reason

    # ==================================================================== tick
    def _tick(self) -> None:
        now = self.clock()
        frame = self.dev.grab()
        if frame is None:
            if self.window_missing_since is None:
                self.window_missing_since = now
                log.warning("Can't see the game (window closed/minimised, or emulator not "
                            "answering over ADB) - waiting...")
            elif now - self.window_missing_since > 60:
                raise BotFinished("Lost the game screen for over a minute. Check that the game / "
                                  "BlueStacks is running and press Start again.")
            return
        if self.window_missing_since is not None:
            log.info("Game window found.")
            self.window_missing_since = None
        self._frame = frame

        # Priority order matters: popups first, then battle, results, story
        # scenes, quest-flow buttons, and finally quest-list navigation.
        for rule in (self._r_return_title, self._r_story_complete, self._r_roster_full, self._r_slots_confirm, self._r_defeat, self._r_ticket_popup,
                     self._r_battle, self._r_results_banner, self._r_skip, self._r_ok, self._r_results_buttons, self._r_close,
                     self._r_area_return, self._r_prepare, self._r_message_popup, self._r_start,
                     self._r_cancel,
                     self._r_select_part, self._r_story_map, self._r_title, self._r_solo_menu,
                     self._r_home, self._r_new_quest,
                     self._r_list_without_new):
            if rule(frame):
                self.last_progress = self.clock()
                self.unknown_since = None
                self._push_stats()
                return
        self._watchdog()
        self._push_stats()

    # ================================================================= helpers
    def find(self, name: str, threshold: float | None = None, frame: Frame | None = None) -> Match | None:
        return self.lib.find(frame or self._frame, name, threshold)

    def find_any(self, names, threshold: float | None = None) -> Match | None:
        return self.lib.find_any(self._frame, names, threshold)

    def click(self, m: Match | tuple, label: str, double: bool = False) -> None:
        x, y = m.center if isinstance(m, Match) else m
        key = (label, x // 20, y // 20)
        if key == self.last_action:
            self.repeat_count += 1
        else:
            self.last_action, self.repeat_count = key, 1
        log.debug(f"Click {label} at ({x}, {y})")
        self._csv("taps.csv", ["time", "screen", "action", "x", "y"],
                  [datetime.now().isoformat(timespec="seconds"), self.stats.screen, label, x, y])
        self.dev.click(x, y, double=double)
        self.ctl.wait(self.s.action_delay)

    def click_verified(self, name: str, label: str, near: Match | None = None) -> bool:
        """For anything that spends orbs: take a fresh screenshot, re-find the button
        with a strict threshold (and at the same spot), and only then tap it."""
        if self.refresh() is None:
            return False
        m = self.find(name, threshold=max(self.s.match_threshold, 0.9))
        if m is None or (near is not None and (abs(m.x - near.x) > 12 or abs(m.y - near.y) > 12)):
            log.warning(f"'{label}' wasn't where expected on a fresh look - not pressing it.")
            return False
        self.click(m, label)
        return True

    def _csv(self, filename: str, header: list, row: list) -> None:
        try:
            path = os.path.join(paths.logs_dir(), filename)
            new = not os.path.exists(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(header)
                w.writerow(row)
        except OSError:
            pass

    def _log_run(self, result: str) -> None:
        if self.quest_started_at is None:
            return
        secs = int(time.time() - self.quest_started_at)
        self._csv("runs.csv", ["finished_at", "mode", "result", "seconds", "run_number"],
                  [datetime.now().isoformat(timespec="seconds"), self.s.mode, result, secs,
                   self.stats.started])
        self.quest_started_at = None

    def refresh(self) -> Frame | None:
        f = self.dev.grab()
        if f is not None:
            self._frame = f
        return f

    def wait_for(self, names, timeout: float = 4.0, threshold: float | None = None) -> Match | None:
        """Poll fresh screenshots until one of `names` appears."""
        if isinstance(names, str):
            names = [names]
        end = self.clock() + timeout
        while True:
            if self.refresh() is not None:
                m = self.find_any(names, threshold)
                if m:
                    return m
            if self.clock() >= end:
                return None
            self.ctl.wait(0.3)

    def _screen(self, name: str) -> None:
        if self.stats.screen != name:
            log.debug(f"Screen: {name}")
        self.stats.screen = name

    def _set_status(self, status: str) -> None:
        self.stats.status = status
        self._push_stats()

    def _push_stats(self) -> None:
        if self.on_stats:
            self.on_stats(self.stats.to_dict())

    def _save_screenshot(self, tag: str) -> str | None:
        frame = getattr(self, "_frame", None)
        if not self.s.save_debug_screenshots or frame is None:
            return None
        path = os.path.join(paths.screenshots_dir(), f"{tag}_{datetime.now():%Y%m%d_%H%M%S}.png")
        imwrite(path, frame.image)
        log.info(f"Saved screenshot: {path}")
        return path

    def _limits_reached(self) -> str | None:
        if self.s.max_clears > 0 and self.stats.cleared >= self.s.max_clears:
            return f"Reached the clear limit ({self.s.max_clears})."
        if self.s.max_runtime_minutes > 0 and \
                self.clock() - self.run_started >= self.s.max_runtime_minutes * 60:
            return f"Reached the time limit ({self.s.max_runtime_minutes} min)."
        return None

    def _check_limits_before_start(self) -> None:
        reason = self._limits_reached()
        if reason:
            raise BotFinished(reason)

    def _quest_started(self) -> None:
        self.stats.started += 1
        self.quest_active = True
        self.clear_counted = False
        self.boost_done = False
        self.revived_this_quest = False
        self.no_new_frames = 0
        self.scrolls = 0
        self.quest_started_at = time.time()
        log.info(f"Quest started (#{self.stats.started}).")

    def _count_clear(self) -> None:
        if self.quest_active and not self.clear_counted:
            self.stats.cleared += 1
            self.clear_counted = True
            self.failures_in_row = 0
            limit = f"/{self.s.max_clears}" if self.s.max_clears else ""
            log.success(f"Quest cleared! ({self.stats.cleared}{limit})")
            self._log_run("clear")
        self.quest_active = False
        self.in_battle = False
        self.post_battle_until = self.clock() + 120

    # =================================================================== rules
    # Each rule returns True if it recognised the screen (and acted on it).

    def _undo_start(self) -> None:
        """A popup blocked the quest from starting: don't count it as started."""
        if self.quest_active and not self.clear_counted and not self.in_battle and self.stats.started > 0:
            self.stats.started -= 1
        self.quest_active = False
        self.last_start_click = -1e9

    def _r_story_complete(self, f: Frame) -> bool:
        """'Story Complete - Congratulations on completing the story!' = no story left."""
        m = self.find("story_complete") or self.find("story_complete_title")
        if not m:
            return False
        self._screen("Story complete")
        if self.quest_active and not self.clear_counted:
            self._count_clear()
        close = self.find("close")
        if close:
            self.click(close, "close (story complete)")
        raise BotFinished("Story complete - there's no more story to play. Congratulations!")

    def _r_roster_full(self, f: Frame) -> bool:
        """'You have reached the maximum number of characters' after Start Quest."""
        if not self.find("roster_full"):
            return False
        self._screen("Character box full")
        self._undo_start()
        cost = 5
        if self.s.expand_roster:
            limit = self.s.roster_orb_limit
            if limit <= 0 or self.roster_orbs + cost <= limit:
                expand = self.find("expand_roster")
                if expand:
                    log.info(f"Character box is full - spending {cost} Spirit Orbs for 5 more slots.")
                    if self.click_verified("expand_roster", "expand roster", near=expand) and \
                            self.wait_for("slots_confirm", timeout=5):
                        ok = self.find("ok")
                        self.slot_buy_at = self.clock()
                        # double check: still the '5 Character Slots' screen, OK in the same place
                        if ok and self.find("slots_confirm") and \
                                self.click_verified("ok", "ok (buy character slots)", near=ok):
                            self.roster_orbs += cost
                            self.stats.orbs_spent += cost
                            cap = f"/{limit}" if limit > 0 else ""
                            log.success(f"Character box expanded. Orbs spent on slots this run: "
                                        f"{self.roster_orbs}{cap}.")
                            return True
                    log.error("The slot purchase screen didn't appear as expected - not buying.")
                    cancel = self.find("cancel")
                    if cancel:
                        self.click(cancel, "cancel (slot purchase)")
                    self.refresh()
            else:
                log.warning(f"Spirit Orb cap for character slots reached "
                            f"({self.roster_orbs}/{limit}).")
        close = self.find("roster_close") or self.find("close_red") or self.find("close")
        if close and self.find("roster_full"):
            self.click(close, "close (character box full)")
        raise BotFinished("Character box is full. Sell or ascend some characters (or turn on "
                          "'Expand character box' in Settings) and press Start again.")

    def _r_slots_confirm(self, f: Frame) -> bool:
        """Safety net: never accept a character-slot purchase the bot didn't ask for."""
        if not self.find("slots_confirm"):
            return False
        self._screen("Confirm purchase (slots)")
        if self.clock() - self.slot_buy_at < 5:
            return True  # our own purchase is going through
        cancel = self.find("cancel")
        if cancel:
            log.warning("Unexpected character-slot purchase screen - cancelling.")
            self.click(cancel, "cancel (slot purchase)")
        return True

    def _r_defeat(self, f: Frame) -> bool:
        if not self.find("continue_check"):
            return False
        self._screen("Defeated - Continue?")
        # Max one revive per quest / 5 per run: once candles run out the same
        # popup can offer to continue with Spirit Orbs, which we must never accept.
        if self.s.use_revive_candles and not self.revived_this_quest and self.stats.revives < 5:
            ok = self.find("ok")
            if ok:
                self.revived_this_quest = True
                log.warning("Team defeated - using a Revive Candle.")
                self.stats.revives += 1
                self.click(ok, "ok (revive)")
                confirm = self.wait_for("ok", timeout=3)
                if confirm:
                    self.click(confirm, "ok (confirm revive)")
                return True
        quit_btn = self.find("quit")
        if quit_btn:
            self.stats.failed += 1
            self._log_run("defeat")
            self.failures_in_row += 1
            self.quest_active = False
            self.in_battle = False
            self.post_battle_until = self.clock() + 120
            log.warning(f"Team defeated - quitting quest ({self.failures_in_row} failure(s) in a row).")
            self.click(quit_btn, "quit")
            if self.failures_in_row >= max(1, self.s.max_failures_per_quest):
                raise BotFinished(
                    f"Lost {self.failures_in_row} times in a row - this quest needs a stronger team. Stopping.")
            return True
        return True  # popup visible but buttons not matched yet; wait

    def _r_ticket_popup(self, f: Frame) -> bool:
        purchase = self.find("purchase")
        if not purchase or self.find("pause"):
            return False
        self._screen("Out of Soul Tickets")
        self.quest_active = False  # the start didn't go through
        if self.stats.started > 0 and not self.clear_counted:
            self.stats.started -= 1
        log.warning("Not enough Soul Tickets.")

        if self.s.use_orbs:
            if self.ticket_orbs + self.s.orbs_per_refill <= self.s.max_orbs:
                if self._buy_tickets(purchase):
                    return True
                log.error("Couldn't complete the Soul Ticket purchase - falling back.")
            else:
                log.warning(f"Spirit Orb cap for tickets reached ({self.ticket_orbs}/{self.s.max_orbs}).")

        # Dismiss the popup
        dismiss = self.find_any(["cancel", "close"])
        if dismiss:
            self.click(dismiss, "dismiss ticket popup")
        if self.s.out_of_tickets == OUT_OF_TICKETS_STOP:
            raise BotFinished("Out of Soul Tickets - stopping (as set in Settings).")
        minutes = max(1, self.s.recharge_wait_minutes)
        log.info(f"Waiting {minutes} min for Soul Tickets to recharge...")
        self._set_status(f"Waiting for tickets ({minutes} min)")
        self.ctl.wait(minutes * 60)
        self._set_status("Running")
        return True

    def _buy_tickets(self, purchase: Match) -> bool:
        log.info(f"Spending {self.s.orbs_per_refill} Spirit Orbs on Soul Tickets...")
        self.click(purchase, "purchase (open shop)")
        pack = self.wait_for("50_soul_tickets", timeout=5)
        if not pack:
            return False
        # Several packs may match; take the strongest match
        self.click(pack, "50 soul tickets")
        confirm = self.wait_for("purchase", timeout=5)
        if not confirm:
            return False
        if not self.click_verified("purchase", "purchase (confirm)", near=confirm):
            return False
        self.stats.orbs_spent += self.s.orbs_per_refill
        self.ticket_orbs += self.s.orbs_per_refill
        self.stats.refills += 1
        log.success(f"Bought Soul Tickets. Orbs spent on tickets this run: {self.ticket_orbs}/{self.s.max_orbs}.")
        close = self.wait_for("close", timeout=4)
        if close:
            self.click(close, "close shop")
        return True

    def _r_battle(self, f: Frame) -> bool:
        if not self.find("pause"):
            return False
        self._screen("In battle")
        now = self.clock()
        if not self.in_battle:
            self.in_battle = True
            self.battle_started = now
            if not self.quest_active:  # e.g. bot started mid-battle, or a story-only start
                self.quest_active = True
                self.clear_counted = False
            log.info("Battle in progress.")
        if self.s.ensure_auto:
            auto = self.find("auto_off")
            if auto:
                log.info("Turning AUTO on.")
                self.click(auto, "auto")
        if self.s.skip_cutscenes:
            skip = self.find("skip")
            if skip:
                self.click(skip, "skip (in battle)")
        if now - self.battle_started > 20 * 60:
            log.warning("Battle has lasted over 20 minutes - check the game.")
            self.battle_started = now
        return True

    def _r_results_banner(self, f: Frame) -> bool:
        m = self.find_any(["quest_clear", "tap_screen", "tap_here_to_continue"])
        if not m:
            return False
        self._screen("Results")
        self._count_clear()
        self.click(m, m.name, double=m.name != "quest_clear")
        return True

    def _r_skip(self, f: Frame) -> bool:
        if not self.s.skip_cutscenes:
            return False
        skip = self.find("skip")
        if not skip:
            return False
        self._screen("Story scene")
        self.click(skip, "skip")
        ok = self.wait_for("ok", timeout=1.5)  # some versions ask "Skip story?"
        if ok:
            self.click(ok, "ok (confirm skip)")
        return True

    # ------------------------------------------------- finding the way to story
    def _r_return_title(self, f: Frame) -> bool:
        """'Return to Title Screen?' - never press its OK."""
        if not self.find("return_title_text"):
            return False
        self._screen("Return to title?")
        cancel = self.find("cancel")
        log.info("'Return to Title Screen?' popup - pressing Cancel.")
        self.click(cancel if cancel else (560, 620), "cancel")
        return True

    def _nav_ready(self) -> bool:
        if self.clock() - self.nav_at < 4:
            return False   # the last tap is still opening its screen
        self.nav_at = self.clock()
        return True

    def _r_title(self, f: Frame) -> bool:
        """Title screen (after the game restarts): tap to start."""
        if not self.find("title_logo"):
            return False
        self._screen("Title screen")
        if self._nav_ready():
            log.info("Title screen - tapping GAME START.")
            self.click((800, 750), "game start")
        return True

    def _r_solo_menu(self, f: Frame) -> bool:
        """Solo Quests menu: open STORY (Story Progress mode)."""
        if self.s.mode != MODE_PROGRESS or not self.find("solo_quests_title"):
            return False
        story = self.find("solo_story")
        if not story:
            return False
        self._screen("Solo Quests")
        if self._nav_ready():
            log.info("Solo Quests - opening STORY.")
            self.click(story, "solo story")
        return True

    def _r_home(self, f: Frame) -> bool:
        """Home screen: open SOLO (Story Progress mode)."""
        if self.s.mode != MODE_PROGRESS:
            return False
        solo = self.find("home_solo")
        if not solo:
            return False
        if stage_map._brightness(f, solo.x, solo.y, solo.x + solo.w, solo.y + solo.h) < 200:
            return False   # dimmed: a menu or popup is open on top of the home screen
        self._screen("Home")
        if self._nav_ready():
            log.info("Home screen - opening SOLO to get to the story.")
            self.click(solo, "home solo")
        return True

    def _r_ok(self, f: Frame) -> bool:
        ok = self.find("ok")
        if not ok:
            return False
        self._screen("Popup")
        self.click(ok, "ok")
        return True

    def _r_results_buttons(self, f: Frame) -> bool:
        retry = self.find("retry")
        nxt = self.find("next_quest") if self.s.mode == MODE_PROGRESS else None
        if not retry and not nxt:
            return False
        self._screen("Quest results")
        self.in_battle = False
        if self.quest_active and not self.clear_counted:
            self._count_clear()
        self.post_battle_until = self.clock() + 120

        if self.s.mode == MODE_FARM:
            if retry:
                self._check_limits_before_start()
                self.click(retry, "retry")
                self._quest_started()
                return True
            return False

        # Story progress: head back to the quest list (or straight to "next")
        if nxt:
            self._check_limits_before_start()
            self.no_next_logged = False
            self.click(nxt, "next quest")
            return True
        if not self.no_next_logged:
            self.no_next_logged = True
            log.info("Results screen has no 'Next Quest' button - going back to the story map.")
            self._save_screenshot("no_next_quest")
        back = self.find_any(AREA_RETURN) or self.find("close") or self.find("back")
        if back:
            self.click(back, f"return ({back.name})")
            return True
        return True

    def _r_close(self, f: Frame) -> bool:
        close = self.find("close")
        if not close:
            return False
        self._screen("Popup")
        self.click(close, "close")
        return True

    def _r_cancel(self, f: Frame) -> bool:
        cancel = self.find("cancel")
        if not cancel:
            return False
        self._screen("Popup")
        self.click(cancel, "cancel")
        return True

    def _r_area_return(self, f: Frame) -> bool:
        if self.clock() > self.post_battle_until:
            return False
        m = self.find_any(AREA_RETURN)
        if not m:
            return False
        self._screen("Quest results")
        self.click(m, f"return ({m.name})")
        self.post_battle_until = 0
        return True

    def _r_prepare(self, f: Frame) -> bool:
        m = self.find("prepare_for_quest")
        if not m:
            return False
        self._screen("Quest info")
        self._check_limits_before_start()
        self.click(m, "prepare for quest")
        return True

    def _r_start(self, f: Frame) -> bool:
        m = self.find_any(START_BUTTONS)
        if not m:
            return False
        if stage_map._brightness(f, m.x, m.y, m.x + m.w, m.y + m.h) < 180:
            return False  # dimmed: a popup is covering the prep screen - deal with that first
        self._screen("Party / prep")
        now = self.clock()
        if self.quest_active and not self.in_battle and now - self.last_start_click < 8:
            return True  # already pressed; the battle is loading - don't press (or count) twice
        self._check_limits_before_start()
        if self.failures_in_row and self.s.mode == MODE_PROGRESS:
            log.info("Retrying the quest after a defeat.")
        if self.s.auto_boost_max and self.s.mode == MODE_FARM and not self.boost_done:
            self._set_boost_max()
            m = self.find_any(START_BUTTONS) or m
        self.click(m, "start quest")
        self.last_start_click = self.clock()
        self._quest_started()
        return True

    def _r_message_popup(self, f: Frame) -> bool:
        """A stage's Message popup whose action button isn't 'Prepare for Quest'
        (e.g. a cutscene-only stage). Layout: red Close on the left, the action
        button mirrored on the right at the same height."""
        close = self.find("close_red")
        if not close:
            return False
        self._screen("Stage message")
        cx, cy = close.center
        if cy < 760 or self.find("roster_full"):
            return False  # not a stage Message popup (e.g. the character-box popup)
        bx, by = cx + 593, cy
        patch = f.image[max(0, by - 12):by + 12, max(0, bx - 120):bx + 120]
        if patch.size == 0:
            return False
        b, g, r = (float(patch[:, :, i].mean()) for i in range(3))
        if b > r + 60:  # a blue button is there
            log.info("Stage message popup - pressing its action button.")
            self.post_battle_until = self.clock() + 120
            self.click((bx, by), "message action")
            return True
        return False

    def _set_boost_max(self) -> None:
        self.boost_done = True
        if self.find("max_boost"):
            return
        b = self.find_any(["boost_1", "boost_2"])
        if not b:
            return
        log.info("Setting Boost to max.")
        self.click(b, "boost")
        plus = self.wait_for("boost_increase", timeout=2)
        for _ in range(10):
            if not plus or self.find("max_boost"):
                break
            self.click(plus, "boost +")
            self.refresh()
            plus = self.find("boost_increase")
        self.refresh()

    # ------------------------------------------------------------ Select Part
    PART_GAP = 35          # px between part cards (base coords)

    def _highlighted_part(self, f: Frame):
        """Bounding box (x1, y1, x2, y2) of the part card with the yellow 'current' frame."""
        import cv2
        import numpy as np
        hsv = cv2.cvtColor(f.image, cv2.COLOR_BGR2HSV)
        y = ((hsv[:, :, 0] > 12) & (hsv[:, :, 0] < 38) & (hsv[:, :, 1] > 140)
             & (hsv[:, :, 2] > 190)).astype(np.uint8)
        y[:120] = 0
        y[720:] = 0
        cols = np.where(y.sum(0) > 250)[0]     # the frame's long vertical edges
        if len(cols) < 4 or cols.max() - cols.min() < 250:
            return None
        x1, x2 = int(cols.min()), int(cols.max())
        rows = np.where(y[:, x1:x2 + 1].sum(1) > 0.6 * (x2 - x1))[0]
        if len(rows) < 2:
            return None
        return x1, int(rows.min()), x2, int(rows.max())

    def _white_cards(self, f: Frame, cy: int) -> list[tuple[int, int]]:
        """Horizontal extents (x0, x1) of the white part cards on Select Part."""
        import cv2
        import numpy as np
        band = cv2.cvtColor(f.image[cy + 60:cy + 110], cv2.COLOR_BGR2GRAY)
        if band.size == 0:
            return []
        white = (band > 200).mean(0) > 0.4
        runs, start = [], None
        for x, w in enumerate(list(white) + [False]):
            if w and start is None:
                start = x
            elif not w and start is not None:
                if runs and start - runs[-1][1] <= 12:   # a gap left by the title text
                    runs[-1] = (runs[-1][0], x - 1)
                else:
                    runs.append((start, x - 1))
                start = None
        return [r for r in runs if r[1] - r[0] > 150]

    def _open_first_part(self, f: Frame, box) -> bool:
        """Started on Select Part: scroll back to Part 1 and open it, so parts go in order."""
        cy = (box[1] + box[3]) // 2 if box else 411
        st = self.part_rewind
        if st is None:
            st = self.part_rewind = {"drags": 0, "last": None, "taps": 0, "at_start": False}
            log.info("Going back to Part 1 - story parts are played in order.")
        cards = self._white_cards(f, cy)
        if not cards:
            return True  # still sliding in
        first = cards[0]
        if not st["at_start"]:
            if (st["drags"] > 0 and st["last"] is not None and abs(first[0] - st["last"]) < 12) \
                    or st["drags"] >= 40:
                st["at_start"] = True   # the list stopped moving: Part 1 is the left-most card
            else:
                st["last"] = first[0]
                st["drags"] += 1
                self.dev.drag(BASE_W * 0.15, cy, BASE_W * 0.85, cy)
                self.ctl.wait(max(1.0, self.s.action_delay))
                return True
        st["taps"] += 1
        if st["taps"] > 6:
            raise BotFinished("Couldn't open Part 1 from Select Part.")
        log.info("Opening Part 1.")
        card_w = (box[2] - box[0]) if box else 430   # neighbouring cards can merge into one run
        self.click((first[0] + min(first[1] - first[0], card_w) // 2, cy), "open part")
        self.fresh_part = True
        return True

    def _r_select_part(self, f: Frame) -> bool:
        """Select Part screen.

        Reached because the bot finished a part: open the part after the highlighted
        (current) one. Otherwise (the run started here): go back to Part 1.
        """
        if not self.find("select_part_title") or self.s.mode != MODE_PROGRESS:
            return False
        self._screen("Select Part")
        box = self._highlighted_part(f)
        if not self.part_from_map:
            return self._open_first_part(f, box)
        if box is None:
            return True  # still sliding in; look again next tick
        x1, y1, x2, y2 = box
        cy = (y1 + y2) // 2
        pick = self.part_pick
        if pick is not None and abs(((x1 + x2) // 2) - pick["from_cx"]) > 100:
            # The next part is now the highlighted one: open it.
            pick["enter_taps"] = pick.get("enter_taps", 0) + 1
            if pick["enter_taps"] > 4:
                raise BotFinished("Couldn't open the next story part from Select Part.")
            log.info("Opening the next story part.")
            self.click(((x1 + x2) // 2, cy), "open part")
            self.fresh_part = True
            return True
        nx = x2 + self.PART_GAP + (x2 - x1) // 2   # centre of the card to the right
        if nx > BASE_W - 110:
            log.info("Scrolling the part list to reach the next part.")
            self.dev.drag(BASE_W * 0.8, cy, BASE_W * 0.8 - (x2 - x1 + self.PART_GAP), cy)
            self.ctl.wait(max(1.0, self.s.action_delay))
            return True
        import cv2
        import numpy as np
        gray = cv2.cvtColor(f.image[cy + 60:cy + 110, nx - 60:nx + 60], cv2.COLOR_BGR2GRAY)
        if gray.size == 0 or float(np.median(gray)) < 150:   # no white card there
            raise BotFinished("There's no story part after this one - the story is complete!")
        if pick is None:
            self.part_pick = pick = {"from_cx": (x1 + x2) // 2, "taps": 0}
        pick["taps"] += 1
        if pick["taps"] > 5:
            raise BotFinished("The next story part didn't respond on Select Part.")
        self.part_switches += 1 if pick["taps"] == 1 else 0
        log.info("Moving on to the next story part.")
        self.click((nx, cy), "next part")
        self.fresh_part = True
        return True

    def _r_story_map(self, f: Frame) -> bool:
        """Story map: open the left-most stage without a CLEAR label that isn't locked."""
        view = stage_map.analyse(self.lib, f, self.s.match_threshold)
        if not view.is_map:
            return False  # includes a map dimmed behind a popup/cutscene
        self._screen("Story map")
        self.part_pick = None
        self.part_rewind = None
        self.back_presses = 0
        if self.s.mode != MODE_PROGRESS:
            return False  # farm mode: fall through to the 'open a stage first' message
        now = self.clock()
        self.ignored_spots = {k: t for k, t in self.ignored_spots.items() if t > now}
        open_stages = [st for st in view.playable
                       if (st.x // 40, st.y // 40) not in self.ignored_spots]
        if open_stages:
            self.map_swipes = 0
            target = open_stages[0]
            cx, cy = target.click_point
            self.no_new_frames = 0
            self.scrolls = 0
            if self.repeat_count >= 4 and self.last_action == ("stage", cx // 20, cy // 20):
                self.ignored_spots[(target.x // 40, target.y // 40)] = now + 60
                log.warning("That stage isn't opening - ignoring it for a minute.")
                self.repeat_count = 0
                return True
            if now - self.last_stage_click < 4:
                return True  # just opened it; the popup is still animating in
            kind = "story scene" if target.kind == "cutscene" else "battle"
            log.info(f"Opening the next uncleared stage ({kind}).")
            self.click((cx, cy), "stage")
            self.last_stage_click = self.clock()
            self.fresh_part = False
            self.left_scrolls = 0
            self.post_battle_until = self.clock() + 120  # in a quest flow: unknown screens get tapped
            return True

        # Nothing playable visible. Give unlock animations ~8s, then page right / finish.
        if self.no_new_frames == 0:
            self.map_empty_since = now
        self.no_new_frames += 1
        # Opening a stage moments ago means the map should be changing - don't conclude
        # anything until it has stayed clear for a while.
        # A part just opened from Select Part has no unlock animation to wait for.
        settle = 3 if self.fresh_part else 8
        if now - self.map_empty_since < settle or now - self.last_stage_click < 30:
            return True
        # Every visible stage is locked: the next stage to play is on an earlier page.
        if (view.left_arrow and self.left_scrolls < 10 and view.stages
                and all(st.locked and not st.cleared for st in view.stages)):
            self.left_scrolls += 1
            log.info("Only locked stages here - moving the map left to the next stage to play.")
            self.click(view.left_arrow, "map arrow left")
            self.no_new_frames = 0
            return True
        if view.right_arrow and self.scrolls < 10:
            self.scrolls += 1
            log.info("All visible stages cleared - moving the map right.")
            self.click(view.right_arrow, "map arrow right")
            self.no_new_frames = 0
            return True
        # Last page of this part, everything cleared: go to the next part via Select Part
        # (in HARD mode, Next Quest doesn't carry on into the next part).
        locked_here = any(st.locked and not st.cleared for st in view.stages)
        sp = self.find("select_part_button")
        if sp and not locked_here and self.part_switches < 50:
            log.info("This part is finished - opening Select Part to move to the next part.")
            self.part_pick = None
            self.part_from_map = True
            self.left_scrolls = 0
            self.click(sp, "select part")
            self.no_new_frames = 0
            return True
        # No arrow recognised: the rest of the part may be off-screen, so swipe the map
        # along before giving up.
        if self.map_swipes < 3:
            self.map_swipes += 1
            log.info(f"No uncleared stage visible - swiping the map along ({self.map_swipes}/3).")
            self.dev.drag(BASE_W * 0.82, BASE_H * 0.5, BASE_W * 0.22, BASE_H * 0.5)
            self.ctl.wait(max(1.0, self.s.action_delay))
            self.no_new_frames = 0
            return True
        locked = sum(1 for st in view.stages if st.locked and not st.cleared)
        if locked:
            raise BotFinished("The next stage is locked (it may need a story requirement or "
                              "level). Everything available here is cleared.")
        raise BotFinished("Every stage on this part of the story is cleared! Use 'Select Part' "
                          "to open the next part and press Start again.")

    def _r_new_quest(self, f: Frame) -> bool:
        if self.s.mode != MODE_PROGRESS:
            return False
        now = self.clock()
        self.ignored_spots = {k: t for k, t in self.ignored_spots.items() if t > now}
        badges: list[Match] = []
        for name in NEW_BADGES:
            badges = [b for b in self.lib.find_all(f, name, threshold=self.s.match_threshold - 0.03)
                      if (b.center[0] // 40, b.center[1] // 40) not in self.ignored_spots]
            if badges:
                break
        if not badges:
            return False
        target = badges[0]  # top-most = earliest uncleared quest/chapter
        self._screen("Quest list")
        self.no_new_frames = 0
        self.scrolls = 0
        cx, cy = target.center
        if self.repeat_count >= 4 and self.last_action == ("NEW", cx // 20, cy // 20):
            self.ignored_spots[(cx // 40, cy // 40)] = now + 60
            log.warning("That NEW badge isn't opening anything - ignoring it for a minute.")
            self.repeat_count = 0
            return True
        log.info("Opening the next NEW quest.")
        self.click(target, "NEW")
        return True

    def _r_list_without_new(self, f: Frame) -> bool:
        back = self.find("back")
        if not back:
            return False
        if stage_map._brightness(f, back.x, back.y, back.x + back.w, back.y + back.h) < stage_map.DIM_LIMIT:
            return False  # Back is dimmed: a popup/cutscene is on top, not a list
        self._screen("Quest list")
        if self.s.mode == MODE_FARM:
            # Farm mode needs a stage to repeat; a bare list means nothing to do.
            self.no_new_frames += 1
            if self.no_new_frames > 20 and not self.quest_active:
                raise BotFinished("Farm mode: open the stage you want to farm (its party / "
                                  "Start Quest screen) and press Start again.")
            return True
        self.no_new_frames += 1
        if self.no_new_frames < 3:  # give the list time to load/animate
            return True
        if self.scrolls < 4:
            self.scrolls += 1
            log.info(f"No NEW quest visible - scrolling the list ({self.scrolls}/4).")
            self.dev.drag(BASE_W * 0.5, BASE_H * 0.72, BASE_W * 0.5, BASE_H * 0.32)
            self.ctl.wait(self.s.action_delay)
            self.no_new_frames = 1
            return True
        # Not a story screen: go Back (towards the home screen, from where the bot
        # finds its way to the story map).
        if self.back_presses < 8:
            self.back_presses += 1
            log.info(f"Not a story screen - pressing Back ({self.back_presses}/8).")
            self.click(back, "back")
            self.no_new_frames = 0
            self.scrolls = 4   # don't scroll again on the next screen
            return True
        raise BotFinished(
            "No NEW quests left on this screen - story is cleared up to here! "
            "Open the next area/chapter and press Start again.")

    # ================================================================ watchdog
    def _save_unknown(self) -> None:
        """Keep one picture of each distinct unrecognised screen (logs/unknown_screens),
        so missing buttons can be captured from it on the Templates page."""
        import cv2
        frame = getattr(self, "_frame", None)
        if frame is None or len(self.unknown_saved) >= 40:
            return
        thumb = cv2.resize(cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY), (64, 36)).astype("float32")
        if any(float(abs(thumb - t).mean()) < 8 for t in self.unknown_saved):
            return
        self.unknown_saved.append(thumb)
        d = os.path.join(paths.logs_dir(), "unknown_screens")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"unknown_{datetime.now():%Y%m%d_%H%M%S}.png")
        imwrite(path, frame.image)
        log.info(f"New unrecognised screen saved: {path}")

    # ================================================================ watchdog
    def _watchdog(self) -> None:
        now = self.clock()
        self._screen("Unknown / loading")
        if self.unknown_since is None:
            self.unknown_since = now
        idle = now - self.last_progress
        if self.s.save_unknown_screens and now - self.unknown_since > 10:
            self._save_unknown()
        # In Story Progress every screen between quests is part of the story flow (results,
        # cutscenes, the intro of a new part...), so keep nudging unknown screens along.
        in_flow = (self.quest_active or now < self.post_battle_until
                   or (self.s.mode == MODE_PROGRESS and self.stats.started > 0))
        if (self.s.tap_to_advance and in_flow and not self.in_battle
                and now - self.unknown_since > 6 and now - self.last_tap > 4):
            log.debug("Unrecognised screen during a quest - tapping to advance.")
            self.last_tap = now
            self.dev.click(*self.TAP_POINT)
        frozen = self._frozen_for(now)
        if frozen > 60 and not self.frozen_warned:
            self.frozen_warned = True
            log.warning("The game picture hasn't changed for a minute. If BlueStacks is "
                        "minimised it may have paused - restore its window (it can stay behind "
                        "other windows).")
        if idle > self.s.stuck_timeout_seconds:
            path = self._save_screenshot("stuck")
            hint = f" Screenshot: {path}" if path else ""
            why = (" The game picture stopped changing - BlueStacks was probably minimised and "
                   "paused. Keep it open (behind other windows is fine) and press Start again."
                   if frozen > 60 else
                   " Use the Templates page to capture the button the bot should press.")
            raise BotFinished(f"Stuck: no known screen for {int(idle)}s.{why}{hint}")

    def _frozen_for(self, now: float) -> float:
        """Seconds the screen has looked exactly the same (a paused emulator)."""
        import cv2
        frame = getattr(self, "_frame", None)
        if frame is None:
            return 0.0
        thumb = cv2.resize(cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY), (96, 54)).astype("float32")
        if self.last_thumb is None or float(abs(thumb - self.last_thumb).mean()) > 1.5:
            self.last_thumb, self.same_since = thumb, now
            self.frozen_warned = False
        return now - self.same_since
