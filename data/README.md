# data/

## What is here

- `sessions/`: 12 recordings from one adult subject, one ZIP per session.
  They are included in this repository and published under this repository's
  licence. Each ZIP contains only the IMU data (`imu.csv`), its `meta.json`
  and a per-capture `README.md`. ECG, heart rate, RR intervals and temperature
  were recorded at the same time but are not published here; the metadata
  still lists those streams so the record of what was captured stays
  complete. The published files carry no device identifier.
- `legacy_labels/`: the label file and model from the first labelling pass,
  kept as the subject of `../docs/LABEL_AUDIT.md`.

## What is never here

Pediatric recordings are never included in this repository, in any form: not
as raw recordings, not as segmented windows, and not as extracted features.
That subject is not of an age to give consent.

`.gitignore` tracks only the 12 session files by exact filename, the
`legacy_labels/*.json` files, this README and `.gitkeep`. Anything else placed
under `data/` is ignored by git. A new file in `sessions/` is not tracked
unless its exact filename is added to `.gitignore`.

This data is not for clinical use; this repository is not a clinical tool.

See `../docs/DATA_POLICY.md` for the full policy.
