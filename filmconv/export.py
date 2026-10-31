"""Writing positives to disk (pure-Python writers, safe with non-ASCII paths)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

FORMATS = {"tiff": ".tif", "jpeg": ".jpg"}


def save_tiff16(path: str | Path, img: np.ndarray) -> None:
    data = (np.clip(img, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    tifffile.imwrite(Path(path), data, photometric="minisblack", compression="zlib")


def save_jpeg(path: str | Path, img: np.ndarray, quality: int = 95) -> None:
    data = (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(data, mode="L").save(Path(path), quality=quality)


def save(path: str | Path, img: np.ndarray, fmt: str) -> None:
    {"tiff": save_tiff16, "jpeg": save_jpeg}[fmt](path, img)
