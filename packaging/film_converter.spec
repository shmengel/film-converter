# PyInstaller spec: a folder build (fast start) of the GUI as "Film Converter.exe".
# Build with tools\build.ps1 (it runs PyInstaller, then Inno Setup).
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "filmconv_gui" / "icon.ico")

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=collect_dynamic_libs("rawpy"),          # LibRaw DLL
    datas=[(ICON, "filmconv_gui")],
    hiddenimports=[],
    excludes=[
        "tkinter", "pytest", "_pytest", "matplotlib", "scipy", "IPython", "pandas",
        # Qt parts the app doesn't use (PySide6 is large).
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
        "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
    ],
    noarchive=False,
)

# Large files the app never uses (~90 MB): OpenCV's video I/O, Qt's software
# OpenGL fallback, and the on-screen-keyboard plugin that drags in Qt Quick/QML
# (plus the PDF image plugin).
DROP = ("opencv_videoio_ffmpeg", "opengl32sw.dll", "qtvirtualkeyboardplugin", "Qt6VirtualKeyboard",
        "Qt6Quick", "Qt6Qml", "qpdf.dll", "Qt6Pdf")
a.binaries = [b for b in a.binaries if not any(d in b[0] for d in DROP)]
a.datas = [d for d in a.datas if not any(x in d[0] for x in DROP)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Film Converter",
    icon=ICON,
    console=False,          # GUI only: no black console window
    upx=False,              # UPX-packed files trigger antivirus false alarms
)
coll = COLLECT(exe, a.binaries, a.datas, name="Film Converter", upx=False)
