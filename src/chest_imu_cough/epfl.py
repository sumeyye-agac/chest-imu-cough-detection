"""Loader for the EPFL edge-AI cough dataset (Zenodo 7562332).

Returns the same Session shape as io.load_session, so the existing detector and
features run unchanged. Format source: EPFL's own loader, see docs/EPFL_DATASET.md.

Layout, below the extracted public_dataset/ folder:
    <subject>/trial_<n>/mov_<sit|walk>/background_noise_<...>/<class>/imu.csv
    ground_truth.json next to imu.csv, cough recordings only.
"""
from __future__ import annotations
import contextlib, json
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

from . import detect
from .io import Session

EPFL_ROOT = Path("data/external/epfl/extracted/public_dataset")
SAMPLE_RATE_HZ = 100.0
BAND_HZ = (10.0, 45.0)   # 10-80 Hz is above Nyquist (50 Hz) at this rate
CONFOUND_CLASSES = ("laugh", "throat_clearing", "deep_breathing")
ACC_COLS = ["Accel x", "Accel y", "Accel z"]
GYRO_COLS = ["Gyro Y", "Gyro P", "Gyro R"]


@dataclass(frozen=True)
class Recording:
    path: Path          # the directory holding imu.csv
    subject: str
    trial: str
    movement: str       # "sit" or "walk"
    noise: str          # background_noise_<...> without the prefix
    cls: str            # cough, laugh, throat_clearing, deep_breathing

    @property
    def name(self) -> str:
        return f"{self.subject}/{self.trial}/{self.movement}/{self.noise}/{self.cls}"


def list_recordings(root: str | Path = EPFL_ROOT) -> list[Recording]:
    root = Path(root)
    out = []
    for f in sorted(root.glob("*/trial_*/mov_*/background_noise_*/*/imu.csv")):
        subject, trial, mov, noise, cls = f.relative_to(root).parts[:-1]
        out.append(Recording(f.parent, subject, trial, mov.removeprefix("mov_"),
                             noise.removeprefix("background_noise_"), cls))
    return out


def load_recording(rec: Recording) -> Session:
    """IMU as magnitudes. Time comes from the sample index at 100 Hz."""
    imu = pd.read_csv(rec.path / "imu.csv")
    acc = np.linalg.norm(imu[ACC_COLS].to_numpy(dtype=float), axis=1)
    gyro = np.linalg.norm(imu[GYRO_COLS].to_numpy(dtype=float), axis=1)
    t = np.arange(len(imu)) / SAMPLE_RATE_HZ
    meta = {"subject": rec.subject, "trial": rec.trial, "movement": rec.movement,
            "noise": rec.noise, "class": rec.cls}
    return Session(rec.name, t, acc, gyro, meta)


def load_coughs(rec: Recording) -> tuple[np.ndarray, np.ndarray]:
    """Annotated cough start and end times in seconds (from audio)."""
    d = json.loads((rec.path / "ground_truth.json").read_text())
    return np.asarray(d["start_times"], float), np.asarray(d["end_times"], float)


@contextlib.contextmanager
def detector_settings(band=BAND_HZ, threshold=None, separation=None):
    """Run the published detector with different constants, then restore them.

    detect.envelope and detect.detect_events read their constants from module
    globals at call time, so this changes the settings without a second copy of
    the detector. features.event_features calls detect.envelope, so it picks up
    the band as well.
    """
    saved = (detect.BAND_HZ, detect.THRESHOLD_MAD, detect.MIN_SEPARATION_S)
    detect.BAND_HZ = tuple(band)
    if threshold is not None:
        detect.THRESHOLD_MAD = threshold
    if separation is not None:
        detect.MIN_SEPARATION_S = separation
    try:
        yield
    finally:
        detect.BAND_HZ, detect.THRESHOLD_MAD, detect.MIN_SEPARATION_S = saved
