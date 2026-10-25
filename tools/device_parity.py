"""Check the ESP32's feature output against tools/features.py on the same logs.

Flash firmware/feature_replay first, then:
  python tools/device_parity.py --port /dev/cu.usbserial-0001 data/raw/<session>.ubx ...

Streams each log to the board, collects the CSV it prints, and reports any
column that differs beyond rounding. mismatches() is also used by
tests/test_firmware_parity.py for the native build.
"""
import argparse
import io
import sys
import time

import numpy as np
import pandas as pd

import features

RTOL, ATOL = 1e-9, 1e-6  # pyubx2 rounds scaled fields to 12 decimals; the firmware does not


def mismatches(py, other):
    """Differences between the Python features and another implementation's, as messages."""
    if list(py["iTOW"]) != list(other["iTOW"]):
        return [f"epochs differ: {len(py)} in Python, {len(other)} in the other"]
    out = []
    for col in py.columns:
        a, b = py[col].astype(float).to_numpy(), other[col].astype(float).to_numpy()
        bad = ~np.isclose(a, b, rtol=RTOL, atol=ATOL, equal_nan=True)
        if bad.any():
            i = bad.argmax()
            out.append(f"{col}: {int(bad.sum())} rows differ, first at row {i}: python {a[i]!r}, other {b[i]!r}")
    for col in sorted(set(other.columns) - set(py.columns)):
        if not other[col].isna().all():
            out.append(f"{col}: set by the other implementation but absent in Python")
    return out


def replay(ser, path, chunk=512, pause=0.025):
    """Stream a .ubx file to feature_replay and return its CSV output as a DataFrame."""
    ser.reset_input_buffer()
    data, out = open(path, "rb").read(), bytearray()
    # Paced so the board's output (larger than its input) never stalls its receive buffer.
    for i in range(0, len(data), chunk):
        ser.write(data[i:i + chunk])
        time.sleep(pause)
        out += ser.read(ser.in_waiting)
    deadline = time.time() + 10
    while not out.endswith(b"END\n") and time.time() < deadline:
        out += ser.read(max(1, ser.in_waiting))
    text = out.decode(errors="replace")
    start = text.find("iTOW,")  # boot ROM noise can precede the header after a reset
    if start < 0 or not text.endswith("END\n"):
        raise RuntimeError("no CSV from the board; is firmware/feature_replay flashed?")
    return pd.read_csv(io.StringIO(text[start: -len("END\n")]))


if __name__ == "__main__":
    import serial

    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("logs", nargs="+")
    args = p.parse_args()
    failed = False
    with serial.Serial(args.port, 921600, timeout=0.5) as ser:
        time.sleep(2)  # opening the port can reset the board
        for path in args.logs:
            problems = mismatches(features.extract(path), replay(ser, path))
            print(f"{path}: {'OK' if not problems else 'MISMATCH'}")
            for msg in problems:
                print("  " + msg)
            failed |= bool(problems)
    sys.exit(1 if failed else 0)
