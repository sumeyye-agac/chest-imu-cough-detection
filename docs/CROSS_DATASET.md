# The method on the EPFL cough dataset

The published EPFL numbers come from `scripts/run_epfl.py`, recorded in
`results/epfl_results.json`. The threshold-placement measurements and the
annotation-based reference come from `scripts/threshold_placement.py`, recorded
in `results/threshold_placement.json`. Neither script changes the detector. The dataset and its layout are described in
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

### The published number

Published detector (10-45 Hz, 8 MAD, 1.0 s refractory). A detection hits a
cough if it falls inside [start - 0.2 s, end + 0.2 s]. Each cough can be hit
once; detections are assigned to coughs by maximum one-to-one matching.

Recall is 0.098: 205 of 2,094 annotated coughs. Precision is 0.958: 205 of 214
detections hit a cough, and the 9 that miss all come from one subject. A
detector that fires rarely and is nearly always right has its threshold in the
wrong place.

### Why the threshold is too high on this data

The detector sets its threshold from the recording's own envelope: baseline is
the median, scale is the MAD, and a peak must exceed baseline + 8 MAD. That
assumes events occupy a small share of the recording. In the EPFL cough
recordings annotated coughs cover a median 46% of the samples, so the median
and the MAD are partly computed on coughs.

Measured against the samples outside annotated coughs, per cough recording
(medians over 168 recordings):

| | whole recording / outside annotated coughs |
|---|---|
| baseline (median of the envelope) | 1.47x |
| scale (MAD) | 1.82x |
| 8-MAD threshold | 1.74x |

The published threshold sits 1.74 times higher than it would on the true
background.

### What a correctly placed threshold reaches

Same detector, same threshold of 8 and refractory period of 1.0 s, but the
baseline and MAD taken from samples outside annotated coughs. This uses the
annotations to place the threshold, so it is a bound on what the published
threshold placement costs on this dataset, not a detector anyone can run
without labels.

| subject | annotated | published recall | published precision | recall, background from annotations | precision, background from annotations |
|---|---|---|---|---|---|
| 14287 | 123 | 0.057 | 0.438 | 0.146 | 0.514 |
| 14342 | 113 | 0.053 | 1.000 | 0.177 | 1.000 |
| 14547 | 150 | 0.047 | 1.000 | 0.080 | 0.923 |
| 20794 | 72 | 0.167 | 1.000 | 0.375 | 0.931 |
| 38936 | 172 | 0.023 | 1.000 | 0.128 | 1.000 |
| 47779 | 155 | 0.000 | no detections | 0.200 | 0.969 |
| 49661 | 120 | 0.375 | 1.000 | 0.583 | 1.000 |
| 55502 | 184 | 0.071 | 1.000 | 0.109 | 1.000 |
| 74768 | 148 | 0.054 | 1.000 | 0.264 | 0.975 |
| 76918 | 162 | 0.062 | 1.000 | 0.333 | 1.000 |
| 84479 | 141 | 0.078 | 1.000 | 0.376 | 1.000 |
| 86463 | 131 | 0.115 | 1.000 | 0.282 | 0.974 |
| 87369 | 122 | 0.270 | 1.000 | 0.434 | 0.981 |
| 87447 | 145 | 0.214 | 1.000 | 0.352 | 0.962 |
| 97706 | 156 | 0.019 | 1.000 | 0.378 | 1.000 |
| **pooled** | **2,094** | **0.098** (205 / 214 detections) | **0.958** | **0.270** (566 / 592 detections) | **0.956** |

Recall rises from 0.098 to 0.270 and precision stays at 0.956. Placing the
threshold on the true background recovers coughs that were there, not noise.
The refractory period now matters too: coughs arrive about every 0.8 s, and
the detector allows at most one detection per 1.0 s.

### How far coughs rise above background, on each device

Recall of 0.270 with a correctly placed threshold is still low. The reason is
how far a cough rises above the background. For each cough, the peak of the
envelope in units of the background MAD:

- EPFL: background from samples outside annotated coughs; peak inside the
  annotated interval.
- Single subject, seated cough sessions: background from samples more than 2 s
  from a detected transient; peak at the detected transient.

| | coughs | median | quartiles | min to max | share above 8 |
|---|---|---|---|---|---|
| EPFL, 15 subjects, annotated coughs | 2,094 | 7.5 | 4.2 to 12.7 | -1.2 to 64.6 | 47% |
| single subject, detected transients | 43 | 87.6 | 75.7 to 95.9 | 13.1 to 185.8 | 100% |
| single subject, same transients, 10-45 Hz envelope | 43 | 78.1 | 69.9 to 87.4 | 12.3 to 169.8 | 100% |
| single subject, legacy confirmed labels | 33 | 44.0 | 7.5 to 73.2 | 1.5 to 125.6 | 73% |

EPFL per-subject medians range from 2.8 to 19.0 (quartiles of the subject
medians 5.3 to 10.4). Single-subject per-session medians range from 74.9 to
98.6.

The single-subject figure for detected transients is selected: a transient is
only detected if it clears the threshold. `cough_natural_02_sitting` is the
exception that removes the selection: its 8 detections match its 8
written-down coughs, and they peak at 79.3 to 185.8 background MADs, median
98.6. The 10-45 Hz row shows the difference is not the band. The legacy labels
sit lower because the label audit found half of them placed at baseline noise.

What this means for a fixed threshold of 8: on the single subject's recordings
every cough clears it by a factor of about ten. On the EPFL recordings the
median cough sits just below it, and 53% of coughs do not reach it even with
the baseline on the true background. The same threshold that has a wide margin on one device has
none on the other.

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
[0.712, 0.787] on 737 transients. The next section replaces this reference with
one taken from the annotations.

## Feature reference from the annotations

The published feature normalisation divides each event's band energies by the
recording's quiet background, taken from windows more than 2 s from any
detection. In EPFL cough recordings 873 of those 920 windows (95%) overlap an
annotated cough. The reference level is not quiet.

Here the reference comes from windows that overlap no annotated cough. The
annotations set that reference level only. They are never a feature and never
a label: the label is still the recording's class, and the features are still
computed from the accelerometer around each detection.

Two decisions this needed:

- **Window length 0.5 s for every recording.** Only 50 of 168 seated cough
  recordings contain a 1 s window free of annotated coughs; 167 contain a
  0.5 s one. Using 0.5 s for cough recordings only would give the two classes
  differently defined references, so every recording, cough and confound, uses
  0.5 s windows.
- **Events without a reference window are dropped.** The published code falls
  back to absolute energies when a recording has no quiet window. That mixes
  scaled and unscaled features. Here those events are dropped instead: 80
  events.

Confound recordings have no annotations. Their reference keeps the published
rule: windows more than 2 s from any detection. The literal alternative, every
window of a confound recording, is reported as well.

| | published | annotation reference (primary) | annotation reference, confound: all windows |
|---|---|---|---|
| reference windows, cough recordings | 1 s, 2 s from detections | 0.5 s, no annotated cough | 0.5 s, no annotated cough |
| reference windows, confound recordings | 1 s, 2 s from detections | 0.5 s, 2 s from detections | 0.5 s, all |
| transients (cough / confound) | 900 (205 / 695) | 820 (204 / 616) | 899 (204 / 695) |
| AUC | 0.765 | 0.874 | 0.904 |
| 95% CI (subject-level bootstrap) | [0.719, 0.803] | [0.803, 0.924] | [0.848, 0.949] |
| AUC, cough vs. laugh | 0.708 | 0.872 | 0.950 |
| AUC, cough vs. throat clearing | 0.707 | 0.856 | 0.879 |
| AUC, cough vs. deep breathing | 0.884 | 0.892 | 0.896 |
| permutation null, mean / max | 0.491 / 0.545 | 0.484 / 0.551 | 0.494 / 0.569 |
| quiet-background check | 0.802 | 0.662 | 0.662 |

The background check falls from 0.802 to 0.662 but does not reach 0.5. The
reference windows still differ between the classes. In cough recordings they
are the short gaps between coughs; in confound recordings they are windows away
from detections, which can still hold laughs, throat clearing or breaths the
detector missed. A model separates those two kinds of window at 0.662. Part of
the rise from 0.765 to 0.874 can come from that difference rather than from the
events. The 0.874 is therefore an upper estimate, and the reference asymmetry
cannot be removed without annotations for the confound recordings.

Two diagnostics with 1 s windows (in `results/threshold_placement.json`) give
AUC 0.920 with the published fallback kept for 213 events, and 0.923 with those
events dropped, on 84 cough transients.

## One subject against fifteen

| | single subject, seated ([FINDINGS.md](FINDINGS.md)) | EPFL, 15 subjects, seated |
|---|---|---|
| unit of independence | session (7) | subject (15) |
| transients (cough / confound) | 80 (43 / 37) | 900 (205 / 695), matched; 820 with the annotation reference |
| AUC, published reference | 0.832 [0.713, 0.986] | 0.765 [0.719, 0.803] |
| AUC, annotation reference | not applicable | 0.874 [0.803, 0.924], upper estimate |
| least separated confound | talking and laughing (64% called cough) | laugh (0.708) and throat clearing (0.707); with the annotation reference throat clearing (0.856) and laugh (0.872) |
| most separated confound | quiet sitting (0% called cough) | deep breathing (0.884; 0.892) |
| quiet-background check | 0.595 | 0.802, not interpretable; 0.662 with the annotation reference |
| detection vs. independent count | 8 / 8 and 11 / 12 against written-down counts | recall 0.098 against audio labels; 0.270 with the threshold on the true background |
| cough peak height, background MADs | median 87.6 (98.6 in the session with all coughs written down) | median 7.5 |

With the published reference, the single-subject AUC of 0.832 is above the
EPFL interval and inside the range of EPFL per-subject AUCs (0.590 to 0.914).
With the annotation reference, the EPFL interval [0.803, 0.924] contains 0.832.
The EPFL interval is narrower because it rests on 15 subjects instead of 7
sessions. In both datasets laughing and throat clearing are the hardest
confounds to separate from coughing, and quiet breathing or sitting the
easiest.

The detection results come from different recordings, not a contradiction.
On the single subject's device a cough rises a median 88 background MADs above
the background, and the count matches what was written down. On the EPFL
device it rises a median 7.5, and the recordings are about half coughing,
which also lifts the threshold 1.74x above the true background.

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
  here. On this data the count moves with every setting. Recall is 0.098 as
  published and 0.270 with the threshold on the true background. Tuning the
  detector to the EPFL labels would be fitting to them.
- The published threshold placement assumes events occupy a small share of the
  recording. The EPFL cough recordings violate it. An estimator that survives
  dense events also changes the single-subject event times (see
  [DETECTOR.md](DETECTOR.md)), so the published detector is kept.
- The annotation-based reference exists only for cough recordings. Confound
  recordings keep a detection-based reference, and the background check (0.662)
  shows the two still differ.
