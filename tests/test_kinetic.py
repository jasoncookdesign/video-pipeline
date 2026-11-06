"""Kinetic-text overlay: timing, spec boundary, caption rules, voicing and motion
plan, props, render, CLI.

The Node and FFmpeg processes are stubbed (a fake ``run`` that records argv and
writes the file the real command would write), so this suite proves naming,
sizing, timing, props, and wiring without Node. The real Remotion render is the
local acceptance check — opt in with ``VP_REMOTION_ACCEPTANCE=1``.
"""

import copy
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from tests._util import REPO_ROOT

from video_pipeline.kinetic import caption as caption_mod
from video_pipeline.kinetic import layout, linebreak, timing, voice
from video_pipeline.kinetic.caption import check_caption
from video_pipeline.kinetic.props import (
    COMPOSITION,
    FULL_SAFE,
    ROLE_PX,
    TITLE_BLOCK_H,
    TITLE_GAP,
    clip_name,
    kinetic_to_remotion_props,
)
from video_pipeline.kinetic.render import STILL_FRACTION, plan_render, render_kinetic, still_times
from video_pipeline.kinetic.spec import (
    KineticSpecError,
    load_kinetic,
    parse_kinetic,
    validate_kinetic_dict,
)
from video_pipeline.kinetic.text import norm_token, phrase_indices, phrase_span
from video_pipeline.visuals.style import MIN_TYPE_PX, load_visual_style

CONFIG = REPO_ROOT / "config"
FIX = REPO_ROOT / "tests" / "fixtures" / "kinetic"
SAMPLE = FIX / "sample.kinetic.json"
LAYOUT = FIX / "layout.kinetic.json"
STRESS = FIX / "stress.kinetic.json"
DEFAULTS = FIX / "defaults.kinetic.json"
FPS_SET = (24, 25, 30, 60)


def sample_dict() -> dict:
    return copy.deepcopy(json.loads(SAMPLE.read_text(encoding="utf-8")))


def message_for(data: dict) -> str:
    with unittest.TestCase().assertRaises(KineticSpecError) as ctx:
        validate_kinetic_dict(data)
    return str(ctx.exception)


def text_beat(text, role="statement", voice_="contrast", accents=(), dur=None, **kw):
    """A resolved beat for the voicing tests (built through the real boundary)."""
    beat = {"id": "B", "kind": "text", "text": text, "role": role, "motion": "rise",
            "voice": voice_, "accents": list(accents)}
    if dur:
        beat["duration_s"] = dur
    beat.update(kw)
    d = {"schema_version": 1, "reel_id": "T", "title": "T",
         "canvas": {"w": 1080, "h": 1920, "fps": 30}, "beats": [beat]}
    return parse_kinetic(d).beats[0]


class TimingTests(unittest.TestCase):
    def test_word_count_splits_on_whitespace(self):
        self.assertEqual(timing.word_count("I don't know."), 3)
        self.assertEqual(timing.word_count("  one   two\nthree  "), 3)
        self.assertEqual(timing.word_count(""), 0)

    def test_duration_follows_reading_pace(self):
        text = " ".join(["word"] * 15)
        self.assertAlmostEqual(timing.beat_duration_s(text), timing.LEAD_S + 15 / timing.READ_WPS)

    def test_short_lines_hold_for_the_minimum(self):
        self.assertEqual(timing.beat_duration_s("I don't know."), timing.MIN_BEAT_S)

    def test_more_words_are_never_shorter(self):
        durations = [timing.beat_duration_s(" ".join(["w"] * n)) for n in range(1, 30)]
        self.assertEqual(durations, sorted(durations))
        self.assertGreater(durations[-1], durations[0])

    def test_override_wins_even_when_shorter_than_the_computed_value(self):
        long_text = " ".join(["word"] * 20)
        self.assertEqual(timing.beat_duration_s(long_text, override=3.0), 3.0)


class TextHelperTests(unittest.TestCase):
    def test_norm_token_strips_edge_punctuation_and_lowercases(self):
        self.assertEqual(norm_token('"Don\'t.'), "don't")
        self.assertEqual(norm_token("(Café!)"), "café")
        self.assertEqual(norm_token("..."), "")

    def test_phrase_span_returns_the_token_range_of_the_first_whole_word_match(self):
        text = "There was no stage show. The spectacle was each other."
        self.assertEqual(phrase_span(text, "each other"), (8, 10))
        self.assertEqual(phrase_span(text, "EACH"), (8, 9))
        self.assertIsNone(phrase_span(text, "spec"))
        self.assertIsNone(phrase_span(text, "other each"))
        self.assertIsNone(phrase_span(text, "  "))
        self.assertIsNone(phrase_span(text, "..."))

    def test_phrase_indices_break_after_punctuation(self):
        toks = "In the 90s, I'd walk into a rave.".split()
        self.assertEqual(phrase_indices(toks), [0, 0, 0, 1, 1, 1, 1, 1])

    def test_phrase_indices_see_through_closing_quotes_and_do_not_split_on_inner_periods(self):
        self.assertEqual(phrase_indices(['"I', "don't", 'know."']), [0, 0, 0])
        self.assertEqual(phrase_indices(["It", "costs", "3.5", "now"]), [0, 0, 0, 0])

    def test_a_bare_punctuation_token_does_not_crash(self):
        self.assertEqual(len(phrase_indices(["well", "-", "yes"])), 3)


class LayoutMeasureTests(unittest.TestCase):
    def test_every_printable_ascii_character_has_a_measured_advance(self):
        for table in (layout.DISPLAY_ADVANCE_EM, layout.BODY_ADVANCE_EM):
            for code in range(32, 127):
                self.assertIn(chr(code), table)
                self.assertGreater(table[chr(code)], 0)

    def test_wide_capitals_measure_wider_than_narrow_letters(self):
        self.assertGreater(layout.text_width_em("W", "display"), 3 * layout.text_width_em("i", "display"))
        self.assertGreater(layout.text_width_em("WWW", "display"), layout.text_width_em("iii", "display"))

    def test_unknown_characters_count_as_the_widest_glyph(self):
        wide = max(layout.DISPLAY_ADVANCE_EM.values())
        self.assertEqual(layout.text_width_em("\u4e2d", "display"), wide)

    def test_fit_checks_use_real_widths_not_character_counts(self):
        self.assertTrue(layout.fits_line("statement", "x" * 18))
        self.assertFalse(layout.fits_line("statement", "W" * 18))
        self.assertTrue(layout.fits_line("statement", "W" * 12))
        self.assertFalse(layout.fits_line("statement", "W" * 13))
        self.assertTrue(layout.fits_line("question", "extraordinarily", 1.3))
        self.assertFalse(layout.fits_line("question", "extraordinarily", 1.4))

    def test_fit_title_picks_the_largest_size_that_wraps_into_the_block(self):
        px = layout.fit_title("Where was the DJ?", 160, 72)
        self.assertGreaterEqual(px, 72)
        self.assertLessEqual(px, 160)
        self.assertIsNone(layout.fit_title("W" * 12 + " W", 160, 72))           # one word wider than a line
        self.assertIsNotNone(layout.fit_title("W" * 11 + " " + "W" * 11 + " " + "W" * 11, 160, 72))
        self.assertIsNone(layout.fit_title(" ".join(["WWWWWWWWWWW"] * 4), 160, 72))  # four lines do not fit


class SpecTests(unittest.TestCase):
    def test_sample_loads_and_resolves_timing(self):
        spec = load_kinetic(SAMPLE)
        self.assertEqual(spec.reel_id, "SAMPLE-01")
        self.assertEqual((spec.width, spec.height, spec.fps), (1080, 1920, 30))
        starts = [b.start_s for b in spec.beats]
        durs = [b.duration_s for b in spec.beats]
        self.assertEqual(starts[0], 0.0)
        for i in range(1, len(spec.beats)):
            self.assertAlmostEqual(starts[i], starts[i - 1] + durs[i - 1])
        self.assertAlmostEqual(spec.total_s, sum(durs))
        b1, b2, b3, b4, b5 = spec.beats
        self.assertAlmostEqual(b1.duration_s, timing.beat_duration_s(b1.text))
        self.assertAlmostEqual(b2.duration_s, 2.9)  # 6 words: 0.5 + 6 / 2.5
        self.assertEqual((b3.kind, b3.duration_s), ("space", 2.0))
        self.assertEqual(b5.duration_s, 4.0)  # explicit override
        self.assertEqual(b4.accents[0].text, "each other")
        self.assertEqual((b4.accents[0].weight, b4.accents[0].italic, b4.accents[0].color), (900, True, "accent"))
        self.assertEqual(b4.voice, "contrast")
        self.assertEqual([b.id for b in spec.text_beats()], ["B01", "B02", "B04", "B05"])

    def test_defaults_are_top_anchored_and_left_aligned(self):
        beats = load_kinetic(SAMPLE).beats
        self.assertEqual((beats[0].slot, beats[0].align), ("top", "left"))
        self.assertEqual((beats[1].slot, beats[1].align), ("bottom", "right"))  # deliberate overrides survive

    def test_a_newline_in_the_text_is_an_authored_line_break(self):
        d = sample_dict()
        d["beats"][0]["text"] = "On Fridays,\nI played\nthe same corner."
        spec = parse_kinetic(d)
        self.assertEqual(spec.beats[0].text, "On Fridays,\nI played\nthe same corner.")
        self.assertAlmostEqual(spec.beats[0].duration_s, timing.beat_duration_s("On Fridays, I played the same corner."))

    def test_an_authored_line_too_wide_for_the_measure_is_rejected_with_its_path(self):
        d = sample_dict()
        d["beats"][0]["text"] = "On Fridays I played the same corner for years\nand years"
        self.assertIn("beats/0/text", message_for(d))
        self.assertIn("line 1", message_for(d))

    def test_an_accent_cannot_cross_an_authored_line_break(self):
        d = sample_dict()
        d["beats"][0]["text"] = "On Fridays I played\nthe same corner."
        d["beats"][0]["accents"] = [{"text": "played the", "weight": 900}]
        self.assertIn("beats/0/accents/0", message_for(d))

    def test_every_documented_motion_is_accepted_and_others_name_their_path(self):
        for motion in ("resolve", "rise", "slide", "mask", "gather", "diminish"):
            d = sample_dict()
            d["beats"][0]["motion"] = motion
            validate_kinetic_dict(d)
        d = sample_dict()
        d["beats"][0]["motion"] = "bounce"
        self.assertIn("beats/0", message_for(d))

    def test_title_over_36_chars_rejected_and_36_accepted(self):
        d = sample_dict()
        d["title"] = "I" * 15 + " " + "I" * 15 + " " + "I" * 5  # 37 characters
        self.assertIn("title", message_for(d))
        d = sample_dict()
        d["title"] = "I" * 15 + " " + "I" * 15 + " " + "I" * 4  # 36 characters
        d.pop("caption"); d.pop("topic_terms")
        validate_kinetic_dict(d)

    def test_blank_title_and_blank_text_rejected(self):
        d = sample_dict()
        d["title"] = "   "
        d.pop("caption"); d.pop("topic_terms")
        self.assertIn("title", message_for(d))
        d = sample_dict()
        d["beats"][0]["text"] = "   "
        self.assertIn("beats/0/text", message_for(d))

    def test_beat_text_over_90_chars_rejected(self):
        d = sample_dict()
        d["beats"][0]["text"] = "word " * 19  # 95 chars
        self.assertIn("beats/0/text", message_for(d))

    def test_a_word_longer_than_18_characters_is_rejected_in_beat_text(self):
        d = sample_dict()
        d["beats"][0]["text"] = "Is it " + "x" * 19 + " tonight"
        self.assertIn("beats/0/text", message_for(d))
        d["beats"][0]["text"] = "Is it " + "x" * 18 + " tonight"
        validate_kinetic_dict(d)

    def test_a_title_word_longer_than_15_characters_is_rejected(self):
        d = sample_dict()
        d.pop("caption"); d.pop("topic_terms")
        d["title"] = "A " + "I" * 16
        self.assertIn("title", message_for(d))
        d["title"] = "A " + "I" * 15
        validate_kinetic_dict(d)

    def test_duplicate_ids_rejected_ignoring_case(self):
        d = sample_dict()
        d["beats"][1]["id"] = "b01"
        self.assertIn("duplicate", message_for(d).lower())

    # --- accents ---
    def test_accent_text_must_match_whole_words(self):
        d = sample_dict()
        d["beats"][0]["text"] = "We were partying all night long."
        d["beats"][0]["accents"] = [{"text": "art", "weight": 900}]
        self.assertIn("beats/0/accents/0/text", message_for(d))

    def test_accent_phrase_must_be_consecutive_and_ignores_edge_punctuation_and_case(self):
        d = sample_dict()
        d["beats"][3]["accents"][0]["text"] = "other each"
        self.assertIn("beats/3/accents/0/text", message_for(d))
        d["beats"][3]["accents"][0]["text"] = "EACH OTHER"  # text ends "each other."
        validate_kinetic_dict(d)

    def test_blank_accent_text_or_accent_with_no_styling_rejected(self):
        d = sample_dict()
        d["beats"][3]["accents"] = [{"text": " ", "weight": 900}]
        self.assertIn("beats/3/accents/0", message_for(d))
        d["beats"][3]["accents"] = [{"text": "each other"}]
        self.assertIn("beats/3/accents/0", message_for(d))

    def test_overlapping_accents_rejected(self):
        d = sample_dict()
        d["beats"][3]["accents"] = [{"text": "around each", "weight": 900}, {"text": "each other", "italic": True}]
        self.assertIn("overlap", message_for(d).lower())

    def test_whip_cannot_be_combined_with_a_true_italic(self):
        d = sample_dict()
        d["beats"][3]["accents"] = [{"text": "each other", "italic": True, "treatment": "whip"}]
        self.assertIn("beats/3/accents/0", message_for(d))
        d["beats"][3]["accents"] = [{"text": "each other", "italic": False, "treatment": "whip"}]
        validate_kinetic_dict(d)

    def test_accent_value_ranges_are_enforced(self):
        for bad in ({"weight": 850}, {"scale": 1.5}, {"scale": 0.7}, {"color": "red"}, {"treatment": "spin"}):
            d = sample_dict()
            d["beats"][3]["accents"] = [dict({"text": "each other"}, **bad)]
            self.assertIn("beats/3/accents/0", message_for(d), bad)

    def test_an_accent_too_wide_for_a_line_is_rejected(self):
        d = sample_dict()
        d["beats"][4]["text"] = "Why is it extraordinarily loud tonight?"
        d["beats"][4]["accents"] = [{"text": "extraordinarily", "scale": 1.4}]
        self.assertIn("beats/4/accents/0", message_for(d))
        d["beats"][4]["accents"] = [{"text": "extraordinarily", "scale": 1.3}]
        validate_kinetic_dict(d)

    def test_an_accent_group_is_measured_as_a_unit_because_it_never_wraps(self):
        d = sample_dict()
        d["beats"][0]["text"] = "We went to extraordinarily extraordinary places."
        d["beats"][0]["accents"] = [{"text": "extraordinarily extraordinary", "weight": 900}]
        self.assertIn("beats/0/accents/0", message_for(d))
        d["beats"][0]["accents"] = [{"text": "extraordinarily", "weight": 900}]   # each word alone fits
        validate_kinetic_dict(d)

    def test_wide_capitals_are_rejected_even_when_the_character_count_is_legal(self):
        d = sample_dict()
        d["beats"][0]["text"] = "Is it " + "W" * 18
        self.assertIn("beats/0/text", message_for(d))
        d["beats"][0]["text"] = "Is it " + "W" * 12
        validate_kinetic_dict(d)

    def test_a_title_that_cannot_fit_the_title_block_is_rejected(self):
        d = sample_dict()
        d.pop("caption"); d.pop("topic_terms")
        d["title"] = "W" * 11 + " " + "W" * 11 + " " + "W" * 12   # last word wider than a line
        self.assertIn("title", message_for(d))
        d["title"] = "W" * 11 + " " + "W" * 11 + " " + "W" * 11
        validate_kinetic_dict(d)

    def test_at_most_four_accents(self):
        d = sample_dict()
        d["beats"][0]["text"] = "one two three four five six"
        d["beats"][0]["accents"] = [{"text": w, "weight": 900} for w in ("one", "two", "three", "four", "five")]
        self.assertIn("beats/0/accents", message_for(d))

    # --- duration overrides ---
    def test_text_beat_duration_override_has_a_one_and_a_half_second_floor(self):
        d = sample_dict()
        d["beats"][4]["duration_s"] = 1.4
        self.assertIn("beats/4/duration_s", message_for(d))
        d["beats"][4]["duration_s"] = 1.5
        validate_kinetic_dict(d)

    def test_an_override_faster_than_twice_reading_pace_is_rejected(self):
        d = sample_dict()
        d["beats"][0]["text"] = " ".join(["word"] * 15)  # computed 6.5 s
        d["beats"][0]["duration_s"] = 3.2
        self.assertIn("beats/0/duration_s", message_for(d))
        d["beats"][0]["duration_s"] = 3.25
        validate_kinetic_dict(d)

    def test_total_over_60_seconds_rejected_and_exactly_60_accepted(self):
        d = sample_dict()
        d.pop("caption"); d.pop("topic_terms")
        d["beats"] = [{"id": f"S{i}", "kind": "space", "duration_s": 6} for i in range(11)]
        self.assertIn("60", message_for(d))
        d["beats"] = [{"id": f"S{i}", "kind": "space", "duration_s": 6} for i in range(10)]
        validate_kinetic_dict(d)

    def test_space_beat_cannot_carry_text(self):
        d = sample_dict()
        d["beats"][2]["text"] = "hello"
        self.assertIn("beats/2", message_for(d))

    def test_text_beat_requires_role_and_motion(self):
        for key in ("role", "motion"):
            d = sample_dict()
            del d["beats"][0][key]
            self.assertIn("beats/0", message_for(d))

    def test_unknown_top_level_key_rejected(self):
        d = sample_dict()
        d["voiceover"] = "x"
        self.assertIn("voiceover", message_for(d))

    def test_fps_and_canvas_are_pinned(self):
        d = sample_dict()
        d["canvas"]["fps"] = 29
        self.assertIn("canvas/fps", message_for(d))
        d = sample_dict()
        d["canvas"]["w"] = 720
        self.assertIn("canvas/w", message_for(d))

    def test_caption_and_topic_terms_travel_together(self):
        d = sample_dict()
        del d["topic_terms"]
        self.assertIn("topic_terms", message_for(d))
        d = sample_dict()
        del d["caption"]
        self.assertIn("caption", message_for(d))

    def test_a_bad_caption_fails_the_spec_with_its_path(self):
        d = sample_dict()
        d["caption"] = "A street musician talks. Then it ends. #busking"
        self.assertIn("caption", message_for(d))

    def test_invalid_json_file_is_a_spec_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{nope", encoding="utf-8")
            with self.assertRaises(KineticSpecError):
                load_kinetic(p)

    def test_non_object_rejected(self):
        with self.assertRaises(KineticSpecError):
            validate_kinetic_dict([1, 2])

    def test_the_acceptance_fixtures_are_valid_specs(self):
        for f in (LAYOUT, STRESS, DEFAULTS):
            load_kinetic(f)


class CaptionRuleTests(unittest.TestCase):
    TITLE = "Where is the stage?"
    BEATS = ["I used to play on the same corner every Friday.", "The crowd formed around each other."]
    TERMS = ["street", "musician", "corner", "spotlight"]
    GOOD = "A street musician on why the best corner is the one with no spotlight."

    def check(self, caption, **kw):
        return check_caption(caption, kw.get("title", self.TITLE),
                             kw.get("beats", self.BEATS), kw.get("terms", self.TERMS))

    def test_a_good_caption_has_no_problems(self):
        self.assertEqual(self.check(self.GOOD), [])

    def test_empty_caption_is_a_problem(self):
        self.assertTrue(self.check("   "))

    def test_hashtags_rejected(self):
        problems = self.check(self.GOOD.rstrip(".") + " #busking")
        self.assertTrue(any("#" in p or "hashtag" in p.lower() for p in problems))

    def test_two_sentences_rejected(self):
        problems = self.check("A street musician on the corner. The spotlight finds nobody.")
        self.assertTrue(any("sentence" in p.lower() for p in problems))

    def test_one_sentence_with_an_internal_period_is_one_sentence(self):
        self.assertEqual(self.check("A street musician on why the 3.5 best corner has no spotlight."), [])

    def test_question_or_exclamation_ends_one_sentence(self):
        self.assertEqual(self.check("Why does a street musician pick the corner with no spotlight?"), [])

    def test_newline_rejected(self):
        self.assertTrue(self.check("A street musician\non the corner with no spotlight."))

    def test_over_220_chars_rejected(self):
        long = "A street musician " + "on the corner " * 20 + "with no spotlight."
        self.assertGreater(len(long), 220)
        self.assertTrue(self.check(long))

    def test_title_inside_caption_rejected_ignoring_case_and_punctuation(self):
        problems = self.check("A street musician asks WHERE IS THE STAGE at the corner spotlight.")
        self.assertTrue(any("title" in p.lower() for p in problems))

    def test_shared_content_trigram_with_a_beat_rejected(self):
        problems = self.check("A street musician learned the crowd formed around the spotlight corner.")
        self.assertTrue(any("crowd formed around" in p.lower() or "repeat" in p.lower() for p in problems))

    def test_shared_trigram_of_function_words_is_allowed(self):
        beats = ["Out of the dark it came", "Nothing else mattered"]
        caption = "A street musician steps out of the corner spotlight."  # shares only 'out of the'
        self.assertEqual(check_caption(caption, "Title here", beats, self.TERMS), [])

    def test_the_same_shared_content_trigram_is_flagged_when_it_is_not_function_words(self):
        beats = ["Dark corner spotlight again"]
        caption = "A street musician finds the dark corner spotlight."
        self.assertTrue(check_caption(caption, "Title here", beats, self.TERMS))

    def test_a_single_shared_word_is_allowed(self):
        self.assertEqual(self.check("A street musician says the corner needs no spotlight."), [])

    def test_straight_quotes_around_a_shared_phrase_do_not_hide_it(self):
        beats = ["I used to play on the same corner every Friday."]
        caption = "A street musician on 'the same corner every' spotlight."
        self.assertTrue(check_caption(caption, "Title here", beats, self.TERMS))

    def test_curly_and_straight_apostrophes_compare_equal(self):
        caption = "A street musician says don’t stop the corner spotlight."
        problems = check_caption(caption, "Don't stop the show", [], self.TERMS)
        self.assertTrue(any("title" in p.lower() for p in problems), problems)

    def test_accented_words_are_not_split(self):
        beats = ["The café corner spotlight faded"]
        caption = "A street musician at the café corner spotlight."
        self.assertTrue(check_caption(caption, "Title here", beats, self.TERMS))

    def test_a_single_word_title_may_also_be_a_topic_term(self):
        self.assertEqual(check_caption("A street musician on the corner spotlight.", "Spotlight", [], self.TERMS), [])

    def test_ellipsis_does_not_end_a_sentence(self):
        self.assertEqual(self.check("A street musician waits... on the corner with no spotlight."), [])
        self.assertEqual(self.check("A street musician waits… on the corner with no spotlight."), [])

    def test_too_few_topic_terms_rejected(self):
        problems = self.check("A busker on why the best spot has no glare.")
        self.assertTrue(any("topic" in p.lower() for p in problems))

    def test_topic_threshold_scales_down_for_short_term_lists(self):
        self.assertEqual(check_caption("A street musician's quiet corner.", "Title", [], ["street"]), [])

    def test_exactly_three_of_many_terms_is_enough(self):
        self.assertEqual(self.check("A street musician and the corner nobody notices."), [])
        self.assertTrue(self.check("A street musician and the place nobody notices."))

    def test_topic_matching_ignores_case(self):
        self.assertEqual(self.check("A STREET MUSICIAN on the CORNER."), [])

    def test_constants_are_the_documented_limits(self):
        self.assertEqual(caption_mod.MAX_CAPTION_CHARS, 220)
        self.assertEqual(caption_mod.MIN_TOPIC_TERMS, 3)


class VoiceTests(unittest.TestCase):
    def test_contrast_voice_sets_function_words_light_and_content_words_heavy(self):
        b = text_beat("I walk into the booth")
        by = {w.text: w for w in voice.style_words(b)}
        self.assertEqual(by["walk"].weight, 700)
        self.assertEqual(by["booth"].weight, 700)
        self.assertEqual(by["into"].weight, 400)
        self.assertEqual(by["the"].weight, 400)
        self.assertTrue(all(w.family == "display" for w in by.values()))
        self.assertTrue(all(w.italic is False and w.scale == 1.0 and w.color == "text" and w.treatment == "none"
                            for w in by.values()))

    def test_even_voice_uses_one_weight(self):
        b = text_beat("I walk into the booth", voice_="even")
        self.assertEqual({w.weight for w in voice.style_words(b)}, {600})

    def test_role_picks_family_and_weights(self):
        q = {w.text: w.weight for w in voice.style_words(text_beat("Where would the energy go", role="question"))}
        self.assertEqual((q["energy"], q["the"]), (800, 400))
        a = voice.style_words(text_beat("People walked past the booth", role="aside"))
        self.assertTrue(all(w.family == "body" for w in a))
        self.assertEqual({w.text: w.weight for w in a}["People"], 600)

    def test_accent_overrides_only_what_it_sets_on_only_the_matched_words(self):
        b = text_beat("The crowd formed around each other.",
                      accents=[{"text": "each other", "italic": True, "color": "accent"}])
        ws = voice.style_words(b)
        each, other, crowd = ws[4], ws[5], ws[1]
        self.assertEqual((each.italic, each.color, each.weight), (True, "accent", 700))  # weight stays voiced
        self.assertEqual((other.italic, other.color), (True, "accent"))
        self.assertEqual((crowd.italic, crowd.color), (False, "text"))

    def test_accent_sets_weight_scale_and_treatment(self):
        b = text_beat("Where would your attention go",
                      accents=[{"text": "your", "weight": 900, "scale": 1.2, "treatment": "bloom"}])
        your = voice.style_words(b)[2]
        self.assertEqual((your.weight, your.scale, your.treatment), (900, 1.2, "bloom"))

    def test_the_words_of_one_accent_are_kept_together_on_a_line(self):
        b = text_beat("The crowd formed around each other and stayed.",
                      accents=[{"text": "around each other", "weight": 900}])
        keep = [w.keep for w in voice.style_words(b)]
        self.assertEqual(keep, [False, False, False, True, True, False, False, False])

    def test_an_accent_applies_to_the_first_occurrence_only(self):
        b = text_beat("one two one two", accents=[{"text": "one", "weight": 900}])
        self.assertEqual([w.weight for w in voice.style_words(b)], [900, 700, 700, 700])

    def test_phrase_numbers_follow_punctuation(self):
        b = text_beat("In the 90s, I walk in.")
        self.assertEqual([w.phrase for w in voice.style_words(b)], [0, 0, 0, 1, 1, 1])


class LineBreakTests(unittest.TestCase):
    """The pure breaker: units of known width, clause numbers, a measure."""

    @staticmethod
    def units(widths, clauses=None, weak=()):
        clauses = clauses or [0] * len(widths)
        return [linebreak.Unit(width=w, words=1, clause=c, weak_end=i in weak)
                for i, (w, c) in enumerate(zip(widths, clauses))]

    @staticmethod
    def groups(lines):
        out = {}
        for i, ln in enumerate(lines):
            out.setdefault(ln, []).append(i)
        return [out[k] for k in sorted(out)]

    def test_a_block_that_fits_is_one_line(self):
        self.assertEqual(linebreak.break_units(self.units([30, 30, 30]), 0, 100), [0, 0, 0])

    def test_no_word_is_left_alone_on_a_line_when_it_can_be_avoided(self):
        # greedy fill gives 3 + 3 + 3 + 1; a widow
        lines = linebreak.break_units(self.units([30] * 10), 0, 100)
        sizes = [len(g) for g in self.groups(lines)]
        self.assertGreaterEqual(min(sizes), 2, sizes)
        self.assertLessEqual(max(sizes) - min(sizes), 1, "and the lines are balanced")

    def test_a_short_last_line_is_pulled_up_to_balance_the_block(self):
        # greedy: 90, 90, 20. Balanced: three lines of roughly 65.
        widths = [30, 30, 30, 30, 30, 30, 20]
        lines = linebreak.break_units(self.units(widths), 0, 100)
        totals = [sum(widths[i] for i in g) for g in self.groups(lines)]
        self.assertLessEqual(max(totals) - min(totals), 30, totals)

    def test_breaks_fall_between_clauses_when_that_costs_little(self):
        lines = linebreak.break_units(self.units([20] * 8, [0, 0, 0, 1, 1, 1, 1, 1]), 0, 100)
        self.assertEqual(self.groups(lines), [[0, 1, 2], [3, 4, 5, 6, 7]])

    def test_a_line_does_not_end_on_a_function_word_inside_a_clause(self):
        # seven words, one clause, three lines either way; a break after word 2 (a function word) is the one to avoid
        widths = [30] * 7
        for weak in ({2}, {1}, {2, 4}):
            lines = linebreak.break_units(self.units(widths, weak=weak), 0, 100)
            ends = {g[-1] for g in self.groups(lines)[:-1]}
            self.assertFalse(ends & weak, (weak, self.groups(lines)))

    def test_the_words_of_one_unit_stay_together_and_count_as_words(self):
        units = [linebreak.Unit(80, 2, 0, False), linebreak.Unit(30, 1, 0, False), linebreak.Unit(30, 1, 0, False)]
        lines = linebreak.break_units(units, 5, 100)
        self.assertEqual(lines[0], 0)
        self.assertNotEqual(lines[0], lines[1])  # 80 + 5 + 30 does not fit

    def test_a_unit_wider_than_the_measure_gets_its_own_line(self):
        self.assertEqual(linebreak.break_units(self.units([30, 150, 30]), 0, 100), [0, 1, 2])

    def test_empty_input(self):
        self.assertEqual(linebreak.break_units([], 5, 100), [])

    def test_deterministic(self):
        u = self.units([30, 20, 40, 30, 50, 10, 20], [0, 0, 1, 1, 1, 2, 2])
        self.assertEqual(linebreak.break_units(u, 3, 100), linebreak.break_units(u, 3, 100))


class MotionPlanTests(unittest.TestCase):
    TEXTS = {
        "one": "Hello",
        "two_phrases": "At raves in the 90s, I'd always look for the DJ booth.",
        "one_phrase_15": " ".join(["word"] * 15),
        "four_phrases": "One two, three four, five six, seven eight.",
        "clauses_uneven": "One two three four, five six, seven eight nine ten eleven twelve.",
    }

    def plan(self, key, fps, hold=False, accents=(), **kw):
        b = text_beat(self.TEXTS[key], accents=accents, **kw)
        frames = round(b.duration_s * fps)
        return b, frames, voice.plan_motion(b, frames, fps, hold)

    def test_one_timing_per_word_and_everything_is_an_int(self):
        for fps in FPS_SET:
            for key in self.TEXTS:
                b, frames, m = self.plan(key, fps)
                self.assertEqual(len(m.timings), len(m.words))
                for t in m.timings:
                    for v in (t.in_from, t.in_frames, t.out_from, t.out_frames, t.treat_from, t.treat_frames):
                        self.assertIsInstance(v, int)

    def test_the_words_of_a_clause_arrive_together_and_clauses_arrive_in_order(self):
        for fps in FPS_SET:
            _, _, m = self.plan("four_phrases", fps)
            by_clause = {}
            for w, t in zip(m.words, m.timings):
                by_clause.setdefault(w.phrase, set()).add(t.in_from)
            self.assertEqual(len(by_clause), 4)
            self.assertTrue(all(len(v) == 1 for v in by_clause.values()), "one start per clause")
            starts = [next(iter(by_clause[k])) for k in sorted(by_clause)]
            self.assertEqual(starts[0], 0)
            self.assertEqual(starts, sorted(set(starts)), "clauses start strictly one after another")

    def test_a_single_clause_arrives_as_one_unit(self):
        for fps in FPS_SET:
            _, _, m = self.plan("one_phrase_15", fps)
            self.assertEqual({t.in_from for t in m.timings}, {0})

    def test_every_word_finishes_arriving_by_the_reveal_and_the_line_then_holds(self):
        for fps in FPS_SET:
            for key in self.TEXTS:
                b, frames, m = self.plan(key, fps)
                for t in m.timings:
                    self.assertLessEqual(t.in_from + t.in_frames, m.reveal_frames)
                hold = frames - m.exit_frames - m.reveal_frames
                self.assertGreaterEqual(hold, round(voice.MIN_HOLD_S * fps) - 1, (key, fps))

    def test_a_clause_gets_dwell_time_in_proportion_to_its_words(self):
        _, _, m = self.plan("clauses_uneven", 30)
        starts = sorted({t.in_from for t in m.timings})
        counts = [sum(1 for w in m.words if w.phrase == k) for k in range(len(starts))]
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        per_word = [g / c for g, c in zip(gaps, counts)]
        self.assertLessEqual(max(per_word) - min(per_word), 1.0)  # rounding only

    def test_exit_stays_inside_the_beat_and_words_fade_in_phrase_order(self):
        for fps in FPS_SET:
            for key in self.TEXTS:
                b, frames, m = self.plan(key, fps)
                self.assertGreater(m.exit_frames, 0)
                outs = [t.out_from for t in m.timings]
                self.assertEqual(outs, sorted(outs))
                for t in m.timings:
                    self.assertGreaterEqual(t.out_from, frames - m.exit_frames)
                    self.assertGreaterEqual(t.out_frames, 3)
                    self.assertLessEqual(t.out_from + t.out_frames, frames)

    def test_the_final_beat_never_leaves(self):
        for fps in FPS_SET:
            _, frames, m = self.plan("two_phrases", fps, hold=True)
            self.assertEqual(m.exit_frames, 0)
            for t in m.timings:
                self.assertEqual((t.out_frames, t.out_from), (0, frames))

    def test_treatments_start_when_the_word_has_arrived_and_finish_before_it_leaves(self):
        for fps in FPS_SET:
            for hold in (False, True):
                acc = [{"text": "always", "weight": 900, "treatment": "whip"},
                       {"text": "raves", "color": "accent", "treatment": "bloom"},
                       {"text": "DJ", "treatment": "swell"}]
                b, frames, m = self.plan("two_phrases", fps, hold=hold, accents=acc)
                treated = 0
                for w, t in zip(m.words, m.timings):
                    if w.treatment == "none":
                        self.assertEqual(t.treat_frames, 0)
                    else:
                        treated += 1
                        self.assertEqual(t.treat_from, t.in_from + t.in_frames)
                        self.assertGreater(t.treat_frames, 0)
                        self.assertLessEqual(t.treat_from + t.treat_frames, t.out_from if not hold else frames)
                self.assertEqual(treated, 3)

    def test_drift_runs_the_length_of_the_reveal_and_flips_for_right_aligned_text(self):
        _, _, m = self.plan("two_phrases", 30)
        self.assertEqual(m.drift_px, voice.DRIFT_PX)
        _, _, r = self.plan("two_phrases", 30, align="right")
        self.assertEqual(r.drift_px, -voice.DRIFT_PX)

    def test_plan_is_deterministic(self):
        self.assertEqual(self.plan("two_phrases", 30)[2], self.plan("two_phrases", 30)[2])

    # -- a whip leans over its neighbour: the rest of the line makes room --
    def test_the_words_after_a_whip_on_its_line_slide_over_in_step_with_the_lean(self):
        acc = [{"text": "ask", "weight": 800, "treatment": "whip"}]
        b = text_beat("I'd ask people if they knew where it was. Many didn't.", accents=acc)
        m = voice.plan_motion(b, round(b.duration_s * 30), 30, False)
        i = [w.text for w in m.words].index("ask")
        whip = m.timings[i]
        for j, (w, t, ln) in enumerate(zip(m.words, m.timings, m.lines)):
            if j > i and ln == m.lines[i]:
                self.assertEqual(len(t.pushes), 1, w.text)
                frm, frames, px = t.pushes[0]
                self.assertEqual((frm, frames), (whip.treat_from, whip.treat_frames))
                self.assertGreater(px, 0)
            else:
                self.assertEqual(t.pushes, (), w.text)

    def test_two_whips_on_a_line_push_the_words_after_the_second_twice(self):
        acc = [{"text": "one", "treatment": "whip"}, {"text": "three", "treatment": "whip"}]
        b = text_beat("one two three four", accents=acc)
        m = voice.plan_motion(b, round(b.duration_s * 30), 30, False)
        self.assertEqual([len(t.pushes) for t in m.timings], [0, 1, 1, 2])

    # -- line breaks --
    def test_authored_line_breaks_are_kept_exactly_even_where_the_breaker_would_choose_otherwise(self):
        authored = "At raves in the\n90s, I'd always look\nfor the DJ booth."
        self.assertEqual(self.lines_of(authored), ["At raves in the", "90s, I'd always look", "for the DJ booth."])
        self.assertNotEqual(self.lines_of(authored.replace("\n", " ")), self.lines_of(authored))

    def test_an_authored_one_word_line_is_allowed_because_the_author_chose_it(self):
        self.assertEqual(self.lines_of("Many didn't.\nWhy?"), ["Many didn't.", "Why?"])

    def lines_of(self, text, **kw):
        m = voice.plan_motion(text_beat(text, **kw), 150, 30, False)
        out = {}
        for w, ln in zip(m.words, m.lines):
            out.setdefault(ln, []).append(w.text)
        return [" ".join(out[k]) for k in sorted(out)]

    def test_a_clause_is_not_split_when_it_fits_a_line_and_a_line_does_not_end_on_id(self):
        lines = self.lines_of("At raves in the 90s, I'd always look for the DJ booth.")
        self.assertEqual(lines[0], "At raves in the 90s,")
        self.assertFalse(any(l.endswith("I'd") for l in lines), lines)

    def test_no_line_is_a_single_word_unless_the_block_is_one_line(self):
        texts = [
            "I'd ask people if they knew where it was. Many didn't.",
            "When I found it, it was a corner, a loft, a spot off to the side.",
            "It was placed so the DJ could see the floor. The floor didn't need to see back.",
            "There was no stage show. The spectacle was each other.",
            "If nobody knew where the DJ was tonight, where would your attention go?",
        ]
        for t in texts:
            lines = self.lines_of(t)
            if len(lines) > 1:
                self.assertTrue(all(len(l.split()) > 1 for l in lines), lines)

    def test_lines_are_balanced(self):
        for t in ("It was placed so the DJ could see the floor. The floor didn't need to see back.",
                  "If nobody knew where the DJ was tonight, where would your attention go?"):
            m = voice.plan_motion(text_beat(t), 150, 30, False)
            widths = {}
            for w, ln in zip(m.words, m.lines):
                widths[ln] = widths.get(ln, 0) + layout.text_width_em(w.text + " ", "display") * w.scale
            self.assertLess(max(widths.values()) - min(widths.values()), 0.45 * max(widths.values()), widths)

    def test_every_line_fits_the_measure_and_accent_groups_stay_on_one_line(self):
        acc = [{"text": "DJ booth", "weight": 900}]
        m = voice.plan_motion(text_beat("At raves in the 90s, I'd always look for the DJ booth.", accents=acc),
                              150, 30, False)
        by_word = {w.text: ln for w, ln in zip(m.words, m.lines)}
        self.assertEqual(by_word["DJ"], by_word["booth."])
        self.assertEqual(m.lines, sorted(m.lines))
        measure = layout.line_width("statement")
        for ln in set(m.lines):
            em = sum(layout.text_width_em(w.text + " ", "display") * w.scale
                     for w, k in zip(m.words, m.lines) if k == ln)
            self.assertLessEqual(em * layout.ROLE_PX["statement"] - 0.214 * 60, measure)

    def test_block_height_is_the_sum_of_line_heights_and_grows_for_big_accents(self):
        plain = voice.plan_motion(text_beat("One two three four five six seven eight nine ten"), 150, 30, False)
        self.assertEqual(len(plain.line_heights), max(plain.lines) + 1)
        self.assertEqual(plain.block_height, sum(plain.line_heights))
        self.assertEqual(plain.line_heights[0], round(1.2 * layout.ROLE_PX["statement"]))
        big = voice.plan_motion(text_beat("One two three four five six seven eight nine ten",
                                          accents=[{"text": "two", "scale": 1.4}]), 150, 30, False)
        self.assertGreater(big.block_height, plain.block_height)

    def test_the_fastest_legal_override_still_plans_cleanly(self):
        # 15 words, computed 6.5 s; half is the floor.
        for fps in FPS_SET:
            b = text_beat(self.TEXTS["one_phrase_15"], dur=3.25)
            frames = round(b.duration_s * fps)
            m = voice.plan_motion(b, frames, fps, False)
            self.assertLessEqual(m.reveal_frames + m.exit_frames, frames)
            self.assertGreaterEqual(min(t.in_frames for t in m.timings), 4)


class PropsTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_kinetic(SAMPLE)
        self.style = load_visual_style(CONFIG, "dyson-hope")
        self.props = kinetic_to_remotion_props(self.spec, self.style)

    def test_clip_name(self):
        self.assertEqual(clip_name("SAMPLE-01"), "SAMPLE-01-kinetic.mov")

    def test_header(self):
        p = self.props
        self.assertEqual((p["schemaVersion"], p["kind"], p["reelId"], p["fps"]), (3, "kinetic", "SAMPLE-01", 30))
        self.assertEqual(p["dimensions"], {"width": 1080, "height": 1920})
        self.assertEqual(COMPOSITION, "KineticText")

    def test_layout_partitions_the_safe_rect(self):
        x, y, w, h = FULL_SAFE
        p = self.props
        self.assertEqual(p["safeBox"], {"x": x, "y": y, "width": w, "height": h})
        t, b = p["titleBox"], p["bodyBox"]
        self.assertEqual((t["x"], t["y"], t["width"], t["height"]), (x, y, w, TITLE_BLOCK_H))
        self.assertEqual(b["y"], y + TITLE_BLOCK_H + TITLE_GAP)
        self.assertEqual(b["y"] + b["height"], y + h)
        self.assertEqual((b["x"], b["width"]), (x, w))

    def test_title_is_plain_static_text_with_a_fitted_size(self):
        self.assertEqual(self.props["title"], "Where is the stage?")
        self.assertIsInstance(self.props["title"], str)
        self.assertEqual(self.props["titlePx"], layout.fit_title("Where is the stage?", 160, 72))
        self.assertGreaterEqual(self.props["titlePx"], MIN_TYPE_PX["title_px"])

    def test_every_word_in_props_equals_the_motion_plan(self):
        for entry, beat in zip(self.props["beats"], self.spec.beats):
            if beat.kind != "text":
                continue
            frames = entry["durationInFrames"]
            plan = voice.plan_motion(beat, frames, self.spec.fps, entry["holdToEnd"])
            self.assertEqual(entry["revealFrames"], plan.reveal_frames)
            self.assertEqual(entry["exitFrames"], plan.exit_frames)
            self.assertEqual(entry["driftPx"], plan.drift_px)
            for got, w, t, ln in zip(entry["words"], plan.words, plan.timings, plan.lines):
                self.assertEqual(
                    got,
                    {"text": w.text, "family": w.family, "weight": w.weight, "italic": w.italic,
                     "scale": w.scale, "color": w.color, "treatment": w.treatment, "keep": w.keep,
                     "inFrom": t.in_from, "inFrames": t.in_frames, "outFrom": t.out_from,
                     "outFrames": t.out_frames, "treatFrom": t.treat_from, "treatFrames": t.treat_frames, "line": ln,
                     "pushes": [list(p) for p in t.pushes]})
            self.assertEqual(entry["lineHeights"], plan.line_heights)
            self.assertEqual(entry["blockHeight"], plan.block_height)

    def test_words_carry_their_line_and_beats_their_block_height(self):
        by_id = {b["id"]: b for b in self.props["beats"]}
        b1 = by_id["B01"]
        self.assertTrue(all("line" in w for w in b1["words"]))
        self.assertEqual(b1["blockHeight"], sum(b1["lineHeights"]))
        self.assertEqual(len(b1["lineHeights"]), max(w["line"] for w in b1["words"]) + 1)

    def test_the_body_container_sits_at_the_bottom_of_the_safe_zone_and_fits_the_tallest_block(self):
        c = self.props["bodyContainer"]
        tallest = max(b["blockHeight"] for b in self.props["beats"] if b["kind"] == "text")
        self.assertEqual(c["height"], tallest)
        safe = self.props["safeBox"]
        self.assertEqual(c["y"] + c["height"], safe["y"] + safe["height"] - layout.PAD)
        self.assertEqual((c["x"], c["width"]), (safe["x"] + layout.PAD, safe["width"] - 2 * layout.PAD))
        body = self.props["bodyBox"]
        self.assertGreaterEqual(c["y"], body["y"] + layout.PAD)

    def test_the_tallest_legal_block_still_fits_the_body_area(self):
        d = sample_dict()
        d["beats"][0].update(text=" ".join(["WWWWWWWWWW"] * 8), role="question", accents=[])  # 8 one-word lines
        props = kinetic_to_remotion_props(parse_kinetic(d), self.style)
        c, body = props["bodyContainer"], props["bodyBox"]
        self.assertEqual(c["height"], props["beats"][0]["blockHeight"])
        self.assertGreaterEqual(c["y"], body["y"] + layout.PAD)

    def test_beat_frames_are_contiguous_and_cover_the_clip(self):
        beats = self.props["beats"]
        self.assertEqual(beats[0]["from"], 0)
        for prev, cur in zip(beats, beats[1:]):
            self.assertEqual(cur["from"], prev["from"] + prev["durationInFrames"])
        self.assertEqual(beats[-1]["from"] + beats[-1]["durationInFrames"], self.props["durationInFrames"])
        self.assertEqual(self.props["durationInFrames"], round(self.spec.total_s * 30))

    def test_text_beats_carry_their_fields_and_a_word_plan(self):
        by_id = {b["id"]: b for b in self.props["beats"]}
        b2 = by_id["B02"]
        self.assertEqual((b2["kind"], b2["role"], b2["motion"], b2["slot"], b2["align"]),
                         ("text", "aside", "diminish", "bottom", "right"))
        self.assertEqual(b2["sizePx"], ROLE_PX["aside"])
        self.assertEqual(len(b2["words"]), len("People walked past without a glance.".split()))
        w0 = b2["words"][0]
        for key in ("text", "family", "weight", "italic", "scale", "color", "treatment", "keep",
                    "inFrom", "inFrames", "outFrom", "outFrames", "treatFrom", "treatFrames"):
            self.assertIn(key, w0)
        self.assertEqual(b2["driftPx"], -40)
        for key in ("revealFrames", "exitFrames"):
            self.assertIn(key, b2)
        self.assertEqual(by_id["B03"]["kind"], "space")
        self.assertNotIn("words", by_id["B03"])
        each = [w for w in by_id["B04"]["words"] if w["text"] in ("each", "other.")]
        self.assertEqual(len(each), 2)
        self.assertTrue(all(w["italic"] and w["color"] == "accent" and w["weight"] == 900 for w in each))

    def test_only_the_final_text_beat_holds_to_the_end_and_its_words_never_leave(self):
        flags = [b["holdToEnd"] for b in self.props["beats"]]
        self.assertEqual(flags, [False, False, False, False, True])
        last = self.props["beats"][-1]
        self.assertTrue(all(w["outFrames"] == 0 for w in last["words"]))
        self.assertTrue(all(w["outFrames"] >= 3 for w in self.props["beats"][0]["words"]))

    def test_a_trailing_space_beat_is_never_flagged_to_hold(self):
        d = sample_dict()
        d["beats"].append({"id": "B06", "kind": "space", "duration_s": 1})
        props = kinetic_to_remotion_props(parse_kinetic(d), self.style)
        flags = {b["id"]: b["holdToEnd"] for b in props["beats"]}
        self.assertFalse(flags["B06"])
        self.assertFalse(flags["B05"])

    def test_role_sizes_match_the_documented_scale_and_respect_the_floors(self):
        self.assertEqual(ROLE_PX, {"statement": 60, "aside": 50, "question": 68})
        self.assertGreaterEqual(ROLE_PX["statement"], MIN_TYPE_PX["heading_px"])
        self.assertGreaterEqual(ROLE_PX["question"], MIN_TYPE_PX["heading_px"])
        self.assertGreaterEqual(ROLE_PX["aside"], MIN_TYPE_PX["body_px"])

    def test_style_and_legibility_floors_ride_along(self):
        self.assertEqual(self.props["style"], self.style.to_dict())
        self.assertEqual(self.props["minType"],
                         {"label_px": 28, "body_px": 40, "heading_px": 56, "title_px": 72})

    def test_safe_rect_matches_the_visual_track_regions(self):
        regions = json.loads((REPO_ROOT / "schema" / "visuals.schema.json").read_text())
        pinned = regions["properties"]["regions"]["properties"]["full_safe"]["const"]
        self.assertEqual(FULL_SAFE, (pinned["x"], pinned["y"], pinned["w"], pinned["h"]))

    def test_frame_counts_at_each_supported_fps(self):
        # 15.1 s of beats: 3.3 + 2.9 + 2 + 2.9 + 4
        for fps, frames in ((24, 362), (30, 453), (60, 906)):
            d = sample_dict()
            d["canvas"]["fps"] = fps
            props = kinetic_to_remotion_props(parse_kinetic(d), self.style)
            self.assertEqual(props["durationInFrames"], frames, fps)

    def test_frames_stay_contiguous_at_25_fps(self):
        d = sample_dict()
        d["canvas"]["fps"] = 25
        beats = kinetic_to_remotion_props(parse_kinetic(d), self.style)["beats"]
        for prev, cur in zip(beats, beats[1:]):
            self.assertEqual(cur["from"], prev["from"] + prev["durationInFrames"])
            self.assertGreater(prev["durationInFrames"], 0)


class StillTimeTests(unittest.TestCase):
    def test_one_still_per_text_beat_inside_the_beat_after_settling(self):
        spec = load_kinetic(SAMPLE)
        times = still_times(spec)
        self.assertEqual(len(times), len(spec.text_beats()))
        for t, b in zip(times, spec.text_beats()):
            self.assertAlmostEqual(t, b.start_s + STILL_FRACTION * b.duration_s, places=2)
            self.assertGreater(t, b.start_s + b.duration_s / 2)
            self.assertLess(t, b.start_s + b.duration_s)

    def test_space_beats_get_no_still(self):
        spec = load_kinetic(SAMPLE)
        space = next(b for b in spec.beats if b.kind == "space")
        for t in still_times(spec):
            self.assertFalse(space.start_s <= t < space.start_s + space.duration_s)


class FakeRun:
    """Stands in for subprocess.run: records argv, writes the clip/png the command would."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, check=True, cwd=None, **kw):
        self.calls.append(list(argv))
        if argv[0] == "npx":
            out = next(a for a in argv if a.endswith(".mov"))
            Path(out).write_bytes(b"mov")
        elif argv[0] == "ffmpeg":
            Path(argv[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(argv, 0)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_kinetic(SAMPLE)
        self.style = load_visual_style(CONFIG, "dyson-hope")

    def test_plan_names_one_canvas_sized_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = plan_render(self.spec, tmp, self.style)
            self.assertEqual(job.output, Path(tmp) / "SAMPLE-01-kinetic.mov")
            self.assertEqual(job.composition, "KineticText")
            self.assertEqual(job.props_path, job.output.with_suffix(".props.json"))
            self.assertEqual(job.props["dimensions"], {"width": 1080, "height": 1920})

    def test_render_writes_props_and_runs_remotion_once_with_no_padding_pass(self):
        run = FakeRun()
        with tempfile.TemporaryDirectory() as tmp:
            res = render_kinetic(self.spec, tmp, self.style, run=run, remotion_dir=str(REPO_ROOT / "remotion"))
            self.assertEqual(len(run.calls), 1)
            argv = run.calls[0]
            self.assertEqual(argv[:3], ["npx", "remotion", "render"])
            self.assertIn("KineticText", argv)
            self.assertIn("--codec=prores", argv)
            self.assertIn("--prores-profile=4444", argv)
            self.assertTrue(Path(res["output"]).exists())
            props = json.loads(Path(res["props"]).read_text(encoding="utf-8"))
            self.assertEqual(props["kind"], "kinetic")
            self.assertEqual(props["title"], self.spec.title)
            self.assertEqual(len(props["beats"]), len(self.spec.beats))

    def test_stills_are_extracted_one_per_text_beat_over_the_preview_plate(self):
        run = FakeRun()
        with tempfile.TemporaryDirectory() as tmp:
            res = render_kinetic(self.spec, tmp, self.style, stills=True, run=run,
                                 frames_dir=Path(tmp) / "frames", preview_bg="#101010",
                                 remotion_dir=str(REPO_ROOT / "remotion"))
            ff = [c for c in run.calls if c[0] == "ffmpeg"]
            self.assertEqual(len(ff), len(self.spec.text_beats()))
            self.assertEqual(len(res["frames"]), len(ff))
            for c in ff:
                self.assertTrue(any("101010" in a for a in c))
            for png in res["frames"]:
                self.assertTrue(Path(png).exists())
                self.assertEqual(Path(png).parent, Path(tmp) / "frames")

    def test_no_stills_unless_asked(self):
        run = FakeRun()
        with tempfile.TemporaryDirectory() as tmp:
            res = render_kinetic(self.spec, tmp, self.style, run=run,
                                 remotion_dir=str(REPO_ROOT / "remotion"))
            self.assertEqual(res["frames"], [])
            self.assertFalse([c for c in run.calls if c[0] == "ffmpeg"])

    def test_dry_run_spawns_nothing_and_writes_nothing(self):
        run = FakeRun()
        with tempfile.TemporaryDirectory() as tmp:
            res = render_kinetic(self.spec, tmp, self.style, stills=True, dry_run=True, run=run)
            self.assertEqual(run.calls, [])
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertEqual(res["argv"][:3], ["npx", "remotion", "render"])
            self.assertEqual(len(res["frames"]), len(self.spec.text_beats()))

    def test_missing_remotion_project_is_an_error_unless_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "Remotion project not found"):
                render_kinetic(self.spec, tmp, self.style, run=FakeRun(), remotion_dir=str(Path(tmp) / "nope"))


class CliTests(unittest.TestCase):
    def _run(self, *argv):
        from video_pipeline.cli import main

        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_check_prints_the_timeline_and_total(self):
        code, out, _ = self._run("kinetic-check", str(SAMPLE))
        self.assertEqual(code, 0)
        spec = load_kinetic(SAMPLE)
        self.assertIn(f"{spec.total_s:.1f}s", out)
        for b in spec.beats:
            self.assertIn(b.id, out)
        self.assertIn("caption: ok", out.lower())

    def test_check_invalid_spec_exits_2_with_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.kinetic.json"
            d = sample_dict()
            d["beats"][0]["motion"] = "bounce"
            bad.write_text(json.dumps(d), encoding="utf-8")
            code, _, err = self._run("kinetic-check", str(bad))
            self.assertEqual(code, 2)
            self.assertIn("beats/0", err)

    def test_check_bad_caption_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.kinetic.json"
            d = sample_dict()
            d["caption"] = "Two sentences. Right here."
            bad.write_text(json.dumps(d), encoding="utf-8")
            code, _, err = self._run("kinetic-check", str(bad))
            self.assertEqual(code, 2)
            self.assertIn("caption", err)

    def test_render_dry_run_against_a_project_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self._run("kinetic-render", str(SAMPLE), "--project", tmp, "--stills", "--dry-run")
            self.assertEqual(code, 0)
            self.assertIn(str(Path(tmp) / "layers" / "kinetic" / "SAMPLE-01-kinetic.mov"), out)
            self.assertIn(str(Path(tmp) / "review" / "kinetic"), out)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_render_needs_a_destination(self):
        code, _, err = self._run("kinetic-render", str(SAMPLE), "--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("--project", err)

    def test_render_drives_the_real_composition_root_with_only_processes_stubbed(self):
        """Config, style layers, spec, timing, voicing, props and argv are all real."""
        run = FakeRun()
        with tempfile.TemporaryDirectory() as tmp, mock.patch("video_pipeline.kinetic.render.subprocess.run", run):
            code, out, err = self._run("kinetic-render", str(SAMPLE), "--project", tmp,
                                       "--identity", "dyson-hope", "--stills")
            self.assertEqual(code, 0, err)
            clip = Path(tmp) / "layers" / "kinetic" / "SAMPLE-01-kinetic.mov"
            self.assertTrue(clip.exists())
            props = json.loads(clip.with_suffix(".props.json").read_text(encoding="utf-8"))
            spec = load_kinetic(SAMPLE)
            self.assertEqual(props["durationInFrames"], round(spec.total_s * spec.fps))
            self.assertEqual(props["style"]["display_font"], "Archivo")
            first = props["beats"][0]
            self.assertEqual(len(first["words"]), len(spec.beats[0].text.split()))
            starts = [w["inFrom"] for w in first["words"]]
            self.assertGreater(len(set(starts)), 1)  # staggered, not one block
            stills = sorted((Path(tmp) / "review" / "kinetic").glob("*.png"))
            self.assertEqual(len(stills), len(spec.text_beats()))

    def test_missing_remotion_project_exits_2_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("video_pipeline.kinetic.render.REMOTION_DIR", Path(tmp) / "nope"):
            code, _, err = self._run("kinetic-render", str(SAMPLE), "--project", tmp)
            self.assertEqual(code, 2)
            self.assertIn("Remotion project not found", err)

    def test_unknown_identity_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self._run("kinetic-render", str(SAMPLE), "--project", tmp,
                                     "--identity", "no-such-identity", "--dry-run")
            self.assertEqual(code, 2)
            self.assertIn("no-such-identity", err)


# --------------------------------------------------------------------------
# Real render: opt in on a machine with Node, FFmpeg, Pillow, and NumPy.
# --------------------------------------------------------------------------
ACCENT_RGB = (0x9C, 0x97, 0xF4)


@unittest.skipUnless(os.environ.get("VP_REMOTION_ACCEPTANCE") == "1",
                     "real Remotion render — set VP_REMOTION_ACCEPTANCE=1 on the daily driver")
class RemotionAcceptanceTests(unittest.TestCase):
    """Renders fixtures for real and inspects pixels."""

    BODY_TOP = FULL_SAFE[1] + TITLE_BLOCK_H + TITLE_GAP

    @classmethod
    def setUpClass(cls):
        from PIL import Image  # noqa: F401  (acceptance needs Pillow)

        cls.root = Path(os.environ.get("VP_ACCEPTANCE_DIR", REPO_ROOT / "review" / "kinetic-acceptance"))
        cls.style = load_visual_style(CONFIG, "dyson-hope")
        cls.renders = {}
        for name, path in (("sample", SAMPLE), ("layout", LAYOUT), ("stress", STRESS), ("defaults", DEFAULTS)):
            spec = load_kinetic(path)
            res = render_kinetic(spec, cls.root / name / "layers", cls.style)
            props = json.loads(Path(res["props"]).read_text(encoding="utf-8"))
            cls.renders[name] = (spec, res, props)

    # -- helpers --
    def _rgba(self, name, t):
        import numpy as np
        from PIL import Image

        png = self.root / name / f"probe-{t:.3f}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", self.renders[name][1]["output"],
                        "-frames:v", "1", "-pix_fmt", "rgba", str(png)], check=True)
        return np.array(Image.open(png).convert("RGBA"))

    @staticmethod
    def _mask(arr, y0=0, y1=1920):
        return arr[y0:y1, :, 3] > 8

    @staticmethod
    def _bbox(mask):
        import numpy as np

        ys, xs = np.where(mask)
        if len(xs) == 0:
            return None
        return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

    def _beat(self, name, beat_id):
        spec = self.renders[name][0]
        b = next(b for b in spec.beats if b.id == beat_id)
        pb = next(x for x in self.renders[name][2]["beats"] if x["id"] == beat_id)
        return b, pb

    def _body(self, name, t):
        return self._mask(self._rgba(name, t), self.BODY_TOP, 1920)

    def _settled(self, name, beat_id):
        """Time just after the beat's last word has arrived."""
        b, pb = self._beat(name, beat_id)
        return b.start_s + (pb["revealFrames"] + 10) / self.renders[name][0].fps

    # -- format --
    def test_stream_is_canvas_sized_prores_with_alpha(self):
        spec, res, _ = self.renders["sample"]
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,pix_fmt,duration", "-of", "json", res["output"]],
            check=True, capture_output=True, text=True)
        s = json.loads(probe.stdout)["streams"][0]
        self.assertEqual((s["width"], s["height"]), (1080, 1920))
        self.assertIn("a", s["pix_fmt"])
        self.assertAlmostEqual(float(s["duration"]), spec.total_s, delta=0.2)

    # -- safe zone: every fixture, four moments of every beat --
    def test_nothing_is_drawn_outside_the_safe_zone_or_in_the_gap_at_any_moment(self):
        x, y, w, h = FULL_SAFE
        seen = 0
        for name in ("sample", "layout", "stress"):
            spec = self.renders[name][0]
            for b in spec.beats:
                for frac in (0.1, 0.3, 0.7, 0.95):
                    t = min(b.start_s + b.duration_s * frac, spec.total_s - 0.05)
                    arr = self._rgba(name, t)
                    bbox = self._bbox(self._mask(arr))
                    if bbox is None:
                        continue
                    seen += 1
                    label = f"{name}/{b.id}@{frac}"
                    self.assertGreaterEqual(bbox[0], x, label)
                    self.assertGreaterEqual(bbox[1], y, label)
                    self.assertLessEqual(bbox[2], x + w, label)
                    self.assertLessEqual(bbox[3], y + h, label)
                    gap = self._mask(arr, y + TITLE_BLOCK_H, self.BODY_TOP)
                    self.assertFalse(gap.any(), f"{label}: pixels in the gap under the title")
        self.assertGreater(seen, 20)

    def test_settled_text_and_the_title_keep_clear_of_the_safe_edges(self):
        """Clipping at the safe edge would still satisfy 'inside the safe rect'; require a margin."""
        x, y, w, h = FULL_SAFE
        for name in ("sample", "layout", "stress"):
            spec = self.renders[name][0]
            title = self._bbox(self._mask(self._rgba(name, 0.0), y, y + TITLE_BLOCK_H))
            self.assertGreaterEqual(title[0], x + 8, f"{name} title cut at the left edge")
            self.assertLessEqual(title[2], x + w - 8, f"{name} title cut at the right edge")
            for b in spec.text_beats():
                bb = self._bbox(self._body(name, self._settled(name, b.id)))
                self.assertIsNotNone(bb, f"{name}/{b.id}")
                self.assertGreaterEqual(bb[0], x + 8, f"{name}/{b.id} cut at the left edge")
                self.assertLessEqual(bb[2], x + w - 8, f"{name}/{b.id} cut at the right edge")

    def test_title_is_visible_from_the_first_frame_and_pixel_identical_throughout(self):
        import numpy as np

        spec = self.renders["layout"][0]
        lo, hi = FULL_SAFE[1], FULL_SAFE[1] + TITLE_BLOCK_H
        ref = self._rgba("layout", 0.0)[lo:hi]
        self.assertTrue((ref[:, :, 3] > 8).any(), "no title on the first frame")
        for b in spec.beats:
            for t in (b.start_s + 0.05, b.start_s + b.duration_s * 0.5):
                cur = self._rgba("layout", min(t, spec.total_s - 0.05))[lo:hi]
                self.assertTrue(np.array_equal(ref, cur), f"title changed during {b.id} at {t:.2f}s")

    # -- clause by clause: the animation is divided up, not applied to the line as a block --
    def test_clauses_arrive_progressively_rather_than_as_a_block(self):
        spec, _, _ = self.renders["sample"]
        b, pb = self._beat("sample", "B01")
        fps = spec.fps
        mass = [int(self._body("sample", b.start_s + int(pb["revealFrames"] * f) / fps).sum())
                for f in (0.2, 0.45, 0.7, 1.0)]
        final = int(self._body("sample", self._settled("sample", "B01")).sum())
        for earlier, later in zip(mass, mass[1:]):
            self.assertGreaterEqual(later, 0.98 * earlier, "text mass must grow as clauses arrive")  # settling jitter only
        self.assertGreater(mass[1], mass[0] * 1.5, "the second clause adds visible mass")
        self.assertLess(mass[0], 0.5 * final, "early in the reveal most clauses are still absent")
        self.assertGreater(mass[2], mass[0] * 1.5)
        self.assertGreater(final, 500)

    def test_the_line_leaves_inside_its_beat_and_is_partly_visible_mid_exit(self):
        spec, _, _ = self.renders["layout"]
        b, pb = self._beat("layout", "T1")
        fps = spec.fps
        self.assertFalse(self._body("layout", b.start_s + b.duration_s - 1.5 / fps).any(),
                         "exit must finish inside the beat")
        mid_exit = b.start_s + (pb["durationInFrames"] - pb["exitFrames"] * 0.6) / fps
        self.assertTrue(self._body("layout", mid_exit).any(), "text should still be partly visible mid-exit")

    def test_the_final_beat_holds_visible_on_the_last_frame(self):
        spec = self.renders["layout"][0]
        self.assertTrue(self._body("layout", spec.total_s - 0.04).any())

    # -- placement --
    def test_slot_moves_the_text_vertically(self):
        ys = {}
        for bid in ("T1", "M1", "U1"):
            bb = self._bbox(self._body("layout", self._settled("layout", bid)))
            self.assertIsNotNone(bb, bid)
            ys[bid] = (bb[1] + bb[3]) / 2
        self.assertLess(ys["T1"] + 30, ys["M1"])
        self.assertLess(ys["M1"] + 30, ys["U1"])

    def test_default_blocks_share_one_first_line_position_and_left_edge(self):
        tops, lefts = [], []
        for bid in ("P1", "P2"):
            bb = self._bbox(self._body("defaults", self._settled("defaults", bid)))
            self.assertIsNotNone(bb, bid)
            tops.append(bb[1])
            lefts.append(bb[0])
        self.assertLessEqual(abs(tops[0] - tops[1]), 6, "first lines start at the same height")
        self.assertLessEqual(abs(lefts[0] - lefts[1]), 40, "left-aligned blocks share a left edge")

    def test_the_body_container_sits_at_the_bottom_of_the_safe_zone(self):
        # P2 is the tallest block, so its last line ends at the container's bottom edge
        bb = self._bbox(self._body("defaults", self._settled("defaults", "P2")))
        bottom = FULL_SAFE[1] + FULL_SAFE[3] - layout.PAD
        ink_bottom = bb[3] + self.BODY_TOP  # the probe is cropped at the top of the body area
        self.assertLessEqual(ink_bottom, bottom)
        self.assertGreaterEqual(ink_bottom, bottom - 50)

    def test_the_rest_of_a_line_slides_over_when_a_word_whips(self):
        spec, _, props = self.renders["defaults"]
        _, pb = self._beat("defaults", "P4")
        push = next(w for w in pb["words"] if w["text"] == "now")["pushes"][0]
        rights = []
        for bid in ("P3", "P4"):
            b, pbeat = self._beat("defaults", bid)
            t = b.start_s + (push[0] + push[1] + 6) / spec.fps
            bb = self._bbox(self._body("defaults", t))
            self.assertIsNotNone(bb, bid)
            rights.append(bb[2])
        self.assertGreaterEqual(rights[1] - rights[0], push[2] - 3)
        self.assertLessEqual(rights[1] - rights[0], push[2] + 4)

    def test_align_moves_the_text_horizontally(self):
        edges = {bid: self._bbox(self._body("layout", self._settled("layout", bid))) for bid in ("L1", "M1", "R1")}
        self.assertLessEqual(edges["L1"][0], FULL_SAFE[0] + 36)
        self.assertGreaterEqual(edges["R1"][2], FULL_SAFE[0] + FULL_SAFE[2] - 36)
        self.assertLess(edges["L1"][0] + 20, edges["M1"][0])
        self.assertGreater(edges["R1"][2] - 20, edges["M1"][2])

    # -- character: accents and weight variety are visible --
    def _accent_pixels(self, arr):
        import numpy as np

        rgb = arr[self.BODY_TOP:, :, :3].astype(int)
        a = arr[self.BODY_TOP:, :, 3]
        near = (np.abs(rgb - np.array(ACCENT_RGB)).sum(axis=2) < 60) & (a > 200)
        return int(near.sum())

    def test_accent_colour_appears_only_where_the_spec_asks_for_it(self):
        a = self._accent_pixels(self._rgba("layout", self._settled("layout", "A1") + 0.6))
        p = self._accent_pixels(self._rgba("layout", self._settled("layout", "N1") + 0.6))
        self.assertGreater(a, 300)
        self.assertEqual(p, 0)

    def test_the_words_of_one_accent_stay_on_one_line(self):
        import numpy as np

        arr = self._rgba("sample", self._settled("sample", "B04") + 0.3)
        rgb = arr[self.BODY_TOP:, :, :3].astype(int)
        near = (np.abs(rgb - np.array(ACCENT_RGB)).sum(axis=2) < 60) & (arr[self.BODY_TOP:, :, 3] > 200)
        bb = self._bbox(near)
        self.assertIsNotNone(bb)
        self.assertLess(bb[3] - bb[1], 100, "'each other' must not wrap onto two lines")

    def test_the_contrast_voice_renders_differently_from_the_even_voice_for_the_same_words(self):
        contrast = int(self._body("layout", self._settled("layout", "M1")).sum())
        even = int(self._body("layout", self._settled("layout", "E1")).sum())
        self.assertGreater(abs(contrast - even), 0.02 * max(contrast, even))

    def _after_treatment(self, beat_id):
        """Time just after the last treated word of ``beat_id`` has finished its treatment."""
        spec = self.renders["layout"][0]
        b, pb = self._beat("layout", beat_id)
        end = max(w["treatFrom"] + w["treatFrames"] for w in pb["words"] if w["treatFrames"])
        return b.start_s + (end + 1) / spec.fps

    def test_treatments_visibly_change_the_word_with_every_motion(self):
        """Each treated beat has a twin with identical words and motion and no treatment;
        once the treatments finish, the two must look different."""
        import numpy as np

        for treated, twin in (("R2", "R0"), ("W1", "W0")):   # rise and mask
            spec = self.renders["layout"][0]
            t_treated = self._after_treatment(treated)
            b_t, _ = self._beat("layout", treated)
            b_0, _ = self._beat("layout", twin)
            offset = t_treated - b_t.start_s
            a = self._body("layout", t_treated)
            b = self._body("layout", b_0.start_s + offset)
            self.assertGreater(int(np.logical_xor(a, b).sum()), 150,
                               f"{treated} looks the same as {twin}: its treatments were dropped")

    def test_the_whole_line_drifts_while_it_reveals(self):
        spec = self.renders["layout"][0]
        b, pb = self._beat("layout", "D1")
        early = self._bbox(self._body("layout", b.start_s + 3 / spec.fps))
        late = self._bbox(self._body("layout", self._settled("layout", "D1")))
        self.assertIsNotNone(early)
        self.assertGreater(abs((early[0] + early[2]) / 2 - (late[0] + late[2]) / 2), 8)

    def test_diminish_softens_the_line_while_it_is_held(self):
        spec = self.renders["layout"][0]
        b, pb = self._beat("layout", "DM")
        fps = spec.fps
        early = int(self._body("layout", b.start_s + (pb["revealFrames"] + 4) / fps).sum())
        late = int(self._body("layout", b.start_s + (pb["durationInFrames"] - pb["exitFrames"] - 2) / fps).sum())
        self.assertLess(late, 0.95 * early)

    def test_the_old_vacuous_contrast_check_is_gone(self):
        self.assertFalse(hasattr(self, "test_contrast_voice_changes_the_look_of_the_same_kind_of_line"))

    # -- stress: the longest legal words and the fastest legal gather --
    def test_the_longest_legal_word_with_the_biggest_accent_is_fully_visible(self):
        bb = self._bbox(self._body("stress", self._settled("stress", "Q1")))
        self.assertGreater(bb[0], FULL_SAFE[0] + 8)
        self.assertLess(bb[2], FULL_SAFE[0] + FULL_SAFE[2] - 8, "text is cut off at the safe edge")

    def test_the_fastest_legal_gather_still_delivers_every_word(self):
        gm = int(self._body("stress", self._settled("stress", "G1")).sum())
        rm = int(self._body("stress", self._settled("stress", "R1")).sum())
        self.assertGreater(gm, 0.85 * rm)
        self.assertLess(gm, 1.15 * rm)


if __name__ == "__main__":
    unittest.main()
