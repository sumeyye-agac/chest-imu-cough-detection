#!/usr/bin/env python3
"""Where the detector's threshold sits relative to the true background.

The published detector is not changed. Three measurements:

1. Cough peak height in units of background MAD, on both datasets. The
   background comes from samples that are not events: on EPFL, samples outside
   annotated coughs; on the single-subject recordings, samples more than 2 s
   from a detected transient.
2. EPFL cough-vs-confound classification with the feature reference level taken
   from windows that overlap no annotated cough. The annotations set that
   reference level only. They are never a feature and never a label.
   Only 50 of 168 seated cough recordings have a cough-free 1 s window, so the
   primary configuration uses 0.5 s reference windows for every recording, and
   drops events whose recording has no reference window instead of letting the
   published fallback give them absolute energies.
3. EPFL detection with background median and MAD taken from outside the
   annotations: a bound on what the published threshold placement costs.

Output: results/threshold_placement.json.
"""
from __future__ import annotations
import argparse, contextlib, json, sys
from pathlib import Path
import numpy as np
from scipy import signal
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from chest_imu_cough import detect, epfl, features, io
from chest_imu_cough.features import _band_energies, event_features, QUIET_EXCLUSION_S, QUIET_WINDOW_S
from chest_imu_cough.evaluate import background_artifact_auc
from run_epfl import match, spread, classify, quiet_windows

FS = epfl.SAMPLE_RATE_HZ
MIN_BACKGROUND_SAMPLES = 50
LEGACY_HALF_WIDTH_S = 0.3   # same window as the label audit's excursion check


def mad_stats(x: np.ndarray) -> tuple[float, float]:
    b = float(np.median(x))
    return b, float(np.median(np.abs(x - b)))


def cough_mask(n: int, starts, ends) -> np.ndarray:
    inside = np.zeros(n, bool)
    for a, b in zip(starts, ends):
        inside[int(a * FS):int(np.ceil(b * FS))] = True
    return inside


def far_from(t: np.ndarray, events: np.ndarray, distance: float) -> np.ndarray:
    if events.size == 0:
        return np.ones(t.size, bool)
    return np.min(np.abs(t[:, None] - events[None, :]), axis=1) > distance


def summary(v) -> dict:
    v = np.asarray(v, float)
    return {"n": int(v.size), **spread(v),
            "share_above_8": float(np.mean(v > 8)), "share_above_5": float(np.mean(v > 5)),
            "share_above_3": float(np.mean(v > 3))}


# ---------------------------------------------------------------- 1. peak heights
def own_heights() -> dict:
    out = {"detected": {}, "detected_band_10_45": {}, "legacy_confirmed": {}}
    legacy = json.loads((ROOT / "data/legacy_labels/confirmed_events.json").read_text())
    for name in [n for n in io.SEATED if n.startswith("cough")]:
        s = io.load_session(ROOT / "data/sessions" / f"{name}.zip")
        env = detect.envelope(s.acc, io.SAMPLE_RATE_HZ)
        ev = detect.detect_events(s, io.SAMPLE_RATE_HZ)
        b, m = mad_stats(env[far_from(s.t, ev, QUIET_EXCLUSION_S)])
        idx = np.searchsorted(s.t, ev)
        out["detected"][name] = ((env[idx] - b) / m).tolist()
        # same events, envelope in the EPFL band, to separate band from device
        with epfl.detector_settings(band=epfl.BAND_HZ):
            env45 = detect.envelope(s.acc, io.SAMPLE_RATE_HZ)
        b45, m45 = mad_stats(env45[far_from(s.t, ev, QUIET_EXCLUSION_S)])
        out["detected_band_10_45"][name] = [
            float((env45[(s.t >= e - 0.1) & (s.t <= e + 0.1)].max() - b45) / m45) for e in ev]
        conf = np.asarray(legacy.get(name, {}).get("confirmed_events_t_unix", []), float)
        if conf.size:
            b, m = mad_stats(env[far_from(s.t, conf, QUIET_EXCLUSION_S)])
            h = [(env[(s.t >= c - LEGACY_HALF_WIDTH_S) & (s.t <= c + LEGACY_HALF_WIDTH_S)].max() - b) / m
                 for c in conf]
            out["legacy_confirmed"][name] = [float(x) for x in h]
    return out


def epfl_heights(cough_recs, sessions, coughs) -> tuple[dict, int]:
    per_subject: dict[str, list] = {}
    skipped = 0
    with epfl.detector_settings():
        for r in cough_recs:
            s = sessions[r.name]
            env = detect.envelope(s.acc, FS)
            st, en = coughs[r.name]
            inside = cough_mask(env.size, st, en)
            if (~inside).sum() < MIN_BACKGROUND_SAMPLES:
                skipped += 1
                continue
            b, m = mad_stats(env[~inside])
            for a, e in zip(st, en):
                seg = env[int(a * FS):int(np.ceil(e * FS)) + 1]
                if seg.size:
                    per_subject.setdefault(r.subject, []).append(float((seg.max() - b) / m))
    return dict(sorted(per_subject.items())), skipped


# ---------------------------------------------------------------- 3. detection bound
def epfl_detection_bound(cough_recs, sessions, coughs, threshold=8.0, separation=1.0) -> dict:
    per = {}
    with epfl.detector_settings():
        for r in cough_recs:
            s = sessions[r.name]
            env = detect.envelope(s.acc, FS)
            st, en = coughs[r.name]
            inside = cough_mask(env.size, st, en)
            bg = env[~inside] if (~inside).sum() >= MIN_BACKGROUND_SAMPLES else env
            b, m = mad_stats(bg)
            peaks, _ = signal.find_peaks((env - b) / m, height=threshold, distance=int(separation * FS))
            d_hit, c_hit = match(s.t[peaks], st, en)
            p = per.setdefault(r.subject, {"annotated": 0, "hit": 0, "detections": 0})
            p["annotated"] += len(st)
            p["hit"] += int(c_hit.sum())
            p["detections"] += len(peaks)
    for p in per.values():
        p["recall"] = p["hit"] / p["annotated"]
        p["precision"] = p["hit"] / p["detections"] if p["detections"] else None
    tot = {k: sum(p[k] for p in per.values()) for k in ("annotated", "hit", "detections")}
    tot["recall"] = tot["hit"] / tot["annotated"]
    tot["precision"] = tot["hit"] / tot["detections"]
    return {"per_subject": dict(sorted(per.items())), "pooled": tot}


def baseline_ratios(cough_recs, sessions, coughs) -> dict:
    rb, rm, rt = [], [], []
    with epfl.detector_settings():
        for r in cough_recs:
            env = detect.envelope(sessions[r.name].acc, FS)
            inside = cough_mask(env.size, *coughs[r.name])
            if (~inside).sum() < MIN_BACKGROUND_SAMPLES:
                continue
            b, m = mad_stats(env)
            qb, qm = mad_stats(env[~inside])
            rb.append(b / qb); rm.append(m / qm); rt.append((b + 8 * m) / (qb + 8 * qm))
    return {"median_ratio": spread(rb), "mad_ratio": spread(rm), "threshold_ratio": spread(rt)}


# ---------------------------------------------------------------- 2. classification
def reference_windows(session, keep_window, window_s=QUIET_WINDOW_S) -> list[tuple[int, int]]:
    width = int(window_s * FS)
    return [(i, i + width) for i in range(0, len(session.t) - width, width) if keep_window(i, i + width)]


def reference_level(session, windows):
    """Median band energies over the given windows; ones if there are none,
    matching the published fallback in features.quiet_baseline."""
    if not windows:
        ones = np.ones(len(features.BANDS_HZ))
        return ones, ones
    acc = [_band_energies(session.acc[a:b], FS)[0] for a, b in windows]
    gyro = [_band_energies(session.gyro[a:b], FS)[0] for a, b in windows]
    return np.median(acc, axis=0), np.median(gyro, axis=0)


@contextlib.contextmanager
def fixed_reference(level):
    """Make features.event_features use a given reference level."""
    saved = features.quiet_baseline
    features.quiet_baseline = lambda session, events, fs=FS: level
    try:
        yield
    finally:
        features.quiet_baseline = saved


def annotation_windows(session, starts, ends, window_s):
    inside = cough_mask(len(session.t), starts, ends)
    return reference_windows(session, lambda a, b: not inside[a:b].any(), window_s)


def detection_windows(session, events, window_s):
    def ok(a, b):
        centre = session.t[a + (b - a) // 2]
        return not (events.size and np.min(np.abs(events - centre)) < QUIET_EXCLUSION_S)
    return reference_windows(session, ok, window_s)


def window_rows(session, windows):
    rows = []
    for a, b in windows:
        ea = _band_energies(session.acc[a:b], FS)[0]
        eg = _band_energies(session.gyro[a:b], FS)[0]
        rows.append(np.concatenate([np.log10(ea + 1e-12), np.log10(eg + 1e-12)]))
    return rows


def run_reference(recs, sessions, coughs, confound_rule: str, window_s: float,
                  drop_without_reference: bool) -> dict:
    """confound_rule: 'detection' keeps the published quiet-window rule for
    confound recordings; 'all' treats every window of a confound recording as
    quiet. window_s applies to every recording, cough and confound alike."""
    X, y, g, c = [], [], [], []
    qx, qy, qg = [], [], []
    no_ref = 0
    with epfl.detector_settings():
        for r in recs:
            s = sessions[r.name]
            ev = detect.detect_events(s, fs=FS)
            if r.cls == "cough":
                wins = annotation_windows(s, *coughs[r.name], window_s)
            elif confound_rule == "detection":
                wins = detection_windows(s, ev, window_s)
            else:
                wins = reference_windows(s, lambda a, b: True, window_s)
            rows = window_rows(s, wins)
            qx += rows; qy += [int(r.cls == "cough")] * len(rows); qg += [r.subject] * len(rows)
            if ev.size == 0:
                continue
            with fixed_reference(reference_level(s, wins)):
                f = event_features(s, ev, fs=FS)
            keep = match(ev, *coughs[r.name])[0] if r.cls == "cough" else np.ones(len(ev), bool)
            if not keep.any():
                continue
            if not wins:
                no_ref += int(keep.sum())
                if drop_without_reference:
                    continue
            X.append(f[keep]); y.append(np.full(keep.sum(), int(r.cls == "cough")))
            g.append(np.full(keep.sum(), r.subject)); c.append(np.full(keep.sum(), r.cls))
    X, y, g, c = np.vstack(X), np.concatenate(y), np.concatenate(g), np.concatenate(c)
    res = classify(X, y, g, g, c)
    res["events_without_reference_window"] = no_ref
    res["events_without_reference_window_dropped"] = drop_without_reference
    res["reference_window_s"] = window_s
    qx, qy, qg = np.array(qx), np.array(qy), np.array(qg)
    res["quiet_background_artifact_auc"] = background_artifact_auc(qx, qy, qg)
    res["reference_windows"] = {"cough": int(qy.sum()), "confound": int((qy == 0).sum())}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    published = json.loads((args.out / "epfl_results.json").read_text())

    recs = [r for r in epfl.list_recordings() if r.movement == "sit"]
    sessions = {r.name: epfl.load_recording(r) for r in recs}
    cough_recs = [r for r in recs if r.cls == "cough"]
    coughs = {r.name: epfl.load_coughs(r) for r in cough_recs}
    report = {}

    print("1. Cough peak height above background, in background MADs")
    own = own_heights()
    for key, label in (("detected", "single subject, detected transients (primary)"),
                       ("detected_band_10_45", "single subject, detected transients, 10-45 Hz envelope"),
                       ("legacy_confirmed", "single subject, legacy confirmed events")):
        allv = [x for v in own[key].values() for x in v]
        sm = summary(allv)
        report.setdefault("peak_height", {})[f"single_subject_{key}"] = {
            "pooled": sm, "per_session": {n: summary(v) for n, v in own[key].items()}}
        print(f"  {label}: n={sm['n']}, median {sm['median']:.1f}, IQR [{sm['q1']:.1f}, {sm['q3']:.1f}], "
              f"above 8: {100 * sm['share_above_8']:.0f}%")
        for n, v in own[key].items():
            s1 = summary(v)
            print(f"    {n:28s} n={s1['n']:2d}  median {s1['median']:6.1f}  "
                  f"[{s1['min']:.1f}, {s1['max']:.1f}]  above 8: {100 * s1['share_above_8']:.0f}%")
    ep, skipped = epfl_heights(cough_recs, sessions, coughs)
    allv = [x for v in ep.values() for x in v]
    sm = summary(allv)
    per_subj = {s: summary(v) for s, v in ep.items()}
    report["peak_height"]["epfl_annotated"] = {
        "pooled": sm, "per_subject": per_subj, "recordings_skipped_no_background": skipped,
        "per_subject_median_spread": spread([p["median"] for p in per_subj.values()])}
    print(f"  EPFL, annotated coughs: n={sm['n']}, median {sm['median']:.1f}, IQR [{sm['q1']:.1f}, {sm['q3']:.1f}], "
          f"above 8: {100 * sm['share_above_8']:.0f}%  ({skipped} recordings skipped: no background)")
    for s, p in per_subj.items():
        print(f"    {s:8s} n={p['n']:3d}  median {p['median']:5.1f}  IQR [{p['q1']:.1f}, {p['q3']:.1f}]  "
              f"above 8: {100 * p['share_above_8']:.0f}%")

    print("\n3. EPFL detection with background from outside the annotations (threshold 8, refractory 1.0 s)")
    ratios = baseline_ratios(cough_recs, sessions, coughs)
    report["baseline_ratios"] = ratios
    print(f"  whole-recording / background: median {ratios['median_ratio']['median']:.2f}x, "
          f"MAD {ratios['mad_ratio']['median']:.2f}x, 8-MAD threshold {ratios['threshold_ratio']['median']:.2f}x")
    bound = epfl_detection_bound(cough_recs, sessions, coughs)
    report["detection_bound"] = bound
    pub = published["recall"]["per_subject"]
    print(f"  {'subject':8s} {'recall pub':>10s} {'prec pub':>9s} {'recall bg':>10s} {'prec bg':>8s}")
    for s, p in bound["per_subject"].items():
        q = pub[s]
        pp = q["hit"] / q["detections"] if q["detections"] else float("nan")
        prec = p["precision"] if p["precision"] is not None else float("nan")
        print(f"  {s:8s} {q['recall']:10.3f} {pp:9.3f} {p['recall']:10.3f} {prec:8.3f}")
    q = published["recall"]["pooled"]
    print(f"  {'pooled':8s} {q['recall']:10.3f} {q['hit'] / q['detections']:9.3f} "
          f"{bound['pooled']['recall']:10.3f} {bound['pooled']['precision']:8.3f}")

    print("\n2. Cough vs. confound (matched), feature reference from windows with no annotated cough")
    report["classification"] = {}
    configs = [
        ("primary_0.5s_dropped", "detection", 0.5, True),
        ("literal_0.5s_dropped", "all", 0.5, True),
        ("diagnostic_1s_fallback_kept", "detection", 1.0, False),
        ("diagnostic_1s_dropped", "detection", 1.0, True),
    ]
    for key, rule, win, drop in configs:
        res = run_reference(recs, sessions, coughs, rule, win, drop)
        report["classification"][key] = res
        print(f"  [{key}: confound reference {rule}, {win} s windows] n={res['n_events']} "
              f"({res['n_cough_events']} cough / {res['n_confound_events']} confound), AUC {res['auc']:.3f} [{res['auc_ci95'][0]:.3f}, {res['auc_ci95'][1]:.3f}], "
              f"perm mean {res['permutation_null_mean']:.3f} max {res['permutation_null_max']:.3f}, "
              f"background {res['quiet_background_artifact_auc']:.3f}, "
              f"events without reference window {res['events_without_reference_window']}")
        print("    AUC cough vs. " + ", ".join(f"{k} {v:.3f}" for k, v in res["auc_cough_vs_each_confound"].items()))

    (args.out / "threshold_placement.json").write_text(json.dumps(report, indent=2))
    print(f"\nwritten to {args.out / 'threshold_placement.json'}")


if __name__ == "__main__":
    main()
