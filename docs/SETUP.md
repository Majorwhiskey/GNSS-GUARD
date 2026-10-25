# Setup

Verified on macOS (Apple Silicon) with Python 3.12 and Arduino core esp32
3.3.12. Linux notes are given where they differ.

## macOS toolchain

| Step | Command | Notes |
|---|---|---|
| 1. Homebrew | see https://brew.sh | Needed for `arduino-cli` |
| 2. Python env | `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` | Python 3.12 |
| 3. Tests | `.venv/bin/pytest` | All tests should pass; CI runs the same on every push |
| 4. arduino-cli | `brew install arduino-cli` | |
| 5. ESP32 core | `arduino-cli core update-index && arduino-cli core install esp32:esp32` | Downloads about 1.5 GB, several minutes with no progress output |
| 6. Rosetta 2 (Apple Silicon only) | `softwareupdate --install-rosetta --agree-to-license` | The core's bundled `ctags` is an x86_64 binary |
| 7. Compile check | `arduino-cli compile --fqbn esp32:esp32:esp32 firmware/ubx_bridge` | No board needed. Reference: 269 KB flash (20%), 22 KB RAM (6%) |

### Known errors

| Error | Cause | Fix |
|---|---|---|
| `fork/exec .../ctags: bad CPU type in executable` | Apple Silicon without Rosetta | Step 6 |
| `arduino-cli: command not found` | Not installed | Step 4 |

## Find the serial port

| OS | Port looks like | How to list |
|---|---|---|
| Linux | `/dev/ttyUSB0` or `/dev/ttyACM0` | `ls /dev/ttyUSB* /dev/ttyACM*` |
| macOS | `/dev/cu.usbserial-0001`, `/dev/cu.SLAB_USBtoUART` or `/dev/cu.wchusbserial*` | `ls /dev/cu.*` or `arduino-cli board list` |

Use the `cu.*` device on macOS, not `tty.*`; `tty.*` waits for a carrier
signal and can block.

The name depends on the USB-serial chip on the ESP32 board: CP210x gives
`usbserial` or `SLAB_USBtoUART`, CH340 gives `wchusbserial`. If nothing
appears when the board is plugged in, try another cable (many are
charge-only), then install the chip vendor's driver.

Flash and log with the port you found:

```bash
PORT=/dev/cu.usbserial-0001   # example
arduino-cli compile --upload -p $PORT --fqbn esp32:esp32:esp32 firmware/ubx_bridge
.venv/bin/python tools/log.py --port $PORT --scenario clean_static --notes "balcony, clear sky"
```

If the upload hangs at `Connecting...`, hold the board's BOOT button until it
starts writing.

Only one program can hold the port at a time: close the Arduino serial
monitor before running `tools/log.py`, and close `tools/log.py` before
flashing.

## Keeping the laptop awake while logging

A sleeping laptop stops the logger. On macOS run `caffeinate -i` in a second
terminal for the duration of the session.
