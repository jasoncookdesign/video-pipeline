"""Run the composite ffmpeg command (daily-driver glue; argv lives in render.py).

Kept thin and side-effect-only so the interesting logic (argv assembly) stays in
the pure, unit-tested ``render`` module.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Sequence

from .render import ffmpeg_composite_command


def render_composite(
    base_path: str,
    overlay_paths: Sequence[str],
    output_path: str,
    *,
    crf: int = 18,
    preset: str = "medium",
    dry_run: bool = False,
) -> List[str]:
    """Build, and unless ``dry_run`` run, the composite render. Returns the argv.

    ``output_path`` is a fresh file (``review/composite.mp4``), never the base, so
    no in-place temp dance is needed (unlike reframe/roughcut, which rewrite the
    base channel). The parent directory is created if missing.
    """
    cmd = ffmpeg_composite_command(
        base_path, list(overlay_paths), output_path, crf=crf, preset=preset
    )
    if dry_run:
        return cmd
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    return cmd
