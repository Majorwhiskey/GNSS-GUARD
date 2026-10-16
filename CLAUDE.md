# CLAUDE.md

Context for Claude Code working in this repository.

## Project

GNSS-GUARD: a low-cost GPS jamming and spoofing detector. u-blox NEO-M8L
(GNSS + built-in IMU) → classic ESP32 → PC logger → feature pipeline →
model → back onto the ESP32. Intended as a portfolio / resume project, so
measured results, honest baselines and clean documentation matter as much as
the code.

Current phase: data collection. No model trained yet. See the roadmap in
README.md and keep it updated when a milestone is reached.

## Hard rules

- **Receive-only.** Never write code, firmware or instructions that transmit on
  GNSS bands, generate spoofing or jamming RF, or drive an SDR transmitter.
  Attack data comes from published datasets (TEXBAT, OAKBAT) and software
  injection into recorded logs only.
- `data/raw/*.ubx` is the source of truth. Never modify or delete raw logs.
  Everything in `data/features/` and `models/` must be regenerable from them.
- Never commit `data/raw/` or `data/features/` contents (see .gitignore).
- A feature computed in Python and on the ESP32 must use the same formula and
  units. When changing a feature, update `tools/features.py`,
  `docs/FEATURES.md` and (once it exists) the firmware implementation together.
- Do not report a metric in README or docs unless it came from a real run;
  note the dataset and command that produced it.

## Hardware facts

- MCU: classic ESP32 (WROOM-32, no PSRAM, no vector instructions, 520 KB SRAM).
  FQBN `esp32:esp32:esp32`, Arduino core 3.3.x installed via arduino-cli.
- GNSS: NEO-M8L on UART2, ESP32 RX = GPIO16, TX = GPIO17, 460800 baud, UBX out.
- USB serial to PC: 921600 baud.
- The bridge configures the receiver in RAM on every boot (no CFG-CFG save),
  trying 9600 / 38400 / 115200 / 460800 to find it.
- RXM-RAWX support on the M8L is unconfirmed; do not build features that
  depend on it until a real log shows the message.
- ESF-RAW scaling: gyro 2^-12 deg/s, accel 2^-10 m/s^2, 24-bit signed field,
  data type in the top byte (gyro z = 5, y = 13, x = 14; accel x/y/z = 16/17/18).
- When sensor fusion is active the M8L's NAV-PVT is a fused GNSS+IMU solution,
  which can mask GNSS-only anomalies. ESF-STATUS `fusionMode` is logged so this
  can be checked per session.

Reference: u-blox 8 / M8 Receiver Description including Protocol
Specification, plus the ADR/UDR protocol description for ESF messages. Check
message layouts against `pyubx2` (`pyubx2.ubxtypes_get.UBX_PAYLOADS_GET`)
rather than from memory.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest                                         # feature pipeline tests
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/ubx_bridge
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 firmware/ubx_bridge
.venv/bin/python tools/log.py --port /dev/ttyUSB0 --scenario <name> --notes "..."
.venv/bin/python tools/features.py data/raw/*.ubx
```

## Conventions

- Python 3.12, virtualenv in `.venv/`. Dependencies pinned loosely in
  `requirements.txt`.
- Feature column names are snake_case; units are SI unless the name or
  docs/FEATURES.md says otherwise (C/N0 in dB-Hz, clock in ns and ns/s).
- Scenario names in log filenames follow docs/DATA_COLLECTION.md
  (`clean_*`, `degraded_*`, and later `attack_*` for imported datasets).
- Arduino sketches: plain Arduino API, no extra libraries for the bridge.
  Comments explain why, not what.
- Docs are Markdown in `docs/`, uppercase filenames, tables preferred over
  long prose.
