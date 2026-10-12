"""Beat timing for the handoff (#62 part A). Pure.

Two bases, picked by what the handoff is given:

  - **Durations** (default): beats laid end-to-end from 0 using ``duration_s`` —
    the plan, taken as **cut time** directly (the visuals.json was written for
    the finished Reel). No transcript needed.
  - **Transcript alignment** (``--transcript``): each beat's ``spoken`` line is
    located in the word-level transcript with the overlay window proposer
    (:func:`video_pipeline.overlay.propose.propose_window` — phrase match, then
    keyword cluster), searching only *after* the previous beat so repeated words
    ("Tycoon") cannot pull a beat backward. A beat starts where its line starts
    and runs until the next beat starts (no flicker gaps). Beats whose line is
    not found (or silent beats) follow the previous beat by its planned
    ``duration_s``. These windows are **source time**, so they are remapped to
    the cut with the same kept-span mapping overlays use
    (:func:`remap_windows`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..fcpxml.timeline import kept_spans, quantize, remap_window
from ..overlay.propose import _STOPWORDS, _tokens, propose_window
from ..roughcut.decision import DecisionList
from ..roughcut.transcript import Transcript
from .spec import VisualsSpec


@dataclass(frozen=True)
class BeatWindow:
    """A beat's on-screen window (seconds). ``basis``: duration | transcript | fallback."""

    beat_id: str
    start: float
    end: float
    basis: str


def windows_from_durations(spec: VisualsSpec) -> List[BeatWindow]:
    """Beats end-to-end from 0 by planned duration (cut time)."""
    out: List[BeatWindow] = []
    t = 0.0
    for b in spec.beats:
        end = round(t + b.duration_s, 6)
        out.append(BeatWindow(b.id, round(t, 6), end, "duration"))
        t = end
    return out


# A beat counts as located only on an exact phrase match or when the matched
# window holds at least this share of the line's distinct keywords — a single
# shared word ("festival") must not pin a beat to someone else's line.
MIN_KEYWORD_COVERAGE = 0.5


def _locate(words, spoken: str):
    """(start, end) of ``spoken`` in ``words`` if the match is strong enough."""
    spoken = spoken.replace("\u2019", "'").replace("\u2018", "'")  # typographic quotes
    if not words or not spoken.strip():
        return None
    match = propose_window(Transcript(words=tuple(words)), spoken)
    if match is None:
        return None
    keywords = {t for t in _tokens(spoken) if t not in _STOPWORDS} or set(_tokens(spoken))
    heard = {w.normalized() for w in words if match[0] - 1e-9 <= w.start and w.end <= match[1] + 1e-9}
    if not keywords or len(keywords & heard) / len(keywords) < MIN_KEYWORD_COVERAGE:
        return None
    return match


def windows_from_transcript(spec: VisualsSpec, transcript: Transcript) -> List[BeatWindow]:
    """Align beats to where their lines are spoken (source time; see module doc).

    Pass 1 locates each line, searching only after the previous located line.
    Pass 2 fills the rest: an unlocated beat follows the previous beat by its
    planned duration, but never past the next located beat; a beat squeezed to
    under one frame is dropped. Windows are contiguous (each ends where the next
    starts); the last ends where its line ends, or after its planned duration.
    """
    words = list(transcript.words)
    lo = words[0].start if words else 0.0
    frame = 1.0 / spec.fps
    beats = spec.beats

    matches = []
    search_from = lo
    for b in beats:
        tail = [w for w in words if w.start >= search_from - 1e-9]
        m = _locate(tail, b.spoken)
        matches.append(m)
        if m is not None:
            search_from = m[1]

    starts: List[float] = []
    for i, b in enumerate(beats):
        if matches[i] is not None:
            start = matches[i][0]
        else:
            start = lo if i == 0 else starts[-1] + beats[i - 1].duration_s
            nxt = next((m[0] for m in matches[i + 1:] if m is not None), None)
            if nxt is not None:
                start = min(start, nxt)
        if starts:
            start = max(start, starts[-1])
        starts.append(round(start, 6))

    out: List[BeatWindow] = []
    for i, b in enumerate(beats):
        if i + 1 < len(beats):
            end = starts[i + 1]
        elif matches[i] is not None:
            end = matches[i][1]
        else:
            end = starts[i] + b.duration_s
        if end - starts[i] < frame - 1e-9:
            continue
        basis = "transcript" if matches[i] is not None else "fallback"
        out.append(BeatWindow(b.id, starts[i], round(end, 6), basis))
    return out


def remap_windows(windows: List[BeatWindow], decision: DecisionList, fps: int = 30) -> List[BeatWindow]:
    """Source-time windows → cut time (dropped beats are omitted)."""
    spans = kept_spans(decision, fps)
    out: List[BeatWindow] = []
    for w in windows:
        cut = remap_window(spans, w.start, w.end, fps)
        if cut is not None:
            out.append(BeatWindow(w.beat_id, cut[0], cut[1], w.basis))
    return out


def quantize_windows(windows: List[BeatWindow], fps: int) -> List[BeatWindow]:
    """Snap windows to the frame grid (durations mode), dropping sub-frame ones."""
    out = []
    for w in windows:
        s, e = quantize(w.start, fps), quantize(w.end, fps)
        if e - s >= 1.0 / fps:
            out.append(BeatWindow(w.beat_id, s, e, w.basis))
    return out
