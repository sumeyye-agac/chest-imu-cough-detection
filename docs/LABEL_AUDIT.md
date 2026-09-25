# Label audit of the first labelling pass

This is an audit of this project's own first labelling pass: the candidate
detector, the merge step, the confirmed event labels and the first classifier
that were produced before the current analysis. The label files it examines are
kept in `data/legacy_labels/` (`confirmed_events.json`, `cough_classifier.json`),
and the status document from that pass is kept in
[legacy/2026-09-21-first-pass-status.md](legacy/2026-09-21-first-pass-status.md).

Each of the eight checks in `scripts/audit_labels.py` re-derives one claim from
the raw recordings in `data/sessions/` and the legacy label files, and prints
PASS or FAIL. A PASS means the problem described is confirmed to be present.
The numbers below are those printed by the script.

## 1. Two model weights are exactly zero

Two of the ten features in the first model had weights of exactly 0.0, and
they were the two zero-crossing-rate features (`acc_zero_crossing_rate`,
`gyro_zero_crossing_rate`).

## 2. Zero-crossing rate on a magnitude signal is identically zero

Zero-crossing rate was computed on the accelerometer and gyroscope magnitude.
A magnitude is non-negative by construction, so it never crosses zero: the
script finds a sign change in 0 of 24 session-channels (12 sessions x 2
channels). Those two features carried nothing, which is why their weights in
check 1 are zero.

## 3. Merged events are labelled at the midpoint

When two candidate events were merged into one, the label was written at their
arithmetic midpoint. All 6 merged pairs do this (merged pairs whose midpoint is
absent from the confirmed events: 0 of 6).

## 4. The midpoint label reaches neither candidate

The label-matching tolerance was 0.5 s. Every merged pair is 1.13-1.88 s wide,
so the half-gap is always larger than the tolerance (pairs with half-gap
<= 0.5 s: 0 of 6). In all 6 cases neither original candidate falls inside the
label window.

**Effect of checks 3 and 4 on the data:** each merge places a positive label at
a time where nothing happened, and leaves the real event, at either candidate
time, labelled negative.

## 5. Candidate times are quantised

Candidate times sit on a 0.18825 s grid: all 17 close-pair gaps are integer
multiples of it, with a largest deviation of 0.0053 steps. The detector was
reporting a window position rather than the time of the peak.

## 6. Many confirmed events are at baseline noise

22 of the 43 confirmed events sit below 1.0 m/s^2 local excursion from 9.81
m/s^2 (within +/-0.3 s of the label), i.e. at baseline noise. In
`cough_natural_02_sitting`, 7 of 8 do.

**Effect on the data:** roughly half of the positive labels are uninformative.

## 7. Detected counts agree with written-down counts only while seated

A detector that reports the true peak time (`src/chest_imu_cough/detect.py`)
was compared against the counts written down during recording:

| session | written down | detected | |
|---|---|---|---|
| `cough_natural_02_sitting` | 8 | 8 | match |
| `baseline_confound_02_throatclear` | 11 | 12 | match |
| `cough_natural_03_standing` | 8 | 13 | mismatch |
| `cough_natural_04_walking` | 9 | 28 | mismatch |

It reproduces the written-down counts while seated but not while standing or
walking. This is the reason the analysis in [FINDINGS.md](FINDINGS.md) is
restricted to seated sessions.

## 8. Recording time is confounded with the label

In the seated subset, the four cough sessions were all recorded before the
three confound sessions (last cough session started 10:27:04, first confound
session started 10:30:12). Recording time is perfectly confounded with the
label.

**Effect on the data:** a classifier could separate the two groups by
anything that drifted between the two recording blocks rather than by the
events themselves. This is why features are normalised per session; see
[FINDINGS.md](FINDINGS.md).

## Re-running the audit

From the repository root, with the package installed (`pip install -e .`):

    python scripts/audit_labels.py

The script ends with `8/8 checks passed` when every finding above is
reproduced. It exits with a non-zero status if any check fails, and lists the
failed checks.
