# chest-imu-cough-detection

Cough detection from a chest-worn inertial measurement unit (IMU), without audio.

On one adult subject, seated, coughs are detected reliably but are not
separated from talking and laughing: 64% of transients in the talking/laughing
session are classified as coughs. Across seven seated sessions the
cough-vs-confound AUC is 0.832, with a 95% confidence interval of
[0.713, 0.986] (sensitivity 0.907, specificity 0.514).

## What this repository contains

- 12 recording sessions from one adult subject, in `data/sessions/`.
- An audit of the project's own first labelling pass:
  [docs/LABEL_AUDIT.md](docs/LABEL_AUDIT.md).
- A leave-one-session-out analysis of seated cough vs. confound sessions:
  [docs/FINDINGS.md](docs/FINDINGS.md).
- The code for both, in `src/chest_imu_cough/` and `scripts/`.

## Result

| | |
|---|---|
| AUC | 0.832, 95% CI [0.713, 0.986] (session-level bootstrap) |
| Sensitivity | 0.907 |
| Specificity | 0.514 |
| Permutation null | mean 0.499, max 0.706 |

Scope: one subject, seated only, 7 sessions, 80 detected transients. Standing
and walking sessions are excluded because the labelling method is measurably
unreliable once the subject moves. See [docs/FINDINGS.md](docs/FINDINGS.md) for the method,
the per-session breakdown and the limits, and
[docs/LABEL_AUDIT.md](docs/LABEL_AUDIT.md) for the audit.

## Reproducing

Requires Python 3.10 or later.

    pip install -e .
    python scripts/audit_labels.py
    python scripts/run_analysis.py

`audit_labels.py` should end with `8/8 checks passed`. `run_analysis.py` prints
the result above and writes it to `results/results.json`. The last digit of
some values may differ across scikit-learn versions.

## Dataset

12 sessions of about two minutes each, recorded from one adult subject with a
chest-worn Movesense sensor, using
[movesense-ecg-hrv-dashboard](https://github.com/sumeyye-agac/movesense-ecg-hrv-dashboard).
Each session is a ZIP file containing `imu.csv` (accelerometer, gyroscope,
magnetometer; subscribed at 208 Hz, delivered at about 216 Hz), `meta.json`
and a per-capture `README.md` describing the format.

ECG, heart rate, RR intervals and temperature were also recorded but are not
published. `meta.json` and the per-capture `README.md` still describe those
streams, as a record of what was recorded, but their data files are not
included. The published recordings carry no device identifier.

The session name gives the activity:

| session | activity |
|---|---|
| `cough_metronomic_01`, `_02` | paced coughing, seated |
| `cough_natural_01_sitting`, `_02_sitting` | natural coughing, seated |
| `cough_natural_03_standing` | natural coughing, standing |
| `cough_natural_04_walking` | natural coughing, walking |
| `baseline_calm_01_sitting` | quiet sitting |
| `baseline_calm_02_standing` | quiet standing |
| `baseline_confound_01_talking` | talking and laughing, seated |
| `baseline_confound_02_throatclear` | throat clearing, seated |
| `baseline_movement_01_walking` | walking |
| `baseline_movement_02_reaching` | arm movement |

`data/legacy_labels/` holds the labels and the model from the first labelling
pass, kept as the subject of the audit.

## Data policy

The 12 adult recordings are included. Pediatric recordings are never included
in any form. This is not a clinical tool. See
[docs/DATA_POLICY.md](docs/DATA_POLICY.md).

## References

- Cough-E (EPFL): arXiv:2410.24066. https://arxiv.org/abs/2410.24066
- EPFL edge-ai-cough-count dataset: Zenodo 7562332.
  https://zenodo.org/records/7562332
- NC State OOD-Multimodal-CoughDet dataset: Dryad, DOI 10.5061/dryad.mkkwh717r.
  https://doi.org/10.5061/dryad.mkkwh717r

## License

MIT. See [LICENSE](LICENSE).
