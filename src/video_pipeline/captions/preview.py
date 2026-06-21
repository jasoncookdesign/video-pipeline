"""Caption preview-frame seam (INI-088 Phase 1) — the verification loop.

The JasonOS sandbox cannot render Remotion (network allowlist blocks npm + the
Chromium headless shell), so styling defects can only be caught by rendering on
the Mac and reading the result back. This module is that seam: after the daily-
driver Remotion render produces the transparent overlay ``.mov``, it grabs a
handful of representative still frames — each composited over a neutral
background so the fill, stroke, and (Phase 2) background plate are all visible —
and writes them as PNGs the President Agent reads in-session to confirm styling.

Split like the rest of the captions phase: the frame-time selection and the
FFmpeg argv builder are **pure and unit-tested**; only :func:`extract_preview_frames`
shells out and is daily-driver-bound.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Tuple

# Mid-gray reads both the white fill and the black stroke of the default style.
DEFAULT_PREVIEW_BG = "#808080"


def preview_frame_times(props: dict, n: int) -> List[float]:
    """Pick ``n`` representative still timestamps (seconds) from a props object.

    One frame per evenly-spaced kept cue, sampled at the cue's temporal midpoint
    so the caption is fully on screen (not mid-fade at an edge). ``n`` is clamped
    to the number of cues; ``n <= 0`` or no cues yields an empty list. Returned
    sorted and de-duplicated.
    """
    cues = props.get("cues", [])
    if not cues or n <= 0:
        return []
    n = min(n, len(cues))
    if n == 1:
        idxs = [len(cues) // 2]
    else:
        idxs = [round(i * (len(cues) - 1) / (n - 1)) for i in range(n)]
    times = []
    for i in idxs:
        c = cues[i]
        times.append(round((c["startSeconds"] + c["endSeconds"]) / 2.0, 3))
    return sorted(set(times))


def frame_extract_command(
    overlay_path: str,
    time_s: float,
    out_png: str,
    width: int,
    height: int,
    background: str = DEFAULT_PREVIEW_BG,
) -> List[str]:
    """Build the FFmpeg argv that grabs one frame of the overlay at ``time_s``,
    composited over a solid ``background`` plate, to ``out_png``. Pure — no
    process is spawned.

    Input 0 is the overlay seeked to ``time_s``; input 1 is a synthetic color
    source the overlay is laid over (so the transparent .mov reads against a
    neutral field instead of an undefined alpha background).
    """
    return [
        "ffmpeg",
        "-y",
        "-ss",
        f"{time_s:.3f}",
        "-i",
        str(Path(overlay_path)),
        "-f",
        "lavfi",
        "-i",
        f"color=c={background}:s={width}x{height}:d=0.1",
        "-filter_complex",
        "[1:v][0:v]overlay=0:0:format=auto",
        "-frames:v",
        "1",
        str(Path(out_png)),
    ]


def extract_preview_frames(  # pragma: no cover - daily-driver: needs FFmpeg + a real .mov
    overlay_path: str,
    times: List[float],
    out_dir: str,
    width: int,
    height: int,
    background: str = DEFAULT_PREVIEW_BG,
    dry_run: bool = False,
) -> List[Tuple[str, List[str]]]:
    """Grab a still for each time in ``times`` to ``out_dir`` (created if absent).

    Returns ``[(png_path, argv), ...]``. With ``dry_run`` the commands are built
    and returned but not executed.
    """
    out = Path(out_dir)
    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)
    results: List[Tuple[str, List[str]]] = []
    for i, t in enumerate(times):
        png = str(out / f"preview-{i:02d}-{t:.3f}s.png")
        cmd = frame_extract_command(overlay_path, t, png, width, height, background)
        if not dry_run:
            subprocess.run(cmd, check=True)
        results.append((png, cmd))
    return results
