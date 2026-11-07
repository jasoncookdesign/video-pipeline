"""Layout constants and text measurement for the kinetic-text layer (px on the 1080x1920 canvas)."""

from __future__ import annotations

import math
import re
from typing import Optional, Sequence, Tuple

# Where content may sit: the shared full-frame safe rect (x, y, w, h). The visual
# track pins the same rect as ``full_safe``; a test asserts they agree.
FULL_SAFE = (35, 250, 880, 1220)
# Height of the static title block at the top of the safe rect, and the gap below it.
TITLE_BLOCK_H = 360
TITLE_GAP = 40
# Body type size per role, above the style layer's legibility floors.
ROLE_PX = {"statement": 60, "aside": 50, "question": 68}
# Content is inset this far from the safe rect's sides (room for the text glow),
# and a text block is this share of that inner width (room for drift to either side).
PAD = 28
# The tallest text block that fits the body container: from PAD below the title block's
# gap to PAD above the bottom of the safe rect.
BODY_MAX_BLOCK_H = FULL_SAFE[3] - PAD - (TITLE_BLOCK_H + TITLE_GAP + PAD)
# The smallest size a beat is shrunk to when its authored lines would not fit at the role size.
MIN_PX = 36
LINE_SHARE = {"statement": 0.9, "aside": 0.78, "question": 0.9}
# Title block internals: text, then a gap, then an accent bar, each inset by PAD.
BAR_GAP = 28
BAR_H = 8
TITLE_LINE_HEIGHT = 1.0
# Line pitch as a multiple of the type size; a line with a bigger accent is as tall as that accent.
LINE_HEIGHT = 1.2
FAMILY_FOR_ROLE = {"statement": "display", "aside": "body", "question": "display"}

# Advance widths (em) of printable ASCII, common punctuation, and Latin accents,
# measured from the bundled font files: the maximum over every bundled weight and
# style, so a width computed from them never underestimates.
DISPLAY_ADVANCE_EM = {
    ' ': 0.214, '!': 0.333, '"': 0.497, '#': 0.66, '$': 0.611, '%': 1.0, '&': 0.889, "'": 0.278,
    '(': 0.389, ')': 0.389, '*': 0.407, '+': 0.66, ',': 0.333, '-': 0.333, '.': 0.333,
    '/': 0.306, '0': 0.667, '1': 0.667, '2': 0.667, '3': 0.667, '4': 0.667, '5': 0.667,
    '6': 0.667, '7': 0.667, '8': 0.667, '9': 0.667, ':': 0.336, ';': 0.336, '<': 0.66,
    '=': 0.66, '>': 0.66, '?': 0.613, '@': 1.01, 'A': 0.778, 'B': 0.778, 'C': 0.778, 'D': 0.778,
    'E': 0.722, 'F': 0.667, 'G': 0.833, 'H': 0.833, 'I': 0.369, 'J': 0.667, 'K': 0.833,
    'L': 0.667, 'M': 0.972, 'N': 0.833, 'O': 0.833, 'P': 0.722, 'Q': 0.833, 'R': 0.778,
    'S': 0.722, 'T': 0.722, 'U': 0.833, 'V': 0.778, 'W': 1.0, 'X': 0.778, 'Y': 0.778,
    'Z': 0.722, '[': 0.389, '\\': 0.306, ']': 0.389, '^': 0.66, '_': 0.556, '`': 0.297,
    'a': 0.667, 'b': 0.667, 'c': 0.667, 'd': 0.667, 'e': 0.667, 'f': 0.389, 'g': 0.666,
    'h': 0.667, 'i': 0.319, 'j': 0.316, 'k': 0.667, 'l': 0.319, 'm': 1.0, 'n': 0.667,
    'o': 0.667, 'p': 0.667, 'q': 0.667, 'r': 0.444, 's': 0.611, 't': 0.444, 'u': 0.667,
    'v': 0.611, 'w': 0.944, 'x': 0.667, 'y': 0.611, 'z': 0.556, '{': 0.394, '|': 0.282,
    '}': 0.395, '~': 0.66, '’': 0.28, '‘': 0.28, '“': 0.508, '”': 0.508, '—': 1.0, '–': 0.5,
    '…': 1.0, 'á': 0.667, 'é': 0.667, 'í': 0.319, 'ó': 0.667, 'ú': 0.667, 'ñ': 0.667,
    'ü': 0.667, 'ç': 0.667, 'à': 0.667, 'è': 0.667, 'ì': 0.319, 'ò': 0.667, 'ù': 0.667,
    'â': 0.667, 'ê': 0.667, 'î': 0.319, 'ô': 0.667, 'û': 0.667, 'ä': 0.667, 'ë': 0.667,
    'ï': 0.319, 'ö': 0.667, 'ÿ': 0.611, 'å': 0.667, 'Á': 0.778, 'É': 0.722, 'Í': 0.369,
    'Ó': 0.833, 'Ú': 0.833, 'Ñ': 0.833, 'Ü': 0.833, 'Ç': 0.778, 'À': 0.778, 'È': 0.722,
    'Ì': 0.369, 'Ò': 0.833, 'Ù': 0.833,
}

BODY_ADVANCE_EM = {
    ' ': 0.281, '!': 0.338, '"': 0.552, '#': 0.649, '$': 0.655, '%': 1.016, '&': 0.691,
    "'": 0.339, '(': 0.377, ')': 0.376, '*': 0.559, '+': 0.679, ',': 0.334, '-': 0.468,
    '.': 0.335, '/': 0.388, '0': 0.675, '1': 0.432, '2': 0.631, '3': 0.646, '4': 0.677,
    '5': 0.622, '6': 0.649, '7': 0.582, '8': 0.651, '9': 0.649, ':': 0.335, ';': 0.343,
    '<': 0.679, '=': 0.679, '>': 0.679, '?': 0.559, '@': 1.016, 'A': 0.747, 'B': 0.662,
    'C': 0.74, 'D': 0.723, 'E': 0.613, 'F': 0.591, 'G': 0.75, 'H': 0.747, 'I': 0.281,
    'J': 0.584, 'K': 0.719, 'L': 0.566, 'M': 0.932, 'N': 0.762, 'O': 0.771, 'P': 0.648,
    'Q': 0.777, 'R': 0.657, 'S': 0.655, 'T': 0.668, 'U': 0.744, 'V': 0.747, 'W': 1.038,
    'X': 0.738, 'Y': 0.731, 'Z': 0.665, '[': 0.377, '\\': 0.388, ']': 0.377, '^': 0.487,
    '_': 0.476, '`': 0.365, 'a': 0.631, 'b': 0.63, 'c': 0.588, 'd': 0.631, 'e': 0.596,
    'f': 0.41, 'g': 0.633, 'h': 0.623, 'i': 0.272, 'j': 0.272, 'k': 0.58, 'l': 0.271,
    'm': 0.913, 'n': 0.623, 'o': 0.614, 'p': 0.63, 'q': 0.631, 'r': 0.408, 's': 0.56,
    't': 0.367, 'u': 0.623, 'v': 0.6, 'w': 0.85, 'x': 0.58, 'y': 0.602, 'z': 0.574, '{': 0.469,
    '|': 0.372, '}': 0.469, '~': 0.679, '’': 0.351, '‘': 0.351, '“': 0.581, '”': 0.573,
    '—': 1.001, '–': 0.501, '…': 1.003, 'á': 0.631, 'é': 0.596, 'í': 0.271, 'ó': 0.614,
    'ú': 0.623, 'ñ': 0.623, 'ü': 0.623, 'ç': 0.589, 'à': 0.631, 'è': 0.596, 'ì': 0.271,
    'ò': 0.614, 'ù': 0.623, 'â': 0.631, 'ê': 0.596, 'î': 0.271, 'ô': 0.614, 'û': 0.623,
    'ä': 0.631, 'ë': 0.596, 'ï': 0.271, 'ö': 0.614, 'ÿ': 0.603, 'å': 0.631, 'Á': 0.747,
    'É': 0.613, 'Í': 0.281, 'Ó': 0.771, 'Ú': 0.744, 'Ñ': 0.762, 'Ü': 0.744, 'Ç': 0.74,
    'À': 0.747, 'È': 0.613, 'Ì': 0.281, 'Ò': 0.771, 'Ù': 0.744,
}

_FALLBACK = {"display": max(DISPLAY_ADVANCE_EM.values()), "body": max(BODY_ADVANCE_EM.values())}
_TABLES = {"display": DISPLAY_ADVANCE_EM, "body": BODY_ADVANCE_EM}


def text_width_em(text: str, family: str) -> float:
    """Width of text in em, from measured advances (unknown characters count as the widest glyph)."""
    table, fallback = _TABLES[family], _FALLBACK[family]
    return sum(table.get(c, fallback) for c in text)


def line_width(role: str) -> float:
    """Width available to one line of a role's text."""
    return (FULL_SAFE[2] - 2 * PAD) * LINE_SHARE[role]


def fits_line(role: str, text: str, scale: float = 1.0) -> bool:
    """Whether text set at scale times the role's size fits on one line."""
    return text_width_em(text, FAMILY_FOR_ROLE[role]) * ROLE_PX[role] * scale <= line_width(role)


def line_height_px(px: int, scale: float = 1.0) -> int:
    """Height of a line set at px whose largest accent is scale times that size."""
    return round(px * max(LINE_HEIGHT, scale))


def fit_px(role: str, lines: Sequence[Tuple[float, float]]) -> Optional[int]:
    """Largest size (an integer, at most the role's size) at which every line fits the measure
    and the block fits the body container, or ``None`` when even :data:`MIN_PX` does not fit.

    Each line is ``(width, scale)``: its width in em at scale 1 for the unscaled words and
    scaled for accented ones (spaces included), and the largest accent scale on it. Widths grow
    linearly with the size, so the width limit is computed directly.
    """
    px = ROLE_PX[role]
    widest = max((em for em, _ in lines), default=0.0)
    if widest > 0:
        px = min(px, math.floor(line_width(role) / widest * (1 + 1e-12)))
    while px >= MIN_PX and sum(line_height_px(px, scale) for _, scale in lines) > BODY_MAX_BLOCK_H:
        px -= 1
    return px if px >= MIN_PX else None


def title_text_height() -> int:
    """Height available to the title's text inside its block."""
    return TITLE_BLOCK_H - PAD - BAR_GAP - BAR_H - PAD


def _title_lines(text: str, px: int, width: float) -> Optional[int]:
    """Lines needed to wrap text at px, or None when a single word is wider than a line."""
    space = text_width_em(" ", "display") * px
    lines, cur = 1, 0.0
    for word in text.split():
        w = text_width_em(word, "display") * px
        if w > width:
            return None
        need = w if cur == 0 else cur + space + w
        if need > width:
            lines, cur = lines + 1, w
        else:
            cur = need
    return lines


def fit_title(title: str, max_px: int, min_px: int) -> Optional[int]:
    """Largest title size in [min_px, max_px] at which the uppercased title wraps
    into the title block, or None when even min_px does not fit."""
    width = FULL_SAFE[2] - 2 * PAD
    text = re.sub(r"\s+", " ", title.upper()).strip()
    for px in range(max_px, min_px - 1, -2):
        lines = _title_lines(text, px, width)
        if lines is not None and lines * px * TITLE_LINE_HEIGHT <= title_text_height():
            return px
    return None
