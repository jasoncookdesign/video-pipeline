# video-pipeline

AI **pre-editing** pipeline for vertical short-form video (Instagram Reels first;
other targets are profiles, not forks). The machine does the mechanical labor —
cut to length, reframe to vertical, caption, place overlays inside the safe zone
— and hands off an **editable project** (FCPXML → Premiere Pro). Pacing, taste,
transitions, and music placement stay with the operator.

> The edit-decision artifacts are the product; renders are regenerable views of
> them. The code is governed (JasonOS INI-085); execution is CEO-operated on the
> daily driver (Ono-Sendai), outside the director perimeter.

Full design rationale: governance repo `architecture/video-pipeline/shaping-brief.md`.

## Status — Phase 1 (probe)

Phase 1 is the trust-model probe. Shipped:

| Deliverable | Where |
|---|---|
| Repo scaffold + project contract (`project.yml` schema, `source/work/review/out/render` layout, `config/` scaffolds) | `schema/`, `src/video_pipeline/{manifest,project}.py`, `config/` |
| **Safe-zone spec generator** (template PNG → notch-aware polygon/mask) | `src/video_pipeline/safezone/`, spec at `config/safezone/reels-9x16.safezone.json` |
| **Reframe probe** (subject tracking → FFmpeg vertical crop) | `src/video_pipeline/reframe/` |

Later phases (rough cut + decision file, captions, safe-zone QC renderer, FCPXML
assembly, source-card overlays) are scoped in the brief §5 and not yet built.

## Install

```bash
pip install -e .            # core: numpy, Pillow, PyYAML, jsonschema
pip install -e '.[reframe]' # daily-driver extras: mediapipe, opencv-python
pip install -e '.[dev]'     # pytest
```

The core install + the test suite need **no** native MediaPipe/OpenCV build. The
reframe probe's real run does (daily driver only).

## Usage

```bash
# 1. Regenerate the safe-zone spec from a template PNG (update-resilient)
video-pipeline safezone-gen config/safezone/instagram-safe-zone-reels-9x16.png \
    --profile reels-9x16 -o config/safezone/reels-9x16.safezone.json

# 2. Scaffold a new project (creates source/work/review/out/render + project.yml)
video-pipeline project-init "2026-06-03 Reel Project - I used to make fun of ravers" \
    --identity dyson-hope --profile reels-9x16

# 3. Reframe a landscape clip to vertical (daily driver; --dry-run prints the cmd)
video-pipeline reframe source/clip.mp4 -o out/clip-9x16.mp4 --profile reels-9x16
```

## Test

```bash
pytest                                 # on the daily driver
python -m unittest discover -s tests   # stdlib-only fallback (no pytest needed)
```

## Layout

```
schema/project.schema.json        project.yml contract
config/safezone/                  template PNG + generated spec
config/glossary/                  layered caption vocabulary (global + per-identity)
src/video_pipeline/
  safezone/                       template PNG -> SafeZoneSpec (polygon + bands)
  reframe/                        tracker (seam) -> crop plan -> ffmpeg command
  manifest.py  project.py         project.yml load/validate + scaffolding
  glossary.py  cli.py
tests/                            unittest/pytest suite (runs without native deps)
docs/phase1.md                    what Phase 1 delivers + acceptance steps
```

Projects are **data**, not code: they live under `~/Video/Projects/` on the daily
driver and archive to Drive. They are never committed to this repo.
