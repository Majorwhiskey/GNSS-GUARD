# Hardware

## Bill of materials

| Ref | Part | Purpose |
|---|---|---|
| U1 | ESP32 DevKit (ESP32-WROOM-32) | Receiver configuration, USB bridge, later on-device inference |
| U2 | u-blox NEO-M8L breakout | Multi-GNSS receiver with integrated 3-axis accelerometer and gyroscope |
| ANT | Active L1 GNSS patch antenna | Mount with a clear sky view; ground plane helps |
| — | USB cable, jumper wires | |

The M8L is an automotive dead-reckoning module (ADR / UDR firmware). The
integrated IMU is the reason it suits this project: it provides motion data
that is independent of the GNSS signals an attacker controls.

## Wiring

| NEO-M8L pin | ESP32 pin | Notes |
|---|---|---|
| TX (TXD1) | GPIO16 | UART2 RX on the ESP32 |
| RX (RXD1) | GPIO17 | UART2 TX on the ESP32 |
| GND | GND | |
| VCC | 3V3 or 5V | Most breakouts have a regulator; check yours before using 5V |

Keep the antenna cable away from the ESP32 and its USB cable. ESP32 WiFi is
off in the bridge firmware, but USB and switching regulators can still raise
the noise floor, which shows up directly in the `noise` and `agc` features.

## Receiver configuration

`firmware/ubx_bridge/ubx_bridge.ino` applies this on every boot (RAM only, not
saved to the receiver's flash):

| Setting | Value |
|---|---|
| UART1 baud | 460800 |
| UART1 protocols | in UBX + NMEA, out UBX only |
| Measurement rate | 1 Hz (CFG-RATE 1000 ms) |

The ESP32 tries 9600, 38400, 115200 and 460800 when sending CFG-PRT, so it
finds the receiver whatever rate it was left at.

### Enabled UBX messages

| Message | Class/ID | Used for |
|---|---|---|
| NAV-PVT | 01 07 | Position, velocity, accuracy estimates, fix type |
| NAV-SAT | 01 35 | Per-satellite C/N0, elevation, azimuth, pseudorange residual, used flag |
| NAV-STATUS | 01 03 | `spoofDetState` (u-blox baseline) |
| NAV-CLOCK | 01 22 | Receiver clock bias (ns) and drift (ns/s) |
| MON-HW | 0A 09 | AGC count, noise per ms, `jamInd`, `jammingState` |
| ESF-STATUS | 10 10 | Sensor fusion mode and IMU calibration status |
| ESF-RAW | 10 03 | Raw IMU samples (gyro and accelerometer) |
| RXM-RAWX | 02 15 | Raw pseudorange, carrier phase, Doppler. **May be unsupported on M8L** |

Confirm on first run with the `msgs:` line printed by `tools/log.py`, or
with the offline check in [DATA_COLLECTION.md](DATA_COLLECTION.md#rxm-rawx-check). If
RXM-RAWX does not appear, the M8L firmware does not provide it, and the
project uses NAV-level features only (or moves to a NEO-M8T / ZED-F9P later).

### Bandwidth

At 1 Hz NAV-SAT is up to about 400 bytes for 30 satellites. ESF-RAW carries
roughly 100 Hz IMU data, a few kB/s. 460800 baud gives about 46 kB/s, so
there is headroom for higher navigation rates later.

## Mounting and IMU calibration

The M8L's sensor fusion and the IMU features assume the module is rigidly
fixed to the vehicle.

1. Mount the breakout firmly (double-sided tape on a flat surface, no
   dangling on wires). Note the orientation in the session notes.
2. Start logging with a clear sky view and wait for a 3D fix.
3. Drive for 5–10 minutes with turns, stops and straight stretches. ESF-STATUS
   reports calibration progress.
4. Static and walking sessions do not need calibration; the raw IMU features
   still work, the fused solution does not.

When fusion is active, NAV-PVT is a fused GNSS + IMU solution. Fusion can
smooth over a GNSS anomaly, so per-satellite and clock features are the main
detection signals, and the IMU is compared against GNSS-derived motion
rather than against the fused output.

## Upgrade path

| Receiver | Adds | Approx. cost |
|---|---|---|
| NEO-M8T | RXM-RAWX raw measurements: Doppler and carrier-phase consistency checks | ₹4–6k |
| ZED-F9P | L1 + L2, RAWX, improved jamming and spoofing indicators, RTK ground truth | ₹20–25k |
