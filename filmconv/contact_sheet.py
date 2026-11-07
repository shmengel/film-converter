"""Contact sheet: one JPEG with a grid of frames, labelled like a darkroom proof."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .export import to_uint8

CELL = 480            # width of one frame's box in pixels; boxes are 3:2
GAP, MARGIN = 28, 48
BACKGROUND, TEXT, DIM = 22, 225, 150
FILE_SUFFIX = "_contact_sheet.jpg"


def thumbnail(img: np.ndarray, size: int = CELL) -> np.ndarray:
    """Downscale a positive (0..1 floats or uint8) to fit a size x size box."""
    h, w = img.shape[:2]
    k = min(size / w, size / h, 1.0)
    small = cv2.resize(img.astype(np.float32) if img.dtype != np.uint8 else img,
                       (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA)
    return small if small.dtype == np.uint8 else to_uint8(small)


def _font(size: int, bold: bool = False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # very old Pillow
        return ImageFont.load_default()


def make(items: list[tuple[str, np.ndarray]], title: str = "", cols: int | None = None) -> Image.Image:
    """items: (label, image) pairs, images as from thumbnail(). Returns a
    grayscale PIL image."""
    n = len(items)
    if n == 0:
        raise ValueError("No frames for the contact sheet.")
    cols = cols or min(n, 6)
    rows = -(-n // cols)
    box_w, box_h = CELL, CELL * 2 // 3
    label_h = 40
    title_h = 80 if title else 0
    width = 2 * MARGIN + cols * box_w + (cols - 1) * GAP
    height = 2 * MARGIN + title_h + rows * (box_h + label_h) + (rows - 1) * GAP
    sheet = Image.new("L", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    if title:
        draw.text((MARGIN, MARGIN), title, fill=TEXT, font=_font(40, bold=True))
        draw.text((width - MARGIN, MARGIN + 14), f"{n} frame{'s' if n != 1 else ''}",
                  fill=DIM, font=_font(26), anchor="ra")
    font = _font(24)
    for i, (label, img) in enumerate(items):
        r, c = divmod(i, cols)
        x0 = MARGIN + c * (box_w + GAP)
        y0 = MARGIN + title_h + r * (box_h + label_h + GAP)
        im = Image.fromarray(thumbnail(img, box_w))
        im.thumbnail((box_w, box_h), Image.LANCZOS)    # portrait frames fit the 3:2 box
        sheet.paste(im, (x0 + (box_w - im.width) // 2, y0 + (box_h - im.height) // 2))
        draw.text((x0 + box_w // 2, y0 + box_h + 8), label, fill=TEXT, font=font, anchor="ma")
    return sheet


def save(path: str | Path, items: list[tuple[str, np.ndarray]], title: str = "") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    make(items, title).save(path, quality=92)
    return path
