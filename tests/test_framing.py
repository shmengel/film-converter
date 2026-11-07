"""Frame / base detection on a synthetic 35 mm strip with real geometry."""
import numpy as np

from filmconv import framing, pipeline
from filmconv.settings import Settings

PPM = 20.0            # pixels per mm
BASE, LIGHT = 0.25, 0.9


def synthetic_strip(frame_x0_mm=20.0):
    """Dark holder, strip with two hole rows, one 24x36 frame plus neighbours."""
    H, W = int(40 * PPM), int(60 * PPM)
    img = np.full((H, W), 0.005, np.float32)                  # holder
    top = int(2.5 * PPM)                                      # strip top edge
    img[top:top + int(35 * PPM), :] = BASE                    # clear film
    hole_w, hole_h = 1.98 * PPM, 2.8 * PPM                    # along x, across y
    inner_top = top + int(4.0 * PPM)                          # inner edge of top row
    inner_bot = inner_top + int(framing.HOLE_SPAN_MM * PPM)
    for k in range(int(W / (4.75 * PPM)) + 1):
        x = int(k * 4.75 * PPM + 1 * PPM)
        img[int(inner_top - hole_h):inner_top, x:int(x + hole_w)] = LIGHT
        img[inner_bot:int(inner_bot + hole_h), x:int(x + hole_w)] = LIGHT
    y0 = int((inner_top + inner_bot) / 2 - 12 * PPM)
    rng = np.random.default_rng(0)
    for fx in (frame_x0_mm - 38, frame_x0_mm, frame_x0_mm + 38):   # 2 mm gaps
        a, b = int(fx * PPM), int((fx + 36) * PPM)
        a, b = max(a, 0), min(b, W)
        if b > a:
            img[y0:y0 + int(24 * PPM), a:b] = BASE * 10 ** -rng.uniform(0.2, 1.2, (int(24 * PPM), b - a))
    return img, (frame_x0_mm * PPM / W, y0 / H, (frame_x0_mm + 36) * PPM / W, (y0 + 24 * PPM) / H)


def test_base_from_rebate_not_holes():
    img, _ = synthetic_strip()
    assert abs(framing.estimate_base(img) - BASE) < 0.005


def test_crop_matches_frame():
    img, truth = synthetic_strip()
    crop = framing.detect_crop(img, BASE)
    assert crop is not None
    assert np.allclose(crop, truth, atol=0.012), (crop, truth)


def test_crop_with_frame_running_under_holder():
    img, _ = synthetic_strip(frame_x0_mm=30.0)    # right part of the frame hidden
    img[:, int(56 * PPM):] = 0.005
    crop = framing.detect_crop(img, BASE)
    assert crop is not None and crop[2] <= 56 * PPM / img.shape[1] + 0.01


def test_pipeline_uses_auto_crop_and_manual_override():
    img, truth = synthetic_strip()
    rgb = np.repeat(img[..., None], 3, axis=2)
    s = Settings()
    pipeline.update_auto(pipeline.to_working(rgb, s), s)
    assert np.allclose(s.effective_crop(), truth, atol=0.012)
    s.crop = (0.1, 0.1, 0.9, 0.9)
    assert s.effective_crop() == (0.1, 0.1, 0.9, 0.9)


def test_sharpening_skipped_on_small_preview_and_applied_at_full_res():
    rng = np.random.default_rng(1)
    img = rng.uniform(0.2, 0.8, (64, 64)).astype(np.float32)
    s = Settings(sharpening=50)
    assert np.array_equal(pipeline.sharpen(img, s, scale=4.0), img)
    assert pipeline.sharpen(img, s, scale=1.0).std() > img.std()


def test_rotation_and_flip():
    img = np.arange(6, dtype=np.float32).reshape(2, 3)
    assert np.array_equal(pipeline.orient(img, Settings(rotation=180)), img[::-1, ::-1])
    assert np.array_equal(pipeline.orient(img, Settings(rotation=90)), np.rot90(img, -1))
    assert np.array_equal(pipeline.orient(img, Settings(flip=True)), img[:, ::-1])


def test_rotation_guess_puts_bright_side_up():
    from filmconv import orientation
    sky_top = np.linspace(1.0, 0.2, 120)[:, None] * np.ones((1, 180))
    assert orientation.guess_rotation(sky_top) == 0
    assert orientation.guess_rotation(sky_top[::-1, ::-1]) == 180


def test_auto_rotation_never_overrides_user():
    from filmconv import pipeline
    s = Settings(rotation=90)
    s.auto.rotation = None
    s.auto.film_base, s.auto.d_black, s.auto.d_white = 0.8, 0.0, 1.0
    s.auto.rotation = 180
    pipeline.apply_auto_rotation(s)
    assert s.rotation == 90
    t = Settings()
    t.auto.rotation = 180
    pipeline.apply_auto_rotation(t)
    assert t.rotation == 180
