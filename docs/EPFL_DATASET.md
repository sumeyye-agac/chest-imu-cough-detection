# EPFL cough dataset: layout as extracted

Source: Zenodo record 7562332, `public_dataset.zip` (852,406,950 bytes,
MD5 `37419b515b29ed6115bcb9ac422eb4a3`), CC-BY 4.0. Orlandic et al., IEEE EMBC
2023, doi:10.1109/EMBC40787.2023.10340413.

`scripts/fetch_epfl.py` downloads the file into `data/external/epfl/`
(gitignored), checks size and MD5 against Zenodo's record, extracts it, and
deletes everything except `imu.csv` and `ground_truth.json`. The extracted
archive is 1,800.6 MB. After deletion it is 54.7 MB. The deleted files are
2,686 `.wav` files and 15 `.json` files other than `ground_truth.json`.
The audio is never used here.

The format reference is EPFL's own loader, `src/helpers.py` in
https://github.com/esl-epfl/edge-ai-cough-count. This repository does not copy
it; `src/chest_imu_cough/epfl.py` is a separate loader.

## Directory tree, two levels deep

    data/external/epfl/extracted/
      public_dataset/
        14287/  trial_1/ trial_2/ trial_3/
        14342/  trial_1/ trial_2/
        14547/  trial_1/ trial_2/ trial_3/
        20794/  trial_1/ trial_2/
        38936/  trial_1/ trial_2/ trial_3/
        47779/  trial_1/ trial_2/ trial_3/
        49661/  trial_1/ trial_2/ trial_3/
        55502/  trial_1/ trial_2/ trial_3/
        74768/  trial_1/ trial_2/ trial_3/
        76918/  trial_1/ trial_2/ trial_3/
        84479/  trial_1/ trial_2/ trial_3/
        86463/  trial_1/ trial_3/
        87369/  trial_1/ trial_2/ trial_3/
        87447/  trial_1/ trial_2/ trial_3/
        97706/  trial_1/ trial_2/ trial_3/

Below each trial the layout is as documented:

    mov_<sit|walk>/background_noise_<music|nothing|someone_else_cough|traffic>/
        <cough|laugh|throat_clearing|deep_breathing>/imu.csv

## Differences from the documented layout

- An extra top-level folder, `public_dataset/`, above the subject folders.
- `imu.csv` has an unnamed leading index column (0, 1, 2, ...). It is ignored.
- The columns are `Accel x`, `Accel y`, `Accel z` in lower case. EPFL's loader
  names them `Accel X/Y/Z`. The gyroscope columns match: `Gyro Y`, `Gyro P`,
  `Gyro R`.
- Not every subject has three trials: 14342 and 20794 have trials 1 and 2,
  86463 has trials 1 and 3.
- One recording is missing: 74768, trial 3, mov_sit, someone_else_cough,
  deep_breathing.

## Counts

15 subjects, 42 subject-trials, 1,343 recordings.

| movement | noise | cough | laugh | throat_clearing | deep_breathing |
|---|---|---|---|---|---|
| sit | music | 42 | 42 | 42 | 42 |
| sit | nothing | 42 | 42 | 42 | 42 |
| sit | someone_else_cough | 42 | 42 | 42 | 41 |
| sit | traffic | 42 | 42 | 42 | 42 |
| walk | music | 42 | 42 | 42 | 42 |
| walk | nothing | 42 | 42 | 42 | 42 |
| walk | someone_else_cough | 42 | 42 | 42 | 42 |
| walk | traffic | 42 | 42 | 42 | 42 |

Row counts at 100 Hz: 167 to 1,755 rows per recording (1.7 to 17.6 s), median
997 (about 10 s), 1,358,931 rows in total. Seated cough recordings: 607 to
1,558 rows, median 896.

## Labels

`ground_truth.json` exists for all 336 cough recordings and for no other class:
`{"start_times": [...], "end_times": [...]}` in seconds from the start of the
recording. Every file has matching start and end lists and every end is after
its start. The coughs were annotated from audio.

There are 4,294 annotated coughs, 5 to 26 per recording, median 12. Seated
cough recordings hold 2,094 of them (see `results/epfl_results.json`).
Consecutive coughs are often annotated back to back: one cough's end time is
the next one's start time.

## Signal values

The IMU is not in physical units. At rest the accelerometer magnitude is about
112 counts and varies from about 86 to 144 between recordings. `Gyro Y` sits at
about -9 in every recording, with a spread of under 1 count; `Gyro P` and
`Gyro R` sit near zero. The dataset does not say whether the gyroscope columns
are angular rates or angles. The loader takes the magnitude of the three
columns, as the existing code does for the Movesense gyroscope.

Neither fact changes the detector or the features. The detector band-passes the
signal before thresholding, which removes constant offsets, and both the MAD
threshold and the session-relative features are unchanged by a change of scale.
See [CROSS_DATASET.md](CROSS_DATASET.md).
