"""video-pipeline command-line entry point.

Subcommands:
  safezone-gen <template.png> --profile NAME -o spec.json
      Derive a safe-zone spec from a template PNG.

  project-init "<YYYY-MM-DD Token Project - Hook>" --identity ID --profile NAME
      Scaffold a project's source/work/review/out/render layout + project.yml.

  reframe <input.mp4> -o <out.mp4> [--profile reels-9x16] [--mode static|dynamic]
      Run the landscape->portrait reframe probe (daily driver: needs MediaPipe).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROFILE_DIMS = {
    "reels-9x16": (1080, 1920),
    "story-9x16": (1080, 1920),
    "feed-portrait-4x5": (1080, 1350),
    "feed-square-1x1": (1080, 1080),
    "feed-landscape-16x9": (1920, 1080),
}


def _cmd_safezone_gen(args: argparse.Namespace) -> int:
    from .safezone import generate_spec

    spec = generate_spec(args.template, profile=args.profile, key=args.key)
    out = args.output or f"{spec.profile}.safezone.json"
    Path(out).write_text(spec.to_json(), encoding="utf-8")
    notch = "with notch" if spec.has_notch else "no notch"
    print(
        f"wrote {out}  profile={spec.profile}  "
        f"safe={spec.safe_fraction:.1%}  {notch}  "
        f"polygon={len(spec.polygon)} verts"
    )
    return 0


def _cmd_project_init(args: argparse.Namespace) -> int:
    from .project import create_project

    paths = create_project(
        args.root,
        args.folder_name,
        identity=args.identity,
        profile=args.profile,
        trim_filler=not args.no_trim_filler,
    )
    print(f"created project: {paths.root}")
    return 0


def _cmd_reframe(args: argparse.Namespace) -> int:
    from .reframe.probe import reframe

    out_w, out_h = _PROFILE_DIMS.get(args.profile, (1080, 1920))
    cmd = reframe(
        args.input, args.output,
        out_w=out_w, out_h=out_h, mode=args.mode, dry_run=args.dry_run,
    )
    if args.dry_run:
        print("ffmpeg command (dry run):")
        print("  " + " ".join(cmd))
    else:
        print(f"wrote {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="video-pipeline", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("safezone-gen", help="derive a safe-zone spec from a template PNG")
    g.add_argument("template")
    g.add_argument("--profile", default=None)
    g.add_argument("--key", default="auto", choices=["auto", "alpha", "color"])
    g.add_argument("-o", "--output", default=None)
    g.set_defaults(func=_cmd_safezone_gen)

    i = sub.add_parser("project-init", help="scaffold a new project folder")
    i.add_argument("folder_name")
    i.add_argument("--identity", required=True)
    i.add_argument("--profile", required=True)
    i.add_argument("--root", default=str(Path.home() / "Video" / "Projects"))
    i.add_argument("--no-trim-filler", action="store_true",
                   help="disable speech/filler trimming (e.g. live-off-the-mixer DJ sets)")
    i.set_defaults(func=_cmd_project_init)

    r = sub.add_parser("reframe", help="run the landscape->portrait reframe probe")
    r.add_argument("input")
    r.add_argument("-o", "--output", required=True)
    r.add_argument("--profile", default="reels-9x16")
    r.add_argument("--mode", default="static", choices=["static", "dynamic"])
    r.add_argument("--dry-run", action="store_true",
                   help="print the FFmpeg command without tracking/rendering")
    r.set_defaults(func=_cmd_reframe)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
