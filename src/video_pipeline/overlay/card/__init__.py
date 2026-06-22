"""Source-card producer (INI-089 Phase B).

The highest-value overlay producer: an article / news card timed to the spoken
span. It follows the pipeline's content-vs-look split, same as captions —

  - **content** is a reviewable, editable JSON product (``CardContent``): the
    heading / body / footer / image / citation the card shows. The CEO edits the
    JSON before render, just like the caption/overlay decision files.
  - **look** is a deterministic Remotion ``Card`` component driven by props
    (``CardStyle``); branding/polish iterate Mac-side without touching content.

The card renders (Remotion, daily-driver) to a transparent layer that becomes a
``kind=card`` overlay in ``overlay.def`` — placement and window come from the
Phase-A primitive and the transcript→window proposer. The LLM never touches the
render path; capture/structuring produce the JSON, the renderer is deterministic.

Modules:
  - :mod:`content`  — ``CardContent`` + JSON round-trip (the product).
  - :mod:`capture`  — ``PageFetcher`` seam (Chrome MCP / Jina) + the pure
                      ``card_from_page`` structuring transform.
  - :mod:`props`    — ``CardStyle`` + content→Remotion-props + the ``kind=card``
                      ``overlay.def`` item builder + the card render argv.
"""

from __future__ import annotations
