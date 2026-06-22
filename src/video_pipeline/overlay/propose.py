"""Transcript→window proposer — the overlay's AI leverage (INI-089). Pure.

The mechanical cost of an overlay is deciding **when** it is on screen, frame-
matched to the narration. The word-level transcript already exists (rough cut /
captions), so the pipeline proposes each overlay's ``[start, end)`` by matching it
to the span where it is discussed and writes that into ``overlay.def``; the CEO
nudges it. This proposer is the matching logic — deterministic, no model in the
render path. It serves every producer: an image/video overlay (Phase A) and a
source card (Phase B) all get their window from here.

Matching strategy (deterministic, explainable):
  1. **Phrase match** — the query's tokens appearing consecutively (normalized,
     punctuation-insensitive) in the transcript. The tightest, most precise window.
  2. **Keyword fallback** — if the exact phrase is not present, the smallest window
     covering the query's distinctive keywords within one sentence-ish cluster.

Returns a padded ``(start, end)`` in **source-time seconds** (the overlay.def
timebase) or ``None`` when nothing matches (the caller leaves the window to manual
placement rather than guessing).
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from ..roughcut.transcript import Transcript, Word

# Very common words carry no locating signal — ignored when keyword-matching so
# "the chart" locates on "chart", not on every "the".
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "this", "that", "it", "with", "at", "as", "by", "be",
}


def _tokens(text: str) -> List[str]:
    return [t for t in (re.sub(r"[^a-z0-9']+", "", w.lower()) for w in text.split()) if t]


def _phrase_match(words: Sequence[Word], query: List[str]) -> Optional[Tuple[int, int]]:
    """Index span [i, j] of the first consecutive run of ``query`` in ``words``."""
    n, m = len(words), len(query)
    if m == 0:
        return None
    norm = [w.normalized() for w in words]
    for i in range(n - m + 1):
        if norm[i : i + m] == query:
            return (i, i + m - 1)
    return None


def _keyword_match(
    words: Sequence[Word], query: List[str], *, max_gap_s: float
) -> Optional[Tuple[int, int]]:
    """Smallest index span covering the query's keywords within one cluster.

    Stopwords are dropped from the query. Walks the transcript collecting matched
    keyword positions, breaking the run when a gap longer than ``max_gap_s``
    separates two words (a sentence boundary heuristic), and returns the span of the
    cluster that covers the most distinct keywords (ties → earliest).
    """
    keywords = {t for t in query if t not in _STOPWORDS} or set(query)
    if not keywords:
        return None
    norm = [w.normalized() for w in words]

    best: Optional[Tuple[int, int, int]] = None  # (distinct_hits, -start, ...) tracked below
    best_span: Optional[Tuple[int, int]] = None
    cluster_start = 0
    hits: List[int] = []

    def consider(start_idx: int, idxs: List[int]):
        nonlocal best, best_span
        if not idxs:
            return
        distinct = len({norm[k] for k in idxs})
        span = (idxs[0], idxs[-1])
        if best is None or distinct > best[0]:
            best = (distinct, span[0], span[1])
            best_span = span

    for i in range(len(words)):
        if i > 0 and (words[i].start - words[i - 1].end) > max_gap_s:
            consider(cluster_start, hits)
            cluster_start = i
            hits = []
        if norm[i] in keywords:
            hits.append(i)
    consider(cluster_start, hits)
    return best_span


def propose_window(
    transcript: Transcript,
    query: str,
    *,
    pad_lead: float = 0.0,
    pad_tail: float = 0.0,
    min_duration: float = 0.0,
    max_gap_s: float = 0.6,
) -> Optional[Tuple[float, float]]:
    """Propose ``(start, end)`` source-time seconds for an overlay about ``query``.

    Tries an exact phrase match first, then a keyword-cluster fallback. The matched
    word span's times are padded by ``pad_lead`` / ``pad_tail`` and clamped to the
    transcript bounds, and stretched (symmetrically, within bounds) to at least
    ``min_duration`` so a one-word match still yields a watchable window. Returns
    ``None`` if nothing matches.
    """
    words = transcript.words
    if not words:
        return None
    q = _tokens(query)
    if not q:
        return None

    span = _phrase_match(words, q) or _keyword_match(words, q, max_gap_s=max_gap_s)
    if span is None:
        return None

    i, j = span
    start = words[i].start - pad_lead
    end = words[j].end + pad_tail

    lo, hi = words[0].start, words[-1].end
    start = max(lo, start)
    end = min(hi, end)

    if min_duration > 0 and (end - start) < min_duration:
        deficit = min_duration - (end - start)
        start = max(lo, start - deficit / 2.0)
        end = min(hi, start + min_duration)
        start = max(lo, end - min_duration)  # re-balance if we hit the upper bound

    return (round(start, 3), round(end, 3))
