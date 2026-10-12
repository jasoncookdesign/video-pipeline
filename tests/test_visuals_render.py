"""visuals-render (#62 part A): style layer, props contract, named/sized outputs.

The Node renderer is stubbed (a fake ``run`` that records argv and writes the file
the real command would write), so this suite proves naming, sizing, props, and the
skip/dry-run behavior without Node. The real Remotion render of every template is
the local acceptance check — opt in with ``VP_REMOTION_ACCEPTANCE=1``.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from tests._util import REPO_ROOT

from video_pipeline.visuals.props import (
    HOLD_TAIL_S,
    TEMPLATE_COMPOSITIONS,
    beat_to_remotion_props,
    clip_name,
)
from video_pipeline.visuals.render import plan_render, render_visuals, still_times
from video_pipeline.visuals.spec import load_visuals
from video_pipeline.visuals.style import (
    MIN_TYPE_PX,
    VisualStyle,
    load_visual_style,
)

CONFIG = REPO_ROOT / "config"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "visuals"
REEL_0227 = FIXTURES / "dh-reel-0227.visuals.json"
GALLERY = FIXTURES / "template-gallery.visuals.json"


class StyleTests(unittest.TestCase):
    def test_identity_layers_over_global(self):
        g = load_visual_style(CONFIG, None)
        dh = load_visual_style(CONFIG, "dyson-hope")
        self.assertEqual(dh.accent, "#9C97F4")
        self.assertEqual(dh.ground, "#191919")
        self.assertEqual(dh.display_font, "Archivo")
        self.assertEqual(dh.mono_font, "IBM Plex Mono")
        self.assertEqual(dh.body_font, "Inter")
        self.assertNotEqual(g.display_font, dh.display_font)

    def test_overrides_win(self):
        s = load_visual_style(CONFIG, "dyson-hope", overrides={"accent": "#FF0000"})
        self.assertEqual(s.accent, "#FF0000")

    def test_minimum_type_sizes_enforced(self):
        for key, floor in MIN_TYPE_PX.items():
            with self.assertRaises(ValueError, msg=key):
                VisualStyle(**{key: floor - 1})
            VisualStyle(**{key: floor})  # the floor itself is legal

    def test_font_allowlist_enforced(self):
        with self.assertRaises(ValueError):
            VisualStyle(display_font="Comic Sans MS")

    def test_unknown_identity_is_an_error(self):
        with self.assertRaises(ValueError):
            load_visual_style(CONFIG, "dyson-hopee")

    def test_color_must_be_hex(self):
        with self.assertRaises(ValueError):
            VisualStyle(accent="periwinkle")


class PropsTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_visuals(REEL_0227)
        self.style = load_visual_style(CONFIG, "dyson-hope")
        self.beats = {b.id: b for b in self.spec.beats}

    def test_clip_name(self):
        self.assertEqual(clip_name("DH-REEL-0227", "B03"), "DH-REEL-0227-B03.mov")

    def test_split_props_are_sized_to_the_graphic_panel(self):
        p = beat_to_remotion_props(self.spec, self.beats["B05"], self.style)
        self.assertEqual(p["dimensions"], {"width": 1080, "height": 960})
        self.assertEqual(p["safeBox"], {"x": 35, "y": 250, "width": 1010, "height": 710})
        self.assertEqual(p["template"], "game-hud")
        self.assertTrue(p["parody"])
        self.assertEqual(p["props"]["stack"]["items"][0], "GA")
        self.assertEqual(p["style"]["accent"], "#9C97F4")
        self.assertEqual(p["fps"], 30)
        self.assertEqual(p["beatFrames"], 135)  # 4.5 s at 30 fps
        self.assertEqual(p["durationInFrames"], round((4.5 + HOLD_TAIL_S) * 30))

    def test_full_graphic_props_fill_the_frame(self):
        p = beat_to_remotion_props(self.spec, self.beats["B03"], self.style)
        self.assertEqual(p["dimensions"], {"width": 1080, "height": 1920})
        self.assertEqual(p["safeBox"], {"x": 35, "y": 250, "width": 880, "height": 1220})
        self.assertFalse(p["parody"])

    def test_non_remotion_beat_rejected(self):
        with self.assertRaises(ValueError):
            beat_to_remotion_props(self.spec, self.beats["B01"], self.style)

    def test_schema_python_and_remotion_agree_on_templates(self):
        schema = json.loads((REPO_ROOT / "schema" / "visuals.schema.json").read_text(encoding="utf-8"))
        enum = schema["definitions"]["beat"]["properties"]["template"]["enum"]
        self.assertEqual(set(TEMPLATE_COMPOSITIONS), set(enum))
        for tid in enum:
            self.assertIn(f"props-{tid}", schema["definitions"])
        tsx = (REPO_ROOT / "remotion" / "src" / "visuals" / "Visuals.tsx").read_text(encoding="utf-8")
        for comp in TEMPLATE_COMPOSITIONS.values():
            self.assertIn(f'["{comp}", {comp},', tsx)

    def test_props_carry_the_legibility_floors(self):
        p = beat_to_remotion_props(self.spec, self.beats["B05"], self.style)
        self.assertEqual(p["minType"], MIN_TYPE_PX)


class StillTimesTests(unittest.TestCase):
    def test_evenly_spaced_ending_on_the_settled_frame(self):
        self.assertEqual(still_times(3.0, 30, 3), [1.0, 2.0, 2.967])

    def test_single_still_is_the_settled_end(self):
        self.assertEqual(still_times(4.0, 30, 1), [3.967])

    def test_zero_requested(self):
        self.assertEqual(still_times(4.0, 30, 0), [])


class _StubRun:
    """Stands in for subprocess.run: records argv, writes the file it would write."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, check=True, cwd=None, **kw):
        self.calls.append(list(argv))
        if argv[0] == "npx":
            Path(argv[5]).write_bytes(b"fake-mov")
        elif argv[0] == "ffmpeg":
            Path(argv[-1]).write_bytes(b"fake-png")
        return subprocess.CompletedProcess(argv, 0)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_visuals(REEL_0227)
        self.style = load_visual_style(CONFIG, "dyson-hope")
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_plan_covers_only_remotion_beats(self):
        jobs = plan_render(self.spec, self.tmp / "layers", self.style)
        self.assertEqual([j.beat_id for j in jobs], ["B02", "B03", "B04", "B05"])
        self.assertEqual([j.output.name for j in jobs], [
            "DH-REEL-0227-B02.mov", "DH-REEL-0227-B03.mov",
            "DH-REEL-0227-B04.mov", "DH-REEL-0227-B05.mov"])
        self.assertEqual([j.composition for j in jobs],
                         ["TextCard", "TextCard", "StoreCard", "GameHud"])

    def test_render_writes_named_outputs_and_props(self):
        run = _StubRun()
        results = render_visuals(self.spec, self.tmp / "layers", self.style,
                                 frames=2, frames_dir=self.tmp / "review", run=run)
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertTrue(Path(r["output"]).exists())
            props = json.loads(Path(r["props"]).read_text(encoding="utf-8"))
            self.assertEqual(props["beatId"], r["beat_id"])
            self.assertEqual(len(r["frames"]), 2)
            for png in r["frames"]:
                self.assertTrue(Path(png).exists())
                self.assertTrue(Path(png).name.startswith(f"DH-REEL-0227-{r['beat_id']}-"))
        npx = [c for c in run.calls if c[0] == "npx"]
        self.assertEqual(len(npx), 4)
        b03 = next(c for c in npx if c[5].endswith("DH-REEL-0227-B03.mov"))
        self.assertEqual(b03[4], "TextCard")
        self.assertIn("--codec=prores", b03)
        self.assertIn("--prores-profile=4444", b03)
        # stills are composited at the clip's own size
        ff = [c for c in run.calls if c[0] == "ffmpeg" and "B03" in c[-1]]
        self.assertTrue(any("s=1080x1920" in a for a in ff[0]))
        ff5 = [c for c in run.calls if c[0] == "ffmpeg" and "B05" in c[-1]]
        self.assertTrue(any("s=1080x960" in a for a in ff5[0]))

    def test_dry_run_spawns_nothing_and_writes_nothing(self):
        run = _StubRun()
        results = render_visuals(self.spec, self.tmp / "layers", self.style,
                                 frames=2, frames_dir=self.tmp / "review",
                                 dry_run=True, run=run)
        self.assertEqual(run.calls, [])
        self.assertEqual(len(results), 4)
        self.assertFalse((self.tmp / "layers").exists())
        self.assertEqual(results[0]["argv"][:3], ["npx", "remotion", "render"])

    def test_only_filter(self):
        run = _StubRun()
        results = render_visuals(self.spec, self.tmp / "layers", self.style,
                                 only=["B04"], run=run)
        self.assertEqual([r["beat_id"] for r in results], ["B04"])


class CliTests(unittest.TestCase):
    def _run(self, *argv):
        from video_pipeline.cli import main

        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_against_a_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self._run("visuals-render", str(REEL_0227), "--project", tmp,
                                     "--frames", "2", "--dry-run")
            self.assertEqual(code, 0)
            self.assertIn(str(Path(tmp) / "layers" / "visuals" / "DH-REEL-0227-B05.mov"), out)
            self.assertIn("skipped 5 non-remotion beat(s)", out)
            self.assertIn(str(Path(tmp) / "review" / "visuals"), out)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_unknown_beat_id_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self._run("visuals-render", str(REEL_0227), "--project", tmp,
                                     "--beat", "B99", "--dry-run")
            self.assertEqual(code, 2)
            self.assertIn("B99", err)

    def test_invalid_spec_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.visuals.json"
            data = json.loads(REEL_0227.read_text(encoding="utf-8"))
            data["beats"][1]["props"]["title"] = "X" * 99
            bad.write_text(json.dumps(data), encoding="utf-8")
            code, _, err = self._run("visuals-render", str(bad), "--project", tmp, "--dry-run")
            self.assertEqual(code, 2)
            self.assertIn("beats/1/props/title", err)


@unittest.skipUnless(os.environ.get("VP_REMOTION_ACCEPTANCE") == "1",
                     "real Remotion render — set VP_REMOTION_ACCEPTANCE=1 on the daily driver")
class RemotionAcceptanceTests(unittest.TestCase):
    """Renders every gallery template for real and checks the clip's size/alpha."""

    def test_gallery_renders_at_region_size(self):
        out_root = Path(os.environ.get("VP_ACCEPTANCE_DIR", REPO_ROOT / "review" / "visuals-acceptance"))
        spec = load_visuals(GALLERY)
        style = load_visual_style(CONFIG, spec.identity)
        results = render_visuals(spec, out_root / "layers", style, frames=3,
                                 frames_dir=out_root / "frames")
        for r in results:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height,pix_fmt", "-of", "json", r["output"]],
                check=True, capture_output=True, text=True)
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual((stream["width"], stream["height"]),
                             (r["width"], r["height"]), r["output"])
            self.assertTrue(stream["pix_fmt"].startswith("yuva"), stream["pix_fmt"])


if __name__ == "__main__":
    unittest.main()
