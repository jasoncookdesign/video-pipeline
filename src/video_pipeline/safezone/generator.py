"""Derive a SafeZoneSpec from a reference template PNG.

The template (from https://adkit.so/tools/safe-zones/instagram) renders the
*danger* region as an opaque overlay and leaves the *safe* region transparent
(or, for flattened templates, light). This module:

  1. classifies every pixel danger/safe (alpha-keyed by default; auto-falls back
     to colour-keying for flattened templates),
  2. isolates the main safe region by a scanline flood-fill from its centroid
     (so stray transparent pixels at the frame edge can't corrupt the spec),
  3. emits a row-convex run-length encoding (``bands``) and an equivalent
     orthogonal ``polygon`` — both notch-aware,
  4. asserts the two views describe the same area before returning.

Dependency-light: numpy + Pillow only. Update-resilient: a new PNG regenerates
the spec with no code change.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

import numpy as np

from .spec import Band, SafeZoneSpec

GENERATOR_VERSION = "1.0"

# Defaults per keying mode.
_ALPHA_DANGER_THRESHOLD = 128   # alpha >= this  => danger (opaque overlay)
_COLOR_SAFE_FLOOR = 200         # min(R,G,B) >= this => safe (near-white)


# ── pixel classification ──────────────────────────────────────────────────────

def _danger_mask(img: np.ndarray, key: str, threshold: Optional[int]) -> Tuple[np.ndarray, str, int]:
    """Return (danger_bool_HxW, key_mode, threshold_used)."""
    h, w = img.shape[:2]
    has_alpha = img.ndim == 3 and img.shape[2] == 4

    mode = key
    if key == "auto":
        if has_alpha and int(img[:, :, 3].min()) < 255 and int(img[:, :, 3].max()) > 0:
            mode = "alpha"
        else:
            mode = "color"

    if mode == "alpha":
        if not has_alpha:
            raise ValueError("alpha keying requested but template has no alpha channel")
        thr = _ALPHA_DANGER_THRESHOLD if threshold is None else threshold
        danger = img[:, :, 3] >= thr
        return danger, "alpha", thr

    if mode == "color":
        thr = _COLOR_SAFE_FLOOR if threshold is None else threshold
        rgb = img[:, :, :3].astype(np.int32)
        safe = rgb.min(axis=2) >= thr          # near-white => safe
        return ~safe, "color", thr

    raise ValueError(f"unknown key mode: {key!r}")


# ── main-region isolation (scanline flood fill) ───────────────────────────────

def _flood_fill(safe: np.ndarray, seed_y: int, seed_x: int) -> np.ndarray:
    """4-connected scanline flood fill of `safe`, returning the component mask."""
    h, w = safe.shape
    out = np.zeros((h, w), dtype=bool)
    if not safe[seed_y, seed_x]:
        return out
    stack: List[Tuple[int, int]] = [(seed_y, seed_x)]
    while stack:
        y, x = stack.pop()
        if out[y, x] or not safe[y, x]:
            continue
        # expand the run on this scanline
        xl = x
        while xl - 1 >= 0 and safe[y, xl - 1] and not out[y, xl - 1]:
            xl -= 1
        xr = x
        while xr + 1 < w and safe[y, xr + 1] and not out[y, xr + 1]:
            xr += 1
        out[y, xl:xr + 1] = True
        for ny in (y - 1, y + 1):
            if 0 <= ny < h:
                row_safe = safe[ny, xl:xr + 1]
                row_done = out[ny, xl:xr + 1]
                cols = np.where(row_safe & ~row_done)[0]
                for c in cols:
                    stack.append((ny, xl + int(c)))
    return out


# ── band / polygon construction ───────────────────────────────────────────────

def _bands_from_mask(mask: np.ndarray) -> List[Band]:
    """Row-convex RLE. Raises if any occupied row is not a single contiguous run."""
    h, w = mask.shape
    rows = np.where(mask.any(axis=1))[0]
    if len(rows) == 0:
        return []
    per_row: List[Tuple[int, int]] = []  # (x0, x1) half-open, per occupied row (contiguous)
    y_index: List[int] = []
    for y in range(int(rows.min()), int(rows.max()) + 1):
        xs = np.where(mask[y])[0]
        if len(xs) == 0:
            raise ValueError(f"safe region is not vertically contiguous at row {y}")
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        if (x1 - x0) != len(xs):
            raise ValueError(
                f"safe region is not row-convex at row {y} "
                f"(expected a single horizontal run)"
            )
        per_row.append((x0, x1))
        y_index.append(y)

    bands: List[Band] = []
    start = 0
    for i in range(1, len(per_row) + 1):
        if i == len(per_row) or per_row[i] != per_row[start]:
            x0, x1 = per_row[start]
            y0 = y_index[start]
            y1 = y_index[i - 1] + 1
            bands.append(Band(x0, y0, x1, y1))
            start = i
    return bands


def _simplify(points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Drop consecutive duplicates and collinear vertices from a closed ring."""
    pts = [p for i, p in enumerate(points) if p != points[i - 1]]
    if len(pts) < 3:
        return pts
    out: List[Tuple[int, int]] = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if cross != 0:
            out.append(b)
    return out


def _polygon_from_bands(bands: List[Band]) -> List[Tuple[int, int]]:
    """Orthogonal boundary ring of a vertically-stacked, row-convex region."""
    if not bands:
        return []
    pts: List[Tuple[int, int]] = []
    for b in bands:                      # right side, top -> bottom
        pts.append((b.x1, b.y0))
        pts.append((b.x1, b.y1))
    for b in reversed(bands):            # left side, bottom -> top
        pts.append((b.x0, b.y1))
        pts.append((b.x0, b.y0))
    return _simplify(pts)


def _notch_rects(bands: List[Band], bbox: Tuple[int, int, int, int]) -> List[Tuple[int, int, int, int]]:
    """Danger rectangles carved from the bounding box (the notches)."""
    bx0, _, bx1, _ = bbox
    raw: List[Tuple[int, int, int, int]] = []
    for b in bands:
        if b.x1 < bx1:                   # right-side notch
            raw.append((b.x1, b.y0, bx1, b.y1))
        if b.x0 > bx0:                   # left-side notch
            raw.append((bx0, b.y0, b.x0, b.y1))
    # merge vertically-adjacent notch rects that share x-extent
    raw.sort(key=lambda r: (r[0], r[2], r[1]))
    merged: List[Tuple[int, int, int, int]] = []
    for r in raw:
        if merged:
            m = merged[-1]
            if m[0] == r[0] and m[2] == r[2] and m[3] == r[1]:
                merged[-1] = (m[0], m[1], m[2], r[3])
                continue
        merged.append(r)
    return merged


# ── public entry point ────────────────────────────────────────────────────────

def generate_spec(
    png_path: str,
    profile: Optional[str] = None,
    key: str = "auto",
    threshold: Optional[int] = None,
) -> SafeZoneSpec:
    """Inspect a template PNG and return a SafeZoneSpec.

    Args:
        png_path:  path to the reference safe-zone template.
        profile:   profile name (default: PNG filename stem).
        key:       "auto" | "alpha" | "color".
        threshold: override the keying threshold (alpha cutoff or colour floor).
    """
    from PIL import Image

    img = np.asarray(Image.open(png_path).convert("RGBA"))
    h, w = img.shape[:2]

    danger, key_mode, thr = _danger_mask(img, key, threshold)
    safe = ~danger
    if not safe.any():
        raise ValueError("no safe pixels found — wrong keying mode or empty template")

    ys, xs = np.where(safe)
    seed_y, seed_x = int(np.median(ys)), int(np.median(xs))
    if not safe[seed_y, seed_x]:
        # centroid landed in a hole; fall back to the densest safe row's centre
        seed_y = int(ys[len(ys) // 2])
        row_xs = np.where(safe[seed_y])[0]
        seed_x = int(row_xs[len(row_xs) // 2])

    component = _flood_fill(safe, seed_y, seed_x)

    bands = _bands_from_mask(component)
    cy = [b.y0 for b in bands] + [bands[-1].y1]
    cx0 = min(b.x0 for b in bands)
    cx1 = max(b.x1 for b in bands)
    bbox = (cx0, min(cy), cx1, max(cy))

    polygon = _polygon_from_bands(bands)
    notch = _notch_rects(bands, bbox)

    safe_area = int(component.sum())
    band_area = sum(b.area for b in bands)
    if band_area != safe_area:
        raise AssertionError(
            f"band area {band_area} != mask area {safe_area} (generator bug)"
        )

    spec = SafeZoneSpec(
        profile=profile or os.path.splitext(os.path.basename(png_path))[0],
        source_template=os.path.basename(png_path),
        image_width=w,
        image_height=h,
        key_mode=key_mode,
        key_threshold=thr,
        bounding_box=bbox,
        polygon=polygon,
        bands=bands,
        notch_rects=notch,
        safe_area_px=safe_area,
        total_px=w * h,
        generator_version=GENERATOR_VERSION,
    )
    return spec
