"""TDD for the manifest contract and project scaffolding."""

import tempfile
import unittest
from pathlib import Path

import yaml

from tests._util import REPO_ROOT  # noqa: F401  (ensures src/ on path)
from video_pipeline.manifest import (
    parse_folder_name,
    kebab,
    manifest_from_dict,
    load_manifest,
)
from video_pipeline.project import create_project, SUBDIRS
from video_pipeline.glossary import load_glossary


class TestFolderName(unittest.TestCase):
    def test_parse(self):
        fn = parse_folder_name("2026-06-03 Reel Project - I used to make fun of ravers")
        self.assertEqual(fn.date, "2026-06-03")
        self.assertEqual(fn.token, "Reel")
        self.assertEqual(fn.hook, "I used to make fun of ravers")

    def test_render_filename(self):
        fn = parse_folder_name("2026-06-03 Reel Project - I used to make fun of ravers")
        self.assertEqual(
            fn.render_filename(),
            "2026-06-03-reel-i-used-to-make-fun-of-ravers.mp4",
        )

    def test_profile_token_is_generic(self):
        fn = parse_folder_name("2026-06-03 Short Project - YouTube hook here")
        self.assertEqual(fn.token, "Short")
        self.assertTrue(fn.render_filename().startswith("2026-06-03-short-"))

    def test_kebab(self):
        self.assertEqual(kebab("I used to make fun of ravers!"),
                         "i-used-to-make-fun-of-ravers")

    def test_rejects_bad_name(self):
        with self.assertRaises(ValueError):
            parse_folder_name("just some folder")


class TestManifestValidation(unittest.TestCase):
    def test_defaults_trim_filler_true(self):
        m = manifest_from_dict({"identity": "dyson-hope", "profile": "reels-9x16"})
        self.assertTrue(m.trim_filler)

    def test_trim_filler_off(self):
        m = manifest_from_dict({
            "identity": "dyson-hope",
            "profile": "reels-9x16",
            "rough_cut": {"trim_filler": False},
        })
        self.assertFalse(m.trim_filler)

    def test_derived_filenames(self):
        m = manifest_from_dict({"identity": "sigil-zero", "profile": "reels-9x16"})
        self.assertEqual(m.safezone_spec_filename, "reels-9x16.safezone.json")
        self.assertEqual(m.identity_glossary_filename, "sigil-zero.yml")

    def test_missing_required_field_rejected(self):
        import jsonschema
        with self.assertRaises(jsonschema.ValidationError):
            manifest_from_dict({"identity": "dyson-hope"})  # no profile

    def test_unknown_field_rejected(self):
        import jsonschema
        with self.assertRaises(jsonschema.ValidationError):
            manifest_from_dict({
                "identity": "dyson-hope", "profile": "reels-9x16", "bogus": 1,
            })

    def test_bad_identity_pattern_rejected(self):
        import jsonschema
        with self.assertRaises(jsonschema.ValidationError):
            manifest_from_dict({"identity": "Dyson Hope", "profile": "reels-9x16"})

    def test_example_manifest_is_valid(self):
        data = yaml.safe_load((REPO_ROOT / "project.example.yml").read_text())
        m = manifest_from_dict(data)
        self.assertEqual(m.identity, "dyson-hope")
        self.assertEqual(m.profile, "reels-9x16")


class TestProjectScaffold(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_layout(self):
        folder = "2026-06-03 Reel Project - I used to make fun of ravers"
        paths = create_project(self.root, folder, identity="dyson-hope", profile="reels-9x16")
        for sub in SUBDIRS:
            self.assertTrue((paths.root / sub).is_dir(), f"missing {sub}/")
        self.assertTrue(paths.manifest.exists())

    def test_render_ships_empty(self):
        folder = "2026-06-03 Reel Project - Hook"
        paths = create_project(self.root, folder, identity="dyson-hope", profile="reels-9x16")
        self.assertEqual(list(paths.render.iterdir()), [])

    def test_manifest_round_trips_and_validates(self):
        folder = "2026-06-03 Reel Project - I used to make fun of ravers"
        paths = create_project(
            self.root, folder, identity="dyson-hope", profile="reels-9x16",
            trim_filler=False,
        )
        m = load_manifest(paths.root)
        self.assertEqual(m.identity, "dyson-hope")
        self.assertEqual(m.profile, "reels-9x16")
        self.assertFalse(m.trim_filler)
        self.assertEqual(m.metadata.get("render_filename"),
                         "2026-06-03-reel-i-used-to-make-fun-of-ravers.mp4")

    def test_rejects_bad_folder_name(self):
        with self.assertRaises(ValueError):
            create_project(self.root, "bad folder", identity="x", profile="y")

    def test_refuses_overwrite(self):
        folder = "2026-06-03 Reel Project - Hook"
        create_project(self.root, folder, identity="dyson-hope", profile="reels-9x16")
        with self.assertRaises(FileExistsError):
            create_project(self.root, folder, identity="dyson-hope", profile="reels-9x16")


class TestGlossary(unittest.TestCase):
    CONFIG = REPO_ROOT / "config"

    def test_layers_merge_identity_wins(self):
        g = load_glossary(self.CONFIG, "dyson-hope")
        self.assertIn("FFmpeg", g.terms)       # from global
        self.assertIn("SIGIL.ZERO", g.terms)   # from identity

    def test_corrections_applied_whole_word_ci(self):
        g = load_glossary(self.CONFIG, "dyson-hope")
        fixed = g.apply_corrections("today on sigil zero we used ff mpeg")
        self.assertIn("SIGIL.ZERO", fixed)
        self.assertIn("FFmpeg", fixed)


if __name__ == "__main__":
    unittest.main()
