"""Per-word voicing and motion plan for a text beat.

Python resolves everything the composition needs per word — weight, italic, size
factor, color, entrance and exit frames, accent treatment — so the composition
renders what it is given and does no text analysis or timing arithmetic.

The plan follows three ideas: a line is revealed word by word (phrases separated
by a short pause) instead of arriving as one block; the whole line drifts a little
while it reveals, counterbalancing the words that appear one after another; and an
accent word gets its own follow-up move once it has arrived.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .spec import KineticBeat
from .text import STOPWORDS, norm_token, phrase_indices, phrase_span, words

# Word entrance length (s), the share of the beat spent revealing, the pause
# between phrases, the longest gap between two words, the shortest fully visible
# hold, and the exit length.
WORD_ANIM_S = 0.5
REVEAL_FRACTION = 0.55
PHRASE_PAUSE_S = 0.2
MAX_STEP_S = 0.3
MIN_HOLD_S = 0.6
EXIT_S = 0.4
# Phrase-to-phrase offset of the exit (s), at most.
EXIT_PHRASE_STEP_S = 0.08
# Fewest frames any word animation (entrance or exit) may take.
MIN_ANIM_FRAMES = 4
MIN_EXIT_WORD_FRAMES = 3
# Sideways drift of the whole line while it reveals (px); right-aligned text drifts the other way.
DRIFT_PX = 40
TREATMENT_S = {"whip": 0.27, "bloom": 0.47, "swell": 0.4}

# role -> (family, content weight, function weight, even weight)
ROLE_VOICE = {
    "statement": ("display", 700, 400, 600),
    "aside": ("body", 600, 400, 500),
    "question": ("display", 800, 400, 700),
}


@dataclass(frozen=True)
class Word:
    text: str
    phrase: int
    family: str          # "display" | "body"
    weight: int
    italic: bool
    scale: float
    color: str           # "text" | "accent" | "warm" | "dim"
    treatment: str       # "none" | "whip" | "bloom" | "swell"
    keep: bool = False   # no line break between this word and the next (one accent phrase)


@dataclass(frozen=True)
class WordTiming:
    in_from: int         # frames from the beat's start
    in_frames: int
    out_from: int
    out_frames: int      # 0 when the word holds to the end of the layer
    treat_from: int
    treat_frames: int    # 0 when the word has no treatment


@dataclass(frozen=True)
class BeatMotion:
    words: List[Word]
    timings: List[WordTiming]
    reveal_frames: int   # when the last word has finished arriving
    exit_frames: int
    drift_px: int


def style_words(beat: KineticBeat) -> List[Word]:
    """One styled :class:`Word` per whitespace-separated token of the beat's text."""
    tokens = words(beat.text)
    phrases = phrase_indices(tokens)
    family, content_w, function_w, even_w = ROLE_VOICE[beat.role]
    out: List[Word] = []
    for tok, phrase in zip(tokens, phrases):
        if beat.voice == "even":
            weight = even_w
        else:
            weight = function_w if norm_token(tok) in STOPWORDS else content_w
        out.append(Word(text=tok, phrase=phrase, family=family, weight=weight,
                        italic=False, scale=1.0, color="text", treatment="none"))
    for accent in beat.accents:
        span = phrase_span(beat.text, accent.text)
        if span is None:  # unreachable for a validated spec
            continue
        for i in range(*span):
            w = out[i]
            out[i] = Word(
                text=w.text, phrase=w.phrase, family=w.family,
                weight=accent.weight if accent.weight is not None else w.weight,
                italic=accent.italic if accent.italic is not None else w.italic,
                scale=accent.scale if accent.scale is not None else w.scale,
                color=accent.color if accent.color is not None else w.color,
                treatment=accent.treatment if accent.treatment is not None else w.treatment,
                keep=w.keep,
            )
        for i in range(span[0], span[1] - 1):   # the words of one accent stay on one line
            w = out[i]
            out[i] = Word(text=w.text, phrase=w.phrase, family=w.family, weight=w.weight, italic=w.italic,
                          scale=w.scale, color=w.color, treatment=w.treatment, keep=True)
    return out


def plan_motion(beat: KineticBeat, frames: int, fps: int, hold_to_end: bool) -> BeatMotion:
    """Frame-accurate entrance, exit, and treatment timing for every word of ``beat``.

    ``frames`` is the beat's length; ``hold_to_end`` keeps the words on screen to
    the end of the layer (the final text beat) instead of fading them out.
    """
    ws = style_words(beat)
    n = len(ws)
    exit_f = 0 if hold_to_end else max(MIN_ANIM_FRAMES, min(round(EXIT_S * fps), frames // 4))
    anim = max(MIN_ANIM_FRAMES, round(WORD_ANIM_S * fps))
    min_hold = round(MIN_HOLD_S * fps)

    reveal = max(round(REVEAL_FRACTION * frames), anim + n - 1)
    reveal = min(reveal, frames - exit_f - min_hold)
    reveal = max(reveal, MIN_ANIM_FRAMES + n - 1)           # never less than a word each frame
    anim = max(MIN_ANIM_FRAMES, min(anim, reveal - (n - 1)))

    n_phrases = ws[-1].phrase + 1 if ws else 1
    budget = reveal - anim                                  # span over which words may start
    pause = round(PHRASE_PAUSE_S * fps) if n_phrases > 1 else 0
    pauses_total = min(pause * (n_phrases - 1), budget // 4)
    pause = pauses_total // (n_phrases - 1) if n_phrases > 1 else 0
    span = budget - pause * (n_phrases - 1)
    step = min(span / (n - 1), round(MAX_STEP_S * fps)) if n > 1 else 0.0

    # exit: phrase by phrase, each word fading over what is left of the exit window
    xs = min(round(EXIT_PHRASE_STEP_S * fps), max(0, (exit_f - MIN_EXIT_WORD_FRAMES) // max(1, n_phrases - 1)))

    timings: List[WordTiming] = []
    for i, w in enumerate(ws):
        in_from = round(i * step + pause * w.phrase)
        if hold_to_end:
            out_from, out_frames = frames, 0
        else:
            out_from = frames - exit_f + w.phrase * xs
            out_frames = max(MIN_EXIT_WORD_FRAMES, exit_f - w.phrase * xs)
            out_frames = min(out_frames, frames - out_from)
        treat_from = in_from + anim
        treat_frames = 0
        if w.treatment != "none":
            limit = (frames if hold_to_end else out_from) - treat_from
            treat_frames = max(1, min(round(TREATMENT_S[w.treatment] * fps), limit))
        timings.append(WordTiming(in_from=in_from, in_frames=anim, out_from=out_from, out_frames=out_frames,
                                  treat_from=treat_from, treat_frames=treat_frames))

    drift = -DRIFT_PX if beat.align == "right" else DRIFT_PX
    return BeatMotion(words=ws, timings=timings, reveal_frames=reveal, exit_frames=exit_f, drift_px=drift)
