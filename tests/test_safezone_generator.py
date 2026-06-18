"""TDD for the safe-zone spec generator.

Covers: a plain rectangle, a notched rectangle (the action-button cluster), the
colour-keyed fallback, JSON round-trip, and the *real* Instagram Reels template
with exact ground-truth geometry.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from tests._util import make_template_png, REELS_PNG
from video_pipeline.safezone import generate_spec, SafeZoneSpec


def _shoelace_area(poly):
    n = len(poly)
    a = 0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


class TestPlainRectangle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.png = Path(self.tmp.name) / "plain.png"
        make_template_png(self.png, 100, 200, safe_rect=(10, 20, 90, 180))

    def tearDown(self):
        self.tmp.cleanup()

    def test_bbox_and_no_notch(self):
        spec = generate_spec(str(self.png), profile="plain")
        self.assertEqual(spec.bounding_box, (10, 20, 90, 180))
        self.assertFalse(spec.has_notch)
        self.assertEqual(spec.notch_rects, [])

    def test_polygon_is_four_corners(self):
        spec = generate_spec(str(self.png), profile="plain")
        self.assertEqual(len(spec.polygon), 4)
        self.assertEqual(set(spec.polygon),
                         {(10, 20), (90, 20), (90, 180), (10, 180)})

    def test_area_consistency(self):
        spec = generate_spec(str(self.png), profile="plain")
        self.assertEqual(spec.safe_area_px, 80 * 160)
        self.assertEqual(_shoelace_area(spec.polygon), spec.safe_area_px)

    def test_contains(self):
        spec = generate_spec(str(self.png), profile="plain")
        self.assertTrue(spec.contains(50, 100))
        self.assertFalse(spec.contains(5, 100))     # left danger margin
        self.assertFalse(spec.contains(95, 100))    # right danger margin


class TestNotchedRectangle(unittest.TestCase):
    """The defining case: a danger rectangle carved out of the lower-right."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.png = Path(self.tmp.name) / "notch.png"
        make_template_png(
            self.png, 100, 200,
            safe_rect=(10, 20, 90, 180),
            notch_rect=(70, 120, 90, 180),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_has_notch(self):
        spec = generate_spec(str(self.png), profile="notch")
        self.assertTrue(spec.has_notch)
        self.assertEqual(spec.notch_rects, [(70, 120, 90, 180)])

    def test_polygon_traces_the_notch(self):
        spec = generate_spec(str(self.png), profile="notch")
        self.assertEqual(len(spec.polygon), 6)
        self.assertEqual(
            set(spec.polygon),
            {(90, 20), (90, 120), (70, 120), (70, 180), (10, 180), (10, 20)},
        )

    def test_area_consistency(self):
        spec = generate_spec(str(self.png), profile="notch")
        expected = 80 * 100 + 60 * 60  # band A + band B
        self.assertEqual(spec.safe_area_px, expected)
        self.assertEqual(_shoelace_area(spec.polygon), expected)

    def test_contains_respects_notch(self):
        spec = generate_spec(str(self.png), profile="notch")
        self.assertTrue(spec.contains(50, 50))     # interior
        self.assertTrue(spec.contains(80, 100))    # above the notch, full width
        self.assertFalse(spec.contains(80, 150))   # inside the notch -> danger
        self.assertFalse(spec.contains(5, 50))     # left margin

    def test_rect_clear_flags_notch_intrusion(self):
        spec = generate_spec(str(self.png), profile="notch")
        self.assertTrue(spec.rect_clear(20, 30, 60, 60))    # clears
        self.assertFalse(spec.rect_clear(72, 130, 88, 170))  # sits in the notch


class TestColorKeyedFallback(unittest.TestCase):
    """Flattened templates (opaque white safe over red) auto-fall back to colour."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.png = Path(self.tmp.name) / "flat.png"
        rgba = np.zeros((200, 100, 4), dtype=np.uint8)
        rgba[:, :, 0] = 239
        rgba[:, :, 3] = 255  # opaque everywhere (no transparency to key on)
        rgba[20:180, 10:90, :3] = 255  # white safe rect
        Image.fromarray(rgba, "RGBA").save(self.png)

    def tearDown(self):
        self.tmp.cleanup()

    def test_auto_detects_color_mode(self):
        spec = generate_spec(str(self.png), profile="flat")
        self.assertEqual(spec.key_mode, "color")
        self.assertEqual(spec.bounding_box, (10, 20, 90, 180))


class TestJsonRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.png = Path(self.tmp.name) / "notch.png"
        make_template_png(
            self.png, 100, 200,
            safe_rect=(10, 20, 90, 180), notch_rect=(70, 120, 90, 180),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        spec = generate_spec(str(self.png), profile="notch")
        back = SafeZoneSpec.from_json(spec.to_json())
        self.assertEqual(back.bounding_box, spec.bounding_box)
        self.assertEqual(back.polygon, spec.polygon)
        self.assertEqual(back.bands, spec.bands)
        self.assertEqual(back.notch_rects, spec.notch_rects)
        self.assertEqual(back.safe_area_px, spec.safe_area_px)


class TestRealReelsTemplate(unittest.TestCase):
    """Ground truth measured from the committed adkit Reels 9x16 template."""

    @classmethod
    def setUpClass(cls):
        cls.spec = generate_spec(str(REELS_PNG), profile="reels-9x16")

    def test_image_dims(self):
        self.assertEqual((self.spec.image_width, self.spec.image_height), (1080, 1920))

    def test_alpha_keyed(self):
        self.assertEqual(self.spec.key_mode, "alpha")

    def test_bounding_box(self):
        self.assertEqual(self.spec.bounding_box, (35, 250, 1045, 1470))

    def test_lower_right_notch(self):
        self.assertTrue(self.spec.has_notch)
        self.assertEqual(self.spec.notch_rects, [(915, 1117, 1045, 1470)])

    def test_polygon(self):
        self.assertEqual(len(self.spec.polygon), 6)
        self.assertEqual(
            set(self.spec.polygon),
            {(1045, 250), (1045, 1117), (915, 1117),
             (915, 1470), (35, 1470), (35, 250)},
        )

    def test_area(self):
        self.assertEqual(self.spec.safe_area_px, 1_186_310)
        self.assertEqual(self.spec.total_px, 2_073_600)
        self.assertAlmostEqual(self.spec.safe_fraction, 0.5721, places=4)
        self.assertEqual(_shoelace_area(self.spec.polygon), self.spec.safe_area_px)

    def test_contains_action_button_notch_is_danger(self):
        self.assertTrue(self.spec.contains(540, 860))    # centre
        self.assertTrue(self.spec.contains(1000, 800))   # above notch, full width
        self.assertFalse(self.spec.contains(1000, 1300))  # action-button cluster
        self.assertFalse(self.spec.contains(540, 100))   # top title-safe margin


if __name__ == "__main__":
    unittest.main()
