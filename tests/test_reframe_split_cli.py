"""CLI surface for the two-task reframe split (INI-091): reframe-propose / reframe-render.

The reframe step becomes two GUI tasks mirroring the caption define/render pattern:

  * ``reframe-propose`` — runs the tracker (native seam, mocked here) -> writes the
    editable ``reframe.def`` + the persisted subject track. NO video.
  * ``reframe-render``  — reads the (hand-editable) ``reframe.def`` -> replays the exact
    geometry -> ffmpeg crop (native seam, mocked here) -> the reframed clip + occupancy.

The native seams (ffprobe dims, the subject tracker, the ffmpeg run) are mocked so the
contract verified here is: the parsers parse, propose writes a valid def + track, and
render reads it back and assembles a runnable ffmpeg argv from the def's geometry —
without re-tracking or re-deriving. The pure pieces (def round-trip, model->geometry,
crop plan) are covered in test_reframe_model.py.
"""

import os
import tempfile
import unittest
from unittest import mock

from tests._util import REPO_ROOT  # noqa: F401  (ensures src/ on path)

from video_pipeline.cli import build_parser
from video_pipeline.reframe.decision import ReframeDef
from video_pipeline.reframe.track_io import read_track
from video_pipeline.reframe.tracker import FrameSubject


def _subjects():
    # A confident, bbox-bearing track (bbox needed for occupancy to be non-empty).
    return [
        FrameSubject(t=i * 0.2, cx=700, cy=400, bbox=(640, 300, 760, 500),
                     confidence=1.0)
        for i in range(8)
    ]


class _StubTracker:
    """A tracker that returns a canned track without touching footage."""

    def track(self, video_path):
        return _subjects()


class TestReframeProposeParser(unittest.TestCase):
    def setUp(self):
        self.p = build_parser()

    def test_propose_flags_parse(self):
        ns = self.p.parse_args([
            "reframe-propose", "in.mp4", "-o", "work/reframe.json",
            "--aspect", "full-portrait", "--resolution", "1080p",
            "--framing", "performer", "--scale", "1.4",
            "--mode", "dynamic", "--lock", "both", "--tracker", "mediapipe",
            "--track-out", "work/t.json", "--allow-upscale",
        ])
        self.assertEqual(ns.output, "work/reframe.json")
        self.assertEqual(ns.aspect, "full-portrait")
        self.assertEqual(ns.resolution, "1080p")
        self.assertEqual(ns.framing, "performer")
        self.assertEqual(ns.scale, 1.4)
        self.assertEqual(ns.mode, "dynamic")
        self.assertEqual(ns.lock, "both")
        self.assertEqual(ns.tracker, "mediapipe")
        self.assertEqual(ns.track_out, "work/t.json")
        self.assertTrue(ns.allow_upscale)

    def test_propose_defaults(self):
        ns = self.p.parse_args(["reframe-propose", "in.mp4", "-o", "d.json"])
        self.assertEqual(ns.lock, "none")
        self.assertEqual(ns.mode, "static")
        self.assertEqual(ns.tracker, "opencv")
        self.assertEqual(ns.resolution, "auto")
        self.assertFalse(ns.allow_upscale)


class TestReframeRenderParser(unittest.TestCase):
    def setUp(self):
        self.p = build_parser()

    def test_render_flags_parse(self):
        ns = self.p.parse_args([
            "reframe-render", "in.mp4", "--reframe-def", "work/reframe.json",
            "-o", "work/base.mp4", "--reframed-out", "work/reframed.mp4",
            "--occupancy-out", "work/occ.json", "--dry-run",
        ])
        self.assertEqual(ns.reframe_def, "work/reframe.json")
        self.assertEqual(ns.output, "work/base.mp4")
        self.assertEqual(ns.reframed_out, "work/reframed.mp4")
        self.assertEqual(ns.occupancy_out, "work/occ.json")
        self.assertTrue(ns.dry_run)

    def test_render_requires_def(self):
        with self.assertRaises(SystemExit):
            self.p.parse_args(["reframe-render", "in.mp4", "-o", "out.mp4"])


class TestProposeRenderCli(unittest.TestCase):
    """Propose (tracker mocked) writes a def; render (ffmpeg mocked) consumes it."""

    def _run(self, argv):
        from video_pipeline.cli import main
        return main(argv)

    def test_propose_writes_valid_def_and_track(self):
        with tempfile.TemporaryDirectory() as d:
            defp = os.path.join(d, "reframe.json")
            with mock.patch(
                "video_pipeline.reframe.probe._probe_dimensions",
                return_value=(1920, 1080, 4.0),
            ), mock.patch(
                "video_pipeline.reframe.tracker.OpenCVFaceTracker",
                return_value=_StubTracker(),
            ):
                rc = self._run([
                    "reframe-propose", os.path.join(d, "in.mp4"), "-o", defp,
                    "--aspect", "full-portrait", "--framing", "performer",
                ])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(defp))
            rdef = ReframeDef.read(defp)
            self.assertEqual(rdef.target.aspect, "full-portrait")
            self.assertEqual(rdef.framing_intent, "performer")
            # the track was persisted beside the def (default) and is readable
            self.assertTrue(rdef.subject_track)
            self.assertTrue(os.path.exists(rdef.subject_track))
            self.assertEqual(len(read_track(rdef.subject_track)), 8)
            # propose renders NO video
            self.assertFalse(os.path.exists(os.path.join(d, "base.mp4")))

    def test_render_reads_def_and_assembles_ffmpeg_argv(self):
        captured = {}

        def _fake_run(cmd, check=False):
            captured["cmd"] = cmd
            class _R:  # noqa: D401
                returncode = 0
            return _R()

        with tempfile.TemporaryDirectory() as d:
            defp = os.path.join(d, "reframe.json")
            inp = os.path.join(d, "in.mp4")
            outp = os.path.join(d, "base.mp4")
            occp = os.path.join(d, "occ.json")
            # propose first (tracker mocked) to write a real def + track
            with mock.patch(
                "video_pipeline.reframe.probe._probe_dimensions",
                return_value=(1920, 1080, 4.0),
            ), mock.patch(
                "video_pipeline.reframe.tracker.OpenCVFaceTracker",
                return_value=_StubTracker(),
            ):
                self._run([
                    "reframe-propose", inp, "-o", defp, "--aspect", "full-portrait",
                ])
            # render: probe + ffmpeg mocked. Distinct input/output so the file isn't
            # rewritten-in-place (no os.replace needed); just assert the argv.
            with mock.patch(
                "video_pipeline.reframe.probe._probe_dimensions",
                return_value=(1920, 1080, 4.0),
            ), mock.patch("subprocess.run", side_effect=_fake_run):
                rc = self._run([
                    "reframe-render", inp, "--reframe-def", defp, "-o", outp,
                    "--occupancy-out", occp,
                ])
            self.assertEqual(rc, 0)
            cmd = captured["cmd"]
            self.assertEqual(cmd[0], "ffmpeg")
            self.assertIn(inp, cmd)
            self.assertIn(outp, cmd)
            # render recomputes occupancy from the final crop
            self.assertTrue(os.path.exists(occp))

    def test_render_dry_run_assembles_argv_without_running(self):
        with tempfile.TemporaryDirectory() as d:
            defp = os.path.join(d, "reframe.json")
            inp = os.path.join(d, "in.mp4")
            with mock.patch(
                "video_pipeline.reframe.probe._probe_dimensions",
                return_value=(1920, 1080, 4.0),
            ), mock.patch(
                "video_pipeline.reframe.tracker.OpenCVFaceTracker",
                return_value=_StubTracker(),
            ):
                self._run(["reframe-propose", inp, "-o", defp])
            # dry-run must NOT call subprocess.run
            with mock.patch(
                "video_pipeline.reframe.probe._probe_dimensions",
                return_value=(1920, 1080, 4.0),
            ), mock.patch("subprocess.run") as run:
                rc = self._run([
                    "reframe-render", inp, "--reframe-def", defp,
                    "-o", os.path.join(d, "out.mp4"), "--dry-run",
                ])
            self.assertEqual(rc, 0)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
