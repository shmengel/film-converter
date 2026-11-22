# PyInstaller spec: a folder build (fast start) of the GUI.
#   Windows: build/dist/Film Converter/Film Converter.exe  (tools\build.ps1, then Inno Setup)
#   macOS:   build/dist/Film Converter.app                 (tools/build_mac.sh, then a .dmg)
# PyInstaller can't cross-compile: the macOS app must be built on a Mac
# (or by the GitHub Actions workflow in .github/workflows/build-mac.yml).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
import filmconv  # noqa: E402  (for the version number)

MAC = sys.platform == "darwin"
ICO = str(ROOT / "filmconv_gui" / "icon.ico")       # window icon (both), exe icon (Windows)
ICNS = str(ROOT / "filmconv_gui" / "icon.icns")     # app bundle icon (macOS)


def licence_files():
    """Licence texts that must travel with the app (see packaging/licenses/
    THIRD_PARTY_NOTICES.txt): our notices + LGPL/GPL texts, each bundled
    package's own licence files, and Python's. They end up in a "licenses"
    folder next to the program files."""
    from importlib.metadata import distribution
    out = [(str(p), "licenses") for p in (ROOT / "packaging" / "licenses").glob("*.txt")]
    out.append((str(ROOT / "LICENSE"), "licenses/film-converter"))      # our own (MIT)
    for pkg in ("numpy", "opencv-python-headless", "pillow", "rawpy", "tifffile",
                "pyside6", "shiboken6"):
        dist = distribution(pkg)
        for f in dist.files or []:
            parts = Path(str(f)).parts
            name = parts[-1].upper()
            if not parts[0].endswith(".dist-info") or "COMMERCIAL" in name:
                continue          # Qt is used under the LGPL, not its commercial licence
            if "LICEN" in name or "COPYING" in name or "NOTICE" in name:
                # Keep sub-folders (numpy has several files called LICENSE.md).
                sub = Path(*parts[1:-1])
                if sub.parts and sub.parts[0] == "licenses":
                    sub = Path(*sub.parts[1:])
                out.append((str(dist.locate_file(f)), str(Path("licenses", pkg, sub))))
    base = Path(sys.base_prefix)
    for p in [base / "LICENSE.txt", *base.glob("lib/python3*/LICENSE.txt")]:
        if p.is_file():
            out.append((str(p), "licenses/python"))
            break
    return out


a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=collect_dynamic_libs("rawpy"),          # LibRaw DLL / dylib
    datas=[(ICO, "filmconv_gui"), (str(ROOT / "docs" / "HOW_IT_WORKS.md"), "docs")] + licence_files(),
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

if not MAC:
    # Large files the app never uses (~90 MB): OpenCV's video I/O, Qt's software
    # OpenGL fallback, and the on-screen-keyboard plugin that drags in Qt Quick/QML
    # (plus the PDF image plugin). Windows only: on macOS, OpenCV links its video
    # libraries directly and Qt comes as signed .framework folders, so removing
    # files there would break the app.
    DROP = ("opencv_videoio_ffmpeg", "opengl32sw.dll", "qtvirtualkeyboardplugin", "Qt6VirtualKeyboard",
            "Qt6Quick", "Qt6Qml", "qpdf.dll", "Qt6Pdf")
    a.binaries = [b for b in a.binaries if not any(d in b[0] for d in DROP)]
    a.datas = [d for d in a.datas if not any(x in d[0] for x in DROP)]
else:
    # Qt Virtual Keyboard is GPL-3.0 only (the rest of Qt used here is LGPL-3.0),
    # and the app has no use for an on-screen keyboard. Remove its plugin and
    # framework as a whole, so no half-framework is left behind.
    def _keep(entry):
        return "virtualkeyboard" not in entry[0].lower()
    a.binaries = [b for b in a.binaries if _keep(b)]
    a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Film Converter",
    icon=ICNS if MAC else ICO,
    console=False,          # GUI only: no console / Terminal window
    upx=False,              # UPX-packed files trigger antivirus false alarms
    # macOS: no Developer ID, so PyInstaller signs ad hoc (required on Apple Silicon).
    # Finder "open with" arrives as a Qt FileOpen event (see app.py), so no argv emulation.
    argv_emulation=False,
    target_arch=None,       # the architecture of the Python that builds it (arm64 on M-series Macs)
    codesign_identity=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Film Converter", upx=False)

if MAC:
    RAW_EXTS = ["nef", "nrw", "dng", "cr2", "cr3", "arw", "raf", "orf", "rw2", "pef"]
    app = BUNDLE(
        coll,
        name="Film Converter.app",
        icon=ICNS,
        bundle_identifier="com.yoavengel.filmconverter",   # keep it fixed: macOS ties permissions to it
        version=filmconv.__version__,
        info_plist={
            "CFBundleName": "Film Converter",
            "CFBundleDisplayName": "Film Converter",
            "CFBundleShortVersionString": filmconv.__version__,
            "CFBundleVersion": filmconv.__version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",   # numpy and PySide6 wheels need macOS 14+
            "NSHumanReadableCopyright": "Yoav Engel",
            # Shows the app under "Open With" for RAW files and lets them be
            # dropped on its Dock icon. "Alternate": never takes over as the default.
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Camera RAW image",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "CFBundleTypeExtensions": RAW_EXTS + [e.upper() for e in RAW_EXTS],
                "LSItemContentTypes": ["public.camera-raw-image", "public.folder"],
            }],
        },
    )
