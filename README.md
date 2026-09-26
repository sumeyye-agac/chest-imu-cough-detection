# chest-imu-cough-detection

Cough detection from a chest-worn motion sensor (IMU), without audio.

Cough monitoring usually relies on a microphone. In a classroom, a shared room,
or a bedroom at night, a microphone records other people and is often not
acceptable. A chest-worn accelerometer and gyroscope record body movement only,
so they can go where a microphone cannot.

## What was found

- **Cough-like movements are detected, when coughs are sparse.** On one adult
  subject, seated, the detector reproduces the counts written down during
  recording (8 of 8, and 12 against 11) and holds that count over a wide range
  of thresholds.
- **They are not separated from laughing.** On that subject, 64% of the
  transients in the talking and laughing session are classified as coughs.
  Across seven seated sessions the cough-vs-confound AUC is 0.832, 95% CI
  [0.713, 0.986].
- **The EPFL cough dataset (15 subjects) adds labels annotated from audio.**
  Against those labels the detector finds 1 cough in 10 (recall 0.098; per
  subject 0.000 to 0.375), and 205 of its 214 detections are real coughs. The
  EPFL recordings are about half coughing, which breaks the detector's
  assumption that transients are rare. Across the 15 subjects, cough vs.
  confound gives AUC 0.765, 95% CI [0.719, 0.803]. Laughing and throat clearing
  are again the least separated from coughing (AUC 0.708 and 0.707).

## Limits

- One subject in this repository's own recordings; 15 in the EPFL data.
- All coughs are voluntary, recorded indoors, at one sensor position.
- The detector's recall on this repository's own protocol, against audio, has
  not been measured. The EPFL measurement comes from a different device,
  sampling rate and protocol.
- In this repository's own recordings the event labels come from the same
  accelerometer the classifier uses. Only the session identity is independent.
- Standing and walking are excluded. Standing needs a different threshold;
  walking cannot be counted with this detector.

## Reproducing

Requires Python 3.10 or later.

    pip install -e .

    # own recordings (included in data/sessions/)
    python scripts/audit_labels.py          # ends with 8/8 checks passed
    python scripts/run_analysis.py          # results/results.json
    python scripts/detector_sensitivity.py  # results/detector_sensitivity.json

    # EPFL dataset (downloaded, about 852 MB; audio deleted after extraction)
    python scripts/fetch_epfl.py
    python scripts/run_epfl.py              # results/epfl_results.json, about 4 minutes

The last digit of some values may differ across scikit-learn versions.

<details>
<summary><b>How the method works</b></summary>

Two stages.

1. **Detection.** Transients are found on the accelerometer magnitude: band-pass
   filter, rectified and smoothed envelope, peaks above a threshold in
   median-absolute-deviations (MAD) of the recording's own envelope, with a
   refractory period between peaks.
2. **Classification.** Each detected transient is classified as cough or not
   by a random forest on band-energy, spectral-shape and duration features.
   Band energies are relative to the same recording's quiet background.

The label for stage 2 comes from what the subject was doing in that recording,
not from the signal. In this repository's own recordings stage 1 is not
independent ground truth: it uses the same accelerometer as stage 2. That is
why the label source matters, and why the EPFL audio annotations were used to
measure the detector.

Evaluation is leave-one-session-out on the single subject and
leave-one-subject-out on EPFL. The 95% interval resamples sessions or subjects,
not events, because events inside one recording are not independent. A
permutation null (labels shuffled) checks that the pipeline does not score by
chance.

Details: [docs/FINDINGS.md](docs/FINDINGS.md).
</details>

<details>
<summary><b>The label audit</b></summary>

The project's first labelling pass took its cough labels from peaks in the
same accelerometer signal it then classified. `scripts/audit_labels.py` checks
eight things about it. It found:

- Two of ten model features (zero-crossing rate on a magnitude signal) were
  identically zero.
- Merged events were labelled at the midpoint of two candidates, 1.13 to
  1.88 s apart, with a 0.5 s tolerance. The label landed where nothing
  happened, and the real events were left negative.
- Candidate times sat on a 0.18825 s grid: the detector reported a window
  position, not the peak.
- 22 of 43 confirmed events were at baseline noise.
- A peak detector matched the written-down counts while seated, not while
  standing or walking.
- The seated cough sessions were all recorded before the confound sessions,
  which is why features are normalised per session.

Details: [docs/LABEL_AUDIT.md](docs/LABEL_AUDIT.md).
</details>

<details>
<summary><b>Detector constants and sensitivity</b></summary>

Band 10-80 Hz, threshold 8 MAD, refractory period 1.0 s. They were set as
round values and checked, not tuned to the written-down counts.
`scripts/detector_sensitivity.py` sweeps each one.

On the seated recordings, the count is exactly 8 at every threshold from 8 to
25. Standing holds at 8 from threshold 11 upward, a higher range than seated,
so one global threshold does not serve both. Walking matches its written-down
count at a single threshold on the way down. Lowering the band's lower edge to
8 or 5 Hz breaks agreement.

On the EPFL data (band 10-45 Hz, because the IMU runs at 100 Hz) the count
does not hold: it falls at every threshold step.

Details: [docs/DETECTOR.md](docs/DETECTOR.md),
[docs/FINDINGS.md](docs/FINDINGS.md), [docs/CROSS_DATASET.md](docs/CROSS_DATASET.md).
</details>

<details>
<summary><b>Cross-dataset results (EPFL, 15 subjects, seated)</b></summary>

Published detector with a 10-45 Hz band. A detection hits a cough if it falls
within 0.2 s of an annotated cough.

| subject | annotated coughs | hit | recall | detections matching no cough | AUC (cough vs. confound) |
|---|---|---|---|---|---|
| 14287 | 123 | 7 | 0.057 | 9 | 0.704 |
| 14342 | 113 | 6 | 0.053 | 0 | 0.914 |
| 14547 | 150 | 7 | 0.047 | 0 | 0.831 |
| 20794 | 72 | 12 | 0.167 | 0 | 0.698 |
| 38936 | 172 | 4 | 0.023 | 0 | 0.594 |
| 47779 | 155 | 0 | 0.000 | 0 | no detected coughs |
| 49661 | 120 | 45 | 0.375 | 0 | 0.739 |
| 55502 | 184 | 13 | 0.071 | 0 | 0.709 |
| 74768 | 148 | 8 | 0.054 | 0 | 0.739 |
| 76918 | 162 | 10 | 0.062 | 0 | 0.590 |
| 84479 | 141 | 11 | 0.078 | 0 | 0.890 |
| 86463 | 131 | 15 | 0.115 | 0 | 0.788 |
| 87369 | 122 | 33 | 0.270 | 0 | 0.691 |
| 87447 | 145 | 31 | 0.214 | 0 | 0.777 |
| 97706 | 156 | 3 | 0.019 | 0 | 0.904 |
| **pooled** | **2,094** | **205** | **0.098** | **9** | **0.765 [0.719, 0.803]** |

Per-subject AUCs rest on 3 to 45 cough transients each.

| | single subject | EPFL |
|---|---|---|
| AUC, 95% CI | 0.832 [0.713, 0.986], 7 sessions | 0.765 [0.719, 0.803], 15 subjects |
| least separated confound | talking and laughing | laugh (0.708), throat clearing (0.707) |
| permutation null, mean | 0.499 | 0.491 |
| quiet-background check | 0.595 | 0.802, not interpretable |

The EPFL quiet-background check fails for a measured reason: 95% of the
"quiet" windows in cough recordings overlap an annotated cough that the
detector missed.

Details: [docs/CROSS_DATASET.md](docs/CROSS_DATASET.md),
[docs/EPFL_DATASET.md](docs/EPFL_DATASET.md).
</details>

<details>
<summary><b>The dataset</b></summary>

`data/sessions/` holds 12 sessions of about two minutes each, recorded from
one adult subject with a chest-worn Movesense sensor, using
[movesense-ecg-hrv-dashboard](https://github.com/sumeyye-agac/movesense-ecg-hrv-dashboard).
Each session is a ZIP with `imu.csv` (accelerometer, gyroscope, magnetometer;
subscribed at 208 Hz, delivered at about 216 Hz), `meta.json` and a
per-capture `README.md`.

ECG, heart rate, RR intervals and temperature were also recorded but are not
published. The metadata still describes those streams, as a record of what was
recorded. The published recordings carry no device identifier.

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

`data/legacy_labels/` holds the labels and model from the first labelling
pass, kept as the subject of the audit.

The EPFL dataset is not in this repository. `scripts/fetch_epfl.py` downloads
it into `data/external/` (gitignored) and keeps only the IMU and the labels.
</details>

## Data policy

The 12 adult recordings are included. Pediatric recordings are never included
in any form. This is not a clinical tool. See
[docs/DATA_POLICY.md](docs/DATA_POLICY.md).

## License

MIT. See [LICENSE](LICENSE).

## References

- Cough-E (EPFL): arXiv:2410.24066. https://arxiv.org/abs/2410.24066
- NC State OOD-Multimodal-CoughDet dataset: Dryad, DOI 10.5061/dryad.mkkwh717r.
  https://doi.org/10.5061/dryad.mkkwh717r
- EPFL edge-AI cough dataset: L. Orlandic et al., "A Multimodal Dataset for
  Automatic Edge-AI Cough Detection", IEEE EMBC 2023,
  doi:10.1109/EMBC40787.2023.10340413. Data: Zenodo 7562332,
  https://zenodo.org/records/7562332, licensed CC-BY 4.0. Used here unmodified
  apart from deleting the audio files after download; not redistributed.
