"""TDD for the rough-cut phase (INI-085 Phase 2).

The pure logic — filler/false-start/silence proposal, the decision-file round
trip, and the FFmpeg trim/concat command — is fully tested here. mlx-whisper
transcription and the real-footage render are the daily-driver steps and are
intentionally out of the sandbox suite.
"""

import unittest

from tests._util import REPO_ROOT  # noqa: F401  (ensures src/ on path)
from video_pipeline.roughcut import (
    DecisionList,
    FixedTranscriber,
    ProposeConfig,
    Segment,
    Transcript,
    Word,
    concat_filtergraph,
    ffmpeg_roughcut_command,
    parse_silencedetect,
    propose,
    speech_regions,
    transcript_from_speech_regions,
    transcript_from_whisper_dict,
)
from video_pipeline.roughcut.propose import R_FILLER, R_FALSE_START, R_SILENCE


def W(text, start, end):
    return Word(text=text, start=start, end=end)


def _covers_clip(decision, duration):
    """Segments form a gap-free, ordered partition of [0, duration]."""
    segs = decision.segments
    assert abs(segs[0].start - 0.0) < 1e-6, segs[0].start
    assert abs(segs[-1].end - duration) < 1e-3, segs[-1].end
    for a, b in zip(segs, segs[1:]):
        assert abs(a.end - b.start) < 1e-6, (a.end, b.start)
        assert b.start >= a.start


# ── transcript model ──────────────────────────────────────────────────────────

class TestTranscript(unittest.TestCase):
    def test_duration_and_text(self):
        t = Transcript([W("Hey", 0.0, 0.4), W("there", 0.4, 0.9)])
        self.assertAlmostEqual(t.duration, 0.9)
        self.assertEqual(t.text(), "Hey there")

    def test_normalized_strips_punctuation(self):
        self.assertEqual(W("Um,", 0, 1).normalized(), "um")
        self.assertEqual(W("You're", 0, 1).normalized(), "you're")

    def test_text_between_uses_word_centre(self):
        t = Transcript([W("a", 0.0, 1.0), W("b", 2.0, 3.0), W("c", 4.0, 5.0)])
        self.assertEqual(t.text_between(1.5, 3.5), "b")

    def test_from_whisper_dict_segments_shape(self):
        data = {
            "language": "en",
            "segments": [
                {"words": [
                    {"word": " Hey", "start": 0.0, "end": 0.4},
                    {"word": " there", "start": 0.4, "end": 0.9},
                ]},
                {"words": [{"word": " friend", "start": 1.0, "end": 1.5}]},
            ],
        }
        t = transcript_from_whisper_dict(data)
        self.assertEqual(t.language, "en")
        self.assertEqual([w.text for w in t.words], ["Hey", "there", "friend"])
        self.assertAlmostEqual(t.words[0].start, 0.0)

    def test_from_whisper_dict_skips_missing_timestamps(self):
        data = {"words": [{"word": "ok", "start": 0.0, "end": 0.5},
                          {"word": "bad", "start": None, "end": 1.0}]}
        t = transcript_from_whisper_dict(data)
        self.assertEqual([w.text for w in t.words], ["ok"])

    def test_fixed_transcriber(self):
        t = FixedTranscriber([W("hi", 0, 1)]).transcribe("anything.mp4")
        self.assertEqual(t.text(), "hi")


# ── proposal: trim_filler = False (DoD) ───────────────────────────────────────

class TestTrimFillerOff(unittest.TestCase):
    def test_no_speech_edits_single_keep(self):
        # a DJ record-style clip: words present, but trimming disabled
        t = Transcript([W("um", 0.2, 0.6), W("yeah", 5.0, 5.4), W("nice", 9.0, 9.5)])
        d = propose(t, duration=12.0, config=ProposeConfig(trim_filler=False))
        self.assertEqual(len(d.segments), 1)
        seg = d.segments[0]
        self.assertTrue(seg.keep)
        self.assertEqual((seg.start, seg.end), (0.0, 12.0))
        self.assertFalse(d.trim_filler)
        # audio continuity: the whole clip survives, nothing dropped
        self.assertAlmostEqual(d.kept_duration(), 12.0)

    def test_empty_transcript_keeps_whole_clip(self):
        d = propose(Transcript([]), duration=8.0)
        self.assertEqual(len(d.segments), 1)
        self.assertTrue(d.segments[0].keep)
        self.assertAlmostEqual(d.segments[0].end, 8.0)


# ── proposal: trim_filler = True ──────────────────────────────────────────────

class TestProposeFiller(unittest.TestCase):
    def test_drops_filler_word(self):
        t = Transcript([
            W("Hello", 0.0, 0.5),
            W("um", 0.55, 0.9),
            W("world", 0.95, 1.4),
        ])
        d = propose(t, duration=1.4)
        _covers_clip(d, 1.4)
        dropped = [s for s in d.segments if not s.keep]
        self.assertTrue(any(s.reason == R_FILLER for s in dropped))
        # the "um" timespan is not inside any kept segment
        for s in d.kept():
            self.assertFalse(s.start <= 0.7 <= s.end and "um" in s.text.split())

    def test_keeps_real_content(self):
        t = Transcript([W("real", 0.0, 0.5), W("content", 0.5, 1.0)])
        d = propose(t, duration=1.0)
        self.assertEqual(d.kept_duration(), d.source_duration())  # nothing to cut

    def test_extra_filler_words(self):
        t = Transcript([W("basically", 0.0, 0.6), W("done", 0.65, 1.0)])
        cfg = ProposeConfig(extra_filler_words=frozenset({"basically"}))
        d = propose(t, duration=1.0, config=cfg)
        self.assertTrue(any(s.reason == R_FILLER for s in d.segments if not s.keep))


class TestProposeSilence(unittest.TestCase):
    def test_drops_mid_dead_air(self):
        t = Transcript([W("start", 0.0, 0.5), W("end", 4.0, 4.5)])  # 3.5s gap
        d = propose(t, duration=4.5)
        _covers_clip(d, 4.5)
        silence = [s for s in d.segments if not s.keep and s.reason == R_SILENCE]
        self.assertTrue(silence)
        # two kept runs separated by the silence
        self.assertEqual(len(d.kept()), 2)

    def test_small_gap_not_trimmed(self):
        t = Transcript([W("close", 0.0, 0.5), W("words", 0.7, 1.2)])  # 0.2s gap
        d = propose(t, duration=1.2, config=ProposeConfig(silence_gap_s=0.6))
        self.assertEqual(len(d.kept()), 1)  # one continuous run

    def test_trailing_dead_air_trimmed(self):
        t = Transcript([W("bye", 0.0, 0.5)])
        d = propose(t, duration=5.0)
        last = d.segments[-1]
        self.assertFalse(last.keep)
        self.assertEqual(last.reason, R_SILENCE)


class TestProposeFalseStart(unittest.TestCase):
    def test_drops_immediate_repeat(self):
        t = Transcript([
            W("I", 0.0, 0.2),
            W("I", 0.25, 0.45),     # restart
            W("think", 0.5, 0.9),
        ])
        d = propose(t, duration=0.9)
        dropped = [s for s in d.segments if not s.keep]
        self.assertTrue(any(s.reason == R_FALSE_START for s in dropped))

    def test_repeat_far_apart_is_kept(self):
        t = Transcript([W("go", 0.0, 0.4), W("go", 3.0, 3.4)])  # not a restart
        cfg = ProposeConfig(false_start_max_gap_s=0.5)
        d = propose(t, duration=3.4, config=cfg)
        self.assertFalse(any(s.reason == R_FALSE_START for s in d.segments))

    def test_false_start_detection_disabled(self):
        t = Transcript([W("I", 0.0, 0.2), W("I", 0.25, 0.45), W("go", 0.5, 0.9)])
        d = propose(t, duration=0.9, config=ProposeConfig(detect_false_starts=False))
        self.assertFalse(any(s.reason == R_FALSE_START for s in d.segments))


# ── decision file round-trip (the product) ────────────────────────────────────

class TestDecisionRoundTrip(unittest.TestCase):
    def _sample(self):
        t = Transcript([
            W("Hello", 0.0, 0.5), W("um", 0.55, 0.9), W("world", 0.95, 1.4),
            W("today", 5.0, 5.5),  # after a big gap
        ])
        return propose(t, duration=6.0, source="clip.mp4", profile="reels-9x16")

    def test_yaml_round_trips_losslessly(self):
        d = self._sample()
        reloaded = DecisionList.from_yaml(d.to_yaml())
        self.assertEqual(reloaded.source, "clip.mp4")
        self.assertEqual(reloaded.profile, "reels-9x16")
        self.assertEqual(len(reloaded.segments), len(d.segments))
        for a, b in zip(d.segments, reloaded.segments):
            self.assertEqual((a.start, a.end, a.keep, a.reason, a.text),
                             (b.start, b.end, b.keep, b.reason, b.text))

    def test_header_is_present_and_parseable(self):
        d = self._sample()
        text = d.to_yaml()
        self.assertIn("THIS FILE IS THE PRODUCT", text)
        self.assertTrue(text.lstrip().startswith("#"))
        DecisionList.from_yaml(text)  # comments don't break parsing

    def test_edit_changes_the_cut(self):
        # round-trip DoD: flipping keep changes what renders
        d = self._sample()
        kept_before = len(d.kept())
        text = d.to_yaml()
        # CEO hand-edit: drop the first kept segment
        reloaded = DecisionList.from_yaml(text)
        first_kept = next(s for s in reloaded.segments if s.keep)
        first_kept.keep = False
        self.assertEqual(len(reloaded.kept()), kept_before - 1)
        cmd_before = ffmpeg_roughcut_command("in.mp4", "out.mp4", d)
        cmd_after = ffmpeg_roughcut_command("in.mp4", "out.mp4", reloaded)
        self.assertNotEqual(cmd_before, cmd_after)


# ── render command ────────────────────────────────────────────────────────────

class TestRenderCommand(unittest.TestCase):
    def test_only_kept_segments_in_filtergraph(self):
        d = DecisionList(
            source="x.mp4",
            segments=[
                Segment(0, 0.0, 1.0, keep=True, text="a"),
                Segment(1, 1.0, 1.5, keep=False, reason="filler", text="um"),
                Segment(2, 1.5, 3.0, keep=True, text="b"),
            ],
        )
        fg = concat_filtergraph(d.kept())
        self.assertIn("concat=n=2:v=1:a=1", fg)
        self.assertIn("trim=start=0.000:end=1.000", fg)
        self.assertIn("trim=start=1.500:end=3.000", fg)
        self.assertNotIn("end=1.500", fg)  # the filler segment is absent

    def test_command_shape(self):
        d = DecisionList(source="x.mp4",
                         segments=[Segment(0, 0.0, 2.0, keep=True, text="a")])
        cmd = ffmpeg_roughcut_command("in.mp4", "out.mp4", d)
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-filter_complex", cmd)
        self.assertIn("[outv]", cmd)
        self.assertIn("[outa]", cmd)
        self.assertEqual(cmd[-1], "out.mp4")

    def test_no_kept_segments_raises(self):
        d = DecisionList(source="x.mp4",
                         segments=[Segment(0, 0.0, 2.0, keep=False, reason="silence")])
        with self.assertRaises(ValueError):
            ffmpeg_roughcut_command("in.mp4", "out.mp4", d)


# ── silence-based fallback (no ASR) ───────────────────────────────────────────

_SILENCE_LOG = """
[silencedetect @ 0x1] silence_start: 0.315
[silencedetect @ 0x1] silence_end: 1.751 | silence_duration: 1.436
[silencedetect @ 0x1] silence_start: 4.803
[silencedetect @ 0x1] silence_end: 5.577 | silence_duration: 0.774
[silencedetect @ 0x1] silence_start: 9.000
"""  # note: trailing silence_start with no end (runs to EOF)


class TestSilenceParse(unittest.TestCase):
    def test_parses_pairs_and_trailing_open_silence(self):
        sils = parse_silencedetect(_SILENCE_LOG)
        self.assertEqual(sils[0], (0.315, 1.751))
        self.assertEqual(sils[1], (4.803, 5.577))
        self.assertEqual(sils[2], (9.000, None))  # open -> EOF

    def test_speech_regions_complement(self):
        sils = [(0.315, 1.751), (4.803, 5.577), (9.0, None)]
        regs = speech_regions(sils, duration=10.0)
        # speech: [0,0.315],[1.751,4.803],[5.577,9.0] ; 9.0->10 is silence (open)
        self.assertEqual(regs[0], (0.0, 0.315))
        self.assertEqual(regs[1], (1.751, 4.803))
        self.assertEqual(regs[2], (5.577, 9.0))
        self.assertTrue(all(b > a for a, b in regs))

    def test_min_speech_filters_slivers(self):
        sils = [(0.30, 0.305)]  # a 0.005s "speech" sliver around it
        regs = speech_regions(sils, duration=2.0, min_speech_s=0.1)
        # the [0,0.30] region survives; the tiny [0.305,2.0]? that's 1.695 -> survives
        self.assertTrue(all((b - a) >= 0.1 for a, b in regs))

    def test_transcript_markers_are_distinct(self):
        t = transcript_from_speech_regions([(0.0, 1.0), (1.2, 2.0), (2.1, 3.0)])
        norms = [w.normalized() for w in t.words]
        self.assertEqual(len(set(norms)), len(norms))  # all distinct

    def test_propose_on_silence_transcript_trims_only_dead_air(self):
        # speech regions separated by a 0.7s gap -> dead air trimmed, no false-start
        regs = [(0.0, 2.0), (2.7, 4.0)]
        t = transcript_from_speech_regions(regs)
        d = propose(t, duration=4.0)
        # exactly the two speech regions kept, the gap dropped as silence
        self.assertEqual(len(d.kept()), 2)
        reasons = {s.reason for s in d.segments if not s.keep}
        self.assertEqual(reasons, {R_SILENCE})

    def test_distinct_markers_avoid_false_start_on_small_gaps(self):
        # regression: a sub-0.5s gap between identical-looking regions must NOT be
        # misread as a false-start (markers are numbered, hence distinct).
        regs = [(0.0, 1.0), (1.3, 2.0)]  # 0.3s gap < false_start_max_gap_s
        t = transcript_from_speech_regions(regs)
        d = propose(t, duration=2.0, config=ProposeConfig(silence_gap_s=0.2))
        self.assertFalse(any(s.reason == R_FALSE_START for s in d.segments))
        self.assertEqual(len(d.kept()), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
