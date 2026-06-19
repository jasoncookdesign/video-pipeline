"""Transcription seam — word-level timestamps behind a Protocol.

A ``Transcriber`` reads an audio/video file and returns a ``Transcript`` of
words with start/end timestamps. Implementations sit behind the ``Transcriber``
Protocol so the rough-cut proposal logic never depends on a particular engine.

Two real implementations ship:

  - ``MLXWhisperTranscriber`` — Apple-Silicon (MLX) Whisper with word-level
    timestamps. The chosen primary transcriber: local-first, native fit for the
    M4 Pro daily driver, no per-minute cost, nothing leaves the machine. Lazy
    import; daily-driver only (the ``[roughcut]`` extra). WhisperX / ElevenLabs
    Scribe are deferred alternatives that would slot in behind this same seam.

  - ``SilenceTranscriber`` — an offline fallback with NO ASR: FFmpeg
    ``silencedetect`` gives speech/silence boundaries, emitted as one marker word
    per speech region. The proposer then trims **dead air only** (filler /
    false-start detection needs real words). Runs anywhere with an FFmpeg binary
    — including the JasonOS sandbox, where mlx-whisper is unavailable.

Tests use ``FixedTranscriber`` and need no native build. ``transcript_from_
whisper_dict`` parses any Whisper-shaped result (segments[].words[]) so a
precomputed transcript JSON in ``work/`` can be loaded without MLX present.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, Tuple


@dataclass(frozen=True)
class Word:
    """One transcribed word with source-time boundaries (seconds)."""

    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def normalized(self) -> str:
        """Lowercase, punctuation-stripped token for filler/repeat matching."""
        return re.sub(r"[^a-z0-9']+", "", self.text.lower())


@dataclass(frozen=True)
class Transcript:
    """An ordered word sequence. ``language`` is advisory."""

    words: tuple
    language: Optional[str] = None

    def __post_init__(self):
        # accept any sequence; freeze to a tuple of Word
        object.__setattr__(self, "words", tuple(self.words))

    @property
    def duration(self) -> float:
        return self.words[-1].end if self.words else 0.0

    def text(self) -> str:
        return " ".join(w.text for w in self.words).strip()

    def text_between(self, start: float, end: float) -> str:
        """Transcript text whose word centre falls within [start, end)."""
        out = []
        for w in self.words:
            mid = (w.start + w.end) / 2.0
            if start <= mid < end:
                out.append(w.text)
        return " ".join(out).strip()


class Transcriber(Protocol):
    def transcribe(self, media_path: str) -> Transcript:
        ...


class FixedTranscriber:
    """Deterministic transcriber for tests/fallback: replays supplied words."""

    def __init__(self, words: Sequence[Word], language: Optional[str] = None):
        self._transcript = Transcript(tuple(words), language=language)

    def transcribe(self, media_path: str) -> Transcript:
        return self._transcript


# ── silence-based fallback (no ASR) ───────────────────────────────────────────

def parse_silencedetect(stderr_text: str) -> List[Tuple[float, Optional[float]]]:
    """Parse FFmpeg ``silencedetect`` log lines into (start, end) silence pairs.

    Lines look like ``silence_start: 0.315`` / ``silence_end: 1.751 | ...``. A
    trailing ``silence_start`` with no matching ``silence_end`` (silence running
    to EOF) yields ``(start, None)`` — resolved to the clip duration later.
    """
    silences: List[Tuple[float, Optional[float]]] = []
    cur_start: Optional[float] = None
    for line in stderr_text.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            cur_start = float(m.group(1))
            continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)", line)
        if m and cur_start is not None:
            silences.append((cur_start, float(m.group(1))))
            cur_start = None
    if cur_start is not None:
        silences.append((cur_start, None))
    return silences


def speech_regions(
    silences: List[Tuple[float, Optional[float]]],
    duration: float,
    min_speech_s: float = 0.0,
) -> List[Tuple[float, float]]:
    """Complement of the silence intervals within ``[0, duration]``.

    ``None`` silence-ends resolve to ``duration``. Speech regions shorter than
    ``min_speech_s`` are discarded (detection noise) — their time falls back into
    surrounding silence and is trimmed as dead air.
    """
    regions: List[Tuple[float, float]] = []
    cursor = 0.0
    for s, e in silences:
        s = max(0.0, min(s, duration))
        e = duration if e is None else max(0.0, min(e, duration))
        if s > cursor:
            regions.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        regions.append((cursor, duration))
    if min_speech_s > 0:
        regions = [(a, b) for a, b in regions if (b - a) >= min_speech_s]
    return regions


def transcript_from_speech_regions(
    regions: List[Tuple[float, float]], language: str = "und"
) -> Transcript:
    """One marker word per speech region. Markers are numbered (``[speech 1]``,
    ``[speech 2]``, ...) so they are distinct — adjacent regions never collide as
    a false-start, and the proposer trims only the silence between them."""
    words = [
        Word(text=f"[speech {i + 1}]", start=round(a, 3), end=round(b, 3))
        for i, (a, b) in enumerate(regions)
    ]
    return Transcript(tuple(words), language=language)


class SilenceTranscriber:
    """Offline, ASR-free fallback transcriber via FFmpeg ``silencedetect``.

    No model, no network — runs anywhere with FFmpeg/ffprobe (incl. the JasonOS
    sandbox, where mlx-whisper is unavailable). Returns one marker word per
    detected speech region, so the proposer trims **dead air only**; filler and
    false-start removal still require a real word-level transcript (mlx-whisper
    on the daily driver). The pure parsing/region helpers are unit-tested; only
    the FFmpeg/ffprobe calls here are daily-driver/binary-bound.
    """

    def __init__(
        self,
        noise_db: float = -30.0,
        min_silence_s: float = 0.6,
        min_speech_s: float = 0.0,
    ):
        self.noise_db = noise_db
        self.min_silence_s = min_silence_s
        self.min_speech_s = min_speech_s

    def _duration(self, media_path: str) -> float:  # pragma: no cover - needs ffprobe + a file
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", media_path],
            capture_output=True, text=True, check=True,
        ).stdout
        return float(json.loads(out).get("format", {}).get("duration", 0.0) or 0.0)

    def transcribe(self, media_path: str) -> Transcript:  # pragma: no cover - runs ffmpeg
        af = f"silencedetect=noise={self.noise_db}dB:d={self.min_silence_s}"
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", media_path,
             "-af", af, "-f", "null", "-"],
            capture_output=True, text=True,
        )
        silences = parse_silencedetect(proc.stderr)
        duration = self._duration(media_path)
        regions = speech_regions(silences, duration, self.min_speech_s)
        return transcript_from_speech_regions(regions)


def transcript_from_whisper_dict(data: dict) -> Transcript:
    """Build a Transcript from a Whisper-shaped result dict.

    Accepts the common shape produced by whisper / mlx-whisper / WhisperX with
    ``word_timestamps=True``::

        {"language": "en",
         "segments": [{"words": [{"word": " Hey", "start": 0.0, "end": 0.4}, ...]}]}

    Falls back to a top-level ``words`` list if present. Word keys may be
    ``word`` or ``text``; missing timestamps are skipped.
    """
    language = data.get("language")
    raw_words: List[dict] = []

    if isinstance(data.get("words"), list):
        raw_words = data["words"]
    else:
        for seg in data.get("segments") or []:
            for w in seg.get("words") or []:
                raw_words.append(w)

    words: List[Word] = []
    for w in raw_words:
        text = (w.get("word") if "word" in w else w.get("text")) or ""
        text = text.strip()
        if not text:
            continue
        start = w.get("start")
        end = w.get("end")
        if start is None or end is None:
            continue
        words.append(Word(text=text, start=float(start), end=float(end)))

    return Transcript(tuple(words), language=language)


class MLXWhisperTranscriber:
    """Local Apple-Silicon Whisper (MLX) with word-level timestamps.

    Daily-driver only — needs ``mlx-whisper`` (the ``[roughcut]`` extra) and an
    Apple-Silicon machine. Lazy import keeps the sandbox suite free of native
    deps; ``transcript_from_whisper_dict`` does the shared parsing.
    """

    DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"

    def __init__(self, model: Optional[str] = None, language: Optional[str] = None):
        self.model = model or self.DEFAULT_MODEL
        self.language = language

    def transcribe(self, media_path: str) -> Transcript:  # pragma: no cover - native deps + footage
        try:
            import mlx_whisper
        except ImportError as exc:
            raise RuntimeError(
                "MLXWhisperTranscriber requires `mlx-whisper` (the `[roughcut]` "
                "extra) on an Apple-Silicon machine."
            ) from exc

        result = mlx_whisper.transcribe(
            media_path,
            path_or_hf_repo=self.model,
            word_timestamps=True,
            language=self.language,
        )
        return transcript_from_whisper_dict(result)
