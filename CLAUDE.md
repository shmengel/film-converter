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
- Lens: Nikon 55mm Micro-Nikkor (manual, non-CPU: the EXIF focal length and
  aperture come from the camera's "non-CPU lens data" menu, so don't trust them).
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
- The light source falls off ~10% toward the corners. (2026-11-08: the user says
  it is steady, not flickering, but will be replaced soon with a better one.
  Don't tune flat-field correction or base defaults to the current light.)
- With a manual crop and the base picked from the gap between frames, the
  conversion looked good. So the inversion and tone pipeline are sound.
- **The user is rebuilding the scanning rig** (likely one frame per shot at
  higher magnification). Wait for new sample scans before tuning defaults,
  and ask about the new framing before assuming it.

### New rig, first conversion (2026-11-07, DSC_0008–0012)
- One 35mm frame per shot, about 3755×2385 px of image area. A dark holder
  masks everything outside the strip; bare light shows only through the
  sprocket holes (green ~0.85, not clipped in DSC_0011). Clear base in the
  rebate ~0.21. Image area spans about x 0.11–0.88, y 0.11–0.85. The frame
  comes out upside down, so it needs `rotation=180`. Mirroring is still unconfirmed.
- The five files are the same frame bracketed; DSC_0009 is about 3 stops under.
- Added `Settings.flip` / `Settings.rotation` (applied last in `render`) and
  CLI `--crop/--rotate/--flip`. Converting DSC_0011 with a manual crop and
  the base from the rebate under the top holes looked good.

### First full roll (2026-11-07, `session1/` DSC_0013–0047, 35 frames)
- `session1/` is in the project root (git-ignored). Many files are hard links
  to the originals in `Pictures\digiCamControl\Session1`, so keep it read-only.
- EXIF: 1/2 s, ISO 200. Focal length 35 mm / f/5.6 are just the camera's
  non-CPU lens setting; the real lens is the 55 mm Micro-Nikkor (user, 2026-11-08).
- Framing moves from shot to shot. Some frames show part of the next frame;
  sometimes the holder hides one hole row or a frame end. Orientation varies:
  about half the frames are upside down. Not mirrored (Thai text in DSC_0034
  reads correctly).
- Sharpness: sprocket-hole edges measure about 5 px (10–90%) everywhere,
  evenly across the frame. That is optical (focus, diffraction at effective
  ~f/8.4, or vibration at 1/2 s), not the software. A sharp setup should
  give about 2.5–3 px.
- Film base (from the rebate) varies 0.18–0.29 between frames at identical
  exposure. With per-frame auto levels it cancels out, but it matters for a
  future "same levels for the whole roll" mode.
- Added `filmconv/framing.py`:
  - finds sprocket holes; film base comes from the rebate between holes
  - pixels/mm from the 4.75 mm hole pitch
  - frame = 24 mm centred between the hole rows (inner span measured at
    25.3 mm); the ends are the clear gaps or holder edges whose spacing best
    matches 36 mm
  - correct on all 35 frames
- Added `Settings.auto_crop` and `AutoValues.crop` (a manual `crop`
  overrides it), DHT demosaic, and a capture-sharpening slider (USM radius
  1 px at full resolution, default 40, skipped on the downscaled preview).
- Output in `output/session1/`. 15 frames were exported with `--rotate 180`:
  0023–25, 0028–31, 0033–39, 0046.

### Stage 2 – roll GUI (2026-11-07; committed 2026-11-08 as 4c59329)
Goal: GUI-only app the user can hand to their dad (non-technical).
- `filmconv/roll.py`: `Roll` (a folder of RAWs, `Settings` per frame,
  persisted to `film-converter.json` in the roll folder; never touches the
  RAWs) and `export_frames` (full-resolution export with progress/cancel;
  analyzes unseen frames from their preview first).
- `pipeline.rect_to_view/rect_from_view`: crop and base picking work on the
  rotated view.
- GUI (later changes are in the sections below): open a roll or drag & drop. Thumbnail strip with
  multi-select; previews prepared on 2 background threads. Rotate selected
  ([ ]), adjust/auto crop, hold B for the negative, sliders, copy/paste/apply
  to all (sliders only), export selected/all with progress, cancel and
  "Open folder". "Advanced" (film base, base-is-black, channel) is collapsed.
  Frames with edits get a ● mark.
- Tested headlessly end to end on a 5-frame copy: about 0.3 s per preview,
  about 1.3 s per JPEG export.

### Stage 2b – workflow polish (2026-11-08)
The user's target workflow: import RAWs → app shows cropped, auto-balanced
positives → scroll and tweak crops and sliders → export what they like.
- Launch: desktop and Start-menu shortcut "Film Converter" (runs
  `.venv\Scripts\pythonw.exe app.py`, no console). Recreate with
  `powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1`.
  The icon comes from `tools/make_icon.py` → `filmconv_gui/icon.ico`.
- Crop editor ("Adjust crop", C): shows the whole scan as a positive with the
  crop on top. Drag edges/corners, drag inside to move, or draw outside for a
  new one; levels update on release. It stays on while moving between frames;
  Enter/Esc finishes.
- Export dialog (Ctrl+E): "This frame only" / "Choose frames" (click thumbnails
  to toggle) / "All frames"; formats JPEG, TIFF 16-bit, TIFF 8-bit
  (`_8bit.tif`), PNG 8-bit; optional contact sheet
  (`filmconv/contact_sheet.py`): one JPEG `<roll>_contact_sheet.jpg`, a 6-wide
  grid labelled with the frame number and file name. Formats, sheet and folder
  are remembered per roll.
- Window-wide keys go through an app event filter (hold B, Enter/Esc), so they
  work while the strip has focus. The mouse wheel scrolls the strip sideways.

### Fixes after first hands-on try (2026-11-08)
- Open roll (Ctrl+O) now uses a file picker that shows the scans; picking any
  one opens the whole folder. The Windows folder picker hid the NEFs, so the
  folder looked empty. Dragging files or a folder onto the window also works.
- Auto upright (`filmconv/orientation.py`): the top third of a photo is usually
  brighter than the bottom, so the frame gets 0 or 180 degrees. On session1
  NEFs: 33/35 correct (misses DSC_0032 water close-up, DSC_0038 pool). Stored
  in `AutoValues.rotation`, guessed once per frame and applied only if the user
  hasn't rotated it. Not counted as an edit (no dot). Portrait (90 degree)
  frames are not detected.
- Flip horizontal / vertical buttons (H / V) next to Rotate. They act on the
  frame as shown and on all selected frames (`pipeline.flip_view`: rotation
  becomes -r, or 180-r for vertical, and `flip` toggles). They replace the old
  "Mirror" checkbox under Advanced. All single-key shortcuts ([ ] H V C, B) go
  through the window's event filter, because the thumbnail strip swallowed
  letters for type-to-search.
- The earlier CLI export in `output/session1/` has DSC_0027 and DSC_0047
  upside down; my manual rotation list missed them.

### Stage 3 – installer for the dad (2026-11-08, version 0.2.0)
- `powershell -ExecutionPolicy Bypass -File tools\build.ps1 -TestRoll session1`
  runs the tests, then a PyInstaller folder build (`packaging/film_converter.spec`,
  `build/dist/`), then a self-test of the built exe on 2 RAWs, then Inno Setup
  (`packaging/installer.iss`). Output: `build/installer/FilmConverter-Setup-<ver>.exe`
  (~53 MB; ~205 MB installed). `build/` is git-ignored.
- Version: `filmconv.__version__`. Bump it for each build you hand out. The
  installer's AppId must never change (upgrades install over the old version).
- The installer is per user (no admin prompt), installs to
  `%LOCALAPPDATA%\Programs\Film Converter`, and adds a Start-menu entry, an
  optional desktop shortcut and an uninstaller.
- The spec drops ~70 MB the app doesn't use: OpenCV video I/O, opengl32sw,
  Qt virtual keyboard (it pulls in Qt Quick/QML), Qt PDF. If a Qt feature is
  missing in the exe but works in dev, check that DROP list first.
- `"Film Converter.exe" --self-test <roll> <out>` exports the first frame in
  every format plus a sheet and writes `self-test.txt`. Exe output is
  bit-identical to the dev version, and Hebrew paths work.
- Not code-signed: Windows SmartScreen shows "Windows protected your PC" on
  first run ("More info" → "Run anyway").
- Build tools: `requirements-build.txt` (PyInstaller); Inno Setup 6 via
  `winget install JRSoftware.InnoSetup --scope user` (installed on this PC).
- Help menu: keyboard shortcuts (F1) and About (version).

### Stage 4 – macOS version (2026-11-22; CI build passes, not yet tried on a real Mac)
Target: Apple Silicon Macs, macOS 14+ (numpy 2.5 and PySide6 6.12 wheels need
14+; all pinned packages have macOS arm64 wheels, checked with
`pip download --platform macosx_14_0_arm64`). Unsigned (no Apple Developer
account): first launch needs System Settings → Privacy & Security → "Open Anyway"
(`packaging/mac_first_launch.txt` is put into the .dmg).
- PyInstaller can't cross-compile; the Mac app must be built on a Mac.
  `bash tools/build_mac.sh [test roll]` (own `.venv-mac`): tests → PyInstaller
  `.app` → `--smoke-test` of the built app → `.dmg` in `build/installer/`.
- `.github/workflows/build-mac.yml` runs that script on a `macos-15` runner (macos-14 is retired)
  (manual run or `v*` tag) and uploads the .dmg. The user will create a new
  GitHub account `shmengel`: private repo `shmengel/film-converter`, remote
  over HTTPS (this PC's SSH key belongs to the old account `yoav-hue`).
  First run passed (tests, smoke test on darwin) in ~1 min; .dmg is 101 MB.
- `app.py --smoke-test <out>`: no RAWs needed. Loads LibRaw, converts a
  synthetic negative to every format + sheet, opens the window off screen.
  Passes on Windows (dev and built exe).
- Spec: one file for both OSes. Windows keeps the DROP list. On macOS
  nothing is dropped (OpenCV links its video libs directly; Qt frameworks are
  signed folders). `BUNDLE` adds Info.plist: bundle id
  `com.yoavengel.filmconverter` (never change it), RAW "Open With",
  HiDPI. Icon `filmconv_gui/icon.icns` comes from `tools/make_icon.py`.
- Code: `app.py` handles Qt FileOpen events (Finder "Open With" or a drop on
  the Dock icon). `widgets.keys_text()` shows ⌘/⇧⌘ instead of Ctrl in labels
  and help on macOS (Qt already maps Ctrl shortcuts to Cmd). File-dialog
  filters list `.nef` and `.NEF` on macOS (case-sensitive there). The contact
  sheet font falls back to Arial / Helvetica Neue on macOS.
- Expect the first real Mac build to need small fixes (it has never run).
  Retina: previews are 1600 px, so a full-screen preview on a 2x display is
  slightly upscaled. Raise `PREVIEW_MAX_SIZE` only if it looks soft.

### Licences (2026-11-22)
Before sharing installers publicly: audited what ships. All dependencies are
permissive (MIT/BSD/Apache/PSF) except Qt + PySide6 (LGPL-3.0), LibRaw
(LGPL-2.1/CDDL; rawpy built without the GPL demosaic packs) and FFmpeg inside
OpenCV (LGPL-2.1). Our code and icon are original; nothing is taken from
Negative Lab Pro, darktable/negadoctor or RawTherapee (only the textbook idea
D = log10(base/T), mentioned in a comment in `film_types.py`).
- `packaging/licenses/` (THIRD_PARTY_NOTICES.txt + LGPL/GPL v3 texts) and each
  package's own licence files are bundled into a `licenses` folder by the
  spec. Qt's commercial licence text is skipped. Help → Open-source licences
  opens it. Update the versions in THIRD_PARTY_NOTICES.txt when bumping
  requirements.txt.
- Qt Virtual Keyboard is GPL-3.0 only: dropped on both OSes. `build_mac.sh`
  fails if it reappears or the licences are missing.
- Not legal advice; the user was told so.

### How-it-works document (2026-11-22)
`docs/HOW_IT_WORKS.md`: plain-language explanation of every step plus a
limitations section, for users. Keep it in sync when the algorithms change.
It is bundled into the app (Help → How it works renders it with
QTextBrowser.setMarkdown, minus the Mermaid diagram and contents list), put
into the .dmg as "How it works.md", and **must be attached to every GitHub
Release** (the user wants people with only release access to be able to
read it). If a public releases-only repo is created, use it as that repo's
README too.

### Pre-MVP review fixes (2026-11-22)
- CLI: each frame now gets its own copy of the settings, so the upright guess
  and auto crop are per frame (before, frame 1's guess was applied to the whole
  roll). The film base is still taken from the first frame; `--roll-levels`
  also carries its levels. An explicit `--rotate` (including 0) is never
  overridden by the guess.
- Output names: two RAWs with the same stem (DSC_1.NEF + DSC_1.DNG) export as
  `DSC_1_NEF.jpg` / `DSC_1_DNG.jpg` (`Roll.output_stem`); unique names are unchanged.
- GUI: asks before replacing files from an earlier export; quitting during an
  export waits for the frame being written; the preview cache keeps at most
  `CACHE_FRAMES` (40) frames, least recently shown dropped first.
- Undo (Ctrl/⌘+Z, Edit menu): up to 50 steps of per-frame settings snapshots.
  One slider drag = one step. Covers sliders, rotate/flip, crop, base pick,
  auto crop/base/balance, reset, paste/apply to all, channel, base-is-black.
  No redo yet.
- The sharpening slider is labelled "Export sharpening": 1 px at full
  resolution can't show on the 1/4-size preview.
- `tests/test_gui.py`: offscreen MainWindow tests with synthetic previews.
  They patch QMessageBox (modal dialogs would hang). `tests/test_cli.py`: CLI.
- Version 0.3.0. Releasing: bump `filmconv.__version__` in the PR. On merge to
  master, the "Build macOS app" workflow sees a version with no release yet
  (drafts count), builds and tests, and creates a DRAFT GitHub Release
  `vX.Y.Z` with the .dmg and HOW_IT_WORKS.md. Publishing it on GitHub creates
  the tag. Merges that keep a released version skip the Mac build.
  The Windows installer is still built by hand (`tools\build.ps1`) and can be
  added to the draft with `gh release upload vX.Y.Z <installer.exe>`.

### Working notes for future sessions
- GUI layout: `filmconv_gui/main_window.py` (window, modes positive /
  negative / crop / base, jobs), `widgets.py` (ImageView with crop editor,
  FilmStrip, histogram), `export_dialog.py`. Per-frame state lives in
  `Roll.frames[name]` (a `Settings`). `self.settings` is the current frame.
- Headless GUI checks: drive `MainWindow` from a script with PySide6 (open a
  copy of a few NEFs, pump events, call methods, `grab()` screenshots).
  Monkeypatch `QMessageBox.exec`/`critical`, or modal dialogs hang the
  script. Set `PYTHONIOENCODING=utf-8` (●/✓ in labels break the cp1252
  console). Qt shortcuts don't fire in headless runs (the window is never
  active), which is one more reason single keys go through the event filter.
- Windows shell: don't put `
` inside Python strings written through a bash
  heredoc (it became a real newline twice). Edit the file directly instead.
  Never `taskkill` all python.exe processes. Find the app's own process by
  its command line (`app.py`).
- `session1/` holds hard links to the user's originals: read-only.

### Next steps
1. User is testing the full workflow on real rolls; then their dad tries it.
2. Dad tries the installer (0.2.0); collect his feedback.
3. The user is replacing the light source (current one: steady but uneven,
   needs 1/2 s exposures). With the new light, re-measure sharpness (hole-edge
   width) and recheck auto-crop and balance before tuning defaults or adding
   flat-field correction.
4. Same-levels-for-roll mode must handle the frame-to-frame base variation.
5. macOS: try the .dmg on a real Mac (first launch, real roll, export,
   Cmd shortcuts, Retina sharpness).
6. Later: presets per film stock, watch folder, portrait (90 degree) upright
   detection, 120/6x6 frame detection (no sprocket holes; needs another
   approach).
