"""Beat → Remotion props: the seam between the spec and the template library.

Mirrors the caption/card pattern: the pipeline builds one props JSON per clip and
the bundled Remotion project renders it; ``remotion/src/visuals/types.ts`` mirrors
:func:`beat_to_remotion_props` (``schemaVersion`` 1).

Every clip is sized to its region (:func:`~video_pipeline.visuals.regions.clip_geometry`)
— the graphic panel for ``split`` beats, the full canvas for ``full-graphic`` —
and carries ``safeBox`` (relative to the clip) so content stays inside the safe
zone. Clips run the beat's ``duration_s`` plus :data:`HOLD_TAIL_S` of held end
state, so a transcript-aligned window that runs longer than planned at handoff
still has picture (in durations mode the tail is simply unused).
"""

from __future__ import annotations

from .regions import clip_geometry
from .spec import Beat, VisualsSpec
from .style import VisualStyle

VISUAL_PROPS_SCHEMA_VERSION = 1

# Held, fully-settled end state appended to every clip (seconds).
HOLD_TAIL_S = 1.5

# Clip container. ProRes 4444 .mov keeps alpha and is the codec the bundled
# Remotion config already renders (captions, cards) — one render path.
CLIP_EXT = ".mov"

# template id (schema) -> Remotion composition id (remotion/src/Root.tsx)
TEMPLATE_COMPOSITIONS = {
    "text-card": "TextCard",
    "game-hud": "GameHud",
    "store-card": "StoreCard",
    "stat-dashboard": "StatDashboard",
    "progress-bar": "ProgressBar",
    "timeline": "Timeline",
    "flowchart": "Flowchart",
}


def clip_name(reel_id: str, beat_id: str, ext: str = CLIP_EXT) -> str:
    """``<reel_id>-<beat_id>.mov`` — the name the handoff references."""
    return f"{reel_id}-{beat_id}{ext}"


def clip_duration_s(beat: Beat) -> float:
    """Rendered clip length: the beat plus the held tail."""
    return round(beat.duration_s + HOLD_TAIL_S, 6)


def beat_to_remotion_props(spec: VisualsSpec, beat: Beat, style: VisualStyle) -> dict:
    """Build the props object for one ``generator: remotion`` beat."""
    if beat.generator != "remotion" or not beat.template:
        raise ValueError(f"beat {beat.id} is not a remotion beat (generator={beat.generator!r})")
    geom = clip_geometry(beat.layout, spec.regions)
    if geom is None:  # unreachable for a validated spec (full-presenter => generator none)
        raise ValueError(f"beat {beat.id} has layout {beat.layout!r}, which has no graphic clip")
    fps = spec.fps
    return {
        "schemaVersion": VISUAL_PROPS_SCHEMA_VERSION,
        "kind": "visual",
        "template": beat.template,
        "reelId": spec.reel_id,
        "beatId": beat.id,
        "layout": beat.layout,
        "parody": beat.parody,
        "fps": fps,
        "beatFrames": round(beat.duration_s * fps),
        "durationInFrames": round(clip_duration_s(beat) * fps),
        "dimensions": {"width": geom.placement.w, "height": geom.placement.h},
        "safeBox": {"x": geom.safe_box.x, "y": geom.safe_box.y,
                    "width": geom.safe_box.w, "height": geom.safe_box.h},
        "style": style.to_dict(),
        "props": beat.props,
    }
