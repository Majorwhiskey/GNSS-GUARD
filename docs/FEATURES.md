# Features

One row per navigation epoch (1 Hz), keyed by GPS time of week `iTOW` (ms).
Produced by `tools/features.py` (reference) and by the C++ library in
`firmware/lib/gnss_features/` for the ESP32. The two must match:

| Check | What it runs | Where |
|---|---|---|
| `tests/test_firmware_parity.py` | Library built natively, compared column by column with `features.py` on clean, injected, gappy, corrupted and turning logs | Every `pytest` run and CI |
| `tools/device_parity.py` | Logs streamed to the ESP32 running `firmware/feature_replay`, output compared the same way | On the bench, after library changes |

Tolerance is 1e-9 relative, 1e-6 absolute: pyubx2 rounds scaled fields to 12
decimals and the library does not. Streaming differences (epochs emitted when
the next one starts; epochs opened by NAV-class messages) are documented in
`gnss_features.h`. First on-device check (`tools/device_parity.py`,
2026-10-25): 7 synthetic logs (clean, all five attacks, heading wrap) matched
on an ESP32-WROOM-32. `feature_replay` uses 27.6 KB of static RAM against
22.1 KB for `ubx_bridge`, so the library's state is roughly 5.5 KB.

Tiers:

- **Portable**: computable from any receiver's observables, including TEXBAT
  recordings processed through GNSS-SDR. Used for cross-dataset evaluation.
- **u-blox**: depend on u-blox-specific messages (accuracy estimates,
  MON-HW, NAV-STATUS). Used for field detection on this hardware.

## Position and velocity (NAV-PVT)

| Column | Unit | Tier | Definition |
|---|---|---|---|
| `fix` | enum | portable | 0 none, 2 2D, 3 3D, 4 GNSS+DR, 1 DR only |
| `fix_ok` | 0/1 | portable | `gnssFixOk` flag |
| `num_sv` | count | portable | Satellites used in the solution |
| `lat`, `lon` | deg | portable | Position |
| `height` | m | portable | Height above ellipsoid |
| `h_acc`, `v_acc` | m | u-blox | Receiver's own horizontal / vertical accuracy estimate |
| `s_acc` | m/s | u-blox | Speed accuracy estimate |
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
| `ublox_spoof_state` | enum | u-blox | 0 unknown/off, 1 no spoofing indicated, 2 spoofing indicated, 3 multiple indications. **Baseline only, never a model input.** |
| `clk_bias` | ns | portable | Receiver clock bias |
| `clk_drift` | ns/s | portable | Receiver clock drift |
| `t_acc`, `f_acc` | ns, ps/s | u-blox | Time and frequency accuracy estimates |
| `noise` | — | u-blox | MON-HW `noisePerMS` |
| `agc` | 0–8191 | u-blox | MON-HW `agcCnt` |
| `jam_ind` | 0–255 | u-blox | CW jamming indicator. **Baseline only.** |
| `jam_state` | enum | u-blox | 0 unknown, 1 ok, 2 warning, 3 critical. **Baseline only.** |

MON-HW has no timestamp; it is attached to the epoch current when it arrives,
and its last value carries forward into new epochs.

## Derived consistency checks

| Column | Unit | Tier | Definition | Why |
|---|---|---|---|---|
| `clk_jump` | ns | portable | `Δclk_bias − clk_drift(prev) × Δt` | Time-push attacks move the bias more than the drift predicts |
| `pos_jump` | m | portable | Distance between consecutive positions minus the displacement predicted by the previous velocity × Δt (flat-earth approximation) | Position pushes and re-acquisition jumps |
| `heading_rate` | deg/s | portable | Wrapped change in heading / Δt | Abrupt heading changes from position pushes |

## Planned features

- Doppler vs velocity consistency needs RXM-RAWX, which this receiver NAKs;
  only with an upgraded receiver.
- Window statistics (5 s and 10 s rolling mean, std, slope) of all the above
  for the tree models.
