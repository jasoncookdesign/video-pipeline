"""Tests for rotation-aware dimension reading (INI-090 follow-up).

A portrait phone clip is often stored landscape-coded with a 90 degrees display
rotation. The reframe must work in *display* space or it carves a wrong crop and
Auto bottoms out at a tiny resolution.
"""

import unittest

from video_pipeline.reframe.probe import _dims_from_probe, _rotation_deg


def _probe(w, h, *, rotate=None, side_rotation=None, dur=24.3):
    stream = {"width": w, "height": h}
    if rotate is not None:
        stream["tags"] = {"rotate": str(rotate)}
    if side_rotation is not None:
        stream["side_data_list"] = [{"rotation": side_rotation}]
    return {"streams": [stream], "format": {"duration": str(dur)}}


class TestRotationDeg(unittest.TestCase):
    def test_no_rotation(self):
        self.assertEqual(_rotation_deg({"width": 1920, "height": 1080}), 0)

    def test_legacy_rotate_tag(self):
        self.assertEqual(_rotation_deg({"tags": {"rotate": "90"}}), 90)

    def test_side_data_negative_rotation_normalises(self):
        # ffmpeg displaymatrix often reports -90; normalise to 270.
        self.assertEqual(_rotation_deg({"side_data_list": [{"rotation": -90}]}), 270)


class TestDimsFromProbe(unittest.TestCase):
    def test_landscape_unrotated(self):
        self.assertEqual(_dims_from_probe(_probe(1920, 1080)), (1920, 1080, 24.3))

    def test_portrait_stored_landscape_with_90_flag_is_swapped(self):
        # The real-world bug: 1920x1080 coded + 90deg flag = 1080x1920 displayed.
        self.assertEqual(_dims_from_probe(_probe(1920, 1080, rotate=90))[:2], (1080, 1920))

    def test_270_side_rotation_swaps(self):
        self.assertEqual(_dims_from_probe(_probe(1920, 1080, side_rotation=-90))[:2], (1080, 1920))

    def test_180_does_not_swap(self):
        self.assertEqual(_dims_from_probe(_probe(1920, 1080, rotate=180))[:2], (1920, 1080))

    def test_duration_parsed(self):
        self.assertEqual(_dims_from_probe(_probe(1080, 1920, dur=12.5))[2], 12.5)


if __name__ == "__main__":
    unittest.main()
