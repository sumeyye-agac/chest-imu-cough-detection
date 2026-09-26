# Detector constants

The transient detector (`src/chest_imu_cough/detect.py`) has three constants:

| constant | value |
|---|---|
| band | 10-80 Hz |
| peak threshold | 8 median-absolute-deviations (MAD) |
| refractory period | 1.0 s |

They were not tuned to reproduce the counts written down during recording.
`scripts/detector_sensitivity.py` sweeps each one with the other two held at
their defaults, so a reader can check that instead of taking it on trust.
Its output is in `results/detector_sensitivity.json`.

    python scripts/detector_sensitivity.py

## Band

The band was placed above the low frequencies of posture changes and gait,
which is why it starts at 10 Hz.

The band sweep is consistent with this. Moving the lower edge down to 8 Hz or
5 Hz breaks agreement with the written-down counts. Moving the edges within
10-100 Hz, or the lower edge up to 15 or 20 Hz, keeps the seated count at 8
and the throat clearing count within one of 11:

| band (Hz) | sitting (8) | throat clearing (11) |
|---|---|---|
| 5-80 | 12 | 15 |
| 8-80 | 10 | 13 |
| 10-60 | 8 | 12 |
| 10-80 | 8 | 12 |
| 10-100 | 8 | 12 |
| 15-80 | 8 | 11 |
| 20-80 | 8 | 10 |

## Threshold and refractory period

The threshold (8 MAD) and the refractory period (1.0 s) were set as round
values and then checked. They were not fitted.

The threshold sweep is the check. The seated count is exactly 8 at every
threshold from 8 to 25. The default of 8 is the lowest threshold in that range.

The refractory sweep gives the same seated count, 8, at every value from 1.0 s
to 2.0 s. Below 1.0 s the count rises (12 at 0.75 s, 13 at 0.5 s).

The standing and walking results of the same sweep, and what they mean for
which sessions are analysed, are in [FINDINGS.md](FINDINGS.md).

## Operating assumption

The threshold is set from the recording's own background: the baseline is the
median of the envelope, the scale is its MAD, and a peak must clear baseline +
8 MAD. That assumes events occupy a small share of the recording, so that the
median and the MAD describe the background and not the events.

On the recordings in this repository the assumption holds well enough that the
detected counts match the written-down counts. On the EPFL cough recordings it
does not: annotated coughs cover a median 46% of each recording. There the
median is 1.47x and the MAD 1.82x what they are on the samples outside the
coughs, and the threshold sits 1.74x too high. Recall against the audio
annotations is 0.098 as published and 0.270 with the baseline and MAD taken
from outside the annotations, at the same threshold of 8. See
[CROSS_DATASET.md](CROSS_DATASET.md).

### Why the estimator was not replaced

An estimator that survives dense events is not a free swap. Four were tried on
a trial version of `detect.py`, not kept in the repository: iterative
rejection of samples above 3, 5 and 8 MAD, and a scale taken from the samples
below the median. Each one changed the detected event times at threshold 8 in 8
to 11 of the 12 single-subject sessions.

The closest to the annotation-based result was iterative rejection at 3 MAD:
EPFL recall 0.274 at precision 0.933. On the single subject it gave 98
transients instead of 80, AUC 0.810 instead of 0.832, 7 of 8 audit checks (the
throat-clearing count became 13 against 11 written down), and 70 detections in
the walking session instead of 28.

The reason is that the single subject's recordings are not sparse in the sense
that matters here. In the seated cough, talking and throat-clearing sessions
4% to 10% of the envelope samples lie above the threshold, against a median
0.5% in the EPFL cough recordings. The EPFL contamination sits in the body of
the distribution, not in its upper tail: coughs peak at a median 7.5
background MADs. A rule that corrects the EPFL baseline moves the
single-subject baseline too.

The published estimator stays. Its counts were validated against counts
written down during recording.
