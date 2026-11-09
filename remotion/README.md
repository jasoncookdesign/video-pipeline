# Remotion caption renderer — the style layer

This is the **style layer** of the captions phase. The Python pipeline owns
*timing* (word-level transcript → 2–4-word cues, glossary-corrected) and *placement*
(a safe-zone-derived caption box); this Remotion project owns *look* (font, colour,
stroke, emphasis, casing, animation) and renders a transparent caption overlay.

It is Node/React and runs on the **local machine** — not in the pure-Python test suite, exactly like mlx-whisper. The Python side is fully unit-tested; the props
contract it emits is the seam.

## One-time setup (local machine)

```sh
cd remotion
npm install
```

## Render

The pipeline writes a props JSON (`video-pipeline captions … --props work/caption-props.json`).
Render the overlay from it:

```sh
npx remotion render src/index.ts Captions out/captions.mov \
    --props=work/caption-props.json --codec=prores --prores-profile=4444
```

`video-pipeline captions-render <caption-file.yml> -o out/captions.mov` does this for
you: it rebuilds props from the (possibly hand-edited) caption file + the project's
style/safe-zone config, then invokes the command above.

Output is **ProRes 4444 with alpha** — composite it over the reframed video in
Premiere/Resolve (or onto a labelled FCPXML track in Phase 5). Captions stay an
independent, restyleable layer.

## Props contract

`src/types.ts` mirrors `video_pipeline.captions.export.track_to_remotion_props`
(`schemaVersion: 1`): `dimensions`, `fps`, `safeBox` (px, inside the safe polygon),
the resolved `style`, and `cues` (frame-accurate `from` / `durationInFrames` +
`emphasis` word indices). `npm run studio` opens the preview with sample props.

## Fonts

`font_family` must resolve on the render machine. Install the family (Archivo /
IBM Plex Mono / Inter per identity) system-wide, or add `@remotion/google-fonts`
loading in `Captions.tsx` if you prefer bundled web fonts.

## Visual templates

`src/visuals/` holds the comedy-forward template library — `TextCard`, `GameHud`,
`StoreCard`, `StatDashboard`, `ProgressBar`, `Timeline`, `Flowchart` — each a
composition sized by `calculateMetadata` from its props (`dimensions`,
`durationInFrames`). Props mirror `video_pipeline.visuals.props.beat_to_remotion_props`
(`src/visuals/types.ts`); `video-pipeline visuals-render` builds and renders them.
See `docs/visuals.md`.

## Kinetic text

`src/kinetic/Kinetic.tsx` registers the `KineticText` composition: one transparent,
canvas-sized layer with a static title and reading-pace text beats, clipped to the
safe rectangle. Props mirror `video_pipeline.kinetic.props.kinetic_to_remotion_props`
(`src/kinetic/types.ts`); `video-pipeline kinetic-render` builds and renders them.
See `docs/kinetic.md`.
