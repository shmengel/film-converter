"""Tone stage: density -> balanced positive (display values 0..1).

Film-type independent: it only sees density, so it will also work per
channel for color negatives later.
"""
from __future__ import annotations

import numpy as np

from .settings import AutoValues, Settings

BLACK_PERCENTILE = 0.2
WHITE_PERCENTILE = 99.8
TARGET_MIDTONE = 0.45   # where the median of the image lands after auto-balance
GAMMA_LIMITS = (0.5, 2.0)
MIN_RANGE = 0.05        # minimum density range, avoids blowing up blank frames


def analysis_area(density: np.ndarray, margin: float) -> np.ndarray:
    """Inner part of the (already cropped) image, without the edges."""
    h, w = density.shape[:2]
    dy, dx = int(h * margin), int(w * margin)
    return density[dy:h - dy or None, dx:w - dx or None]


def analyze(density: np.ndarray, settings: Settings) -> tuple[float, float, float]:
    """Auto black point, white point and midtone gamma from the image area."""
    vals = analysis_area(density, settings.analysis_margin).ravel()
    vals = vals[np.isfinite(vals)]
    d_black, d_median, d_white = (float(x) for x in np.percentile(
        vals, [BLACK_PERCENTILE, 50.0, WHITE_PERCENTILE]))
    if settings.black_from_base:
        d_black = 0.0
    d_white = max(d_white, d_black + MIN_RANGE)
    mid = np.clip((d_median - d_black) / (d_white - d_black), 1e-3, 0.999)
    gamma = float(np.clip(np.log(TARGET_MIDTONE) / np.log(mid), *GAMMA_LIMITS))
    return d_black, d_white, gamma


def apply_tone(density: np.ndarray, settings: Settings, auto: AutoValues | None = None) -> np.ndarray:
    auto = auto or settings.auto
    d_black, d_white = auto.d_black, auto.d_white
    rng = d_white - d_black

    # Blacks / whites move the end points (up to a quarter of the range each).
    lo = d_black - settings.blacks / 100.0 * 0.25 * rng
    hi = d_white - settings.whites / 100.0 * 0.25 * rng
    v = np.clip((density - lo) / max(hi - lo, 1e-6), 0.0, 1.0)

    v = v ** auto.gamma

    # Exposure in EV acts on linear light; v is roughly gamma-2.2 encoded.
    if settings.exposure:
        v = v * 2.0 ** (settings.exposure / 2.2)
        v = np.clip(v, 0.0, 1.0)

    if settings.shadows:
        v = v + settings.shadows / 100.0 * 0.6 * v * (1.0 - v) ** 2
    if settings.highlights:
        v = v + settings.highlights / 100.0 * 0.6 * v ** 2 * (1.0 - v)

    if settings.contrast > 0:
        s = v * v * (3.0 - 2.0 * v)              # smoothstep S-curve
        v = v + settings.contrast / 100.0 * (s - v)
    elif settings.contrast < 0:
        v = 0.5 + (v - 0.5) * (1.0 + settings.contrast / 200.0)

    return np.clip(v, 0.0, 1.0).astype(np.float32)
