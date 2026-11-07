"""Draw the app icon (a film strip with a positive frame) -> filmconv_gui/icon.ico"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024   # drawn large, then downsampled for clean edges


def draw() -> Image.Image:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=180, fill=(34, 38, 46, 255))
    # film strip
    top, bot = 230, S - 230
    d.rectangle((40, top, S - 40, bot), fill=(18, 18, 20, 255))
    # sprocket holes
    for x in range(110, S - 100, 130):
        for y in (top + 28, bot - 28 - 50):
            d.rounded_rectangle((x, y, x + 64, y + 50), radius=12, fill=(235, 225, 200, 255))
    # the frame: a little B&W landscape (sky gradient, sun, hills)
    fx0, fy0, fx1, fy1 = 170, top + 110, S - 170, bot - 110
    for y in range(fy0, fy1):
        v = int(250 - 90 * (y - fy0) / (fy1 - fy0))
        d.line((fx0, y, fx1, y), fill=(v, v, v, 255))
    d.ellipse((S - 380, fy0 + 40, S - 280, fy0 + 140), fill=(255, 255, 255, 255), outline=(200, 200, 200, 255), width=6)
    d.polygon([(fx0, fy1), (fx0, fy1 - 120), (380, fy1 - 230), (560, fy1 - 90), (700, fy1 - 170),
               (fx1, fy1 - 60), (fx1, fy1)], fill=(60, 60, 60, 255))
    return im


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "filmconv_gui" / "icon.ico"
    draw().resize((256, 256), Image.LANCZOS).save(
        out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out)
