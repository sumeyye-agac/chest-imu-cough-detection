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

## Limits

- One subject.
- One session per confound type. A per-confound cross-validated breakdown
  cannot be computed from this data; the per-session percentages above are
  descriptive.
- Event labels still originate from accelerometer peaks, checked only against
  session-level counts written down during recording.
- Voluntary coughs, recorded indoors, with one sensor position.
- 80 events is small; the confidence interval reflects that.

## Next step

The remaining circularity can only be broken with a label source that is
independent of the accelerometer. The concrete plan:

1. Record a session with audio captured on a separate device.
2. Clap at the start and at the end of the session, to align the two clocks
   and to correct drift between them linearly.
3. Mark every cough from the audio.
4. Measure what fraction of those audible coughs the accelerometer-based
   detector finds.

That single number converts the main caveat into a measurement, and bounds
everything reported here.
