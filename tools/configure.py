"""Apply the bridge's receiver configuration over the receiver's own USB port.

For logging with the GNSS module plugged straight into the PC instead of through
the ESP32 bridge. Mirrors firmware/ubx_bridge/ubx_bridge.ino: same messages, same
rate, RAM only, so it must be re-applied after every power cycle.

Usage: python tools/configure.py --port /dev/cu.usbmodem1101
"""
import argparse
import time

import serial
from pyubx2 import SET, UBX_PROTOCOL, UBXMessage, UBXReader

USB_PORT_ID = 3

# Keep in sync with enableMsg() calls in firmware/ubx_bridge/ubx_bridge.ino.
MESSAGES = [
    ("NAV-PVT", 0x01, 0x07),
    ("NAV-SAT", 0x01, 0x35),
    ("NAV-STATUS", 0x01, 0x03),
    ("NAV-CLOCK", 0x01, 0x22),
    ("MON-HW", 0x0A, 0x09),
    ("RXM-RAWX", 0x02, 0x15),  # NAKed if this firmware lacks it
]


def _cfg(msg_id, payload):
    return UBXMessage(0x06, msg_id, SET, payload=bytes(payload))


def _await_ack(reader, msg_id, timeout=1.0):
    """'ACK', 'NAK' or 'none' for the CFG message with this ID."""
    end = time.time() + timeout
    while time.time() < end:
        _, msg = reader.read()
        if msg is not None and msg.identity in ("ACK-ACK", "ACK-NAK") and msg.clsID == 0x06 and msg.msgID == msg_id:
            return "ACK" if msg.identity == "ACK-ACK" else "NAK"
    return "none"


def configure(ser):
    """Send the configuration and return {setting: 'ACK' | 'NAK' | 'none'}."""
    reader = UBXReader(ser, protfilter=UBX_PROTOCOL, quitonerror=0)
    steps = []

    # CFG-PRT for USB: UBX+NMEA in, UBX only out, so NMEA does not pad the logs.
    prt = bytearray(20)
    prt[0] = USB_PORT_ID
    prt[12] = 0x03
    prt[14] = 0x01
    steps.append(("CFG-PRT usb", 0x00, prt))
    # CFG-RATE: 1000 ms measurement, 1 cycle per solution, GPS time.
    steps.append(("CFG-RATE 1 Hz", 0x08, [0xE8, 0x03, 0x01, 0x00, 0x01, 0x00]))
    # CFG-MSG short form: rate applies to the port the command arrived on.
    for name, cls, mid in MESSAGES:
        steps.append((name, 0x01, [cls, mid, 1]))

    results = {}
    for name, msg_id, payload in steps:
        ser.reset_input_buffer()
        ser.write(_cfg(msg_id, payload).serialize())
        results[name] = _await_ack(reader, msg_id)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    args = p.parse_args()
    with serial.Serial(args.port, 9600, timeout=0.2) as ser:
        for name, result in configure(ser).items():
            print(f"{name:14s} {result}")
