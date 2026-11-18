# Findings: seated cough vs. confound from a chest-worn IMU

The numbers in this document come from `scripts/run_analysis.py`. The run they
are taken from is recorded in `results/results.json`.

## Scope

- One adult subject.
- Seated sessions only: 7 sessions, about 14.5 minutes of recording.
- 80 detected transients: 43 in cough sessions, 37 in confound sessions.

| session | role |
|---|---|
| `cough_metronomic_01` | cough |
| `cough_metronomic_02` | cough |
| `cough_natural_01_sitting` | cough |
| `cough_natural_02_sitting` | cough |
| `baseline_calm_01_sitting` | confound: quiet sitting |
| `baseline_confound_01_talking` | confound: talking and laughing |
| `baseline_confound_02_throatclear` | confound: throat clearing |

The standing and walking sessions are excluded, for different reasons.

At the default threshold (8 MAD), check 7 of the [label audit](LABEL_AUDIT.md)
shows the detector reproducing the counts written down during recording while
seated (8 written / 8 detected; 11 / 12) but not while standing (8 / 13) or
walking (9 / 28). A sweep over the detector threshold
(`scripts/detector_sensitivity.py`, output in `results/detector_sensitivity.json`)
separates the two cases:

| session (written down) | count across thresholds 6 to 25 MAD |
|---|---|
| `cough_natural_02_sitting` (8) | exactly 8 from threshold 8 to 25 |
| `baseline_confound_02_throatclear` (11) | within one of 11 over a run of 10 thresholds (7 to 16) |
| `cough_natural_03_standing` (8) | exactly 8 from threshold 11 to 25 |
| `cough_natural_04_walking` (9) | falls from 44 to 0; equals 9 only at threshold 10 |

- **Standing:** the events are there. The count holds at 8 over a wide range
  of thresholds, but that range starts higher than the seated one. One global
  threshold does not serve both postures.
- **Walking:** no threshold recovers the written-down count. The count passes
  9 at a single threshold on its way down. That is a crossing, not a property
  of the recording.

The detector keeps one global threshold. Tuning it per posture to match the
written-down counts is the same fitting the label audit is about.

Standing could be brought in with a documented per-posture threshold. That is a
choice not yet made, not an oversight. Walking cannot be brought in with this
detector.

## Method

### Two stages

1. **Detection.** Transients are detected from the accelerometer magnitude
   (`src/chest_imu_cough/detect.py`).
2. **Classification.** Each detected transient is classified as cough or not.
   Its label comes from which session it belongs to, i.e. what the subject was
   doing during that recording, not from the signal.

Stage 1 is **not** independent ground truth. It shares its input, the
accelerometer signal, with stage 2. Only the session identity is independent
of the signal. Only stage 2 is a claim about detection quality.

### Session-relative normalisation

Band energies of each event are expressed relative to the same session's own
quiet background (`src/chest_imu_cough/features.py`). The reason: a model
trained on quiet background windows alone, with no events in them, separates
the two recording blocks at AUC 0.595. With absolute features, the classifier
would absorb that block difference into its result (see check 8 of the
[label audit](LABEL_AUDIT.md)).

### Leave-one-session-out

Each session is held out in turn, and its events are scored by a model trained
on the other six sessions. No session is ever predicted by a model that saw it
in training.

### Session-level bootstrap

The 95% confidence interval for the AUC is computed by resampling whole
sessions, not individual events. Events inside one session share a posture, a
belt position and a moment in time, so they are not independent. Resampling
events would give a narrower interval than the data justify.

## Result

| | |
|---|---|
| AUC | 0.832, 95% CI [0.713, 0.986] (session-level bootstrap, n=1947) |
| Sensitivity | 0.907 |
| Specificity | 0.514 |
| Permutation null (shuffled labels) | mean 0.499, max 0.706 |
| Quiet-background artifact | 0.595 |

Per session, fraction of transients called cough:

| session | events | called cough |
|---|---|---|
| `cough_metronomic_01` | 13 | 85% |
| `cough_metronomic_02` | 13 | 85% |
| `cough_natural_01_sitting` | 9 | 100% |
| `cough_natural_02_sitting` | 8 | 100% |
| `baseline_calm_01_sitting` | 3 | 0% |
| `baseline_confound_01_talking` | 22 | 64% |
| `baseline_confound_02_throatclear` | 12 | 33% |

## What it means

Transients are found reliably. They are not separated from talking and
laughing: 64% of the talking/laughing session's transients are called coughs,
against 33% for throat clearing and 0% for quiet sitting. Quiet sitting is
clean. This direction holds in all four cough sessions and all three confound
sessions.

The permutation null at 0.499 shows the pipeline is not scoring by chance.

The confidence interval is wide because the unit of independence is the
session, and there are seven. The AUC of 0.832 should not be presented without
its interval.

## Burst shape in the talking session

A lead, not a result: one session, one subject.

`scripts/burst_shape.py` (output in `results/burst_shape.json`) measures, for
every detected transient, how long the envelope stays above 3 MAD around the
peak (searched up to 3 s each way) and how many detected transients fall
inside that stretch. Two MAD scales are reported, because the answer depends
on the choice: the background scale (samples more than 2 s from any transient,
as in the peak-height measurement) and the detector's own scale (the whole
recording).

| | background scale | detector scale |
|---|---|---|
| 17 natural seated coughs, burst duration | 0.68 to 2.04 s, median 1.32 | 0.67 to 1.49 s, median 1.07 |
| all 43 seated coughs, transients sharing a burst | 0 | 0 |
| talking session, transients sharing a burst | 10 of 22 | 8 of 22 |
| talking session, transients at 50 MAD or more | 8 | 5 |
| their burst durations | 1.15 to 2.34 s; 6 of 8 in double-peaked bursts | 0.42, 1.03, 1.69, 1.90, 2.30 s; the three longest double-peaked |

What holds on both scales: every seated cough is a single-peaked burst, and in
the talking session 8 to 10 of 22 transients share their burst with a second
detected peak. Duration alone does not separate them on the background scale:
one cough lasts 2.04 s, longer than three of the five double-peaked talking
bursts (1.40 to 2.34 s).

The talking session holds talking and laughing in one recording, so which
transients are laughs is not known. The idea that the double-peaked bursts are
laughs is a hypothesis.

### Tested with a wider window and burst-shape features

`scripts/shape_comparison.py` (output in `results/shape_comparison.json`) adds
an alternative feature set, `src/chest_imu_cough/features_shape.py`: the
published features plus burst duration, the number of detected transients in
the burst, the median interval between them, and burst duration over the main
peak's width at half height. Each is computed over three windows. Published
features over the wider windows alone are run as a control.

| configuration | AUC [95% CI] | talking called cough | throat clearing called cough |
|---|---|---|---|
| published, 0.4 / 0.6 s | 0.832 [0.713, 0.986] | 64% | 33% |
| published features, 0.5 / 2.0 s | 0.856 [0.716, 0.992] | 86% | 25% |
| published features, 1.0 / 2.5 s | 0.855 [0.742, 0.997] | 86% | 17% |
| with burst shape, 0.4 / 0.6 s | 0.820 [0.684, 0.983] | 64% | 33% |
| with burst shape, 0.5 / 2.0 s | 0.857 [0.715, 0.992] | 86% | 17% |
| with burst shape, 1.0 / 2.5 s | 0.871 [0.753, 0.997] | 86% | 17% |

On these sessions the wider windows move the talking session the wrong way:
86% of its transients are called coughs, against 64% as published. The AUC
still rises: throat clearing drops, and one paced-cough session goes from 85%
to 92%. Every interval overlaps the published one.

On EPFL, where laugh is its own class, the result is mixed; see
[CROSS_DATASET.md](CROSS_DATASET.md#burst-shape-and-a-wider-window). The
feature set stays as published.

## Limits

- One subject.
- One session per confound type. A per-confound cross-validated breakdown
  cannot be computed from this data; the per-session percentages above are
  descriptive.
- Event labels still originate from accelerometer peaks, checked only against
  session-level counts written down during recording.
- Voluntary coughs, recorded indoors, with one sensor position.
- 80 events is small; the confidence interval reflects that.

## Label source independent of the accelerometer

This section originally proposed recording audio on a separate device, marking
every cough from it, and measuring what fraction of those coughs the
accelerometer detector finds. The EPFL cough dataset provides that measurement
with someone else's annotations: 15 subjects, seated, coughs annotated from
audio. See [CROSS_DATASET.md](CROSS_DATASET.md).

What was measured, with the published detector (band 10-45 Hz at 100 Hz,
threshold 8 MAD, refractory 1.0 s):

- Recall is 0.098: 205 of 2,094 annotated coughs are detected. Per subject it
  ranges from 0.000 to 0.375, median 0.062.
- 205 of the 214 detections hit an annotated cough.
- The detection count does not hold over a range of thresholds, as it did on
  the seated recordings here. In the EPFL recordings coughs cover about half of
  each recording, and the MAD threshold assumes transients are rare: it lands
  1.74x above the true background. With the baseline and MAD taken from outside
  the annotations, at the same threshold of 8, recall is 0.270 at precision
  0.956.
- Coughs on the EPFL device peak a median 7.5 background MADs above the
  background. On the recordings here they peak a median 88. About half of the
  EPFL coughs never reach a threshold of 8. Against walking, the coughs differ
  by a factor of about 1.5 to 2.5, so most of that gap is a higher EPFL
  background (an order-of-magnitude check; the EPFL units cannot be
  calibrated).
- Cough against confound: AUC 0.765, 95% CI [0.719, 0.803], leave-one-subject-out.
  The feature reference moves it from 0.719 (same rule for both classes,
  contaminated by coughs) to 0.874 (cough-free reference for cough recordings
  only). Neither reference is clean; 0.765 is the reported figure.
  Laughing and throat clearing are the least separated from coughing (AUC 0.708
  and 0.707), deep breathing the most (0.884).

What is still open:

- Recall on this repository's own protocol. The EPFL recordings are short and
  densely packed with coughs; the recordings here have sparse coughs over 2
  minutes, where the detector's count matched the written-down counts. The
  number that bounds the results in this document is the detector's recall on
  recordings like these, against audio. That still needs the recording plan
  above: audio on a separate device, a clap at the start and end to align the
  clocks and correct drift linearly, every cough marked from the audio.
- Whether cough-like movements can be separated from laughing. Both datasets
  put laughing closest to coughing.
- Spontaneous coughs. Both datasets use voluntary coughs.
