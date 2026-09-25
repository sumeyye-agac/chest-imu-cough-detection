#!/usr/bin/env python3
"""Audit of the first labelling pass.

Each check re-derives one claim from the raw recordings and the label files
that the earlier pipeline produced. Every check prints PASS or FAIL so the
findings in docs/LABEL_AUDIT.md can be confirmed rather than taken on trust.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chest_imu_cough.io import load_session, STATED_COUNTS
from chest_imu_cough.detect import detect_events

DATA = Path("data/sessions")
LEGACY = Path("data/legacy_labels")
LABEL_TOLERANCE_S = 0.5     # the tolerance the first pipeline used
GRID_S = 0.18825            # candidate quantisation found in check 5
results: list[tuple[str, bool]] = []


def check(name: str, passed: bool) -> None:
    results.append((name, passed))
    print(f"  -> {'PASS' if passed else 'FAIL'}\n")


def excursion(session, t0: float, half_width: float = 0.3) -> float:
    m = (session.t >= t0 - half_width) & (session.t <= t0 + half_width)
    return float(np.abs(session.acc[m] - 9.81).max()) if m.any() else 0.0


def main() -> None:
    events = json.loads((LEGACY / "confirmed_events.json").read_text())
    clf = json.loads((LEGACY / "cough_classifier.json").read_text())
    sessions = {p.stem: load_session(p) for p in sorted(DATA.glob("*.zip"))}

    print("1. Two trained weights are exactly zero, and they are the zero-crossing features")
    zeros = [(n, w) for n, w in zip(clf["feature_order"], clf["weights"]) if w == 0.0]
    print(f"   {zeros}")
    check("zero weights are the ZCR features",
          len(zeros) == 2 and all("zero_crossing" in n for n, _ in zeros))

    print("2. Zero-crossing rate on a magnitude signal is identically zero")
    nonzero = sum(
        1 for s in sessions.values() for x in (s.acc, s.gyro)
        if np.sum(np.diff(np.sign(x)) != 0) != 0
    )
    print(f"   channels with any sign change: {nonzero} of {2 * len(sessions)}")
    check("magnitude never crosses zero", nonzero == 0)

    print("3. Every merged event is the arithmetic midpoint of its two candidates")
    missing = sum(
        1 for info in events.values() for a, b in info["merged_pairs"]
        if not any(abs(e - (a + b) / 2) < 1e-3 for e in info["confirmed_events_t_unix"])
    )
    total_pairs = sum(len(i["merged_pairs"]) for i in events.values())
    print(f"   merged pairs whose midpoint is absent: {missing} of {total_pairs}")
    check("merge writes the midpoint", missing == 0 and total_pairs > 0)

    print("4. For every merged pair, both candidates lie outside the label tolerance")
    inside = sum(
        1 for info in events.values() for a, b in info["merged_pairs"]
        if (b - a) / 2 <= LABEL_TOLERANCE_S
    )
    print(f"   pairs with half-gap <= {LABEL_TOLERANCE_S}s: {inside} of {total_pairs}")
    check("midpoint label reaches neither candidate", inside == 0)

    print(f"5. Close-pair gaps are integer multiples of a {GRID_S}s grid")
    gaps = []
    for info in events.values():
        raw = sorted(set(info["confirmed_events_t_unix"]
                         + [x for p in info["merged_pairs"] for x in p]))
        gaps += [g for g in np.diff(raw) if g < 2.5]
    steps = np.array(gaps) / GRID_S
    deviation = float(np.abs(steps - np.round(steps)).max())
    print(f"   {len(gaps)} gaps, largest deviation {deviation:.4f} steps")
    check("candidate times are quantised", deviation < 0.02)

    print("6. A large share of confirmed events sit at baseline noise")
    weak = total = 0
    for name, info in events.items():
        s = sessions[name]
        for e in info["confirmed_events_t_unix"]:
            total += 1
            weak += excursion(s, e) < 1.0
    print(f"   {weak} of {total} confirmed events below 1.0 m/s^2 excursion")
    check("labels include events with no signal", weak > 0)

    print("7. A peak detector reproduces the written-down counts while seated only")
    for name, stated in STATED_COUNTS.items():
        n = len(detect_events(sessions[name]))
        verdict = "match" if abs(n - stated) <= 1 else "MISMATCH"
        print(f"   {name:34s} written down={stated:2d} detected={n:2d}  {verdict}")
    seated_ok = all(
        abs(len(detect_events(sessions[n])) - c) <= 1
        for n, c in STATED_COUNTS.items() if "standing" not in n and "walking" not in n
    )
    moving_off = all(
        abs(len(detect_events(sessions[n])) - c) > 1
        for n, c in STATED_COUNTS.items() if "standing" in n or "walking" in n
    )
    check("counts agree seated, disagree standing/walking", seated_ok and moving_off)

    print("8. Seated cough sessions were all recorded before the confound sessions")
    starts = {n: s.meta["started_utc"] for n, s in sessions.items() if "sitting" in n
              or n.startswith(("cough_metronomic", "baseline_confound"))}
    last_cough = max(t for n, t in starts.items() if n.startswith("cough"))
    first_conf = min(t for n, t in starts.items() if n.startswith("baseline"))
    print(f"   last cough {last_cough[11:19]}, first confound {first_conf[11:19]}")
    check("recording blocks are separated in time", last_cough < first_conf)

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("failed: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
