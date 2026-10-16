"""Log raw UBX from the ESP32 bridge to data/raw/<time>_<scenario>.ubx with a live summary.

Usage: python tools/log.py --port /dev/ttyUSB0 --scenario clean_drive --notes "city loop, dashboard mount"
"""
import argparse
import collections
import json
import os
import statistics
import time

import serial
from pyubx2 import UBX_PROTOCOL, UBXReader

p = argparse.ArgumentParser()
p.add_argument("--port", default="/dev/ttyUSB0")
p.add_argument("--baud", type=int, default=921600)
p.add_argument("--scenario", required=True, help="e.g. clean_static, clean_drive, foil_cover, urban_canyon")
p.add_argument("--notes", default="")
args = p.parse_args()

os.makedirs("data/raw", exist_ok=True)
stem = os.path.join("data/raw", time.strftime("%Y%m%d_%H%M%S") + "_" + args.scenario)
with open(stem + ".json", "w") as f:
    json.dump({"scenario": args.scenario, "notes": args.notes, "start": time.time()}, f, indent=2)

ser = serial.Serial(args.port, args.baud, timeout=1)
reader = UBXReader(ser, protfilter=UBX_PROTOCOL, quitonerror=0)
counts = collections.Counter()
last = {}
t_print = time.time()

print(f"logging to {stem}.ubx, Ctrl+C to stop")
with open(stem + ".ubx", "wb") as out:
    try:
        while True:
            raw, msg = reader.read()
            if raw is None:
                continue
            out.write(raw)
            counts[msg.identity] += 1
            last[msg.identity] = msg
            if time.time() - t_print >= 5:
                t_print = time.time()
                pvt, sat, hw, st = (last.get(k) for k in ("NAV-PVT", "NAV-SAT", "MON-HW", "NAV-STATUS"))
                line = []
                if pvt:
                    line.append(f"fix={pvt.fixType} sv={pvt.numSV} hAcc={pvt.hAcc / 1000:.1f}m")
                if sat and sat.numSvs:
                    cnos = [getattr(sat, f"cno_{i:02d}") for i in range(1, sat.numSvs + 1)]
                    cnos = [c for c in cnos if c > 0]
                    if cnos:
                        line.append(f"cno={statistics.mean(cnos):.1f}dBHz")
                if hw:
                    line.append(f"agc={hw.agcCnt} jamInd={hw.jamInd} jamState={hw.jammingState}")
                if st:
                    line.append(f"spoofDet={st.spoofDetState}")
                print(" | ".join(line) or "waiting for data...")
                print("   msgs:", dict(counts))
    except KeyboardInterrupt:
        pass
print("saved", stem + ".ubx")
