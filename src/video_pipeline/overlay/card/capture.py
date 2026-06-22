"""Upstream capture → CardContent (INI-089 Phase B).

Two layers, split the way the transcriber seam is (``roughcut/transcript.py``):

  - **The fetch is a seam.** A :class:`PageFetcher` reads a URL and returns a
    :class:`CapturedPage` of already-extracted fields. Real implementations sit
    behind the Protocol — a Chrome-MCP fetcher (render JS, read the article) and a
    Jina-reader fetcher (``r.jina.ai`` → clean markdown) — and run where the
    network/daily-driver is, not in the JasonOS sandbox. ``FixedFetcher`` lets the
    structuring logic be unit-tested with no network.

  - **The structuring is pure.** :func:`card_from_page` turns a captured page into
    a :class:`~video_pipeline.overlay.card.content.CardContent` deterministically:
    pick the heading, trim the body to a legible length, derive the citation from
    the domain, carry the lead image. No LLM in this path — the result is a
    reviewable JSON the CEO edits before render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol
from urllib.parse import urlparse

from .content import DEFAULT_MAX_BODY_CHARS, DEFAULT_MAX_HEADING_CHARS, CardContent


@dataclass
class CapturedPage:
    """Already-extracted fields from a fetched page (the fetcher's output).

    ``paragraphs`` is the article body split into paragraphs (lead first), so the
    structuring step can build a short body without re-parsing HTML. ``site_name``
    and ``byline`` feed the footer; ``top_image`` is the lead image if any.
    """

    url: str
    title: str
    paragraphs: List[str] = field(default_factory=list)
    site_name: str = ""
    byline: str = ""
    top_image: Optional[str] = None


class PageFetcher(Protocol):
    """Reads a URL and returns a :class:`CapturedPage`. The capture seam."""

    def fetch(self, url: str) -> CapturedPage: ...


class FixedFetcher:
    """A no-network fetcher returning a preset page — for tests and dry runs."""

    def __init__(self, page: CapturedPage):
        self._page = page

    def fetch(self, url: str) -> CapturedPage:  # noqa: D401 - trivial
        return self._page


def citation_from_url(url: str) -> str:
    """The short source label for a URL — the bare registrable host.

    ``https://www.nytimes.com/2026/...`` → ``nytimes.com``. Empty string for a URL
    with no host (so a hand-entered citation is never clobbered by a bad parse).
    """
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _clip(text: str, limit: int) -> str:
    """Trim ``text`` to ``limit`` chars on a word boundary, adding an ellipsis."""
    text = " ".join(text.split())  # collapse whitespace
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip()
    return (cut or text[:limit].rstrip()) + "…"


def card_from_page(
    page: CapturedPage,
    *,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
    max_heading_chars: int = DEFAULT_MAX_HEADING_CHARS,
) -> CardContent:
    """Structure a captured page into a reviewable :class:`CardContent`.

    Deterministic: heading from the title (clipped), body from the lead paragraphs
    joined up to ``max_body_chars``, footer from the byline (falling back to the
    site name), citation from the domain, image from the lead image. The CEO edits
    the result before render.
    """
    heading = _clip(page.title, max_heading_chars)

    body_parts: List[str] = []
    used = 0
    for para in page.paragraphs:
        para = " ".join(para.split())
        if not para:
            continue
        if not body_parts:
            body_parts.append(para)
            used = len(para)
        elif used + 1 + len(para) <= max_body_chars:
            body_parts.append(para)
            used += 1 + len(para)
        else:
            break
    body = _clip(" ".join(body_parts), max_body_chars)

    footer = page.byline.strip() or page.site_name.strip()

    return CardContent(
        heading=heading,
        body=body,
        footer=footer,
        image=page.top_image,
        citation=citation_from_url(page.url),
        source_url=page.url,
    )
