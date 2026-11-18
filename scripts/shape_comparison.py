#!/usr/bin/env python3
"""Published features against the burst-shape feature set.

The lead: in the talking session, the long cough-sized transients are double-
peaked bursts, while the seated coughs are single bursts of about 1 s. If the
published 0.4 / 0.6 s window is why laughs are not separated, a wider window
with burst-shape features should separate cough from laugh on EPFL, where laugh
is its own recording class.

Configurations, all with the published detector:
  published          published features, published window 0.4 / 0.6 s
  window_only_*      published features over a wider window (control: window alone)
  shape_*            published features plus burst shape, over each window

EPFL: seated, leave-one-subject-out, matched variant (detections in cough
recordings kept only when they hit an annotated cough), published reference.
Cough vs. each confound uses the scores of the cough-vs-all-confounds model,
restricted to cough and that confound, as in run_epfl.py.

Own recordings: the seven seated sessions, leave-one-session-out.

Interpretation rule, fixed before the first run:
  For each shape window w, delta_laugh(w) = AUC cough-vs-laugh (shape_w) minus
  AUC cough-vs-laugh (published), and delta_breath(w) the same for deep
  breathing. Intervals come from a paired bootstrap over subjects (the same
  resampled subjects for both configurations). Three windows are tested, so the
  interval is 98.33% (Bonferroni, 0.05 / 3).
    (a) the lower bound of delta_laugh(w) is above 0;
    (b) the lower bound of delta_laugh(w) - delta_breath(w) is above 0.
  supported      (a) and (b) for at least one window
  mixed          (a) for some window, but (b) for none of those
  not supported  (a) for no window
  A rise in every confound is a better feature set, not evidence about laughing.

Output: results/shape_comparison.json.
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from chest_imu_cough import detect, epfl, io
from chest_imu_cough.features import event_features
from chest_imu_cough.features_shape import event_features_shape, WINDOWS, PUBLISHED_WINDOW, SHAPE_NAMES
from chest_imu_cough.evaluate import leave_one_session_out, session_bootstrap_ci
from run_epfl import match

N_BOOT = 2000
CI_LEVEL = 1 - 0.05 / 3
N_PERM = 30
SEED = 0


def configs():
    out = {"published": (event_features, PUBLISHED_WINDOW)}
    for w in WINDOWS:
        if w != PUBLISHED_WINDOW:
            out[f"window_only_{w[0]}_{w[1]}"] = (event_features, w)
    for w in WINDOWS:
        out[f"shape_{w[0]}_{w[1]}"] = (event_features_shape, w)
    return out


def ci(draws, level=0.95):
    a = (1 - level) / 2 * 100
    return [float(np.percentile(draws, a)), float(np.percentile(draws, 100 - a))]


def subset_auc(y, s, m):
    return float(roc_auc_score(y[m], s[m]))


def bootstrap_draws(y, groups, masks, score_sets, n_boot=N_BOOT, seed=SEED):
    """AUC draws for every (mask, score set), with the same resampled groups."""
    rng = np.random.default_rng(seed)
    names = np.array(sorted(set(groups.tolist())))
    idx = {g: np.flatnonzero(groups == g) for g in names}
    out = {(mk, sk): [] for mk in masks for sk in score_sets}
    for _ in range(n_boot):
        pick = np.concatenate([idx[g] for g in rng.choice(names, size=len(names), replace=True)])
        for mk, m in masks.items():
            mm = pick[m[pick]]
            yy = y[mm]
            if len(set(yy)) < 2:
                for sk in score_sets:
                    out[(mk, sk)].append(np.nan)
                continue
            for sk, s in score_sets.items():
                out[(mk, sk)].append(roc_auc_score(yy, s[mm]))
    return {k: np.array(v) for k, v in out.items()}


# ---------------------------------------------------------------- EPFL
def epfl_events(root):
    recs = [r for r in epfl.list_recordings(root) if r.movement == "sit"]
    sessions = {r.name: epfl.load_recording(r) for r in recs}
    kept = []
    with epfl.detector_settings():
        for r in recs:
            s = sessions[r.name]
            ev = detect.detect_events(s, fs=epfl.SAMPLE_RATE_HZ)
            if ev.size == 0:
                continue
            keep = match(ev, *epfl.load_coughs(r))[0] if r.cls == "cough" else np.ones(len(ev), bool)
            if keep.any():
                kept.append((r, s, ev, keep))
    return kept


def epfl_features(kept, fn, window):
    X, y, g, c = [], [], [], []
    with epfl.detector_settings():
        for r, s, ev, keep in kept:
            # features see every detection in the recording (as published); only kept rows are used
            f = fn(s, ev, epfl.SAMPLE_RATE_HZ, pre_s=window[0], post_s=window[1])[keep]
            X.append(f); y.append(np.full(len(f), int(r.cls == "cough")))
            g.append(np.full(len(f), r.subject)); c.append(np.full(len(f), r.cls))
    return np.vstack(X), np.concatenate(y), np.concatenate(g), np.concatenate(c)


# ---------------------------------------------------------------- own recordings
def own_features(fn, window):
    X, y, g = [], [], []
    for n in io.SEATED:
        s = io.load_session(ROOT / "data/sessions" / f"{n}.zip")
        ev = detect.detect_events(s)
        f = fn(s, ev, io.SAMPLE_RATE_HZ, pre_s=window[0], post_s=window[1])
        X.append(f); y.append(np.full(len(f), int(s.is_cough))); g.append(np.full(len(f), n))
    return np.vstack(X), np.concatenate(y), np.concatenate(g)


def permutation(X, y, groups, masks, rounds=N_PERM, seed=SEED):
    """Labels shuffled; the classifier never sees the real ones. Overall AUC is
    taken against the shuffled labels, as in evaluate.permutation_null; the
    per-confound AUCs against the true labels of that subset."""
    rng = np.random.default_rng(seed)
    out = defaultdict(list)
    for _ in range(rounds):
        sh = rng.permutation(y)
        try:
            s = leave_one_session_out(X, sh, groups, n_estimators=150)
        except ValueError:
            continue
        out["overall"].append(roc_auc_score(sh, s))
        for k, m in masks.items():
            out[k].append(roc_auc_score(y[m], s[m]))
    return {k: {"mean": float(np.mean(v)), "max": float(np.max(v)), "n": len(v)} for k, v in out.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=epfl.EPFL_ROOT, type=Path)
    ap.add_argument("--out", default="results", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cfgs = configs()
    report = {"settings": {"windows_s": WINDOWS, "published_window_s": list(PUBLISHED_WINDOW),
                           "n_bootstrap": N_BOOT, "rule_interval": CI_LEVEL,
                           "permutation_rounds": N_PERM},
              "epfl": {}, "own": {}}

    # ---- EPFL
    kept = epfl_events(args.root)
    scores, data, Xs = {}, None, {}
    for name, (fn, w) in cfgs.items():
        X, y, g, c = epfl_features(kept, fn, w)
        if data is None:
            data = (y, g, c)
        else:
            assert np.array_equal(data[0], y) and np.array_equal(data[1], g)
        scores[name] = leave_one_session_out(X, y, g)
        Xs[name] = X
    y, g, c = data
    conf = epfl.CONFOUND_CLASSES
    masks = {"overall": np.ones(len(y), bool),
             **{k: (c == "cough") | (c == k) for k in conf}}
    draws = bootstrap_draws(y, g, masks, scores)
    ep = {"n_events": int(len(y)), "n_cough": int(y.sum()),
          "n_per_class": {k: int((c == k).sum()) for k in ("cough",) + conf}, "configs": {}}
    for name in cfgs:
        e = {}
        for mk, m in masks.items():
            lo, hi, _ = session_bootstrap_ci(y[m], scores[name][m], g[m])
            e[mk] = {"auc": subset_auc(y, scores[name], m), "ci95": [lo, hi]}
        ep["configs"][name] = e
    pub = ep["configs"]["published"]
    assert abs(pub["overall"]["auc"] - 0.765) < 0.0006, pub["overall"]["auc"]
    assert abs(pub["laugh"]["auc"] - 0.708) < 0.0006, pub["laugh"]["auc"]

    # paired deltas and the rule
    rule = {}
    for name in cfgs:
        if name == "published":
            continue
        d = {}
        for mk in masks:
            dd = draws[(mk, name)] - draws[(mk, "published")]
            dd = dd[~np.isnan(dd)]
            d[mk] = {"delta": ep["configs"][name][mk]["auc"] - pub[mk]["auc"],
                     "ci95": ci(dd), "ci_rule": ci(dd, CI_LEVEL)}
        diff = (draws[("laugh", name)] - draws[("laugh", "published")]) - (
            draws[("deep_breathing", name)] - draws[("deep_breathing", "published")])
        diff = diff[~np.isnan(diff)]
        d["laugh_minus_breathing"] = {
            "delta": d["laugh"]["delta"] - d["deep_breathing"]["delta"],
            "ci95": ci(diff), "ci_rule": ci(diff, CI_LEVEL)}
        d["a"] = d["laugh"]["ci_rule"][0] > 0
        d["b"] = d["laugh_minus_breathing"]["ci_rule"][0] > 0
        rule[name] = d
    shape_names = [n for n in cfgs if n.startswith("shape_")]
    a_any = [n for n in shape_names if rule[n]["a"]]
    ab = [n for n in a_any if rule[n]["b"]]
    verdict = "supported" if ab else ("mixed" if a_any else "not supported")
    ep["deltas_vs_published"] = rule
    ep["verdict"] = {"result": verdict, "windows_meeting_a": a_any, "windows_meeting_a_and_b": ab}

    # what the shape columns look like per class: do EPFL laughs show trains at all?
    by_class = {}
    for w in WINDOWS:
        cols = Xs[f"shape_{w[0]}_{w[1]}"][:, -len(SHAPE_NAMES):]
        by_class[f"{w[0]}_{w[1]}"] = {
            k: {"n": int((c == k).sum()),
                "burst_duration_s_median": float(np.median(cols[c == k, 0])),
                "burst_duration_s_q1_q3": [float(np.percentile(cols[c == k, 0], 25)),
                                           float(np.percentile(cols[c == k, 0], 75))],
                "share_more_than_one_peak": float(np.mean(cols[c == k, 1] > 1))}
            for k in ("cough",) + conf}
    ep["shape_columns_by_class"] = by_class

    best = max(shape_names, key=lambda n: ep["configs"][n]["laugh"]["auc"])
    ep["permutation_null"] = {"config": best, "chosen_by": "highest cough-vs-laugh AUC among shape windows",
                              **permutation(Xs[best], y, g, {k: masks[k] for k in conf})}
    report["epfl"] = ep

    # ---- own recordings
    own_scores = {}
    for name, (fn, w) in cfgs.items():
        X, yo, go = own_features(fn, w)
        own_scores[name] = leave_one_session_out(X, yo, go)
    own = {"n_events": int(len(yo)), "configs": {}}
    for name in cfgs:
        s = own_scores[name]
        lo, hi, _ = session_bootstrap_ci(yo, s, go)
        own["configs"][name] = {
            "auc": float(roc_auc_score(yo, s)), "ci95": [lo, hi],
            "per_session_called_cough": {n: float((s[go == n] >= 0.5).mean()) for n in io.SEATED}}
    assert abs(own["configs"]["published"]["auc"] - 0.832) < 0.0006
    report["own"] = own

    # ---- print
    cols = ["overall", *conf]
    print("EPFL, seated, leave-one-subject-out, matched variant. AUC [95% CI, subject bootstrap]")
    print(f"{'configuration':26s} " + " ".join(f"{k:>22s}" for k in cols))
    for name in cfgs:
        e = ep["configs"][name]
        print(f"{name:26s} " + " ".join(
            f"{e[k]['auc']:.3f} [{e[k]['ci95'][0]:.3f}, {e[k]['ci95'][1]:.3f}]" for k in cols))
    print(f"\nChange against published, paired bootstrap ({100 * CI_LEVEL:.2f}% interval for the rule)")
    for name, d in rule.items():
        print(f"{name:26s} " + " ".join(
            f"{d[k]['delta']:+.3f} [{d[k]['ci_rule'][0]:+.3f}, {d[k]['ci_rule'][1]:+.3f}]" for k in cols)
            + f"   laugh-breath {d['laugh_minus_breathing']['delta']:+.3f} "
              f"[{d['laugh_minus_breathing']['ci_rule'][0]:+.3f}, {d['laugh_minus_breathing']['ci_rule'][1]:+.3f}]"
              f"  a={d['a']} b={d['b']}")
    print(f"\nRule: {verdict}")
    for wk, bc in by_class.items():
        print(f"  shape columns, window {wk}: " + ", ".join(
            f"{k} {v['burst_duration_s_median']:.2f} s, >1 peak {100 * v['share_more_than_one_peak']:.0f}%"
            for k, v in bc.items()))
    pn = ep["permutation_null"]
    print(f"Permutation null for {best}: " + ", ".join(
        f"{k} mean {v['mean']:.3f} max {v['max']:.3f}" for k, v in pn.items() if isinstance(v, dict)))
    print("\nOwn seated sessions, leave-one-session-out. AUC [95% CI, session bootstrap]; % called cough")
    for name in cfgs:
        o = own["configs"][name]
        pc = " ".join(f"{100 * v:3.0f}" for v in o["per_session_called_cough"].values())
        print(f"{name:26s} {o['auc']:.3f} [{o['ci95'][0]:.3f}, {o['ci95'][1]:.3f}]   {pc}")
    print("  sessions: " + ", ".join(io.SEATED))

    (args.out / "shape_comparison.json").write_text(json.dumps(report, indent=2))
    print(f"\nwritten to {args.out / 'shape_comparison.json'}")


if __name__ == "__main__":
    main()
