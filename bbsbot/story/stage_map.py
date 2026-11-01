"""Reads the Story *map* screen (Story -> MAIN/SIDE -> Part N).

Stages sit on a path drawn over the city:

* Battle stages: a hexagon with the stage number, then a plate of three stars.
* Cutscene-only stages: a round blue pedestal with the number underneath.

A stage is **cleared** when a "CLEAR" label sits right under its number.
Gold stars are a bonus and don't matter. A stage with no CLEAR label is new or
incomplete. A **locked** stage is drawn darkened, so its number is grey instead
of bright white. The next stage to play is the left-most stage that is neither
cleared nor locked.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from bbsbot.vision import BASE_H, BASE_W, Frame, TemplateLibrary

CLEAR = "story_clear"
STARS = "story_stars_empty"   # grey (unearned) star plate under a battle stage
NODE = "story_node"           # blue pedestal of a cutscene stage
NODE_CURRENT = "story_node_current"  # yellow pedestal: the stage your character stands on
ARROW_LEFT = "story_arrow_left"
ARROW_RIGHT = "story_arrow_right"

STARS_THRESHOLD = 0.70        # locked plates are darker and score ~0.76
NUMBER_BRIGHT = 190           # 97th-percentile grey level of an unlocked stage number
DIM_LIMIT = 150               # Back button / CLEAR labels are ~255 normally, ~55 under a popup


@dataclass
class Stage:
    kind: str                 # "battle" or "cutscene"
    x: int                    # anchor (centre of star plate / pedestal), base coords
    y: int
    cleared: bool
    locked: bool
    number_brightness: float

    @property
    def playable(self) -> bool:
        return not self.cleared and not self.locked

    @property
    def click_point(self) -> tuple[int, int]:
        # Battle: click the stage number above the stars. Cutscene: the pedestal.
        if self.kind == "battle":
            return self.x, max(0, self.y - 38)
        return self.x, self.y


@dataclass
class MapView:
    is_map: bool = False
    stages: list[Stage] = field(default_factory=list)
    left_arrow: tuple[int, int] | None = None
    right_arrow: tuple[int, int] | None = None
    dimmed: bool = False      # a popup / cutscene is drawn over the map

    @property
    def playable(self) -> list[Stage]:
        return sorted((s for s in self.stages if s.playable), key=lambda s: s.x)


def _brightness(frame: Frame, x0: int, y0: int, x1: int, y1: int) -> float:
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(BASE_W, x1), min(BASE_H, y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    gray = cv2.cvtColor(frame.image[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return float(np.percentile(gray, 97))


def analyse(lib: TemplateLibrary, frame: Frame, threshold: float | None = None) -> MapView:
    thr = threshold if threshold is not None else lib.threshold
    view = MapView()
    if not (lib.has(CLEAR) and (lib.has(STARS) or lib.has(NODE))):
        return view

    clears = [m.center for m in lib.find_all(frame, CLEAR, threshold=thr - 0.05)]

    def has_clear(x, y, dy_min, dy_max):
        return any(abs(cx - x) < 70 and dy_min <= cy - y <= dy_max for cx, cy in clears)

    for m in lib.find_all(frame, STARS, threshold=min(thr, STARS_THRESHOLD)):
        x, y = m.center
        b = _brightness(frame, x - 48, y - 57, x + 50, y - 20)  # number above the stars
        view.stages.append(Stage("battle", x, y, has_clear(x, y, -5, 60), b < NUMBER_BRIGHT, b))

    for m in lib.find_all(frame, NODE, threshold=thr - 0.05):
        x, y = m.center
        b = _brightness(frame, x - 45, y + 33, x + 45, y + 68)  # number below the pedestal
        view.stages.append(Stage("cutscene", x, y, has_clear(x, y, 50, 125), b < NUMBER_BRIGHT, b))

    # The stage your character stands on has a yellow pedestal instead of a blue one
    # (seen in HARD mode at the start of a part). Same geometry, slightly lower anchor.
    if lib.has(NODE_CURRENT):
        for m in lib.find_all(frame, NODE_CURRENT, threshold=thr - 0.08):
            x, y = m.center
            if any(abs(s.x - x) < 40 and abs(s.y - y) < 40 for s in view.stages):
                continue
            b = _brightness(frame, x - 45, y + 24, x + 45, y + 56)
            view.stages.append(Stage("cutscene", x, y, has_clear(x, y, 40, 115),
                                     b < NUMBER_BRIGHT, b))

    left = lib.find(frame, ARROW_LEFT, threshold=thr)
    right = lib.find(frame, ARROW_RIGHT, threshold=thr)
    view.left_arrow = left.center if left else None
    view.right_arrow = right.center if right else None

    # Cleared stages with gold stars aren't matched by STARS, but their CLEAR
    # labels still tell us this is the map.
    back = lib.find(frame, "back")
    signals = len(view.stages) + len(clears) + (left is not None) + (right is not None)
    looks_like_map = signals >= 2 or (signals >= 1 and back is not None)

    # A popup or cutscene drawn over the map darkens everything behind it. Template
    # matching ignores brightness, so check it explicitly: never act on a dimmed map.
    if back is not None:
        level = _brightness(frame, back.x, back.y, back.x + back.w, back.y + back.h)
    elif clears:
        cx, cy = clears[0]
        level = _brightness(frame, cx - 40, cy - 12, cx + 40, cy + 12)
    else:
        level = 255.0
    view.dimmed = looks_like_map and level < DIM_LIMIT
    view.is_map = looks_like_map and not view.dimmed
    return view
