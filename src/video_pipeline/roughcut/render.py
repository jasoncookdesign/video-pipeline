"""Decision list -> FFmpeg rough-cut command.

Pure string/argument assembly (no subprocess here, so it is unit-testable);
``runner.py`` runs the returned argv. The rough cut is the concatenation of the
decision list's KEEP segments, in order, built with a ``filter_complex`` of
per-segment ``trim`` / ``atrim`` pairs feeding ``concat`` — frame-accurate and
free of the keyframe-snapping the concat *demuxer* would introduce.

This is a **rough** render (re-encode is fine and expected): it exists only to
preview the decision file. ``source/`` is never modified — the input is read,
the cut is written elsewhere (``work/``). Editing the decision file and
re-running this is the round-trip the initiative DoD checks.
"""

from __future__ import annotations

from typing import List

from .decision import DecisionList, Segment


def concat_filtergraph(segments: List[Segment]) -> str:
    """Build the filter_complex string for the kept segments (in order).

    Each kept segment becomes a trimmed + PTS-reset video/audio pair; the pairs
    are concatenated. Raises ValueError if there is nothing to keep.
    """
    if not segments:
        raise ValueError("no kept segments to render")

    parts: List[str] = []
    labels: List[str] = []
    for i, s in enumerate(segments):
        parts.append(
            f"[0:v]trim=start={s.start:.3f}:end={s.end:.3f},"
            f"setpts=PTS-STARTPTS[v{i}]"
        )
        parts.append(
            f"[0:a]atrim=start={s.start:.3f}:end={s.end:.3f},"
            f"asetpts=PTS-STARTPTS[a{i}]"
        )
        labels.append(f"[v{i}][a{i}]")

    n = len(segments)
    parts.append(f"{''.join(labels)}concat=n={n}:v=1:a=1[outv][outa]")
    return ";".join(parts)


def ffmpeg_roughcut_command(
    input_path: str,
    output_path: str,
    decision: DecisionList,
    crf: int = 20,
    preset: str = "veryfast",
    audio_bitrate: str = "192k",
) -> List[str]:
    """Assemble the FFmpeg argv that renders the rough cut from ``decision``.

    Only KEEP segments are rendered (the whole point of the decision file). The
    rough cut re-encodes (libx264 + AAC) because trim/concat cuts on arbitrary
    frames; a faster preset is used since this is a throwaway preview, not the
    final master.
    """
    kept = decision.kept()
    if not kept:
        raise ValueError(
            "decision list has no KEEP segments — nothing to render "
            "(flip `keep: true` on at least one segment)"
        )

    filtergraph = concat_filtergraph(kept)
    return [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-filter_complex", filtergraph,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        output_path,
    ]
