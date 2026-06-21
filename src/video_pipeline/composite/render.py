"""Layer stack -> FFmpeg composite command.

Pure string/argument assembly (no subprocess here, so it is unit-testable);
``runner.py`` runs the returned argv — the same split the rough-cut renderer uses.
The composite flattens the base video and any transparent overlay layers (the
caption .mov, future overlays), stacked bottom-to-top by z-order, into a single
previewable .mp4.

This is a **preview/handoff intermediate** written to ``review/`` — NOT the final
cut (that is ``render/``, filled by the editor from their NLE). ``source/`` and
the layer files are read-only inputs; the composite is written to a fresh path.
"""

from __future__ import annotations

from typing import List, Sequence


def composite_filtergraph(n_overlays: int) -> str:
    """Chain ``overlay`` filters stacking ``n_overlays`` over input 0 (the base).

    Inputs are assumed ordered base, then overlays in low->high z-order, so each
    overlay lands on top of the ones before it. Returns the ``filter_complex``
    string whose final video pad is ``[outv]`` (mapped by the caller). Empty
    string when there are no overlays (the base is mapped directly).
    """
    parts: List[str] = []
    prev = "[0:v]"
    for i in range(1, n_overlays + 1):
        out = "[outv]" if i == n_overlays else f"[ov{i}]"
        # format=auto lets ffmpeg pick yuva/rgba so straight-alpha overlays key
        # cleanly over the base; overlay at 0,0 (layers are full-frame).
        parts.append(f"{prev}[{i}:v]overlay=0:0:format=auto{out}")
        prev = out
    return ";".join(parts)


def ffmpeg_composite_command(
    base_path: str,
    overlay_paths: Sequence[str],
    output_path: str,
    crf: int = 18,
    preset: str = "medium",
    audio_bitrate: str = "192k",
) -> List[str]:
    """Assemble the FFmpeg argv that flattens base + overlays into ``output_path``.

    Overlays are stacked in the given order (low->high z-order) over the base; the
    base's audio is carried through (``0:a?`` — optional, so a silent base still
    renders). With no overlays the base is simply re-encoded (a one-layer
    composite). Re-encodes libx264 + AAC at a quality-biased crf/preset because
    the composite is a deliverable-quality preview, not the rough cut's throwaway.
    """
    if not base_path:
        raise ValueError("composite needs a base video")

    cmd: List[str] = ["ffmpeg", "-y", "-i", base_path]
    for p in overlay_paths:
        cmd += ["-i", p]

    if overlay_paths:
        cmd += [
            "-filter_complex", composite_filtergraph(len(overlay_paths)),
            "-map", "[outv]",
        ]
    else:
        cmd += ["-map", "0:v"]

    cmd += [
        "-map", "0:a?",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        output_path,
    ]
    return cmd
