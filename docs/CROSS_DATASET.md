# The method on the EPFL cough dataset

All numbers come from `scripts/run_epfl.py`, recorded in
`results/epfl_results.json`. The dataset and its layout are described in
[EPFL_DATASET.md](EPFL_DATASET.md).

## Scope

- EPFL edge-AI cough dataset (Zenodo 7562332), seated recordings (`mov_sit`)
  only, to match the seated scope of [FINDINGS.md](FINDINGS.md).
- All four background-noise conditions and all trials.
- 15 subjects, all with seated cough and confound recordings.
- 671 recordings: 168 cough, 503 confound (168 laugh, 168 throat clearing,
  167 deep breathing).
- 2,094 coughs annotated from audio in the cough recordings.

The recordings are short: 9 s median for seated cough recordings. Coughs are
dense: annotated coughs cover a median 46% of each cough recording's samples
(21% to 74%). The seated single-subject cough recordings are 2 minutes long,
with 8 to 13 detected transients each.

## What was adapted for 100 Hz

- **Band: 10-45 Hz instead of 10-80 Hz.** The EPFL IMU runs at 100 Hz, so
  anything above 50 Hz does not exist. The lower edge stays at 10 Hz. The
  threshold (8 MAD) and the refractory period (1.0 s) are unchanged.
- **How the band is set.** `detect.py` reads its constants from module
  globals. `epfl.detector_settings()` sets them for the duration of a block and
  restores them afterwards, so the published detector runs without a second
  copy and without editing `detect.py`.
- **Time.** From the sample index at 100 Hz. `imu.csv` has no timestamp column.
- **Features: unchanged.** The published feature set includes a 50-100 Hz band.
  At 100 Hz that band is empty, so 4 of the 24 features (its relative and
  fractional energy, for acc and gyro) are constant and carry nothing.

No unit conversion was needed. The detector is scale-free by construction: the
threshold is in median-absolute-deviations of the recording's own envelope, and
the features are energies relative to the same recording's quiet background,
spectral fractions, a spectral centroid and a duration. Multiplying the signal
by any constant changes none of them. The EPFL accelerometer is in
uncalibrated counts (about 112 at rest), and that never enters. The one
exception is a recording with no quiet window, where the published code falls
back to absolute energies; see below.

## Does the detection count hold over a range of settings?

No. On the seated single-subject recordings the count held at the written-down
value from threshold 8 to 25 ([DETECTOR.md](DETECTOR.md)). Here it falls at
every step, and never approaches the annotated count:

| threshold (MAD) | 3 | 5 | 8 | 10 | 15 | 20 | 25 |
|---|---|---|---|---|---|---|---|
| detections in cough recordings | 749 | 492 | 214 | 118 | 36 | 15 | 4 |
| recall | 0.337 | 0.221 | 0.098 | 0.053 | 0.016 | 0.007 | 0.001 |
| detections matching no cough | 43 | 30 | 9 | 6 | 2 | 1 | 1 |
| detections in confound recordings | 2,212 | 1,402 | 695 | 480 | 230 | 141 | 93 |

The band and refractory sweeps move the count as well. Raising the lower band
edge increases recall (0.056 at 5-45 Hz, 0.098 at 10-45 Hz, 0.177 at 20-45 Hz).
Shortening the refractory period from 2.0 s to 0.25 s raises recall from 0.078
to 0.118. The full sweeps are in `results/epfl_results.json`.

This is consistent with the MAD threshold's assumption failing. The threshold
is set relative to the median and spread of the recording's own envelope. That
works when transients are rare. When coughs fill half of the recording, they
raise the median and the spread, and most of them fall below the threshold.

## Detection recall against labels independent of the accelerometer

Published settings (10-45 Hz, 8 MAD, 1.0 s). A detection hits a cough if it
falls inside [start - 0.2 s, end + 0.2 s]. Each cough can be hit once;
detections are assigned to coughs by maximum one-to-one matching.

| subject | annotated coughs | hit | recall | detections matching no cough |
|---|---|---|---|---|
| 14287 | 123 | 7 | 0.057 | 9 |
| 14342 | 113 | 6 | 0.053 | 0 |
| 14547 | 150 | 7 | 0.047 | 0 |
| 20794 | 72 | 12 | 0.167 | 0 |
| 38936 | 172 | 4 | 0.023 | 0 |
| 47779 | 155 | 0 | 0.000 | 0 |
| 49661 | 120 | 45 | 0.375 | 0 |
| 55502 | 184 | 13 | 0.071 | 0 |
| 74768 | 148 | 8 | 0.054 | 0 |
| 76918 | 162 | 10 | 0.062 | 0 |
| 84479 | 141 | 11 | 0.078 | 0 |
| 86463 | 131 | 15 | 0.115 | 0 |
| 87369 | 122 | 33 | 0.270 | 0 |
| 87447 | 145 | 31 | 0.214 | 0 |
| 97706 | 156 | 3 | 0.019 | 0 |
| **pooled** | **2,094** | **205** | **0.098** | **9** |

Per-subject recall: min 0.000, first quartile 0.050, median 0.062, third
quartile 0.141, max 0.375.

The detector finds about one cough in ten, and what it finds is almost always
a cough: 205 of 214 detections hit an annotated cough. All 9 that match nothing
come from one subject.

## Cough vs. confound

Same two-stage design as [FINDINGS.md](FINDINGS.md). Detected transients are
the units. The label comes from the recording's class: cough recordings
positive; laugh, throat clearing and deep breathing negative. Features and
session-relative normalisation are the published ones, with each recording as
a session. Leave-one-subject-out; the bootstrap resamples subjects.

- **Matched** (primary): in cough recordings, only detections that hit an
  annotated cough.
- **All detections**: every detection in a cough recording counts as positive,
  as in the single-subject analysis.

| | matched | all detections |
|---|---|---|
| transients (cough / confound) | 900 (205 / 695) | 909 (214 / 695) |
| AUC | 0.765 | 0.767 |
| 95% CI (subject-level bootstrap, n=2000) | [0.719, 0.803] | [0.723, 0.809] |
| sensitivity at 0.5 | 0.127 | 0.136 |
| specificity at 0.5 | 0.978 | 0.980 |
| AUC, cough vs. laugh | 0.708 | 0.719 |
| AUC, cough vs. throat clearing | 0.707 | 0.707 |
| AUC, cough vs. deep breathing | 0.884 | 0.881 |
| permutation null (30 rounds) | mean 0.491, max 0.545 | mean 0.502, max 0.558 |

Per-subject AUC (matched), 14 subjects with both classes: min 0.590, median
0.739, max 0.914. Subject 47779 has no detected coughs. Several subjects have 3
to 8 cough transients, so their individual AUCs rest on few events.

The two variants differ by 9 events, because only 9 detections in cough
recordings match nothing. This comparison therefore cannot show what label
quality is worth on this data: at 8 MAD the detector almost never fires outside
a cough.

Sensitivity and specificity at a 0.5 cut-off follow the class balance: 205
cough against 695 confound transients, where the single-subject analysis had
43 against 37. The AUCs, including cough against each confound, do not depend
on a cut-off.

## Permutation and background checks

The permutation null sits at 0.49 to 0.50, so the pipeline is not scoring by
chance.

The quiet-background check does not work on this data. A model trained on
windows away from any detection separates cough recordings from confound
recordings at AUC 0.802 (4,008 windows). But 873 of the 920 "quiet" windows in
cough recordings (95%) overlap an annotated cough. The detector misses nine
coughs in ten, so the windows it treats as background are mostly undetected
coughs. The check measures that, not a recording-block difference.

The same problem reaches the features. The session-relative normalisation
divides each event's band energies by the recording's quiet background, and in
cough recordings that background is mostly coughing. 163 transients come from
recordings with no window far enough from a detection, where the published code
falls back to absolute energies. Without them the matched AUC is 0.750
[0.712, 0.787] on 737 transients.

## One subject against fifteen

| | single subject, seated ([FINDINGS.md](FINDINGS.md)) | EPFL, 15 subjects, seated |
|---|---|---|
| unit of independence | session (7) | subject (15) |
| transients (cough / confound) | 80 (43 / 37) | 900 (205 / 695), matched |
| AUC | 0.832 | 0.765 |
| 95% CI | [0.713, 0.986] | [0.719, 0.803] |
| least separated confound | talking and laughing (64% called cough) | laugh (AUC 0.708) and throat clearing (0.707) |
| most separated confound | quiet sitting (0% called cough) | deep breathing (AUC 0.884) |
| quiet-background check | 0.595 | 0.802, not interpretable (see above) |
| detection vs. independent count | 8 / 8 and 11 / 12 against written-down counts | recall 0.098 against audio labels |

The single-subject AUC of 0.832 is above the EPFL interval, and inside the
range of EPFL per-subject AUCs (0.590 to 0.914). The EPFL interval is narrower
because it rests on 15 subjects instead of 7 sessions. The ordering of the
confounds is the same in both: laughing is the hardest to separate from
coughing, quiet breathing or sitting the easiest.

The detection results do not contradict each other. They come from different
protocols. The single-subject recordings have sparse coughs in 2 minutes, where
the MAD threshold's assumption holds; the EPFL recordings are about half
coughing.

## Limits

- A different device: the EPFL sensor is not the Movesense, its units are
  uncalibrated counts, and it is not documented whether its gyroscope columns
  are rates or angles.
- A different sampling rate: 100 Hz instead of about 216 Hz. The band had to
  change, and 4 features are constant.
- A different protocol: short recordings, densely packed coughs, and the
  laugh, throat-clearing and breathing classes instead of talking.
- The coughs are still voluntary.
- The detector's constants were set on the single-subject recordings and kept
  here. On this data the count moves with every setting, and recall is 0.098.
  Tuning the detector to the EPFL labels would be possible, and would be
  fitting to them.
- The quiet-background check and the session-relative normalisation both
  assume the detector finds most events. Here it does not.
