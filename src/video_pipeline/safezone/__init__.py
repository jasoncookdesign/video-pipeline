"""Safe-zone spec derivation.

An Instagram safe zone is *not* a rectangle. It is an irregular polygon — a
safe-area rectangle with a smaller rectangle notched out of the lower-right
corner for the action-button cluster. This package derives that polygon
*from a reference template PNG* (adkit.so), so that when Instagram changes the
safe zone the spec regenerates by dropping in a new PNG — no code change.

Public API:
    generate_spec(png_path, profile=...) -> SafeZoneSpec
    SafeZoneSpec  (dataclass; .to_dict() / .from_dict() / .contains())
"""

from .spec import SafeZoneSpec, Band
from .generator import generate_spec, GENERATOR_VERSION

__all__ = ["SafeZoneSpec", "Band", "generate_spec", "GENERATOR_VERSION"]
