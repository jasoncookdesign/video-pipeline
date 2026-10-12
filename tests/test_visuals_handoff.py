"""Layout-aware handoff (#62 part A): visual clips on V2, placed + timed per beat.

Both serializers: FCP7 XML (Premiere) and FCPXML (Resolve / Final Cut). Split-
layout clips are the graphic panel (1080x960) positioned at the top of the frame;
full-graphic clips fill it; full-presenter beats leave V2 empty. Captions move up
one track/lane when visuals are present and stay put when they are not.
"""

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from tests._util import REPO_ROOT

from video_pipeline.captions.cue import CaptionTrack, Cue
from video_pipeline.fcpxml.document import assemble_fcpxml
from video_pipeline.fcpxml.xmeml import assemble_xmeml
from video_pipeline.roughcut.decision import DecisionList, Segment
from video_pipeline.visuals.placement import build_placements
from video_pipeline.visuals.props import HOLD_TAIL_S
from video_pipeline.visuals.spec import load_visuals
from video_pipeline.visuals.timing import windows_from_durations

REEL_0227 = REPO_ROOT / "tests" / "fixtures" / "visuals" / "dh-reel-0227.visuals.json"
FPS = 30
CLIPS = "/Video/proj/layers/visuals"


def _decision(total=60.0):
    return DecisionList(source="a.mp4", profile="reels-9x16",
                        segments=[Segment(index=0, start=0.0, end=total, keep=True)])


def _two_cut():
    # second clip starts at cut time 20.0 (source 22.0)
    return DecisionList(source="a.mp4", profile="reels-9x16", segments=[
        Segment(index=0, start=0.0, end=20.0, keep=True),
        Segment(index=1, start=20.0, end=22.0, keep=False, reason="silence"),
        Segment(index=2, start=22.0, end=62.0, keep=True)])


def _track():
    return CaptionTrack(source="a.mp4", identity="dyson-hope", profile="reels-9x16",
                        cues=[Cue(index=0, start=1.0, end=2.0, words=["hi"])])


def _placements():
    spec = load_visuals(REEL_0227)
    return build_placements(spec, windows_from_durations(spec), CLIPS, fps=FPS)


class PlacementTests(unittest.TestCase):
    def test_only_remotion_beats_with_a_graphic_are_placed(self):
        placed, notes = _placements()
        self.assertEqual([p.beat_id for p in placed], ["B02", "B03", "B04", "B05"])
        self.assertTrue(any("B01" in n and "real" in n for n in notes))

    def test_geometry_and_time(self):
        placed = {p.beat_id: p for p in _placements()[0]}
        b02 = placed["B02"]
        self.assertEqual(b02.src, f"{CLIPS}/DH-REEL-0227-B02.mov")
        self.assertEqual((b02.x, b02.y, b02.w, b02.h), (0, 0, 1080, 960))
        self.assertEqual((b02.start, b02.end), (4.5, 10.5))
        self.assertEqual(b02.media_duration, 6.0 + HOLD_TAIL_S)
        b03 = placed["B03"]
        self.assertEqual((b03.x, b03.y, b03.w, b03.h), (0, 0, 1080, 1920))

    def test_window_longer_than_the_clip_is_trimmed_with_a_note(self):
        from video_pipeline.visuals.timing import BeatWindow

        spec = load_visuals(REEL_0227)
        wins = [BeatWindow("B04", 0.0, 10.0, "transcript")]  # clip is 2.5 + tail
        placed, notes = build_placements(spec, wins, CLIPS, fps=FPS)
        self.assertEqual(placed[0].end, 2.5 + HOLD_TAIL_S)
        self.assertTrue(any("B04" in n and "longer than" in n for n in notes))


class CutLengthTests(unittest.TestCase):
    def test_placements_are_clamped_to_the_cut(self):
        from video_pipeline.fcpxml.runner import _visual_placements

        placed, info = _visual_placements(str(REEL_0227), _decision(total=12.0), fps=FPS,
                                          clips_dir=CLIPS)
        by = {p.beat_id: p for p in placed}
        self.assertEqual((by["B03"].start, by["B03"].end), (10.5, 12.0))
        self.assertNotIn("B04", by)
        self.assertTrue(any("B03" in n and "end of the cut" in n for n in info["notes"]))

    def test_missing_rendered_clips_are_reported(self):
        from video_pipeline.fcpxml.runner import _visual_placements

        _, info = _visual_placements(str(REEL_0227), _decision(), fps=FPS, clips_dir=CLIPS)
        self.assertTrue(any("not rendered" in n and "B02" in n for n in info["notes"]))


class XmemlVisualTests(unittest.TestCase):
    def _root(self, visuals, captions=True):
        xml, _ = assemble_xmeml(
            _decision(), _track() if captions else None,
            reframed_src="/Video/proj/work/reframed.mp4",
            overlay_src="/Video/proj/layers/captions.mov" if captions else None,
            fps=FPS, visuals=visuals,
        )
        return ET.fromstring(xml.split("<!DOCTYPE xmeml>")[1])

    def _tracks(self, root):
        return root.findall("./sequence/media/video/track")

    def test_v2_holds_one_clipitem_per_placed_beat(self):
        tracks = self._tracks(self._root(_placements()[0]))
        v2 = tracks[1].findall("clipitem")
        self.assertEqual([c.findtext("name") for c in v2],
                         ["DH-REEL-0227-B02", "DH-REEL-0227-B03",
                          "DH-REEL-0227-B04", "DH-REEL-0227-B05"])
        b02 = v2[0]
        self.assertEqual((b02.findtext("start"), b02.findtext("end")), ("135", "315"))
        self.assertEqual((b02.findtext("in"), b02.findtext("out")), ("0", "180"))
        self.assertEqual(b02.findtext("alphatype"), "straight")
        self.assertTrue(b02.find("file/pathurl").text.endswith("/layers/visuals/DH-REEL-0227-B02.mov"))
        sc = b02.find("file/media/video/samplecharacteristics")
        self.assertEqual((sc.findtext("width"), sc.findtext("height")), ("1080", "960"))
        self.assertIsNone(b02.find("file/media/audio"))

    def test_split_clip_is_moved_to_the_top_panel(self):
        b02 = self._tracks(self._root(_placements()[0]))[1].findall("clipitem")[0]
        eff = b02.find("filter/effect")
        self.assertEqual(eff.findtext("effectid"), "basic")
        params = {p.findtext("parameterid"): p for p in eff.findall("parameter")}
        self.assertEqual(params["scale"].findtext("value"), "100")
        center = params["center"].find("value")
        self.assertEqual(float(center.findtext("horiz")), 0.0)
        self.assertEqual(float(center.findtext("vert")), -0.25)  # panel center y=480 of 1920

    def test_full_graphic_clip_is_centered_full_frame(self):
        b03 = self._tracks(self._root(_placements()[0]))[1].findall("clipitem")[1]
        sc = b03.find("file/media/video/samplecharacteristics")
        self.assertEqual((sc.findtext("width"), sc.findtext("height")), ("1080", "1920"))
        params = {p.findtext("parameterid"): p for p in b03.findall("filter/effect/parameter")}
        center = params["center"].find("value")
        self.assertEqual((float(center.findtext("horiz")), float(center.findtext("vert"))), (0.0, 0.0))

    def test_captions_move_to_v3_when_visuals_present(self):
        tracks = self._tracks(self._root(_placements()[0]))
        self.assertEqual(tracks[2].find("clipitem").findtext("name"), "Captions")

    def test_without_visuals_captions_stay_on_v2(self):
        tracks = self._tracks(self._root(None))
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[1].find("clipitem").findtext("name"), "Captions")

    def test_no_placements_means_no_visual_track(self):
        tracks = self._tracks(self._root([], captions=False))
        self.assertEqual(len(tracks), 1)


class FcpxmlVisualTests(unittest.TestCase):
    def _root(self, decision, visuals, captions=True):
        xml, _ = assemble_fcpxml(
            decision, _track() if captions else None,
            reframed_src="/Video/proj/work/reframed.mp4",
            overlay_src="/Video/proj/layers/captions.mov" if captions else None,
            fps=FPS, visuals=visuals,
        )
        return ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])

    def _visual_clips(self, root):
        return [c for c in root.iter("asset-clip") if c.get("videoRole") == "Visuals"]

    def test_visual_assets_carry_their_own_format(self):
        root = self._root(_decision(), _placements()[0])
        fmts = {f.get("id"): f for f in root.findall("./resources/format")}
        assets = {a.get("name"): a for a in root.findall("./resources/asset")}
        b02 = assets["DH-REEL-0227-B02"]
        self.assertEqual((fmts[b02.get("format")].get("width"), fmts[b02.get("format")].get("height")),
                         ("1080", "960"))
        self.assertEqual(b02.get("duration"), f"{round((6.0 + HOLD_TAIL_S) * FPS)}/30s")
        self.assertIsNone(b02.get("hasAudio"))
        self.assertTrue(b02.find("media-rep").get("src").endswith("DH-REEL-0227-B02.mov"))

    def test_connected_on_lane_1_at_the_beat_time(self):
        clips = self._visual_clips(self._root(_decision(), _placements()[0]))
        self.assertEqual([c.get("name") for c in clips][:2], ["DH-REEL-0227-B02", "DH-REEL-0227-B03"])
        b02 = clips[0]
        self.assertEqual(b02.get("lane"), "1")
        self.assertEqual(b02.get("offset"), "135/30s")  # parent-local == cut time (source_in 0)
        self.assertEqual(b02.get("duration"), "180/30s")
        self.assertEqual(b02.find("adjust-conform").get("type"), "none")
        # +25% of frame height = up 480 px: panel center (y=480) vs frame center (960)
        self.assertEqual(b02.find("adjust-transform").get("position"), "0 25")

    def test_full_graphic_has_no_offset(self):
        b03 = self._visual_clips(self._root(_decision(), _placements()[0]))[1]
        self.assertEqual(b03.find("adjust-transform").get("position"), "0 0")

    def test_anchored_to_the_base_clip_that_contains_the_beat(self):
        spec = load_visuals(REEL_0227)
        from video_pipeline.visuals.timing import BeatWindow
        wins = [BeatWindow("B05", 21.0, 24.0, "transcript")]  # cut time, inside clip 2
        placed, _ = build_placements(spec, wins, CLIPS, fps=FPS)
        root = self._root(_two_cut(), placed)
        spine = root.find(".//spine").findall("asset-clip")
        self.assertEqual(self._visual_clips(spine[0]), [])
        b05 = self._visual_clips(spine[1])[0]
        # parent start = source 22.0; cut 21.0 is 1.0 s into it -> local 23.0
        self.assertEqual(b05.get("offset"), "690/30s")

    def test_captions_move_to_lane_2_when_visuals_present(self):
        root = self._root(_decision(), _placements()[0])
        caps = [c for c in root.iter("asset-clip") if c.get("videoRole") == "Captions"][0]
        self.assertEqual(caps.get("lane"), "2")
        root = self._root(_decision(), None)
        caps = [c for c in root.iter("asset-clip") if c.get("videoRole") == "Captions"][0]
        self.assertEqual(caps.get("lane"), "1")


class HandoffCliTests(unittest.TestCase):
    def test_handoff_with_visuals_places_v2(self):
        from video_pipeline.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "work").mkdir()
            _decision().write(root / "work" / "roughcut.decision.yml")
            _track().write(root / "work" / "captions.yml")
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["handoff", "--project", tmp, "--reframed", str(root / "r.mp4"),
                             "--visuals", str(REEL_0227)])
            self.assertEqual(code, 0, err.getvalue())
            xml = (root / "exports" / "premiere" / f"{root.name}.xml").read_text(encoding="utf-8")
            self.assertIn("/layers/visuals/DH-REEL-0227-B05.mov", xml)
            self.assertIn("placed 4 visual clip(s) on V2", out.getvalue())
            self.assertIn("timing: durations", out.getvalue())
            self.assertIn("B01: real asset", out.getvalue())

    def test_handoff_aligns_to_a_transcript_when_given(self):
        from video_pipeline.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "work").mkdir()
            _decision().write(root / "work" / "roughcut.decision.yml")
            _track().write(root / "work" / "captions.yml")
            words, t = [], 3.0
            for w in ("It's called Music Festival Tycoon. Made with a studio called Livewire. "
                      "You build the festival. You manage the festival.").split():
                words.append({"word": w, "start": t, "end": t + 0.2})
                t += 0.25
            (root / "work" / "transcript.json").write_text(
                json.dumps({"segments": [{"words": words}]}), encoding="utf-8")
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["handoff", "--project", tmp, "--reframed", str(root / "r.mp4"),
                             "--visuals", str(REEL_0227), "--format", "fcpxml",
                             "--transcript", str(root / "work" / "transcript.json")])
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn("timing: transcript (1 matched", out.getvalue())
            xml = (root / "exports" / "fcpxml" / f"{root.name}.fcpxml").read_text(encoding="utf-8")
            root_el = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
            b02 = next(c for c in root_el.iter("asset-clip") if c.get("name") == "DH-REEL-0227-B02")
            self.assertEqual(b02.get("offset"), "90/30s")  # spoken at 3.0 s

    def _run(self, *argv):
        from video_pipeline.cli import main
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def _project(self, tmp):
        root = Path(tmp)
        (root / "work").mkdir()
        _decision().write(root / "work" / "roughcut.decision.yml")
        _track().write(root / "work" / "captions.yml")
        return root

    def test_invalid_visuals_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            bad = root / "bad.json"
            bad.write_text('{"schema_version": 1}', encoding="utf-8")
            code, _, err = self._run("handoff", "--project", tmp, "--reframed", "r.mp4",
                                     "--visuals", str(bad))
            self.assertEqual(code, 2)
            self.assertIn("error:", err)

    def test_profile_canvas_mismatch_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp)
            code, _, err = self._run("handoff", "--project", tmp, "--reframed", "r.mp4",
                                     "--visuals", str(REEL_0227), "--profile", "feed-square-1x1")
            self.assertEqual(code, 2)
            self.assertIn("1080x1920", err)


if __name__ == "__main__":
    unittest.main()
