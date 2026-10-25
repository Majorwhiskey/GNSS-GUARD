# Hardware

## Bill of materials

| Ref | Part | Purpose |
|---|---|---|
| U1 | ESP32 DevKit (ESP32-WROOM-32) | Receiver configuration, USB bridge, later on-device inference |
| U2 | u-blox NEO-M8N breakout | Multi-GNSS receiver (GPS, GLONASS, Galileo, BeiDou), no IMU |
| ANT | Active L1 GNSS patch antenna | Mount with a clear sky view; ground plane helps |
| — | USB cable, jumper wires | |

The M8N is a standard-precision receiver with no inertial sensors. Every
detection signal therefore comes from the GNSS signals themselves and the
receiver's monitor data; there is no independent motion reference to check
position against. See the upgrade path for modules that add one.

## Wiring

| NEO-M8N pin | ESP32 pin | Notes |
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
| RXM-RAWX | 02 15 | Raw pseudorange, carrier phase, Doppler. **Not officially supported on M8N** |

Confirm on first run with the `msgs:` line printed by `tools/log.py`, or
with the offline check in [DATA_COLLECTION.md](DATA_COLLECTION.md#rxm-rawx-check). If
RXM-RAWX does not appear, the M8N firmware does not provide it, and the
project uses NAV-level features only (or moves to a NEO-M8T / ZED-F9P later).

### Bandwidth

At 1 Hz NAV-SAT is up to about 400 bytes for 30 satellites, and the full
message set stays under 2 kB/s even with RXM-RAWX. 460800 baud gives about
46 kB/s, so there is headroom for higher navigation rates later.

## Mounting

1. Put the antenna where it sees the most sky: car roof (magnetic base) or
   the top of a backpack. Note the placement in the session notes, since it
   changes C/N0 and multipath.
2. Secure the breakout and ESP32 so wires cannot pull loose mid-session; a
   dropped UART shows up as a frozen `msgs:` count.
3. Start logging with a clear sky view and wait for a 3D fix.

## Upgrade path

| Receiver | Adds | Approx. cost |
|---|---|---|
| NEO-M8T | RXM-RAWX raw measurements: Doppler and carrier-phase consistency checks | ₹4–6k |
| NEO-M8U / NEO-M8L | Built-in IMU (UDR / ADR): GNSS-independent motion to check position drag-off against | — |
| ZED-F9P | L1 + L2, RAWX, improved jamming and spoofing indicators, RTK ground truth | ₹20–25k |
