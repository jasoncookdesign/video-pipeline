"""Beat windows → V2 placements (#62 part A). Pure; consumed by both serializers.

A :class:`VisualPlacement` is everything a serializer needs to drop one rendered
clip on the visuals track: the media path, its pixel size and length, where it
sits on the canvas, and its cut-time window. Only ``generator: remotion`` beats
are placed (their clips come from ``visuals-render`` under a known name); real /
Higgsfield beats are reported in the notes for the editor to place by hand, and
``full-presenter`` beats leave the track empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from ..fcpxml.timeline import quantize
from .props import clip_duration_s, clip_name
from .spec import VisualsSpec
from .timing import BeatWindow


@dataclass(frozen=True)
class VisualPlacement:
    beat_id: str
    name: str            # clip name without extension
    src: str             # media path
    layout: str          # split | full-graphic
    x: int
    y: int
    w: int               # clip pixel size == the canvas (the panel is baked in)
    h: int
    start: float         # cut-time seconds, frame-quantized
    end: float
    media_duration: float
    canvas_w: int
    canvas_h: int

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 6)


def build_placements(
    spec: VisualsSpec,
    windows: List[BeatWindow],
    clips_dir: str | Path,
    fps: int = 30,
) -> Tuple[List[VisualPlacement], List[str]]:
    """Placements for the remotion beats that have a window, plus editor notes."""
    by_id = {w.beat_id: w for w in windows}
    placed: List[VisualPlacement] = []
    notes: List[str] = []
    for beat in spec.beats:
        if beat.generator in ("real", "higgsfield"):
            notes.append(f"{beat.id}: {beat.generator} asset {beat.asset} — place by hand "
                         f"({beat.layout})")
            continue
        if beat.generator != "remotion":
            continue
        win = by_id.get(beat.id)
        if win is None:
            notes.append(f"{beat.id}: no window on the cut (dropped by the rough cut) — not placed")
            continue
        media = clip_duration_s(beat)
        start, end = quantize(win.start, fps), quantize(win.end, fps)
        if end - start > media + 1e-9:
            notes.append(f"{beat.id}: window {end - start:.2f}s is longer than the rendered "
                         f"clip ({media:.2f}s) — trimmed; raise duration_s and re-render to fill it")
            end = quantize(start + media, fps)
        name = clip_name(spec.reel_id, beat.id, ext="")
        placed.append(VisualPlacement(
            beat_id=beat.id, name=name, src=str(Path(clips_dir) / clip_name(spec.reel_id, beat.id)),
            layout=beat.layout, x=0, y=0, w=spec.width, h=spec.height,
            start=start, end=end,
            media_duration=media, canvas_w=spec.width, canvas_h=spec.height,
        ))
    return placed, notes
