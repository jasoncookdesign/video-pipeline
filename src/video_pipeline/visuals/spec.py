"""visuals.json — the per-Reel visual track spec, validated at the Python boundary.

The contract is ``schema/visuals.schema.json`` (owned here; the reels plugin pins a
copy and writes against it). This module is the boundary: it validates a spec
against that schema — including each template's props contract — plus the one
rule JSON Schema cannot express (beat ids unique ignoring case), and returns typed objects.
Nothing downstream (props builder, renderer, handoff) re-validates; a spec that
loads is a spec the renderer can render.

Errors are :class:`VisualsSpecError` with the JSON path of the offending value
(``beats/3/props/price``) so a hand-edited or plugin-written file points straight
at what to fix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

# Repo root -> schema/. parents: visuals -> video_pipeline -> src -> repo root.
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "visuals.schema.json"

LAYOUTS = ("split", "full-graphic", "full-presenter")
GENERATORS = ("remotion", "higgsfield", "real", "none")


class VisualsSpecError(ValueError):
    """A visuals.json that does not satisfy the contract."""


@dataclass(frozen=True)
class Beat:
    """One beat of the visual track (see the schema for field meanings)."""

    id: str
    spoken: str
    duration_s: float
    layout: str
    generator: str
    template: Optional[str] = None
    props: dict = field(default_factory=dict)
    asset: Optional[str] = None
    parody: bool = False
    notes: str = ""


@dataclass
class VisualsSpec:
    """A validated visuals.json."""

    reel_id: str
    fps: int
    width: int
    height: int
    layout: str
    regions_version: str
    regions: dict
    beats: List[Beat]
    identity: Optional[str] = None
    title: str = ""

    def remotion_beats(self) -> List[Beat]:
        """The beats ``visuals-render`` renders, in spec order."""
        return [b for b in self.beats if b.generator == "remotion"]


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _path(error) -> str:
    return "/".join(str(p) for p in error.absolute_path) or "<root>"


def _deepest(error):
    """Descend into ``context`` sub-errors (if/then/allOf) to the most specific one."""
    while error.context:
        error = max(error.context, key=lambda e: len(e.absolute_path))
    return error


def validate_visuals_dict(data: dict) -> None:
    """Raise :class:`VisualsSpecError` unless ``data`` satisfies the contract."""
    import jsonschema

    if not isinstance(data, dict):
        raise VisualsSpecError("visuals.json must be a JSON object")
    validator = jsonschema.Draft7Validator(load_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: (list(e.absolute_path), e.message))
    if errors:
        lines = []
        for err in errors[:8]:
            leaf = _deepest(err)
            lines.append(f"{_path(leaf)}: {leaf.message}")
        more = f" (+{len(errors) - 8} more)" if len(errors) > 8 else ""
        raise VisualsSpecError("invalid visuals.json — " + "; ".join(lines) + more)

    seen = set()
    for i, beat in enumerate(data["beats"]):
        key = beat["id"].casefold()  # ids name clip files; APFS is case-insensitive
        if key in seen:
            raise VisualsSpecError(f"beats/{i}/id: duplicate beat id {beat['id']!r} (ids compare ignoring case)")
        seen.add(key)


def parse_visuals(data: dict) -> VisualsSpec:
    """Validate ``data`` and build a :class:`VisualsSpec`."""
    validate_visuals_dict(data)
    beats = [
        Beat(
            id=b["id"],
            spoken=b["spoken"],
            duration_s=float(b["duration_s"]),
            layout=b["layout"],
            generator=b["generator"],
            template=b.get("template"),
            props=b.get("props", {}),
            asset=b.get("asset"),
            parody=bool(b.get("parody", False)),
            notes=b.get("notes", ""),
        )
        for b in data["beats"]
    ]
    canvas = data["canvas"]
    return VisualsSpec(
        reel_id=data["reel_id"],
        fps=int(canvas["fps"]),
        width=int(canvas["w"]),
        height=int(canvas["h"]),
        layout=data["layout"],
        regions_version=data["regions_version"],
        regions=data["regions"],
        beats=beats,
        identity=data.get("identity"),
        title=data.get("title", ""),
    )


def load_visuals(path) -> VisualsSpec:
    """Read + validate a visuals.json file."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VisualsSpecError(f"{p}: not valid JSON ({exc})") from None
    return parse_visuals(data)
