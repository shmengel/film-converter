"""High-level processing: preview analysis, rendering and export.

Flow: RAW -> linear RGB -> working (film type) -> density -> tone -> crop.
Auto values are computed on the preview and stored in Settings.auto, then
reused unchanged for the full-resolution export.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import export, raw_io
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
    if settings.crop is not None:
        d = region(d, settings.crop)
    return d


def update_auto(working: np.ndarray, settings: Settings, force: bool = False) -> None:
    """Fill settings.auto from a preview. Levels are recomputed when
    auto_levels is on (or forced, or never computed yet)."""
    update_film_base(working, settings)
    if force or settings.auto_levels or settings.auto.d_black is None:
        a = settings.auto
        a.d_black, a.d_white, a.gamma = analyze(density(working, settings), settings)


def render(working: np.ndarray, settings: Settings) -> np.ndarray:
    """Positive image (display values 0..1) using the stored auto values."""
    return apply_tone(density(working, settings), settings)


def output_paths(raw_path: Path, out_dir: Path, formats: list[str]) -> dict[str, Path]:
    return {fmt: out_dir / (raw_path.stem + export.FORMATS[fmt]) for fmt in formats}


def export_file(raw_path: str | Path, settings: Settings, out_dir: str | Path,
                formats: list[str]) -> list[Path]:
    """Full-resolution export. Settings.auto must already be filled (from the
    preview), so the result matches the on-screen preview."""
    raw_path, out_dir = Path(raw_path), Path(out_dir)
    if settings.auto.film_base is None or settings.auto.d_black is None:
        raise ValueError("Auto values missing: analyze the preview first (update_auto).")
    out_dir.mkdir(parents=True, exist_ok=True)
    working = to_working(raw_io.load_linear(raw_path), settings)
    positive = render(working, settings)
    written = []
    for fmt, path in output_paths(raw_path, out_dir, formats).items():
        export.save(path, positive, fmt)
        written.append(path)
    return written
