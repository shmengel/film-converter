r"""Launch the Film Converter GUI:  .venv\Scripts\python app.py [roll folder or file.NEF]

The desktop shortcut (tools/create_shortcut.ps1) runs this with pythonw.exe,
so no console window appears. The installer build (tools/build.ps1) bundles
it with PyInstaller as "Film Converter.exe".

Hidden check for the bundled app:  "Film Converter.exe" --self-test <roll> <out>
opens the roll, exports its first frame and writes <out>/self-test.txt.
"""
import sys
import traceback
from pathlib import Path

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


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--self-test":
        return self_test(Path(sys.argv[2]), Path(sys.argv[3]))
    if sys.platform == "win32":
        # Own taskbar entry and icon, instead of being grouped under Python.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FilmConverter.App")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(filmconv.APP_NAME)
    app.setWindowIcon(QIcon(str(ICON)))
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        win.open_path(Path(sys.argv[1]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
