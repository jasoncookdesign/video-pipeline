"""Beat timing (#62 part A): planned durations, or transcript alignment + cut remap."""

import unittest

from tests._util import REPO_ROOT

from video_pipeline.roughcut.decision import DecisionList, Segment
from video_pipeline.roughcut.transcript import Transcript, Word
from video_pipeline.visuals.spec import load_visuals
from video_pipeline.visuals.timing import (
    BeatWindow,
    remap_windows,
    windows_from_durations,
    windows_from_transcript,
)
from video_pipeline.fcpxml.timeline import remap_window, kept_spans

REEL_0227 = REPO_ROOT / "tests" / "fixtures" / "visuals" / "dh-reel-0227.visuals.json"
FPS = 30


def _transcript(lines):
    """[(start, "words ...")] -> word-level Transcript, 0.25 s per word."""
    words = []
    for start, text in lines:
        t = start
        for w in text.split():
            words.append(Word(text=w, start=round(t, 3), end=round(t + 0.2, 3)))
            t += 0.25
    return Transcript(words=tuple(words))


class DurationTimingTests(unittest.TestCase):
    def test_cumulative_from_zero(self):
        w = windows_from_durations(load_visuals(REEL_0227))
        self.assertEqual([x.beat_id for x in w][:3], ["B01", "B02", "B03"])
        self.assertEqual((w[0].start, w[0].end), (0.0, 4.5))
        self.assertEqual((w[1].start, w[1].end), (4.5, 10.5))
        self.assertEqual((w[2].start, w[2].end), (10.5, 14.5))
        self.assertEqual(w[-1].end, 49.5)
        self.assertTrue(all(x.basis == "duration" for x in w))


class TranscriptTimingTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_visuals(REEL_0227)
        # The recording starts late, runs slower than planned, and repeats "tycoon".
        self.tr = _transcript([
            (2.0, "Live Nation helped make a festival game for Roblox. Guess which job they gave you."),
            (8.0, "It's called Music Festival Tycoon. Made with a studio called Livewire. You build the festival. You manage the festival."),
            (16.0, "Tycoon. They named it Tycoon."),
            (20.0, "I'm waiting for the expansion pack"),
            (22.5, "where the wristband has six tiers and the free party is a locked achievement."),
            (27.0, "And look, building things is fun. Nobody playing it is doing anything wrong."),
            (32.0, "But a festival game on Roblox is a strange thing."),
        ])

    def test_beats_start_where_their_line_is_spoken(self):
        w = {x.beat_id: x for x in windows_from_transcript(self.spec, self.tr)}
        self.assertEqual(w["B01"].start, 2.0)
        self.assertEqual(w["B02"].start, 8.0)
        self.assertEqual(w["B03"].start, 16.0)  # not the earlier "Tycoon" in B02
        self.assertEqual(w["B04"].start, 20.0)
        self.assertEqual(w["B05"].start, 22.5)
        self.assertEqual(w["B03"].basis, "transcript")

    def test_windows_are_contiguous_and_monotonic(self):
        w = windows_from_transcript(self.spec, self.tr)
        for a, b in zip(w, w[1:]):
            self.assertEqual(a.end, b.start)
            self.assertLess(a.start, b.start)

    def test_a_single_shared_keyword_is_not_a_match(self):
        # Only "festival" from B01's line is spoken (inside B02's line): weak match.
        tr = _transcript([(3.0, "It's called Music Festival Tycoon. Made with a studio called Livewire. You build the festival. You manage the festival.")])
        w = {x.beat_id: x for x in windows_from_transcript(self.spec, tr)}
        self.assertEqual(w["B02"].start, 3.0)
        self.assertEqual(w["B02"].basis, "transcript")
        self.assertNotIn("B01", w)  # no room before B02's anchor -> dropped

    def test_unspoken_beat_follows_the_previous_with_its_planned_length(self):
        # B08/B09 lines are missing from this transcript -> fall back to duration.
        w = {x.beat_id: x for x in windows_from_transcript(self.spec, self.tr)}
        self.assertEqual(w["B08"].basis, "fallback")
        self.assertAlmostEqual(w["B08"].start, w["B07"].start + 11.0, places=3)
        self.assertAlmostEqual(w["B09"].end - w["B09"].start, 5.0, places=3)


class RemapTests(unittest.TestCase):
    def setUp(self):
        segs = [Segment(index=0, start=0.0, end=2.0, keep=False, reason="silence"),
                Segment(index=1, start=2.0, end=10.0, keep=True),
                Segment(index=2, start=10.0, end=12.0, keep=False, reason="silence"),
                Segment(index=3, start=12.0, end=20.0, keep=True)]
        self.decision = DecisionList(source="a.mp4", segments=segs, profile="reels-9x16")

    def test_remap_window_shared_helper(self):
        spans = kept_spans(self.decision, FPS)
        self.assertEqual(remap_window(spans, 3.0, 5.0, FPS), (1.0, 3.0))
        self.assertEqual(remap_window(spans, 9.0, 13.0, FPS), (7.0, 9.0))  # spans the cut
        self.assertIsNone(remap_window(spans, 10.2, 11.8, FPS))           # fully dropped

    def test_windows_move_with_the_cut(self):
        src = [BeatWindow("B01", 2.0, 9.0, "transcript"),
               BeatWindow("B02", 9.0, 11.0, "transcript"),
               BeatWindow("B03", 12.5, 16.0, "transcript"),
               BeatWindow("B04", 10.5, 11.5, "fallback")]  # inside the dropped gap
        out = {w.beat_id: w for w in remap_windows(src, self.decision, FPS)}
        self.assertEqual((out["B01"].start, out["B01"].end), (0.0, 7.0))
        self.assertEqual((out["B02"].start, out["B02"].end), (7.0, 8.0))
        self.assertEqual((out["B03"].start, out["B03"].end), (8.5, 12.0))
        self.assertNotIn("B04", out)


if __name__ == "__main__":
    unittest.main()
