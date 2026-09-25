"""Leave-one-session-out evaluation with session-level uncertainty.

Sessions, not events, are the unit of independence: events inside one session
share a posture, a belt position and a moment in time. Bootstrapping over
events gives a narrower interval that is not justified by the data.
"""
from __future__ import annotations
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

RANDOM_STATE = 0


def _model(n_estimators: int = 500) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=n_estimators, min_samples_leaf=3, random_state=RANDOM_STATE, n_jobs=-1
    )


def leave_one_session_out(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray, n_estimators: int = 500
) -> np.ndarray:
    """Out-of-fold scores; each session is predicted by a model that never saw it."""
    scores = np.zeros(len(y), dtype=float)
    for name in dict.fromkeys(groups.tolist()):
        held = groups == name
        if len(set(y[~held])) < 2:
            raise ValueError(f"holding out {name} leaves a single class in training")
        scores[held] = (
            _model(n_estimators).fit(X[~held], y[~held]).predict_proba(X[held])[:, 1]
        )
    return scores


def confusion(y: np.ndarray, scores: np.ndarray, threshold: float = 0.5) -> dict:
    pred = scores >= threshold
    tp = int((pred & (y == 1)).sum())
    fn = int((~pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    tn = int((~pred & (y == 0)).sum())
    return {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "sensitivity": tp / (tp + fn) if tp + fn else float("nan"),
        "specificity": tn / (tn + fp) if tn + fp else float("nan"),
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
    }


def session_bootstrap_ci(y, scores, groups, n_boot: int = 2000, seed: int = 0):
    """95% interval for AUC, resampling whole sessions."""
    rng = np.random.default_rng(seed)
    names = np.array(list(dict.fromkeys(groups.tolist())))
    draws = []
    for _ in range(n_boot):
        picked = rng.choice(names, size=len(names), replace=True)
        yy = np.concatenate([y[groups == s] for s in picked])
        ss = np.concatenate([scores[groups == s] for s in picked])
        if len(set(yy)) < 2:
            continue
        draws.append(roc_auc_score(yy, ss))
    draws = np.array(draws)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)), len(draws)


def permutation_null(X, y, groups, n_rounds: int = 30, seed: int = 0):
    """AUC when the labels are shuffled: shows what the pipeline scores by chance."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_rounds):
        shuffled = rng.permutation(y)
        try:
            out.append(
                roc_auc_score(
                    shuffled, leave_one_session_out(X, shuffled, groups, n_estimators=150)
                )
            )
        except ValueError:
            continue
    return float(np.mean(out)), float(np.max(out)), len(out)


def background_artifact_auc(X_quiet, y_quiet, groups_quiet):
    """AUC from quiet background windows alone.

    0.5 means the two groups of sessions are indistinguishable when nothing is
    happening. Anything higher is a session or recording-block difference that
    an event-level result would otherwise absorb.
    """
    return float(roc_auc_score(y_quiet, leave_one_session_out(X_quiet, y_quiet, groups_quiet)))
