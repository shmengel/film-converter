"""Finding things on the scanned strip: sprocket holes, film base, frame edges.

Works on the downscaled mono preview (transmission, 0..1). Assumes one
frame per shot with the strip running roughly along the image's long side,
which is how the scanning rig is set up. Every function returns None when it
is not confident, so callers can fall back to a manual pick.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

CLEAR_DENSITY = 0.08      # density above base still counted as "clear film"
MIN_CLEAR_RUN = 0.006     # a gap/rebate must be at least this wide (fraction of size)
CROP_INSET = 0.01         # pull the crop 1% inside the detected edges (frames are rarely exactly 24x36)
# 35 mm film geometry (ISO 1007 / Kodak KS perforations)
PERF_PITCH_MM = 4.75      # hole to hole along the strip
FRAME_MM = (24.0, 36.0)   # image area across x along the strip
HOLE_SPAN_MM = 25.3       # between the inner edges of the two hole rows (measured)
REBATE_MM = 0.45          # clear strip sampled next to the holes (rebate is ~0.65 mm)


@dataclass
class Hole:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Strip:
    """Sprocket holes split into the two rows along the strip edges."""
    horizontal: bool          # True: strip runs left-right, holes at top/bottom
    near: list[Hole]          # top row (or left column if vertical)
    far: list[Hole]           # bottom row (or right column)


def find_holes(working: np.ndarray) -> list[Hole]:
    """Bright, hole-sized, mostly rectangular blobs = light through sprocket holes."""
    h, w = working.shape
    thr = 0.5 * float(np.percentile(working, 99.9))
    mask = (working > thr).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    holes = []
    small, large = 0.012 * max(h, w), 0.08 * max(h, w)
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if small < bw < large and small < bh < large and area > 0.6 * bw * bh:
            holes.append(Hole(x, y, bw, bh))
    return holes


def find_strip(working: np.ndarray) -> Strip | None:
    holes = find_holes(working)
    if len(holes) < 3:
        return None
    h, w = working.shape
    ys = np.array([o.cy for o in holes]) / h
    xs = np.array([o.cx for o in holes]) / w
    # Along the strip, hole centres are spread evenly (small gaps); across it
    # they bunch into one or two tight groups (one big gap). "Spread minus the
    # largest gap" is large only for the along-the-strip axis.
    horizontal = _along(xs) >= _along(ys)
    pos = ys if horizontal else xs
    near = [o for o, p in zip(holes, pos) if p < 0.5]
    far = [o for o, p in zip(holes, pos) if p >= 0.5]
    return Strip(horizontal, near, far)


def estimate_base(working: np.ndarray, strip: Strip | None = None) -> float | None:
    """Film base transmission from the clear rebate between neighbouring holes."""
    strip = strip or find_strip(working)
    if strip is None:
        return None
    img = working if strip.horizontal else working.T
    samples = []
    for row in (strip.near, strip.far):
        holes = sorted((_t(o, strip.horizontal) for o in row), key=lambda o: o.x)
        for a, b in zip(holes, holes[1:]):
            gap = b.x - (a.x + a.w)
            if not (0.3 * a.w < gap < 2.5 * a.w):
                continue  # not neighbours (a hole is missing / not detected)
            mx, my = max(2, gap // 5), max(2, a.h // 4)
            patch = img[a.y + my:a.y + a.h - my, a.x + a.w + mx:b.x - mx]
            if patch.size:
                samples.append(float(np.median(patch)))
    if len(samples) < 2:
        return None
    return float(np.median(samples))


def pixels_per_mm(strip: Strip) -> float | None:
    """Scale from the sprocket-hole pitch (4.75 mm on all 35 mm film)."""
    pitches = []
    for row in (strip.near, strip.far):
        along = np.sort([o.cx if strip.horizontal else o.cy for o in row])
        pitches.extend(np.diff(along))
    if len(pitches) < 2:
        return None
    p = np.asarray(pitches)
    med = np.median(p)
    p = p[np.abs(p - med) < 0.25 * med]   # drop gaps where a hole was missed
    return float(np.median(p)) / PERF_PITCH_MM if p.size else None


def detect_crop(working: np.ndarray, base: float,
                strip: Strip | None = None) -> tuple[float, float, float, float] | None:
    """Normalized (x0, y0, x1, y1) of the image area of the 35 mm frame
    nearest the middle, or None if the strip or its scale can't be found.

    Across the strip the frame position is fixed by the film's geometry
    (24 mm image centred between the hole rows). Along the strip the frame
    ends at the clear gap to the next frame, or where the holder covers it."""
    strip = strip or find_strip(working)
    if strip is None or not (strip.near or strip.far):
        return None
    ppm = pixels_per_mm(strip)
    if ppm is None:
        return None
    hz = strip.horizontal
    img = working if hz else working.T
    H, W = img.shape
    near = [_t(o, hz) for o in strip.near]
    far = [_t(o, hz) for o in strip.far]
    half = FRAME_MM[0] / 2 * ppm
    if near and far:
        lo = np.median([o.y + o.h for o in near])
        hi = np.median([o.y for o in far])
        centre = (lo + hi) / 2
    elif near:
        lo = np.median([o.y + o.h for o in near])
        centre = lo + HOLE_SPAN_MM / 2 * ppm
    else:
        hi = np.median([o.y for o in far])
        centre = hi - HOLE_SPAN_MM / 2 * ppm
    y0, y1 = int(round(centre - half)), int(round(centre + half))

    # Per-column clear-film reference from the rebate bands (follows light
    # fall-off toward the edges), and the image density relative to it.
    reb = max(int(REBATE_MM * ppm), 3)
    bands = []
    if near:
        bands.append(img[int(lo) + 1:int(lo) + reb])
    if far:
        bands.append(img[int(hi) - reb:int(hi) - 1])
    bands = [b for b in bands if b.shape[0] >= 2]
    ref = np.median(np.vstack(bands), axis=0) if bands else np.full(W, base)
    # Light fall-off is smooth; a wide median removes edge-printing letters.
    ref = _median1d(ref, max(3, int(3 * ppm) | 1))
    rows = img[max(y0, 0) + 2 * reb:min(y1, H) - 2 * reb]
    d = np.log10(np.maximum(ref, 1e-6) / np.maximum(rows, 1e-6))
    col_stat = np.percentile(d, 75, axis=0)
    covered = _holder_columns(img, near, far, base, max(2, int(MIN_CLEAR_RUN * W)))
    x0, x1 = _best_span(col_stat < CLEAR_DENSITY, covered,
                        max(2, int(MIN_CLEAR_RUN * W)), FRAME_MM[1] * ppm)
    x0, x1 = max(x0, 0), min(x1, W)
    y0, y1 = max(y0, 0), min(y1, H)

    ix, iy = CROP_INSET * W, CROP_INSET * H
    rect = ((x0 + ix) / W, (y0 + iy) / H, (x1 - ix) / W, (y1 - iy) / H)
    if not hz:
        rect = (rect[1], rect[0], rect[3], rect[2])
    return tuple(float(v) for v in rect)


def frame_aspect(rect, shape) -> float:
    x0, y0, x1, y1 = rect
    a = (x1 - x0) * shape[1] / max((y1 - y0) * shape[0], 1e-6)
    return max(a, 1 / a)


# --- helpers -------------------------------------------------------------------
def _along(pos: np.ndarray) -> float:
    s = np.sort(pos)
    return float(np.ptp(s) - np.max(np.diff(s), initial=0.0))


def _t(o: Hole, horizontal: bool) -> Hole:
    """Hole in the coordinates of the (possibly transposed) strip image."""
    return o if horizontal else Hole(o.y, o.x, o.h, o.w)


def _median1d(v: np.ndarray, k: int) -> np.ndarray:
    pad = np.pad(v, k // 2, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(pad, k), axis=1)


def _holder_columns(img, near, far, base, min_run) -> np.ndarray:
    """Columns where the holder hides the film. Uses the whole sprocket-hole
    band: wherever film is visible, the clear rebate between holes (and the
    holes) make that band bright; under the holder all of it is dark."""
    H, W = img.shape
    dark = np.ones(W, bool)
    for row in (near, far):
        if not row:
            continue
        top = int(np.median([o.y for o in row]))
        bot = int(np.median([o.y + o.h for o in row]))
        band = img[max(top, 0):min(bot, H)]
        if band.shape[0] >= 2:
            dark &= np.percentile(band, 90, axis=0) < 0.5 * base
    if not (near or far):
        dark[:] = False
    # ignore specks: only runs of meaningful width count
    out = np.zeros(W, bool)
    for a, b in _runs(dark):
        if b - a >= min_run:
            out[a:b] = True
    return out


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) of runs of True, end exclusive."""
    m = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _best_span(clear: np.ndarray, covered: np.ndarray, min_run: int,
               length: float) -> tuple[float, float]:
    """Choose the frame's two ends along the strip.

    Candidates for an end are clear gaps between frames ("closed" ends) and
    the place where the holder or the photo edge cuts the strip ("open" ends:
    the frame may continue beyond it). Picks the pair whose distance best
    matches the known frame length, preferring closed ends. Bright parts of
    the picture can look like a gap, but rarely at the right distance."""
    n = len(clear)
    gaps = [(a, b) for a, b in _runs(clear & ~covered) if b - a >= min_run]
    cov = _runs(covered)
    lefts = [(b, True) for a, b in gaps] + [(b, False) for a, b in cov if a == 0 or b < n] + [(0, False)]
    rights = [(a, True) for a, b in gaps] + [(a, False) for a, b in cov if a > 0] + [(n, False)]
    best, best_score = (0.0, float(n)), float("inf")
    for L, l_closed in lefts:
        for R, r_closed in rights:
            span = R - L
            if span < 0.5 * length or span > 1.3 * length:
                continue
            if covered[L:R].mean() > 0.05:
                continue
            if l_closed and r_closed:
                score = abs(span - length)
            else:
                # an open end may hide part of the frame: only too long is wrong
                score = max(0.0, span - length) + 0.03 * length * (2 - l_closed - r_closed)
                score += 0.5 * max(0.0, length - span) * (l_closed + r_closed == 2)
            if score < best_score:
                best, best_score = (float(L), float(R)), score
    L, R = best
    if R - L > length * 1.04:           # too long: trim from the open side
        if any(L == g[1] for g in gaps):
            R = L + length
        elif any(R == g[0] for g in gaps):
            L = R - length
        else:
            mid = (L + R) / 2
            L, R = mid - length / 2, mid + length / 2
    return L, R
