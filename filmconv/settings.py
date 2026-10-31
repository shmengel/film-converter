"""One serializable settings object for all processing.

Presets, copy/paste between frames and per-roll settings all reuse this
structure, so anything that affects the output must live here.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

CHANNELS = ("luminance", "red", "green", "blue")

# Slider adjustments: name -> (min, max, default). All are "positive image"
# directions: moving right makes the result brighter / more of the effect.
ADJUSTMENTS = {
    "exposure": (-3.0, 3.0, 0.0),        # EV
    "contrast": (-100.0, 100.0, 0.0),
    "blacks": (-100.0, 100.0, 0.0),      # + lifts blacks, - crushes them
    "whites": (-100.0, 100.0, 0.0),      # + brightens whites, - dims them
    "highlights": (-100.0, 100.0, 0.0),
    "shadows": (-100.0, 100.0, 0.0),
}


@dataclass
class AutoValues:
    """Values computed by auto-analysis on the preview and reused at export,
    so the exported file matches what was shown on screen."""
    film_base: float | None = None   # linear transmission of the clear film base
    d_black: float | None = None     # density (above base) mapped to output black
    d_white: float | None = None     # density mapped to output white
    gamma: float = 1.0               # midtone curve chosen by auto-balance


@dataclass
class Settings:
    film_type: str = "bw_negative"
    channel: str = "green"
    # Rectangle (x0, y0, x1, y1), normalized 0..1 on the uncropped image,
    # where the user sampled the clear film base. None = estimate automatically.
    film_base_rect: tuple[float, float, float, float] | None = None
    # True: recompute black/white points and gamma for every frame.
    # False: keep the stored auto values (same look for the whole roll).
    auto_levels: bool = True
    # True: film base density is pure output black (faithful, often flatter).
    black_from_base: bool = False
    # Fraction of each edge ignored by auto-balance (border, rebate, sprockets).
    analysis_margin: float = 0.08
    # Crop rectangle normalized on the uncropped image, or None.
    crop: tuple[float, float, float, float] | None = None

    exposure: float = 0.0
    contrast: float = 0.0
    blacks: float = 0.0
    whites: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0

    auto: AutoValues = field(default_factory=AutoValues)

    # --- serialization -------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        auto = kwargs.pop("auto", None) or {}
        auto_known = {f.name for f in fields(AutoValues)}
        kwargs["auto"] = AutoValues(**{k: v for k, v in auto.items() if k in auto_known})
        for key in ("film_base_rect", "crop"):
            if kwargs.get(key) is not None:
                kwargs[key] = tuple(float(x) for x in kwargs[key])
        return cls(**kwargs)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Settings":
        return cls.from_dict(json.loads(text))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def copy(self) -> "Settings":
        return replace(self, auto=replace(self.auto))

    def reset_adjustments(self) -> None:
        for name, (_, _, default) in ADJUSTMENTS.items():
            setattr(self, name, default)
