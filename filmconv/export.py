"""Writing positives to disk (pure-Python writers, safe with non-ASCII paths)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

# format key -> (file name suffix, label shown in the GUI)
FORMATS = {
    "jpeg": (".jpg", "JPEG"),
    "tiff": (".tif", "TIFF 16-bit"),
    "tiff8": ("_8bit.tif", "TIFF 8-bit"),
    "png": (".png", "PNG"),
}
JPEG_QUALITY = 95


def suffix(fmt: str) -> str:
    return FORMATS[fmt][0]


def to_uint8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def to_uint16(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)


def save_tiff16(path: str | Path, img: np.ndarray) -> None:
    tifffile.imwrite(Path(path), to_uint16(img), photometric="minisblack", compression="zlib")


def save_tiff8(path: str | Path, img: np.ndarray) -> None:
    tifffile.imwrite(Path(path), to_uint8(img), photometric="minisblack", compression="zlib")


def save_jpeg(path: str | Path, img: np.ndarray, quality: int = JPEG_QUALITY) -> None:
    Image.fromarray(to_uint8(img), mode="L").save(Path(path), quality=quality)


def save_png(path: str | Path, img: np.ndarray) -> None:
    Image.fromarray(to_uint8(img), mode="L").save(Path(path), optimize=False, compress_level=6)


def save(path: str | Path, img: np.ndarray, fmt: str) -> None:
    {"tiff": save_tiff16, "tiff8": save_tiff8, "jpeg": save_jpeg, "png": save_png}[fmt](path, img)
