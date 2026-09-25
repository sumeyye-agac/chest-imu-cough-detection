#!/usr/bin/env python3
"""Seated cough-vs-confound analysis.

Two stages:
  1. detect transients on the chest accelerometer, checked against the counts
     written down during recording;
  2. classify each detected transient as cough or not, where the label comes
     from what the subject was doing in that session, not from the signal.

Only stage 2 is a claim about detection quality. Stage 1 shares its input with
the classifier, so its output is not independent ground truth.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chest_imu_cough.io import load_session, SEATED, STATED_COUNTS, SAMPLE_RATE_HZ
from chest_imu_cough.detect import detect_events
from chest_imu_cough.features import (
    event_features, quiet_baseline, _band_energies, QUIET_EXCLUSION_S, QUIET_WINDOW_S,
)
from chest_imu_cough.evaluate import (
    leave_one_session_out, confusion, session_bootstrap_ci, permutation_null,
    background_artifact_auc,
)


def quiet_windows(session, events, fs=SAMPLE_RATE_HZ):
    width = int(QUIET_WINDOW_S * fs)
    rows = []
    for i in range(0, len(session.t) - width, width):
        centre = session.t[i + width // 2]
        if events.size and np.min(np.abs(events - centre)) < QUIET_EXCLUSION_S:
            continue
        a, f, p = _band_energies(session.acc[i : i + width], fs)
        g, _, _ = _band_energies(session.gyro[i : i + width], fs)
        rows.append(np.concatenate([np.log10(a + 1e-12), np.log10(g + 1e-12)]))
    return np.array(rows) if rows else np.empty((0, 10))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/sessions", type=Path)
    ap.add_argument("--out", default="results", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    sessions = {n: load_session(args.data / f"{n}.zip") for n in SEATED}
    events = {n: detect_events(s) for n, s in sessions.items()}

    print("Stage 1 - transient detection")
    detection = {}
    for n, ev in events.items():
        stated = STATED_COUNTS.get(n)
        detection[n] = {"detected": int(len(ev)), "stated": stated}
        print(f"  {n:34s} detected={len(ev):3d}  written down={stated if stated else '-'}")

    X, y, groups = [], [], []
    for n, s in sessions.items():
        f = event_features(s, events[n])
        X.append(f)
        y.append(np.full(len(f), int(s.is_cough)))
        groups.append(np.full(len(f), n))
    X = np.vstack(X); y = np.concatenate(y); groups = np.concatenate(groups)
    print(f"\n  {len(y)} transients: {int(y.sum())} in cough sessions, "
          f"{int((y == 0).sum())} in confound sessions")

    Xq, yq, gq = [], [], []
    for n, s in sessions.items():
        q = quiet_windows(s, events[n])
        Xq.append(q); yq.append(np.full(len(q), int(s.is_cough))); gq.append(np.full(len(q), n))
    art = background_artifact_auc(np.vstack(Xq), np.concatenate(yq), np.concatenate(gq))

    print("\nStage 2 - classification, leave-one-session-out")
    scores = leave_one_session_out(X, y, groups)
    auc = roc_auc_score(y, scores)
    lo, hi, n_boot = session_bootstrap_ci(y, scores, groups)
    perm_mean, perm_max, _ = permutation_null(X, y, groups)
    cm = confusion(y, scores)

    print(f"  AUC                         {auc:.3f}   95% CI [{lo:.3f}, {hi:.3f}] "
          f"(session-level bootstrap, n={n_boot})")
    print(f"  sensitivity                 {cm['sensitivity']:.3f}")
    print(f"  specificity                 {cm['specificity']:.3f}")
    print(f"  permutation null            mean {perm_mean:.3f}, max {perm_max:.3f}")
    print(f"  quiet-background artifact   {art:.3f}   (0.5 = sessions differ only in their events)")

    print("\n  per session")
    per = {}
    for n in SEATED:
        m = groups == n
        called = float((scores[m] >= 0.5).mean())
        per[n] = {"n_events": int(m.sum()), "is_cough_session": bool(sessions[n].is_cough),
                  "fraction_called_cough": called}
        print(f"    {n:34s} n={m.sum():3d}  called cough {100 * called:3.0f}%")

    (args.out / "results.json").write_text(json.dumps({
        "auc": auc, "auc_ci95": [lo, hi], "n_bootstrap": n_boot,
        "sensitivity": cm["sensitivity"], "specificity": cm["specificity"],
        "precision": cm["precision"], "confusion": cm,
        "permutation_null_mean": perm_mean, "permutation_null_max": perm_max,
        "quiet_background_artifact_auc": art,
        "detection": detection, "per_session": per,
        "n_events": int(len(y)), "n_sessions": len(SEATED),
    }, indent=2))
    print(f"\n  written to {args.out / 'results.json'}")


if __name__ == "__main__":
    main()
