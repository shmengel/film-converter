from pathlib import Path

import numpy as np

from filmconv import cli, pipeline, raw_io
from test_pipeline import synthetic_negative


def upright_and_upside_down():
    """Two scans whose positives are bright at the top / at the bottom."""
    h, w, base = 200, 300, 0.8
    scene = np.repeat(np.linspace(1.0, 0.0, h - 40, dtype=np.float32)[:, None], w - 40, axis=1)
    frames = {}
    for name, sc in (("_A0001.NEF", scene), ("_A0002.NEF", scene[::-1])):
        img = np.full((h, w), base, np.float32)
        img[20:-20, 20:-20] = base * 10 ** -(0.1 + 1.5 * sc)
        frames[name] = np.repeat(img[..., None], 3, axis=2)
    return frames


def run_cli(tmp_path, monkeypatch, frames, *extra):
    """Runs the CLI on fake RAWs; returns {name: settings used for its export}."""
    used = {}
    monkeypatch.setattr(raw_io, "load_preview", lambda p, *a, **k: frames[Path(p).name])
    monkeypatch.setattr(pipeline, "export_file",
                        lambda p, s, *a, **k: used.__setitem__(Path(p).name, s.copy()) or [])
    for name in frames:
        (tmp_path / name).write_bytes(b"")
    assert cli.main([str(tmp_path / n) for n in frames] + ["-o", str(tmp_path / "out"), *extra]) == 0
    return used


def test_cli_guesses_upright_per_frame(tmp_path, monkeypatch):
    used = run_cli(tmp_path, monkeypatch, upright_and_upside_down())
    assert used["_A0001.NEF"].rotation == 0
    assert used["_A0002.NEF"].rotation == 180


def test_cli_explicit_rotation_wins_over_the_guess(tmp_path, monkeypatch):
    upside_down = {"_A0002.NEF": upright_and_upside_down()["_A0002.NEF"]}
    used = run_cli(tmp_path, monkeypatch, upside_down, "--rotate", "0")
    assert used["_A0002.NEF"].rotation == 0


def test_cli_keeps_first_frames_film_base_for_the_roll(tmp_path, monkeypatch):
    frames = {"_A0001.NEF": synthetic_negative(base=0.8), "_A0002.NEF": synthetic_negative(base=0.5)}
    used = run_cli(tmp_path, monkeypatch, frames)
    assert used["_A0002.NEF"].auto.film_base == used["_A0001.NEF"].auto.film_base
