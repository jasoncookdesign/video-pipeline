"""Rough-cut proposal — pure, fully unit-tested.

Given a word-level ``Transcript``, the clip ``duration``, and a ``ProposeConfig``,
produce a ``DecisionList`` that partitions ``[0, duration]`` end-to-end into
KEEP / DROP segments. The machine removes three classes of mechanical waste —
**filler** words, **false starts**, and **dead air** — and keeps everything else;
taste stays with the CEO.

The ``rough_cut.trim_filler`` toggle is honored at the top: when it is ``False``
the proposal makes **no speech-based edits** — a single whole-clip KEEP segment,
preserving audio continuity (e.g. a Radio DJ record showcase recorded live off
the mixer, where cutting on speech would break the mix). This is the behaviour
the initiative DoD checks.

No I/O, no FFmpeg, no native deps here — just timestamps in, a decision list out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Tuple

from .decision import DecisionList, Segment
from .transcript import Transcript, Word

# Conservative, high-precision filler lexicon. Words like "like" / "so" / "you
# know" are intentionally excluded — they are too often content, and a false cut
# is worse than a missed one (the CEO can always tighten further by hand).
FILLER_WORDS: FrozenSet[str] = frozenset(
    {"um", "umm", "uh", "uhh", "uhm", "er", "err", "erm", "ah", "ahh",
     "eh", "hmm", "mm", "mmm", "mhm"}
)

# Reason labels (also used as DROP `reason` values in the decision file).
R_FILLER = "filler"
R_FALSE_START = "false-start"
R_SILENCE = "silence"


@dataclass(frozen=True)
class ProposeConfig:
    trim_filler: bool = True
    filler_words: FrozenSet[str] = FILLER_WORDS
    extra_filler_words: FrozenSet[str] = frozenset()
    silence_gap_s: float = 0.6        # inter-word gap above this => dead air
    keep_pad_lead_s: float = 0.06     # padding kept BEFORE speech at each cut
    keep_pad_tail_s: float = 0.15     # padding kept AFTER speech (Whisper clips ends early)
    detect_false_starts: bool = True
    false_start_max_gap_s: float = 0.5  # adjacent repeat within this gap => restart

    def all_filler(self) -> FrozenSet[str]:
        return self.filler_words | self.extra_filler_words


@dataclass
class _Marker:
    start: float
    end: float
    reason: str


# ── word labelling ────────────────────────────────────────────────────────────

def _label_words(words: List[Word], cfg: ProposeConfig) -> List[Optional[str]]:
    """Per-word drop reason (None = keep). Filler takes precedence over repeat."""
    fillers = cfg.all_filler()
    labels: List[Optional[str]] = [None] * len(words)

    for i, w in enumerate(words):
        if w.normalized() in fillers:
            labels[i] = R_FILLER

    if cfg.detect_false_starts:
        for i in range(len(words) - 1):
            if labels[i] is not None:
                continue
            a, b = words[i], words[i + 1]
            na = a.normalized()
            if not na:
                continue
            gap = b.start - a.end
            # an immediately-repeated token within a tight window = a restart;
            # drop the FIRST (abandoned) utterance, keep the clean repeat.
            if na == b.normalized() and gap <= cfg.false_start_max_gap_s:
                labels[i] = R_FALSE_START

    return labels


# ── run building ──────────────────────────────────────────────────────────────

def _keep_runs(
    words: List[Word], labels: List[Optional[str]], cfg: ProposeConfig
) -> List[Tuple[float, float]]:
    """Maximal runs of kept words with no dropped word and no >gap silence inside.

    A dropped word closes the current run (its time becomes a DROP region); a
    gap larger than ``silence_gap_s`` also closes it (the gap becomes silence).
    """
    runs: List[Tuple[float, float]] = []
    run_start: Optional[float] = None
    run_end: Optional[float] = None

    for w, label in zip(words, labels):
        if label is not None:  # dropped word breaks the run
            if run_start is not None:
                runs.append((run_start, run_end))
                run_start = run_end = None
            continue
        if run_start is None:
            run_start, run_end = w.start, w.end
        else:
            if w.start - run_end <= cfg.silence_gap_s:
                run_end = max(run_end, w.end)
            else:  # dead-air gap splits the run
                runs.append((run_start, run_end))
                run_start, run_end = w.start, w.end

    if run_start is not None:
        runs.append((run_start, run_end))
    return runs


def _pad_runs(
    runs: List[Tuple[float, float]], duration: float, cfg: ProposeConfig
) -> List[Tuple[float, float]]:
    """Expand each run by the lead/tail pads without overlapping a neighbour or clip.

    The tail pad is larger than the lead pad by default because Whisper word-end
    timestamps tend to land slightly early — a bigger tail keeps word endings from
    being clipped at a cut.
    """
    padded: List[Tuple[float, float]] = []
    for idx, (a, b) in enumerate(runs):
        lo_bound = runs[idx - 1][1] if idx > 0 else 0.0
        hi_bound = runs[idx + 1][0] if idx + 1 < len(runs) else duration
        a2 = max(lo_bound, a - cfg.keep_pad_lead_s, 0.0)
        b2 = min(hi_bound, b + cfg.keep_pad_tail_s, duration)
        padded.append((a2, max(a2, b2)))
    return padded


def _drop_markers(words: List[Word], labels: List[Optional[str]]) -> List[_Marker]:
    return [
        _Marker(w.start, w.end, label)
        for w, label in zip(words, labels)
        if label is not None
    ]


def _region_reason(start: float, end: float, markers: List[_Marker]) -> str:
    """Reason for a DROP region: dominant overlapping dropped-word reason, else silence."""
    reasons = {
        m.reason for m in markers if m.start < end and m.end > start
    }
    if R_FILLER in reasons:
        return R_FILLER
    if R_FALSE_START in reasons:
        return R_FALSE_START
    return R_SILENCE


# ── public API ────────────────────────────────────────────────────────────────

def propose(
    transcript: Transcript,
    duration: Optional[float] = None,
    config: Optional[ProposeConfig] = None,
    source: str = "",
    profile: Optional[str] = None,
) -> DecisionList:
    """Propose a rough cut as a ``DecisionList`` partitioning the whole clip.

    ``duration`` defaults to the transcript's last word end. When
    ``config.trim_filler`` is False, the result is a single whole-clip KEEP
    segment (no speech-based edits). With an empty transcript the whole clip is
    kept (nothing can be trimmed with confidence).
    """
    cfg = config or ProposeConfig()
    words = list(transcript.words)
    dur = float(duration) if duration is not None else transcript.duration
    dur = max(dur, words[-1].end if words else 0.0)

    def _whole_clip_keep() -> DecisionList:
        seg = Segment(
            index=0, start=0.0, end=dur, keep=True, reason="",
            text=transcript.text(),
        )
        return DecisionList(
            source=source, segments=[seg], profile=profile,
            trim_filler=cfg.trim_filler, duration=dur,
        )

    if not cfg.trim_filler or not words:
        return _whole_clip_keep()

    labels = _label_words(words, cfg)
    runs = _pad_runs(_keep_runs(words, labels, cfg), dur, cfg)

    if not runs:  # everything was filler/false-start — don't emit an empty cut
        return _whole_clip_keep()

    markers = _drop_markers(words, labels)
    segments: List[Segment] = []
    cursor = 0.0
    idx = 0

    def _emit(start: float, end: float, keep: bool):
        nonlocal idx
        if end - start <= 1e-6:
            return
        reason = "" if keep else _region_reason(start, end, markers)
        segments.append(
            Segment(
                index=idx, start=start, end=end, keep=keep, reason=reason,
                text=transcript.text_between(start, end),
            )
        )
        idx += 1

    for a, b in runs:
        if a > cursor:
            _emit(cursor, a, keep=False)   # dropped: filler / false-start / silence
        _emit(a, b, keep=True)             # kept content
        cursor = b
    if cursor < dur:
        _emit(cursor, dur, keep=False)     # trailing dead air

    return DecisionList(
        source=source, segments=segments, profile=profile,
        trim_filler=cfg.trim_filler, duration=dur,
    )
