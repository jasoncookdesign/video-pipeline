"""Visual-template style — layered repo config, validated at the Python boundary.

Same pattern as :mod:`video_pipeline.captions.style`: ``config/visual-styles/``
holds ``global.yml`` plus ``identities/<identity>.yml``; precedence (low → high) is
built-in defaults, global, identity, then explicit overrides. The resolved
:class:`VisualStyle` rides in every template's props as ``style``.

Legibility is enforced here, not in the templates: every type size has a floor
(:data:`MIN_TYPE_PX`) so a template rendered into the graphic panel stays readable
on a phone, and fonts must be in the shared caption allowlist (the Remotion
project registers exactly those families).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ..captions.style import FONT_ALLOWLIST

# px at the 1920-px canvas height. On a ~390-pt-wide phone a 1080-px frame maps
# at ~0.36 pt/px: 28 px ≈ 10 pt (tags), 40 px ≈ 14 pt (body), 56 px ≈ 20 pt.
MIN_TYPE_PX = {"label_px": 28, "body_px": 40, "heading_px": 56, "title_px": 72}
MAX_TYPE_PX = 400

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_COLOR_KEYS = ("ground", "surface", "surface_2", "line", "line_2", "text", "text_2",
               "accent", "accent_ink", "warm", "alert")
_FONT_KEYS = ("display_font", "body_font", "mono_font")
_FONTS_LC = {f.lower() for f in FONT_ALLOWLIST}


@dataclass(frozen=True)
class VisualStyle:
    ground: str = "#141414"
    surface: str = "#202020"
    surface_2: str = "#2A2A2A"
    line: str = "#3A3A3A"
    line_2: str = "#505050"
    text: str = "#F2F2F2"
    text_2: str = "#A0A0A0"
    accent: str = "#FFE14D"
    accent_ink: str = "#141414"
    warm: str = "#E8B27C"
    alert: str = "#FF6B5A"
    display_font: str = "Helvetica"
    body_font: str = "Helvetica"
    mono_font: str = "Menlo"
    label_px: int = 30
    body_px: int = 44
    heading_px: int = 64
    title_px: int = 112
    parody_label: str = "PARODY"
    brand_label: str = ""

    def __post_init__(self):
        for key in _COLOR_KEYS:
            if not _HEX.match(getattr(self, key)):
                raise ValueError(f"{key} {getattr(self, key)!r} is not a #RRGGBB hex color")
        for key in _FONT_KEYS:
            if getattr(self, key).lower() not in _FONTS_LC:
                raise ValueError(f"{key} {getattr(self, key)!r} not in the font allowlist {FONT_ALLOWLIST}")
        for key, floor in MIN_TYPE_PX.items():
            v = getattr(self, key)
            if not (floor <= v <= MAX_TYPE_PX):
                raise ValueError(f"{key} {v} out of range [{floor}, {MAX_TYPE_PX}] (legibility floor)")
        if not self.parody_label.strip():
            raise ValueError("parody_label must not be blank")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_COERCE = {f.name: (int if f.type in ("int", int) else str) for f in fields(VisualStyle)}


def _clean(data: Optional[dict]) -> Dict[str, Any]:
    if not data:
        return {}
    return {k: _COERCE[k](v) for k, v in data.items() if k in _COERCE and v is not None}


def _load_layer(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return _clean(data)


def load_visual_style(
    config_root: str | Path,
    identity: Optional[str],
    overrides: Optional[dict] = None,
) -> VisualStyle:
    """Merge global + identity + overrides into a validated :class:`VisualStyle`."""
    root = Path(config_root) / "visual-styles"
    merged: Dict[str, Any] = {}
    merged.update(_load_layer(root / "global.yml"))
    if identity:
        layer = root / "identities" / f"{identity}.yml"
        if not layer.exists():
            known = sorted(f.stem for f in (root / "identities").glob("*.yml"))
            raise ValueError(f"unknown visual-style identity {identity!r} (known: {known})")
        merged.update(_load_layer(layer))
    merged.update(_clean(overrides))
    return replace(VisualStyle(), **merged)
