"""Glossary — layered, repo-resident caption vocabulary.

Two parts per layer (brief §3.3, §7):
  - ``terms``       — canonical spellings to preserve (SIGIL.ZERO, Dyson Hope,
                      FFmpeg, Remotion, ...).
  - ``corrections`` — mishear -> canonical map, applied as a *post-transcription*
                      pass (Whisper-family models only weakly honour prompt
                      biasing, so fixing afterwards is more reliable).

Layers compose: ``global`` + the project's ``identity`` layer. The identity layer
wins on key collisions. Caption rendering (a later phase) consumes the merged
glossary; this module is the seam + loader, scaffolded now.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import yaml


@dataclass
class Glossary:
    terms: List[str] = field(default_factory=list)
    corrections: Dict[str, str] = field(default_factory=dict)

    def apply_corrections(self, text: str) -> str:
        """Whole-word, case-insensitive mishear -> canonical substitution."""
        out = text
        # longest keys first so multi-word fixes win over single-word ones
        for wrong in sorted(self.corrections, key=len, reverse=True):
            right = self.corrections[wrong]
            pattern = re.compile(
                r"\b" + r"\s+".join(re.escape(w) for w in wrong.split()) + r"\b",
                re.IGNORECASE,
            )
            out = pattern.sub(right, out)
        return out


def _load_layer(path: Path) -> Glossary:
    if not path.exists():
        return Glossary()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Glossary(
        terms=list(data.get("terms") or []),
        corrections=dict(data.get("corrections") or {}),
    )


def load_glossary(config_root: str | Path, identity: str) -> Glossary:
    """Merge the global layer with the identity layer (identity wins)."""
    root = Path(config_root)
    base = _load_layer(root / "glossary" / "global.yml")
    layer = _load_layer(root / "glossary" / "identities" / f"{identity}.yml")

    terms = list(dict.fromkeys(base.terms + layer.terms))  # de-dup, keep order
    corrections = {**base.corrections, **layer.corrections}
    return Glossary(terms=terms, corrections=corrections)
