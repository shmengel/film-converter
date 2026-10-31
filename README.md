# Film Converter

Converts RAW (NEF) scans of B&W film negatives into balanced positives.

## Setup (once)
```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run
- GUI: `.venv\Scripts\python app.py` (optionally pass a .NEF path)
- Command line: `.venv\Scripts\python -m filmconv.cli <files or roll folder> -o output --format tiff jpeg`
- Tests: `.venv\Scripts\python -m pytest`

## Layout
- `filmconv/` – processing core, no Qt (settings, RAW reading, film-type stage, tone stage, export, CLI)
- `filmconv_gui/` – PySide6 GUI
- `samples/` – your test NEFs (read-only, not in git); `output/` – test results (not in git)
