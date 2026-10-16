# Features

One row per navigation epoch (1 Hz), keyed by GPS time of week `iTOW` (ms).
Produced by `tools/features.py`. The ESP32 implementation (phase 3) must match
these definitions exactly.

Tiers:

- **Portable**: computable from any receiver's observables, including TEXBAT
  recordings processed through GNSS-SDR. Used for cross-dataset evaluation.
- **M8L**: depend on u-blox monitor messages or the M8L's IMU. Used for field
  detection on this hardware.

## Position and velocity (NAV-PVT)

| Column | Unit | Tier | Definition |
|---|---|---|---|
| `fix` | enum | portable | 0 none, 2 2D, 3 3D, 4 GNSS+DR, 1 DR only |
| `fix_ok` | 0/1 | portable | `gnssFixOk` flag |
| `num_sv` | count | portable | Satellites used in the solution |
| `lat`, `lon` | deg | portable | Position |
| `height` | m | portable | Height above ellipsoid |
| `h_acc`, `v_acc` | m | M8L | Receiver's own horizontal / vertical accuracy estimate |
| `s_acc` | m/s | M8L | Speed accuracy estimate |
| `speed` | m/s | portable | Ground speed |
| `vel_n`, `vel_e`, `vel_d` | m/s | portable | NED velocity |
| `heading` | deg | portable | Heading of motion |
| `pdop` | — | portable | Position dilution of precision |

## Satellite signals (NAV-SAT)

Computed over satellites with C/N0 > 0. Residual features use satellites
flagged `svUsed` only.

| Column | Unit | Tier | Definition | Why |
|---|---|---|---|---|
| `n_tracked` | count | portable | Satellites with C/N0 > 0 | Jamming drops this |
| `n_used` | count | portable | Satellites used in the fix | |
| `cno_mean`, `cno_std` | dB-Hz | portable | Mean and std of C/N0 | Spoofed skies are often strong and uniform |
| `cno_max`, `cno_min` | dB-Hz | portable | Extremes | |
| `cno_top4` | dB-Hz | portable | Mean of the 4 strongest | Robust to weak low-elevation satellites |
| `cno_elev_corr` | — | portable | Pearson correlation of C/N0 with elevation; NaN if fewer than 3 satellites or zero variance | Real signals strengthen with elevation; one spoofer antenna breaks this |
| `prres_rms`, `prres_maxabs` | m | portable | RMS and max abs pseudorange residual | Inconsistent fake signals fit the solution badly |
| `cno_delta_mean` | dB-Hz | portable | Mean change in C/N0 since previous epoch, over satellites present in both (at least 3) | Spoofer power changes move all satellites together |
| `cno_delta_std` | dB-Hz | portable | Std of that change | Small std with large mean = common-mode change |

## Receiver state (NAV-STATUS, NAV-CLOCK, MON-HW)

| Column | Unit | Tier | Definition |
|---|---|---|---|
| `ublox_spoof_state` | enum | M8L | 0 unknown/off, 1 no spoofing indicated, 2 spoofing indicated, 3 multiple indications. **Baseline only, never a model input.** |
| `clk_bias` | ns | portable | Receiver clock bias |
| `clk_drift` | ns/s | portable | Receiver clock drift |
| `t_acc`, `f_acc` | ns, ps/s | M8L | Time and frequency accuracy estimates |
| `noise` | — | M8L | MON-HW `noisePerMS` |
| `agc` | 0–8191 | M8L | MON-HW `agcCnt` |
| `jam_ind` | 0–255 | M8L | CW jamming indicator. **Baseline only.** |
| `jam_state` | enum | M8L | 0 unknown, 1 ok, 2 warning, 3 critical. **Baseline only.** |

MON-HW has no timestamp; it is attached to the epoch current when it arrives,
and its last value carries forward into new epochs.

## IMU (ESF-RAW)

Samples arriving between two epochs are aggregated into the earlier epoch.

| Column | Unit | Tier | Definition |
|---|---|---|---|
| `gyro_z_mean` | deg/s | M8L | Mean gyro z rate |
| `acc_mag_mean`, `acc_mag_std` | m/s² | M8L | Mean and std of accelerometer magnitude |

Scaling: gyro raw × 2^-12 deg/s, accel raw × 2^-10 m/s², 24-bit signed.

Known limitation: ESF-RAW samples are assigned by arrival order, not by their
sensor time tag (`sTag`). Good enough at 1 Hz; revisit before using IMU
features at higher rates.

## Derived consistency checks

| Column | Unit | Tier | Definition | Why |
|---|---|---|---|---|
| `clk_jump` | ns | portable | `Δclk_bias − clk_drift(prev) × Δt` | Time-push attacks move the bias more than the drift predicts |
| `pos_jump` | m | portable | Distance between consecutive positions minus the displacement predicted by the previous velocity × Δt (flat-earth approximation) | Position pushes and re-acquisition jumps |
| `heading_rate` | deg/s | portable | Wrapped change in heading / Δt | Compared against `gyro_z_mean` by the model |

## Planned features

- `heading_rate − gyro_z_mean` residual once the gyro sign convention and
  mounting orientation are confirmed on real logs.
- IMU-propagated velocity vs GNSS velocity over 5–10 s windows.
- Doppler vs velocity consistency, if RXM-RAWX turns out to be available.
- Window statistics (5 s and 10 s rolling mean, std, slope) of all the above
  for the tree models.
