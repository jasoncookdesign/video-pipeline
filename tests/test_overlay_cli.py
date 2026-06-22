"""Overlay CLI surface (INI-089) — overlay / overlay-card / overlay-render, and
the schema↔CLI consistency (every overlay task subcommand is a real CLI command,
and its resolved argv parses)."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests._util import make_template_png

from video_pipeline import schema as S
from video_pipeline.cli import build_parser, main
from video_pipeline.safezone import generate_spec
from video_pipeline.overlay.decision import OverlayList
from video_pipeline.overlay.card.content import CardContent


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


class OverlayDefineCLITests(unittest.TestCase):
    def test_author_from_add_specs(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "overlay.def.yml")
            rc, _ = _run([
                "overlay", "-o", out, "--profile", "reels-9x16",
                "--add", "kind=image;src=a.png;start=3.2;end=7.8;placement=bottom-half",
                "--add", "kind=video;src=b.mov;start=10;end=14;placement=pip-rect;"
                         "rect=60,1180,420,560;audio=duck",
            ])
            self.assertEqual(rc, 0)
            ov = OverlayList.read(out)
            self.assertEqual(len(ov.segments), 2)
            self.assertEqual(ov.segments[0].placement, "bottom-half")
            self.assertEqual(ov.segments[1].rect, (60, 1180, 420, 560))
            self.assertEqual(ov.segments[1].audio, "duck")

    def test_window_proposed_from_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            tr = os.path.join(d, "t.json")
            Path(tr).write_text(json.dumps({"segments": [{"words": [
                {"word": "look", "start": 0.0, "end": 0.4},
                {"word": "at", "start": 0.4, "end": 0.6},
                {"word": "the", "start": 0.6, "end": 0.8},
                {"word": "chart", "start": 3.0, "end": 3.6},
            ]}]}))
            out = os.path.join(d, "o.yml")
            rc, _ = _run([
                "overlay", "-o", out, "--transcript", tr,
                "--add", 'kind=image;src=c.png;at=chart;placement=bottom-half',
            ])
            self.assertEqual(rc, 0)
            ov = OverlayList.read(out)
            self.assertEqual((ov.segments[0].start, ov.segments[0].end), (3.0, 3.6))

    def test_missing_window_errors(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _ = _run(["overlay", "-o", os.path.join(d, "o.yml"),
                          "--add", "kind=image;src=a.png"])
            self.assertEqual(rc, 2)


class OverlayCardCLITests(unittest.TestCase):
    def test_structures_from_captured_page_json(self):
        with tempfile.TemporaryDirectory() as d:
            page = os.path.join(d, "page.json")
            Path(page).write_text(json.dumps({
                "url": "https://www.theverge.com/2026/x",
                "title": "A headline about a thing",
                "paragraphs": ["The lead paragraph is short and clear."],
                "site_name": "The Verge",
                "byline": "By J. Writer",
                "top_image": "https://cdn/x.jpg",
            }))
            out = os.path.join(d, "card.json")
            rc, _ = _run(["overlay-card", "https://www.theverge.com/2026/x",
                          "-o", out, "--from-json", page])
            self.assertEqual(rc, 0)
            c = CardContent.read(out)
            self.assertEqual(c.citation, "theverge.com")
            self.assertEqual(c.footer, "By J. Writer")


class OverlayRenderCLITests(unittest.TestCase):
    def test_dry_run_prints_ffmpeg(self):
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "t.png"
            make_template_png(png, 1080, 1920, safe_rect=(40, 160, 1040, 1760))
            sz = os.path.join(d, "safezone.json")
            Path(sz).write_text(generate_spec(str(png), profile="reels-9x16").to_json())

            ovp = os.path.join(d, "overlay.def.yml")
            _run(["overlay", "-o", ovp,
                  "--add", "kind=image;src=a.png;start=1;end=4;placement=bottom-half"])

            occ = os.path.join(d, "occ.json")
            rc, out = _run([
                "overlay-render", ovp, "-i", os.path.join(d, "base.mp4"),
                "-o", os.path.join(d, "out.mp4"), "--safezone", sz,
                "--occupancy", occ, "--dry-run",
            ])
            self.assertEqual(rc, 0)
            self.assertIn("ffmpeg", out)
            self.assertTrue(os.path.exists(occ))  # occupancy written even on dry-run


class SchemaCLIConsistencyTests(unittest.TestCase):
    def test_overlay_task_subcommands_are_real_cli_commands(self):
        parser = build_parser()
        # the subparser choices (real CLI commands)
        choices = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
        sch = S.build_schema()
        for t in sch.tasks:
            if t.step == "overlay":
                self.assertIn(t.subcommand, choices, t.id)

    def test_resolved_argv_parses(self):
        sch = S.build_schema()
        parser = build_parser()
        argv = S.resolve_argv(
            sch, "overlay.render", {"crf": 18, "dry_run": False},
            {"overlay.def": "o.yml", "base": "b.mp4", "overlay.composite": "c.mp4",
             "safezone.def": "s.json", "overlay.occupancy": "occ.json"},
        )
        # argv[0] is the program name; parse the rest as CLI args
        ns = parser.parse_args(argv[1:])
        self.assertEqual(ns.overlays, "o.yml")
        self.assertEqual(ns.input, "b.mp4")
        self.assertEqual(ns.safezone, "s.json")


if __name__ == "__main__":
    unittest.main()
