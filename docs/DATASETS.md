# Datasets

Attack data comes from three sources. None of them involves transmitting RF.

## TEXBAT (Texas Spoofing Test Battery)

Published by the UT Austin Radionavigation Laboratory (Humphreys et al.,
ION GNSS 2012). Recordings of raw GPS L1 RF samples with spoofing attacks
mixed in, so any receiver (hardware or software) can be tested against the
same attacks.

Scenarios as described in the original paper; check them against the dataset
documentation before relying on this table:

| Scenario | Platform | Attack |
|---|---|---|
| ds1 | static | Clean reference |
| ds2 | static | Switch to an overpowered spoofer (simplistic) |
| ds3 | static | Overpowered time push |
| ds4 | static | Matched-power time push |
| ds5 | static | Matched-power position push |
| ds6 | dynamic | Matched-power position push |
| ds7 | static | Matched-power, carrier-phase aligned time push |
| ds8 | — | Later addition; see dataset documentation |

Access: request through the lab's website. Files are raw complex samples and
very large (tens of GB per scenario); budget disk space before downloading.

### Processing

TEXBAT contains RF samples, not receiver messages, so the u-blox pipeline
cannot read it directly. Plan:

1. Run each scenario through [GNSS-SDR](https://gnss-sdr.org/) configured for
   the dataset's sample rate and format.
2. Export per-epoch observables (C/N0, pseudorange, Doppler, satellite
   elevation) and the PVT solution with clock bias and drift.
3. Convert to the **portable** feature columns in FEATURES.md with a separate
   script (`tools/texbat_features.py`, to be written).

u-blox-only features (AGC, jamInd, accuracy estimates) do not exist for TEXBAT. Models evaluated
on TEXBAT use the portable feature set only.

Expect a domain gap: GNSS-SDR's C/N0 estimator and residuals differ from the
M8N's. Normalise features per session (for example z-score against the first
minutes of clean data) before cross-dataset evaluation, and report results
with and without normalisation.

## OAKBAT

A newer spoofing dataset from Oak Ridge National Laboratory, also distributed
as raw RF recordings. Same processing route as TEXBAT. Check the current
access terms and scenario list on the ORNL publication page before planning
around it.

## Synthetic injection

Attacks injected in software into clean M8N logs. Fast to generate, fully
labelled, and covers the u-blox-only features that public datasets lack. Used
for development and tuning, **never** as the only test set: results must also
be reported on TEXBAT / OAKBAT.

```bash
.venv/bin/python tools/inject.py data/raw/<session>.ubx --attack all --seeds 1-5
.venv/bin/python tools/features.py data/synthetic/*.ubx
```

`tools/inject.py` edits the UBX messages themselves (NAV-SAT, NAV-PVT,
NAV-CLOCK, NAV-STATUS, MON-HW) and writes a new log to `data/synthetic/`, so
`features.py` computes every feature from the injected messages with the same
code as for real logs. The raw log is never modified. Each output has a
`.json` with the attack, seed, parameters and window (`start_itow` to
`end_itow`, ms, end exclusive); `inject.labels()` turns it into per-epoch
labels.

| Type | Injection | Parameters (uniform draw) |
|---|---|---|
| `jam_ramp` | C/N0 on every satellite falls linearly; satellites below 25 dB-Hz leave the fix, below 12 dB-Hz lose lock; fix lost under 4 used; MON-HW noise rises up to 4× and AGC falls to half | `rate_db_s` 0.2–1.0 |
| `spoof_takeover` | Optional loss of lock, then every tracked satellite sits at the old mean + delta with a fixed per-satellite offset, unrelated to elevation, capped at 55 dB-Hz | `delta_db` 5–10, `spread_db` 0.5–1.5, `loss_s` 0–3 |
| `spoof_time_push` | `clkB` ramps; `clkD` untouched, so the drift does not explain it | `rate_ns_s` 2–50 |
| `spoof_pos_push` | Position moves along a bearing; reported velocity untouched | `speed_m_s` 0.5–5, `bearing_deg` 0–360 |
| `meaconing` | Optional loss of lock, then a constant clock step (rebroadcast delay), position step (rebroadcast antenna location) and common C/N0 offset | `delay_us` 1–100, `offset_m` 50–2000, `bearing_deg`, `cno_offset_db` −3 to 6, `loss_s` 0–3 |

Every window starts 30–60% into the log and lasts 60–300 s (or to the end of
the log). The tracking thresholds and the MON-HW response are assumptions, not
measurements; recalibrate them once `degraded_*` sessions show how this
receiver actually behaves as signals weaken.

Vendor flags (`spoofDetState`, `jamInd`, `jammingState`) are passed through as
recorded, because u-blox's detector cannot be simulated. Baselines B0 and B1
are therefore only evaluated on real attack data, never on synthetic.
