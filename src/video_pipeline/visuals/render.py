"""``visuals-render`` — render each Remotion beat to a named, region-sized clip.

Plan (pure) → props JSON per clip → ``npx remotion render <Composition>`` (the
same argv builder the caption overlay uses) → optional still previews grabbed off
each clip with the caption-preview FFmpeg seam, composited over a neutral plate.

Non-Remotion beats (``real`` / ``higgsfield`` / ``none``) are skipped. The process
runner is injectable (``run``) so the suite stubs Node/FFmpeg; on the daily driver
it is :func:`subprocess.run`.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from ..captions.preview import DEFAULT_PREVIEW_BG, frame_extract_command
from ..captions.remotion import REMOTION_DIR, remotion_render_command
from .props import (
    TEMPLATE_COMPOSITIONS,
    beat_to_remotion_props,
    clip_name,
)
from .regions import clip_geometry
from .spec import VisualsSpec
from .style import VisualStyle


@dataclass
class RenderJob:
    beat_id: str
    template: str
    composition: str
    output: Path
    props_path: Path
    props: dict
    x: int          # where the rendered panel sits on the canvas
    y: int
    canvas_w: int
    canvas_h: int

    @property
    def panel_width(self) -> int:
        return self.props["dimensions"]["width"]

    @property
    def panel_height(self) -> int:
        return self.props["dimensions"]["height"]

    @property
    def width(self) -> int:
        """Final clip width: every visual clip is canvas-sized."""
        return self.canvas_w

    @property
    def height(self) -> int:
        return self.canvas_h

    @property
    def needs_padding(self) -> bool:
        return (self.panel_width, self.panel_height) != (self.canvas_w, self.canvas_h)


def pad_to_canvas_command(src, dst, *, x, y, canvas_w, canvas_h) -> List[str]:
    """FFmpeg argv that places a clip at ``(x, y)`` on a transparent canvas.

    The clip keeps its alpha (ProRes 4444), so a split-layout graphic comes out as
    a canvas-sized clip with the top panel filled and the rest transparent. The
    editor then drops it on the timeline with no position transform, which every
    NLE places identically.
    """
    return [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", f"pad={canvas_w}:{canvas_h}:{x}:{y}:color=0x00000000",
        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
        "-an", str(dst),
    ]


def still_times(duration_s: float, fps: int, n: int) -> List[float]:
    """``n`` still timestamps across a beat, the last on its settled final frame.

    Evenly spaced at ``duration_s * k / n`` for k = 1..n, with the last pulled back
    one frame so it lands inside the beat (animations have settled by then).
    """
    if n <= 0:
        return []
    last = duration_s - 1.0 / fps
    times = [min(duration_s * k / n, last) for k in range(1, n + 1)]
    return sorted({round(t, 3) for t in times})


def plan_render(
    spec: VisualsSpec,
    out_dir: str | Path,
    style: VisualStyle,
    only: Optional[Iterable[str]] = None,
) -> List[RenderJob]:
    """One :class:`RenderJob` per remotion beat (optionally filtered by beat id)."""
    out = Path(out_dir)
    keep = set(only) if only else None
    if keep is not None:
        unknown = keep - {b.id for b in spec.remotion_beats()}
        if unknown:
            raise ValueError(f"no remotion beat with id {', '.join(sorted(unknown))} in {spec.reel_id}")
    jobs: List[RenderJob] = []
    for beat in spec.remotion_beats():
        if keep is not None and beat.id not in keep:
            continue
        name = clip_name(spec.reel_id, beat.id)
        output = out / name
        placement = clip_geometry(beat.layout, spec.regions).placement
        jobs.append(
            RenderJob(
                beat_id=beat.id,
                template=beat.template,
                composition=TEMPLATE_COMPOSITIONS[beat.template],
                output=output,
                props_path=output.with_suffix(".props.json"),
                props=beat_to_remotion_props(spec, beat, style),
                x=placement.x, y=placement.y,
                canvas_w=spec.width, canvas_h=spec.height,
            )
        )
    return jobs


def render_visuals(
    spec: VisualsSpec,
    out_dir: str | Path,
    style: VisualStyle,
    *,
    frames: int = 0,
    frames_dir: Optional[str | Path] = None,
    only: Optional[Iterable[str]] = None,
    dry_run: bool = False,
    run: Callable = subprocess.run,
    remotion_dir: Optional[str] = None,
    preview_bg: str = DEFAULT_PREVIEW_BG,
) -> List[dict]:
    """Render every planned clip (+ ``frames`` stills each). Returns one result per clip.

    Each result: ``beat_id``, ``template``, ``composition``, ``output``, ``props``,
    ``width``, ``height``, ``argv`` (the Remotion command), and ``frames`` (still
    PNG paths). With ``dry_run`` nothing is written or spawned.
    """
    rdir = Path(remotion_dir) if remotion_dir else REMOTION_DIR
    if not dry_run and not (rdir / "package.json").exists():
        raise RuntimeError(f"Remotion project not found at {rdir}; run `npm install` there once.")
    fdir = Path(frames_dir) if frames_dir else Path(out_dir)
    results: List[dict] = []
    for job in plan_render(spec, out_dir, style, only=only):
        argv = remotion_render_command(
            str(job.props_path), str(job.output),
            composition=job.composition, remotion_dir=str(rdir),
        )
        if not dry_run:
            job.output.parent.mkdir(parents=True, exist_ok=True)
            job.props_path.write_text(json.dumps(job.props, indent=2, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
            run(argv, check=True, cwd=str(rdir))
            if job.needs_padding:
                staged = job.output.with_name(job.output.stem + ".canvas.mov")
                run(pad_to_canvas_command(job.output, staged, x=job.x, y=job.y,
                                          canvas_w=job.canvas_w, canvas_h=job.canvas_h),
                    check=True)
                os.replace(staged, job.output)

        beat_s = job.props["beatFrames"] / spec.fps
        pngs: List[str] = []
        for i, t in enumerate(still_times(beat_s, spec.fps, frames)):
            png = fdir / f"{job.output.stem}-f{i + 1}-{t:.2f}s.png"
            fcmd = frame_extract_command(str(job.output), t, str(png),
                                         job.width, job.height, preview_bg)
            if not dry_run:
                png.parent.mkdir(parents=True, exist_ok=True)
                run(fcmd, check=True)
            pngs.append(str(png))

        results.append({
            "beat_id": job.beat_id,
            "template": job.template,
            "composition": job.composition,
            "output": str(job.output),
            "props": str(job.props_path),
            "width": job.width,
            "height": job.height,
            "argv": argv,
            "frames": pngs,
        })
    return results
