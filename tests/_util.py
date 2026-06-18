"""Shared test helpers: make src/ importable and synthesise template PNGs."""

import sys
from pathlib import Path

import numpy as np

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

REPO_ROOT = Path(__file__).resolve().parents[1]
REELS_PNG = REPO_ROOT / "config" / "safezone" / "instagram-safe-zone-reels-9x16.png"


def make_template_png(
    path,
    width,
    height,
    safe_rect,
    notch_rect=None,
):
    """Write an adkit-style template PNG: transparent safe zone over opaque red.

    safe_rect / notch_rect are (x0, y0, x1, y1) half-open. The safe region is the
    safe_rect minus the notch_rect (a danger rectangle carved out).
    """
    from PIL import Image

    sx0, sy0, sx1, sy1 = safe_rect
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    # everything danger (opaque red) by default
    rgba[:, :, 0] = 239
    rgba[:, :, 1] = 68
    rgba[:, :, 2] = 68
    rgba[:, :, 3] = 255
    # carve the safe rect transparent
    rgba[sy0:sy1, sx0:sx1, 3] = 0
    # restore the notch back to danger
    if notch_rect is not None:
        nx0, ny0, nx1, ny1 = notch_rect
        rgba[ny0:ny1, nx0:nx1, 3] = 255
    Image.fromarray(rgba, "RGBA").save(path)
    return path
