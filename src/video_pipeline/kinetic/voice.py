"""Per-word voicing and motion plan for a text beat.

Python resolves everything the composition needs per word — weight, italic, size
factor, color, entrance and exit frames, accent treatment — so the composition
renders what it is given and does no text analysis or timing arithmetic.

The plan follows three ideas: a line is revealed clause by clause (every word of a
clause arrives together, so the eye takes in a unit of meaning) instead of arriving
as one block or one word at a time; the whole line drifts a little while it reveals,
counterbalancing the clauses that appear one after another; and an accent word gets
its own follow-up move once it has arrived. A clause is a run of words ending at
clause punctuation; the ``phrase`` field numbers them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Tuple

from .layout import FAMILY_FOR_ROLE, LINE_HEIGHT, ROLE_PX, line_width, text_width_em
from .linebreak import Unit, break_units
from .spec import KineticBeat
from .text import STOPWORDS, authored_lines, is_function_word, norm_token, phrase_indices, phrase_span, words

# Clause entrance length (s), the share of the beat spent revealing, the shortest
# fully visible hold, and the exit length.
WORD_ANIM_S = 0.5
REVEAL_FRACTION = 0.55
MIN_HOLD_S = 0.6
EXIT_S = 0.4
# Phrase-to-phrase offset of the exit (s), at most.
EXIT_PHRASE_STEP_S = 0.08
# Fewest frames any word animation (entrance or exit) may take.
MIN_ANIM_FRAMES = 4
MIN_EXIT_WORD_FRAMES = 3
# Sideways drift of the whole line while it reveals (px); right-aligned text drifts the other way.
DRIFT_PX = 40
# A whip leans its word over the next one; the words after it on the line slide over
# by this share of the leaning word's size so the lean never touches them.
WHIP_PUSH_EM = 0.15
# Share of a scatter clause's exit that the next clause overlaps.
SCATTER_OVERLAP = 0.6
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
    pushes: Tuple[Tuple[int, int, int], ...] = ()   # (from frame, frames, px): slides over as an earlier whip leans


@dataclass(frozen=True)
class BeatMotion:
    words: List[Word]
    timings: List[WordTiming]
    reveal_frames: int   # when the last word has finished arriving
    exit_frames: int
    drift_px: int
    lines: List[int]          # line number of each word
    line_heights: List[int]   # px, one per line
    block_height: int         # px, the sum of the line heights


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


def break_into_lines(beat: KineticBeat, ws: List[Word]) -> List[int]:
    """Line number of each word. Lines the author broke with newlines are kept exactly;
    otherwise the breaker chooses: clauses kept whole where they fit, no one-word lines,
    lines of similar length (:mod:`video_pipeline.kinetic.linebreak`). The words of
    one accent stay on one line."""
    authored = authored_lines(beat.text)
    if authored is not None:    # the author broke the lines: keep them exactly
        return [n for n, line in enumerate(authored) for _ in line]
    px = ROLE_PX[beat.role]
    space = text_width_em(" ", FAMILY_FOR_ROLE[beat.role]) * px
    units: List[Unit] = []
    members: List[int] = []     # first word of each unit
    for i, w in enumerate(ws):
        width = text_width_em(w.text, w.family) * px * w.scale
        if i > 0 and ws[i - 1].keep:
            u = units[-1]
            units[-1] = Unit(u.width + space + width, u.words + 1, w.phrase, is_function_word(w.text))
        else:
            units.append(Unit(width, 1, w.phrase, is_function_word(w.text)))
            members.append(i)
    unit_lines = break_units(units, space, line_width(beat.role))
    lines: List[int] = []
    for i in range(len(ws)):
        k = max(j for j, first in enumerate(members) if first <= i)
        lines.append(unit_lines[k])
    return lines


def line_heights(beat: KineticBeat, ws: List[Word], lines: List[int]) -> List[int]:
    """Height of each line in px: the role's pitch, or the biggest accent on the line if taller."""
    px = ROLE_PX[beat.role]
    out = []
    for ln in range(max(lines) + 1 if lines else 0):
        scale = max(w.scale for w, k in zip(ws, lines) if k == ln)
        out.append(round(px * max(LINE_HEIGHT, scale)))
    return out


def plan_motion(beat: KineticBeat, frames: int, fps: int, hold_to_end: bool) -> BeatMotion:
    """Frame-accurate entrance, exit, and treatment timing for every word of ``beat``.

    ``frames`` is the beat's length; ``hold_to_end`` keeps the words on screen to
    the end of the layer (the final text beat) instead of fading them out.
    """
    ws = style_words(beat)
    n = len(ws)
    gradual = beat.exit.motion == "scatter" and not hold_to_end
    default_exit = max(MIN_ANIM_FRAMES, min(round(EXIT_S * fps), frames // 4))
    exit_f = 0 if hold_to_end else (round(beat.exit.duration_s * fps) if gradual else default_exit)
    # time added by a longer exit and a linger is not reveal time: the reveal keeps its reading pace
    extra = (exit_f - default_exit + round(beat.exit.linger_s * fps)) if gradual else 0
    reading_frames = frames - extra
    anim = max(MIN_ANIM_FRAMES, round(WORD_ANIM_S * fps))
    min_hold = round(MIN_HOLD_S * fps)

    reveal = max(round(REVEAL_FRACTION * reading_frames), anim + n - 1)
    reveal = min(reveal, frames - exit_f - min_hold)
    reveal = max(reveal, MIN_ANIM_FRAMES + n - 1)           # never less than a word each frame
    anim = max(MIN_ANIM_FRAMES, min(anim, reveal - (n - 1)))

    n_phrases = ws[-1].phrase + 1 if ws else 1
    budget = reveal - anim                                  # span over which clauses may start
    # a clause starts after the words before it have had their share of the budget,
    # so a longer clause gets proportionally longer to be read
    before = [0] * n_phrases
    for w in ws:
        for k in range(w.phrase + 1, n_phrases):
            before[k] += 1
    clause_start = [round(budget * before[k] / n) for k in range(n_phrases)]

    # exit: phrase by phrase, each word fading over what is left of the exit window
    xs = min(round(EXIT_PHRASE_STEP_S * fps), max(0, (exit_f - MIN_EXIT_WORD_FRAMES) // max(1, n_phrases - 1)))
    # gradual exit: each clause takes most of the exit and the next begins before it ends
    scatter_win = round(exit_f / ((n_phrases - 1) * SCATTER_OVERLAP + 1)) if gradual else 0
    scatter_step = (exit_f - scatter_win) / (n_phrases - 1) if gradual and n_phrases > 1 else 0.0

    timings: List[WordTiming] = []
    for i, w in enumerate(ws):
        in_from = clause_start[w.phrase]
        if hold_to_end:
            out_from, out_frames = frames, 0
        elif gradual:
            out_from = frames - exit_f + round(w.phrase * scatter_step)
            out_frames = frames - out_from if w.phrase == n_phrases - 1 else scatter_win
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

    lines = break_into_lines(beat, ws)
    px = ROLE_PX[beat.role]
    for i, w in enumerate(ws):
        if w.treatment != "whip":
            continue
        push = (timings[i].treat_from, timings[i].treat_frames, round(WHIP_PUSH_EM * px * w.scale))
        for j in range(i + 1, n):
            if lines[j] == lines[i]:
                timings[j] = replace(timings[j], pushes=timings[j].pushes + (push,))

    drift = -DRIFT_PX if beat.align == "right" else DRIFT_PX
    heights = line_heights(beat, ws, lines)
    return BeatMotion(words=ws, timings=timings, reveal_frames=reveal, exit_frames=exit_f, drift_px=drift,
                      lines=lines, line_heights=heights, block_height=sum(heights))
