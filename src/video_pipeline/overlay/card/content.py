"""CardContent — the reviewable, editable source-card product (INI-089 Phase B).

A card shows a heading, a short body, a footer, an optional image, and a citation.
This is the *content* half of the content-vs-look split: a small JSON document the
CEO can edit before rendering (fix a clumsy auto-summary, trim the body, swap the
image), mirroring ``overlay.def`` / ``caption.def``. The deterministic Remotion
``Card`` component renders whatever this holds; the look lives there, not here.

The round-trip is lossless: :meth:`CardContent.from_json` parses exactly what
:meth:`CardContent.to_json` writes, so a hand-edited card file loads back cleanly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

CARD_CONTENT_VERSION = "1.0"

# Soft caps — the structuring transform trims to these; over-long hand-edited text
# is allowed (the renderer ellipsizes) so an edit is never rejected for length.
DEFAULT_MAX_BODY_CHARS = 280
DEFAULT_MAX_HEADING_CHARS = 120


@dataclass
class CardContent:
    """The text/image a source card displays.

    ``heading`` is required (a card with no headline is not a card). ``body`` is the
    short supporting text; ``footer`` is attribution/date/byline; ``image`` is an
    optional path or URL to the card's image; ``citation`` is the short source label
    shown on the card (e.g. ``"nytimes.com"``); ``source_url`` is the provenance of
    the capture (kept for traceability, not necessarily shown).
    """

    heading: str
    body: str = ""
    footer: str = ""
    image: Optional[str] = None
    citation: str = ""
    source_url: str = ""

    def __post_init__(self):
        self.heading = (self.heading or "").strip()
        self.body = (self.body or "").strip()
        self.footer = (self.footer or "").strip()
        self.citation = (self.citation or "").strip()
        self.source_url = (self.source_url or "").strip()
        if self.image is not None:
            self.image = self.image.strip() or None
        if not self.heading:
            raise ValueError("card content needs a non-empty heading")

    def to_dict(self) -> dict:
        return {
            "card_content_version": CARD_CONTENT_VERSION,
            "heading": self.heading,
            "body": self.body,
            "footer": self.footer,
            "image": self.image,
            "citation": self.citation,
            "source_url": self.source_url,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, d: dict) -> "CardContent":
        return cls(
            heading=str(d.get("heading", "")),
            body=str(d.get("body", "") or ""),
            footer=str(d.get("footer", "") or ""),
            image=(str(d["image"]) if d.get("image") else None),
            citation=str(d.get("citation", "") or ""),
            source_url=str(d.get("source_url", "") or ""),
        )

    @classmethod
    def from_json(cls, text: str) -> "CardContent":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("card content did not parse to an object")
        return cls.from_dict(data)

    def write(self, path) -> None:
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def read(cls, path) -> "CardContent":
        from pathlib import Path

        return cls.from_json(Path(path).read_text(encoding="utf-8"))
