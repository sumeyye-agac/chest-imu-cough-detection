# Verified analysis code for chest-imu-cough-detection

Drop `src/` and `scripts/` into the repository root.

## What is here

    src/chest_imu_cough/io.py         session loading, seated subset, written-down counts
    src/chest_imu_cough/detect.py     transient detector (true peak time, no grid)
    src/chest_imu_cough/features.py   per-event features, normalised per session
    src/chest_imu_cough/evaluate.py   leave-one-session-out, bootstrap CI, permutation, artifact check
    scripts/audit_labels.py           8 checks on the first labelling pass
    scripts/run_analysis.py           the seated cough-vs-confound result

## Expected data layout

    data/sessions/<session_name>.zip          the 12 recordings
    data/legacy_labels/confirmed_events.json  labels from the first pass
    data/legacy_labels/cough_classifier.json  model from the first pass

## Expected output

`scripts/audit_labels.py` ends with `8/8 checks passed`.

`scripts/run_analysis.py` produces, on the seated subset (7 sessions, 80 transients):

    AUC                         0.832   95% CI [0.713, 0.986]
    sensitivity                 0.907
    specificity                 0.514
    permutation null            mean 0.499, max 0.707
    quiet-background artifact   0.595

    per session, fraction called cough
      cough_metronomic_01               13 events    85%
      cough_metronomic_02               13 events    85%
      cough_natural_01_sitting           9 events   100%
      cough_natural_02_sitting           8 events   100%
      baseline_calm_01_sitting           3 events     0%
      baseline_confound_01_talking      22 events    64%
      baseline_confound_02_throatclear  12 events    33%

Small differences in the last digit are possible across scikit-learn versions.
The per-session percentages should be identical.

## What the numbers mean

The AUC interval is wide because the unit of independence is the session and
there are seven of them. Report the interval with the point estimate.

Sensitivity is high and specificity is near chance: transients are found
reliably, and talking and laughing are not separated from coughs. That
direction holds in all four cough sessions and all three confound sessions.

Stage 1 detection shares its input with stage 2, so it is not independent
ground truth. Only the session identity is independent of the signal.
