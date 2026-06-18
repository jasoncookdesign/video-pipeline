"""Crop plan -> FFmpeg command.

Pure string/argument assembly (no subprocess here, so it is unit-testable).
``probe.py`` runs the returned argv. A static plan becomes a single
``crop=...,scale=...`` filter; a dynamic plan becomes a time-keyed ``crop`` whose
``x`` is a piecewise expression over ``t`` (FFmpeg evaluates per frame).
"""

from __future__ import annotations

from typing import List

from .plan import CropPlan


def _scale_filter(out_w: int, out_h: int) -> str:
    return f"scale={out_w}:{out_h}:flags=lanczos"


def static_filtergraph(plan: CropPlan) -> str:
    w = plan.windows[0]
    return (
        f"crop={w.w}:{w.h}:{w.x}:{w.y},"
        f"{_scale_filter(plan.out_w, plan.out_h)}"
    )


def dynamic_filtergraph(plan: CropPlan) -> str:
    """Piecewise-constant x(t) crop. Each window holds its x until the next."""
    ws = plan.windows
    h = ws[0].h
    cw = ws[0].w
    y = ws[0].y
    # build nested if() expression: if(lt(t,t1), x0, if(lt(t,t2), x1, ... xN))
    expr = str(ws[-1].x)
    for w in reversed(ws[:-1]):
        expr = f"if(lt(t\\,{w.t_end:.3f})\\,{w.x}\\,{expr})"
    return (
        f"crop=w={cw}:h={h}:x='{expr}':y={y},"
        f"{_scale_filter(plan.out_w, plan.out_h)}"
    )


def filtergraph(plan: CropPlan) -> str:
    if plan.mode == "static" or len(plan.windows) == 1:
        return static_filtergraph(plan)
    return dynamic_filtergraph(plan)


def ffmpeg_crop_command(
    input_path: str,
    output_path: str,
    plan: CropPlan,
    crf: int = 18,
    preset: str = "medium",
) -> List[str]:
    """Assemble the FFmpeg argv that renders the reframed vertical video.

    Audio is stream-copied (the reframe is a spatial-only operation; no
    speech-based edits happen here — that is the rough-cut phase).
    """
    return [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vf", filtergraph(plan),
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]
