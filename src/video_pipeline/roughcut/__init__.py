"""Rough-cut phase.

Turns a transcript into the **editable decision file** — the product of this
phase — and renders a regenerable rough cut from it. Taste (pacing, the comedic
pause) stays with the editor; the machine does mechanical labor: dropping filler,
false starts, and dead air.

Layering mirrors the reframe phase:

  - ``transcript`` — a ``Transcriber`` Protocol seam (mlx-whisper behind it on the
    local machine; ``FixedTranscriber`` in tests) + word-level timestamp model.
  - ``propose``    — pure: transcript + duration + config -> a full-timeline
    partition of KEEP/DROP segments, honoring ``rough_cut.trim_filler``.
  - ``decision``   — the decision file (``Segment`` / ``DecisionList``), a clean
    YAML round-trip. Editing an entry and re-rendering changes the cut.
  - ``render``     — pure: a ``DecisionList`` -> an FFmpeg ``trim``/``concat``
    argv (kept segments only; ``source/`` is never modified).
  - ``runner``     — local glue (transcribe -> propose -> write -> render).

Only ``runner`` and the mlx-whisper transcriber need native deps / footage; the
rest is pure and unit-tested in the test suite.
"""

from __future__ import annotations

from .decision import DecisionList, Segment
from .propose import ProposeConfig, FILLER_WORDS, propose
from .render import ffmpeg_roughcut_command, concat_filtergraph
from .transcript import (
    FixedTranscriber,
    SilenceTranscriber,
    Transcriber,
    Transcript,
    Word,
    parse_silencedetect,
    speech_regions,
    transcript_from_speech_regions,
    transcript_from_whisper_dict,
)

__all__ = [
    "DecisionList",
    "Segment",
    "ProposeConfig",
    "FILLER_WORDS",
    "propose",
    "ffmpeg_roughcut_command",
    "concat_filtergraph",
    "FixedTranscriber",
    "SilenceTranscriber",
    "Transcriber",
    "Transcript",
    "Word",
    "parse_silencedetect",
    "speech_regions",
    "transcript_from_speech_regions",
    "transcript_from_whisper_dict",
]
