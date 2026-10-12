# Visual track — comedy-forward Reels (#62 part A)

A per-Reel **visual spec** (`visuals.json`) drives a library of DH-framed Remotion
templates and lands the rendered clips on the editor timeline, placed in the
graphic panel and timed per beat. The spec is written upstream (the `reels`
plugin, #62 part B) or by hand; this repo owns its contract.

```
visuals.json ──validate──► visuals-render ──► layers/visuals/<reel_id>-<beat_id>.mov (+ stills)
      │                                                     │
      └────────────── handoff --visuals [--transcript] ─────┴──► V2 (FCP7 XML) / lane 1 (FCPXML)
```

## The contract: `schema/visuals.schema.json`

Draft-07 JSON Schema, `schema_version: 1`. Consumers pin a copy; breaking changes
bump `schema_version`, region changes bump `regions_version`. Validation happens
once, at the Python boundary (`video_pipeline.visuals.spec`), including each
template's props; errors name the JSON path (`beats/3/props/price`).

Top level: `schema_version`, `reel_id` (filename-safe), optional `identity`
(style layer) and `title`, `canvas` (`1080×1920`, `fps` 24/25/30/60), `layout`
(`top-bottom`), `regions_version`, `regions`, `beats`.

Each beat: `id` (filename-safe, unique ignoring case — ids name clip files),
`spoken` (`""` for a silent hold), `duration_s` (0.25–60), `layout` (`split` | `full-graphic` | `full-presenter`),
`generator` (`remotion` | `higgsfield` | `real` | `none`), and:

- `remotion` → `template`, `props`, `parody` required; no `asset`.
- `real` / `higgsfield` → `asset` required; no `template`/`props`.
- `none` → no `asset`/`template`/`props`.
- `full-presenter` → `generator` must be `none`. It only leaves V2 empty: V1
  shows unchanged; any presenter punch-in is the editor's call.
- `full-graphic` → needs a graphic (`generator` is not `none`).
- `split` + `none` is a plain split: nothing on V2, the panel area shows V1.
- optional `notes` (never rendered).

## Regions (`reels-9x16.top-bottom.v1`)

Derived from `config/safezone/reels-9x16.safezone.json` by
`video_pipeline.visuals.regions.derive_regions` (largest safe rect inside each
panel, computed exactly over the notch-aware bands). The schema pins these values
and a test asserts they still equal the derivation.

| Region | x, y, w, h | Meaning |
|---|---|---|
| `graphic` | 0, 0, 1080, 960 | Top panel; a split clip covers it (background bleeds to the edges) |
| `graphic_safe` | 35, 250, 1010, 710 | Where template content lives in a split clip |
| `presenter` | 0, 960, 1080, 960 | Bottom panel; V1 shows through |
| `presenter_safe` | 35, 960, 880, 510 | Notch-free safe rect — frame the face here when recording |
| `full_safe` | 35, 250, 880, 1220 | Where content lives in a full-graphic clip |

Clip sizes: `split` → 1080×960 at (0, 0); `full-graphic` → 1080×1920;
`full-presenter` → no clip.

## Templates

Each is a Remotion composition (`remotion/src/visuals/`) inside the shared DH
frame: ground fill, mono header row (brand label, PARODY tag when
`parody: true`), hairline rule, barcode motif in the bleed, accent seam on the
panel edge. Everything settles within ~55% of the beat. Text length caps live in
the schema and were sized by rendering every field at its cap
(`tests/fixtures/visuals/max-length.visuals.json`) — the longest allowed strings
still fit at the legibility floors. Props:

| Template id | Composition | Props |
|---|---|---|
| `text-card` | `TextCard` | `title`, `eyebrow?`, `subtitle?`, `source?` |
| `game-hud` | `GameHud` | `title`, `currency? {label, value}`, `stack? {label, items[1–6]}`, `achievement? {label, state: locked\|unlocked}`, `toast?` |
| `store-card` | `StoreCard` | `title`, `price`, `cta`, `eyebrow?`, `price_note?`, `features[0–3]?`, `badge?` |
| `stat-dashboard` | `StatDashboard` | `title`, `stats[1–4] {label, value (±999,999), from?, prefix?, suffix?, decimals?}` (count-up), `footnote?` |
| `progress-bar` | `ProgressBar` | `label`, `to_pct`, `from_pct?`, `status?`, `caption?` |
| `timeline` | `Timeline` | `items[2–5] {label, when?}`, `title?`, `emphasis_last?` |
| `flowchart` | `Flowchart` | `steps[2–5]` (last = punchline, highlighted), `title?` |

Look comes from the layered style config `config/visual-styles/` (see its
README); type sizes have legibility floors enforced at the Python boundary
(label 28, body 40, heading 56, title 72 px at 1920 high). Fonts: Archivo,
Inter, IBM Plex Mono — the DH system's families, all SIL OFL 1.1, bundled via
`@fontsource` (no substitution needed).

## Render: `video-pipeline visuals-render`

```bash
video-pipeline visuals-render work/visuals.json --project . --frames 3
video-pipeline visuals-render work/visuals.json --project . --beat B05 --dry-run
```

One clip per `remotion` beat: `<project>/layers/visuals/<reel_id>-<beat_id>.mov`
(props JSON alongside), **ProRes 4444 with alpha**, sized to its region,
`duration_s + 1.5 s` long (the tail holds the settled end state so a
transcript-aligned window that runs long still has picture). `--frames N` grabs N
stills per clip into `<project>/review/visuals/` (the last on the settled final
frame). Non-remotion beats are skipped. Flags: `--out-dir`, `--frames-dir`,
`--beat ID` (repeatable; an unknown id exits 2), `--identity` (default: the
spec's, then `project.yml`'s; an unknown identity exits 2), `--config-root`,
`--dry-run`.

Why ProRes 4444 `.mov` over H.264 `.mp4`: it is the codec the bundled Remotion
config already renders (one render path for captions, cards, visuals), it keeps
alpha so templates may use transparency later without a format change, and it is
intraframe (scrubs cleanly in the NLE). The cost is file size, which is small for
clips of a few seconds.

## Handoff: V2 placement and timing

`video-pipeline handoff` (and `export premiere|fcpxml`) take `--visuals
<visuals.json>` (default with `--project`: `work/visuals.json` if present),
`--visuals-dir` (default `layers/visuals/`), and `--transcript`.

- **Timing.** Without `--transcript`, planned `duration_s` values are laid
  end-to-end from 0 and used as **cut time**. With `--transcript`, each beat's
  `spoken` line is located with the overlay window proposer (phrase match, else a
  keyword cluster covering ≥ 50% of the line's keywords), searching only after
  the previous beat; a beat runs until the next one starts. Unlocated or silent
  beats follow the previous beat by their planned duration (squeezed, or dropped,
  if the next located beat comes first). Those source-time windows are remapped
  to the cut with the same kept-span mapping as overlays (`remap_window`).
- **FCP7 XML (Premiere).** V1 base cut, **V2 visuals**, V3 captions, V4
  composite guide. Each beat is a clipitem at native size (Scale 100) with Basic
  Motion `center` = clip-center offset from frame center normalized by the
  sequence size (split → `0, -0.25`; full-graphic → `0, 0`), `alphatype
  straight`.
- **FCPXML (Resolve / FCP).** Each beat is an asset with its own format
  (1080×960 or the project format), connected on **lane 1** to the base clip
  containing its start, with `adjust-conform type="none"` and `adjust-transform
  position` in percent of frame height, y up (split → `0 25`). Captions move to
  lane 2, the composite guide up one. Roles use `videoRole` (`Visuals`,
  `Captions`, `Composite`) per the FCPXML DTD.
- `full-presenter` beats leave V2 empty. `real` / `higgsfield` beats are listed as
  "place by hand" notes. A window longer than the rendered clip, or running past
  the end of the cut, is trimmed with a note; clips not yet rendered are listed.
- Errors exit 2 with a message: an invalid visuals.json, an fps mismatch, or a
  `--profile` whose canvas differs from the spec's.

**Acceptance still open:** the transform encodings follow Apple's FCPXML
reference and Premiere's own default-center export (`0,0`), but opening the
generated projects in Premiere and Resolve and confirming the panel sits on top
is the local acceptance check.
