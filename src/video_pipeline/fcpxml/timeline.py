"""The cut timeline + source->cut time remap. Pure, fully unit-tested.

The rough-cut **decision file** removes interior segments, so the handoff
timeline is *compressed* relative to the source: a KEEP segment at source
``[3.0, 5.0)`` may sit at cut time ``[1.2, 3.2)`` once the dead air before it is
dropped. Two things follow:

  1. **The base cut** is the KEEP segments laid end-to-end. Each becomes its own
     timeline clip (a separate clip so the editor can drop a transition between
     cuts), with a frame-quantized timeline ``offset`` = the cumulative kept
     duration before it and a source in-point = the segment's ``start``.

  2. **Captions must move with the cut.** Caption cues are timed against the
     *source*; on the compressed timeline they would drift. :func:`source_to_cut`
     maps a source time onto the cut timeline, and :func:`remap_track` rebuilds
     the caption track in cut time — dropping cues that fall entirely in removed
     regions and clipping cues that straddle a cut boundary. The remapped track
     re-renders to an overlay that lines up with the base cut.

Everything is quantized to the frame grid (``fps``) so the FCPXML times are
exact frame multiples and the base cut and caption overlay stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..captions.cue import CaptionTrack, Cue
from ..roughcut.decision import DecisionList, Segment


def quantize(t: float, fps: int) -> float:
    """Snap a time to the nearest frame boundary at ``fps`` (seconds)."""
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps!r}")
    return round(round(float(t) * fps) / fps, 6)


def to_frames(t: float, fps: int) -> int:
    """Frame index for a time (rounded to the nearest frame)."""
    return int(round(float(t) * fps))


@dataclass(frozen=True)
class BaseClip:
    """One KEEP segment placed on the cut timeline.

    ``source_in`` / ``source_out`` are the in/out points into the (reframed)
    source asset; ``offset`` is the clip's position on the cut timeline; all are
    frame-quantized seconds. ``duration`` = ``source_out - source_in``.
    """

    index: int
    source_in: float
    source_out: float
    offset: float
    text: str = ""

    @property
    def duration(self) -> float:
        return round(self.source_out - self.source_in, 6)


@dataclass(frozen=True)
class KeptSpan:
    """A kept source span and where it lands on the cut timeline."""

    src_start: float
    src_end: float
    cut_start: float

    @property
    def cut_end(self) -> float:
        return round(self.cut_start + (self.src_end - self.src_start), 6)


def build_base_cut(decision: DecisionList, fps: int = 30) -> List[BaseClip]:
    """Lay the decision file's KEEP segments end-to-end on the cut timeline.

    Each kept segment becomes a :class:`BaseClip` with a frame-quantized source
    in/out and a cumulative timeline offset. Raises ``ValueError`` if nothing is
    kept (mirrors the rough-cut renderer — there is no cut to hand off).
    """
    kept = decision.kept()
    if not kept:
        raise ValueError(
            "decision file has no KEEP segments — nothing to assemble "
            "(flip `keep: true` on at least one segment)"
        )
    clips: List[BaseClip] = []
    offset = 0.0
    for i, seg in enumerate(kept):
        src_in = quantize(seg.start, fps)
        src_out = quantize(seg.end, fps)
        if src_out <= src_in:  # a sub-frame segment after quantization — skip it
            continue
        clips.append(
            BaseClip(
                index=i,
                source_in=src_in,
                source_out=src_out,
                offset=round(offset, 6),
                text=seg.text,
            )
        )
        offset = round(offset + (src_out - src_in), 6)
    if not clips:
        raise ValueError("decision file KEEP segments are all sub-frame — nothing to assemble")
    return clips


def kept_spans(decision: DecisionList, fps: int = 30) -> List[KeptSpan]:
    """The KEEP segments as (source span -> cut position) spans, for remapping."""
    spans: List[KeptSpan] = []
    cut = 0.0
    for clip in build_base_cut(decision, fps):
        spans.append(KeptSpan(clip.source_in, clip.source_out, round(cut, 6)))
        cut = round(cut + clip.duration, 6)
    return spans


def cut_duration(spans: List[KeptSpan]) -> float:
    """Total length of the cut timeline."""
    return spans[-1].cut_end if spans else 0.0


def source_to_cut(spans: List[KeptSpan], t: float) -> float:
    """Map a source time onto the cut timeline.

    A time inside a kept span maps linearly into it. A time in a *dropped* region
    snaps forward to the head of the next kept span (so a cue boundary that lands
    in trimmed dead air clamps to the adjacent kept content). A time past the end
    clamps to the cut end.
    """
    if not spans:
        return 0.0
    for span in spans:
        if t < span.src_start:
            return span.cut_start
        if t <= span.src_end:
            return round(span.cut_start + (t - span.src_start), 6)
    return cut_duration(spans)


def _overlaps_kept(spans: List[KeptSpan], start: float, end: float) -> bool:
    """True if [start, end) intersects any kept span (with positive overlap)."""
    for span in spans:
        if min(end, span.src_end) - max(start, span.src_start) > 1e-9:
            return True
    return False


def remap_cue(
    spans: List[KeptSpan], cue: Cue, fps: int = 30
) -> Optional[Cue]:
    """Rebuild one cue in cut time, or ``None`` if it falls in a dropped region.

    The cue is clipped to the kept content it overlaps; per-word timings (for the
    karaoke highlight) are shifted by the same mapping and dropped if any word
    leaves the kept content (the renderer then even-splits). A cue with no kept
    overlap returns ``None``.
    """
    if not _overlaps_kept(spans, cue.start, cue.end):
        return None
    cut_start = quantize(source_to_cut(spans, cue.start), fps)
    cut_end = quantize(source_to_cut(spans, cue.end), fps)
    if cut_end - cut_start < 1.0 / fps:  # collapsed below one frame after clipping
        return None

    word_times: List[tuple] = []
    if cue.word_times and len(cue.word_times) == len(cue.words):
        ok = True
        for ws, we in cue.word_times:
            if not _overlaps_kept(spans, ws, we):
                ok = False
                break
            word_times.append(
                (
                    quantize(source_to_cut(spans, ws), fps),
                    quantize(source_to_cut(spans, we), fps),
                )
            )
        if not ok:
            word_times = []

    return Cue(
        index=cue.index,
        start=cut_start,
        end=cut_end,
        words=list(cue.words),
        emphasis=list(cue.emphasis),
        keep=cue.keep,
        word_times=word_times,
    )


def remap_track(
    track: CaptionTrack, decision: DecisionList, fps: int = 30
) -> CaptionTrack:
    """Rebuild a caption track in cut time against a decision file.

    Only kept cues are considered; each is remapped via :func:`remap_cue`. Cues
    that fall entirely in dropped regions are omitted; survivors are reindexed in
    time order. The result renders to an overlay aligned to the base cut.

    When ``trim_filler: false`` (the decision file is a single whole-clip KEEP),
    the mapping is the identity and the track passes through unchanged in timing.
    """
    spans = kept_spans(decision, fps)
    out: List[Cue] = []
    for cue in track.kept():
        remapped = remap_cue(spans, cue, fps)
        if remapped is not None:
            out.append(remapped)
    new = CaptionTrack(
        source=track.source,
        cues=out,
        identity=track.identity,
        profile=track.profile,
        style_ref=track.style_ref,
        language=track.language,
        karaoke=track.karaoke,
    )
    return new.reindex()
