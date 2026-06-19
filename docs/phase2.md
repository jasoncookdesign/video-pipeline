# Phase 2 — Rough cut + decision file

Phase 2 turns a transcript into the **editable decision file** — the product of
this phase — and renders a regenerable rough cut from it. The machine does
mechanical labor only (dropping filler, false starts, dead air); pacing, taste,
and the comedic pause stay with you.

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

### Tuning knobs

| Flag | Applies to | Default | What it does |
|---|---|---|---|
| `--silence-gap` | all | 0.6 | inter-word gap (s) above which dead air is trimmed |
| `--pad-lead` | all | 0.06 | padding (s) kept **before** speech at each cut |
| `--pad-tail` | all | 0.15 | padding (s) kept **after** speech — larger, because Whisper clips word ends early |
| `--no-false-starts` | all | off | disable immediate-repeat (stutter) trimming |
| `--model` | mlx-whisper | large-v3-turbo | HF model repo |
| `--online` | mlx-whisper | off (offline) | allow network to download an uncached model |
| `--noise-db` | `--transcriber silence` | -30 | silence threshold (dB); raise toward 0 to treat low-level non-speech (handling noise) as silence |
| `--min-silence` | `--transcriber silence` | 0.6 | min silence duration (s) to detect |

### Configuration (`project.yml`)

Every flag above has a persistent equivalent in the project's `project.yml`, so a
project keeps its rough-cut behaviour without re-passing flags. The CLI flag, when
given, overrides the file. Authoritative key list: `schema/project.schema.json`.

```yaml
# project.yml
rough_cut:
  trim_filler: true        # false = no speech-based cuts (--no-trim-filler)
  silence_gap_s: 0.6       # dead-air gap threshold (s)          (--silence-gap)
  keep_pad_lead_s: 0.06    # padding kept before each kept span  (--pad-lead)
  keep_pad_tail_s: 0.15    # padding kept after each kept span   (--pad-tail)
  detect_false_starts: true # drop immediate repeats/stutters    (--no-false-starts)
  extra_filler_words: []   # extra words to treat as filler, e.g. ["basically"]
```

Caption configuration (the `captions:` block, including the words-per-cue range)
is documented in [phase3.md](phase3.md) and `config/caption-styles/README.md`.

### mlx-whisper network: offline by default

The model (`whisper-large-v3-turbo`, ~1.6 GB) downloads **once** to
`~/.cache/huggingface/hub`. After that the pipeline runs **offline by default**
(`HF_HUB_OFFLINE=1` is set internally) — cache-only, no network, fastest startup.
You do **not** need to set `HF_HUB_OFFLINE` in your shell.

- **First run / new `--model`:** add `--online` to allow the one-time download.
  Set `HF_TOKEN` in your shell (a free read-only token from
  huggingface.co/settings/tokens) for faster, rate-limit-free downloads;
  huggingface_hub reads it automatically — never pass a token on the command line.
- **Offline + model not cached:** the pipeline prints a clear instruction to
  re-run with `--online`, rather than a cryptic Hub error.

## `trim_filler: false`

When `rough_cut.trim_filler` is false (or `--no-trim-filler`), the proposal makes
**no speech-based edits** — one whole-clip KEEP segment. Audio continuity is
preserved. This is the live-off-the-mixer DJ case in the initiative DoD.

## What runs where

| Piece | Where | Why |
|---|---|---|
| `propose`, decision round-trip, render-command assembly | sandbox (pure, unit-tested) | no native deps |
| mlx-whisper transcription | an Apple-Silicon Mac (`[roughcut]` extra) | local-first, word-level timestamps |
| FFmpeg trim/concat render | anywhere with an FFmpeg binary | rough preview |

Transcription, the silence model (derived from word-gap timestamps), and the
render command are all behind seams, so WhisperX / ElevenLabs Scribe (deferred)
slot in without touching the proposal logic.
