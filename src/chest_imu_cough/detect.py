"""Transient detection on chest accelerometer magnitude.

The detector reports the time of the actual envelope peak. The earlier
implementation reported a window position instead, which quantised every
event onto a 0.188 s grid; see docs/LABEL_AUDIT.md.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import signal

from .io import SAMPLE_RATE_HZ, Session

BAND_HZ = (10.0, 80.0)      # cough transients; walking and posture live below this
SMOOTH_S = 0.15             # envelope smoothing
MIN_SEPARATION_S = 1.0      # refractory period between events
THRESHOLD_MAD = 8.0         # peak height in median-absolute-deviations


def envelope(x: np.ndarray, fs: float = SAMPLE_RATE_HZ) -> np.ndarray:
    sos = signal.butter(4, BAND_HZ, "bp", fs=fs, output="sos")
    rectified = np.abs(signal.sosfiltfilt(sos, x - x.mean()))
    width = max(int(SMOOTH_S * fs), 1)
    return (
        pd.Series(rectified)
        .rolling(width, center=True)
        .mean()
        .bfill()
        .ffill()
        .to_numpy()
    )


def detect_events(session: Session, fs: float = SAMPLE_RATE_HZ) -> np.ndarray:
    """Return absolute times of detected transients."""
    env = envelope(session.acc, fs)
    baseline = np.median(env)
    mad = np.median(np.abs(env - baseline))
    if mad <= 0:
        return np.empty(0)
    score = (env - baseline) / mad
    peaks, _ = signal.find_peaks(
        score, height=THRESHOLD_MAD, distance=int(MIN_SEPARATION_S * fs)
    )
    return session.t[peaks]
