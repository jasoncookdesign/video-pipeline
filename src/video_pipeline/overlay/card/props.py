"""Card look + the Remotion props contract + the overlay.def wiring (Phase B).

The content (``CardContent``) is what the card says; this module is the *look* and
the seams that carry it:

  - :class:`CardStyle` — the deterministic look (colors, sizes, radius, font). The
    Remotion ``Card`` component is driven entirely by props, so branding iterates
    here / Mac-side without touching content.
  - :func:`card_to_remotion_props` — the JSON contract the bundled ``Card``
    composition reads (mirrors ``captions.export.track_to_remotion_props``).
  - :func:`build_card_overlay_item` — turns a rendered card into a ``kind=card``
    entry in ``overlay.def`` so the Phase-A primitive places and windows it.
  - :func:`card_render_command` — the ``npx remotion render`` argv for the card
    (pure; the subprocess runs on the daily driver).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..decision import OverlayItem
from .content import CardContent

CARD_PROPS_SCHEMA_VERSION = 1

# Repo root -> the bundled Remotion project. parents: card -> overlay ->
# video_pipeline -> src -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
REMOTION_DIR = _REPO_ROOT / "remotion"
CARD_COMPOSITION = "Card"


@dataclass
class CardStyle:
    """The card's look. Neutral defaults; identity/brand overrides layer on later."""

    bg_color: str = "#101014"
    text_color: str = "#FFFFFF"
    accent_color: str = "#9C97F4"
    heading_size: int = 64
    body_size: int = 40
    footer_size: int = 28
    corner_radius: int = 24
    padding: int = 56
    font_family: str = "Helvetica"

    def to_dict(self) -> dict:
        return {
            "bg_color": self.bg_color,
            "text_color": self.text_color,
            "accent_color": self.accent_color,
            "heading_size": self.heading_size,
            "body_size": self.body_size,
            "footer_size": self.footer_size,
            "corner_radius": self.corner_radius,
            "padding": self.padding,
            "font_family": self.font_family,
        }


def card_to_remotion_props(
    content: CardContent,
    *,
    width: int,
    height: int,
    identity: Optional[str] = None,
    profile: Optional[str] = None,
    fps: int = 30,
    style: Optional[CardStyle] = None,
) -> dict:
    """Build the props object the bundled ``Card`` composition renders.

    The card is a static-content overlay — its on-screen *window* is owned by the
    Phase-A primitive (``overlay.def``), so the props carry no per-frame cues, only
    look + content + frame dimensions. ``calculateMetadata`` in the composition
    sizes the render to ``dimensions``.
    """
    style = style or CardStyle()
    return {
        "schemaVersion": CARD_PROPS_SCHEMA_VERSION,
        "kind": "card",
        "identity": identity,
        "profile": profile,
        "fps": fps,
        "dimensions": {"width": width, "height": height},
        "style": style.to_dict(),
        "content": {
            "heading": content.heading,
            "body": content.body,
            "footer": content.footer,
            "image": content.image,
            "citation": content.citation,
        },
    }


def build_card_overlay_item(
    index: int,
    content_path: str,
    start: float,
    end: float,
    *,
    placement: str = "bottom-half",
    rect: Optional[tuple] = None,
    transition: str = "fade",
    fade: float = 0.3,
    text: str = "",
) -> OverlayItem:
    """A ``kind=card`` overlay for ``overlay.def``.

    ``content_path`` is the card's content-JSON (the ``src`` a card carries, per the
    overlay decision-file contract). Defaults match how a source card usually wants
    to read: lower-half, fading in/out over the discussed span. ``start`` / ``end``
    are source-time seconds (typically from the transcript→window proposer).
    """
    return OverlayItem(
        index=index,
        kind="card",
        src=content_path,
        start=start,
        end=end,
        placement=placement,
        rect=rect,
        transition=transition,
        fade=fade,
        audio="mute",  # a card has no audio of its own
        text=text,
    )


def card_render_command(
    props_path: str,
    output_path: str,
    *,
    remotion_dir: Optional[str] = None,
    codec: str = "prores",
    prores_profile: str = "4444",
) -> List[str]:
    """``npx remotion render`` argv for the ``Card`` composition. Pure — no spawn.

    ProRes 4444 preserves the card's alpha so it composites cleanly as an overlay
    layer; ``--props`` points at the JSON from :func:`card_to_remotion_props`.
    """
    rdir = Path(remotion_dir) if remotion_dir else REMOTION_DIR
    return [
        "npx",
        "remotion",
        "render",
        str(rdir / "src" / "index.ts"),
        CARD_COMPOSITION,
        str(Path(output_path).resolve()),
        f"--props={Path(props_path).resolve()}",
        f"--codec={codec}",
        f"--prores-profile={prores_profile}",
    ]
