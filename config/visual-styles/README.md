# Visual styles — the template style layer (#62)

The Remotion visual templates (`remotion/src/visuals/`) are driven entirely by
props. This directory is the **style** half of those props: the frame's colors,
fonts, type scale, and labels. It layers exactly like `caption-styles/`:

    global.yml                 # shared defaults across every identity
    identities/<identity>.yml  # per-identity overrides (identity wins)

The identity comes from `visuals.json` (`identity`), else the project's
`project.yml`, else only the global layer applies. Unknown keys are ignored.

## Keys

| Key | Meaning |
| --- | --- |
| `ground` / `surface` / `surface_2` | Frame background and panel fills (hex). |
| `line` / `line_2` | Hairline and stronger rule colors. |
| `text` / `text_2` | Primary and secondary text. |
| `accent` / `accent_ink` | The signal color and the text color used on accent fills. |
| `warm` | Secondary signal (game currency, prices). |
| `alert` | Locked/negative states (e.g. a locked achievement). |
| `display_font` / `body_font` / `mono_font` | Families; must be in the caption font allowlist (`config/caption-styles/README.md`). |
| `label_px` | Mono labels, eyebrows, the PARODY tag. Floor **28**. |
| `body_px` | Body text and list items. Floor **40**. |
| `heading_px` | Panel headings and stat numbers' base size. Floor **56**. |
| `title_px` | Hero titles; long titles shrink toward the floor, never below it. Floor **72**. |
| `parody_label` | Text of the PARODY tag shown on beats with `parody: true`. |
| `brand_label` | Mono label in the frame header (empty = none). |

Type sizes are px at the 1920-px canvas height. The floors are enforced at the
Python boundary (`video_pipeline.visuals.style`) so a template is always legible
at the graphic-panel size on a phone (28 px ≈ 10 pt, 40 px ≈ 14 pt on a 390-pt-wide
screen). The floors also ride in every clip's props (`minType`): hero titles fit
down to the title floor (72), other fitted headings and numbers down to the body
floor (40), never below. The schema's length caps are sized so the longest
allowed strings fit at those floors (`tests/fixtures/visuals/max-length.visuals.json`).
