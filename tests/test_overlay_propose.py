"""Transcript→window proposer (INI-089) — pure matching logic."""

import unittest

from video_pipeline.roughcut.transcript import Transcript, Word
from video_pipeline.overlay.propose import propose_window


def _t(*pairs):
    """Build a Transcript from (text, start, end) triples."""
    return Transcript(words=[Word(text=t, start=s, end=e) for (t, s, e) in pairs])


class PhraseMatchTests(unittest.TestCase):
    def setUp(self):
        # "look at this amazing chart over here" — chart at [3.0, 3.6)
        self.tr = _t(
            ("Look", 0.0, 0.4),
            ("at", 0.4, 0.6),
            ("this", 0.6, 0.9),
            ("amazing", 0.9, 1.5),
            ("chart", 3.0, 3.6),
            ("over", 3.6, 3.9),
            ("here", 3.9, 4.2),
        )

    def test_single_keyword_window(self):
        w = propose_window(self.tr, "chart")
        self.assertEqual(w, (3.0, 3.6))

    def test_exact_phrase_window(self):
        w = propose_window(self.tr, "amazing chart")
        self.assertEqual(w, (0.9, 3.6))

    def test_punctuation_insensitive(self):
        w = propose_window(self.tr, "chart!")
        self.assertEqual(w, (3.0, 3.6))

    def test_padding_applied_and_clamped(self):
        w = propose_window(self.tr, "chart", pad_lead=0.2, pad_tail=0.2)
        self.assertEqual(w, (2.8, 3.8))
        # clamp at the transcript end
        w2 = propose_window(self.tr, "here", pad_tail=5.0)
        self.assertEqual(w2[1], 4.2)

    def test_min_duration_stretches_short_match(self):
        w = propose_window(self.tr, "chart", min_duration=2.0)
        self.assertIsNotNone(w)
        self.assertGreaterEqual(round(w[1] - w[0], 3), 2.0)

    def test_no_match_returns_none(self):
        self.assertIsNone(propose_window(self.tr, "spaceship"))

    def test_empty_query_or_transcript(self):
        self.assertIsNone(propose_window(self.tr, "   "))
        self.assertIsNone(propose_window(_t(), "chart"))


class KeywordFallbackTests(unittest.TestCase):
    def test_keywords_when_phrase_not_consecutive(self):
        # "rates" and "inflation" both present but not adjacent; fallback spans them
        tr = _t(
            ("The", 0.0, 0.2),
            ("central", 0.2, 0.6),
            ("bank", 0.6, 0.9),
            ("cut", 0.9, 1.1),
            ("rates", 1.1, 1.5),
            ("citing", 1.5, 1.9),
            ("falling", 1.9, 2.3),
            ("inflation", 2.3, 2.9),
        )
        w = propose_window(tr, "rates inflation")
        self.assertEqual(w, (1.1, 2.9))

    def test_stopwords_do_not_anchor(self):
        # "the" appears first; query "the chart" should still locate on "chart"
        tr = _t(
            ("the", 0.0, 0.2),
            ("intro", 0.2, 0.6),
            ("the", 2.0, 2.2),
            ("chart", 2.2, 2.8),
        )
        w = propose_window(tr, "the chart")
        # exact phrase "the chart" is consecutive at index 2..3
        self.assertEqual(w, (2.0, 2.8))

    def test_cluster_break_on_long_gap(self):
        # keyword appears in two clusters; the one covering more distinct keywords wins
        tr = _t(
            ("demo", 0.0, 0.4),
            ("later", 0.4, 0.8),
            # long gap (sentence boundary)
            ("the", 5.0, 5.2),
            ("live", 5.2, 5.6),
            ("demo", 5.6, 6.0),
        )
        # query "live demo": phrase match is the second cluster
        w = propose_window(tr, "live demo")
        self.assertEqual(w, (5.2, 6.0))


if __name__ == "__main__":
    unittest.main()
