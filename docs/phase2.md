# Phase 2 — Rough cut + decision file

Phase 2 turns a transcript into the **editable decision file** — the product of
this phase — and renders a regenerable rough cut from it. The machine does
mechanical labor only (dropping filler, false starts, dead air); pacing, taste,
and the comedic pause stay with the CEO.

> The decision file *is the deliverable*. The rough cut is just a render of it.

## Flow

```
media  ->  transcribe (mlx-whisper)  ->  propose  ->  decision file  ->  rough render
                                                          (review/)        (work/)
```

`source/` is never modified. The decision file lands in `review/`; the rough cut
in `work/`.

## The decision file

A flat YAML list of segments that partition the clip end-to-end. Each segment is
KEEP or DROP; the rough cut is the concatenation of the KEEP segments, in order.

```yaml
source: 2026-06-03-reel.mp4
profile: reels-9x16
trim_filler: true
duration: 12.4
kept_duration: 9.8
segments:
  - {i: 0, start: 0.0,   end: 0.34,  keep: false, reason: silence,     text: ""}
  - {i: 1, start: 0.26,  end: 3.10,  keep: true,  reason: "",          text: "Hey what's up everyone"}
  - {i: 2, start: 3.10,  end: 3.52,  keep: false, reason: filler,      text: "um"}
  - {i: 3, start: 3.52,  end: 8.90,  keep: true,  reason: "",          text: "so today we're..."}
```

**To edit the cut**, flip `keep:` on a segment (or nudge `start` / `end`), then
re-render. The edit round-trips — the file you hand-edit parses back losslessly.

`reason` is advisory: `filler | false-start | silence | manual`.

## CLI

```bash
# Propose (daily driver — needs mlx-whisper, the [roughcut] extra):
video-pipeline roughcut "<clip.mp4>" -o review/decision.yml --render work/rough.mp4

# Re-propose from a cached transcript (no MLX needed):
video-pipeline roughcut "<clip.mp4>" --transcript work/transcript.json -o review/decision.yml

# ASR-free fallback (no model, no network) — trims DEAD AIR ONLY:
video-pipeline roughcut "<clip.mp4>" --transcriber silence -o review/decision.yml --render work/rough.mp4

# Preserve audio continuity — NO speech-based edits (DJ record showcases):
video-pipeline roughcut "<clip.mp4>" -o review/decision.yml --no-trim-filler

# Round-trip: re-render after hand-editing the decision file:
video-pipeline roughcut-render review/decision.yml -i "<clip.mp4>" -o work/rough.mp4
```

## `trim_filler: false`

When `rough_cut.trim_filler` is false (or `--no-trim-filler`), the proposal makes
**no speech-based edits** — one whole-clip KEEP segment. Audio continuity is
preserved. This is the live-off-the-mixer DJ case in the initiative DoD.

## What runs where

| Piece | Where | Why |
|---|---|---|
| `propose`, decision round-trip, render-command assembly | sandbox (pure, unit-tested) | no native deps |
| mlx-whisper transcription | Ono-Sendai (`[roughcut]` extra) | Apple-Silicon, local-first |
| FFmpeg trim/concat render | anywhere with an FFmpeg binary | rough preview |

Transcription, the silence model (derived from word-gap timestamps), and the
render command are all behind seams, so WhisperX / ElevenLabs Scribe (deferred)
slot in without touching the proposal logic.
