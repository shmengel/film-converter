"""Main window: open one RAW, pick film base, adjust, export."""
from __future__ import annotations

import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSlider, QVBoxLayout, QWidget,
)

from filmconv import pipeline, raw_io
from filmconv.settings import ADJUSTMENTS, CHANNELS, Settings

from .widgets import HistogramWidget, ImageView

RAW_FILTER = "RAW files (" + " ".join(f"*{e}" for e in sorted(raw_io.RAW_EXTENSIONS)) + ")"
SLIDER_STEPS = 100   # slider ints per settings unit for exposure (EV)


# --- background tasks ------------------------------------------------------
class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    """Runs fn(*args) on the thread pool; results come back on the GUI thread."""

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args)
        except Exception:
            self.signals.failed.emit(traceback.format_exc())
        else:
            self.signals.done.emit(result)


def negative_display(working: np.ndarray) -> np.ndarray:
    """The negative as the camera saw it, for the 'before' view."""
    v = np.clip(working / max(float(working.max()), 1e-6), 0, 1) ** (1 / 2.2)
    return (v * 255 + 0.5).astype(np.uint8)


def to8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


# --- window ------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Film Converter")
        self.resize(1400, 900)
        self.qsettings = QSettings("film-converter", "film-converter")
        self.pool = QThreadPool.globalInstance()
        self._tasks: set[Task] = set()

        self.settings = Settings()
        self.path: Path | None = None
        self.rgb: np.ndarray | None = None       # preview linear RGB
        self.working: np.ndarray | None = None   # preview transmission (mono)
        self.positive8: np.ndarray | None = None

        self._render_timer = QTimer(self, singleShot=True, interval=15)
        self._render_timer.timeout.connect(self.render)

        self._build_ui()
        self._build_menu()
        self._sync_controls()

    # --- UI construction ---------------------------------------------------
    def _build_ui(self):
        self.view = ImageView()
        self.view.rectPicked.connect(self.on_base_picked)

        panel = QWidget()
        lay = QVBoxLayout(panel)

        # View
        self.btn_before = QPushButton("Show negative (B)", checkable=True)
        self.btn_before.setShortcut("B")
        self.btn_before.toggled.connect(self.update_view)
        lay.addWidget(self.btn_before)

        # Film base
        g = QGroupBox("Film base")
        gl = QVBoxLayout(g)
        self.lbl_base = QLabel("–")
        gl.addWidget(self.lbl_base)
        row = QHBoxLayout()
        self.btn_pick = QPushButton("Pick on image", checkable=True)
        self.btn_pick.setToolTip("Drag a rectangle on clear film (the border between frames)")
        self.btn_pick.toggled.connect(self.on_pick_toggled)
        btn_auto_base = QPushButton("Auto")
        btn_auto_base.setToolTip("Estimate the film base automatically")
        btn_auto_base.clicked.connect(self.on_auto_base)
        row.addWidget(self.btn_pick)
        row.addWidget(btn_auto_base)
        gl.addLayout(row)
        self.chk_base_black = QCheckBox("Film base is pure black")
        self.chk_base_black.setToolTip("Faithful to the negative; usually flatter than auto black point")
        self.chk_base_black.toggled.connect(self.on_option_changed)
        gl.addWidget(self.chk_base_black)
        lay.addWidget(g)

        # Conversion
        g = QGroupBox("Conversion")
        form = QFormLayout(g)
        self.cmb_channel = QComboBox()
        self.cmb_channel.addItems([c.capitalize() for c in CHANNELS])
        self.cmb_channel.currentIndexChanged.connect(self.on_channel_changed)
        form.addRow("Channel", self.cmb_channel)
        lay.addWidget(g)

        # Adjustments
        g = QGroupBox("Adjustments")
        form = QFormLayout(g)
        self.sliders: dict[str, QSlider] = {}
        self.slider_labels: dict[str, QLabel] = {}
        for name, (lo, hi, _default) in ADJUSTMENTS.items():
            s = QSlider(Qt.Horizontal)
            scale = SLIDER_STEPS if name == "exposure" else 1
            s.setRange(int(lo * scale), int(hi * scale))
            s.valueChanged.connect(lambda v, n=name, k=scale: self.on_slider(n, v / k))
            val = QLabel()
            val.setMinimumWidth(42)
            row = QHBoxLayout()
            row.addWidget(s)
            row.addWidget(val)
            form.addRow(name.capitalize(), row)
            self.sliders[name], self.slider_labels[name] = s, val
        row = QHBoxLayout()
        btn = QPushButton("Auto balance")
        btn.setToolTip("Recompute black/white points and midtones for this frame")
        btn.clicked.connect(self.on_auto_balance)
        row.addWidget(btn)
        btn = QPushButton("Reset sliders")
        btn.clicked.connect(self.on_reset_sliders)
        row.addWidget(btn)
        form.addRow(row)
        lay.addWidget(g)

        # Histogram
        g = QGroupBox("Histogram (positive)")
        gl = QVBoxLayout(g)
        self.hist = HistogramWidget()
        gl.addWidget(self.hist)
        lay.addWidget(g)

        # Export
        g = QGroupBox("Export")
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        self.chk_tiff = QCheckBox("TIFF 16-bit", checked=True)
        self.chk_jpeg = QCheckBox("JPEG")
        row.addWidget(self.chk_tiff)
        row.addWidget(self.chk_jpeg)
        gl.addLayout(row)
        row = QHBoxLayout()
        self.txt_out = QLineEdit()
        self.txt_out.setPlaceholderText("Output folder")
        btn = QPushButton("…")
        btn.setFixedWidth(30)
        btn.clicked.connect(self.on_browse_output)
        row.addWidget(self.txt_out)
        row.addWidget(btn)
        gl.addLayout(row)
        self.btn_export = QPushButton("Export full resolution")
        self.btn_export.clicked.connect(self.on_export)
        gl.addWidget(self.btn_export)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        gl.addWidget(self.progress)
        lay.addWidget(g)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(370)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.view, 1)
        h.addWidget(scroll)
        self.setCentralWidget(central)

    def _build_menu(self):
        m = self.menuBar().addMenu("&File")
        for text, key, slot in [
            ("&Open RAW…", QKeySequence.Open, self.on_open),
            ("&Export", "Ctrl+E", self.on_export),
            (None, None, None),
            ("&Save settings…", "Ctrl+S", self.on_save_settings),
            ("&Load settings…", "Ctrl+L", self.on_load_settings),
            (None, None, None),
            ("&Quit", QKeySequence.Quit, self.close),
        ]:
            if text is None:
                m.addSeparator()
                continue
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(slot)
            m.addAction(a)

    def _sync_controls(self):
        """Push self.settings into the widgets without triggering re-renders."""
        s = self.settings
        for name, slider in self.sliders.items():
            slider.blockSignals(True)
            scale = SLIDER_STEPS if name == "exposure" else 1
            slider.setValue(int(round(getattr(s, name) * scale)))
            slider.blockSignals(False)
            self._update_slider_label(name)
        for w, value in [(self.chk_base_black, s.black_from_base),
                         (self.cmb_channel, CHANNELS.index(s.channel))]:
            w.blockSignals(True)
            w.setChecked(value) if isinstance(w, QCheckBox) else w.setCurrentIndex(value)
            w.blockSignals(False)
        self._update_base_label()

    def _update_slider_label(self, name):
        v = getattr(self.settings, name)
        self.slider_labels[name].setText(f"{v:+.2f}" if name == "exposure" else f"{v:+.0f}")

    def _update_base_label(self):
        a, s = self.settings.auto, self.settings
        if a.film_base is None:
            self.lbl_base.setText("Not sampled yet")
        else:
            src = "picked" if s.film_base_rect else "auto-estimated"
            self.lbl_base.setText(f"Transmission {a.film_base:.4f} ({src})")

    # --- tasks ---------------------------------------------------------------
    def run_task(self, fn, *args, done, failed=None, busy_text=""):
        task = Task(fn, *args)
        self._tasks.add(task)

        def finish(result, ok):
            self._tasks.discard(task)
            self.progress.setVisible(False)
            self.statusBar().clearMessage()
            if ok:
                done(result)
            else:
                if failed:
                    failed()
                QMessageBox.critical(self, "Error", result)

        task.signals.done.connect(lambda r: finish(r, True))
        task.signals.failed.connect(lambda msg: finish(msg, False))
        self.progress.setRange(0, 0)   # busy indicator
        self.progress.setVisible(True)
        self.statusBar().showMessage(busy_text)
        self.pool.start(task)

    # --- actions -------------------------------------------------------------
    def on_open(self):
        start = self.qsettings.value("last_dir", str(Path.home()))
        name, _ = QFileDialog.getOpenFileName(self, "Open RAW", start, RAW_FILTER)
        if name:
            self.open_file(Path(name))

    def open_file(self, path: Path):
        self.qsettings.setValue("last_dir", str(path.parent))
        self.view.placeholder = f"Loading {path.name}…"
        self.view.set_image(None)
        self.run_task(raw_io.load_preview, path, busy_text=f"Loading {path.name}…",
                      done=lambda rgb: self.on_loaded(path, rgb))

    def on_loaded(self, path: Path, rgb: np.ndarray):
        self.path, self.rgb = path, rgb
        self.setWindowTitle(f"Film Converter – {path.name}")
        if not self.txt_out.text():
            self.txt_out.setText(str(path.parent / "positives"))
        self.reprocess()

    def reprocess(self, force_levels=False):
        """Recompute working image + auto values (after load / channel change)."""
        if self.rgb is None:
            return
        self.working = pipeline.to_working(self.rgb, self.settings)
        pipeline.update_auto(self.working, self.settings, force=force_levels)
        self._update_base_label()
        self.render()

    def render(self):
        if self.working is None:
            return
        self.positive8 = to8(pipeline.render(self.working, self.settings))
        self.hist.set_image(self.positive8)
        self.update_view()

    def update_view(self):
        if self.working is None:
            return
        show_negative = self.btn_before.isChecked() or self.btn_pick.isChecked()
        if show_negative:
            self.view.set_image(negative_display(self.working))
            self.view.overlay_rect = self.settings.film_base_rect
        else:
            self.view.set_image(self.positive8)
            self.view.overlay_rect = None

    def on_slider(self, name, value):
        setattr(self.settings, name, value)
        self._update_slider_label(name)
        self._render_timer.start()

    def on_channel_changed(self, index):
        self.settings.channel = CHANNELS[index]
        if self.settings.film_base_rect is None:
            self.settings.auto.film_base = None   # re-estimate for the new channel
        self.reprocess(force_levels=True)

    def on_option_changed(self):
        self.settings.black_from_base = self.chk_base_black.isChecked()
        self.reprocess(force_levels=True)

    def on_pick_toggled(self, on):
        self.view.set_pick_mode(on)
        if on:
            self.statusBar().showMessage("Drag a rectangle over clear film base (no image, no sprocket holes)")
        self.update_view()

    def on_base_picked(self, rect):
        self.settings.film_base_rect = rect
        self.btn_pick.setChecked(False)
        self.reprocess(force_levels=True)

    def on_auto_base(self):
        self.settings.film_base_rect = None
        self.settings.auto.film_base = None
        self.reprocess(force_levels=True)

    def on_auto_balance(self):
        self.reprocess(force_levels=True)

    def on_reset_sliders(self):
        self.settings.reset_adjustments()
        self._sync_controls()
        self.render()

    def on_browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.txt_out.text())
        if d:
            self.txt_out.setText(d)

    def on_export(self):
        if self.path is None or self.working is None:
            return
        formats = [f for f, chk in (("tiff", self.chk_tiff), ("jpeg", self.chk_jpeg)) if chk.isChecked()]
        if not formats or not self.txt_out.text().strip():
            QMessageBox.warning(self, "Export", "Choose at least one format and an output folder.")
            return
        out_dir = Path(self.txt_out.text().strip())
        self.btn_export.setEnabled(False)

        def done(written):
            self.btn_export.setEnabled(True)
            self.statusBar().showMessage("Saved: " + ", ".join(str(p) for p in written), 8000)

        self.run_task(pipeline.export_file, self.path, self.settings.copy(), out_dir, formats,
                      done=done, failed=lambda: self.btn_export.setEnabled(True),
                      busy_text=f"Exporting {self.path.name} at full resolution…")

    def on_save_settings(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save settings", "", "Settings (*.json)")
        if name:
            self.settings.save(name)

    def on_load_settings(self):
        name, _ = QFileDialog.getOpenFileName(self, "Load settings", "", "Settings (*.json)")
        if not name:
            return
        try:
            self.settings = Settings.load(name)
        except Exception as e:
            QMessageBox.critical(self, "Load settings", f"Could not read settings:\n{e}")
            return
        self._sync_controls()
        self.reprocess()
