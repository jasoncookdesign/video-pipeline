"""SafeZoneSpec — the machine-readable safe-zone contract.

Coordinate convention
---------------------
Integer **pixel-edge** coordinates with origin at the top-left, x increasing
right, y increasing down. A band/rectangle ``(x0, y0, x1, y1)`` covers the
pixels ``x0 <= x < x1`` and ``y0 <= y < y1`` (half-open, like ranges). So a
safe band whose rightmost safe *pixel column* is 1044 has ``x1 == 1045``.

The spec carries two equivalent views of the safe region:
  - ``bands``   — row-convex run-length encoding; O(1) point-in-safe tests
                  (what the QC validator consumes), notch included natively.
  - ``polygon`` — ordered orthogonal vertices tracing the same region; the
                  human/printable artifact and the basis for overlay placement.

The two are derived from the same mask and must agree (area equality is
asserted at generation time).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Tuple


@dataclass(frozen=True)
class Band:
    """A horizontal run of safe pixels: x0 <= x < x1 over rows y0 <= y < y1."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class SafeZoneSpec:
    """Derived safe-zone description for one output profile."""

    profile: str
    source_template: str
    image_width: int
    image_height: int
    key_mode: str  # "alpha" | "color"
    key_threshold: int
    bounding_box: Tuple[int, int, int, int]  # (x0, y0, x1, y1), half-open
    polygon: List[Tuple[int, int]]           # ordered orthogonal vertices, closed implicitly
    bands: List[Band]                        # row-convex RLE of the safe region
    notch_rects: List[Tuple[int, int, int, int]]  # danger rects carved from bbox
    safe_area_px: int
    total_px: int
    generator_version: str

    # ── stats ────────────────────────────────────────────────────────────────
    @property
    def safe_fraction(self) -> float:
        return self.safe_area_px / self.total_px if self.total_px else 0.0

    @property
    def has_notch(self) -> bool:
        return len(self.notch_rects) > 0

    # ── geometry ──────────────────────────────────────────────────────────────
    def contains(self, x: float, y: float) -> bool:
        """True if point (x, y) is inside the safe region (notch-aware)."""
        for b in self.bands:
            if b.y0 <= y < b.y1 and b.x0 <= x < b.x1:
                return True
        return False

    def rect_clear(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        """True if rectangle [x0,x1)x[y0,y1) lies fully inside the safe region.

        Used by the QC validator to flag overlays/text/logos intruding on the
        danger region (including the notch).
        """
        # Sample the four corners and the centre is insufficient for a notch;
        # do an exact band-coverage test over the rectangle's row span.
        import math

        iy0, iy1 = int(math.floor(y0)), int(math.ceil(y1))
        for y in range(iy0, iy1):
            covered = False
            for b in self.bands:
                if b.y0 <= y < b.y1 and b.x0 <= x0 and x1 <= b.x1:
                    covered = True
                    break
            if not covered:
                return False
        return True

    # ── serialisation ──────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "source_template": self.source_template,
            "image": {"width": self.image_width, "height": self.image_height},
            "key": {"mode": self.key_mode, "threshold": self.key_threshold},
            "bounding_box": {
                "x0": self.bounding_box[0],
                "y0": self.bounding_box[1],
                "x1": self.bounding_box[2],
                "y1": self.bounding_box[3],
            },
            "polygon": [[int(x), int(y)] for x, y in self.polygon],
            "bands": [
                {"x0": b.x0, "y0": b.y0, "x1": b.x1, "y1": b.y1} for b in self.bands
            ],
            "notch_rects": [list(r) for r in self.notch_rects],
            "stats": {
                "safe_area_px": self.safe_area_px,
                "total_px": self.total_px,
                "safe_fraction": round(self.safe_fraction, 6),
                "has_notch": self.has_notch,
            },
            "generator_version": self.generator_version,
            "coordinate_convention": (
                "integer pixel-edge; origin top-left; x right, y down; "
                "rects are half-open x0<=x<x1, y0<=y<y1"
            ),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    @classmethod
    def from_dict(cls, d: dict) -> "SafeZoneSpec":
        bb = d["bounding_box"]
        return cls(
            profile=d["profile"],
            source_template=d["source_template"],
            image_width=d["image"]["width"],
            image_height=d["image"]["height"],
            key_mode=d["key"]["mode"],
            key_threshold=d["key"]["threshold"],
            bounding_box=(bb["x0"], bb["y0"], bb["x1"], bb["y1"]),
            polygon=[(int(x), int(y)) for x, y in d["polygon"]],
            bands=[Band(b["x0"], b["y0"], b["x1"], b["y1"]) for b in d["bands"]],
            notch_rects=[tuple(r) for r in d.get("notch_rects", [])],
            safe_area_px=d["stats"]["safe_area_px"],
            total_px=d["stats"]["total_px"],
            generator_version=d.get("generator_version", "unknown"),
        )

    @classmethod
    def from_json(cls, text: str) -> "SafeZoneSpec":
        return cls.from_dict(json.loads(text))
