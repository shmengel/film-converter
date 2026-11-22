import json

import numpy as np
import pytest

from filmconv import pipeline
import tifffile

from filmconv import contact_sheet, export
from filmconv.roll import ROLL_FILE, Roll, export_frames
from filmconv.settings import Settings


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
def test_rect_mapping_matches_orient(rotation, flip):
    s = Settings(rotation=rotation, flip=flip)
    img = np.zeros((40, 60), np.float32)
    rect = (0.1, 0.2, 0.3, 0.6)                      # camera coordinates
    img[8:24, 6:18] = 1.0                             # the same rect in pixels
    view = pipeline.orient(img, s)
    x0, y0, x1, y1 = pipeline.rect_to_view(rect, s)
    h, w = view.shape
    ys, xs = np.nonzero(view)
    assert abs(xs.min() / w - x0) < 0.02 and abs((xs.max() + 1) / w - x1) < 0.02
    assert abs(ys.min() / h - y0) < 0.02 and abs((ys.max() + 1) / h - y1) < 0.02
    back = pipeline.rect_from_view((x0, y0, x1, y1), s)
    assert np.allclose(back, rect)


def make_roll(tmp_path, names=("_A0001.NEF", "_A0002.NEF", "_A0003.nef")):
    tmp_path.mkdir(parents=True, exist_ok=True)
    for n in names:
        (tmp_path / n).write_bytes(b"not really raw")
    (tmp_path / "notes.txt").write_text("x")
    return Roll.open(tmp_path)


def test_roll_lists_raws_in_name_order(tmp_path):
    roll = make_roll(tmp_path)
    assert roll.names() == ["_A0001.NEF", "_A0002.NEF", "_A0003.nef"]
    assert roll.output_dir == tmp_path / "positives"


def test_roll_settings_persist(tmp_path):
    roll = make_roll(tmp_path)
    roll.frames["_A0002.NEF"].rotation = 180
    roll.frames["_A0002.NEF"].exposure = 0.5
    roll.formats = ["tiff", "jpeg"]
    assert roll.save()
    again = Roll.open(tmp_path)
    assert again.frames["_A0002.NEF"].rotation == 180
    assert again.frames["_A0002.NEF"].exposure == 0.5
    assert again.frames["_A0001.NEF"] == Settings()
    assert again.formats == ["tiff", "jpeg"]


def test_roll_survives_damaged_file(tmp_path):
    make_roll(tmp_path)
    (tmp_path / ROLL_FILE).write_text("{ not json", encoding="utf-8")
    assert Roll.open(tmp_path).frames["_A0001.NEF"] == Settings()
    (tmp_path / ROLL_FILE).write_text(json.dumps({"frames": {"_A0001.NEF": {"rotation": 90}}}))
    assert Roll.open(tmp_path).frames["_A0001.NEF"].rotation == 90


def test_apply_adjustments_copies_look_only(tmp_path):
    roll = make_roll(tmp_path)
    src = Settings(exposure=1.0, contrast=20, rotation=90, crop=(0.1, 0.1, 0.9, 0.9))
    roll.apply_adjustments(src, ["_A0001.NEF", "_A0003.nef"])
    a = roll.frames["_A0001.NEF"]
    assert a.exposure == 1.0 and a.contrast == 20
    assert a.rotation == 0 and a.crop is None
    assert roll.frames["_A0002.NEF"].exposure == 0.0


def test_export_frames_all_formats_and_contact_sheet(tmp_path, monkeypatch):
    """Every format is written next to each other, plus a contact sheet."""
    from filmconv import raw_io
    from PIL import Image
    from test_pipeline import synthetic_negative

    full = synthetic_negative(300, 450)
    monkeypatch.setattr(raw_io, "load_linear", lambda path, half_size=False: full)
    monkeypatch.setattr(raw_io, "load_preview", lambda path: full)
    roll = make_roll(tmp_path / "Roll 7 גלגל")
    roll.frames["_A0002.NEF"].rotation = 90
    out = tmp_path / "out"
    steps = []
    written, errors = export_frames(roll, roll.names()[:2], out, list(export.FORMATS), sheet=True,
                                    progress=lambda i, name: steps.append(i))
    assert errors == []
    names = sorted(p.name for p in written)
    assert names == sorted(["_A0001.jpg", "_A0001.tif", "_A0001_8bit.tif", "_A0001.png",
                            "_A0002.jpg", "_A0002.tif", "_A0002_8bit.tif", "_A0002.png",
                            "Roll 7 גלגל" + contact_sheet.FILE_SUFFIX])
    assert tifffile.imread(out / "_A0001.tif").dtype == np.uint16
    assert tifffile.imread(out / "_A0001_8bit.tif").dtype == np.uint8
    assert Image.open(out / "_A0002.png").size == (300, 450)        # rotated
    sheet = Image.open(out / ("Roll 7 גלגל" + contact_sheet.FILE_SUFFIX))
    assert sheet.mode == "L" and sheet.width > 2 * contact_sheet.CELL
    assert steps[-1] == 3                                            # 2 frames + sheet


def test_contact_sheet_only(tmp_path, monkeypatch):
    from filmconv import raw_io
    from test_pipeline import synthetic_negative

    full = synthetic_negative(300, 450)
    monkeypatch.setattr(raw_io, "load_linear", lambda path, half_size=False: full)
    monkeypatch.setattr(raw_io, "load_preview", lambda path: full)
    roll = make_roll(tmp_path / "r")
    written, errors = export_frames(roll, roll.names(), tmp_path / "out", [], sheet=True)
    assert errors == [] and [p.name for p in written] == ["r" + contact_sheet.FILE_SUFFIX]


def test_roll_remembers_export_choices(tmp_path):
    roll = make_roll(tmp_path)
    roll.formats, roll.contact_sheet = ["png", "tiff8"], True
    roll.save()
    again = Roll.open(tmp_path)
    assert again.formats == ["png", "tiff8"] and again.contact_sheet


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("vertical", [False, True])
def test_flip_view_mirrors_what_is_shown(rotation, flip, vertical):
    img = np.arange(12 * 20, dtype=float).reshape(12, 20)
    s = Settings(rotation=rotation, flip=flip)
    shown = pipeline.orient(img, s)
    pipeline.flip_view(s, vertical)
    expected = shown[::-1] if vertical else shown[:, ::-1]
    assert np.array_equal(pipeline.orient(img, s), expected)
    pipeline.flip_view(s, vertical)                      # flipping twice undoes it
    assert np.array_equal(pipeline.orient(img, s), shown)


def test_same_name_in_two_raw_formats_exports_both(tmp_path, monkeypatch):
    """DSC_1.NEF and DSC_1.DNG must not overwrite each other's output."""
    from filmconv import raw_io
    from test_pipeline import synthetic_negative

    full = synthetic_negative(300, 450)
    monkeypatch.setattr(raw_io, "load_linear", lambda path, half_size=False: full)
    monkeypatch.setattr(raw_io, "load_preview", lambda path: full)
    roll = make_roll(tmp_path / "r", names=("DSC_1.NEF", "DSC_1.DNG", "DSC_2.NEF"))
    written, errors = export_frames(roll, roll.names(), tmp_path / "out", ["jpeg"])
    assert errors == []
    assert len({p.name for p in written}) == 3
    assert "DSC_2.jpg" in {p.name for p in written}          # unique names stay as before
