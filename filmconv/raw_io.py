"""Reading RAW files into linear floating-point data."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rawpy

RAW_EXTENSIONS = {".nef", ".nrw", ".dng", ".cr2", ".cr3", ".arw", ".raf", ".orf", ".rw2", ".pef"}
PREVIEW_MAX_SIZE = 1600
# DHT keeps more fine detail than LibRaw's default (AHD): measured ~10% more
# high-frequency detail on real scans, at the same speed. B&W film is grey,
# so the demosaic's colour handling does not matter here, only sharpness.
DEMOSAIC = rawpy.DemosaicAlgorithm.DHT


def list_raw_files(folder: str | Path) -> list[Path]:
    """RAW files in a folder, ordered by filename (EXIF dates may be wrong)."""
    folder = Path(folder)
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS]
    return sorted(files, key=lambda p: p.name.lower())


def load_linear(path: str | Path, half_size: bool = False) -> np.ndarray:
    """Demosaic a RAW file to linear float32 RGB in 0..1.

    No auto-brightening, no tone curve (gamma 1), camera white balance and the
    camera's native ("raw") color space: for B&W film we only need clean
    per-channel transmission, not accurate colors.
    """
    # Open via a Python file object: LibRaw's own path handling can fail on
    # non-ASCII (e.g. Hebrew) Windows paths.
    with open(Path(path), "rb") as f, rawpy.imread(f) as raw:
        rgb = raw.postprocess(
            gamma=(1, 1),
            no_auto_bright=True,
            output_bps=16,
            use_camera_wb=True,
            output_color=rawpy.ColorSpace.raw,
            half_size=half_size,
            demosaic_algorithm=None if half_size else DEMOSAIC,
        )
    return rgb.astype(np.float32) / 65535.0


def full_size(path: str | Path) -> tuple[int, int]:
    """(height, width) of the full-resolution output, without decoding it."""
    with open(Path(path), "rb") as f, rawpy.imread(f) as raw:
        s = raw.sizes
        h, w = s.height, s.width
        return (w, h) if s.flip in (5, 6) else (h, w)


def downscale(img: np.ndarray, max_size: int) -> np.ndarray:
    """Shrink by an integer factor using block averaging (fast, alias-free)."""
    factor = int(np.ceil(max(img.shape[:2]) / max_size))
    if factor <= 1:
        return img
    h = img.shape[0] // factor * factor
    w = img.shape[1] // factor * factor
    img = img[:h, :w]
    shape = (h // factor, factor, w // factor, factor) + img.shape[2:]
    return img.reshape(shape).mean(axis=(1, 3), dtype=np.float32)


def load_preview(path: str | Path, max_size: int = PREVIEW_MAX_SIZE) -> np.ndarray:
    """Fast, downscaled linear RGB for on-screen previews."""
    return downscale(load_linear(path, half_size=True), max_size)
