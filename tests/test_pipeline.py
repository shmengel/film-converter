import numpy as np
import tifffile
from PIL import Image

from filmconv import export, pipeline
from filmconv.settings import Settings


def synthetic_negative(h=200, w=300, base=0.8):
    """Linear RGB 'scan': clear base border around a gradient frame.
    Scene brightness rises left to right, so the negative gets darker."""
    scene = np.tile(np.linspace(0.0, 1.0, w - 40, dtype=np.float32), (h - 40, 1))
    density = 0.1 + 1.5 * scene                 # denser where the scene is brighter
    img = np.full((h, w), base, np.float32)
    img[20:-20, 20:-20] = base * 10 ** -density
    return np.repeat(img[..., None], 3, axis=2)


def prepared(settings=None):
    settings = settings or Settings()
    working = pipeline.to_working(synthetic_negative(), settings)
    pipeline.update_auto(working, settings)
    return working, settings


def test_settings_json_roundtrip():
    s = Settings(exposure=1.5, crop=(0.1, 0.1, 0.9, 0.9), film_base_rect=(0, 0, 0.05, 1))
    s.auto.film_base = 0.7
    assert Settings.from_json(s.to_json()) == s


def test_settings_ignores_unknown_keys():
    assert Settings.from_dict({"exposure": 1.0, "future_option": 3}).exposure == 1.0


def test_base_estimated_from_border():
    _, s = prepared()
    assert abs(s.auto.film_base - 0.8) < 0.01


def test_base_sampled_from_rect():
    s = Settings(film_base_rect=(0.0, 0.0, 0.05, 1.0))
    _, s = prepared(s)
    assert abs(s.auto.film_base - 0.8) < 1e-4


def test_inversion_direction_and_range():
    working, s = prepared(Settings(crop=(0.07, 0.1, 0.93, 0.9)))
    out = pipeline.render(working, s)
    row = out[out.shape[0] // 2]
    assert row[-1] > row[0]                     # bright scene -> bright positive
    assert np.all(np.diff(row) >= -1e-6)        # monotonic
    assert row[0] < 0.02 and row[-1] > 0.98     # full range after auto-balance


def test_slider_directions():
    working, s = prepared()
    base = pipeline.render(working, s).mean()
    for name, value in [("exposure", 1.0), ("blacks", 50), ("whites", 50), ("shadows", 50), ("highlights", 50)]:
        t = s.copy()
        setattr(t, name, value)
        assert pipeline.render(working, t).mean() > base, name


def test_contrast_increases_spread():
    working, s = prepared()
    t = s.copy()
    t.contrast = 80
    assert pipeline.render(working, t).std() > pipeline.render(working, s).std()


def test_export_writers_handle_hebrew_paths(tmp_path):
    img = np.linspace(0, 1, 100 * 50, dtype=np.float32).reshape(50, 100)
    folder = tmp_path / "סריקות רול 1"
    folder.mkdir()
    export.save(folder / "a.tif", img, "tiff")
    export.save(folder / "a.jpg", img, "jpeg")
    tif = tifffile.imread(folder / "a.tif")
    assert tif.dtype == np.uint16 and tif.shape == (50, 100) and tif.max() == 65535
    assert Image.open(folder / "a.jpg").mode == "L"


def test_export_matches_preview(tmp_path, monkeypatch):
    """Auto values come from the downscaled preview and are reused at full size."""
    from filmconv import raw_io
    full = synthetic_negative(400, 600)
    monkeypatch.setattr(raw_io, "load_linear", lambda path, half_size=False: full)
    s = Settings(exposure=0.3)
    preview = pipeline.to_working(raw_io.downscale(full, 300), s)
    pipeline.update_auto(preview, s)
    preview_out = pipeline.render(preview, s)

    (written,) = pipeline.export_file(tmp_path / "_ZNG0001.NEF", s, tmp_path / "out", ["tiff"])
    assert written.name == "_ZNG0001.tif"
    full_out = tifffile.imread(written) / 65535.0
    assert full_out.shape == (400, 600)
    assert abs(full_out.mean() - preview_out.mean()) < 0.01
