"""Burst shape around a detected transient.

A burst is the contiguous stretch around a detected peak where the envelope
stays above a level, in MAD units. Its duration, and how many detected
transients fall inside it, describe whether an event is one expulsion or a
train of them.

Used by scripts/burst_shape.py (measurement) and features_shape.py (the
alternative feature set). The published detector and features do not use it.
"""
from __future__ import annotations
import numpy as np

BURST_LEVEL_MAD = 3.0


def mad_scale(env: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Envelope in MAD units. The median and MAD come from env[mask], or from
    the whole envelope when mask is None (the detector's own scale)."""
    ref = env if mask is None else env[mask]
    b = float(np.median(ref))
    m = float(np.median(np.abs(ref - b)))
    return (env - b) / m if m > 0 else np.zeros_like(env)


def stretch(z: np.ndarray, i: int, level: float, lo_limit: int, hi_limit: int) -> tuple[int, int, bool]:
    """Indices [lo, hi] of the run of z > level that contains i, kept inside
    [lo_limit, hi_limit]. The flag is True when a limit cut the run short."""
    lo_limit, hi_limit = max(lo_limit, 0), min(hi_limit, len(z) - 1)
    lo = hi = i
    while lo > lo_limit and z[lo - 1] > level:
        lo -= 1
    while hi < hi_limit and z[hi + 1] > level:
        hi += 1
    cut = (lo == lo_limit and lo > 0 and z[lo - 1] > level) or (
        hi == hi_limit and hi < len(z) - 1 and z[hi + 1] > level)
    return lo, hi, bool(cut)


def burst(z: np.ndarray, t: np.ndarray, events: np.ndarray, t_event: float, fs: float,
          before_s: float, after_s: float, level: float = BURST_LEVEL_MAD) -> dict:
    """Shape of the burst around one detected transient.

    The search runs at most before_s back and after_s forward from the peak.
    Peaks inside the burst are the detected transients (events) whose times fall
    inside it, so they are at least the detector's refractory period apart.
    """
    i = int(np.searchsorted(t, t_event))
    i = min(i, len(z) - 1)
    lo, hi, cut = stretch(z, i, level, i - int(round(before_s * fs)), i + int(round(after_s * fs)))
    inside = np.sort(events[(events >= t[lo]) & (events <= t[hi])])
    half_lo, half_hi, _ = stretch(z, i, z[i] / 2.0, lo, hi)
    duration = (hi - lo + 1) / fs
    half_width = (half_hi - half_lo + 1) / fs
    return {
        "height": float(z[i]),
        "duration_s": float(duration),
        "n_peaks": int(max(len(inside), 1)),
        "median_interval_s": float(np.median(np.diff(inside))) if len(inside) > 1 else 0.0,
        "half_height_width_s": float(half_width),
        "duration_to_half_width": float(duration / half_width),
        "start_t": float(t[lo]),
        "end_t": float(t[hi]),
        "cut_by_search_limit": cut,
    }
