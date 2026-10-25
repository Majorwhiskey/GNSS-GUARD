# Evaluation

## Questions

1. How does a learned detector on low-cost hardware compare with the
   receiver's built-in jamming and spoofing indicators?
2. Does a model trained only on clean data (anomaly detection) generalise to
   real attacks it has never seen?
3. Does it fit and run on a classic ESP32 at 1 Hz?

## Baselines

| ID | Detector | Notes |
|---|---|---|
| B0 | u-blox `spoofDetState` ≥ 2 | Vendor spoofing flag |
| B1 | u-blox `jam_state` ≥ 2 or `jam_ind` above threshold | Vendor jamming flag |
| B2 | Hand-tuned rules: `cno_elev_corr`, `clk_jump`, `pos_jump`, `cno_delta_mean` thresholds | Classical consistency checks |

All three are in `tools/baselines.py`. `fit` sets each threshold at a chosen
per-epoch quantile of the clean val sessions (default 0.999, which is about 3.6
alarm epochs per hour before any alarm merging); `apply` reports alarms, and
for injected logs time to first alarm and false-alarm epochs. B0 and B1 are
reported on real attack data only: synthetic injection passes vendor flags
through unchanged (see DATASETS.md).

```bash
.venv/bin/python tools/baselines.py fit data/features/<val sessions>.csv --out models/baselines.json
.venv/bin/python tools/baselines.py apply models/baselines.json data/features/<session>.csv
```

## Models

| ID | Model | Training data |
|---|---|---|
| M1 | Gradient-boosted trees on windowed features | Clean + synthetic attacks (supervised) |
| M2 | Small autoencoder or GRU predictor, anomaly score = reconstruction / prediction error | Clean only (unsupervised) |
| M3 | M2 quantised to int8, running on the ESP32 | As M2 |

## Splits

Split by session, never by row: neighbouring epochs are nearly identical, so
row-level splits leak.

| Split | Contents |
|---|---|
| train | 70% of clean sessions (+ synthetic attacks on them for M1) |
| val | 15% of clean sessions, used for thresholds |
| test-clean | 15% of clean sessions + all `degraded_*` sessions |
| test-synth | Synthetic attacks injected into test-clean sessions |
| test-real | TEXBAT / OAKBAT, portable features only |

Thresholds are fixed on val and never tuned on any test split.

`tools/split.py` keeps the assignment in `data/splits.json`, which is
committed. Run it on the feature CSVs after each collection day:

```bash
.venv/bin/python tools/split.py data/features/*.csv
```

A session never changes split once assigned; new `clean_*` sessions go to
whichever split is furthest below its target hours for that scenario (the
first three sessions of a scenario go to train, val and test-clean in turn).
Injected logs are skipped. Inject synthetic attacks only from sessions of the
split they will be used in: train sessions for M1's training attacks,
test-clean sessions for test-synth.

## Metrics

| Metric | Meaning |
|---|---|
| ROC AUC, PR AUC | Ranking quality per attack type |
| Detection rate at a fixed false-alarm rate | For example at 1 false alarm per 10 hours |
| Time to detect | Seconds from attack start to first alarm, median and 90th percentile |
| False alarms per hour | On test-clean, reported separately for `degraded_*` |
| Missed attacks | Attacks with no alarm before the attack ends |
| Flash, RAM, inference time, energy per inference | For M3 on the ESP32 |

An alarm is counted once per contiguous run of positive epochs. An alarm
within 5 s before an attack's labelled start counts as a true detection
(label timing in imported datasets is approximate).

`tools/evaluate.py` implements these rules. Per detector and attack type it
reports sessions, detected, missed, and median / 90th percentile time to
detect; per detector it reports false alarms per hour, with sessions whose
name contains `degraded_` reported separately. An alarm event overlapping the
attack window or the 5 s before it is a detection; every other event is a
false alarm, and false-alarm hours exclude that window.

```bash
.venv/bin/python tools/evaluate.py models/baselines.json \
    --clean data/features/<test-clean and degraded sessions>.csv \
    --attacked data/features/<session>__<attack>_s<seed>.csv
```

Injected CSVs start with their source session's name, so a glob such as
`clean_static_*.csv` also matches them; `evaluate.py` rejects any `--clean`
file that has attack labels. Detection rate at a fixed false-alarm rate and
ROC / PR AUC need a continuous score and are added with the models.

## Experiments

| ID | Comparison | Answers |
|---|---|---|
| E1 | B0, B1, B2 vs M1, M2 on test-synth and test-real | Question 1 |
| E2 | M2 trained clean-only vs M1 supervised, on attack types withheld from M1's training | Question 2 |
| E3 | M2 vs M3 (float vs int8 on device): accuracy loss, latency, memory | Question 3 |
| E4 | 10+ hours of continuous driving with M3 live | Real-world false alarm rate |

## Reporting

Every number in the README or write-up comes from a script run committed to
the repository, with the command and data version noted next to it. Results
tables live in `docs/RESULTS.md` once experiments start.
