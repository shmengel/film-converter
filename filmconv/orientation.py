"""Guess whether a frame is upside down.

Frames come off the rig the right way up or rotated 180 degrees, depending on
which way the strip went into the holder. The cue: the top of a photo is
usually brighter than the bottom (sky, ceilings, windows). On the first real
roll (35 frames) this was right on 33, in about 50 ms per frame. Portrait
(90 degree) frames are not detected; those stay manual.
"""
from __future__ import annotations

import numpy as np

MIN_SIDE = 16


def top_minus_bottom(positive: np.ndarray) -> float:
    """Mean brightness of the top third minus the bottom third (0..1 scale)."""
    h = positive.shape[0]
    if h < MIN_SIDE:
        return 0.0
    return float(positive[: h // 3].mean() - positive[h - h // 3:].mean())


def guess_rotation(positive: np.ndarray) -> int:
    """0 or 180: the rotation that puts the brighter side on top.
    `positive` is the cropped positive as it comes from the camera
    (before any rotation)."""
    return 180 if top_minus_bottom(positive) < 0 else 0
