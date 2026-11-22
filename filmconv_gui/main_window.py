"""Main window: open a roll (folder), browse frames, adjust, export."""
from __future__ import annotations

import traceback
from dataclasses import fields
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QObject,QRunnable, QSettings, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QApplication, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSlider, QToolButton, QVBoxLayout, QWidget,
)

from filmconv import contact_sheet, pipeline, raw_io
from filmconv.roll import Roll, export_frames
from filmconv.settings import ADJUSTMENTS, CHANNELS, AutoValues, Settings

from .export_dialog import ALL, ExportDialog
from .widgets import MAC, FilmStrip, HistogramWidget, ImageView, keys_text

# File-dialog filters are case-sensitive on macOS, so list .nef and .NEF there.
RAW_FILTER = "RAW files (" + " ".join(
    f"*{x}" for e in sorted(raw_io.RAW_EXTENSIONS) for x in ((e, e.upper()) if MAC else (e,))) + ")"
SLIDER_STEPS = 100   # slider ints per settings unit for exposure (EV)
CROP_COLOR, BASE_COLOR = QColor(80, 220, 120), QColor(255, 80, 60)
# Settings fields that are "user edits" (shown with a dot in the strip).
EDIT_FIELDS = [f.name for f in fields(Settings) if f.name not in ("auto",)]
# Changing these invalidates the automatic analysis of a frame.
ANALYSIS_FIELDS = ("channel", "film_base_rect", "crop", "auto_crop", "black_from_base")


# --- background jobs -----------------------------------------------------------
class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)


class Job(QRunnable):
    """Runs fn(*args) on a thread pool; results come back on the GUI thread.
    With with_progress=True, fn gets `progress(i, text)` and `cancelled()` keywords."""

    def __init__(self, fn, *args, with_progress=False):
        super().__init__()
        self.fn, self.args, self.with_progress = fn, args, with_progress
        self.signals = _Signals()
        self.cancel_requested = False

    def run(self):
        try:
            if self.with_progress:
                result = self.fn(*self.args, progress=self.signals.progress.emit,
                                 cancelled=lambda: self.cancel_requested)
            else:
                result = self.fn(*self.args)
        except Exception:
            self._emit(self.signals.failed, traceback.format_exc())
        else:
            self._emit(self.signals.done, result)

    @staticmethod
    def _emit(signal, value):
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # the window was closed while this job was running


def prepare_frame(path: Path, settings: Settings):
    """Background: load the preview and analyze it with a copy of the frame's
    settings. Returns (working, scale, auto)."""
    rgb = raw_io.load_preview(path)
    working = pipeline.to_working(rgb, settings)
    pipeline.update_auto(working, settings)
    scale = raw_io.full_size(path)[1] / rgb.shape[1]
    return working, scale, settings.auto


def negative_display(working: np.ndarray) -> np.ndarray:
    """The negative as the camera saw it, for the 'before' view."""
    v = np.clip(working / max(float(np.percentile(working, 99.9)), 1e-6), 0, 1) ** (1 / 2.2)
    return (v * 255 + 0.5).astype(np.uint8)


def to8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def analysis_key(s: Settings) -> tuple:
    return tuple(getattr(s, k) for k in ANALYSIS_FIELDS)


def is_edited(s: Settings) -> bool:
    d = Settings()
    d.rotation = s.auto.rotation or 0      # the automatic upright guess is not an edit
    return any(getattr(s, k) != getattr(d, k) for k in EDIT_FIELDS)


# --- window ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Film Converter")
        self.resize(1500, 950)
        self.setAcceptDrops(True)
        self.qsettings = QSettings("film-converter", "film-converter")
        self.pool = QThreadPool.globalInstance()
        self.bg_pool = QThreadPool(self)          # preview preparation
        self.bg_pool.setMaxThreadCount(2)
        self._jobs: set[Job] = set()
        self._generation = 0                       # bumps when a new roll opens

        self.roll: Roll | None = None
        self.name: str | None = None               # current frame
        self.cache: dict[tuple[str, str], tuple[np.ndarray, float]] = {}
        self.working: np.ndarray | None = None
        self.scale = 1.0
        self.positive8: np.ndarray | None = None
        self.clipboard: Settings | None = None
        self.export_job: Job | None = None
        self.mode = "positive"                     # positive | negative | crop | base

        self._render_timer = QTimer(self, singleShot=True, interval=15)
        self._render_timer.timeout.connect(self.render)
        self._save_timer = QTimer(self, singleShot=True, interval=700)
        self._save_timer.timeout.connect(self.save_roll)
        self._save_warned = False

        self._build_ui()
        self._build_menu()
        self._set_enabled(False)
        QApplication.instance().installEventFilter(self)

    @property
    def settings(self) -> Settings:
        return self.roll.frames[self.name]

    # --- UI construction ---------------------------------------------------
    def _build_ui(self):
        self.view = ImageView()
        self.view.rectPicked.connect(self.on_rect_picked)
        self.view.cropEdited.connect(self.on_crop_edited)
        self.strip = FilmStrip()
        self.strip.currentItemChanged.connect(lambda *_: self.on_frame_selected())

        panel = QWidget()
        lay = QVBoxLayout(panel)

        # Frame
        g = QGroupBox("Frame")
        gl = QVBoxLayout(g)
        self.lbl_frame = QLabel("No roll open")
        self.lbl_frame.setStyleSheet("font-weight: bold;")
        gl.addWidget(self.lbl_frame)
        row = QHBoxLayout()
        self.btn_rot_l = QPushButton("⟲ Rotate left")
        self.btn_rot_l.setToolTip("Rotate the selected frames 90° to the left  ( [ )")
        self.btn_rot_l.clicked.connect(lambda: self.rotate(-90))
        self.btn_rot_r = QPushButton("Rotate right ⟳")
        self.btn_rot_r.setToolTip("Rotate the selected frames 90° to the right  ( ] )")
        self.btn_rot_r.clicked.connect(lambda: self.rotate(90))
        row.addWidget(self.btn_rot_l)
        row.addWidget(self.btn_rot_r)
        gl.addLayout(row)
        row = QHBoxLayout()
        self.btn_flip_h = QPushButton("⇆ Flip horizontal")
        self.btn_flip_h.setToolTip("Mirror the selected frames left to right  (H)\n"
                                   "Use it when the film was scanned from the emulsion side")
        self.btn_flip_h.clicked.connect(lambda: self.flip(vertical=False))
        self.btn_flip_v = QPushButton("⇅ Flip vertical")
        self.btn_flip_v.setToolTip("Mirror the selected frames top to bottom  (V)")
        self.btn_flip_v.clicked.connect(lambda: self.flip(vertical=True))
        row.addWidget(self.btn_flip_h)
        row.addWidget(self.btn_flip_v)
        gl.addLayout(row)
        row = QHBoxLayout()
        self.btn_crop = QPushButton("Adjust crop", checkable=True)
        self.btn_crop.setToolTip("Shows the whole scan: drag the edges or corners of the crop, "
                                 "drag inside to move it  (C; Enter = done)")
        self.btn_crop.toggled.connect(lambda on: self.set_mode("crop" if on else "positive"))
        self.btn_auto_crop = QPushButton("Auto crop")
        self.btn_auto_crop.setToolTip("Let the app find the frame edges again")
        self.btn_auto_crop.clicked.connect(self.on_auto_crop)
        row.addWidget(self.btn_crop)
        row.addWidget(self.btn_auto_crop)
        gl.addLayout(row)
        self.btn_before = QPushButton("Show negative  (hold B)", checkable=True)
        self.btn_before.toggled.connect(lambda on: self.set_mode("negative" if on else "positive"))
        gl.addWidget(self.btn_before)
        lay.addWidget(g)

        # Adjustments
        g = QGroupBox("Adjustments")
        form = QFormLayout(g)
        self.sliders: dict[str, QSlider] = {}
        self.slider_labels: dict[str, QLabel] = {}
        for name, (lo, hi, _default) in ADJUSTMENTS.items():
            s = QSlider(Qt.Horizontal)
            k = SLIDER_STEPS if name == "exposure" else 1
            s.setRange(int(lo * k), int(hi * k))
            s.valueChanged.connect(lambda v, n=name, k=k: self.on_slider(n, v / k))
            val = QLabel()
            val.setMinimumWidth(42)
            row = QHBoxLayout()
            row.addWidget(s)
            row.addWidget(val)
            form.addRow(name.capitalize(), row)
            self.sliders[name], self.slider_labels[name] = s, val
        row = QHBoxLayout()
        btn = QPushButton("Auto balance")
        btn.setToolTip("Recompute black point, white point and midtones for this frame")
        btn.clicked.connect(lambda: self.reprocess(force_levels=True))
        row.addWidget(btn)
        btn = QPushButton("Reset sliders")
        btn.clicked.connect(self.on_reset_sliders)
        row.addWidget(btn)
        form.addRow(row)
        row = QHBoxLayout()
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setToolTip(keys_text("Copy this frame's slider settings (Ctrl+Shift+C)"))
        self.btn_copy.clicked.connect(self.on_copy)
        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setToolTip(keys_text("Paste slider settings onto the selected frames (Ctrl+Shift+V)"))
        self.btn_paste.clicked.connect(self.on_paste)
        btn_all = QPushButton("Apply to all")
        btn_all.setToolTip("Use this frame's slider settings on every frame of the roll")
        btn_all.clicked.connect(self.on_apply_all)
        row.addWidget(self.btn_copy)
        row.addWidget(self.btn_paste)
        row.addWidget(btn_all)
        form.addRow(row)
        lay.addWidget(g)

        # Histogram
        g = QGroupBox("Histogram")
        gl = QVBoxLayout(g)
        self.hist = HistogramWidget()
        gl.addWidget(self.hist)
        lay.addWidget(g)

        # Export
        g = QGroupBox("Export")
        gl = QVBoxLayout(g)
        self.btn_export = QPushButton("Export…")
        self.btn_export.setToolTip(keys_text("Choose frames, formats, contact sheet and folder  (Ctrl+E)"))
        self.btn_export.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_export.clicked.connect(lambda: self.open_export_dialog())
        gl.addWidget(self.btn_export)
        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.on_cancel_export)
        row.addWidget(self.progress)
        row.addWidget(self.btn_cancel)
        gl.addLayout(row)
        lay.addWidget(g)

        # Advanced (collapsed)
        self.btn_adv = QToolButton(text="Advanced ▸", checkable=True)
        self.btn_adv.setStyleSheet("QToolButton { border: none; color: #999; }")
        self.btn_adv.toggled.connect(self.on_toggle_advanced)
        lay.addWidget(self.btn_adv)
        self.adv = QGroupBox()
        form = QFormLayout(self.adv)
        self.lbl_base = QLabel("–")
        form.addRow("Film base", self.lbl_base)
        row = QHBoxLayout()
        self.btn_pick = QPushButton("Pick on image", checkable=True)
        self.btn_pick.setToolTip("Drag a rectangle on clear film (between sprocket holes)")
        self.btn_pick.toggled.connect(lambda on: self.set_mode("base" if on else "positive"))
        btn = QPushButton("Auto")
        btn.clicked.connect(self.on_auto_base)
        row.addWidget(self.btn_pick)
        row.addWidget(btn)
        form.addRow(row)
        self.chk_base_black = QCheckBox("Film base is pure black")
        self.chk_base_black.setToolTip("Faithful to the negative; usually flatter than auto")
        self.chk_base_black.toggled.connect(self.on_option_changed)
        form.addRow(self.chk_base_black)
        self.cmb_channel = QComboBox()
        self.cmb_channel.addItems([c.capitalize() for c in CHANNELS])
        self.cmb_channel.currentIndexChanged.connect(self.on_channel_changed)
        form.addRow("Channel", self.cmb_channel)
        self.adv.setVisible(False)
        lay.addWidget(self.adv)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(450)

        top = QWidget()
        h = QHBoxLayout(top)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.view, 1)
        h.addWidget(scroll)
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(top, 1)
        v.addWidget(self.strip)
        self.setCentralWidget(central)

    def _build_menu(self):
        m = self.menuBar().addMenu("&File")
        self._add_actions(m, [
            ("&Open roll…", QKeySequence.Open, self.on_open_roll),
            None,
            ("&Export…", "Ctrl+E", lambda: self.open_export_dialog()),
            ("Export &all frames…", None, lambda: self.open_export_dialog(ALL)),
            ("Open output folder", None, self.open_output_folder),
            None,
            ("&Quit", QKeySequence.Quit, self.close),
        ])
        m = self.menuBar().addMenu("&Edit")
        self._add_actions(m, [
            ("&Copy settings", "Ctrl+Shift+C", self.on_copy),
            ("&Paste settings to selected", "Ctrl+Shift+V", self.on_paste),
            ("Select &all frames", "Ctrl+A", lambda: self.strip.selectAll()),
            None,
            ("Previous frame", "PgUp", lambda: self.step_frame(-1)),
            ("Next frame", "PgDown", lambda: self.step_frame(1)),
        ])
        m = self.menuBar().addMenu("&Help")
        self._add_actions(m, [
            ("&Keyboard shortcuts", "F1", self.show_help),
            ("&About", None, self.show_about),
        ])

    def show_help(self):
        QMessageBox.information(self, "Keyboard shortcuts", keys_text(
            "Ctrl+O\tOpen a roll (pick any scan in the folder)\n"
            "PgUp / PgDn\tPrevious / next frame\n"
            "[  ]\tRotate left / right\n"
            "H  V\tFlip horizontal / vertical\n"
            "C\tAdjust crop (Enter = done)\n"
            "hold B\tShow the negative\n"
            "Ctrl+Shift+C / V\tCopy / paste slider settings\n"
            "Ctrl+E\tExport…\n\n"
            "Ctrl+click or Shift+click thumbnails to work on several frames at once."))

    def show_about(self):
        import filmconv
        QMessageBox.about(self, f"About {filmconv.APP_NAME}", (
            f"<b>{filmconv.APP_NAME}</b> {filmconv.__version__}<br><br>"
            "Turns DSLR scans of black-and-white negatives into positives.<br>"
            "Your RAW files are never changed; edits are kept in "
            "<i>film-converter.json</i> inside each roll folder."))

    def _add_actions(self, menu, items):
        for item in items:
            if item is None:
                menu.addSeparator()
                continue
            text, key, slot = item
            a = QAction(text, self)
            if key:
                a.setShortcut(key)
            a.triggered.connect(slot)
            menu.addAction(a)

    def _set_enabled(self, on: bool):
        for w in self.findChildren(QPushButton) + list(self.sliders.values()) + \
                [self.cmb_channel, self.chk_base_black]:
            w.setEnabled(on)

    # --- opening -------------------------------------------------------------
    def on_open_roll(self):
        """A file picker that shows the scans (a folder picker hides them, which
        looks like an empty folder). Picking any scan opens its whole folder."""
        start = self.qsettings.value("last_dir", str(Path.home()))
        names, _ = QFileDialog.getOpenFileNames(
            self, "Open roll – pick any scan in the folder (the whole roll opens)", start,
            RAW_FILTER + ";;All files (*)")
        if names:
            self.open_path(Path(names[0]))

    def open_path(self, path: Path):
        """A folder opens as a roll; a file opens its folder with that frame selected."""
        folder, select = (path, None) if path.is_dir() else (path.parent, path.name)
        roll = Roll.open(folder)
        if not roll.files:
            QMessageBox.information(self, "Open roll", f"No RAW files found in\n{folder}")
            return
        self.save_roll()
        self.qsettings.setValue("last_dir", str(folder))
        self._generation += 1
        self.bg_pool.clear()
        self.roll, self.name, self.working = roll, None, None
        self.cache.clear()
        self.setWindowTitle(f"Film Converter – {folder.name}")
        self.strip.set_frames(roll.names())
        for n in roll.names():
            self.strip.set_edited(n, is_edited(roll.frames[n]))
        self._set_enabled(True)
        first = select if select in roll.frames else roll.names()[0]
        self.strip.select_name(first)
        self.strip.setFocus()
        # Prepare all previews in the background, starting near the current frame.
        names = roll.names()
        i = names.index(first)
        for n in names[i:] + names[:i]:
            self._queue_prepare(n, self.bg_pool)

    def _queue_prepare(self, name: str, pool: QThreadPool):
        s = self.roll.frames[name].copy()
        gen, key = self._generation, analysis_key(s)
        job = Job(prepare_frame, self.roll.path(name), s)
        self._jobs.add(job)

        def done(result):
            self._jobs.discard(job)
            if gen == self._generation:
                self.on_prepared(name, key, s.channel, result)

        def failed(msg):
            self._jobs.discard(job)
            if gen == self._generation:
                self.strip.set_edited(name, False)
                self.statusBar().showMessage(f"Could not read {name}", 8000)
                print(msg)

        job.signals.done.connect(done)
        job.signals.failed.connect(failed)
        pool.start(job)

    def on_prepared(self, name, key, channel, result):
        working, scale, auto = result
        self.cache[(name, channel)] = (working, scale)
        s = self.roll.frames[name]
        if analysis_key(s) == key and s.channel == channel and s.auto.d_black is None:
            s.auto = auto
            pipeline.apply_auto_rotation(s)
            self._save_timer.start()
        elif s.auto.rotation is None and auto.rotation is not None:
            # A roll analyzed before rotation guessing existed: add the guess.
            s.auto.rotation = auto.rotation
            pipeline.apply_auto_rotation(s)
            self._save_timer.start()
        if name == self.name and self.working is None and s.channel == channel:
            self.show_frame()
        elif name != self.name:
            self.update_thumbnail(name)    # with the frame's current settings
        ready = len({n for n, _ in self.cache})
        total = len(self.roll.files)
        if ready < total:
            self.statusBar().showMessage(f"Preparing previews… {ready}/{total}")
        else:
            self.statusBar().showMessage("All previews ready", 4000)

    # --- frames ----------------------------------------------------------------
    def on_frame_selected(self):
        name = self.strip.current_name()
        if self.roll is None or name is None or name == self.name:
            return
        self.name = name
        self.working = None
        if self.mode == "base":     # crop mode stays on, to tweak frame after frame
            self._uncheck_modes()
        i = self.roll.names().index(name)
        self.lbl_frame.setText(f"{name}    ({i + 1} of {len(self.roll.files)})")
        self._sync_controls()
        cached = self.cache.get((name, self.settings.channel))
        if cached:
            self.show_frame()
        else:
            self.view.placeholder = f"Loading {name}…"
            self.view.set_image(None)
            self._queue_prepare(name, self.pool)   # priority: the main pool

    def show_frame(self):
        self.working, self.scale = self.cache[(self.name, self.settings.channel)]
        if self.settings.auto.d_black is None or self.settings.auto.film_base is None:
            pipeline.update_auto(self.working, self.settings)
        self._update_base_label()
        self.render()

    def step_frame(self, step: int):
        if self.roll is None or self.name is None:
            return
        names = self.roll.names()
        i = (names.index(self.name) + step) % len(names)
        self.strip.select_name(names[i])

    def selected_or_current(self) -> list[str]:
        names = self.strip.selected_names()
        return names or ([self.name] if self.name else [])

    # --- rendering -------------------------------------------------------------
    def reprocess(self, force_levels=False):
        """Recompute the automatic values (after crop / base / channel changes)."""
        if self.working is None:
            return
        pipeline.update_auto(self.working, self.settings, force=force_levels)
        self._update_base_label()
        self.render()
        self.frame_changed()

    def render(self):
        if self.working is None:
            return
        self.positive8 = to8(pipeline.render(self.working, self.settings, self.scale))
        self.hist.set_image(self.positive8)
        self.strip.set_thumbnail(self.name, self.positive8)
        self.update_view()

    def update_view(self):
        if self.working is None:
            return
        s = self.settings
        self.view.overlays = []
        if self.mode == "positive":
            self.view.set_image(self.positive8)
        elif self.mode == "crop":
            # The whole scan as a positive (levels of the cropped frame), with the crop on top.
            full = s.copy()
            full.crop, full.auto_crop = None, False
            self.view.set_image(to8(pipeline.render(self.working, full, self.scale)))
            crop = s.effective_crop()
            self.view.set_crop_mode(True, pipeline.rect_to_view(crop, s) if crop else None)
        else:
            self.view.set_image(pipeline.orient(negative_display(self.working), s))
            overlays = []
            crop = s.effective_crop()
            if crop and self.mode == "negative":
                overlays.append((pipeline.rect_to_view(crop, s), CROP_COLOR))
            if s.film_base_rect and self.mode in ("base", "negative"):
                overlays.append((pipeline.rect_to_view(s.film_base_rect, s), BASE_COLOR))
            self.view.overlays = overlays
        self.view.update()

    def update_thumbnail(self, name: str):
        s = self.roll.frames[name]
        cached = self.cache.get((name, s.channel))
        if cached is None:
            return
        working, scale = cached
        if s.auto.d_black is None:
            pipeline.update_auto(working, s)
        self.strip.set_thumbnail(name, to8(pipeline.render(working, s, scale)))

    def frame_changed(self, names: list[str] | None = None):
        """Mark frames as edited and schedule saving the roll file."""
        for n in names or [self.name]:
            self.strip.set_edited(n, is_edited(self.roll.frames[n]))
        self._save_timer.start()

    def save_roll(self):
        if self.roll is None:
            return
        if not self.roll.save() and not self._save_warned:
            self._save_warned = True
            self.statusBar().showMessage(
                "Note: can't save edits in this folder (read-only?). They last until you close the app.", 10000)

    # --- controls ----------------------------------------------------------------
    def _sync_controls(self):
        s = self.settings
        for name, slider in self.sliders.items():
            slider.blockSignals(True)
            k = SLIDER_STEPS if name == "exposure" else 1
            slider.setValue(int(round(getattr(s, name) * k)))
            slider.blockSignals(False)
            self._update_slider_label(name)
        for w, value in [(self.chk_base_black, s.black_from_base)]:
            w.blockSignals(True)
            w.setChecked(value)
            w.blockSignals(False)
        self.cmb_channel.blockSignals(True)
        self.cmb_channel.setCurrentIndex(CHANNELS.index(s.channel))
        self.cmb_channel.blockSignals(False)
        self._update_base_label()

    def _update_slider_label(self, name):
        v = getattr(self.settings, name)
        text = f"{v:+.2f}" if name == "exposure" else (f"{v:.0f}" if name == "sharpening" else f"{v:+.0f}")
        self.slider_labels[name].setText(text)

    def _update_base_label(self):
        a, s = self.settings.auto, self.settings
        if a.film_base is None:
            self.lbl_base.setText("not measured yet")
        else:
            self.lbl_base.setText(f"{a.film_base:.3f} ({'picked' if s.film_base_rect else 'auto'})")

    def _uncheck_modes(self):
        for b in (self.btn_crop, self.btn_pick, self.btn_before):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self.mode = "positive"
        self.view.set_pick_mode(False)
        self.view.set_crop_mode(False)
        self.btn_crop.setText("Adjust crop")
        self.statusBar().clearMessage()

    def set_mode(self, mode: str):
        if mode != "positive":
            for b, m in ((self.btn_crop, "crop"), (self.btn_pick, "base"), (self.btn_before, "negative")):
                if m != mode:
                    b.blockSignals(True)
                    b.setChecked(False)
                    b.blockSignals(False)
        self.mode = mode
        self.view.set_pick_mode(mode == "base")
        self.view.set_crop_mode(mode == "crop")
        self.btn_crop.setText("✓ Done cropping" if mode == "crop" else "Adjust crop")
        if mode == "crop":
            self.statusBar().showMessage(
                "Drag the edges or corners to adjust, drag inside to move, or draw a new frame "
                "outside it. Enter = done.")
        elif mode == "base":
            self.statusBar().showMessage("Drag a rectangle over clear film (no picture, no sprocket holes)")
        else:
            self.statusBar().clearMessage()
        self.update_view()

    def _single_keys(self) -> dict:
        """One-key shortcuts (no modifiers): key -> button to click."""
        return {Qt.Key_BracketLeft: self.btn_rot_l, Qt.Key_BracketRight: self.btn_rot_r,
                Qt.Key_H: self.btn_flip_h, Qt.Key_V: self.btn_flip_v, Qt.Key_C: self.btn_crop}

    def _is_mine(self, obj) -> bool:
        if isinstance(obj, QWidget):
            return obj.window() is self
        return obj is self.windowHandle()

    def eventFilter(self, obj, e):
        """Window-wide keys, handled here so they work whatever has focus (the
        strip would otherwise eat letters for its type-to-search). Each key
        event is handled once and then consumed."""
        t = e.type()
        if t not in (QEvent.KeyPress, QEvent.KeyRelease) or not self._is_mine(obj)                 or QApplication.activeModalWidget() is not None or self.working is None:
            return super().eventFilter(obj, e)
        key = e.key()
        plain = not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))
        if key == Qt.Key_B and plain:
            if not e.isAutoRepeat():
                if t == QEvent.KeyPress and self.mode == "positive":
                    self.mode = "negative"
                    self.update_view()
                elif t == QEvent.KeyRelease and self.mode == "negative" and not self.btn_before.isChecked():
                    self.mode = "positive"
                    self.update_view()
            return True
        button = self._single_keys().get(key) if plain else None
        if button is not None:
            if t == QEvent.KeyPress and not e.isAutoRepeat() and button.isEnabled():
                button.click()
            return True
        if t == QEvent.KeyPress and self.mode == "crop" and                 key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.btn_crop.setChecked(False)
            return True
        return super().eventFilter(obj, e)

    def on_crop_edited(self, rect):
        if self.working is None or self.mode != "crop":
            return
        self.settings.crop = pipeline.rect_from_view(rect, self.settings)
        self.reprocess(force_levels=True)

    def on_rect_picked(self, rect):
        if self.working is None:
            return
        rect = pipeline.rect_from_view(rect, self.settings)
        if self.mode == "base":
            self.settings.film_base_rect = rect
            pipeline.update_film_base(self.working, self.settings)
            self.btn_pick.setChecked(False)
        self.reprocess(force_levels=True)

    def on_slider(self, name, value):
        setattr(self.settings, name, value)
        self._update_slider_label(name)
        self._render_timer.start()
        self.frame_changed()

    def rotate(self, degrees: int):
        self._transform(lambda s: setattr(s, "rotation", (s.rotation + degrees) % 360))

    def flip(self, vertical: bool):
        self._transform(lambda s: pipeline.flip_view(s, vertical))

    def _transform(self, fn):
        """Rotate or flip all selected frames."""
        if self.roll is None or self.name is None:
            return
        names = self.selected_or_current()
        for n in names:
            fn(self.roll.frames[n])
            if n != self.name:
                self.update_thumbnail(n)
        self.render()
        self.frame_changed(names)

    def on_auto_crop(self):
        self.settings.crop = None
        self.settings.auto_crop = True
        self.reprocess(force_levels=True)

    def on_reset_sliders(self):
        self.settings.reset_adjustments()
        self._sync_controls()
        self.render()
        self.frame_changed()

    def on_copy(self):
        if self.name:
            self.clipboard = self.settings.copy()
            self.statusBar().showMessage(f"Copied slider settings of {self.name}", 4000)

    def on_paste(self):
        if self.clipboard is None or self.roll is None:
            return
        names = self.selected_or_current()
        self._apply_look(self.clipboard, names)

    def on_apply_all(self):
        if self.roll is None:
            return
        if QMessageBox.question(self, "Apply to all",
                                "Use this frame's slider settings on every frame of the roll?") \
                != QMessageBox.Yes:
            return
        self._apply_look(self.settings.copy(), self.roll.names())

    def _apply_look(self, source: Settings, names: list[str]):
        self.roll.apply_adjustments(source, names)
        for n in names:
            if n != self.name:
                self.update_thumbnail(n)
        self._sync_controls()
        self.render()
        self.frame_changed(names)
        self.statusBar().showMessage(f"Applied settings to {len(names)} frame(s)", 4000)

    def on_channel_changed(self, index):
        self.settings.channel = CHANNELS[index]
        if self.settings.film_base_rect is None:
            self.settings.auto.film_base = None
        self.settings.auto = AutoValues(film_base=self.settings.auto.film_base,
                                        rotation=self.settings.auto.rotation)
        self.frame_changed()
        self.working = None
        if (self.name, self.settings.channel) in self.cache:
            self.show_frame()
        else:
            self._queue_prepare(self.name, self.pool)

    def on_option_changed(self):
        self.settings.black_from_base = self.chk_base_black.isChecked()
        self.reprocess(force_levels=True)

    def on_auto_base(self):
        self.settings.film_base_rect = None
        self.settings.auto.film_base = None
        self.reprocess(force_levels=True)

    def on_toggle_advanced(self, on):
        self.adv.setVisible(on)
        self.btn_adv.setText("Advanced ▾" if on else "Advanced ▸")

    # --- export ------------------------------------------------------------------
    def open_export_dialog(self, mode: int | None = None):
        if self.roll is None or self.name is None or self.export_job is not None:
            return
        icons = {n: self.strip.icon(n) for n in self.roll.names()}
        dlg = ExportDialog(self, self.roll, self.name, self.strip.selected_names(), icons, mode)
        if dlg.exec() != QDialog.Accepted:
            return
        self.roll.formats = dlg.formats() or self.roll.formats
        self.roll.contact_sheet = dlg.contact_sheet()
        self.roll.output_dir = dlg.output_dir()
        self.export(dlg.names(), dlg.formats(), dlg.contact_sheet())

    def export(self, names: list[str], formats: list[str], sheet: bool = False):
        out_dir = self.roll.output_dir if self.roll else None
        if self.roll is None or not names or out_dir is None or self.export_job is not None:
            return
        self.save_roll()
        job = Job(export_frames, self.roll, list(names), out_dir, formats, sheet, with_progress=True)
        self.export_job = job
        self.progress.setRange(0, len(names) + (1 if sheet else 0))
        self.progress.setValue(0)
        for w in (self.progress, self.btn_cancel):
            w.setVisible(True)
        self.btn_export.setEnabled(False)

        def progress(i, name):
            self.progress.setValue(i)
            if name == "contact sheet":
                self.statusBar().showMessage("Making the contact sheet…")
            elif name:
                self.statusBar().showMessage(f"Exporting {name} ({i + 1} of {len(names)})…")

        def finish():
            self.export_job = None
            for w in (self.progress, self.btn_cancel):
                w.setVisible(False)
            self.btn_export.setEnabled(True)
            self.statusBar().clearMessage()

        def done(result):
            written, errors = result
            finish()
            sheets = [p for p in written if p.name.endswith(contact_sheet.FILE_SUFFIX)]
            done_paths = set(written)
            frames = sum(1 for n in names if any(
                p in done_paths for p in pipeline.output_paths(Path(n), out_dir, formats).values()))
            msg = QMessageBox(self)
            msg.setWindowTitle("Export finished")
            text = f"Exported {frames} of {len(names)} frame(s) to\n{out_dir}" if formats else \
                f"Saved to\n{out_dir}"
            if sheets:
                text += f"\n\nContact sheet: {sheets[0].name}"
            if job.cancel_requested:
                text = "Export cancelled.\n" + text
            if errors:
                text += "\n\nProblems:\n" + "\n".join(errors[:10])
            msg.setText(text)
            open_btn = msg.addButton("Open folder", QMessageBox.AcceptRole)
            sheet_btn = msg.addButton("Open contact sheet", QMessageBox.ActionRole) if sheets else None
            msg.addButton(QMessageBox.Close)
            msg.exec()
            if msg.clickedButton() is open_btn:
                self.open_output_folder()
            elif sheets and msg.clickedButton() is sheet_btn:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(sheets[0])))

        def failed(text):
            finish()
            QMessageBox.critical(self, "Export failed", text)

        job.signals.progress.connect(progress)
        job.signals.done.connect(done)
        job.signals.failed.connect(failed)
        self.pool.start(job)

    def on_cancel_export(self):
        if self.export_job is not None:
            self.export_job.cancel_requested = True
            self.statusBar().showMessage("Cancelling after the current frame…")

    def open_output_folder(self):
        if self.roll and self.roll.output_dir:
            self.roll.output_dir.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.roll.output_dir)))

    # --- drag & drop, closing ---------------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.open_path(Path(urls[0].toLocalFile()))

    def closeEvent(self, e):
        if self.export_job is not None:
            if QMessageBox.question(self, "Quit", "An export is running. Quit anyway?") != QMessageBox.Yes:
                e.ignore()
                return
            self.export_job.cancel_requested = True
        QApplication.instance().removeEventFilter(self)
        self.save_roll()
        self.bg_pool.clear()
        self.bg_pool.waitForDone(3000)
        super().closeEvent(e)
