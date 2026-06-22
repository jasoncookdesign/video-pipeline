"""Repeatable `rows` param (INI-089 GUI authoring) — schema emit + argv assembly,
and that the resolved argv parses back through the CLI."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from video_pipeline import schema as S
from video_pipeline.schema.definition import build_schema
from video_pipeline.cli import build_parser, main
from video_pipeline.overlay.decision import OverlayList


class RowsSchemaTests(unittest.TestCase):
    def setUp(self):
        self.sch = build_schema()

    def test_schema_still_conformant(self):
        self.assertEqual(self.sch.validate(), [])

    def test_overlay_define_has_rows_param(self):
        t = next(t for t in self.sch.tasks if t.id == "overlay.define")
        ov = next(p for p in t.params if p.key == "overlays")
        self.assertEqual(ov.arity, "rows")
        self.assertEqual(ov.flag, "--add")

    def test_rows_param_emits_control_and_row_schema(self):
        d = self.sch.to_dict()
        t = next(t for t in d["tasks"] if t["id"] == "overlay.define")
        ov = next(p for p in t["params"] if p["key"] == "overlays")
        self.assertEqual(ov["control"], "rows")
        self.assertIn("row", ov)
        keys = [rf["key"] for rf in ov["row"]]
        self.assertIn("kind", keys)
        self.assertIn("placement", keys)


class RowsArgvTests(unittest.TestCase):
    def setUp(self):
        self.sch = build_schema()

    def test_one_add_per_row_only_nonempty_fields(self):
        argv = S.resolve_argv(
            self.sch, "overlay.define",
            {"profile": "reels-9x16", "overlays": [
                {"kind": "image", "src": "assets/chart.png", "start": "3.2",
                 "end": "7.8", "placement": "bottom-half", "transition": "fade",
                 "fade": "0.3"},
                {"kind": "video", "src": "b.mov", "at": "the demo",
                 "placement": "pip-rect", "rect": "60,1180,420,560", "audio": "duck"},
            ]},
            {"overlay.def": "work/overlay.def.yml"},
        )
        adds = [argv[i + 1] for i, a in enumerate(argv) if a == "--add"]
        self.assertEqual(len(adds), 2)
        self.assertEqual(
            adds[0],
            "kind=image;src=assets/chart.png;start=3.2;end=7.8;"
            "placement=bottom-half;transition=fade;fade=0.3",
        )
        self.assertEqual(
            adds[1],
            "kind=video;src=b.mov;at=the demo;placement=pip-rect;"
            "rect=60,1180,420,560;audio=duck",
        )
        # output binding still present
        self.assertEqual(argv[argv.index("-o") + 1], "work/overlay.def.yml")

    def test_empty_rows_emit_no_add(self):
        argv = S.resolve_argv(
            self.sch, "overlay.define",
            {"overlays": []}, {"overlay.def": "o.yml"},
        )
        self.assertNotIn("--add", argv)

    def test_row_missing_value_omits_field(self):
        argv = S.resolve_argv(
            self.sch, "overlay.define",
            {"overlays": [{"kind": "image", "src": "", "start": "1", "end": "2"}]},
            {"overlay.def": "o.yml"},
        )
        add = argv[argv.index("--add") + 1]
        self.assertNotIn("src=", add)            # empty src omitted
        self.assertEqual(add, "kind=image;start=1;end=2")


class RowsRoundTripCLITests(unittest.TestCase):
    """The argv the GUI resolves from rows must actually run through the CLI."""

    def test_resolved_argv_authors_the_file(self):
        sch = build_schema()
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "overlay.def.yml")
            argv = S.resolve_argv(
                sch, "overlay.define",
                {"overlays": [
                    {"kind": "image", "src": "a.png", "start": "3.2", "end": "7.8",
                     "placement": "bottom-half"},
                    {"kind": "video", "src": "b.mov", "start": "10", "end": "14",
                     "placement": "pip-rect", "rect": "60,1180,420,560", "audio": "duck"},
                ]},
                {"overlay.def": out},
            )
            # argv[0] is the program name; feed the rest to the real parser + handler
            ns = build_parser().parse_args(argv[1:])
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ns.func(ns)
            self.assertEqual(rc, 0)
            ov = OverlayList.read(out)
            self.assertEqual(len(ov.segments), 2)
            self.assertEqual(ov.segments[0].placement, "bottom-half")
            self.assertEqual(ov.segments[1].rect, (60, 1180, 420, 560))
            self.assertEqual(ov.segments[1].audio, "duck")


if __name__ == "__main__":
    unittest.main()
