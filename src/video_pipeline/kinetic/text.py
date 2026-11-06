"""Word-level text helpers shared by validation, voicing, and caption rules."""

from __future__ import annotations

from typing import List, Optional, Tuple

# Common function words: set lighter in the "contrast" voice, ignored when
# comparing a caption against on-screen text.
STOPWORDS = frozenset("""
a an the of in on at to for and or but is was were are be been it its i you your we he she
they them that this these those with as by from out up down around over into about than then
so if not no do did does had has have my me our their his her
""".split())

# A phrase ends after a word ending in one of these (closing quotes ignored).
PHRASE_END = ",;:.!?—–…"
_CLOSERS = "\"')”’]"


def norm_token(token: str) -> str:
    """Lowercase ``token`` with leading and trailing non-alphanumeric characters removed."""
    chars = list(token)
    while chars and not chars[0].isalnum():
        chars.pop(0)
    while chars and not chars[-1].isalnum():
        chars.pop()
    return "".join(chars).lower()


def words(text: str) -> List[str]:
    """Whitespace-separated tokens."""
    return text.split()


def phrase_span(text: str, phrase: str) -> Optional[Tuple[int, int]]:
    """Token index range ``[start, end)`` of the first place ``phrase`` occurs in
    ``text`` as whole, consecutive words (case-insensitive, edge punctuation
    ignored), or ``None``."""
    want = [norm_token(t) for t in words(phrase)]
    if not want or any(not w for w in want):
        return None
    have = [norm_token(t) for t in words(text)]
    for i in range(len(have) - len(want) + 1):
        if have[i:i + len(want)] == want:
            return (i, i + len(want))
    return None


def phrase_indices(tokens: List[str]) -> List[int]:
    """Phrase number (0-based) of each token; a token ending in punctuation closes its phrase."""
    out, phrase = [], 0
    for tok in tokens:
        out.append(phrase)
        if tok.rstrip(_CLOSERS)[-1:] in PHRASE_END and tok.rstrip(_CLOSERS):
            phrase += 1
    # a trailing boundary does not create an empty phrase
    return out


def is_function_word(token: str) -> bool:
    """Whether ``token`` is a function word, or a contraction of one (``I'd``, ``it's``)."""
    norm = norm_token(token)
    return norm in STOPWORDS or norm.replace("’", "'").split("'")[0] in STOPWORDS


def authored_lines(text: str) -> Optional[List[List[str]]]:
    """The author's lines (each a list of words) when ``text`` contains line breaks
    (newlines), else ``None``. Blank lines are ignored."""
    lines = [ln.split() for ln in text.split("\n") if ln.strip()]
    return lines if len(lines) > 1 else None
