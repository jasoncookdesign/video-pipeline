"""visuals.json contract (#62 part A): schema validation at the Python boundary.

The schema (schema/visuals.schema.json) is the contract part B (the reels plugin)
writes against. These tests pin what it accepts and — more importantly — what it
rejects, including per-template props, so a bad spec never reaches the renderer.
"""

import copy
import json
import unittest

from tests._util import REPO_ROOT

from video_pipeline.visuals.spec import (
    SCHEMA_PATH,
    VisualsSpecError,
    load_visuals,
    parse_visuals,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "visuals"
REEL_0227 = FIXTURES / "dh-reel-0227.visuals.json"
GALLERY = FIXTURES / "template-gallery.visuals.json"


def _data():
    return json.loads(REEL_0227.read_text(encoding="utf-8"))


def _beat(data, beat_id):
    return next(b for b in data["beats"] if b["id"] == beat_id)


class SchemaFileTests(unittest.TestCase):
    def test_schema_is_a_valid_draft7_schema(self):
        import jsonschema

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft7Validator.check_schema(schema)
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)


class ValidSpecTests(unittest.TestCase):
    def test_0227_fixture_parses(self):
        spec = load_visuals(REEL_0227)
        self.assertEqual(spec.reel_id, "DH-REEL-0227")
        self.assertEqual(spec.fps, 30)
        self.assertEqual(spec.identity, "dyson-hope")
        self.assertEqual([b.id for b in spec.beats],
                         ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09"])
        self.assertEqual([b.id for b in spec.remotion_beats()], ["B02", "B03", "B04", "B05"])

    def test_beat_fields_carry_through(self):
        spec = load_visuals(REEL_0227)
        b05 = next(b for b in spec.beats if b.id == "B05")
        self.assertEqual(b05.template, "game-hud")
        self.assertTrue(b05.parody)
        self.assertEqual(b05.layout, "split")
        self.assertEqual(b05.duration_s, 4.5)
        self.assertEqual(b05.props["stack"]["items"][-1], "???")
        b01 = spec.beats[0]
        self.assertEqual(b01.generator, "real")
        self.assertEqual(b01.asset, "assets/music-ally-headline.png")
        self.assertIsNone(b01.template)
        self.assertFalse(b01.parody)  # absent -> False for non-remotion beats

    def test_gallery_covers_every_template(self):
        spec = load_visuals(GALLERY)
        self.assertEqual(
            {b.template for b in spec.remotion_beats()},
            {"text-card", "game-hud", "store-card", "stat-dashboard",
             "progress-bar", "timeline", "flowchart"},
        )


class InvalidSpecTests(unittest.TestCase):
    """Each mutation must be rejected with VisualsSpecError naming the problem."""

    def assertRejected(self, data, needle):
        with self.assertRaises(VisualsSpecError) as cm:
            parse_visuals(data)
        self.assertIn(needle, str(cm.exception))

    def test_missing_reel_id(self):
        d = _data()
        del d["reel_id"]
        self.assertRejected(d, "reel_id")

    def test_reel_id_not_filename_safe(self):
        d = _data()
        d["reel_id"] = "DH REEL/0227"
        self.assertRejected(d, "reel_id")

    def test_regions_must_match_the_versioned_geometry(self):
        d = _data()
        d["regions"]["graphic"]["h"] = 900
        self.assertRejected(d, "regions")

    def test_unknown_regions_version(self):
        d = _data()
        d["regions_version"] = "reels-9x16.top-bottom.v0"
        self.assertRejected(d, "regions_version")

    def test_remotion_beat_requires_template(self):
        d = _data()
        del _beat(d, "B02")["template"]
        self.assertRejected(d, "beats/1")

    def test_remotion_beat_requires_parody_flag(self):
        d = _data()
        del _beat(d, "B02")["parody"]
        self.assertRejected(d, "beats/1")

    def test_unknown_template(self):
        d = _data()
        _beat(d, "B02")["template"] = "pie-chart"
        self.assertRejected(d, "beats/1")

    def test_text_card_title_too_long(self):
        d = _data()
        _beat(d, "B02")["props"]["title"] = "X" * 41
        self.assertRejected(d, "beats/1/props/title")

    def test_blank_label_rejected(self):
        d = _data()
        _beat(d, "B02")["props"]["title"] = "   "
        self.assertRejected(d, "beats/1/props/title")

    def test_unknown_prop_key_rejected(self):
        d = _data()
        _beat(d, "B02")["props"]["colour"] = "#fff"
        self.assertRejected(d, "beats/1/props")

    def test_game_hud_stack_too_many_items(self):
        d = _data()
        _beat(d, "B05")["props"]["stack"]["items"].append("DIAMOND")
        self.assertRejected(d, "beats/4/props/stack/items")

    def test_store_card_requires_price(self):
        d = _data()
        del _beat(d, "B04")["props"]["price"]
        self.assertRejected(d, "beats/3/props")

    def test_props_checked_against_their_own_template(self):
        # game-hud props under a store-card template must fail (no title/price mix-up)
        d = _data()
        b = _beat(d, "B04")
        b["props"] = copy.deepcopy(_beat(d, "B05")["props"])
        self.assertRejected(d, "beats/3/props")

    def test_stat_value_must_be_number(self):
        d = _data()
        b = _beat(d, "B02")
        b["template"] = "stat-dashboard"
        b["props"] = {"title": "KPIs", "stats": [{"label": "Tickets", "value": "48k"}]}
        self.assertRejected(d, "beats/1/props/stats/0/value")

    def test_full_presenter_cannot_carry_a_graphic(self):
        d = _data()
        _beat(d, "B02")["layout"] = "full-presenter"
        self.assertRejected(d, "beats/1")

    def test_real_beat_requires_asset(self):
        d = _data()
        del _beat(d, "B01")["asset"]
        self.assertRejected(d, "beats/0")

    def test_none_beat_cannot_have_template(self):
        d = _data()
        _beat(d, "B07")["template"] = "text-card"
        self.assertRejected(d, "beats/6")

    def test_non_positive_duration(self):
        d = _data()
        _beat(d, "B03")["duration_s"] = 0
        self.assertRejected(d, "beats/2/duration_s")

    def test_duplicate_beat_ids(self):
        d = _data()
        _beat(d, "B03")["id"] = "B02"
        self.assertRejected(d, "duplicate beat id 'B02'")

    def test_load_reports_unparseable_json(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.visuals.json"
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(VisualsSpecError):
                load_visuals(p)


if __name__ == "__main__":
    unittest.main()
