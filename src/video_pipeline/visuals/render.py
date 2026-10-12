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

    @property
    def width(self) -> int:
        return self.props["dimensions"]["width"]

    @property
    def height(self) -> int:
        return self.props["dimensions"]["height"]


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
        jobs.append(
            RenderJob(
                beat_id=beat.id,
                template=beat.template,
                composition=TEMPLATE_COMPOSITIONS[beat.template],
                output=output,
                props_path=output.with_suffix(".props.json"),
                props=beat_to_remotion_props(spec, beat, style),
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
