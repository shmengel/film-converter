"""A roll = one folder of RAW scans, with settings per frame.

Per-frame settings live in a small JSON file in the roll folder, so edits
survive closing the app. The RAW files themselves are never modified.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import contact_sheet, export, pipeline, raw_io
from .settings import ADJUSTMENTS, Settings

ROLL_FILE = "film-converter.json"
ROLL_VERSION = 1


@dataclass
class Roll:
    folder: Path
    files: list[Path] = field(default_factory=list)
    frames: dict[str, Settings] = field(default_factory=dict)
    output_dir: Path | None = None
    formats: list[str] = field(default_factory=lambda: ["jpeg"])
    contact_sheet: bool = False

    @classmethod
    def open(cls, folder: str | Path) -> "Roll":
        folder = Path(folder)
        roll = cls(folder, raw_io.list_raw_files(folder))
        roll.frames = {p.name: Settings() for p in roll.files}
        roll.output_dir = folder / "positives"
        roll._load()
        return roll

    # --- persistence -------------------------------------------------------
    @property
    def settings_file(self) -> Path:
        return self.folder / ROLL_FILE

    def _load(self) -> None:
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for name, d in data.get("frames", {}).items():
            if name in self.frames:
                try:
                    self.frames[name] = Settings.from_dict(d)
                except (TypeError, ValueError):
                    pass  # a damaged entry just falls back to defaults
        if data.get("output_dir"):
            self.output_dir = Path(data["output_dir"])
        if data.get("formats"):
            self.formats = [f for f in data["formats"] if f in export.FORMATS] or self.formats
        self.contact_sheet = bool(data.get("contact_sheet", False))

    def save(self) -> bool:
        """Write the roll file (atomically). Returns False if the folder is
        read-only; the app keeps working, edits just aren't remembered."""
        data = {
            "version": ROLL_VERSION,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "formats": self.formats,
            "contact_sheet": self.contact_sheet,
            "frames": {name: s.to_dict() for name, s in self.frames.items()},
        }
        tmp = self.settings_file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            os.replace(tmp, self.settings_file)
            return True
        except OSError:
            return False

    # --- frames ------------------------------------------------------------
    def path(self, name: str) -> Path:
        return self.folder / name

    def names(self) -> list[str]:
        return [p.name for p in self.files]

    def number(self, name: str) -> int:
        """1-based position of a frame in the roll."""
        return self.names().index(name) + 1

    def apply_adjustments(self, source: Settings, names: list[str]) -> None:
        """Copy the slider values (the 'look') to other frames. Crop, rotation,
        film base and auto values stay per frame."""
        for name in names:
            dst = self.frames[name]
            for key in ADJUSTMENTS:
                setattr(dst, key, getattr(source, key))


def analyze(path: str | Path, settings: Settings) -> "object":
    """Load the preview and fill settings.auto. Returns the working preview."""
    working = pipeline.to_working(raw_io.load_preview(path), settings)
    pipeline.update_auto(working, settings)
    return working


def export_frames(roll: Roll, names: list[str], out_dir: Path, formats: list[str],
                  sheet: bool = False,
                  progress: Callable[[int, str], None] | None = None,
                  cancelled: Callable[[], bool] | None = None) -> tuple[list[Path], list[str]]:
    """Full-resolution export of the given frames with their own settings.
    Frames never analyzed get their auto values from the preview first, so the
    output always matches what the preview shows. With sheet=True a contact
    sheet of these frames is written too (formats may then be empty).
    Returns (written, errors); progress counts len(names) + 1 steps with a sheet."""
    written, errors, thumbs = [], [], []
    out_dir = Path(out_dir)
    for i, name in enumerate(names):
        if cancelled and cancelled():
            break
        if progress:
            progress(i, name)
        settings = roll.frames[name].copy()
        path = roll.path(name)
        try:
            if settings.auto.d_black is None:
                analyze(path, settings)
                roll.frames[name].auto = settings.auto
                roll.frames[name].rotation = settings.rotation
            positive = pipeline.render_full(path, settings)
            written += pipeline.save_positive(positive, path, out_dir, formats)
            if sheet:
                thumbs.append((f"{roll.number(name)}   {path.stem}", contact_sheet.thumbnail(positive)))
        except Exception as e:  # keep going; report at the end
            errors.append(f"{name}: {e}")
    if sheet and thumbs and not (cancelled and cancelled()):
        if progress:
            progress(len(names), "contact sheet")
        try:
            target = out_dir / (roll.folder.name + contact_sheet.FILE_SUFFIX)
            written.append(contact_sheet.save(target, thumbs, title=roll.folder.name))
        except Exception as e:
            errors.append(f"contact sheet: {e}")
    if progress:
        progress(len(names) + (1 if sheet else 0), "")
    return written, errors
