"""Reading-pace timing for kinetic text beats."""

from __future__ import annotations

from typing import Optional

# Words per second a viewer comfortably reads short on-screen lines.
READ_WPS = 2.5
# Shortest a text beat stays on screen.
MIN_BEAT_S = 2.0
# Lead-in added to every computed duration (arrival of the line).
LEAD_S = 0.5
# Longest allowed overlay layer.
MAX_TOTAL_S = 60.0


def word_count(text: str) -> int:
    """Whitespace-separated tokens in ``text``."""
    return len(text.split())


def beat_duration_s(text: str, override: Optional[float] = None) -> float:
    """Seconds a text beat stays on screen: ``override`` if given, else
    ``max(MIN_BEAT_S, LEAD_S + words / READ_WPS)``."""
    if override is not None:
        return float(override)
    return max(MIN_BEAT_S, LEAD_S + word_count(text) / READ_WPS)
