# Evaluation

## Questions

1. How does a learned detector on low-cost hardware compare with the
   receiver's built-in jamming and spoofing indicators?
2. Does a model trained only on clean data (anomaly detection) generalise to
   real attacks it has never seen?
3. How much do the M8L's IMU features add over GNSS-only features?
4. Does it fit and run on a classic ESP32 at 1 Hz?

## Baselines

| ID | Detector | Notes |
|---|---|---|
| B0 | u-blox `spoofDetState` ≥ 2 | Vendor spoofing flag |
| B1 | u-blox `jam_state` ≥ 2 or `jam_ind` above threshold | Vendor jamming flag |
| B2 | Hand-tuned rules: `cno_elev_corr`, `clk_jump`, `pos_jump`, `cno_delta_mean` thresholds | Classical consistency checks |

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

## Experiments

| ID | Comparison | Answers |
|---|---|---|
| E1 | B0, B1, B2 vs M1, M2 on test-synth and test-real | Question 1 |
| E2 | M2 trained clean-only vs M1 supervised, on attack types withheld from M1's training | Question 2 |
| E3 | M1 / M2 with and without IMU features, on test-synth `spoof_pos_push` | Question 3 |
| E4 | M2 vs M3 (float vs int8 on device): accuracy loss, latency, memory | Question 4 |
| E5 | 10+ hours of continuous driving with M3 live | Real-world false alarm rate |

## Reporting

Every number in the README or write-up comes from a script run committed to
the repository, with the command and data version noted next to it. Results
tables live in `docs/RESULTS.md` once experiments start.
