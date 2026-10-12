"""Top-bottom layout regions, derived from the safe-zone spec (#62 part A). Pure.

The comedy-forward layout splits the 1080x1920 canvas into a **graphic panel** on
top and the **presenter** (head-and-shoulders) below. The panels are fixed halves
of the canvas; what the safe zone decides is where things may *live* inside them:

  - ``graphic``        — the top panel. A split-layout clip covers all of it, so
                         its background bleeds to the frame edges (no presenter
                         slivers around the graphic). Background only lands in the
                         danger zone; content never does.
  - ``graphic_safe``   — the largest safe rect inside the top panel: where template
                         content (text, numbers, the PARODY tag) is laid out.
  - ``presenter``      — the bottom panel (the V1 presenter shows through here).
  - ``presenter_safe`` — the largest safe, notch-free rect inside the bottom panel:
                         where the presenter's face should land when recording.
  - ``full_safe``      — the largest safe rect on the whole canvas: where content
                         lives in a full-graphic (punch-in) clip.

"Largest safe rect" is computed exactly from the spec's row-convex ``bands``
(notch included), so a safe-zone regeneration flows through. The result is
versioned (:data:`REGIONS_VERSION`); the schema pins the v1 numbers and a test
asserts they still equal this derivation, so a safe-zone change forces a bump.

Rects are integer pixel-edge ``(x, y, w, h)`` on the canvas, half-open like the
safe-zone spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Union

from ..safezone.spec import Band, SafeZoneSpec

REGIONS_VERSION = "reels-9x16.top-bottom.v1"
LAYOUTS = ("split", "full-graphic", "full-presenter")


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def x1(self) -> int:
        return self.x + self.w

    @property
    def y1(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    def contains(self, other: "Rect") -> bool:
        return (self.x <= other.x and self.y <= other.y
                and other.x1 <= self.x1 and other.y1 <= self.y1)

    def relative_to(self, origin: "Rect") -> "Rect":
        return Rect(self.x - origin.x, self.y - origin.y, self.w, self.h)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_any(cls, r: Union["Rect", Mapping]) -> "Rect":
        if isinstance(r, Rect):
            return r
        return cls(int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"]))


@dataclass(frozen=True)
class ClipGeometry:
    """Where a beat's clip sits on the canvas and where its content lives.

    ``placement`` is the clip's rect on the canvas (its pixel size is the render
    size); ``safe_box`` is the content rect **relative to the clip's own frame**.
    """

    placement: Rect
    safe_box: Rect


def _clip_bands(bands: List[Band], panel: Rect) -> List[Band]:
    out: List[Band] = []
    for b in sorted(bands, key=lambda b: b.y0):
        x0, x1 = max(b.x0, panel.x), min(b.x1, panel.x1)
        y0, y1 = max(b.y0, panel.y), min(b.y1, panel.y1)
        if x1 > x0 and y1 > y0:
            out.append(Band(x0, y0, x1, y1))
    return out


def largest_safe_rect(spec: SafeZoneSpec, panel: Rect) -> Rect:
    """The largest-area axis-aligned rect inside both ``panel`` and the safe region.

    Exact over the spec's row-convex bands: every run of vertically contiguous
    bands bounds a candidate (its common x-span times its height). Ties prefer the
    wider, then the higher candidate. Raises ``ValueError`` if the panel holds no
    safe pixels.
    """
    bands = _clip_bands(spec.bands, panel)
    best: Optional[Rect] = None
    for i in range(len(bands)):
        x0, x1 = bands[i].x0, bands[i].x1
        for j in range(i, len(bands)):
            if j > i and bands[j].y0 != bands[j - 1].y1:
                break  # a vertical gap ends the run
            x0, x1 = max(x0, bands[j].x0), min(x1, bands[j].x1)
            if x1 <= x0:
                break
            cand = Rect(x0, bands[i].y0, x1 - x0, bands[j].y1 - bands[i].y0)
            if best is None or (cand.area, cand.w, -cand.y) > (best.area, best.w, -best.y):
                best = cand
    if best is None:
        raise ValueError(f"no safe area inside panel {panel.to_dict()} — check the safe-zone spec")
    return best


def derive_regions(spec: SafeZoneSpec) -> Dict[str, Rect]:
    """The v1 top-bottom regions for ``spec``'s canvas (see module docstring)."""
    w, h = spec.image_width, spec.image_height
    split_y = h // 2
    graphic = Rect(0, 0, w, split_y)
    presenter = Rect(0, split_y, w, h - split_y)
    return {
        "graphic": graphic,
        "graphic_safe": largest_safe_rect(spec, graphic),
        "presenter": presenter,
        "presenter_safe": largest_safe_rect(spec, presenter),
        "full_safe": largest_safe_rect(spec, Rect(0, 0, w, h)),
    }


def clip_geometry(layout: str, regions: Mapping[str, Union[Rect, Mapping]]) -> Optional[ClipGeometry]:
    """Clip placement + relative content box for a beat layout.

    ``split`` → the graphic panel; ``full-graphic`` → the whole canvas (graphic +
    presenter panels) with content in ``full_safe``; ``full-presenter`` → ``None``
    (no clip). ``regions`` may be :class:`Rect` values or the schema's dict form.
    """
    if layout not in LAYOUTS:
        raise ValueError(f"layout {layout!r} not in {LAYOUTS}")
    r = {k: Rect.from_any(v) for k, v in regions.items()}
    if layout == "full-presenter":
        return None
    if layout == "split":
        placement = r["graphic"]
        return ClipGeometry(placement, r["graphic_safe"].relative_to(placement))
    g, p = r["graphic"], r["presenter"]
    canvas = Rect(min(g.x, p.x), min(g.y, p.y), max(g.x1, p.x1) - min(g.x, p.x),
                  max(g.y1, p.y1) - min(g.y, p.y))
    return ClipGeometry(canvas, r["full_safe"].relative_to(canvas))
