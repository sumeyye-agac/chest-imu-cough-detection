# Data Policy

## Adult recordings: included

The 12 session recordings in `data/sessions/` are recordings of one adult
subject. The subject is an adult who consented to publication of these
recordings. They are included in this repository and published under this
repository's licence (see `LICENSE`). The first-pass label files in
`data/legacy_labels/` are published on the same terms.

Only the IMU stream is published. Each recording contains `imu.csv`,
`meta.json` and a per-capture `README.md`. ECG, heart rate, RR intervals and
skin temperature were recorded in the same sessions but are not published in
this repository in any form. The metadata keeps its description of those
streams so that the record of what was recorded stays accurate; it contains no
samples from them. The device identifier of the sensor has been removed from
the published files.

These 12 files are listed by exact filename in `.gitignore`. Any other file
placed under `data/` is ignored by git unless it is deliberately added there.

## Pediatric recordings: never included

The project may also use recordings from a pediatric subject. That subject is
not of an age to give consent, so these recordings are never included in this
repository, under any circumstances and in any form: not as raw recordings,
not as segmented windows, and not as extracted per-event or per-window
features.

Only aggregate summary statistics and model results derived from such
recordings may be shared here.

## Public datasets

Public datasets referenced by this project (EPFL edge-ai-cough-count, Zenodo
record 7562332; NC State OOD-Multimodal-CoughDet, Dryad DOI
10.5061/dryad.mkkwh717r) are downloaded by each user from the original source
under that source's own licence. No copies are kept in this repository.

## Not a clinical tool

This repository is a research project. It is not a medical device and not a
clinical tool, and it must not be used for diagnosis or treatment decisions.
