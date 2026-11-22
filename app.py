r"""Launch the Film Converter GUI:  .venv\Scripts\python app.py [roll folder or file.NEF]

The desktop shortcut (tools/create_shortcut.ps1) runs this with pythonw.exe,
so no console window appears. The installer build (tools/build.ps1) bundles
it with PyInstaller as "Film Converter.exe".

Hidden checks for the bundled app (Windows .exe or the binary inside the macOS
.app, "Film Converter.app/Contents/MacOS/Film Converter"):
  --self-test <roll> <out>   opens the roll, exports its first frame and writes
                             <out>/self-test.txt
  --smoke-test <out>         no RAWs needed (used by the macOS cloud build):
                             loads LibRaw, converts a synthetic negative to every
                             format and opens the main window off screen
"""
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import filmconv
from filmconv_gui.main_window import MainWindow

# Inside the PyInstaller bundle, data files live under sys._MEIPASS.
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON = BASE / "filmconv_gui" / "icon.ico"


def self_test(roll_dir: Path, out_dir: Path) -> int:
    """Headless end-to-end check of the bundle: RAW decode, analysis, export."""
    from filmconv import export
    from filmconv.roll import Roll, export_frames
    report = out_dir / "self-test.txt"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        roll = Roll.open(roll_dir)
        names = roll.names()[:1]
        written, errors = export_frames(roll, names, out_dir, list(export.FORMATS), sheet=True)
        report.write_text(f"version {filmconv.__version__}\nframes {len(roll.names())}\n"
                          f"written {[p.name for p in written]}\nerrors {errors}\n", encoding="utf-8")
        return 0 if written and not errors else 1
    except Exception:
        report.write_text(traceback.format_exc(), encoding="utf-8")
        return 1


def smoke_test(out_dir: Path) -> int:
    """Checks that the bundle's libraries load and work, without any RAW files."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "smoke-test.txt"
    try:
        import numpy as np
        import rawpy
        from filmconv import contact_sheet, export, pipeline
        from filmconv.settings import Settings
        # Synthetic linear scan: clear base border around a gradient frame.
        h, w, base = 400, 600, 0.8
        scene = np.tile(np.linspace(0.0, 1.0, w - 80, dtype=np.float32), (h - 80, 1))
        img = np.full((h, w), base, np.float32)
        img[40:-40, 40:-40] = base * 10 ** -(0.1 + 1.5 * scene)
        rgb = np.repeat(img[..., None], 3, axis=2)
        settings = Settings()
        working = pipeline.to_working(rgb, settings)
        pipeline.update_auto(working, settings)
        positive = pipeline.render(working, settings)
        written = []
        for fmt in export.FORMATS:
            path = out_dir / ("smoke" + export.suffix(fmt))
            export.save(path, positive, fmt)
            written.append(path.name)
        sheet = contact_sheet.make([("1", contact_sheet.thumbnail(positive))], title="smoke test")
        sheet.save(out_dir / "smoke_sheet.jpg")
        app = QApplication(sys.argv[:1])
        win = MainWindow()
        win.show()
        app.processEvents()
        shot = win.grab()
        win.close()
        lines = [f"version {filmconv.__version__}", f"platform {sys.platform}",
                 f"libraw {rawpy.libraw_version}", f"written {written}",
                 f"window {shot.width()}x{shot.height()}", "OK"]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    except Exception:
        report.write_text(traceback.format_exc(), encoding="utf-8")
        return 1


class FilmConverterApp(QApplication):
    """On macOS, files dropped on the Dock icon or opened from Finder arrive as
    a FileOpen event, not on the command line."""

    def __init__(self, argv):
        super().__init__(argv)
        self.window: MainWindow | None = None
        self.pending: Path | None = None

    def event(self, e):
        if e.type() == QEvent.FileOpen:
            path = Path(e.file())
            if self.window is not None:
                self.window.open_path(path)
            else:
                self.pending = path
            return True
        return super().event(e)


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--self-test":
        return self_test(Path(sys.argv[2]), Path(sys.argv[3]))
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        return smoke_test(Path(sys.argv[2]))
    if sys.platform == "win32":
        # Own taskbar entry and icon, instead of being grouped under Python.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FilmConverter.App")
    app = FilmConverterApp(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(filmconv.APP_NAME)
    app.setWindowIcon(QIcon(str(ICON)))
    win = app.window = MainWindow()
    win.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        win.open_path(Path(sys.argv[1]))
    elif app.pending is not None:
        win.open_path(app.pending)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
