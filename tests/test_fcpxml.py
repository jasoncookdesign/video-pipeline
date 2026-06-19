"""Phase-5 FCPXML handoff tests — cut timeline, cue remap, and document.

All pure; no native toolchain and no media files. Builds small synthetic
decision + caption files and exercises the base-cut layout, the source->cut
time remap, and the assembled FCPXML's structure (parsed back with ElementTree).
"""

import unittest
import xml.etree.ElementTree as ET

from tests._util import REPO_ROOT  # noqa: F401  (ensures src/ on path)

from video_pipeline.captions.cue import CaptionTrack, Cue
from video_pipeline.roughcut.decision import DecisionList, Segment
from video_pipeline.fcpxml.document import (
    assemble_fcpxml,
    file_uri,
    frame_duration_str,
    time_str,
)
from video_pipeline.fcpxml.timeline import (
    build_base_cut,
    cut_duration,
    kept_spans,
    quantize,
    remap_track,
    source_to_cut,
)

FPS = 30


def make_decision(segments, source="2026-06-03-reel.mp4", trim_filler=True):
    segs = [
        Segment(index=i, start=s, end=e, keep=k, reason=r, text=t)
        for i, (s, e, k, r, t) in enumerate(segments)
    ]
    return DecisionList(source=source, segments=segs, profile="reels-9x16",
                        trim_filler=trim_filler)


def make_track(cues, source="2026-06-03-reel.mp4"):
    out = []
    for i, (s, e, text) in enumerate(cues):
        out.append(Cue(index=i, start=s, end=e, words=text.split()))
    return CaptionTrack(source=source, cues=out, identity="dyson-hope",
                        profile="reels-9x16")


# A clip with two dropped regions: keep [0.4,3.0), drop [3.0,3.5), keep
# [3.5,6.0), drop [6.0,6.4) (trailing). Total kept = 2.6 + 2.5 = 5.1s.
TWO_CUT = [
    (0.0, 0.4, False, "silence", ""),
    (0.4, 3.0, True, "", "first kept span"),
    (3.0, 3.5, False, "filler", "um"),
    (3.5, 6.0, True, "", "second kept span"),
    (6.0, 6.4, False, "silence", ""),
]


# ── frame-time helpers ───────────────────────────────────────────────────────

class FrameTimeTests(unittest.TestCase):
    def test_frame_duration(self):
        self.assertEqual(frame_duration_str(30), "1/30s")
        self.assertEqual(frame_duration_str(24), "1/24s")
        with self.assertRaises(ValueError):
            frame_duration_str(0)

    def test_time_str_is_frame_exact(self):
        self.assertEqual(time_str(0.0, 30), "0s")
        self.assertEqual(time_str(1.0, 30), "30/30s")     # 30 frames
        self.assertEqual(time_str(0.5, 30), "15/30s")     # 15 frames
        # a non-frame time snaps to the nearest frame
        self.assertEqual(time_str(0.49, 30), "15/30s")    # 14.7 -> 15

    def test_quantize(self):
        self.assertEqual(quantize(0.49, 30), round(15 / 30, 6))
        self.assertEqual(quantize(2.0, 30), 2.0)

    def test_file_uri(self):
        self.assertTrue(file_uri("/tmp/a b.mp4").startswith("file:///"))
        self.assertIn("a%20b.mp4", file_uri("/tmp/a b.mp4"))
        self.assertEqual(file_uri("file:///x.mp4"), "file:///x.mp4")


# ── base cut ─────────────────────────────────────────────────────────────────

class BaseCutTests(unittest.TestCase):
    def test_clips_are_kept_segments_in_order(self):
        clips = build_base_cut(make_decision(TWO_CUT), FPS)
        self.assertEqual(len(clips), 2)
        self.assertEqual((clips[0].source_in, clips[0].source_out), (0.4, 3.0))
        self.assertEqual((clips[1].source_in, clips[1].source_out), (3.5, 6.0))

    def test_offsets_are_cumulative_and_frame_exact(self):
        clips = build_base_cut(make_decision(TWO_CUT), FPS)
        self.assertEqual(clips[0].offset, 0.0)
        # second clip starts where the first ends on the (compressed) timeline
        self.assertAlmostEqual(clips[1].offset, clips[0].duration, places=6)
        self.assertAlmostEqual(clips[0].duration, 2.6, places=6)
        self.assertAlmostEqual(clips[1].duration, 2.5, places=6)

    def test_empty_keep_raises(self):
        d = make_decision([(0.0, 1.0, False, "silence", "")])
        with self.assertRaises(ValueError):
            build_base_cut(d, FPS)

    def test_subframe_segment_skipped(self):
        # a kept span shorter than a frame is dropped, not emitted as a zero clip
        d = make_decision([
            (0.0, 1.0, True, "", "real"),
            (1.0, 1.0 + 1 / 90.0, True, "", "sub-frame"),
        ])
        clips = build_base_cut(d, FPS)
        self.assertEqual(len(clips), 1)


# ── source -> cut remap ──────────────────────────────────────────────────────

class RemapTests(unittest.TestCase):
    def setUp(self):
        self.spans = kept_spans(make_decision(TWO_CUT), FPS)

    def test_cut_duration(self):
        self.assertAlmostEqual(cut_duration(self.spans), 5.1, places=6)

    def test_time_inside_first_span(self):
        # source 1.4 is 1.0s into the first kept span (which starts at 0.4)
        self.assertAlmostEqual(source_to_cut(self.spans, 1.4), 1.0, places=6)

    def test_time_inside_second_span_is_compressed(self):
        # source 4.5 -> first span is 2.6s, plus 1.0s into the second (starts 3.5)
        self.assertAlmostEqual(source_to_cut(self.spans, 4.5), 3.6, places=6)

    def test_time_in_dropped_region_snaps_forward(self):
        # source 3.2 sits in the dropped [3.0,3.5) gap -> head of the next span
        self.assertAlmostEqual(source_to_cut(self.spans, 3.2), 2.6, places=6)

    def test_cue_inside_kept_is_shifted(self):
        track = make_track([(4.0, 4.8, "second span words")])
        out = remap_track(track, make_decision(TWO_CUT), FPS)
        self.assertEqual(len(out.kept()), 1)
        c = out.cues[0]
        # 4.0 -> 2.6 + (4.0-3.5)=3.1 ; 4.8 -> 3.9
        self.assertAlmostEqual(c.start, 3.1, places=6)
        self.assertAlmostEqual(c.end, 3.9, places=6)

    def test_cue_entirely_in_dropped_region_is_omitted(self):
        track = make_track([(3.1, 3.4, "um")])  # inside the [3.0,3.5) drop
        out = remap_track(track, make_decision(TWO_CUT), FPS)
        self.assertEqual(out.kept(), [])

    def test_cue_straddling_boundary_is_clipped(self):
        # spans the drop: source [2.8, 3.7) -> kept parts compress together
        track = make_track([(2.8, 3.7, "across the cut")])
        out = remap_track(track, make_decision(TWO_CUT), FPS)
        self.assertEqual(len(out.kept()), 1)
        c = out.cues[0]
        # 2.8 -> 2.4 (into span 1); 3.7 -> 2.6 + (3.7-3.5)=2.8
        self.assertAlmostEqual(c.start, 2.4, places=6)
        self.assertAlmostEqual(c.end, 2.8, places=6)

    def test_trim_filler_false_is_identity(self):
        d = make_decision([(0.0, 6.0, True, "", "whole clip")], trim_filler=False)
        track = make_track([(1.0, 1.8, "hello"), (2.0, 2.6, "world")])
        out = remap_track(track, d, FPS)
        self.assertEqual(len(out.kept()), 2)
        self.assertAlmostEqual(out.cues[0].start, 1.0, places=6)
        self.assertAlmostEqual(out.cues[1].end, 2.6, places=6)

    def test_word_times_remapped(self):
        cue = Cue(index=0, start=4.0, end=4.6, words=["two", "words"],
                  word_times=[(4.0, 4.3), (4.3, 4.6)])
        track = CaptionTrack(source="x.mp4", cues=[cue], identity="dyson-hope")
        out = remap_track(track, make_decision(TWO_CUT), FPS)
        c = out.cues[0]
        self.assertEqual(len(c.word_times), 2)
        # 4.0 -> 3.1 (start of cue), first word starts there
        self.assertAlmostEqual(c.word_times[0][0], 3.1, places=6)


# ── assembled FCPXML document ────────────────────────────────────────────────

class DocumentTests(unittest.TestCase):
    def _assemble(self, with_caps=True):
        d = make_decision(TWO_CUT)
        track = make_track([(1.0, 1.8, "first words"),
                            (4.0, 4.8, "second words")]) if with_caps else None
        return assemble_fcpxml(
            d, track,
            reframed_src="/Video/work/clip-9x16.mp4",
            overlay_src="/Video/out/clip.captions.mov" if with_caps else None,
            fps=FPS,
        )

    def test_parses_and_versioned(self):
        xml, _ = self._assemble()
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        self.assertEqual(root.tag, "fcpxml")
        self.assertEqual(root.attrib["version"], "1.10")

    def test_has_doctype_and_declaration(self):
        xml, _ = self._assemble()
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("<!DOCTYPE fcpxml>", xml)

    def test_format_dimensions_and_frame_rate(self):
        xml, _ = self._assemble()
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        fmt = root.find("./resources/format")
        self.assertEqual(fmt.attrib["width"], "1080")
        self.assertEqual(fmt.attrib["height"], "1920")
        self.assertEqual(fmt.attrib["frameDuration"], "1/30s")

    def test_two_assets_when_captioned(self):
        xml, _ = self._assemble(with_caps=True)
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        assets = root.findall("./resources/asset")
        self.assertEqual(len(assets), 2)
        # the overlay asset carries no audio
        overlay = [a for a in assets if a.attrib["id"] == "r3"][0]
        self.assertNotIn("hasAudio", overlay.attrib)

    def test_one_asset_without_captions(self):
        xml, _ = self._assemble(with_caps=False)
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        self.assertEqual(len(root.findall("./resources/asset")), 1)

    def test_spine_has_one_clip_per_kept_segment(self):
        xml, _ = self._assemble()
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        spine = root.find("./library/event/project/sequence/spine")
        base_clips = spine.findall("./asset-clip")
        self.assertEqual(len(base_clips), 2)
        self.assertEqual(base_clips[0].attrib["start"], "12/30s")   # 0.4s
        self.assertEqual(base_clips[0].attrib["offset"], "0s")
        self.assertEqual(base_clips[1].attrib["offset"], "78/30s")  # 2.6s

    def test_caption_is_connected_clip_on_lane_one(self):
        xml, _ = self._assemble()
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        first = root.find("./library/event/project/sequence/spine/asset-clip")
        cap = first.find("./asset-clip")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.attrib["lane"], "1")
        self.assertEqual(cap.attrib["role"], "Captions")
        self.assertEqual(cap.attrib["ref"], "r3")
        # anchored at the first base clip's source in-point so it aligns to t=0
        self.assertEqual(cap.attrib["offset"], "12/30s")
        # spans the whole 5.1s cut
        self.assertEqual(cap.attrib["duration"], time_str(5.1, FPS))

    def test_sequence_duration_is_total_cut(self):
        xml, _ = self._assemble()
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        seq = root.find("./library/event/project/sequence")
        self.assertEqual(seq.attrib["duration"], time_str(5.1, FPS))

    def test_cut_track_returned_and_remapped(self):
        _, cut = self._assemble()
        self.assertEqual(len(cut.kept()), 2)
        # second cue (source 4.0) lands at cut 3.1
        self.assertAlmostEqual(cut.cues[1].start, 3.1, places=6)

    def test_no_overlay_when_all_cues_dropped(self):
        d = make_decision(TWO_CUT)
        track = make_track([(3.1, 3.4, "um")])  # only cue is in a dropped gap
        xml, cut = assemble_fcpxml(
            d, track, reframed_src="/v/clip.mp4",
            overlay_src="/v/cap.mov", fps=FPS,
        )
        root = ET.fromstring(xml.split("<!DOCTYPE fcpxml>")[1])
        self.assertEqual(len(root.findall("./resources/asset")), 1)  # no overlay
        self.assertEqual(cut.kept(), [])


if __name__ == "__main__":
    unittest.main()
