"""Crop-plan computation — subject centres -> a stabilised crop window.

Pure and fully unit-tested. Given per-frame subject centres and the source
dimensions, produce a 9:16 (profile-aspect) crop window that:
  - has the exact output aspect ratio,
  - is clamped inside the source frame (never crops outside the footage),
  - is stabilised (EMA smoothing + per-sample shift clamp + dead-band) so the
    reframe doesn't jitter when the subject makes small movements.

Two modes:
  - ``static``  (probe default) — one robust window for the whole clip. Simplest
    thing that proves the trust model.
  - ``dynamic`` — a window per sample, smoothed; the seam for motion tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import List, Optional, Tuple

from .tracker import FrameSubject


@dataclass(frozen=True)
class CropWindow:
    t_start: float
    t_end: float
    x: int
    y: int
    w: int
    h: int

    @property
    def aspect(self) -> float:
        return self.w / self.h


@dataclass(frozen=True)
class CropPlan:
    src_w: int
    src_h: int
    out_w: int
    out_h: int
    mode: str
    windows: List[CropWindow]


# ── geometry helpers ──────────────────────────────────────────────────────────

def crop_dims(src_w: int, src_h: int, out_w: int, out_h: int) -> Tuple[int, int]:
    """Largest crop of (src_w, src_h) matching the out aspect, even dimensions."""
    target = out_w / out_h
    cw = src_h * out_w / out_h
    if cw <= src_w:
        crop_w, crop_h = cw, float(src_h)
    else:
        crop_w, crop_h = float(src_w), src_w * out_h / out_w
    # round to even (encoder-friendly) and never exceed the source
    crop_w = min(src_w, int(round(crop_w / 2) * 2))
    crop_h = min(src_h, int(round(crop_h / 2) * 2))
    return crop_w, crop_h


def clamp_center(cx: float, crop_w: int, src_w: int) -> float:
    """Clamp a desired centre x so the crop window stays inside the frame."""
    lo = crop_w / 2
    hi = src_w - crop_w / 2
    if hi < lo:  # crop spans the whole width
        return src_w / 2
    return min(max(cx, lo), hi)


def window_x(cx: float, crop_w: int, src_w: int) -> int:
    """Integer left edge for a clamped centre."""
    x = int(round(clamp_center(cx, crop_w, src_w) - crop_w / 2))
    return min(max(x, 0), src_w - crop_w)


def ema_smooth(values: List[float], alpha: float) -> List[float]:
    """Exponential moving average. alpha in (0, 1]; higher = less smoothing."""
    if not values:
        return []
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def _robust_center(subjects: List[FrameSubject], src_w: int) -> float:
    if not subjects:
        return src_w / 2
    confident = [s.cx for s in subjects if s.confidence > 0]
    xs = confident if confident else [s.cx for s in subjects]
    return float(median(xs))


# ── plan builders ─────────────────────────────────────────────────────────────

def build_crop_plan(
    subjects: List[FrameSubject],
    src_w: int,
    src_h: int,
    out_w: int = 1080,
    out_h: int = 1920,
    mode: str = "static",
    ema_alpha: float = 0.2,
    max_shift_frac: float = 0.04,
    deadband_frac: float = 0.02,
    duration: Optional[float] = None,
) -> CropPlan:
    """Build a crop plan from subject centres.

    Args:
        subjects:      per-frame subject centres (may be empty -> centred crop).
        src_w, src_h:  source dimensions.
        out_w, out_h:  output (profile) dimensions; sets the crop aspect.
        mode:          "static" | "dynamic".
        ema_alpha:     smoothing factor for dynamic mode.
        max_shift_frac:max centre shift between samples, as a fraction of src_w.
        deadband_frac: ignore centre moves smaller than this fraction of src_w.
        duration:      clip duration (for the static window end / last sample).
    """
    crop_w, crop_h = crop_dims(src_w, src_h, out_w, out_h)
    y = (src_h - crop_h) // 2  # vertical: centre band (subjects are framed in it)

    if mode == "static" or len(subjects) <= 1:
        cx = _robust_center(subjects, src_w)
        x = window_x(cx, crop_w, src_w)
        t_end = duration if duration is not None else (subjects[-1].t if subjects else 0.0)
        t_start = subjects[0].t if subjects else 0.0
        return CropPlan(
            src_w, src_h, out_w, out_h, "static",
            [CropWindow(t_start, max(t_end, t_start), x, y, crop_w, crop_h)],
        )

    if mode != "dynamic":
        raise ValueError(f"unknown mode: {mode!r}")

    # dynamic: clamp raw centres, EMA-smooth, apply dead-band + per-sample shift clamp
    max_shift = max_shift_frac * src_w
    deadband = deadband_frac * src_w
    raw = [clamp_center(s.cx, crop_w, src_w) for s in subjects]
    smoothed = ema_smooth(raw, ema_alpha)

    centres: List[float] = []
    for i, c in enumerate(smoothed):
        if i == 0:
            centres.append(c)
            continue
        prev = centres[-1]
        if abs(c - prev) < deadband:
            centres.append(prev)
            continue
        step = max(-max_shift, min(max_shift, c - prev))
        centres.append(prev + step)

    windows: List[CropWindow] = []
    n = len(subjects)
    for i, s in enumerate(subjects):
        t_start = s.t
        t_end = subjects[i + 1].t if i + 1 < n else (
            duration if duration is not None else s.t
        )
        x = window_x(centres[i], crop_w, src_w)
        windows.append(CropWindow(t_start, max(t_end, t_start), x, y, crop_w, crop_h))
    return CropPlan(src_w, src_h, out_w, out_h, "dynamic", windows)
