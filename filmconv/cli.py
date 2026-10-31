"""Command-line converter (no GUI).

Examples:
    python -m filmconv.cli samples\\_ZNG0674.NEF -o output
    python -m filmconv.cli "D:\\Scans\\Roll 12" -o output --format tiff jpeg --base-rect 0.01 0.4 0.04 0.6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import pipeline, raw_io
from .settings import ADJUSTMENTS, CHANNELS, Settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="filmconv", description="Convert B&W negative RAW scans to positives.")
    p.add_argument("inputs", nargs="+", type=Path, help="RAW files and/or folders (a roll)")
    p.add_argument("-o", "--output", type=Path, required=True, help="output folder")
    p.add_argument("--format", nargs="+", choices=["tiff", "jpeg"], default=["tiff"])
    p.add_argument("--settings", type=Path, help="settings/preset JSON to start from")
    p.add_argument("--channel", choices=CHANNELS)
    p.add_argument("--base-rect", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                   help="film base sample rectangle, normalized 0..1 on the first frame")
    p.add_argument("--roll-levels", action="store_true",
                   help="use the first frame's auto levels for the whole roll")
    p.add_argument("--black-from-base", action="store_true", help="film base = pure black")
    for name in ADJUSTMENTS:
        p.add_argument(f"--{name}", type=float)
    args = p.parse_args(argv)

    settings = Settings.load(args.settings) if args.settings else Settings()
    if args.channel:
        settings.channel = args.channel
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

    for i, path in enumerate(files, 1):
        preview = pipeline.to_working(raw_io.load_preview(path), settings)
        if i == 1 and args.base_rect:
            settings.film_base_rect = tuple(args.base_rect)
        # The base is sampled once (first frame) and kept for the whole roll.
        pipeline.update_auto(preview, settings)
        settings.film_base_rect = None
        written = pipeline.export_file(path, settings, args.output, args.format)
        a = settings.auto
        print(f"[{i}/{len(files)}] {path.name} -> {', '.join(w.name for w in written)}"
              f"  (base {a.film_base:.4f}, D {a.d_black:.2f}..{a.d_white:.2f}, gamma {a.gamma:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
