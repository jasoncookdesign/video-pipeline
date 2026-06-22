"""Framing intents — target-relative composition presets for the reframe (INI-090 C).

A framing intent is the *human composition decision* the bare subject-tracker lacks.
It is expressed relative to the target frame (fractions, not pixels), so the same
intent resolves against any aspect preset:

  - ``subject_scale`` — punch-in factor. 1.0 = the widest native crop (the largest
    target-aspect rectangle that fits the source — the most you can show without
    letterbox fill); > 1.0 punches in (crop = native / scale, subject larger). Values
    < 1.0 clamp to native — there is deliberately no pull-back past the source bounds
    (no fill), so native is the widest framing.
  - ``subject_y_frac`` — where the subject's vertical centre sits inside the crop
    (0.0 = top, 1.0 = bottom). Only bites when the crop is shorter than the source
    (i.e. when zoomed, or a source taller than the target); a full-height crop has no
    vertical slack. ``None`` keeps the legacy centred behaviour.
  - ``caption_position`` — the caption anchor this framing pairs with, so the crop and
    the caption band are designed together instead of colliding. ``performer`` frames
    the face high and reserves the lower band for the torso/props *and* the captions.

The crop geometry consumes ``subject_scale`` + ``subject_y_frac`` (see
``plan.build_crop_plan``); the caption layer consumes ``caption_position``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class FramingIntent:
    key: str
    label: str
    subject_scale: float
    subject_y_frac: Optional[float]
    caption_position: str          # "lower-third" | "upper-third" | "center"
    description: str


FRAMING_INTENTS: Dict[str, FramingIntent] = {
    "talking-head": FramingIntent(
        "talking-head", "Talking head", 1.30, 0.33, "lower-third",
        "Punched in on the face (upper third), captions low. For pieces-to-camera "
        "where the speaker is the whole shot."),
    "performer": FramingIntent(
        "performer", "Performer", 1.00, 0.35, "lower-third",
        "Widest native crop with the face high, reserving the lower band for the "
        "torso / instrument / props and the captions. The DJ-at-the-decks framing. "
        "(Vertical bias only bites when there is slack — i.e. when punched in or the "
        "source is taller than the target.)"),
    "wide-context": FramingIntent(
        "wide-context", "Wide context", 1.00, 0.50, "lower-third",
        "Widest native crop, subject centred — show as much of the source as the "
        "target aspect allows (no fill). Captions low."),
}

DEFAULT_FRAMING = "performer"   # recommended; CLI leaves framing opt-in (None = legacy)


def framing_intent(key: str) -> FramingIntent:
    try:
        return FRAMING_INTENTS[key]
    except KeyError:
        raise ValueError(
            f"unknown framing intent {key!r}; valid: {sorted(FRAMING_INTENTS)}"
        ) from None
