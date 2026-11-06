"""Line breaking for a text beat: where each line ends.

The composition renders the lines it is given, so the browser never decides where a
clause breaks. The breaker picks, for the whole block at once, the set of breaks with
the lowest cost under four rules:

* **Balance.** Every line, the last included, should be about as full as the others
  (squared shortfall from the full measure, so one very short line costs far more than
  two slightly short ones).
* **Clauses.** Break between clauses when possible. Breaking inside a clause costs a
  little; ending a line on a function word (``the``, ``I'd``) costs a little more.
* **No orphans or widows.** A line holding a single word, first or last, costs a lot.
* **Compactness.** Each extra line costs a fixed amount, so a block takes the fewest
  lines that the other rules allow.

An accent's words (a *unit*) never split across lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

# Fixed cost of a line, of breaking inside a clause, of ending a line on a function
# word, and of a one-word line, against a balance cost between 0 and 1 per line.
LINE_COST = 0.25
MID_CLAUSE_COST = 0.12
WEAK_END_COST = 0.15
ONE_WORD_COST = 0.8


@dataclass(frozen=True)
class Unit:
    width: float        # px, the unit's words and the spaces between them
    words: int
    clause: int         # clause number of the unit's last word
    weak_end: bool      # the unit ends on a function word


def break_units(units: Sequence[Unit], space: float, max_width: float) -> List[int]:
    """Line number (0-based) of each unit. ``space`` is the width of a word space in px.
    A unit wider than ``max_width`` gets a line to itself."""
    n = len(units)
    if n == 0:
        return []
    inf = float("inf")
    best = [inf] * (n + 1)
    prev = [0] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        width, words = 0.0, 0
        for i in range(j - 1, -1, -1):          # the line holds units i..j-1
            width += units[i].width + (space if words else 0.0)
            words += units[i].words
            if width > max_width and i < j - 1:
                break
            if best[i] == inf:
                continue
            cost = LINE_COST + (max(0.0, max_width - width) / max_width) ** 2
            if words == 1:
                cost += ONE_WORD_COST
            if j < n and units[j - 1].clause == units[j].clause:
                cost += MID_CLAUSE_COST
                if units[j - 1].weak_end:
                    cost += WEAK_END_COST
            if best[i] + cost < best[j] - 1e-12:
                best[j], prev[j] = best[i] + cost, i
    lines = [0] * n
    j, line = n, 0
    cuts = []
    while j > 0:
        cuts.append((prev[j], j))
        j = prev[j]
    for line, (i, j) in enumerate(reversed(cuts)):
        for k in range(i, j):
            lines[k] = line
    return lines
