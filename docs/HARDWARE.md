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
| GND | GND | Shared with the GPS power supply |
| VCC | 3V3 | With a 100+ µF capacitor across GPS VCC/GND, and a solid USB supply, see below |

Pin labels are not consistent between breakouts. The board used here labels
its UART pins from the host's side, so its "TX" pin goes to GPIO17 and its
"RX" pin to GPIO16. If GPIO16 sees only `0x00` bytes, swap the two wires.

### Power

The GPS can run from the ESP32 DevKit's 3V3 pin, but it needs a solid supply
behind the ESP32. On the first bench session the ESP32 was on a bus-powered
USB-C hub:

| Setup | Result |
|---|---|
| GPS on ESP32 3V3, no capacitor | ESP32 brownout resets |
| + 100+ µF capacitor across GPS VCC/GND | ESP32 stable, GPS rebooting every ~1.75 s (`$GNTXT` banner repeating, LED blinking) |
| Same, ESP32 on a power bank | LED steady |
| Same, hub's USB-C PD input connected to the charger | Stable: no reboots in 30 s, UBX through the bridge |

A multimeter on 3V3 read a steady 3.2 V throughout, because the dips are too
short to register. If the banner repeats or the LED blinks before a fix, suspect
the USB supply first. A separate 3.3 V supply (for example an MB102 breadboard
module) with grounds tied together also works.

### Direct USB logging (no bridge)

The receiver's own USB port is an alternative to the bridge for data
collection, useful when the ESP32's supply is the problem: same UBX messages,
same files.

```bash
.venv/bin/python tools/log.py --port /dev/cu.usbmodem1101 --configure --scenario clean_static --notes "..."
```

`--configure` sends the bridge's configuration over USB (`tools/configure.py`)
and records each ACK/NAK and `"link": "direct-usb"` in the session's `.json`.

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
| RXM-RAWX | 02 15 | Raw pseudorange, carrier phase, Doppler. **NAKed by this receiver (FW 2.01), unsupported** |

Result on this unit (2026-10-25, `tools/configure.py`): every message ACKed
except RXM-RAWX, which was NAKed. The project uses NAV-level features only,
with a NEO-M8T / ZED-F9P as the upgrade path for raw measurements.

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
