"""QC consumption of overlay.occupancy (INI-089) — caption-over-overlay + the
occupancy→elements bridge + per-cue box in caption_elements_from_props."""

import tempfile
import unittest
from pathlib import Path

from tests._util import make_template_png

from video_pipeline.safezone import generate_spec
from video_pipeline.qc.report import OVERLAY_KIND, QCElement, Rect
from video_pipeline.qc.validate import overlay_elements, validate
from video_pipeline.qc.runner import (
    caption_elements_from_props,
    overlay_elements_from_occupancy,
)
from video_pipeline.overlay.decision import OverlayItem, OverlayList
from video_pipeline.overlay.occupancy import (
    avoid_windows,
    build_occupancy,
    occupancy_to_dict,
)


def _full_frame_spec(d):
    png = Path(d) / "t.png"
    make_template_png(png, 1080, 1920, safe_rect=(40, 160, 1040, 1760))
    return generate_spec(str(png), profile="reels-9x16")


def _caption(x, y, w, h, t, t_end, label="cap"):
    return QCElement(kind="caption", rect=Rect.from_xywh(x, y, w, h),
                     label=label, t=t, t_end=t_end)


class OverlayElementsTests(unittest.TestCase):
    def test_bridge_builds_overlay_kind(self):
        els = overlay_elements([(0, 960, 1080, 960, 2.0, 6.0)])
        self.assertEqual(len(els), 1)
        self.assertEqual(els[0].kind, OVERLAY_KIND)
        self.assertEqual((els[0].t, els[0].t_end), (2.0, 6.0))

    def test_from_occupancy_descriptor(self):
        ov = OverlayList(source="x", segments=[
            OverlayItem(index=0, kind="image", src="a.png", start=2.0, end=6.0,
                        placement="bottom-half"),
        ])
        occ = occupancy_to_dict(build_occupancy(ov, 1080, 1920),
                                profile="reels-9x16", image_width=1080, image_height=1920)
        els = overlay_elements_from_occupancy(occ)
        self.assertEqual(els[0].rect.to_dict(),
                         {"x0": 0.0, "y0": 960.0, "x1": 1080.0, "y1": 1920.0})


class CaptionOverOverlayTests(unittest.TestCase):
    def test_caption_on_overlay_during_window_flags_warning(self):
        with tempfile.TemporaryDirectory() as d:
            spec = _full_frame_spec(d)
            overlays = overlay_elements([(0, 960, 1080, 960, 2.0, 6.0)])  # bottom half
            cap = _caption(100, 1100, 800, 200, 3.0, 4.0)  # sits in the bottom half
            report = validate(spec, [cap], overlays=overlays)
            kinds = [v.kind for v in report.violations]
            self.assertIn("caption-over-overlay", kinds)
            self.assertEqual(report.overlays_checked, 1)
            v = next(v for v in report.violations if v.kind == "caption-over-overlay")
            self.assertEqual(v.severity, "warning")

    def test_no_flag_when_times_disjoint(self):
        with tempfile.TemporaryDirectory() as d:
            spec = _full_frame_spec(d)
            overlays = overlay_elements([(0, 960, 1080, 960, 2.0, 6.0)])
            cap = _caption(100, 1100, 800, 200, 8.0, 9.0)  # after the overlay
            report = validate(spec, [cap], overlays=overlays)
            self.assertNotIn("caption-over-overlay", [v.kind for v in report.violations])

    def test_no_flag_when_caption_clears_overlay_spatially(self):
        with tempfile.TemporaryDirectory() as d:
            spec = _full_frame_spec(d)
            overlays = overlay_elements([(0, 960, 1080, 960, 2.0, 6.0)])
            cap = _caption(100, 300, 800, 200, 3.0, 4.0)  # upper third, clear of overlay
            report = validate(spec, [cap], overlays=overlays)
            self.assertNotIn("caption-over-overlay", [v.kind for v in report.violations])

    def test_overlay_not_flagged_for_danger_intrusion(self):
        # a full-bleed overlay covers the danger zone by design — must NOT be a
        # danger-intrusion violation (overlays go via `overlays`, not `elements`)
        with tempfile.TemporaryDirectory() as d:
            spec = _full_frame_spec(d)
            overlays = overlay_elements([(0, 0, 1080, 1920, 0.0, 5.0)])
            report = validate(spec, [], overlays=overlays)
            self.assertEqual([v.kind for v in report.violations], [])
            self.assertEqual(report.overlays_checked, 1)

    def test_disable_check(self):
        with tempfile.TemporaryDirectory() as d:
            spec = _full_frame_spec(d)
            overlays = overlay_elements([(0, 960, 1080, 960, 2.0, 6.0)])
            cap = _caption(100, 1100, 800, 200, 3.0, 4.0)
            report = validate(spec, [cap], overlays=overlays,
                              check_caption_over_overlay=False)
            self.assertNotIn("caption-over-overlay", [v.kind for v in report.violations])


class PerCueBoxInQCTests(unittest.TestCase):
    def test_dodged_cue_box_is_used(self):
        # a cue carrying its own (dodged) box → QC checks that box, not safeBox
        props = {
            "safeBox": {"x": 100, "y": 1100, "width": 800, "height": 200},
            "fps": 30,
            "cues": [
                {"index": 0, "text": "dodged", "from": 90, "durationInFrames": 30,
                 "startSeconds": 3.0, "endSeconds": 4.0,
                 "box": {"x": 100, "y": 300, "width": 800, "height": 200}},
                {"index": 1, "text": "default", "from": 240, "durationInFrames": 30,
                 "startSeconds": 8.0, "endSeconds": 9.0},
            ],
        }
        els = caption_elements_from_props(props)
        self.assertEqual(els[0].rect.y0, 300)    # used the per-cue box
        self.assertEqual(els[1].rect.y0, 1100)   # fell back to safeBox


if __name__ == "__main__":
    unittest.main()
