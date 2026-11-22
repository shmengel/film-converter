"""Command-line converter (no GUI).

Examples:
    python -m filmconv.cli samples\\_ZNG0674.NEF -o output
    python -m filmconv.cli "D:\\Scans\\Roll 12" -o output --format tiff jpeg --base-rect 0.01 0.4 0.04 0.6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import export, pipeline, raw_io
from .settings import ADJUSTMENTS, CHANNELS, Settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="filmconv", description="Convert B&W negative RAW scans to positives.")
    p.add_argument("inputs", nargs="+", type=Path, help="RAW files and/or folders (a roll)")
    p.add_argument("-o", "--output", type=Path, required=True, help="output folder")
    p.add_argument("--format", nargs="+", choices=list(export.FORMATS), default=["tiff"])
    p.add_argument("--settings", type=Path, help="settings/preset JSON to start from")
    p.add_argument("--channel", choices=CHANNELS)
    p.add_argument("--base-rect", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                   help="film base sample rectangle, normalized 0..1 on the first frame")
    p.add_argument("--crop", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                   help="crop rectangle, normalized 0..1 on the camera image (before rotation)")
    p.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], help="rotate clockwise")
    p.add_argument("--flip", action="store_true", help="mirror left-right (emulsion-side scans)")
    p.add_argument("--roll-levels", action="store_true",
                   help="use the first frame's auto levels for the whole roll")
    p.add_argument("--black-from-base", action="store_true", help="film base = pure black")
    for name in ADJUSTMENTS:
        p.add_argument(f"--{name}", type=float)
    args = p.parse_args(argv)

    settings = Settings.load(args.settings) if args.settings else Settings()
    if args.channel:
        settings.channel = args.channel
    if args.crop:
        settings.crop = tuple(args.crop)
    if args.rotate is not None:
        # Marking the rotation as already decided stops the per-frame upright guess.
        settings.rotation = settings.auto.rotation = args.rotate
    if args.flip:
        settings.flip = True
    if args.black_from_base:
        settings.black_from_base = True
    if args.roll_levels:
        settings.auto_levels = False
    for name in ADJUSTMENTS:
        if getattr(args, name) is not None:
            setattr(settings, name, getattr(args, name))

    files: list[Path] = []
    for item in args.inputs:
        files.extend(raw_io.list_raw_files(item) if item.is_dir() else [item])
    if not files:
        print("No RAW files found.", file=sys.stderr)
        return 1

    first = None   # auto values of the first frame
    for i, path in enumerate(files, 1):
        # Fresh settings per frame: crop and upright guess are per frame.
        s = settings.copy()
        if first is None:
            if args.base_rect:
                s.film_base_rect = tuple(args.base_rect)
        else:
            # The base is sampled once (first frame) and kept for the whole roll.
            s.auto.film_base = first.film_base
            if args.roll_levels:
                s.auto.d_black, s.auto.d_white, s.auto.gamma = first.d_black, first.d_white, first.gamma
        preview = pipeline.to_working(raw_io.load_preview(path), s)
        pipeline.update_auto(preview, s)
        s.film_base_rect = None
        first = first or s.auto
        written = pipeline.export_file(path, s, args.output, args.format)
        a = s.auto
        print(f"[{i}/{len(files)}] {path.name} -> {', '.join(w.name for w in written)}"
              f"  (base {a.film_base:.4f}, D {a.d_black:.2f}..{a.d_white:.2f}, gamma {a.gamma:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
