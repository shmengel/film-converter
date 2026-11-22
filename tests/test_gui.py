"""Offscreen checks of the main window (no RAW files: previews are synthetic)."""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from filmconv import raw_io  # noqa: E402
from filmconv_gui import main_window  # noqa: E402
from filmconv_gui.main_window import MainWindow  # noqa: E402
from test_pipeline import synthetic_negative  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    # Modal dialogs would block an offscreen run.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    for name in ("critical", "information", "warning"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Ok)
    preview = synthetic_negative(200, 300)
    monkeypatch.setattr(raw_io, "load_preview", lambda p, *a, **k: preview)
    monkeypatch.setattr(raw_io, "full_size", lambda p: (800, 1200))
    for i in range(1, 5):
        (tmp_path / f"_A000{i}.NEF").write_bytes(b"")
    w = MainWindow()
    w.open_path(tmp_path)
    settle(app, w)
    yield w
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    w.close()


def settle(app, w):
    for _ in range(50):
        app.processEvents()
        w.bg_pool.waitForDone(20)
        w.pool.waitForDone(20)
    app.processEvents()


def test_quitting_during_export_waits_for_the_current_frame(win, monkeypatch):
    finished = threading.Event()

    def slow_export(*args, progress=None, cancelled=None):
        time.sleep(0.5)                        # one frame being written
        finished.set()
        return [], []

    monkeypatch.setattr(main_window, "export_frames", slow_export)
    win.export(win.roll.names(), ["jpeg"])
    assert win.export_job is not None
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win.close()
    assert finished.is_set()


def test_preview_cache_is_bounded(win, monkeypatch):
    monkeypatch.setattr(main_window, "CACHE_FRAMES", 2)
    for n in win.roll.names():
        win.strip.select_name(n)
        settle(QApplication.instance(), win)
    assert len(win.cache) <= 2
    assert (win.name, win.settings.channel) in win.cache       # the shown frame stays


def test_export_asks_before_replacing_files(win, monkeypatch, tmp_path):
    out = win.roll.output_dir
    out.mkdir(parents=True)
    (out / "_A0001.jpg").write_bytes(b"old")
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a) or QMessageBox.No)
    win.export(["_A0001.NEF"], ["jpeg"])
    assert asked and win.export_job is None
    assert (out / "_A0001.jpg").read_bytes() == b"old"


def test_undo_reverts_slider_change(win):
    win.sliders["contrast"].setValue(40)
    win.sliders["contrast"].sliderReleased.emit()
    assert win.settings.contrast == 40
    win.undo()
    assert win.settings.contrast == 0
    assert win.sliders["contrast"].value() == 0


def test_undo_reverts_apply_to_all(win, monkeypatch):
    win.settings.exposure = 1.0
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win.on_apply_all()
    assert all(s.exposure == 1.0 for s in win.roll.frames.values())
    win.undo()
    others = [s for n, s in win.roll.frames.items() if n != win.name]
    assert all(s.exposure == 0.0 for s in others)


def test_undo_reverts_rotation(win):
    before = win.settings.rotation
    win.rotate(90)
    win.undo()
    assert win.settings.rotation == before
