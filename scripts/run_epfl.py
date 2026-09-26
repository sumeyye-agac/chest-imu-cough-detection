#!/usr/bin/env python3
"""The published method on the EPFL cough dataset, seated recordings only.

1. Detector sensitivity at 100 Hz: threshold, band and refractory sweeps.
2. Detection recall against cough labels annotated from audio, per subject.
3. Cough vs. confound classification of detected transients, leave-one-subject-out,
   with detections in cough recordings either restricted to those that hit an
   annotated cough ("matched") or all kept ("all").

The detector, features and evaluation are the published ones, unchanged. The only
setting that differs is the band, 10-45 Hz instead of 10-80 Hz, because the IMU
runs at 100 Hz. Output: results/epfl_results.json.
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from chest_imu_cough import detect, epfl
from chest_imu_cough.features import event_features, QUIET_EXCLUSION_S, QUIET_WINDOW_S
from chest_imu_cough.evaluate import (
    leave_one_session_out, confusion, session_bootstrap_ci, permutation_null,
    background_artifact_auc,
)
from run_analysis import quiet_windows

FS = epfl.SAMPLE_RATE_HZ
HIT_TOLERANCE_S = 0.2


def match(det, starts, ends, tol=HIT_TOLERANCE_S):
    """Maximum one-to-one matching of detections to annotated coughs.

    A detection can hit a cough if it lies in [start - tol, end + tol]. Each
    cough is hit at most once and each detection hits at most one cough.
    Returns boolean arrays: detection matched, cough hit.
    """
    det = np.asarray(det, float)
    lo, hi = np.asarray(starts) - tol, np.asarray(ends) + tol
    if det.size == 0 or lo.size == 0:
        return np.zeros(det.size, bool), np.zeros(lo.size, bool)
    ok = (det[:, None] >= lo[None, :]) & (det[:, None] <= hi[None, :])
    r, c = linear_sum_assignment(-ok.astype(float))
    keep = ok[r, c]
    d_hit, c_hit = np.zeros(det.size, bool), np.zeros(lo.size, bool)
    d_hit[r[keep]] = True
    c_hit[c[keep]] = True
    return d_hit, c_hit


def in_any_window(det, starts, ends, tol=HIT_TOLERANCE_S):
    det = np.asarray(det, float)
    if det.size == 0 or len(starts) == 0:
        return np.zeros(det.size, bool)
    return ((det[:, None] >= np.asarray(starts)[None, :] - tol)
            & (det[:, None] <= np.asarray(ends)[None, :] + tol)).any(axis=1)


def has_quiet_window(session, events) -> bool:
    width = int(QUIET_WINDOW_S * FS)
    for i in range(0, len(session.t) - width, width):
        centre = session.t[i + width // 2]
        if not (events.size and np.min(np.abs(events - centre)) < QUIET_EXCLUSION_S):
            return True
    return False


def spread(values) -> dict:
    v = np.asarray(values, float)
    return {"min": float(v.min()), "q1": float(np.percentile(v, 25)),
            "median": float(np.median(v)), "q3": float(np.percentile(v, 75)),
            "max": float(v.max()), "mean": float(v.mean())}


def recall_table(recs, sessions, coughs, band, threshold, separation):
    """Per-subject annotated coughs, hits and unmatched detections."""
    per = defaultdict(lambda: {"annotated": 0, "hit": 0, "detections": 0,
                               "unmatched": 0, "unmatched_inside_cough": 0})
    with epfl.detector_settings(band, threshold, separation):
        for r in recs:
            ev = detect.detect_events(sessions[r.name], fs=FS)
            st, en = coughs[r.name]
            d_hit, c_hit = match(ev, st, en)
            p = per[r.subject]
            p["annotated"] += len(st)
            p["hit"] += int(c_hit.sum())
            p["detections"] += len(ev)
            p["unmatched"] += int((~d_hit).sum())
            p["unmatched_inside_cough"] += int((~d_hit & in_any_window(ev, st, en)).sum())
    for p in per.values():
        p["recall"] = p["hit"] / p["annotated"]
    return dict(sorted(per.items()))


def pooled(per: dict) -> dict:
    tot = {k: sum(p[k] for p in per.values())
           for k in ("annotated", "hit", "detections", "unmatched", "unmatched_inside_cough")}
    tot["recall"] = tot["hit"] / tot["annotated"]
    return tot


def count_detections(recs, sessions, band, threshold, separation) -> int:
    with epfl.detector_settings(band, threshold, separation):
        return int(sum(len(detect.detect_events(sessions[r.name], fs=FS)) for r in recs))


def classify(X, y, groups, subjects_of_event, classes_of_event) -> dict:
    scores = leave_one_session_out(X, y, groups)
    auc = float(roc_auc_score(y, scores))
    lo, hi, n_boot = session_bootstrap_ci(y, scores, groups)
    perm_mean, perm_max, n_perm = permutation_null(X, y, groups)
    cm = confusion(y, scores)
    called = scores >= 0.5
    per_class = {c: {"n_events": int((classes_of_event == c).sum()),
                     "fraction_called_cough": float(called[classes_of_event == c].mean())}
                 for c in ("cough",) + epfl.CONFOUND_CLASSES if (classes_of_event == c).any()}
    per_subject = {}
    for s in sorted(set(subjects_of_event)):
        m = subjects_of_event == s
        entry = {"n_cough_events": int((y[m] == 1).sum()), "n_confound_events": int((y[m] == 0).sum()),
                 "cough_called_cough": float(called[m & (y == 1)].mean()) if (m & (y == 1)).any() else None,
                 "confound_called_cough": float(called[m & (y == 0)].mean()) if (m & (y == 0)).any() else None}
        entry["auc"] = float(roc_auc_score(y[m], scores[m])) if len(set(y[m])) == 2 else None
        per_subject[s] = entry
    subj_auc = [e["auc"] for e in per_subject.values() if e["auc"] is not None]
    cough_vs = {}
    for c in epfl.CONFOUND_CLASSES:
        m = (classes_of_event == "cough") | (classes_of_event == c)
        if (classes_of_event == c).any() and (classes_of_event == "cough").any():
            cough_vs[c] = float(roc_auc_score(y[m], scores[m]))
    return {"n_events": int(len(y)), "n_cough_events": int(y.sum()),
            "n_confound_events": int((y == 0).sum()), "n_subjects": len(set(groups)),
            "auc": auc, "auc_ci95": [lo, hi], "n_bootstrap": n_boot,
            "sensitivity": cm["sensitivity"], "specificity": cm["specificity"],
            "precision": cm["precision"], "confusion": cm,
            "permutation_null_mean": perm_mean, "permutation_null_max": perm_max,
            "n_permutation_rounds": n_perm,
            "per_class": per_class, "auc_cough_vs_each_confound": cough_vs,
            "per_subject": per_subject,
            "per_subject_auc_spread": spread(subj_auc) if subj_auc else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=epfl.EPFL_ROOT, type=Path)
    ap.add_argument("--out", default="results", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    recs = [r for r in epfl.list_recordings(args.root) if r.movement == "sit"]
    sessions = {r.name: epfl.load_recording(r) for r in recs}
    cough_recs = [r for r in recs if r.cls == "cough"]
    conf_recs = [r for r in recs if r.cls in epfl.CONFOUND_CLASSES]
    coughs = {r.name: epfl.load_coughs(r) for r in cough_recs}
    subjects = sorted({r.subject for r in recs})
    eligible = sorted({r.subject for r in cough_recs} & {r.subject for r in conf_recs})
    report = {"scope": {"movement": "sit", "n_recordings": len(recs),
                        "n_cough_recordings": len(cough_recs), "n_confound_recordings": len(conf_recs),
                        "n_subjects": len(subjects), "n_subjects_with_cough_and_confound": len(eligible),
                        "n_annotated_coughs": int(sum(len(coughs[r.name][0]) for r in cough_recs)),
                        "sample_rate_hz": FS, "hit_tolerance_s": HIT_TOLERANCE_S},
              "detector": {"band_hz": list(epfl.BAND_HZ), "threshold_mad": detect.THRESHOLD_MAD,
                           "refractory_s": detect.MIN_SEPARATION_S}}
    band, thr, sep = epfl.BAND_HZ, detect.THRESHOLD_MAD, detect.MIN_SEPARATION_S
    n_ann = report["scope"]["n_annotated_coughs"]
    print(f"Scope: mov_sit, {len(subjects)} subjects ({len(eligible)} with cough and confound), "
          f"{len(cough_recs)} cough and {len(conf_recs)} confound recordings, {n_ann} annotated coughs\n")

    # 1. Sensitivity sweeps
    print("1. Detector sensitivity at 100 Hz (seated cough recordings)")
    print(f"{'threshold':>9s} {'detections':>10s} {'det/annot':>9s} {'recall':>7s} {'unmatched':>9s} {'confound det':>12s}")
    sweep = []
    for t in range(3, 26):
        pr = pooled(recall_table(cough_recs, sessions, coughs, band, t, sep))
        nc = count_detections(conf_recs, sessions, band, t, sep)
        sweep.append({"threshold": t, **pr, "confound_detections": nc})
        print(f"{t:9d} {pr['detections']:10d} {pr['detections'] / n_ann:9.3f} {pr['recall']:7.3f} "
              f"{pr['unmatched']:9d} {nc:12d}")
    report["threshold_sweep"] = sweep

    print(f"\n{'band (Hz)':>9s} {'detections':>10s} {'recall':>7s} {'unmatched':>9s}   (threshold {thr}, refractory {sep} s)")
    report["band_sweep"] = {}
    for b in [(5, 45), (8, 45), (10, 30), (10, 40), (10, 45), (15, 45), (20, 45)]:
        pr = pooled(recall_table(cough_recs, sessions, coughs, b, thr, sep))
        report["band_sweep"][f"{b[0]}-{b[1]}"] = pr
        print(f"{f'{b[0]}-{b[1]}':>9s} {pr['detections']:10d} {pr['recall']:7.3f} {pr['unmatched']:9d}")

    print(f"\n{'refractory':>10s} {'detections':>10s} {'recall':>7s} {'unmatched':>9s}   (band {band[0]:.0f}-{band[1]:.0f} Hz, threshold {thr})")
    report["refractory_sweep"] = {}
    for s in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        pr = pooled(recall_table(cough_recs, sessions, coughs, band, thr, s))
        report["refractory_sweep"][str(s)] = pr
        print(f"{s:9.2f}s {pr['detections']:10d} {pr['recall']:7.3f} {pr['unmatched']:9d}")

    # 2. Recall against audio-annotated labels, default settings
    print(f"\n2. Detection recall against audio-annotated coughs (band {band[0]:.0f}-{band[1]:.0f} Hz, "
          f"threshold {thr}, refractory {sep} s, tolerance {HIT_TOLERANCE_S} s)")
    per = recall_table(cough_recs, sessions, coughs, band, thr, sep)
    pool = pooled(per)
    print(f"  {'subject':8s} {'annotated':>9s} {'hit':>5s} {'recall':>7s} {'detections':>10s} {'unmatched':>9s} {'(inside a cough)':>16s}")
    for s, p in per.items():
        print(f"  {s:8s} {p['annotated']:9d} {p['hit']:5d} {p['recall']:7.3f} {p['detections']:10d} "
              f"{p['unmatched']:9d} {p['unmatched_inside_cough']:16d}")
    print(f"  {'pooled':8s} {pool['annotated']:9d} {pool['hit']:5d} {pool['recall']:7.3f} {pool['detections']:10d} "
          f"{pool['unmatched']:9d} {pool['unmatched_inside_cough']:16d}")
    rs = spread([p["recall"] for p in per.values()])
    print(f"  per-subject recall: min {rs['min']:.3f}, q1 {rs['q1']:.3f}, median {rs['median']:.3f}, "
          f"q3 {rs['q3']:.3f}, max {rs['max']:.3f}")
    report["recall"] = {"per_subject": per, "pooled": pool, "per_subject_recall_spread": rs}

    # 3. Classification
    rows = {"matched": defaultdict(list), "all": defaultdict(list)}
    fallback = {"matched": 0, "all": 0}
    with epfl.detector_settings(band, thr, sep):
        for r in recs:
            s = sessions[r.name]
            ev = detect.detect_events(s, fs=FS)
            if ev.size == 0:
                continue
            f = event_features(s, ev, fs=FS)
            no_quiet = not has_quiet_window(s, ev)
            if r.cls == "cough":
                keep_sets = {"matched": match(ev, *coughs[r.name])[0], "all": np.ones(len(ev), bool)}
            else:
                keep_sets = {"matched": np.ones(len(ev), bool), "all": np.ones(len(ev), bool)}
            for variant, keep in keep_sets.items():
                k = int(keep.sum())
                if k == 0:
                    continue
                d = rows[variant]
                d["X"].append(f[keep])
                d["y"].append(np.full(k, int(r.cls == "cough")))
                d["subject"].append(np.full(k, r.subject))
                d["cls"].append(np.full(k, r.cls))
                d["no_quiet"].append(np.full(k, no_quiet))
                fallback[variant] += k if no_quiet else 0

    def stack(d):
        return (np.vstack(d["X"]), np.concatenate(d["y"]), np.concatenate(d["subject"]),
                np.concatenate(d["cls"]), np.concatenate(d["no_quiet"]))

    qx, qy, qg = [], [], []
    with epfl.detector_settings(band, thr, sep):
        for r in recs:
            s = sessions[r.name]
            q = quiet_windows(s, detect.detect_events(s, fs=FS), fs=FS)
            qx.append(q); qy.append(np.full(len(q), int(r.cls == "cough"))); qg.append(np.full(len(q), r.subject))
    qx, qy, qg = np.vstack(qx), np.concatenate(qy), np.concatenate(qg)
    art = background_artifact_auc(qx, qy, qg)
    coverage = []
    for r in cough_recs:
        st, en = coughs[r.name]
        covered = np.zeros(len(sessions[r.name].t), bool)
        for a, b in zip(st, en):
            covered[int(a * FS):int(np.ceil(b * FS))] = True
        coverage.append(float(covered.mean()))
    width = int(QUIET_WINDOW_S * FS)
    n_q = n_q_cough = 0
    with epfl.detector_settings(band, thr, sep):
        for r in cough_recs:
            s = sessions[r.name]
            ev = detect.detect_events(s, fs=FS)
            st, en = coughs[r.name]
            for i in range(0, len(s.t) - width, width):
                centre = s.t[i + width // 2]
                if ev.size and np.min(np.abs(ev - centre)) < QUIET_EXCLUSION_S:
                    continue
                n_q += 1
                a, b = s.t[i], s.t[i + width - 1]
                n_q_cough += bool(np.any((st <= b) & (en >= a)))
    report["cough_time_fraction_per_recording"] = spread(coverage)
    report["quiet_windows_in_cough_recordings"] = {
        "n": n_q, "overlapping_an_annotated_cough": n_q_cough,
        "fraction": n_q_cough / n_q if n_q else None}
    report["quiet_background_artifact_auc"] = art
    report["quiet_background_windows"] = {"n": int(len(qy)), "cough": int(qy.sum()), "confound": int((qy == 0).sum())}

    print(f"\n3. Cough vs. confound, leave-one-subject-out, bootstrap over subjects")
    print(f"  quiet-background artifact AUC {art:.3f}  ({len(qy)} windows)")
    cv = report["cough_time_fraction_per_recording"]
    print(f"  share of each cough recording inside an annotated cough: median {cv['median']:.2f} "
          f"(min {cv['min']:.2f}, max {cv['max']:.2f})")
    qc = report["quiet_windows_in_cough_recordings"]
    print(f"  'quiet' windows in cough recordings that overlap an annotated cough: "
          f"{qc['overlapping_an_annotated_cough']} of {qc['n']} ({100 * qc['fraction']:.0f}%)")
    report["classification"] = {}
    for variant in ("matched", "all"):
        X, y, g, c, nq = stack(rows[variant])
        res = classify(X, y, g, g, c)
        # same analysis without events from recordings that had no quiet window
        keep = ~nq
        res_q = classify(X[keep], y[keep], g[keep], g[keep], c[keep]) if keep.sum() < len(keep) else None
        res["events_from_recordings_without_quiet_window"] = int(nq.sum())
        res["excluding_those_events"] = None if res_q is None else {
            k: res_q[k] for k in ("n_events", "auc", "auc_ci95", "sensitivity", "specificity")}
        report["classification"][variant] = res
        print(f"\n  [{variant}] {res['n_events']} transients ({res['n_cough_events']} cough, "
              f"{res['n_confound_events']} confound), {res['n_subjects']} subjects")
        print(f"  AUC                         {res['auc']:.3f}   95% CI [{res['auc_ci95'][0]:.3f}, "
              f"{res['auc_ci95'][1]:.3f}] (subject-level bootstrap, n={res['n_bootstrap']})")
        print(f"  sensitivity                 {res['sensitivity']:.3f}")
        print(f"  specificity                 {res['specificity']:.3f}")
        print(f"  permutation null            mean {res['permutation_null_mean']:.3f}, max {res['permutation_null_max']:.3f}")
        for cls, pc in res["per_class"].items():
            print(f"    {cls:18s} n={pc['n_events']:4d}  called cough {100 * pc['fraction_called_cough']:3.0f}%")
        print("  AUC, cough vs. each confound: " + ", ".join(
            f"{k} {v:.3f}" for k, v in res["auc_cough_vs_each_confound"].items()))
        sa = res["per_subject_auc_spread"]
        print(f"  per-subject AUC: min {sa['min']:.3f}, median {sa['median']:.3f}, max {sa['max']:.3f}")
        if res_q is not None:
            print(f"  without the {int(nq.sum())} events from recordings with no quiet window: "
                  f"AUC {res_q['auc']:.3f} [{res_q['auc_ci95'][0]:.3f}, {res_q['auc_ci95'][1]:.3f}], "
                  f"n={res_q['n_events']}")

    (args.out / "epfl_results.json").write_text(json.dumps(report, indent=2))
    print(f"\nwritten to {args.out / 'epfl_results.json'}")


if __name__ == "__main__":
    main()
