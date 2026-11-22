# Film Converter

Converts RAW (NEF) scans of B&W film negatives into balanced positives.
Desktop app for Windows and macOS (PySide6) with a command-line mode. See `CLAUDE.md` for
the full spec and the detailed project status.

**How the conversion works, and its limits:** [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)
(also in the app: Help → How it works).

## Setup (once)
```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run
- GUI: `.venv\Scripts\python app.py` (optionally pass a .NEF path)
- Command line: `.venv\Scripts\python -m filmconv.cli <files or roll folder> -o output --format tiff jpeg`
  (`--help` lists all options: channel, film base rectangle, sliders, roll levels)
- Tests: `.venv\Scripts\python -m pytest`

## Building the apps
- Windows installer: `powershell -ExecutionPolicy Bypass -File toolsuild.ps1 [-TestRoll <folder>]`
- macOS .dmg (Apple Silicon, macOS 14+): must be built on a Mac. Either run
  `bash tools/build_mac.sh [test roll folder]` on a Mac with Python 3.12, or
  push to GitHub and run the "Build macOS app" workflow (Actions tab); the .dmg
  appears under the run's Artifacts. The app is unsigned; see
  `packaging/mac_first_launch.txt` for the one-time "Open Anyway" step.

## Using the GUI
1. **Ctrl+O** opens a RAW file. **B** switches between the negative and the positive.
2. **Film base → Pick on image:** drag a rectangle over clear film, such as the
   gap between frames or the edge strip. Don't include sprocket holes or
   bare light. **Auto** estimates the base instead.
3. Adjust with the sliders. They all work in "positive" directions: moving
   right makes the image brighter or the effect stronger. **Auto balance**
   recalculates the levels. **Reset sliders** sets the sliders back to zero.
4. Choose TIFF (16-bit) and/or JPEG and an output folder, then click
   **Export full resolution**.
   The original RAW files are never modified.
5. File → Save/Load settings stores all settings as JSON.

## Status
- **Stage 1 (done):** single-frame conversion with film base picking,
  density-based inversion, auto-balance, sliders, histogram, TIFF/JPEG export, CLI.
- **First real test:** the inversion works well once the image is cropped
  to one frame and the base is picked by hand. The test scan showed several
  frames per shot, mirrored film and soft detail. The scanning rig is being
  rebuilt before the next round.
- **Next:** flip/rotate, crop tool, a better automatic film-base estimate,
  then the roll workflow (stage 2).

## Layout
- `filmconv/` – processing core, no Qt (settings, RAW reading, film-type stage, tone stage, export, CLI)
- `filmconv_gui/` – PySide6 GUI
- `tests/` – pytest tests on synthetic negatives
- `samples/` – your test NEFs (read-only, not in git); `output/` – test results (not in git)
