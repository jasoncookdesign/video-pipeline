# Phase 5 — FCPXML handoff

The pipeline's last automated step. It assembles the accepted layers — the
**base cut** (the rough-cut decision file's KEEP segments) over the **reframed
vertical clip**, plus the **styled caption overlay** — into a single FCPXML that
opens in **Adobe Premiere Pro** (primary), **DaVinci Resolve** (free; FCPXML
import confirmed), or **Final Cut Pro**. The editor's last mile — pacing,
transitions, music placement, final mix — stays with the CEO (shaping brief §5).

As with the rest of the pipeline, the assembly is **pure and unit-tested**; the
only machine-specific requirement is that the referenced media (the reframed
clip and the rendered overlay) exists on the editing machine so the project
relinks.

## Flow

```
decision file (KEEP segments) ─▶ base cut: asset-clips on the spine
                                  (labeled "Base Cut", over the reframed clip)
reframed clip ──────────────────▶ the base-cut clips reference it (reframe baked)
caption file ─▶ remap to cut-time ─▶ cut-time caption file ─▶ (captions-render) ─▶ overlay
                                  ▲                                                  │
                                  └── the cut drops segments, so cues must move ─────┘
overlay (.mov) ─────────────────▶ Captions track: one connected clip (lane 1)
                              =  out/<project>.fcpxml
```

## Two design decisions

**The reframe is baked, not a transform.** The base-cut clips reference the
*reframed* vertical clip (`work/<clip>-9x16.mp4`), which the CEO already accepted
on real footage in Phase 1. Re-expressing the reframe as an FCPXML transform
would be lossy and editor-dependent; referencing the rendered clip is frame-exact
and imports identically everywhere. (A future "editable reframe" mode could emit
a transform instead; not built.)

**Captions are remapped to cut time.** Caption cues are timed against the
*source*. The base cut drops segments, so the timeline is **compressed** — a cue
at source `4.0s` may belong at cut `3.1s`. `fcpxml.timeline.remap_track` rebuilds
the caption track in cut time: cues that fall entirely in dropped regions are
omitted, cues that straddle a cut boundary are clipped, and per-word (karaoke)
timings move with them. The runner writes this as `out/<project>.captions.cut.yml`;
render *that* file to the overlay so the captions line up with the compressed cut.
When `trim_filler: false` (a single whole-clip KEEP), the remap is the identity
and captions pass through unchanged.

## The FCPXML

- **FCPXML 1.10**, a single project `format` at the profile dimensions, rational
  frame-exact times (`frameDuration = 1/fps`; every time an integer multiple).
- **Base Cut** — each KEEP segment is its own `asset-clip` on the `<spine>`,
  referencing the reframed asset with a cumulative timeline `offset` and a source
  in-point (`start`). Separate clips mean the editor can drop a transition
  between cuts. Audio rides here (`audioRole="dialogue"`).
- **Captions** — the overlay as one connected `asset-clip` (`lane="1"`, custom
  role `Captions`) anchored to the first base clip, spanning the whole cut. The
  overlay has video + alpha, no audio.

## Usage

```bash
# Assemble the handoff (writes the .fcpxml + the cut-time caption file)
video-pipeline fcpxml review/decision.yml -o out/reel.fcpxml \
    --reframed work/clip-9x16.mp4 \
    --captions review/captions.yml \
    --profile reels-9x16 --fps 30

# Render the aligned overlay from the cut-time caption file, then re-open the
# FCPXML (it already references out/reel.captions.mov):
video-pipeline captions-render out/reel.captions.cut.yml \
    -o out/reel.captions.mov --safezone config/safezone/reels-9x16.safezone.json
```

Without `--captions`, the FCPXML is base-cut only (still opens with the reframed,
trimmed timeline ready to edit). `--overlay` overrides the overlay path the
FCPXML references; `--project-name` / `--event` set the FCPXML labels.

## What's pure vs. machine-specific

| Piece | Where | Tested in CI |
|---|---|---|
| Base-cut timeline + cumulative offsets | `fcpxml/timeline.py` | ✅ |
| Source→cut time remap (drop / clip / karaoke) | `fcpxml/timeline.py` | ✅ |
| FCPXML 1.10 document (rationals, assets, spine, lanes) | `fcpxml/document.py` | ✅ |
| Path/file-URI resolution + file writes | `fcpxml/runner.py` | reads/writes only |
| Opening the project + relinking media; overlay render | Premiere / Resolve / FCP | local acceptance |

The remaining unverified surface is the same as the other phases' daily-driver
seams: the actual import into Premiere/Resolve and the overlay render. The
document structure, timeline math, and remap are fully covered by the suite.
