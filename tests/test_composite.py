"""Composite render — pure argv assembly (no ffmpeg needed)."""

import unittest

from video_pipeline.composite.render import (
    composite_filtergraph,
    ffmpeg_composite_command,
)
from video_pipeline.composite.runner import render_composite


class FiltergraphTests(unittest.TestCase):
    def test_no_overlays_is_empty(self):
        self.assertEqual(composite_filtergraph(0), "")

    def test_single_overlay_maps_outv(self):
        self.assertEqual(
            composite_filtergraph(1),
            "[0:v][1:v]overlay=0:0:format=auto[outv]",
        )

    def test_two_overlays_chain_low_to_high(self):
        # input 1 lands first (lower z), input 2 stacks on top -> [outv]
        self.assertEqual(
            composite_filtergraph(2),
            "[0:v][1:v]overlay=0:0:format=auto[ov1];"
            "[ov1][2:v]overlay=0:0:format=auto[outv]",
        )


class CommandTests(unittest.TestCase):
    def test_overlay_command_shape(self):
        cmd = ffmpeg_composite_command(
            "work/base.mp4", ["layers/captions.mov"], "review/composite.mp4"
        )
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-filter_complex", cmd)
        fg = cmd[cmd.index("-filter_complex") + 1]
        self.assertEqual(fg, "[0:v][1:v]overlay=0:0:format=auto[outv]")
        # base + one overlay = two inputs, base audio carried (optional)
        self.assertEqual(cmd.count("-i"), 2)
        self.assertIn("[outv]", cmd)
        self.assertIn("0:a?", cmd)
        self.assertIn("libx264", cmd)
        self.assertEqual(cmd[-1], "review/composite.mp4")

    def test_no_overlay_maps_base_video_directly(self):
        cmd = ffmpeg_composite_command("work/base.mp4", [], "review/composite.mp4")
        self.assertNotIn("-filter_complex", cmd)
        self.assertIn("0:v", cmd)
        self.assertEqual(cmd.count("-i"), 1)

    def test_crf_and_preset_passthrough(self):
        cmd = ffmpeg_composite_command(
            "b.mp4", ["c.mov"], "o.mp4", crf=20, preset="slow"
        )
        self.assertEqual(cmd[cmd.index("-crf") + 1], "20")
        self.assertEqual(cmd[cmd.index("-preset") + 1], "slow")

    def test_empty_base_raises(self):
        with self.assertRaises(ValueError):
            ffmpeg_composite_command("", ["c.mov"], "o.mp4")

    def test_two_overlays_order_preserved_as_inputs(self):
        cmd = ffmpeg_composite_command(
            "base.mp4", ["lo.mov", "hi.mov"], "o.mp4"
        )
        i = [cmd[k + 1] for k, t in enumerate(cmd) if t == "-i"]
        self.assertEqual(i, ["base.mp4", "lo.mov", "hi.mov"])


class RunnerTests(unittest.TestCase):
    def test_dry_run_returns_argv_without_running(self):
        # dry_run must not touch the filesystem; just returns the argv.
        cmd = render_composite(
            "work/base.mp4", ["layers/captions.mov"],
            "/nonexistent/dir/review/composite.mp4", dry_run=True,
        )
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertEqual(cmd[-1], "/nonexistent/dir/review/composite.mp4")


if __name__ == "__main__":
    unittest.main()
