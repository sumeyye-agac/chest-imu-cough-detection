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
