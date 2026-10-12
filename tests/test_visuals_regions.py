"""Top-bottom region math (#62 part A): derived from the safe-zone spec, versioned.

The schema pins the v1 geometry as constants so consumers can copy it; these tests
prove those constants are what the derivation produces from the committed Reels
safe-zone spec (so a safe-zone change fails here and forces a version bump), that
every content rect sits inside the safe polygon (notch included), and that the
derivation really follows the spec rather than returning constants.
"""

import json
import unittest

from tests._util import REPO_ROOT

from video_pipeline.safezone.spec import Band, SafeZoneSpec
from video_pipeline.visuals.regions import (
    REGIONS_VERSION,
    Rect,
    clip_geometry,
    derive_regions,
)

REELS_SPEC = REPO_ROOT / "config" / "safezone" / "reels-9x16.safezone.json"
SCHEMA = REPO_ROOT / "schema" / "visuals.schema.json"


def _reels():
    return SafeZoneSpec.from_json(REELS_SPEC.read_text(encoding="utf-8"))


def _rect_spec(x0, y0, x1, y1, w=1080, h=1920):
    """A plain rectangular safe zone (no notch) on a w x h canvas."""
    return SafeZoneSpec(
        profile="synthetic", source_template="-", image_width=w, image_height=h,
        key_mode="alpha", key_threshold=128, bounding_box=(x0, y0, x1, y1),
        polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        bands=[Band(x0, y0, x1, y1)], notch_rects=[],
        safe_area_px=(x1 - x0) * (y1 - y0), total_px=w * h, generator_version="t",
    )


class DerivedFromSpecTests(unittest.TestCase):
    def test_reels_v1_geometry(self):
        r = derive_regions(_reels())
        self.assertEqual(r["graphic"], Rect(0, 0, 1080, 960))
        self.assertEqual(r["graphic_safe"], Rect(35, 250, 1010, 710))
        self.assertEqual(r["presenter"], Rect(0, 960, 1080, 960))
        self.assertEqual(r["presenter_safe"], Rect(35, 960, 880, 510))
        self.assertEqual(r["full_safe"], Rect(35, 250, 880, 1220))

    def test_schema_constants_match_the_derivation(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["regions_version"]["const"], REGIONS_VERSION)
        pinned = {k: v["const"] for k, v in schema["properties"]["regions"]["properties"].items()}
        derived = {k: v.to_dict() for k, v in derive_regions(_reels()).items()}
        self.assertEqual(pinned, derived)

    def test_content_rects_are_inside_the_safe_zone(self):
        spec = _reels()
        for name in ("graphic_safe", "presenter_safe", "full_safe"):
            r = derive_regions(spec)[name]
            self.assertTrue(spec.rect_clear(r.x, r.y, r.x1, r.y1), name)

    def test_presenter_safe_avoids_the_notch(self):
        spec = _reels()
        r = derive_regions(spec)["presenter_safe"]
        for nx0, ny0, nx1, ny1 in spec.notch_rects:
            overlap_x = min(r.x1, nx1) - max(r.x, nx0)
            overlap_y = min(r.y1, ny1) - max(r.y, ny0)
            self.assertFalse(overlap_x > 0 and overlap_y > 0)

    def test_panels_tile_the_canvas(self):
        r = derive_regions(_reels())
        g, p = r["graphic"], r["presenter"]
        self.assertEqual((g.x, g.w, p.x, p.w), (0, 1080, 0, 1080))
        self.assertEqual(g.y1, p.y)
        self.assertEqual(g.h + p.h, 1920)

    def test_safe_rects_sit_inside_their_panels(self):
        r = derive_regions(_reels())
        self.assertTrue(r["graphic"].contains(r["graphic_safe"]))
        self.assertTrue(r["presenter"].contains(r["presenter_safe"]))

    def test_derivation_follows_a_different_spec(self):
        r = derive_regions(_rect_spec(100, 200, 980, 1600))
        self.assertEqual(r["graphic_safe"], Rect(100, 200, 880, 760))
        self.assertEqual(r["presenter_safe"], Rect(100, 960, 880, 640))
        self.assertEqual(r["full_safe"], Rect(100, 200, 880, 1400))

    def test_spec_with_no_safe_area_in_a_panel_raises(self):
        with self.assertRaises(ValueError):
            derive_regions(_rect_spec(35, 1000, 1045, 1400))  # nothing safe up top


class ClipGeometryTests(unittest.TestCase):
    def setUp(self):
        self.regions = derive_regions(_reels())

    def test_split_clip_is_the_graphic_panel(self):
        g = clip_geometry("split", self.regions)
        self.assertEqual(g.placement, Rect(0, 0, 1080, 960))
        # content box is relative to the clip's own frame
        self.assertEqual(g.safe_box, Rect(35, 250, 1010, 710))

    def test_full_graphic_clip_fills_the_frame(self):
        g = clip_geometry("full-graphic", self.regions)
        self.assertEqual(g.placement, Rect(0, 0, 1080, 1920))
        self.assertEqual(g.safe_box, Rect(35, 250, 880, 1220))

    def test_full_presenter_has_no_clip(self):
        self.assertIsNone(clip_geometry("full-presenter", self.regions))

    def test_accepts_the_schema_dict_form(self):
        as_dicts = {k: v.to_dict() for k, v in self.regions.items()}
        self.assertEqual(clip_geometry("split", as_dicts).placement, Rect(0, 0, 1080, 960))

    def test_unknown_layout(self):
        with self.assertRaises(ValueError):
            clip_geometry("picture-in-picture", self.regions)


if __name__ == "__main__":
    unittest.main()
