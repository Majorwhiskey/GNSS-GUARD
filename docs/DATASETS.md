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

M8L-only features (AGC, jamInd, IMU) do not exist for TEXBAT. Models evaluated
on TEXBAT use the portable feature set only.

Expect a domain gap: GNSS-SDR's C/N0 estimator and residuals differ from the
M8L's. Normalise features per session (for example z-score against the first
minutes of clean data) before cross-dataset evaluation, and report results
with and without normalisation.

## OAKBAT

A newer spoofing dataset from Oak Ridge National Laboratory, also distributed
as raw RF recordings. Same processing route as TEXBAT. Check the current
access terms and scenario list on the ORNL publication page before planning
around it.

## Synthetic injection

Attacks injected in software into clean M8L feature logs. Fast to generate,
fully labelled, and covers the M8L-only features that public datasets lack.
Used for development and tuning, **never** as the only test set: results must
also be reported on TEXBAT / OAKBAT.

| Type | Injection |
|---|---|
| `jam_ramp` | AGC falls, noise rises, C/N0 drops on all satellites at a set rate, fix degrades and is lost |
| `spoof_takeover` | All C/N0 jump 5–10 dB together and become uniform; C/N0–elevation correlation collapses; brief loss of lock |
| `spoof_time_push` | Clock bias ramps at a chosen rate beyond the reported drift |
| `spoof_pos_push` | Position drifts at 0.5–5 m/s in a fixed direction while IMU features keep their recorded values |
| `meaconing` | Position and time step to a delayed copy of the same log |

Injection parameters (start time, rate, magnitude) are randomised and stored
alongside each synthetic file so every result can be reproduced.
