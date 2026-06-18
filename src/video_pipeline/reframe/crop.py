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
    """Piecewise-LINEAR x(t) crop: interpolate between keyframes (no steps).

    Each window is a keyframe (its x at ``t_start``). Between consecutive
    keyframes the crop x ramps linearly; after the last it holds. The x value is
    single-quoted, so commas inside the expression are literal and must NOT also
    be backslash-escaped (doing both corrupts the filter).
    """
    ws = plan.windows
    h = ws[0].h
    cw = ws[0].w
    y = ws[0].y
    max_x = plan.src_w - cw

    kf = [(w.t_start, w.x) for w in ws]
    if len(kf) == 1:
        expr = str(kf[0][1])
    else:
        expr = str(kf[-1][1])  # hold after the last keyframe
        for i in range(len(kf) - 2, -1, -1):
            t0, x0 = kf[i]
            t1, x1 = kf[i + 1]
            dt = t1 - t0
            if dt <= 1e-6:
                seg = str(x1)
            else:
                # x0 + (x1-x0)*(t-t0)/dt  -> linear ramp over [t0, t1]
                seg = f"({x0}+({x1 - x0})*(t-{t0:.3f})/{dt:.3f})"
            expr = f"if(lt(t,{t1:.3f}),{seg},{expr})"
        expr = f"clip({expr},0,{max_x})"  # belt-and-suspenders: stay in frame

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
