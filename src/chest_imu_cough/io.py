"""Loading of recorded Movesense sessions."""
from __future__ import annotations
import io, json, zipfile
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

SAMPLE_RATE_HZ = 216.216  # delivered IMU9 rate when subscribed at 208 Hz


@dataclass(frozen=True)
class Session:
    name: str
    t: np.ndarray        # absolute time, seconds (the t_unix column)
    acc: np.ndarray      # accelerometer magnitude, m/s^2
    gyro: np.ndarray     # gyroscope magnitude, deg/s
    meta: dict

    @property
    def is_cough(self) -> bool:
        return self.name.startswith("cough")

    @property
    def duration_s(self) -> float:
        return float(self.t[-1] - self.t[0])


def load_session(path: str | Path) -> Session:
    """Read one session ZIP as produced by the recorder.

    t_unix is used as the time base. It is the only column that is both
    absolute and evenly spaced; see the recorder's data-format notes.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        imu = pd.read_csv(io.BytesIO(z.read("imu.csv")))
        meta = json.loads(z.read("meta.json"))
    acc = np.sqrt(imu.acc_x**2 + imu.acc_y**2 + imu.acc_z**2).to_numpy()
    gyro = np.sqrt(imu.gyro_x**2 + imu.gyro_y**2 + imu.gyro_z**2).to_numpy()
    return Session(path.stem, imu.t_unix.to_numpy(), acc, gyro, meta)


def load_all(directory: str | Path) -> dict[str, Session]:
    return {p.stem: load_session(p) for p in sorted(Path(directory).glob("*.zip"))}


SEATED = [
    "cough_metronomic_01",
    "cough_metronomic_02",
    "cough_natural_01_sitting",
    "cough_natural_02_sitting",
    "baseline_calm_01_sitting",
    "baseline_confound_01_talking",
    "baseline_confound_02_throatclear",
]

# Counts written down during recording, independent of any signal processing.
# Used to check the detector, never to train on.
STATED_COUNTS = {
    "cough_natural_02_sitting": 8,
    "cough_natural_03_standing": 8,
    "cough_natural_04_walking": 9,
    "baseline_confound_02_throatclear": 11,
}
