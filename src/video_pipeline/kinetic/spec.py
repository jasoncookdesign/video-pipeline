"""kinetic.json — the kinetic-text overlay spec, validated at the Python boundary.

The contract is ``schema/kinetic.schema.json``. This module validates a spec
against it plus the rules JSON Schema cannot express (beat ids unique ignoring
case, accent text matching whole consecutive words, word length, override pace,
total length, caption rules), resolves every beat's start and duration, and
returns typed objects. Nothing downstream re-validates.

Errors are :class:`KineticSpecError` with the JSON path of the offending value
(``beats/3/accents/0/text``) so a hand-edited file points straight at what to fix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

from .caption import check_caption
from .layout import BODY_MAX_BLOCK_H, FAMILY_FOR_ROLE, ROLE_PX, fit_title, fits_line, line_width, text_width_em
from .text import authored_lines, phrase_span, words
from .timing import EXIT_DEFAULT_S, SCATTER_DEFAULT_S, MAX_TOTAL_S, SOFT_TOTAL_S, beat_duration_s

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "kinetic.schema.json"

# Longest single word, in characters: beat text, and the (larger, uppercase) title.
MAX_WORD_CHARS = 18
MAX_TITLE_WORD_CHARS = 15
# A duration override may not be faster than this fraction of the reading-pace duration.
MIN_OVERRIDE_FRACTION = 0.5
# The smallest title size the style layer allows (legibility floor).
MIN_TITLE_PX = 72


class KineticSpecError(ValueError):
    """A kinetic.json that does not satisfy the contract."""


@dataclass(frozen=True)
class Accent:
    text: str
    weight: Optional[int] = None
    italic: Optional[bool] = None
    scale: Optional[float] = None
    color: Optional[str] = None
    treatment: Optional[str] = None


@dataclass(frozen=True)
class ExitSpec:
    """How a beat leaves: ``fade`` (quick, clause by clause) or ``scatter`` (gradual: clauses
    drift apart in turn); ``duration_s`` is the length of the exit and ``linger_s`` an extra
    hold of the finished line before it starts."""
    motion: str = "fade"
    duration_s: float = EXIT_DEFAULT_S
    linger_s: float = 0.0


@dataclass(frozen=True)
class KineticBeat:
    id: str
    kind: str                      # "text" | "space"
    start_s: float                 # resolved: cumulative start
    duration_s: float              # resolved: computed or overridden
    text: str = ""
    role: str = ""
    motion: str = ""
    slot: str = "top"
    align: str = "left"
    voice: str = "contrast"
    accents: Tuple[Accent, ...] = ()
    exit: ExitSpec = ExitSpec()


@dataclass
class KineticSpec:
    reel_id: str
    fps: int
    width: int
    height: int
    title: str
    beats: List[KineticBeat]
    identity: Optional[str] = None
    caption: Optional[str] = None
    topic_terms: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_s(self) -> float:
        return sum(b.duration_s for b in self.beats)

    def length_warnings(self) -> List[str]:
        """Non-fatal notes about the spec: a layer over the 60 s guideline."""
        if self.total_s > SOFT_TOTAL_S + 1e-9:
            return [f"total length {self.total_s:.1f}s is over the {SOFT_TOTAL_S:.0f} s guideline "
                    f"(hard limit {MAX_TOTAL_S:.0f} s)"]
        return []

    def text_beats(self) -> List[KineticBeat]:
        return [b for b in self.beats if b.kind == "text"]


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _path(error) -> str:
    return "/".join(str(p) for p in error.absolute_path) or "<root>"


def _deepest(error):
    while error.context:
        error = max(error.context, key=lambda e: len(e.absolute_path))
    return error


def _accents(raw) -> Tuple[Accent, ...]:
    return tuple(
        Accent(text=a["text"], weight=a.get("weight"), italic=a.get("italic"),
               scale=a.get("scale"), color=a.get("color"), treatment=a.get("treatment"))
        for a in raw
    )


def _resolve_beats(data: dict) -> List[KineticBeat]:
    beats: List[KineticBeat] = []
    t = 0.0
    for b in data["beats"]:
        if b["kind"] == "text":
            ex = b.get("exit", {})
            exit_ = ExitSpec(motion=ex.get("motion", "fade"),
                             duration_s=ex.get("duration_s", EXIT_DEFAULT_S if ex.get("motion", "fade") == "fade" else SCATTER_DEFAULT_S),
                             linger_s=ex.get("linger_s", 0.0))
            dur = beat_duration_s(b["text"], b.get("duration_s"),
                                  extra_s=(exit_.duration_s - EXIT_DEFAULT_S) + exit_.linger_s)
            beat = KineticBeat(
                id=b["id"], kind="text", start_s=t, duration_s=dur, text=b["text"],
                role=b["role"], motion=b["motion"], slot=b.get("slot", "top"),
                align=b.get("align", "left"), voice=b.get("voice", "contrast"),
                accents=_accents(b.get("accents", ())), exit=exit_,
            )
        else:
            dur = float(b["duration_s"])
            beat = KineticBeat(id=b["id"], kind="space", start_s=t, duration_s=dur)
        beats.append(beat)
        t += dur
    return beats


def _check_authored_lines(i: int, b: dict, spans: list) -> None:
    """Lines the author broke with newlines must each fit the measure, and no accent may cross a break."""
    lines = authored_lines(b["text"])
    if lines is None:
        return
    scale_of = {}
    for j, span in spans:
        for k in range(*span):
            scale_of[k] = b["accents"][j].get("scale", 1.0)
    family, px, measure = FAMILY_FOR_ROLE[b["role"]], ROLE_PX[b["role"]], line_width(b["role"])
    space = text_width_em(" ", family) * px
    first = 0
    for n, line in enumerate(lines, 1):
        last = first + len(line) - 1
        for j, (a, e) in spans:
            if a <= last < e - 1:
                raise KineticSpecError(
                    f"beats/{i}/accents/{j}: the accent's words cross the line break after line {n}; "
                    "an accent's words stay on one line")
        width = sum(text_width_em(t, family) * px * scale_of.get(first + k, 1.0) for k, t in enumerate(line))
        width += space * (len(line) - 1)
        if width > measure:
            raise KineticSpecError(
                f"beats/{i}/text: line {n} ({' '.join(line)!r}) is {width:.0f} px wide and the measure is "
                f"{measure:.0f} px; break it into shorter lines")
        first = last + 1


def _check_text_beat(i: int, b: dict) -> None:
    text = b["text"]
    for word in words(text):
        if len(word) > MAX_WORD_CHARS:
            raise KineticSpecError(
                f"beats/{i}/text: word {word!r} is {len(word)} characters (limit {MAX_WORD_CHARS})")
        if not fits_line(b["role"], word):
            raise KineticSpecError(
                f"beats/{i}/text: word {word!r} is too wide to fit a line of a {b['role']}")

    spans = []
    for j, accent in enumerate(b.get("accents", ())):
        where = f"beats/{i}/accents/{j}"
        span = phrase_span(text, accent["text"])
        if span is None:
            raise KineticSpecError(
                f"{where}/text: {accent['text']!r} does not occur in the beat text as whole, consecutive words")
        for k, other in spans:
            if span[0] < other[1] and other[0] < span[1]:
                raise KineticSpecError(
                    f"{where}: accent overlaps accent {k} (both cover the same words)")
        spans.append((j, span))
        scale = accent.get("scale", 1.0)
        group = " ".join(words(text)[span[0]:span[1]])  # an accent's words never break across lines
        if not fits_line(b["role"], group, scale):
            raise KineticSpecError(
                f"{where}: {group!r} at scale {scale} is too wide to fit one line of a {b['role']}")
        if accent.get("treatment") == "whip" and accent.get("italic") is True:
            raise KineticSpecError(
                f"{where}: treatment 'whip' produces the italic itself; it cannot be combined with italic: true")

    _check_authored_lines(i, b, spans)

    if "duration_s" in b:
        computed = beat_duration_s(text)
        if b["duration_s"] + 1e-9 < MIN_OVERRIDE_FRACTION * computed:
            raise KineticSpecError(
                f"beats/{i}/duration_s: {b['duration_s']} s is faster than twice reading pace "
                f"(this line needs at least {MIN_OVERRIDE_FRACTION * computed:.2f} s)")


def _check_block_heights(beats: List["KineticBeat"]) -> None:
    """Every text block must fit the body container, which is as tall as the tallest block."""
    from .voice import plan_motion  # voice imports this module

    for i, b in enumerate(beats):
        if b.kind != "text":
            continue
        height = plan_motion(b, max(1, round(b.duration_s * 30)), 30, False).block_height
        if height > BODY_MAX_BLOCK_H:
            raise KineticSpecError(
                f"beats/{i}/text: the laid-out block is {height} px tall and the body container "
                f"holds {BODY_MAX_BLOCK_H} px; shorten the text")


def validate_kinetic_dict(data: dict) -> None:
    """Raise :class:`KineticSpecError` (naming the JSON path) unless ``data``
    satisfies the schema and the rules the schema cannot express."""
    import jsonschema

    if not isinstance(data, dict):
        raise KineticSpecError("kinetic.json must be a JSON object")
    validator = jsonschema.Draft7Validator(load_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: (list(e.absolute_path), e.message))
    if errors:
        lines = [f"{_path(_deepest(e))}: {_deepest(e).message}" for e in errors[:8]]
        more = f" (+{len(errors) - 8} more)" if len(errors) > 8 else ""
        raise KineticSpecError("invalid kinetic.json — " + "; ".join(lines) + more)

    for word in words(data["title"]):
        if len(word) > MAX_TITLE_WORD_CHARS:
            raise KineticSpecError(
                f"title: word {word!r} is {len(word)} characters (limit {MAX_TITLE_WORD_CHARS})")
    if fit_title(data["title"], MIN_TITLE_PX, MIN_TITLE_PX) is None:
        raise KineticSpecError("title: too wide to fit the title block at the minimum title size")

    seen = set()
    for i, beat in enumerate(data["beats"]):
        key = beat["id"].casefold()  # ids are compared ignoring case
        if key in seen:
            raise KineticSpecError(f"beats/{i}/id: duplicate beat id {beat['id']!r} (ids compare ignoring case)")
        seen.add(key)
        if beat["kind"] == "text":
            _check_text_beat(i, beat)

    beats = _resolve_beats(data)
    total = sum(b.duration_s for b in beats)
    if total > MAX_TOTAL_S + 1e-9:
        raise KineticSpecError(
            f"beats: total length {total:.1f}s exceeds the {MAX_TOTAL_S:.0f} s maximum")

    _check_block_heights(beats)

    if "caption" in data:
        problems = check_caption(
            data["caption"], data["title"],
            [b.text for b in beats if b.kind == "text"], data["topic_terms"])
        if problems:
            raise KineticSpecError("caption: " + "; ".join(problems))


def parse_kinetic(data: dict) -> KineticSpec:
    validate_kinetic_dict(data)
    canvas = data["canvas"]
    return KineticSpec(
        reel_id=data["reel_id"],
        fps=int(canvas["fps"]),
        width=int(canvas["w"]),
        height=int(canvas["h"]),
        title=data["title"],
        beats=_resolve_beats(data),
        identity=data.get("identity"),
        caption=data.get("caption"),
        topic_terms=tuple(data.get("topic_terms", ())),
    )


def load_kinetic(path) -> KineticSpec:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KineticSpecError(f"{p}: not valid JSON ({exc})") from None
    return parse_kinetic(data)
