"""Launch the Film Converter GUI:  .venv\Scripts\python app.py [file.NEF]"""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from filmconv_gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.open_file(Path(sys.argv[1]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
