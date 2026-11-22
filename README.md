# Film Converter

**Turn DSLR "scans" of black-and-white film negatives into finished positives, automatically.**

Photograph your negatives with a digital camera, open the folder, and Film
Converter finds each frame, crops it, inverts it and balances the tones. You
only fine-tune the frames you want and export. Free and open source, for
Windows and Mac.

## ⬇️ Download

### **[Get the latest version →](https://github.com/shmengel/film-converter/releases/latest)**

| Your computer | File to download | Needs |
|---|---|---|
| **Windows** | `FilmConverter-Setup-<version>.exe` | Windows 10 or 11, 64-bit |
| **Mac** | `FilmConverter-<version>-mac-arm64.dmg` | Apple Silicon (M1 or newer), macOS 14 Sonoma or newer |

The files are under **Assets** at the bottom of the release page.
[All versions](https://github.com/shmengel/film-converter/releases)

### Installing

**Windows:** run the Setup file. Windows may show *"Windows protected your
PC"*, because the app isn't signed with a paid certificate. Click **More info**
→ **Run anyway**. No administrator rights are needed.

**Mac:** open the `.dmg` and drag **Film Converter** into **Applications**.
The first time you open it, macOS blocks it, because the app isn't registered
with Apple. Click **Done**, then go to **System Settings → Privacy & Security**,
scroll down and click **Open Anyway**. This is needed only once. The `.dmg`
contains step-by-step instructions.

## What it does

- **Open a whole roll at once:** pick any scan in a folder; every RAW file
  in it appears in a film strip.
- **Automatic per frame:** finds the frame using the sprocket holes and crops
  away the border, then inverts using the film base and balances black, white
  and midtones. Upside-down frames are turned upright.
- **Your adjustments:** exposure, contrast, highlights, shadows, whites,
  blacks and sharpening; crop, rotate and flip. Copy and paste settings
  between frames, or apply them to the whole roll.
- **Export:** JPEG, 16-bit or 8-bit TIFF, PNG, and a contact sheet of the roll.
- **Non-destructive:** your RAW files are never changed.
- Works with RAW files from most cameras (Nikon, Canon, Sony, Fujifilm,
  Olympus, Panasonic, Pentax, DNG).

Black-and-white **35 mm** film is supported now. Colour negatives and
automatic cropping for 120 film are planned.

## How it works

**[How Film Converter works →](docs/HOW_IT_WORKS.md)**: a plain-language
explanation of every step (finding the frame, inverting, balancing) and its
limitations, with tips for scans that convert well. The same text is in the
app under **Help → How it works**, and attached to every release.

## Quick start

1. Photograph your negatives in RAW: one frame per shot, with **both rows of
   sprocket holes** and a bit of clear film between frames visible, and the
   same manual exposure for the whole roll.
2. Open Film Converter, press **Ctrl+O** (**⌘O** on Mac) and pick any scan in
   the folder.
3. Browse the frames, adjust what you like (hold **B** to see the negative),
   then **Export** (Ctrl+E / ⌘E).

**Help → Keyboard shortcuts** lists all the keys.

---

## For developers

The app is written in Python: PySide6 (Qt) for the window, rawpy (LibRaw) to
read RAW files, and NumPy / OpenCV for the processing.

### Run from source

```
py -3.12 -m venv .venv                          # macOS: python3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py                     # the app
.venv\Scripts\python -m filmconv.cli <files or roll folder> -o output --format tiff jpeg
.venv\Scripts\python -m pytest                  # tests (synthetic negatives, no RAWs needed)
```

### Build the installers

- **Windows:** `powershell -ExecutionPolicy Bypass -File tools\build.ps1 [-TestRoll <folder>]`
  (needs Inno Setup 6) → `build\installer\FilmConverter-Setup-<version>.exe`
- **Mac:** must be built on a Mac: `bash tools/build_mac.sh` → a `.dmg` in
  `build/installer/`. Or let GitHub build it: run the **Build macOS app**
  workflow from the Actions tab (or push a tag like `v0.2.1`); the `.dmg` is
  under the run's Artifacts.

### Code layout

| Folder | Contents |
|---|---|
| `filmconv/` | Processing core, no GUI code: RAW reading, frame detection, inversion, tone, export, command line |
| `filmconv_gui/` | The PySide6 app |
| `tests/` | pytest tests |
| `docs/` | User documentation |
| `packaging/`, `tools/` | Installer builds, licence notices |

`CLAUDE.md` holds the full design notes and project history.

## Licence

Film Converter is released under the [MIT licence](LICENSE). The installers
include open-source components under their own licences (Qt / PySide6 and
LibRaw under the LGPL, among others). See
[THIRD_PARTY_NOTICES.txt](packaging/licenses/THIRD_PARTY_NOTICES.txt).
