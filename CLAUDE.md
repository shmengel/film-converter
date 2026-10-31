# Project: Desktop app for automatic B&W film negative conversion (DSLR scans)

## Goal
Build a Windows desktop program with a friendly GUI that takes RAW files of
black-and-white film negatives photographed with a DSLR and automatically
converts them into balanced positive images: inversion plus automatic
exposure / brightness / contrast. The point is to stop manually inverting
and adjusting every frame. For reference, look at how existing tools work:
Negative Lab Pro (Lightroom plugin), darktable's "negadoctor", and
RawTherapee's "Film Negative" tool. But this should be a standalone app.

Version 1 is B&W only. Color negative (C-41) support will come in a later
version, so keep the processing code modular (e.g. a "film type" processing
stage that can be swapped or extended).

## My scanning setup (where the input comes from)
- Camera: Nikon D7000 (16 MP APS-C, 14-bit RAW, Nikon .NEF files,
  ~17–19 MB each).
- Lens: Nikon 50mm macro (Micro-Nikkor).
- Rig: camera mounted on a drill-press stand pointing down; film sits in a
  tray over a light source. Height sets magnification; focus is fine-tuned
  from the laptop.
- Tethering: camera connected by USB (Mini-B) to a Windows 11 laptop and
  controlled with digiCamControl (live view, focus, capture). Files are saved
  directly to a folder on the laptop, one folder per roll.
- Capture settings: RAW (NEF), ISO 100, aperture ~f/5.6–f/8, manual exposure,
  fixed white balance, exposure delay mode. Every frame of a roll is shot
  with identical settings.
- Framing: each shot may include some film border / rebate (clear film base
  and possibly sprocket holes), which can serve as a reference for the film
  base density.
- The camera clock may be wrong, so don't rely on EXIF dates for ordering;
  use filenames (e.g. _ZNG0674.NEF).

## Film formats
- 35mm (3:2 frames), the main use case.
- 120 medium format, mainly 6x6 from a Kiev-88. Assume one frame per shot for
  now; stitching multiple shots is a possible later feature.

## Processing pipeline (suggested, open to better ideas)
1. Read the NEF with rawpy (LibRaw) into linear 16-bit data, with no
   auto-brightening and no camera tone curve.
2. Convert to monochrome (luminance, or a selectable channel such as green,
   which is usually the sharpest and least noisy).
3. Film base: let the user click on the clear film border (or detect it
   automatically) to sample the base density; use it as the reference for
   the darkest output black.
4. Invert in linear space (e.g. 1/x or log/density-based, like negadoctor),
   not a simple 255−x on gamma-encoded data.
5. Auto-balance: black/white points from percentiles of the image area only
   (exclude the border, rebate and sprocket holes), then a gamma/contrast curve.
6. Auto-crop: detect the frame edges and crop out the border (with manual override).
7. Export 16-bit grayscale TIFF and/or JPEG.

## Roll-based workflow (key requirement)
- Open a whole folder (a roll) at once.
- Sample the film base once per roll and apply it to all frames, so tones stay
  consistent across the roll.
- Offer both "auto per frame" and "same settings for the whole roll" modes.
- Allow per-frame tweaks after the automatic pass.
- Copy / paste settings between frames; save and load presets per film stock
  (e.g. HP5, Tri-X, Fomapan).
- Optional: watch-folder mode that converts new files automatically as
  digiCamControl saves them during a scanning session.

## GUI requirements
- Simple and friendly; I'm a first-year engineering student, comfortable with
  some code, but the app itself should need none.
- Thumbnail strip of the roll, plus a large before/after preview.
- Sliders for exposure, contrast, black point, white point, highlights/shadows,
  with directions already corrected for inverted images (moving exposure up
  makes the positive brighter).
- Film base picker, crop tool, histogram.
- Batch export with progress bar; output folder and format selection.
- Fast previews (work on downscaled images; process full resolution only on export).

## Tech constraints
- Language: Python. Suggested libraries: rawpy, numpy, OpenCV/scikit-image,
  tifffile/imageio, and a GUI toolkit (PySide6/PyQt preferred, but suggest
  the best fit).
- Runs locally on a Windows 11 laptop; should be packageable as an .exe later.
- Non-destructive: never modify the original NEF files.

## How I want to work
Build this step by step. Start with a working minimal version (open one NEF,
pick film base, invert, auto-balance, export TIFF/JPEG), then add features in
stages: roll/batch processing, GUI polish, presets, auto-crop, watch folder.
Explain key decisions briefly. Ask me if anything about my setup is unclear
before assuming.

## Project conventions (for Claude)
- Use a virtual environment in `.venv` with Python 3.11 or 3.12 (newer
  versions may lack rawpy / PyInstaller wheels). Keep `requirements.txt`
  up to date.
- Sample NEFs for testing live in `samples/`. Treat them as read-only; write
  test outputs to `output/` (git-ignored), never next to the originals.
- Keep processing code (no Qt imports) separate from GUI code, so it can be
  tested and run from a command-line script without the GUI.
- Keep all processing settings in one serializable settings object (JSON),
  so presets, copy/paste and per-roll settings reuse the same structure.
- Compute auto-balance values on the preview and reuse them at export, so the
  exported file matches what was shown on screen.
- Windows gotchas: folder paths may contain Hebrew or spaces; use
  `pathlib` and avoid libraries that break on non-ASCII paths (e.g.
  `cv2.imwrite` — use `cv2.imencode(...).tofile(...)` or Pillow). If OpenCV is
  needed alongside PySide6, use `opencv-python-headless` to avoid Qt plugin
  conflicts.
- After each stage, tell me how to run it and what to test on my real scans.

## Project status (keep this section up to date)

### Stage 1 – done (2026-10-31)
Single-frame conversion: open one NEF, pick or auto-estimate the film base,
invert, auto-balance, adjust with sliders, export 16-bit TIFF / JPEG.
- Environment: Python 3.12.10 in `.venv` (system also has 3.14; use
  `py -3.12`). Git repo initialized; `samples/` and `output/` are git-ignored.
- Code layout: `filmconv/` is the core with no Qt imports (`settings.py`,
  `raw_io.py`, `film_types.py`, `tone.py`, `pipeline.py`, `export.py`,
  `cli.py`). `filmconv_gui/` is the PySide6 GUI. `app.py` launches it.
  `tests/` holds pytest tests that run on synthetic negatives.
- Pipeline: rawpy (gamma 1, no auto-bright, camera WB, raw color space) →
  channel (default green) → density D = log10(base / T) → auto levels from
  the 0.2/99.8 percentiles of the inner image (8% edge margin) plus a midtone
  gamma that puts the median at 0.45 → sliders → crop → export. Auto values
  are stored in `Settings.auto` and reused at export.
- Slider directions follow Lightroom: moving right makes the image
  brighter or the effect stronger (Blacks + lifts the shadows).
- With the auto black point, the film base value mostly cancels out. It
  matters for "Film base is pure black" mode, for keeping the reference
  fixed across a roll, and later for C-41.

### First real scan test (DSC_0007.nef, Ilford HP5+)
- The scan held about 2.5 frames on a strip, with ~40% bare light-source
  area around it. That gave only ~2000×1350 px per frame and soft results.
- Shot from the emulsion side, so the image is mirrored (edge printing
  reads backwards).
- Green-channel values: bare light and sprocket holes ~0.44, clear film
  base ~0.14. The auto base estimate wrongly picked the bare light, and
  auto-balance was thrown off by the light and the rebate.
- The light source falls off ~10% toward the corners.
- With a manual crop and the base picked from the gap between frames, the
  conversion looked good. So the inversion and tone pipeline are sound.
- **The user is rebuilding the scanning rig** (likely one frame per shot at
  higher magnification). Wait for new sample scans before tuning defaults,
  and ask about the new framing before assuming it.

### Next steps
1. When new scans arrive: flip/rotate setting, crop tool (manual), a film
   base estimate that excludes bare light / sprocket holes (e.g. the
   brightest plateau clearly below the light source), and auto-balance that
   ignores areas outside the film.
2. Stage 2: roll workflow (open folder, thumbnail strip, base once per roll,
   auto-per-frame vs same-for-roll, copy/paste settings, batch export).
3. Later: presets per film stock, auto-crop / frame detection, watch folder,
   PyInstaller .exe. If several frames per shot remain common, add
   frame splitting.
