# config/glossary/

Layered, repo-resident caption vocabulary. Loaded by the caption phase; the
transcriber owns *timing*, the glossary owns *spelling*.

## Layers

- `global.yml` — terms shared across every identity (tool names, recurring jargon).
- `identities/<identity>.yml` — per-identity terms (brand names, project names).

Layers compose: `global` + the project's `identity` layer, identity winning on
key collisions. `identity` comes from `project.yml`.

## Two parts per layer

- `terms` — canonical spellings to **preserve** (e.g. `SIGIL.ZERO`, `FFmpeg`).
- `corrections` — `mishear -> canonical` map, applied as a **post-transcription**
  substitution (whole-word, case-insensitive). Whisper-family models only weakly
  honour prompt biasing, so correcting afterwards is more reliable than priming.

## Seeding

These files are **seeds**, to be expanded from the JasonOS KB identity docs
(`knowledge/clients/dyson-hope-family/`, etc.) as real transcripts surface
recurring mishears. Add a correction the first time the pipeline mis-spells a
proper noun; it then lands right on the first pass for every later project.
