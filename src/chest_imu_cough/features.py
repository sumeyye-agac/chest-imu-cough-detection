"""Per-event features.

Band energies are expressed relative to the same session's own quiet
background. Without that normalisation the classifier can separate sessions
by their recording block rather than by the events themselves; the seated
cough and confound sessions were recorded in two consecutive blocks, and a
model trained on quiet background alone separates those blocks at AUC 0.64.
"""
from __future__ import annotations
import numpy as np
from scipy import signal

from .io import SAMPLE_RATE_HZ, Session
from .detect import envelope

BANDS_HZ = [(1, 3), (3, 10), (10, 25), (25, 50), (50, 100)]
PRE_S, POST_S = 0.4, 0.6          # window taken around each event
QUIET_EXCLUSION_S = 2.0           # distance from any event for background windows
QUIET_WINDOW_S = 1.0

FEATURE_NAMES = [
    name
    for ch in ("acc", "gyro")
    for name in (
        [f"{ch}_{lo}_{hi}_rel" for lo, hi in BANDS_HZ]
        + [f"{ch}_{lo}_{hi}_frac" for lo, hi in BANDS_HZ]
        + [f"{ch}_centroid", f"{ch}_burst_s"]
    )
]


def _band_energies(w: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    w = w - w.mean()
    f, p = signal.welch(w, fs=fs, nperseg=min(len(w), 128))
    e = np.array([p[(f >= lo) & (f < hi)].sum() for lo, hi in BANDS_HZ])
    return e, f, p


def quiet_baseline(session: Session, events: np.ndarray, fs: float = SAMPLE_RATE_HZ):
    """Median band energies over windows far from any detected event."""
    width = int(QUIET_WINDOW_S * fs)
    acc_e, gyro_e = [], []
    for i in range(0, len(session.t) - width, width):
        centre = session.t[i + width // 2]
        if events.size and np.min(np.abs(events - centre)) < QUIET_EXCLUSION_S:
            continue
        acc_e.append(_band_energies(session.acc[i : i + width], fs)[0])
        gyro_e.append(_band_energies(session.gyro[i : i + width], fs)[0])
    if not acc_e:
        ones = np.ones(len(BANDS_HZ))
        return ones, ones
    return np.median(acc_e, axis=0), np.median(gyro_e, axis=0)


def event_features(session: Session, events: np.ndarray, fs: float = SAMPLE_RATE_HZ) -> np.ndarray:
    ref_acc, ref_gyro = quiet_baseline(session, events, fs)
    rows = []
    for t0 in events:
        mask = (session.t >= t0 - PRE_S) & (session.t <= t0 + POST_S)
        row = []
        for channel, ref in ((session.acc, ref_acc), (session.gyro, ref_gyro)):
            w = channel[mask]
            e, f, p = _band_energies(w, fs)
            total = p.sum() + 1e-12
            row += list(np.log10(e / (ref + 1e-12) + 1e-12))   # relative to this session
            row += list(e / total)                              # spectral shape, scale-free
            row += [float((f * p).sum() / total)]
            env = envelope(w, fs)
            row += [float((env > 0.5 * env.max()).sum()) / fs]  # burst duration
        rows.append(row)
    return np.array(rows) if rows else np.empty((0, len(FEATURE_NAMES)))
