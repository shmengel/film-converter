"""High-level processing: preview analysis, rendering and export.

Flow: RAW -> linear RGB -> working (film type) -> density -> crop -> tone
-> sharpen -> orient.
Auto values are computed on the preview and stored in Settings.auto, then
reused unchanged for the full-resolution export.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import export, framing, orientation, raw_io
from .film_types import get_film_type, region
from .settings import Settings
from .tone import analyze, apply_tone


def to_working(rgb: np.ndarray, settings: Settings) -> np.ndarray:
    return get_film_type(settings.film_type).to_working(rgb, settings)


def update_film_base(working: np.ndarray, settings: Settings) -> None:
    """Sample the base from the picked rectangle, or estimate it if unknown."""
    ft = get_film_type(settings.film_type)
    if settings.film_base_rect is not None:
        settings.auto.film_base = ft.sample_base(working, settings.film_base_rect)
    elif settings.auto.film_base is None:
        settings.auto.film_base = ft.estimate_base(working)


def density(working: np.ndarray, settings: Settings) -> np.ndarray:
    """Cropped density image."""
    d = get_film_type(settings.film_type).to_density(working, settings.auto.film_base)
    crop = settings.effective_crop()
    if crop is not None:
        d = region(d, crop)
    return d


def update_auto(working: np.ndarray, settings: Settings, force: bool = False) -> None:
    """Fill settings.auto from a preview. Levels are recomputed when
    auto_levels is on (or forced, or never computed yet)."""
    update_film_base(working, settings)
    if settings.auto_crop and settings.crop is None:
        # Detect per frame: the frame sits differently in every shot.
        base = framing.estimate_base(working) or settings.auto.film_base
        settings.auto.crop = framing.detect_crop(working, base)
    if force or settings.auto_levels or settings.auto.d_black is None:
        a = settings.auto
        a.d_black, a.d_white, a.gamma = analyze(density(working, settings), settings)
    if settings.auto.rotation is None:
        guess_rotation(working, settings)


def guess_rotation(working: np.ndarray, settings: Settings) -> None:
    """Guess once whether the frame is upside down, and apply the guess unless
    the user already rotated the frame themselves."""
    positive = apply_tone(density(working, settings), settings)
    settings.auto.rotation = orientation.guess_rotation(positive)
    apply_auto_rotation(settings)


def apply_auto_rotation(settings: Settings) -> None:
    if settings.rotation == 0 and settings.auto.rotation:
        settings.rotation = settings.auto.rotation


def orient(img: np.ndarray, settings: Settings) -> np.ndarray:
    """Apply flip, then clockwise rotation."""
    if settings.flip:
        img = img[:, ::-1]
    k = (settings.rotation // 90) % 4
    if k:
        img = np.rot90(img, -k)  # negative k = clockwise
    return np.ascontiguousarray(img)


def flip_view(settings: Settings, vertical: bool = False) -> None:
    """Mirror the frame as it is seen on screen (after its rotation).

    The view is R(rotation) . F^flip, with F the left-right mirror. Mirroring
    the view left-right gives H . R(r) . F^f = R(-r) . F^(f+1), because a mirror
    reverses the sense of rotation. Up-down is left-right plus 180 degrees.
    Crop and film-base rectangles stay in camera coordinates, so they still fit."""
    settings.flip = not settings.flip
    settings.rotation = ((180 if vertical else 0) - settings.rotation) % 360


def _point_to_view(x: float, y: float, s: Settings) -> tuple[float, float]:
    if s.flip:
        x = 1.0 - x
    for _ in range((s.rotation // 90) % 4):
        x, y = 1.0 - y, x          # 90 degrees clockwise
    return x, y


def _point_from_view(x: float, y: float, s: Settings) -> tuple[float, float]:
    for _ in range((s.rotation // 90) % 4):
        x, y = y, 1.0 - x          # 90 degrees counter-clockwise
    if s.flip:
        x = 1.0 - x
    return x, y


def _map_rect(rect, s: Settings, fn):
    (ax, ay), (bx, by) = fn(rect[0], rect[1], s), fn(rect[2], rect[3], s)
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


def rect_to_view(rect, s: Settings):
    """Normalized rect in camera coordinates -> as seen after flip/rotation."""
    return _map_rect(rect, s, _point_to_view)


def rect_from_view(rect, s: Settings):
    """Inverse of rect_to_view (e.g. a crop drawn on the rotated view)."""
    return _map_rect(rect, s, _point_from_view)


SHARPEN_RADIUS = 1.0   # full-resolution pixels (matches the ~5 px edge blur of the scans)
SHARPEN_MAX_AMOUNT = 1.5


def sharpen(img: np.ndarray, settings: Settings, scale: float = 1.0) -> np.ndarray:
    """Capture sharpening (unsharp mask) on the positive.

    scale = full-resolution pixels per pixel of img. The radius is defined at
    full resolution, so on a downscaled preview it shrinks; below half a
    pixel it is skipped (the preview is too small to show it anyway)."""
    amount = settings.sharpening / 100.0 * SHARPEN_MAX_AMOUNT
    radius = SHARPEN_RADIUS / scale
    if amount <= 0 or radius < 0.5:
        return img
    blur = cv2.GaussianBlur(img, (0, 0), radius)
    return np.clip(img + amount * (img - blur), 0.0, 1.0)


def render(working: np.ndarray, settings: Settings, scale: float = 1.0) -> np.ndarray:
    """Positive image (display values 0..1) using the stored auto values.
    scale: full-resolution pixels per working pixel (1.0 at export)."""
    positive = apply_tone(density(working, settings), settings)
    return orient(sharpen(positive, settings, scale), settings)


def output_paths(raw_path: Path, out_dir: Path, formats: list[str],
                 stem: str | None = None) -> dict[str, Path]:
    stem = stem or raw_path.stem
    return {fmt: out_dir / (stem + export.suffix(fmt)) for fmt in formats}


def render_full(raw_path: str | Path, settings: Settings) -> np.ndarray:
    """Full-resolution positive. Settings.auto must already be filled (from
    the preview), so the result matches the on-screen preview."""
    if settings.auto.film_base is None or settings.auto.d_black is None:
        raise ValueError("Auto values missing: analyze the preview first (update_auto).")
    working = to_working(raw_io.load_linear(Path(raw_path)), settings)
    return render(working, settings)


def save_positive(positive: np.ndarray, raw_path: str | Path, out_dir: str | Path,
                  formats: list[str], stem: str | None = None) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for fmt, path in output_paths(Path(raw_path), out_dir, formats, stem).items():
        export.save(path, positive, fmt)
        written.append(path)
    return written


def export_file(raw_path: str | Path, settings: Settings, out_dir: str | Path,
                formats: list[str]) -> list[Path]:
    """Full-resolution export in the given formats."""
    return save_positive(render_full(raw_path, settings), raw_path, out_dir, formats)
