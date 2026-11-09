# Documentation index

A routing map from each document to the part of the project it is the source of
truth for. Before completing a change, find the row(s) whose subject your change
touched and update those documents **in the same change** — stale docs are defects.
When you add or remove a document, or add a subsystem, update this index too.

## Top level

| Document | Source of truth for |
|---|---|
| [README.md](README.md) | What the project is; install/extras; the full CLI usage walkthrough; the `project.yml` configuration surface; repo layout. The entry point — any new command, flag, or config key is reflected here. |

## Pipeline stages and subsystems (`docs/`)

| Document | Source of truth for |
|---|---|
| [docs/reframe.md](docs/reframe.md) | The reframe subsystem: target format (aspect presets, resolution tiers, Auto), framing intents, the propose/render split + editable `reframe.def`, scale/pan/subject-y, composition lock, and the project-level `target`. |
| [docs/visuals.md](docs/visuals.md) | The comedy-forward visual track: the `visuals.json` contract (`schema/visuals.schema.json`), top-bottom region math, the DH-framed template library, `visuals-render`, and V2 placement/timing at handoff. |
| [docs/kinetic.md](docs/kinetic.md) | The kinetic-text overlay: the `kinetic.json` contract (`schema/kinetic.schema.json`), reading-pace timing, the static-title layout inside the safe rectangle, the motion vocabulary, caption rules, and `kinetic-check` / `kinetic-render`. |
| [docs/gui-schema.md](docs/gui-schema.md) | The pipeline side of the control-tower GUI contract: the `schema` subcommand (emit/`--check`), the `schema/` module layout, and how to add a step/flag/export target. (GUI repo: `video-pipeline-gui`.) |

## Configuration and renderer (layered config + Node)

| Document | Source of truth for |
|---|---|
| [config/glossary/README.md](config/glossary/README.md) | The layered caption vocabulary (global + per-identity glossary files). |
| [config/caption-styles/README.md](config/caption-styles/README.md) | The layered caption style + chunking config (look, casing, the words-per-cue range, the font allowlist and style caps). |
| [config/visual-styles/README.md](config/visual-styles/README.md) | The layered visual-template style config (frame colors, fonts, type scale with legibility floors, PARODY/brand labels). |
| [config/safezone/README.md](config/safezone/README.md) | The safe-zone template PNG → generated spec workflow. |
| [remotion/README.md](remotion/README.md) | The Remotion caption renderer (the style layer; the Node project the pipeline drives). |
