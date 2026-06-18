"""Transcription seam — word-level timestamps behind a Protocol.

A ``Transcriber`` reads an audio/video file and returns a ``Transcript`` of
words with start/end timestamps. Implementations sit behind the ``Transcriber``
Protocol so the rough-cut proposal logic never depends on a particular engine.

One real implementation ships:

  - ``MLXWhisperTranscriber`` — Apple-Silicon (MLX) Whisper with word-level
    timestamps. The chosen primary transcriber: local-first, native fit for the
    M4 Pro daily driver, no per-minute cost, nothing leaves the machine. Lazy
    import; daily-driver only (the ``[roughcut]`` extra). WhisperX / ElevenLabs
    Scribe are deferred alternatives that would slot in behind this same seam.

Tests use ``FixedTranscriber`` and need no native build. ``transcript_from_
whisper_dict`` parses any Whisper-shaped result (segments[].words[]) so a
precomputed transcript JSON in ``work/`` can be loaded without MLX present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence


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
