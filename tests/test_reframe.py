"""TDD for the reframe crop-plan and FFmpeg command assembly.

The pure logic — geometry, clamping, smoothing, command building — is fully
tested here. The MediaPipe tracking + real-footage render is the daily-driver
(Ono-Sendai) acceptance step and is intentionally out of the sandbox suite.
"""

import statistics
import unittest

from tests._util import REPO_ROOT  # noqa: F401  (ensures src/ on path)
from video_pipeline.reframe import (
    FrameSubject,
    FixedTracker,
    build_crop_plan,
    ffmpeg_crop_command,
)
from video_pipeline.reframe.plan import (
    crop_dims, clamp_center, window_x, ema_smooth, sample_x,
)
from video_pipeline.reframe.crop import filtergraph, static_filtergraph, dynamic_filtergraph


LANDSCAPE = (1920, 1080)  # the classic landscape->portrait case


class TestCropGeometry(unittest.TestCase):
    def test_crop_dims_aspect(self):
        cw, ch = crop_dims(1920, 1080, 1080, 1920)
        self.assertEqual(ch, 1080)              # full source height
        self.assertEqual(cw % 2, 0)             # even (encoder-friendly)
        self.assertAlmostEqual(cw / ch, 1080 / 1920, delta=0.01)
        self.assertLessEqual(cw, 1920)

    def test_crop_never_exceeds_source(self):
        # already-portrait source: crop height instead of width, stay in-bounds
        cw, ch = crop_dims(1080, 1920, 1080, 1920)
        self.assertLessEqual(cw, 1080)
        self.assertLessEqual(ch, 1920)

    def test_clamp_center_edges(self):
        cw, _ = crop_dims(*LANDSCAPE, 1080, 1920)
        self.assertEqual(window_x(0, cw, 1920), 0)                 # far-left subject
        self.assertEqual(window_x(1920, cw, 1920), 1920 - cw)      # far-right subject
        mid = window_x(960, cw, 1920)
        self.assertGreater(mid, 0)
        self.assertLess(mid, 1920 - cw)

    def test_clamp_center_full_width(self):
        # crop spans whole width -> centre is forced to frame centre
        self.assertEqual(clamp_center(0, 1920, 1920), 960)


class TestSmoothing(unittest.TestCase):
    def test_ema_reduces_jitter(self):
        raw = [960, 1200, 940, 1180, 950, 1210, 945]
        smoothed = ema_smooth(raw, 0.2)
        self.assertLess(statistics.pstdev(smoothed), statistics.pstdev(raw))

    def test_ema_empty(self):
        self.assertEqual(ema_smooth([], 0.2), [])


class TestStaticPlan(unittest.TestCase):
    def test_no_subjects_is_centered(self):
        plan = build_crop_plan([], *LANDSCAPE, duration=5.0)
        self.assertEqual(plan.mode, "static")
        self.assertEqual(len(plan.windows), 1)
        w = plan.windows[0]
        self.assertEqual(w.x, (1920 - w.w) // 2)
        self.assertAlmostEqual(w.aspect, 1080 / 1920, delta=0.01)

    def test_robust_center_uses_confident_samples(self):
        subs = [
            FrameSubject(t=0.0, cx=500, cy=540, confidence=1.0),
            FrameSubject(t=0.2, cx=520, cy=540, confidence=1.0),
            FrameSubject(t=0.4, cx=510, cy=540, confidence=1.0),
            FrameSubject(t=0.6, cx=960, cy=540, confidence=0.0),  # no detection, ignored
        ]
        plan = build_crop_plan(subs, *LANDSCAPE, mode="static", duration=1.0)
        w = plan.windows[0]
        # window centred near ~510, not dragged to 960 by the zero-confidence sample
        self.assertLess(w.x + w.w / 2, 700)

    def test_window_stays_in_frame_for_edge_subject(self):
        subs = [FrameSubject(t=0.0, cx=15, cy=540) for _ in range(3)]
        plan = build_crop_plan(subs, *LANDSCAPE, mode="static", duration=1.0)
        w = plan.windows[0]
        self.assertEqual(w.x, 0)
        self.assertLessEqual(w.x + w.w, 1920)


class TestDynamicPlan(unittest.TestCase):
    def _jumpy_with_gaps(self):
        # big swings AND detection gaps (confidence 0 = no face that frame)
        data = [
            (0.0, 960, 1.0), (0.2, 970, 1.0), (0.4, 1500, 1.0),
            (0.6, 0, 0.0), (0.8, 0, 0.0),                 # gap (no detection)
            (1.0, 300, 1.0), (1.2, 990, 1.0), (1.4, 1000, 1.0),
        ]
        return [FrameSubject(t=t, cx=cx, cy=540, confidence=c) for t, cx, c in data]

    def test_mode_is_dynamic(self):
        plan = build_crop_plan(self._jumpy_with_gaps(), *LANDSCAPE, mode="dynamic", duration=1.6)
        self.assertEqual(plan.mode, "dynamic")
        self.assertGreaterEqual(len(plan.windows), 1)

    def test_keyframes_stay_in_frame(self):
        plan = build_crop_plan(self._jumpy_with_gaps(), *LANDSCAPE, mode="dynamic", duration=1.6)
        for w in plan.windows:
            self.assertGreaterEqual(w.x, 0)
            self.assertLessEqual(w.x + w.w, 1920)

    def test_no_sudden_jumps(self):
        # the core regression: x(t) is continuous, never snaps (old step bug)
        plan = build_crop_plan(self._jumpy_with_gaps(), *LANDSCAPE, mode="dynamic", duration=1.6)
        dt = 0.02
        prev = sample_x(plan, 0.0)
        for i in range(1, int(1.6 / dt)):
            cur = sample_x(plan, i * dt)
            self.assertLess(abs(cur - prev), 25.0)  # a snap would be hundreds of px
            prev = cur

    def test_velocity_is_bounded(self):
        frac = 0.12
        plan = build_crop_plan(self._jumpy_with_gaps(), *LANDSCAPE, mode="dynamic",
                               max_pan_frac_per_s=frac, duration=1.6)
        max_v = frac * 1920  # px/s
        dt = 0.05
        prev = sample_x(plan, 0.0)
        for i in range(1, int(1.6 / dt)):
            cur = sample_x(plan, i * dt)
            self.assertLessEqual(abs(cur - prev) / dt, max_v * 1.5)  # generous margin
            prev = cur

    def test_too_few_detections_falls_back_to_static(self):
        subs = [
            FrameSubject(t=0.0, cx=500, cy=540, confidence=1.0),
            FrameSubject(t=0.2, cx=500, cy=540, confidence=0.0),  # only 1 detection
        ]
        plan = build_crop_plan(subs, *LANDSCAPE, mode="dynamic", duration=1.0)
        self.assertEqual(plan.mode, "static")


class TestFfmpegCommand(unittest.TestCase):
    def _static_plan(self):
        subs = [FrameSubject(t=0.0, cx=900, cy=540) for _ in range(3)]
        return build_crop_plan(subs, *LANDSCAPE, mode="static", duration=2.0)

    def test_static_filtergraph(self):
        plan = self._static_plan()
        fg = static_filtergraph(plan)
        w = plan.windows[0]
        self.assertIn(f"crop={w.w}:{w.h}:{w.x}:{w.y}", fg)
        self.assertIn("scale=1080:1920", fg)

    def _moving_subjects(self):
        xs = [400, 500, 900, 1300, 1400]
        return [FrameSubject(t=i * 0.5, cx=x, cy=540, confidence=1.0)
                for i, x in enumerate(xs)]

    def test_dynamic_filtergraph_is_linear_and_keyed(self):
        plan = build_crop_plan(self._moving_subjects(), *LANDSCAPE, mode="dynamic", duration=2.5)
        fg = dynamic_filtergraph(plan)
        self.assertIn("crop=w=", fg)
        self.assertIn("if(lt(t", fg)
        self.assertIn("(t-", fg)        # a linear ramp term, not a constant step
        self.assertIn("clip(", fg)      # clamped into frame
        self.assertIn("scale=1080:1920", fg)

    def test_dynamic_filtergraph_not_double_escaped(self):
        # regression: commas are single-quoted, must NOT also be backslash-escaped
        plan = build_crop_plan(self._moving_subjects(), *LANDSCAPE, mode="dynamic", duration=2.5)
        fg = dynamic_filtergraph(plan)
        self.assertNotIn("\\,", fg)

    def test_dynamic_filtergraph_constant_is_single_value(self):
        # a stationary subject collapses to one keyframe (no conditional)
        subs = [FrameSubject(t=i * 0.2, cx=960, cy=540, confidence=1.0) for i in range(6)]
        plan = build_crop_plan(subs, *LANDSCAPE, mode="dynamic", duration=1.2)
        fg = dynamic_filtergraph(plan)
        self.assertNotIn("if(", fg)

    def test_command_structure(self):
        plan = self._static_plan()
        cmd = ffmpeg_crop_command("in.mp4", "out.mp4", plan)
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("in.mp4", cmd)
        self.assertEqual(cmd[-1], "out.mp4")
        self.assertIn("-vf", cmd)
        self.assertIn("-c:a", cmd)
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "copy")  # audio untouched
        self.assertIn("libx264", cmd)

    def test_filtergraph_dispatch(self):
        plan = self._static_plan()
        self.assertEqual(filtergraph(plan), static_filtergraph(plan))


class TestFixedTracker(unittest.TestCase):
    def test_replays_subjects(self):
        subs = [FrameSubject(t=0.0, cx=100, cy=200)]
        self.assertEqual(FixedTracker(subs).track("anything.mp4"), subs)


if __name__ == "__main__":
    unittest.main()
