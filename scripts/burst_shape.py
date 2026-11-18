#!/usr/bin/env python3
"""Burst shape of every detected transient in the seated sessions.

For each transient: peak height, how long the envelope stays above 3 MAD
around the peak (searching up to 3 s each way), and how many detected
transients fall inside that stretch.

Two MAD scales are reported, because the answer depends on the choice:
  - background: median and MAD of envelope samples more than 2 s from any
    detected transient, as in scripts/threshold_placement.py (primary);
  - detector: median and MAD of the whole envelope, the scale the detector
    thresholds at 8.

Output: results/burst_shape.json.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chest_imu_cough import detect, io, shape
from chest_imu_cough.features import QUIET_EXCLUSION_S

SEARCH_S = 3.0
COUGH_SCALE_MAD = 50.0
FS = io.SAMPLE_RATE_HZ


def far_from(t, events, distance):
    if events.size == 0:
        return np.ones(t.size, bool)
    return np.min(np.abs(t[:, None] - events[None, :]), axis=1) > distance


def spread(v):
    v = np.asarray(v, float)
    if v.size == 0:
        return None
    return {"n": int(v.size), "min": float(v.min()), "median": float(np.median(v)), "max": float(v.max())}


def measure(name: str) -> dict:
    s = io.load_session(ROOT / "data/sessions" / f"{name}.zip")
    env = detect.envelope(s.acc, FS)
    ev = detect.detect_events(s, FS)
    scales = {"background": shape.mad_scale(env, far_from(s.t, ev, QUIET_EXCLUSION_S)),
              "detector": shape.mad_scale(env)}
    rows = []
    for e in ev:
        row = {"t_s": float(e - s.t[0])}
        for scale, z in scales.items():
            b = shape.burst(z, s.t, ev, e, FS, SEARCH_S, SEARCH_S)
            row[scale] = {k: b[k] for k in ("height", "duration_s", "n_peaks", "cut_by_search_limit")}
        rows.append(row)
    return {"is_cough_session": s.is_cough, "transients": rows}


def summarise(rows, scale):
    d = [r[scale]["duration_s"] for r in rows]
    big = [r for r in rows if r[scale]["height"] >= COUGH_SCALE_MAD]
    return {
        "duration_s": spread(d),
        "n_with_more_than_one_peak": int(sum(r[scale]["n_peaks"] > 1 for r in rows)),
        "n_cut_by_search_limit": int(sum(r[scale]["cut_by_search_limit"] for r in rows)),
        "cough_scale": {
            "n": len(big),
            "duration_s": [round(r[scale]["duration_s"], 2) for r in big],
            "n_peaks": [r[scale]["n_peaks"] for r in big],
            "height": [round(r[scale]["height"], 1) for r in big],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    per = {n: measure(n) for n in io.SEATED}
    report = {"settings": {"burst_level_mad": shape.BURST_LEVEL_MAD, "search_s_each_way": SEARCH_S,
                           "cough_scale_mad": COUGH_SCALE_MAD, "band_hz": list(detect.BAND_HZ),
                           "threshold_mad": detect.THRESHOLD_MAD, "refractory_s": detect.MIN_SEPARATION_S},
              "sessions": {}, "groups": {}}
    for n, d in per.items():
        report["sessions"][n] = {**d, "summary": {sc: summarise(d["transients"], sc)
                                                  for sc in ("background", "detector")}}

    groups = {
        "natural_cough_sitting": ["cough_natural_01_sitting", "cough_natural_02_sitting"],
        "all_seated_cough": [n for n in io.SEATED if n.startswith("cough")],
        "talking": ["baseline_confound_01_talking"],
        "throat_clearing": ["baseline_confound_02_throatclear"],
    }
    for g, names in groups.items():
        rows = [r for n in names for r in per[n]["transients"]]
        report["groups"][g] = {sc: summarise(rows, sc) for sc in ("background", "detector")}

    for sc in ("background", "detector"):
        print(f"\nScale: {sc} MAD. Burst = envelope above {shape.BURST_LEVEL_MAD:g} MAD, "
              f"searched up to {SEARCH_S:g} s each way.")
        print(f"{'session':34s} {'n':>3s} {'duration s (min / median / max)':>32s} "
              f"{'>1 peak':>7s} {'cut':>4s}")
        for n in io.SEATED:
            sm = report["sessions"][n]["summary"][sc]
            dd = sm["duration_s"]
            print(f"{n:34s} {dd['n']:3d} {dd['min']:10.2f} / {dd['median']:5.2f} / {dd['max']:5.2f}      "
                  f"{sm['n_with_more_than_one_peak']:7d} {sm['n_cut_by_search_limit']:4d}")
        print(f"\n  transients at {COUGH_SCALE_MAD:g} MAD or more:")
        for g in ("natural_cough_sitting", "talking"):
            cs = report["groups"][g][sc]["cough_scale"]
            print(f"  {g:22s} n={cs['n']:2d}  durations {cs['duration_s']}")
            print(f"  {'':22s}       peaks in burst {cs['n_peaks']}")
            print(f"  {'':22s}       heights {cs['height']}")

    (args.out / "burst_shape.json").write_text(json.dumps(report, indent=2))
    print(f"\nwritten to {args.out / 'burst_shape.json'}")


if __name__ == "__main__":
    main()
