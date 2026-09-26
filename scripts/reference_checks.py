#!/usr/bin/env python3
"""Two checks on the EPFL threshold-placement results. The detector is unchanged.

Check 1: is the gap in cough height (7.5 against 88 background MADs) about
weaker coughs or a noisier sensor?
  1a. Does the EPFL accelerometer carry gravity? Median magnitude outside
      annotated coughs, per recording, seated. Decision rule, fixed before the
      numbers were seen: gravity if every per-subject median lies within 15% of
      the median across subjects.
  1b. If so, convert EPFL to m/s^2 and compare background MAD and cough
      amplitude in m/s^2, both datasets on a 10-45 Hz envelope.
  1c. Cough peak relative to the envelope level during walking, per dataset.
      Scale-free.

Check 2: is the annotation-reference AUC separation or asymmetry? The
reference is rebuilt the same way for both classes: candidates from the
published detector at a low threshold, windows more than 0.5 s from any
candidate.

Output: results/reference_checks.json.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from chest_imu_cough import detect, epfl, io
from chest_imu_cough.features import _band_energies, event_features
from chest_imu_cough.evaluate import background_artifact_auc
from run_epfl import match, spread, classify
from threshold_placement import (
    cough_mask, far_from, mad_stats, reference_windows, reference_level,
    fixed_reference, window_rows, annotation_windows, MIN_BACKGROUND_SAMPLES,
)

G = 9.81
GRAVITY_TOLERANCE = 0.15
BAND = epfl.BAND_HZ                 # 10-45 Hz on both datasets for check 1
CANDIDATE_THRESHOLD = 3.0           # check 2: deliberately low
CANDIDATE_REFRACTORY_S = 0.25
CANDIDATE_EXCLUSION_S = 0.5
REFERENCE_WINDOW_S = 0.5
FS = epfl.SAMPLE_RATE_HZ


def envelope45(acc, fs):
    with epfl.detector_settings(band=BAND):
        return detect.envelope(acc, fs)


# ---------------------------------------------------------------- check 1
def gravity(recs, sessions, coughs) -> dict:
    per_rec = {}
    for r in recs:
        s = sessions[r.name]
        keep = ~cough_mask(len(s.t), *coughs[r.name]) if r.cls == "cough" else np.ones(len(s.t), bool)
        per_rec[r.name] = (r.subject, float(np.median(s.acc[keep])))
    subjects = sorted({v[0] for v in per_rec.values()})
    per_subject = {}
    for subj in subjects:
        v = np.array([m for sj, m in per_rec.values() if sj == subj])
        per_subject[subj] = {"median": float(np.median(v)), "min": float(v.min()), "max": float(v.max()),
                             "n_recordings": int(v.size)}
    med = np.array([p["median"] for p in per_subject.values()])
    grand = float(np.median(med))
    within = bool(np.all(np.abs(med / grand - 1) <= GRAVITY_TOLERANCE))
    return {"per_subject": per_subject, "median_across_subjects": grand,
            "subject_median_spread": spread(med),
            "max_relative_deviation": float(np.max(np.abs(med / grand - 1))),
            "recording_median_spread": spread([m for _, m in per_rec.values()]),
            "branch": "A" if (within and grand > 0) else "B",
            "scale_to_ms2": G / grand if (within and grand > 0) else None}


def own_resting_magnitude() -> float:
    s = io.load_session(ROOT / "data/sessions/baseline_calm_01_sitting.zip")
    return float(np.median(s.acc))


def own_amplitudes() -> dict:
    """Single subject, seated cough sessions, 10-45 Hz envelope, m/s^2."""
    out = {"background_mad": {}, "cough_amplitude": {}, "cough_peak": {}}
    for name in [n for n in io.SEATED if n.startswith("cough")]:
        s = io.load_session(ROOT / "data/sessions" / f"{name}.zip")
        ev = detect.detect_events(s, io.SAMPLE_RATE_HZ)          # published detector
        env = envelope45(s.acc, io.SAMPLE_RATE_HZ)
        b, m = mad_stats(env[far_from(s.t, ev, 2.0)])
        peaks = np.array([env[(s.t >= e - 0.1) & (s.t <= e + 0.1)].max() for e in ev])
        out["background_mad"][name] = m
        out["cough_amplitude"][name] = (peaks - b).tolist()
        out["cough_peak"][name] = peaks.tolist()
    return out


def epfl_amplitudes(cough_recs, sessions, coughs, scale) -> dict:
    out = {"background_mad": {}, "cough_amplitude": {}, "cough_peak": {}}
    for r in cough_recs:
        s = sessions[r.name]
        env = envelope45(s.acc * scale, FS)
        st, en = coughs[r.name]
        inside = cough_mask(env.size, st, en)
        if (~inside).sum() < MIN_BACKGROUND_SAMPLES:
            continue
        b, m = mad_stats(env[~inside])
        peaks = [env[int(a * FS):int(np.ceil(e * FS)) + 1].max() for a, e in zip(st, en)]
        out["background_mad"].setdefault(r.subject, []).append(m)
        out["cough_amplitude"].setdefault(r.subject, []).extend([p - b for p in peaks])
        out["cough_peak"].setdefault(r.subject, []).extend(peaks)
    return out


def walking_levels(all_recs, scale) -> dict:
    """EPFL walking envelope: mov_walk cough recordings outside annotated coughs
    (primary), and whole mov_walk deep-breathing recordings (secondary)."""
    primary, secondary = {}, {}
    for r in all_recs:
        if r.movement != "walk" or r.cls not in ("cough", "deep_breathing"):
            continue
        s = epfl.load_recording(r)
        env = envelope45(s.acc * scale, FS)
        if r.cls == "cough":
            keep = ~cough_mask(env.size, *epfl.load_coughs(r))
            if keep.sum() >= MIN_BACKGROUND_SAMPLES:
                primary.setdefault(r.subject, []).append(env[keep])
        else:
            secondary.setdefault(r.subject, []).append(env)
    summarise = lambda d: {s: {"median": float(np.median(np.concatenate(v))),
                               "p90": float(np.percentile(np.concatenate(v), 90))} for s, v in sorted(d.items())}
    return {"cough_recordings_outside_coughs": summarise(primary), "deep_breathing_recordings": summarise(secondary)}


def own_walking_level() -> dict:
    s = io.load_session(ROOT / "data/sessions/baseline_movement_01_walking.zip")
    env = envelope45(s.acc, io.SAMPLE_RATE_HZ)
    return {"median": float(np.median(env)), "p90": float(np.percentile(env, 90))}


# ---------------------------------------------------------------- check 2
def candidate_windows(session):
    with epfl.detector_settings(threshold=CANDIDATE_THRESHOLD, separation=CANDIDATE_REFRACTORY_S):
        cand = detect.detect_events(session, fs=FS)
    width = int(REFERENCE_WINDOW_S * FS)

    def ok(a, b):
        if cand.size == 0:
            return True
        lo, hi = session.t[a], session.t[b - 1]
        # window must lie more than the exclusion distance from every candidate
        return bool(np.all((cand < lo - CANDIDATE_EXCLUSION_S) | (cand > hi + CANDIDATE_EXCLUSION_S)))
    return reference_windows(session, ok, REFERENCE_WINDOW_S), cand


def candidate_threshold_sweep(recs, sessions, coughs, thresholds=(1.0, 1.5, 2.0, 3.0)) -> dict:
    """How clean the symmetric windows are, and how many recordings keep one."""
    global CANDIDATE_THRESHOLD
    saved, out = CANDIDATE_THRESHOLD, {}
    try:
        for thr in thresholds:
            CANDIDATE_THRESHOLD = thr
            n = hit = 0
            wins_n = {"cough": 0, "confound": 0}
            empty = {"cough": 0, "confound": 0}
            with epfl.detector_settings():
                for r in recs:
                    s = sessions[r.name]
                    wins, _ = candidate_windows(s)
                    k = "cough" if r.cls == "cough" else "confound"
                    wins_n[k] += len(wins)
                    empty[k] += int(not wins)
                    if r.cls == "cough":
                        inside = cough_mask(len(s.t), *coughs[r.name])
                        n += len(wins)
                        hit += sum(bool(inside[a:b].any()) for a, b in wins)
            out[str(thr)] = {"cough_windows_overlapping_annotated_cough": hit, "cough_windows": n,
                             "overlap_fraction": hit / n if n else None, "windows": wins_n,
                             "recordings_without_window": empty}
    finally:
        CANDIDATE_THRESHOLD = saved
    return out


def symmetric_classification(recs, sessions, coughs) -> dict:
    X, y, g, c = [], [], [], []
    qx, qy, qg = [], [], []
    dropped = {"cough": 0, "confound": 0}
    no_window_recordings = {"cough": 0, "confound": 0}
    agreement, overlap_n, overlap_hit = [], 0, 0
    with epfl.detector_settings():
        for r in recs:
            s = sessions[r.name]
            key = "cough" if r.cls == "cough" else "confound"
            wins, _ = candidate_windows(s)
            if not wins:
                no_window_recordings[key] += 1
            rows = window_rows(s, wins)
            qx += rows; qy += [int(r.cls == "cough")] * len(rows); qg += [r.subject] * len(rows)
            if r.cls == "cough":
                inside = cough_mask(len(s.t), *coughs[r.name])
                overlap_n += len(wins)
                overlap_hit += sum(bool(inside[a:b].any()) for a, b in wins)
                ann = annotation_windows(s, *coughs[r.name], REFERENCE_WINDOW_S)
                if wins and ann:
                    sym_acc = reference_level(s, wins)[0][:4]      # 50-100 Hz band is empty at 100 Hz
                    ann_acc = reference_level(s, ann)[0][:4]
                    agreement.append(np.log10((sym_acc + 1e-12) / (ann_acc + 1e-12)))
            ev = detect.detect_events(s, fs=FS)
            if ev.size == 0:
                continue
            keep = match(ev, *coughs[r.name])[0] if r.cls == "cough" else np.ones(len(ev), bool)
            if not keep.any():
                continue
            if not wins:
                dropped[key] += int(keep.sum())
                continue
            with fixed_reference(reference_level(s, wins)):
                f = event_features(s, ev, fs=FS)
            X.append(f[keep]); y.append(np.full(keep.sum(), int(r.cls == "cough")))
            g.append(np.full(keep.sum(), r.subject)); c.append(np.full(keep.sum(), r.cls))
    X, y, g, c = np.vstack(X), np.concatenate(y), np.concatenate(g), np.concatenate(c)
    res = classify(X, y, g, g, c)
    res["quiet_background_artifact_auc"] = background_artifact_auc(np.array(qx), np.array(qy), np.array(qg))
    res["reference_windows"] = {"cough": int(np.sum(qy)), "confound": int(len(qy) - np.sum(qy))}
    res["events_dropped_without_reference"] = dropped
    res["recordings_without_reference_window"] = no_window_recordings
    a = np.array(agreement)
    res["agreement_with_annotation_reference"] = {
        "n_recordings": int(len(a)),
        "symmetric_windows_overlapping_annotated_cough": overlap_hit,
        "symmetric_windows_in_cough_recordings": overlap_n,
        "overlap_fraction": overlap_hit / overlap_n if overlap_n else None,
        "median_abs_log10_ratio_per_band": np.median(np.abs(a), axis=0).tolist() if len(a) else None,
        "median_log10_ratio_per_band": np.median(a, axis=0).tolist() if len(a) else None,
        "bands_hz": [[1, 3], [3, 10], [10, 25], [25, 50]],
    }
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results", type=Path)
    args = ap.parse_args()
    all_recs = epfl.list_recordings()
    recs = [r for r in all_recs if r.movement == "sit"]
    sessions = {r.name: epfl.load_recording(r) for r in recs}
    cough_recs = [r for r in recs if r.cls == "cough"]
    coughs = {r.name: epfl.load_coughs(r) for r in cough_recs}
    report = {"settings": {"band_hz": list(BAND), "gravity_tolerance": GRAVITY_TOLERANCE,
                           "candidate_threshold_mad": CANDIDATE_THRESHOLD,
                           "candidate_refractory_s": CANDIDATE_REFRACTORY_S,
                           "candidate_exclusion_s": CANDIDATE_EXCLUSION_S,
                           "reference_window_s": REFERENCE_WINDOW_S}}

    print("1a. EPFL accelerometer magnitude outside annotated coughs, seated")
    gr = gravity(recs, sessions, {**coughs, **{r.name: ([], []) for r in recs if r.cls != "cough"}})
    report["gravity"] = gr
    report["own_resting_magnitude_ms2"] = own_resting_magnitude()
    for subj, p in gr["per_subject"].items():
        print(f"  {subj}  median {p['median']:6.1f}  recordings {p['min']:6.1f} to {p['max']:6.1f}  (n={p['n_recordings']})")
    ss = gr["subject_median_spread"]
    print(f"  across subjects: median {gr['median_across_subjects']:.1f}, min {ss['min']:.1f}, max {ss['max']:.1f}, "
          f"largest deviation {100 * gr['max_relative_deviation']:.0f}%")
    print(f"  single subject at rest: {report['own_resting_magnitude_ms2']:.2f} m/s^2")
    print(f"  branch {gr['branch']}" + (f", scale {gr['scale_to_ms2']:.4f} m/s^2 per count" if gr["scale_to_ms2"] else ""))

    scale = gr["scale_to_ms2"]
    own = own_amplitudes()
    if scale:
        print("\n1b. Background MAD and cough amplitude in m/s^2, 10-45 Hz envelope")
        ep = epfl_amplitudes(cough_recs, sessions, coughs, scale)
        own_bg = list(own["background_mad"].values())
        own_amp = [x for v in own["cough_amplitude"].values() for x in v]
        ep_bg_subj = {s: float(np.median(v)) for s, v in ep["background_mad"].items()}
        ep_amp_subj = {s: float(np.median(v)) for s, v in ep["cough_amplitude"].items()}
        ep_bg = [x for v in ep["background_mad"].values() for x in v]
        ep_amp = [x for v in ep["cough_amplitude"].values() for x in v]
        report["amplitudes_ms2"] = {
            "single_subject": {"background_mad_per_session": own["background_mad"],
                               "background_mad": spread(own_bg), "cough_amplitude": spread(own_amp),
                               "cough_amplitude_natural_02": spread(own["cough_amplitude"]["cough_natural_02_sitting"])},
            "epfl": {"background_mad_per_recording": spread(ep_bg), "background_mad_subject_medians": spread(list(ep_bg_subj.values())),
                     "cough_amplitude": spread(ep_amp), "cough_amplitude_subject_medians": spread(list(ep_amp_subj.values())),
                     "per_subject": {s: {"background_mad": ep_bg_subj[s], "cough_amplitude": ep_amp_subj[s]} for s in ep_bg_subj}}}
        a = report["amplitudes_ms2"]
        print(f"  single subject: background MAD median {a['single_subject']['background_mad']['median']:.4f} "
              f"(sessions {a['single_subject']['background_mad']['min']:.4f} to {a['single_subject']['background_mad']['max']:.4f}); "
              f"cough amplitude median {a['single_subject']['cough_amplitude']['median']:.3f} "
              f"(IQR {a['single_subject']['cough_amplitude']['q1']:.3f} to {a['single_subject']['cough_amplitude']['q3']:.3f})")
        print(f"  EPFL: background MAD median {a['epfl']['background_mad_per_recording']['median']:.4f} "
              f"(subject medians {a['epfl']['background_mad_subject_medians']['min']:.4f} to {a['epfl']['background_mad_subject_medians']['max']:.4f}); "
              f"cough amplitude median {a['epfl']['cough_amplitude']['median']:.3f} "
              f"(IQR {a['epfl']['cough_amplitude']['q1']:.3f} to {a['epfl']['cough_amplitude']['q3']:.3f}; "
              f"subject medians {a['epfl']['cough_amplitude_subject_medians']['min']:.3f} to {a['epfl']['cough_amplitude_subject_medians']['max']:.3f})")
    else:
        print("\n1b skipped: no scale")

    print("\n1c. Cough peak relative to the envelope during walking (scale-free)")
    wl = walking_levels(all_recs, scale or 1.0)
    own_walk = own_walking_level()
    own_peak = [x for v in own["cough_peak"].values() for x in v]
    own_ratio = float(np.median(own_peak) / own_walk["median"])
    ep_peaks = epfl_amplitudes(cough_recs, sessions, coughs, scale or 1.0)["cough_peak"]
    ratios = {}
    for key in ("cough_recordings_outside_coughs", "deep_breathing_recordings"):
        per = {s: float(np.median(ep_peaks[s]) / wl[key][s]["median"]) for s in ep_peaks if s in wl[key]}
        ratios[key] = {"per_subject": per, "spread": spread(list(per.values()))}
    report["walking"] = {"single_subject": {"walking_envelope": own_walk, "cough_peak_median": float(np.median(own_peak)),
                                            "ratio": own_ratio,
                                            "ratio_natural_02": float(np.median(own["cough_peak"]["cough_natural_02_sitting"]) / own_walk["median"])},
                         "epfl_walking_envelope": wl, "epfl_ratio": ratios}
    print(f"  single subject: cough peak / walking envelope median = {own_ratio:.1f} "
          f"(cough_natural_02_sitting only: {report['walking']['single_subject']['ratio_natural_02']:.1f})")
    for key, v in ratios.items():
        sp = v["spread"]
        print(f"  EPFL [{key}]: per-subject median {sp['median']:.1f}, IQR {sp['q1']:.1f} to {sp['q3']:.1f}, "
              f"range {sp['min']:.1f} to {sp['max']:.1f}")

    print("\n2. Symmetric reference: candidates at 3 MAD, 0.25 s refractory, windows > 0.5 s from any candidate")
    sym = symmetric_classification(recs, sessions, coughs)
    report["symmetric_reference"] = sym
    ag = sym["agreement_with_annotation_reference"]
    print(f"  n={sym['n_events']} ({sym['n_cough_events']} cough / {sym['n_confound_events']} confound), "
          f"AUC {sym['auc']:.3f} [{sym['auc_ci95'][0]:.3f}, {sym['auc_ci95'][1]:.3f}], "
          f"perm mean {sym['permutation_null_mean']:.3f} max {sym['permutation_null_max']:.3f}, "
          f"background {sym['quiet_background_artifact_auc']:.3f}")
    print("  AUC cough vs. " + ", ".join(f"{k} {v:.3f}" for k, v in sym["auc_cough_vs_each_confound"].items()))
    print(f"  reference windows: {sym['reference_windows']}; recordings without one: {sym['recordings_without_reference_window']}; "
          f"events dropped: {sym['events_dropped_without_reference']}")
    print(f"  agreement on cough recordings: {ag['symmetric_windows_overlapping_annotated_cough']} of "
          f"{ag['symmetric_windows_in_cough_recordings']} symmetric windows overlap an annotated cough; "
          f"median |log10 ratio| per band {[round(x, 3) for x in ag['median_abs_log10_ratio_per_band']]} "
          f"over {ag['n_recordings']} recordings")

    sweep = candidate_threshold_sweep(recs, sessions, coughs)
    report["symmetric_candidate_threshold_sweep"] = sweep
    print("  candidate threshold sweep (cleanliness vs. availability):")
    for thr, v in sweep.items():
        print(f"    {thr} MAD: {v['cough_windows_overlapping_annotated_cough']}/{v['cough_windows']} cough-recording windows "
              f"overlap a cough ({100 * v['overlap_fraction']:.0f}%); recordings without a window: "
              f"cough {v['recordings_without_window']['cough']} of 168, confound {v['recordings_without_window']['confound']} of 503")

    (args.out / "reference_checks.json").write_text(json.dumps(report, indent=2))
    print(f"\nwritten to {args.out / 'reference_checks.json'}")


if __name__ == "__main__":
    main()
