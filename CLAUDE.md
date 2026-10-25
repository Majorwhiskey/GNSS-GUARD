# CLAUDE.md

Context for Claude Code working in this repository.

## Project

GNSS-GUARD: a low-cost GPS jamming and spoofing detector. u-blox NEO-M8N
(GNSS only, no IMU) → classic ESP32 → PC logger → feature pipeline →
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
- GNSS: NEO-M8N on UART2, ESP32 RX = GPIO16, TX = GPIO17, 460800 baud, UBX out.
- USB serial to PC: 921600 baud. Port is `/dev/ttyUSB0` on Linux and
  `/dev/cu.usbserial-*` on macOS (use `cu.*`, not `tty.*`); see docs/SETUP.md.
- The bridge configures the receiver in RAM on every boot (no CFG-CFG save),
  trying 9600 / 38400 / 115200 / 460800 to find it.
- The M8N has no IMU and no ESF messages, so NAV-PVT is a pure GNSS solution
  and there is no GNSS-independent motion reference. An earlier version of
  this repo assumed a NEO-M8L; IMU features were removed when that was
  corrected.
- RXM-RAWX is not officially supported on the M8N (it is an M8T feature);
  unconfirmed on this unit. Do not build features that depend on it until a
  real log shows the message.

Reference: u-blox 8 / M8 Receiver Description including Protocol
Specification. Check message layouts against `pyubx2`
(`pyubx2.ubxtypes_get.UBX_PAYLOADS_GET`) rather than from memory.

## Commands

Dev machine is macOS on Apple Silicon: `arduino-cli` needs Rosetta 2 (bundled
`ctags` is x86_64). Toolchain steps and known errors are in docs/SETUP.md. In
the commands below replace `/dev/ttyUSB0` with the real port.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest                                         # feature pipeline tests
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/ubx_bridge
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 firmware/ubx_bridge
.venv/bin/python tools/log.py --port /dev/ttyUSB0 --scenario <name> --notes "..."
.venv/bin/python tools/features.py data/raw/*.ubx
```

First real session: follow the checklist in docs/DATA_COLLECTION.md, including
the RXM-RAWX check, then record the result under Hardware facts above.

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
