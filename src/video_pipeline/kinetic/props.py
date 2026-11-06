"""Spec -> Remotion props for the KineticText composition.

``remotion/src/kinetic/types.ts`` mirrors :func:`kinetic_to_remotion_props`
(``schemaVersion`` 2). Everything is resolved here so the composition does no text
analysis or timing arithmetic: each beat starts where the previous one ended, the
last beat ends at the clip's final frame, and every word carries its own style and
entrance, exit, and treatment frames (:mod:`video_pipeline.kinetic.voice`).
"""

from __future__ import annotations

from ..visuals.style import MIN_TYPE_PX, VisualStyle
from .layout import FULL_SAFE, PAD, ROLE_PX, TITLE_BLOCK_H, TITLE_GAP, fit_title  # noqa: F401  (re-exported)
from .spec import KineticSpec
from .voice import plan_motion

KINETIC_PROPS_SCHEMA_VERSION = 3
COMPOSITION = "KineticText"
CLIP_EXT = ".mov"

def clip_name(reel_id: str, ext: str = CLIP_EXT) -> str:
    """``<reel_id>-kinetic.mov``."""
    return f"{reel_id}-kinetic{ext}"


def _box(x: int, y: int, w: int, h: int) -> dict:
    return {"x": x, "y": y, "width": w, "height": h}


def kinetic_to_remotion_props(spec: KineticSpec, style: VisualStyle) -> dict:
    x, y, w, h = FULL_SAFE
    fps = spec.fps
    total_frames = round(spec.total_s * fps)
    last = len(spec.beats) - 1
    beats = []
    for i, b in enumerate(spec.beats):
        start = round(b.start_s * fps)
        end = round(spec.beats[i + 1].start_s * fps) if i < last else total_frames
        entry = {
            "id": b.id,
            "kind": b.kind,
            "from": start,
            "durationInFrames": end - start,
            "holdToEnd": i == last and b.kind == "text",
        }
        if b.kind == "text":
            plan = plan_motion(b, end - start, fps, entry["holdToEnd"])
            entry.update(
                text=b.text, role=b.role, motion=b.motion, exitMotion=b.exit.motion, slot=b.slot, align=b.align,
                sizePx=b.size_px, revealFrames=plan.reveal_frames,
                exitFrames=plan.exit_frames, driftPx=plan.drift_px,
                lineHeights=plan.line_heights, blockHeight=plan.block_height,
                words=[
                    {"text": w.text, "family": w.family, "weight": w.weight, "italic": w.italic,
                     "scale": w.scale, "color": w.color, "treatment": w.treatment, "keep": w.keep,
                     "inFrom": t.in_from, "inFrames": t.in_frames,
                     "outFrom": t.out_from, "outFrames": t.out_frames,
                     "treatFrom": t.treat_from, "treatFrames": t.treat_frames, "line": ln,
                     "pushes": [list(p) for p in t.pushes]}
                    for w, t, ln in zip(plan.words, plan.timings, plan.lines)
                ],
            )
        beats.append(entry)
    body_y = y + TITLE_BLOCK_H + TITLE_GAP
    # The body container is as tall as the tallest block and sits at the bottom of the
    # safe zone; every block starts at the container's top (its slot says otherwise).
    tallest = max((e["blockHeight"] for e in beats if e["kind"] == "text"), default=0)
    container = _box(x + PAD, y + h - PAD - tallest, w - 2 * PAD, tallest)
    title_px = fit_title(spec.title, min(style.title_px + 48, 160), MIN_TYPE_PX["title_px"])
    return {
        "schemaVersion": KINETIC_PROPS_SCHEMA_VERSION,
        "kind": "kinetic",
        "reelId": spec.reel_id,
        "fps": fps,
        "durationInFrames": total_frames,
        "dimensions": {"width": spec.width, "height": spec.height},
        "safeBox": _box(x, y, w, h),
        "titleBox": _box(x, y, w, TITLE_BLOCK_H),
        "bodyBox": _box(x, body_y, w, y + h - body_y),
        "bodyContainer": container,
        "style": style.to_dict(),
        "minType": dict(MIN_TYPE_PX),
        "title": spec.title,
        "titlePx": title_px,
        "beats": beats,
    }
