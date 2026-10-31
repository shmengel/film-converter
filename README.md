# Film Converter

Converts RAW (NEF) scans of B&W film negatives into balanced positives.
Windows desktop app (PySide6) with a command-line mode. See `CLAUDE.md` for
the full spec and the detailed project status.

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
