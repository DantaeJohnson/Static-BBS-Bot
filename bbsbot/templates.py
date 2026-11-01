"""Catalogue of every on-screen element the bot looks for.

The Templates page in the GUI uses this list so you can see what's missing and
re-capture any button straight from your own game.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    group: str
    description: str
    required: bool = True


SPECS: list[TemplateSpec] = [
    # Battle
    TemplateSpec("pause", "Battle", "Pause button (top-left) - tells the bot a battle is running"),
    TemplateSpec("auto_off", "Battle", "AUTO button while auto-battle is OFF"),
    TemplateSpec("continue_check", "Battle", "'Continue?' text after your team is defeated"),
    TemplateSpec("quit", "Battle", "Red 'Quit' button on the Continue? popup"),
    # Results
    TemplateSpec("quest_clear", "Results", "'QUEST CLEAR' banner"),
    TemplateSpec("tap_screen", "Results", "'TAP SCREEN' prompt on the results screen"),
    TemplateSpec("tap_here_to_continue", "Results", "'TAP HERE TO CONTINUE' prompt"),
    TemplateSpec("next_quest", "Results",
                 "'Next Quest' button on the results screen - how Story Progress moves on"),
    TemplateSpec("retry", "Results", "'Retry' button after a quest (used in Farm mode)"),
    TemplateSpec("human_world", "Results", "'The Human World' return button"),
    TemplateSpec("soul_society", "Results", "'The Soul Society' return button"),
    TemplateSpec("hueco_mundo", "Results", "'Hueco Mundo' return button"),
    TemplateSpec("side_stories", "Results", "'Side Stories' return button"),
    TemplateSpec("others", "Results", "'Others' return button"),
    TemplateSpec("story_return", "Results",
                 "'Story' button on the results screen (back to the story map)"),
    # Story / quest flow
    TemplateSpec("skip", "Story", "'Skip' button during story scenes/dialogue"),
    TemplateSpec("ok", "Story", "Blue 'OK' button on popups"),
    TemplateSpec("close", "Story", "Blue 'Close' button on popups"),
    TemplateSpec("cancel", "Story", "Red 'Cancel' button on popups"),
    TemplateSpec("close_red", "Story", "Red 'Close' button on a stage's Message popup"),
    TemplateSpec("back", "Story", "'Back' arrow (top-left) - marks a list screen"),
    TemplateSpec("story_clear", "Story", "'CLEAR' label under a finished stage on the story map"),
    TemplateSpec("story_stars_empty", "Story", "Grey (unearned) star plate under a battle stage on the map"),
    TemplateSpec("story_node", "Story", "Blue pedestal of a cutscene-only stage on the map"),
    TemplateSpec("story_node_current", "Story",
                 "Yellow pedestal of the stage your character is standing on", False),
    TemplateSpec("story_arrow_left", "Story", "Yellow '<' arrow on the story map", False),
    TemplateSpec("story_arrow_right", "Story",
                 "Yellow '>' arrow on the story map - moves to the next page of stages"),
    TemplateSpec("select_part_button", "Story", "'Select Part' button (bottom-left of the story map)"),
    TemplateSpec("select_part_title", "Story", "'Select Part' title at the top of the part list"),
    TemplateSpec("new_2", "Story", "'NEW' badge on an uncleared quest (side-story lists)"),
    TemplateSpec("new", "Story", "'NEW' badge (alternate style)"),
    TemplateSpec("story_new", "Story",
                 "'NEW' badge in a list-style menu, if yours differs from the defaults", False),
    TemplateSpec("prepare_for_quest", "Story", "Blue 'Prepare for Quest' button on the stage's Message popup"),
    TemplateSpec("start_quest", "Story", "Blue 'Start Quest' button on the Prepare for Quest screen"),
    TemplateSpec("orbs_start_quest", "Story", "'Start Quest' button (alternate size)", False),
    # Tickets & orbs
    TemplateSpec("purchase", "Tickets", "'Purchase' button on the not-enough-Soul-Tickets popup / shop"),
    TemplateSpec("50_soul_tickets", "Tickets", "'50 Soul Tickets' option in the refill shop"),
    TemplateSpec("start_quest_failed", "Tickets", "Red 'Start Quest' (not enough tickets)", False),
    # End of content
    TemplateSpec("story_complete", "Results", "'Congratulations on completing the story!' (Story Complete popup)"),
    TemplateSpec("story_complete_title", "Results", "'Story Complete' popup title", False),
    # Character box full
    TemplateSpec("roster_full", "Tickets", "'You have reached the maximum number of characters' text"),
    TemplateSpec("expand_roster", "Tickets", "Blue 'Expand Roster' button on that popup"),
    TemplateSpec("roster_close", "Tickets", "Red 'Close' button on that popup"),
    TemplateSpec("slots_confirm", "Tickets", "Yellow '5 Character' text on the slot purchase confirmation"),
    # Boost
    TemplateSpec("boost_1", "Boost", "'Boost' label (off)", False),
    TemplateSpec("boost_2", "Boost", "'Boost' label (orange/on)", False),
    TemplateSpec("boost_increase", "Boost", "Green '+' to raise boost", False),
    TemplateSpec("max_boost", "Boost", "'x10 Boost' indicator", False),
]

SPEC_BY_NAME = {s.name: s for s in SPECS}
GROUPS = ["Battle", "Results", "Story", "Tickets", "Boost"]

AREA_RETURN = ["story_return", "human_world", "soul_society", "hueco_mundo", "side_stories", "others"]
NEW_BADGES = ["story_new", "new_2", "new"]
START_BUTTONS = ["start_quest", "orbs_start_quest"]
