# Kinetic-text overlay

A `kinetic.json` spec describes one continuous, transparent overlay layer for a
1080×1920 vertical video: a **static title** held in the top of the safe zone from the
first frame to the last, and a sequence of **kinetic text beats** beneath it. Each beat
reveals **clause by clause** at reading pace: the words of a clause arrive together, so the
reader takes in a unit of meaning at a time. It is never animated as one block or one word
at a time. The layer is rendered once and laid over any footage; it does not depend on what
the footage contains.

```
kinetic.json ──kinetic-check──► timeline + caption verdict
      │
      └──kinetic-render──► layers/kinetic/<reel_id>-kinetic.mov (+ review/kinetic/ stills)
```

## Contract: `schema/kinetic.schema.json`

Draft-07 JSON Schema, `schema_version: 1`. The Python boundary
(`video_pipeline.kinetic.spec`) validates the schema plus the rules JSON Schema cannot
express, and errors name the JSON path (`beats/3/accents/0/text`).

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `reel_id` | Filename-safe id; the layer is `<reel_id>-kinetic.mov` |
| `identity` | Optional style identity (`config/visual-styles/identities/<identity>.yml`) |
| `canvas` | `{w: 1080, h: 1920, fps: 24 \| 25 \| 30 \| 60}` |
| `title` | 1–36 characters, no word over 15, and it must wrap into the title block at the minimum title size (72 px), measured from the real glyph widths. Static for the whole layer, so any frame works as a cover |
| `caption`, `topic_terms` | Optional, together. See *Caption rules* |
| `beats` | 1–40 beats, in order |

A **text beat** has `id`, `kind: "text"`, `text` (≤ 150 characters, no word over 18 characters or wider than a line), `role`,
`motion`, and optionally `slot`, `align`, `voice`, `accents`, `exit`, `duration_s`:

| Field | Values |
|---|---|
| `role` | `statement` (display type, 60 px), `aside` (body type, 50 px), `question` (display type, 68 px). These are the sizes a beat is set at; a beat with authored line breaks may be set smaller to keep them (see *Line breaks*) |
| `motion` | How each clause's words arrive: `resolve` (blur to sharp), `rise`, `slide` (in from the right), `mask` (up from a clipped baseline), `gather` (in from alternating sides), `diminish` (rise, then the whole line shrinks, loosens, and softens while held) |
| `slot` | Vertical position inside the body container (below): `top` (default), `middle`, `bottom`. The default puts the first line of every block at the same height; the others are deliberate choices |
| `align` | `left` (default), `center`, `right`. Left is the rule; the others are deliberate choices |
| `voice` | `contrast` (default): function words light, content words heavy. `even`: one weight throughout |
| `accents` | Up to 4 per-word treatments, below |
| `exit` | How the beat leaves, below. Default: a quick fade |
| `duration_s` | Optional override, 1.5–30 s, and no faster than twice the reading-pace duration |

An **accent** is `{text, weight?, italic?, scale?, color?, treatment?}` with at least one
styling field. `text` must match whole, consecutive words of the beat's text
(case-insensitive, edge punctuation ignored); the first occurrence is styled; accents may
not overlap. The words of one accent never break across lines.

| Accent field | Values |
|---|---|
| `weight` | 300, 400, 500, 600, 700, 800, 900 |
| `italic` | `true` for the true italic face |
| `scale` | 0.8–1.4 times the line's size. The accent's words, which never break across lines, must fit one line at that scale. Fit is measured from the bundled fonts' real glyph widths (the widest weight and style), so wide capitals count for more than narrow letters: for example 12 capital W fit a statement line, and `extraordinarily` fits a question line up to scale 1.3 |
| `color` | `accent`, `warm`, `dim` (the style layer's colors) |
| `treatment` | A follow-up move once the word has arrived: `whip` (the word leans into an italic, and the words after it on its line slide over by 0.15 of its size, in step with the lean, so it never touches them; not combined with `italic: true`), `bloom` (color shifts to the accent), `swell` (grows 10%), or `none` |

An **exit** is `{motion?, duration_s?, linger_s?}`:

| Field | Meaning |
|---|---|
| `motion` | `fade` (default): clauses fade out quickly in turn over 0.4 s. `scatter`: gradual. Clauses leave in turn, each taking most of the exit and the next starting before it ends; each line drifts to its own side (alternating, like `gather` in reverse), rising a little, blurring, swelling 5%, and softening, so the line dissolves instead of switching off |
| `duration_s` | Length of the exit, 0.4–4 s (`fade` 0.4, `scatter` 2.0) |
| `linger_s` | Extra hold of the finished line before the exit starts, 0–6 s (default 0) |

A longer exit and any linger add to the beat's computed length, and the reveal keeps its
reading pace; an explicit `duration_s` on the beat still wins. A final text beat holds to the end
of the layer and never exits.

A **space beat** (`id`, `kind: "space"`, `duration_s` 0.5–6) shows no text: the footage is
left alone.

Beat ids must be unique ignoring case. The total length should stay within 60 seconds: a longer layer (up to the 120 second
limit) is accepted, and `kinetic-check` and `kinetic-render` print a warning that the reel
is over 60 s. Beyond 120 seconds is an error. A text beat's laid-out block must also fit
the body container (764 px tall, about 10 lines of statement type); a longer block is an error
naming the beat. A block with authored line breaks is first set smaller to fit (see *Line breaks*).

## Timing

A text beat stays on screen for `max(2.0, 0.5 + words / 2.5)` seconds unless `duration_s`
is set (`video_pipeline.kinetic.timing`). Inside that time (`video_pipeline.kinetic.voice`):

- About 55% of the beat reveals the line. A **clause** is a run of words ending at
  `, ; : . ! ? — – …`. All words of a clause start together and take 0.5 s to arrive.
  Clauses start one after another, each after the words before it have had their share of
  the reveal, so a longer clause gets proportionally longer to be read.
- The whole line drifts 40 px sideways while it reveals (the other way for right-aligned
  text) with a steep deceleration, counterbalancing the words that appear one after
  another, and keeps moving the way it came as it leaves.
- The full line then holds for at least 0.6 s.
- Words leave over the exit (0.4 s for `fade`), clause by clause, accelerating, and are gone by the beat's last
  frame. The final text beat, when it is the last beat, holds to the end of the layer.

At that pace a 30–60 second layer carries roughly 60–130 words including pauses.

## Voice and type

Each word is set individually. In the `contrast` voice, function words (the, a, of, and
so on) are weight 400 and content words 700 (`statement`), 600 (`aside`), or 800
(`question`), which gives a line rhythm without any markup; accents add heavier or lighter
weights, true italics, size, and color on top. Fonts are the style layer's display and body
families (Archivo and Inter for the Dyson Hope identity) in weights 300–900 with italics.
Text carries a soft dark glow so it stays readable over footage. Type sizes respect the
style layer's legibility floors.

One easing curve (`cubic-bezier(.2,.7,.2,1)`) for entrances, with no bounce, spring, or
overshoot. Expression comes from blur, scale, tracking, weight, italic, and position.

## Layout

Everything is drawn inside the shared full-frame safe rectangle `x 35, y 250, 880 × 1220`
(the same rectangle `visuals.json` calls `full_safe`). The top 360 px hold the title; a 40
px gap follows; the remaining 820 px are the body area for text beats. The composition
clips to the safe rectangle and insets content by the text glow's reach, so nothing is
drawn outside it, or in the gap under the title, at any frame.

The body copy sits in a **body container** at the bottom of the safe zone (inset by the
glow's reach). The container is as tall as the tallest block in the layer, so the whole
body is bottom-anchored while every block starts at the container's top, and the first
lines of all blocks share one height.

### Line breaks

Lines are chosen, like the lines of a stanza; the composition draws the lines it is given.

**Authored.** A newline in a beat's `text` is a line break the author chose. When a beat
has any, every line is shown exactly as written (a one-word line is allowed), and no
accent's words may cross a break.

Each such beat is set at the largest whole-pixel size, no bigger than its role's size and no
smaller than 36 px, at which every line fits the measure (accented words count at their
`scale`) and the laid-out block fits the body container. A beat whose lines already fit keeps
its role's size exactly, and a beat with no authored breaks always does. Line pitch, whip
pushes, and every word's width follow the beat's size. Only a beat that does not fit even at
36 px is an error, naming the line (or the block height) and the minimum size. `kinetic-check`
lists each beat that was set smaller, for example `note: B05 set at 46 px to keep its line
breaks`. The size used is the beat's `sizePx` in the props JSON.

**Automatic.** A beat with no newline is broken in Python
(`video_pipeline.kinetic.linebreak`) for the whole block at once, from the bundled fonts'
measured widths. The rules, in order of weight:

- No one-word lines (no orphans or widows) in a block of more than one line.
- Balance: every line, the last included, is as close to the full measure as the other rules allow.
- Break between clauses where possible; a break inside a clause costs a little, and
  ending a line on a function word (`the`, `I'd`) costs a little more.
- The fewest lines the rules above allow. An accent's words never split across lines.

A line is as tall as the beat's type size × 1.2, or as its largest accent if taller.

## Caption rules

When `caption` is present, `topic_terms` is required, and the caption must satisfy
`video_pipeline.kinetic.caption.check_caption`:

- One line, at most 220 characters, exactly one sentence, no `#`.
- Does not contain a title of two or more words.
- Shares no three-word run with the title or any beat's text, where the run contains at
  least two words that are not common function words. Curly and straight quotes and
  apostrophes compare equal.
- Contains at least `min(3, len(topic_terms))` of the topic terms (case-insensitive,
  matching from the start of a word, so `booth` matches `booths`).

A sentence ends at `.`, `!`, or `?` followed by whitespace and more text. An ellipsis
(`...` or `…`) does not end one. Abbreviations written with a trailing period and a space,
such as `Mr. Smith`, count as a sentence break.

## Commands

```bash
# Validate a spec and print its resolved timeline and caption verdict
video-pipeline kinetic-check episode.kinetic.json

# Render the layer (and one still per text beat) into a project
video-pipeline kinetic-render episode.kinetic.json --project . --stills
```

`kinetic-render` flags:

| Flag | Meaning |
|---|---|
| `--project DIR` | Project root. The layer goes to `<DIR>/layers/kinetic/`, stills to `<DIR>/review/kinetic/` |
| `--out-dir DIR` | Layer directory (overrides `--project`) |
| `--stills` | One PNG per text beat, taken 70% through the beat, over a neutral plate |
| `--frames-dir DIR` | Still directory (overrides `--project`; without `--project`, `<out-dir>/frames`) |
| `--preview-bg COLOR` | Plate color for stills (default: neutral gray) |
| `--identity NAME` | Style identity (default: the spec's, then `project.yml`'s, then global) |
| `--config-root DIR` | Config directory holding `visual-styles/` |
| `--dry-run` | Print the Remotion plan; write and spawn nothing |

`kinetic-check` prints a `note:` line for each beat set smaller than its role's size to keep its authored line breaks. It exits 2 with a message on an invalid spec or caption. `kinetic-render` also
exits 2 on an unknown identity, a missing destination, or a missing Remotion project.

## Output

ProRes 4444 `.mov` with alpha, 1080×1920, the spec's frame rate, the exact length of the
beats. The props JSON the composition rendered from sits beside it
(`<reel_id>-kinetic.props.json`); it carries every word's style and timing. Place the layer
above the footage in any editor.

## Tests

`tests/test_kinetic.py` covers timing, the spec boundary, caption rules, per-word voicing
and motion planning, props, render planning, and the CLI with Node and FFmpeg stubbed. The
real render is the local acceptance check:

```bash
VP_REMOTION_ACCEPTANCE=1 python -m pytest tests/test_kinetic.py -k Acceptance
```

It renders the fixtures and checks pixels: the clip's size and alpha; that nothing is
drawn outside the safe rectangle or in the gap under the title at four points of every
beat; that the title is visible from the first frame and never changes; that clauses arrive
progressively and not as a block; that default blocks share a first-line height and left edge; that a scatter exit lingers, then dissolves gradually while the lines drift apart; that lines leave inside their beat and the final line
holds; that `slot`, `align`, and accent color take effect; that accent phrases stay on one
line; that a beat with a long authored line is set smaller and its text stays inside the measure; and that the longest legal word and the fastest legal gather render completely.
Needs Node, FFmpeg, Pillow, and NumPy.
