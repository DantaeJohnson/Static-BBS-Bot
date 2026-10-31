"""Screen capture normalisation and template matching.

Every screenshot is resized to a fixed *base* resolution (1600x900, the size
the button templates were captured at). That makes matching work for any 16:9
window size; coordinates are converted back to screen pixels when clicking.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass

import cv2
import numpy as np

from bbsbot import paths

BASE_W, BASE_H = 1600, 900
COARSE_SLACK = 0.18   # how much lower a coarse score may be and still get refined
REFINE_PAD = 10       # px of search margin around a coarse hit (full res)


@dataclass
class Match:
    name: str
    score: float
    x: int  # top-left, base coords
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


class Frame:
    """A screenshot normalised to the base resolution, with a small pyramid."""

    def __init__(self, image: np.ndarray, source_size: tuple[int, int] | None = None):
        h, w = image.shape[:2]
        self.source_size = source_size or (w, h)
        if (w, h) != (BASE_W, BASE_H):
            interp = cv2.INTER_AREA if w > BASE_W else cv2.INTER_LINEAR
            image = cv2.resize(image, (BASE_W, BASE_H), interpolation=interp)
        self.image = image
        self._levels: dict[int, np.ndarray] = {}

    def level(self, factor: int) -> np.ndarray:
        """Downscaled grayscale copy used for the fast coarse search."""
        if factor not in self._levels:
            gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
            self._levels[factor] = gray if factor == 1 else cv2.resize(
                gray, (BASE_W // factor, BASE_H // factor), interpolation=cv2.INTER_AREA)
        return self._levels[factor]

    @property
    def aspect_ok(self) -> bool:
        w, h = self.source_size
        return h > 0 and abs((w / h) - (BASE_W / BASE_H)) < 0.03


class _Template:
    def __init__(self, name: str, path: str, image: np.ndarray, user: bool):
        self.name = name
        self.path = path
        self.user = user
        self.full = image
        h, w = image.shape[:2]
        # Pick the coarsest level that keeps at least ~7px on the short side.
        self.factor = 4 if min(w, h) >= 28 else 2 if min(w, h) >= 14 else 1
        f = self.factor
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self.coarse = gray if f == 1 else cv2.resize(
            gray, (max(1, w // f), max(1, h // f)), interpolation=cv2.INTER_AREA)


class TemplateLibrary:
    """Loads PNG templates. User-captured templates override bundled ones.

    Matching is coarse-to-fine: search a downscaled frame, then confirm each
    candidate at full resolution in a small window. Scores are always the
    full-resolution TM_CCOEFF_NORMED value.
    """

    def __init__(self, threshold: float = 0.85, fast: bool = True,
                 bundled_dir: str | None = None, user_dir: str | None = None):
        self.threshold = threshold
        self.fast = fast
        self.bundled_dir = bundled_dir or paths.bundled_templates_dir()
        self.user_dir = user_dir or paths.user_templates_dir()
        self._templates: dict[str, _Template] = {}
        self._lock = threading.Lock()
        self.reload()

    # -- loading -----------------------------------------------------------
    def reload(self) -> None:
        templates: dict[str, _Template] = {}
        for folder, is_user in ((self.bundled_dir, False), (self.user_dir, True)):
            if not folder or not os.path.isdir(folder):
                continue
            for fn in sorted(os.listdir(folder)):
                if not fn.lower().endswith(".png"):
                    continue
                path = os.path.join(folder, fn)
                img = imread(path)
                if img is None:
                    continue
                name = os.path.splitext(fn)[0]
                templates[name] = _Template(name, path, img, is_user)
        with self._lock:
            self._templates = templates

    def names(self) -> list[str]:
        return sorted(self._templates)

    def has(self, name: str) -> bool:
        return name in self._templates

    def info(self, name: str):
        return self._templates.get(name)

    # -- core matching -----------------------------------------------------
    def _candidates(self, frame: Frame, t: _Template, thr: float, many: bool):
        """Yield (score, x, y) full-res matches >= thr."""
        H, W = frame.image.shape[:2]
        th, tw = t.full.shape[:2]
        if th > H or tw > W:
            return []
        if not self.fast:
            res = cv2.matchTemplate(frame.image, t.full, cv2.TM_CCOEFF_NORMED)
            return self._peaks(res, thr, many, th, tw, 1)

        f = t.factor
        res = cv2.matchTemplate(frame.level(f), t.coarse, cv2.TM_CCOEFF_NORMED)
        coarse = self._peaks(res, thr - COARSE_SLACK, True, max(1, th // f), max(1, tw // f), f,
                             limit=12 if many else 3)
        out = []
        for _, cx, cy in coarse:
            x0 = max(0, cx - REFINE_PAD - f)
            y0 = max(0, cy - REFINE_PAD - f)
            x1 = min(W, cx + tw + REFINE_PAD + f)
            y1 = min(H, cy + th + REFINE_PAD + f)
            roi = frame.image[y0:y1, x0:x1]
            if roi.shape[0] < th or roi.shape[1] < tw:
                continue
            r = cv2.matchTemplate(roi, t.full, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(r)
            if mv >= thr:
                out.append((float(mv), x0 + ml[0], y0 + ml[1]))
        out.sort(key=lambda c: -c[0])
        return out if many else out[:1]

    @staticmethod
    def _peaks(res, thr, many, h, w, scale, limit=20):
        if not many:
            _, mv, _, ml = cv2.minMaxLoc(res)
            return [(float(mv), ml[0] * scale, ml[1] * scale)] if mv >= thr else []
        ys, xs = np.where(res >= thr)
        if len(xs) == 0:
            return []
        scores = res[ys, xs]
        order = np.argsort(-scores)
        picked = []
        for i in order:
            x, y = int(xs[i]), int(ys[i])
            if any(abs(x - px) < w * 0.6 and abs(y - py) < h * 0.6 for _, px, py in picked):
                continue
            picked.append((float(scores[i]), x, y))
            if len(picked) >= limit:
                break
        return [(s, x * scale, y * scale) for s, x, y in picked]

    # -- public API --------------------------------------------------------
    def score(self, frame: Frame, name: str) -> float:
        """Best full-resolution score (for the Test Detection tool)."""
        t = self._templates.get(name)
        if t is None or t.full.shape[0] > BASE_H or t.full.shape[1] > BASE_W:
            return 0.0
        res = cv2.matchTemplate(frame.image, t.full, cv2.TM_CCOEFF_NORMED)
        return float(res.max())

    def find(self, frame: Frame, name: str, threshold: float | None = None) -> Match | None:
        """Best match above threshold, or None (also None if template missing)."""
        t = self._templates.get(name)
        if t is None:
            return None
        thr = threshold if threshold is not None else self.threshold
        c = self._candidates(frame, t, thr, many=False)
        if not c:
            return None
        s, x, y = c[0]
        h, w = t.full.shape[:2]
        return Match(name, s, x, y, w, h)

    def find_any(self, frame: Frame, names, threshold: float | None = None) -> Match | None:
        for n in names:
            m = self.find(frame, n, threshold)
            if m:
                return m
        return None

    def find_all(self, frame: Frame, name: str, threshold: float | None = None,
                 max_results: int = 20) -> list[Match]:
        """All non-overlapping matches, sorted top-to-bottom then left-to-right."""
        t = self._templates.get(name)
        if t is None:
            return []
        thr = threshold if threshold is not None else self.threshold
        h, w = t.full.shape[:2]
        picked: list[Match] = []
        for s, x, y in self._candidates(frame, t, thr, many=True):
            if any(abs(x - m.x) < w * 0.6 and abs(y - m.y) < h * 0.6 for m in picked):
                continue
            picked.append(Match(name, s, x, y, w, h))
            if len(picked) >= max_results:
                break
        picked.sort(key=lambda m: (m.y, m.x))
        return picked


# -- file helpers that handle non-ASCII Windows paths ------------------------
def imread(path: str):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except (OSError, ValueError):
        return None


def imwrite(path: str, image: np.ndarray) -> bool:
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, image)
    if not ok:
        return False
    buf.tofile(path)
    return True
