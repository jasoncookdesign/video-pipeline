"""Caption rules for a kinetic-text reel.

The caption is the one text channel a viewer and a recommendation system both
read that the video does not already carry, so it must say what the video is
about without repeating the title or the on-screen lines.
"""

from __future__ import annotations

import re
from typing import List, Sequence

from .text import STOPWORDS

MAX_CAPTION_CHARS = 220
MIN_TOPIC_TERMS = 3

_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")
# A sentence ends at . ! or ? (optionally followed by closing quotes/brackets)
# and whitespace, with more text after it. A period inside "3.5" does not split.
_SENTENCE_BREAK = re.compile(r"""(?<=[.!?])["')\]]*\s+(?=\S)""")




_QUOTES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})


def _tokens(text: str) -> List[str]:
    """Lowercased words; curly quotes read as straight, edge quotes are not part of a word."""
    return _WORD.findall(text.translate(_QUOTES).lower())


def _trigrams(tokens: Sequence[str]):
    return {tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)}


def _content_words(gram) -> int:
    return sum(1 for w in gram if w not in STOPWORDS)


def check_caption(
    caption: str,
    title: str,
    beat_texts: Sequence[str],
    topic_terms: Sequence[str],
) -> List[str]:
    """Return the list of rule violations (empty when the caption is acceptable).

    Rules: non-empty, one line, at most :data:`MAX_CAPTION_CHARS`, exactly one
    sentence (an ellipsis does not end one), no ``#``, does not contain a title of
    two or more words, shares no three-word run
    (with at least two content words) with the title or any beat text, and
    contains at least ``min(MIN_TOPIC_TERMS, len(topic_terms))`` topic terms.
    """
    problems: List[str] = []
    text = caption.strip()
    if not text:
        return ["caption is empty"]
    if "\n" in text or "\r" in text:
        problems.append("caption must be a single line")
    if len(text) > MAX_CAPTION_CHARS:
        problems.append(f"caption is {len(text)} characters (limit {MAX_CAPTION_CHARS})")
    if "#" in text:
        problems.append("caption must not contain hashtags (#)")
    if len(_SENTENCE_BREAK.split(re.sub(r"\.{2,}", "\u2026", text))) > 1:
        problems.append("caption must be one sentence")

    cap_tokens = _tokens(text)
    cap_joined = " " + " ".join(cap_tokens) + " "
    title_tokens = _tokens(title)
    if len(title_tokens) >= 2 and " " + " ".join(title_tokens) + " " in cap_joined:
        problems.append("caption repeats the title")

    cap_grams = _trigrams(cap_tokens)
    sources = [("the title", title)] + [(f"beat {i + 1}", t) for i, t in enumerate(beat_texts)]
    for where, source in sources:
        for gram in sorted(cap_grams & _trigrams(_tokens(source))):
            if _content_words(gram) >= 2:
                problems.append(f"caption repeats the phrase '{' '.join(gram)}' from {where}")
                break

    need = min(MIN_TOPIC_TERMS, len(topic_terms))
    present = [t for t in topic_terms if re.search(r"(?<!\w)" + re.escape(t), text, re.IGNORECASE)]
    if len(present) < need:
        problems.append(
            f"caption names {len(present)} of the topic terms {list(topic_terms)} (needs {need})"
        )
    return problems
