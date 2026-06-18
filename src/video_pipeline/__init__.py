"""video_pipeline — AI pre-editing pipeline for vertical short-form video.

The edit-decision artifacts are the product; renders are regenerable views of
them. This package holds the governed code (schemas, generators, reframe/render
logic). Projects (the data) live outside the repo under ``~/Video/Projects/``
and archive to Drive.

Phase 1 surface:
  - ``video_pipeline.safezone``  — derive a machine-readable safe-zone spec
    (polygon + bands, notch-aware) from an Instagram template PNG.
  - ``video_pipeline.manifest``  — load/validate ``project.yml`` and parse the
    project folder-name convention.
  - ``video_pipeline.project``   — scaffold a project's source/work/review/out/
    render layout.
  - ``video_pipeline.reframe``   — landscape->portrait auto-reframe: subject
    tracking (seam) -> crop plan -> FFmpeg command.
"""

__version__ = "0.1.0"
