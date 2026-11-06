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
from .layout import fit_title, fits_line
from .text import phrase_span, words
from .timing import MAX_TOTAL_S, beat_duration_s

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
            dur = beat_duration_s(b["text"], b.get("duration_s"))
            beat = KineticBeat(
                id=b["id"], kind="text", start_s=t, duration_s=dur, text=b["text"],
                role=b["role"], motion=b["motion"], slot=b.get("slot", "top"),
                align=b.get("align", "left"), voice=b.get("voice", "contrast"),
                accents=_accents(b.get("accents", ())),
            )
        else:
            dur = float(b["duration_s"])
            beat = KineticBeat(id=b["id"], kind="space", start_s=t, duration_s=dur)
        beats.append(beat)
        t += dur
    return beats


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

    if "duration_s" in b:
        computed = beat_duration_s(text)
        if b["duration_s"] + 1e-9 < MIN_OVERRIDE_FRACTION * computed:
            raise KineticSpecError(
                f"beats/{i}/duration_s: {b['duration_s']} s is faster than twice reading pace "
                f"(this line needs at least {MIN_OVERRIDE_FRACTION * computed:.2f} s)")


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
