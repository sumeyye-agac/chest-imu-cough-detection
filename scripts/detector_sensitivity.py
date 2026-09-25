#!/usr/bin/env python3
"""How much the detector's settings matter.

The detector has three constants: the band, the peak threshold in
median-absolute-deviations, and the refractory period. Picking them to make the
counts come out right would be fitting, so this sweeps each one and reports how
wide the agreement is.

A count that holds over a wide range of thresholds reflects something in the
signal. A count that only touches the written-down value on its way down as the
threshold rises does not.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chest_imu_cough.io import load_session, STATED_COUNTS, SAMPLE_RATE_HZ
from chest_imu_cough.detect import BAND_HZ, THRESHOLD_MAD, MIN_SEPARATION_S, SMOOTH_S

TOLERANCE = 1  # a count within one event of the written-down number counts as agreeing


def count_events(session, band, threshold, separation, fs=SAMPLE_RATE_HZ) -> int:
    sos = signal.butter(4, band, "bp", fs=fs, output="sos")
    rectified = np.abs(signal.sosfiltfilt(sos, session.acc - session.acc.mean()))
    env = (
        pd.Series(rectified).rolling(max(int(SMOOTH_S * fs), 1), center=True)
        .mean().bfill().ffill().to_numpy()
    )
    base = np.median(env)
    mad = np.median(np.abs(env - base))
    if mad <= 0:
        return 0
    peaks, _ = signal.find_peaks(
        (env - base) / mad, height=threshold, distance=int(separation * fs)
    )
    return len(peaks)


def longest_run(counts, target) -> int:
    best = run = 0
    for c in counts:
        run = run + 1 if abs(c - target) <= TOLERANCE else 0
        best = max(best, run)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/sessions", type=Path)
    ap.add_argument("--out", default="results", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    sessions = {n: load_session(args.data / f"{n}.zip") for n in STATED_COUNTS}
    report = {"defaults": {"band_hz": list(BAND_HZ), "threshold_mad": THRESHOLD_MAD,
                           "refractory_s": MIN_SEPARATION_S}}

    thresholds = list(range(6, 26))
    print("Threshold sweep. Band and refractory period at their defaults.")
    print("A wide stable run means the count is a property of the recording,")
    print("not of the threshold.\n")
    header = " ".join(f"{t:3d}" for t in thresholds)
    print(f"{'session (written down)':40s} {header}   stable run")
    report["threshold_sweep"] = {"thresholds": thresholds, "sessions": {}}
    for name, stated in STATED_COUNTS.items():
        counts = [count_events(sessions[name], BAND_HZ, t, MIN_SEPARATION_S) for t in thresholds]
        run = longest_run(counts, stated)
        report["threshold_sweep"]["sessions"][name] = {
            "written_down": stated, "counts": counts, "stable_run": run
        }
        print(f"{name + f' ({stated})':40s} " + " ".join(f"{c:3d}" for c in counts) + f"   {run}")

    print("\nBand sweep, threshold and refractory period at their defaults.")
    bands = [(5, 80), (8, 80), (10, 60), (10, 80), (10, 100), (15, 80), (20, 80)]
    report["band_sweep"] = {}
    print(f"{'band (Hz)':>12s}  " + "  ".join(f"{n.split('_')[-1][:9]:>9s}" for n in STATED_COUNTS))
    for band in bands:
        counts = {n: count_events(sessions[n], band, THRESHOLD_MAD, MIN_SEPARATION_S)
                  for n in STATED_COUNTS}
        report["band_sweep"][f"{band[0]}-{band[1]}"] = counts
        print(f"{f'{band[0]}-{band[1]}':>12s}  " + "  ".join(f"{counts[n]:9d}" for n in STATED_COUNTS))

    print("\nRefractory sweep, band and threshold at their defaults.")
    report["refractory_sweep"] = {}
    for sep in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        counts = {n: count_events(sessions[n], BAND_HZ, THRESHOLD_MAD, sep) for n in STATED_COUNTS}
        report["refractory_sweep"][str(sep)] = counts
        print(f"{sep:11.2f}s  " + "  ".join(f"{counts[n]:9d}" for n in STATED_COUNTS))

    (args.out / "detector_sensitivity.json").write_text(json.dumps(report, indent=2))
    print(f"\nwritten to {args.out / 'detector_sensitivity.json'}")


if __name__ == "__main__":
    main()
