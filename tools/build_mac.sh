#!/bin/bash
# Builds the macOS app and a .dmg for people without Python. Run it ON A MAC
# (PyInstaller can't build Mac apps from Windows), or let GitHub Actions run it
# (.github/workflows/build-mac.yml).
#
#   bash tools/build_mac.sh [test roll folder with a few RAWs]
#
# Steps: venv + packages -> tests -> PyInstaller (.app) -> smoke test of the
# built app (+ self-test on real RAWs if a folder is given) -> .dmg
# Result: build/installer/FilmConverter-<version>-mac-<arch>.dmg
# Needs: Python 3.12 (python.org installer or `brew install python@3.12`).
# Uses its own .venv-mac, so a project folder copied from Windows (with a
# Windows .venv inside) still works.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
TEST_ROLL="${1:-}"

PY_SYS="${PYTHON:-$(command -v python3.12 || true)}"
[ -n "$PY_SYS" ] || { echo "Python 3.12 not found (brew install python@3.12, or set PYTHON=...)"; exit 1; }
VENV="$ROOT/.venv-mac"
if [ ! -x "$VENV/bin/python" ]; then
    echo "== Creating $VENV"
    "$PY_SYS" -m venv "$VENV"
fi
PY="$VENV/bin/python"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt -r requirements-build.txt

VERSION="$("$PY" -c 'import filmconv; print(filmconv.__version__)')"
ARCH="$(uname -m)"          # arm64 on Apple Silicon
echo "== Film Converter $VERSION ($ARCH)"

echo "== Tests"
QT_QPA_PLATFORM=offscreen "$PY" -m pytest -q

echo "== PyInstaller"
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath build/dist --workpath build/work packaging/film_converter.spec
APP="build/dist/Film Converter.app"
BIN="$APP/Contents/MacOS/Film Converter"

echo "== Licence check"
# Qt Virtual Keyboard is GPL-only and must not ship (the spec removes it).
if find "$APP" -ipath '*virtualkeyboard*' | grep -q .; then
    find "$APP" -ipath '*virtualkeyboard*' | head
    echo "GPL-only Qt Virtual Keyboard found in the app"; exit 1
fi
LIC="$(find "$APP" -type d -name licenses | head -1)"
[ -f "$LIC/THIRD_PARTY_NOTICES.txt" ] && [ -f "$LIC/LGPL-3.0.txt" ] || { echo "Licence files missing from the app"; exit 1; }
echo "licences: $LIC ($(find "$LIC" -type f | wc -l | tr -d ' ') files)"

echo "== Smoke test of the built app"
rm -rf build/smoke
if ! "$BIN" --smoke-test build/smoke; then
    cat build/smoke/smoke-test.txt || true
    echo "Smoke test of the built app failed"; exit 1
fi
cat build/smoke/smoke-test.txt

if [ -n "$TEST_ROLL" ]; then
    echo "== Self-test on 2 RAWs from $TEST_ROLL"
    TMP="$(mktemp -d)"
    mkdir "$TMP/roll"
    find "$TEST_ROLL" -maxdepth 1 -type f \( -iname '*.nef' -o -iname '*.dng' \) | sort | head -2 |
        while read -r f; do cp "$f" "$TMP/roll/"; done
    "$BIN" --self-test "$TMP/roll" "$TMP/out" || { cat "$TMP/out/self-test.txt"; exit 1; }
    cat "$TMP/out/self-test.txt"
fi

echo "== Disk image"
mkdir -p build/installer
STAGE="build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/Film Converter.app"            # ditto keeps symlinks and the signature
ln -s /Applications "$STAGE/Applications"
cp packaging/mac_first_launch.txt "$STAGE/First launch - read me.txt"
cp docs/HOW_IT_WORKS.md "$STAGE/How it works.md"
DMG="build/installer/FilmConverter-$VERSION-mac-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "Film Converter" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "== Done: $DMG ($(du -h "$DMG" | cut -f1))"
