"""Source-card producer (INI-089 Phase B) — pure logic: content round-trip,
capture→content structuring, props + overlay.def wiring + render argv."""

import json
import unittest

from video_pipeline.overlay.card.content import CardContent
from video_pipeline.overlay.card.capture import (
    CapturedPage,
    FixedFetcher,
    card_from_page,
    citation_from_url,
)
from video_pipeline.overlay.card.props import (
    CardStyle,
    build_card_overlay_item,
    card_render_command,
    card_to_remotion_props,
)


class CardContentTests(unittest.TestCase):
    def test_requires_heading(self):
        with self.assertRaises(ValueError):
            CardContent(heading="   ")

    def test_round_trips_losslessly(self):
        c = CardContent(
            heading="Markets rally on rate cut",
            body="Stocks jumped after the central bank trimmed rates.",
            footer="By A. Reporter",
            image="assets/card.png",
            citation="nytimes.com",
            source_url="https://www.nytimes.com/2026/06/21/markets.html",
        )
        again = CardContent.from_json(c.to_json())
        self.assertEqual(again.to_json(), c.to_json())
        self.assertEqual(again.heading, c.heading)
        self.assertEqual(again.image, "assets/card.png")

    def test_blank_image_normalizes_to_none(self):
        self.assertIsNone(CardContent(heading="H", image="  ").image)

    def test_from_dict_tolerates_missing_optionals(self):
        c = CardContent.from_dict({"heading": "Just a headline"})
        self.assertEqual(c.body, "")
        self.assertIsNone(c.image)

    def test_version_in_serialization(self):
        self.assertIn("card_content_version", json.loads(CardContent(heading="H").to_json()))


class CitationTests(unittest.TestCase):
    def test_strips_scheme_and_www(self):
        self.assertEqual(
            citation_from_url("https://www.nytimes.com/2026/x"), "nytimes.com"
        )

    def test_keeps_subdomain_other_than_www(self):
        self.assertEqual(citation_from_url("https://blog.example.org/p"), "blog.example.org")

    def test_no_host_is_empty(self):
        self.assertEqual(citation_from_url("not a url"), "")


class CardFromPageTests(unittest.TestCase):
    def _page(self, **kw):
        base = dict(
            url="https://www.theverge.com/2026/6/21/gadget",
            title="A very long headline about a gadget that keeps going well past",
            paragraphs=[
                "The lead paragraph sets up the story in one tight sentence.",
                "A second paragraph adds detail that may or may not fit the card.",
                "A third paragraph almost certainly will not fit.",
            ],
            site_name="The Verge",
            byline="By J. Writer",
            top_image="https://cdn.theverge.com/lead.jpg",
        )
        base.update(kw)
        return CapturedPage(**base)

    def test_heading_clipped_to_limit(self):
        c = card_from_page(self._page(), max_heading_chars=40)
        self.assertLessEqual(len(c.heading), 41)  # +ellipsis
        self.assertTrue(c.heading.endswith("…"))

    def test_body_respects_char_budget(self):
        c = card_from_page(self._page(), max_body_chars=70)
        self.assertLessEqual(len(c.body), 71)
        self.assertTrue(c.body.startswith("The lead paragraph"))

    def test_lead_paragraph_always_present_even_if_over_budget(self):
        page = self._page(paragraphs=["This single lead paragraph is definitely longer than the tiny budget allows."])
        c = card_from_page(page, max_body_chars=20)
        self.assertTrue(c.body.endswith("…"))
        self.assertTrue(c.body.startswith("This single"))

    def test_footer_prefers_byline(self):
        self.assertEqual(card_from_page(self._page()).footer, "By J. Writer")

    def test_footer_falls_back_to_site_name(self):
        self.assertEqual(card_from_page(self._page(byline="")).footer, "The Verge")

    def test_citation_and_image_and_provenance(self):
        c = card_from_page(self._page())
        self.assertEqual(c.citation, "theverge.com")
        self.assertEqual(c.image, "https://cdn.theverge.com/lead.jpg")
        self.assertEqual(c.source_url, "https://www.theverge.com/2026/6/21/gadget")

    def test_fixed_fetcher_seam(self):
        page = self._page()
        fetched = FixedFetcher(page).fetch("https://ignored")
        self.assertEqual(fetched.title, page.title)


class CardPropsTests(unittest.TestCase):
    def _content(self):
        return CardContent(heading="Headline", body="Body text", footer="Source",
                           citation="example.com")

    def test_props_shape_content_look_split(self):
        props = card_to_remotion_props(
            self._content(), width=1080, height=1920,
            identity="dyson-hope", profile="reels-9x16",
        )
        self.assertEqual(props["kind"], "card")
        self.assertEqual(props["dimensions"], {"width": 1080, "height": 1920})
        self.assertEqual(props["content"]["heading"], "Headline")
        self.assertIn("style", props)
        self.assertEqual(props["identity"], "dyson-hope")
        self.assertIn("schemaVersion", props)

    def test_custom_style_flows_into_props(self):
        style = CardStyle(bg_color="#000000", accent_color="#FF0000")
        props = card_to_remotion_props(self._content(), width=1080, height=1920, style=style)
        self.assertEqual(props["style"]["bg_color"], "#000000")
        self.assertEqual(props["style"]["accent_color"], "#FF0000")

    def test_build_card_overlay_item_defaults(self):
        item = build_card_overlay_item(0, "work/card.json", 3.0, 8.0, text="the article")
        self.assertEqual(item.kind, "card")
        self.assertEqual(item.src, "work/card.json")
        self.assertEqual(item.placement, "bottom-half")
        self.assertEqual(item.transition, "fade")
        self.assertEqual(item.audio, "mute")
        self.assertEqual(item.duration, 5.0)

    def test_card_overlay_item_pip(self):
        item = build_card_overlay_item(
            1, "c.json", 1.0, 4.0, placement="pip-rect", rect=(60, 1180, 420, 560)
        )
        self.assertEqual(item.rect, (60, 1180, 420, 560))

    def test_render_command_targets_card_composition(self):
        cmd = card_render_command("work/card.props.json", "layers/card.mov")
        self.assertEqual(cmd[:3], ["npx", "remotion", "render"])
        self.assertIn("Card", cmd)
        self.assertTrue(any(a.startswith("--props=") for a in cmd))
        self.assertIn("--codec=prores", cmd)
        self.assertTrue(any(a.startswith("--prores-profile=") for a in cmd))


if __name__ == "__main__":
    unittest.main()
