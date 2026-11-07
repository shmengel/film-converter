"""Launch the Film Converter GUI:  .venv\Scripts\python app.py [roll folder or file.NEF]

The desktop shortcut (tools/create_shortcut.ps1) runs this with pythonw.exe,
so no console window appears.
"""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from filmconv_gui.main_window import MainWindow

ICON = Path(__file__).resolve().parent / "filmconv_gui" / "icon.ico"


def main() -> int:
    if sys.platform == "win32":
        # Own taskbar entry and icon, instead of being grouped under Python.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FilmConverter.App")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(ICON)))
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.open_path(Path(sys.argv[1]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
