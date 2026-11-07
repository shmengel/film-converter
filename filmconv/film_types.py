"""Film-type stage: turns linear camera RGB into film density.

Everything specific to a kind of film lives here, so color negative (C-41)
can be added later as another FilmType without touching the tone stage.
"""
from __future__ import annotations

import numpy as np

from .settings import Settings

# Weights for "luminance" in the camera's raw color space (green counts double,
# like the Bayer pattern). For B&W film color accuracy does not matter.
_LUMA_WEIGHTS = np.array([0.25, 0.5, 0.25], dtype=np.float32)
_CHANNEL_INDEX = {"red": 0, "green": 1, "blue": 2}
_EPS = 1e-6


def region(img: np.ndarray, rect: tuple[float, float, float, float]) -> np.ndarray:
    """Slice of img inside a normalized (x0, y0, x1, y1) rectangle."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = rect
    c0, c1 = sorted((int(round(x0 * w)), int(round(x1 * w))))
    r0, r1 = sorted((int(round(y0 * h)), int(round(y1 * h))))
    return img[r0:max(r1, r0 + 1), c0:max(c1, c0 + 1)]


class FilmType:
    name = ""
    label = ""

    def to_working(self, rgb: np.ndarray, settings: Settings) -> np.ndarray:
        """Linear RGB -> working transmission image (what the negative passes)."""
        raise NotImplementedError

    def sample_base(self, working: np.ndarray, rect) -> float:
        """Film base transmission from a user-picked rectangle."""
        raise NotImplementedError

    def estimate_base(self, working: np.ndarray) -> float:
        """Film base transmission guessed from the whole frame."""
        raise NotImplementedError

    def to_density(self, working: np.ndarray, base: float) -> np.ndarray:
        """Density above film base: 0 at the base, higher where the negative is darker."""
        raise NotImplementedError


class BWNegative(FilmType):
    name = "bw_negative"
    label = "B&W negative"

    def to_working(self, rgb, settings):
        if settings.channel == "luminance":
            return rgb @ _LUMA_WEIGHTS
        return np.ascontiguousarray(rgb[..., _CHANNEL_INDEX[settings.channel]])

    def sample_base(self, working, rect):
        return float(np.median(region(working, rect)))

    def estimate_base(self, working):
        # Best: the clear rebate between sprocket holes (never bare light).
        from .framing import estimate_base
        base = estimate_base(working)
        if base is not None:
            return base
        # Fallback: the clear base is the brightest part of a negative, except sprocket
        # holes / gaps that show the bare light source (often clipped).
        # Ignore clipped pixels, then take a high percentile.
        vals = working[working < 0.98]
        if vals.size < 100:
            vals = working.ravel()
        return float(np.percentile(vals, 99.5))

    def to_density(self, working, base):
        # Inversion in linear space via optical density: D = log10(base / T).
        # Density is roughly proportional to log scene exposure, which is
        # also how darktable's negadoctor works.
        return np.log10(max(base, _EPS) / np.maximum(working, _EPS)).astype(np.float32)


FILM_TYPES: dict[str, FilmType] = {ft.name: ft for ft in (BWNegative(),)}


def get_film_type(name: str) -> FilmType:
    return FILM_TYPES[name]
