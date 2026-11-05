"""``kinetic-render`` — render a kinetic.json to one canvas-sized alpha layer.

Plan (pure) -> props JSON -> ``npx remotion render KineticText`` (the same argv
builder the caption overlay uses) -> optional still previews grabbed off the
layer with the caption-preview FFmpeg seam, composited over a neutral plate. The
layer is canvas-sized, so no padding pass is needed. The process runner is
injectable (``run``) so the suite stubs Node/FFmpeg; by default it is
:func:`subprocess.run`, looked up at call time.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from ..captions.preview import DEFAULT_PREVIEW_BG, frame_extract_command
from ..captions.remotion import REMOTION_DIR, remotion_render_command
from .props import COMPOSITION, clip_name, kinetic_to_remotion_props
from .spec import KineticSpec

# Stills are taken this fraction of the way through each text beat, after its
# entrance has settled and before its exit begins.
STILL_FRACTION = 0.7


@dataclass
class KineticRenderJob:
    composition: str
    output: Path
    props_path: Path
    props: dict


def still_times(spec: KineticSpec) -> List[float]:
    """One still time per text beat, after the beat has settled and before it ends."""
    return [round(b.start_s + STILL_FRACTION * b.duration_s, 3) for b in spec.text_beats()]


def plan_render(spec: KineticSpec, out_dir, style) -> KineticRenderJob:
    output = Path(out_dir) / clip_name(spec.reel_id)
    return KineticRenderJob(
        composition=COMPOSITION,
        output=output,
        props_path=output.with_suffix(".props.json"),
        props=kinetic_to_remotion_props(spec, style),
    )


def render_kinetic(
    spec: KineticSpec,
    out_dir,
    style,
    *,
    stills: bool = False,
    frames_dir=None,
    dry_run: bool = False,
    run: Optional[Callable] = None,
    remotion_dir: Optional[str] = None,
    preview_bg: Optional[str] = None,
) -> dict:
    """Render the layer (+ one still per text beat with ``stills``).

    Returns ``composition``, ``output``, ``props``, ``width``, ``height``,
    ``argv`` (the Remotion command) and ``frames`` (still PNG paths). With
    ``dry_run`` nothing is written or spawned.
    """
    rdir = Path(remotion_dir) if remotion_dir else REMOTION_DIR
    if not dry_run and not (rdir / "package.json").exists():
        raise RuntimeError(f"Remotion project not found at {rdir}; run `npm install` there once.")
    runner = run or subprocess.run
    job = plan_render(spec, out_dir, style)
    argv = remotion_render_command(
        str(job.props_path), str(job.output), composition=job.composition, remotion_dir=str(rdir))
    if not dry_run:
        job.output.parent.mkdir(parents=True, exist_ok=True)
        job.props_path.write_text(json.dumps(job.props, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
        runner(argv, check=True, cwd=str(rdir))

    pngs: List[str] = []
    if stills:
        fdir = Path(frames_dir) if frames_dir else Path(out_dir) / "frames"
        for i, t in enumerate(still_times(spec)):
            png = fdir / f"{job.output.stem}-s{i + 1}-{t:.2f}s.png"
            cmd = frame_extract_command(str(job.output), t, str(png), spec.width, spec.height,
                                        preview_bg or DEFAULT_PREVIEW_BG)
            if not dry_run:
                png.parent.mkdir(parents=True, exist_ok=True)
                runner(cmd, check=True)
            pngs.append(str(png))

    return {
        "composition": job.composition,
        "output": str(job.output),
        "props": str(job.props_path),
        "width": spec.width,
        "height": spec.height,
        "argv": argv,
        "frames": pngs,
    }
