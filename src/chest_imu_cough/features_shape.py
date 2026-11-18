"""Alternative feature set: the published features plus burst shape.

Not the published configuration. The published features stay in features.py
and are used unchanged by run_analysis.py and run_epfl.py.

Added per transient, on the detector's own MAD scale (whole-recording median
and MAD, the scale the detector thresholds at 8):
  - burst duration: time the envelope stays above 3 MAD around the peak
  - number of detected transients inside that burst
  - median interval between them (0 when there is one)
  - burst duration divided by the main peak's width at half its height

The burst search is limited to the feature window, so the window decides the
longest burst that can be seen. The published features are computed over the
same window.
"""
from __future__ import annotations
import numpy as np

from . import detect, shape
from .features import FEATURE_NAMES, event_features
from .io import SAMPLE_RATE_HZ, Session

PUBLISHED_WINDOW = (0.4, 0.6)
WINDOWS = [(0.4, 0.6), (0.5, 2.0), (1.0, 2.5)]
SHAPE_NAMES = ["burst_duration_s", "burst_n_peaks", "burst_median_interval_s", "burst_to_half_width"]
FEATURE_NAMES_SHAPE = FEATURE_NAMES + SHAPE_NAMES


def shape_features(session: Session, events: np.ndarray, fs: float = SAMPLE_RATE_HZ,
                   pre_s: float = PUBLISHED_WINDOW[0], post_s: float = PUBLISHED_WINDOW[1]) -> np.ndarray:
    """Burst-shape columns only, one row per event."""
    if events.size == 0:
        return np.empty((0, len(SHAPE_NAMES)))
    z = shape.mad_scale(detect.envelope(session.acc, fs))
    rows = []
    for t0 in events:
        b = shape.burst(z, session.t, events, t0, fs, pre_s, post_s)
        rows.append([b["duration_s"], b["n_peaks"], b["median_interval_s"], b["duration_to_half_width"]])
    return np.array(rows, float)


def event_features_shape(session: Session, events: np.ndarray, fs: float = SAMPLE_RATE_HZ,
                         pre_s: float = PUBLISHED_WINDOW[0], post_s: float = PUBLISHED_WINDOW[1]) -> np.ndarray:
    base = event_features(session, events, fs, pre_s=pre_s, post_s=post_s)
    if events.size == 0:
        return np.empty((0, len(FEATURE_NAMES_SHAPE)))
    return np.hstack([base, shape_features(session, events, fs, pre_s, post_s)])
