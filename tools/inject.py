"""Inject synthetic attacks into a clean .ubx log, at the UBX message level.

Usage: python tools/inject.py data/raw/<session>.ubx --attack spoof_takeover --seeds 1
       python tools/inject.py data/raw/*.ubx --attack all --seeds 1-5

Writes data/synthetic/<session>__<attack>_s<seed>.ubx plus a .json with the
attack window (iTOW, ms, end exclusive) and parameters. Run features.py on the
output unchanged: injecting messages rather than feature columns keeps every
feature formula in one place.

Vendor flags (spoofDetState, jamInd, jammingState) pass through as recorded.
u-blox's detector cannot be simulated, so baselines B0 and B1 are only
meaningful on real attack data. Attack models are in docs/DATASETS.md.
"""
import argparse
import json
import math
import os

import numpy as np
from pyubx2 import GET, UBX_PROTOCOL, UBXMessage, UBXReader

ATTACKS = ("jam_ramp", "spoof_takeover", "spoof_time_push", "spoof_pos_push", "meaconing")
EARTH_R = 6371000
# Assumed receiver behaviour, not measured on this unit yet.
SV_USED_MIN_CNO = 25  # dB-Hz, weaker satellites are dropped from the fix
TRACK_MIN_CNO = 12  # dB-Hz, weaker satellites lose lock
MAX_CNO = 55  # dB-Hz, ceiling for spoofed signals
MIN_SATS_FOR_FIX = 4


def sample_params(attack, rng):
    u = lambda lo, hi: float(rng.uniform(lo, hi))
    if attack == "jam_ramp":
        return {"rate_db_s": u(0.2, 1.0)}
    if attack == "spoof_takeover":
        return {"delta_db": u(5, 10), "spread_db": u(0.5, 1.5), "loss_s": int(rng.integers(0, 4))}
    if attack == "spoof_time_push":
        return {"rate_ns_s": u(2, 50)}
    if attack == "spoof_pos_push":
        return {"speed_m_s": u(0.5, 5), "bearing_deg": u(0, 360)}
    if attack == "meaconing":
        return {"delay_us": u(1, 100), "offset_m": u(50, 2000), "bearing_deg": u(0, 360),
                "cno_offset_db": u(-3, 6), "loss_s": int(rng.integers(0, 4))}
    raise ValueError(attack)


def sample_window(itows, rng):
    """Start 30-60% into the log, last 60-300 s or until the log ends."""
    n = len(itows)
    if n < 20:
        raise ValueError(f"log too short for injection: {n} epochs")
    start = int(rng.uniform(0.3, 0.6) * n)
    end = start + int(rng.uniform(60, 300))
    return itows[start], itows[end] if end < n else itows[-1] + 1000


def read_epochs(path):
    """[(iTOW, [(raw, msg), ...])]. MON-HW has no iTOW and joins the epoch current when it arrives, as in features.py."""
    epochs, cur, itow = [], [], None
    with open(path, "rb") as fh:
        for raw, msg in UBXReader(fh, protfilter=UBX_PROTOCOL, quitonerror=0):
            if msg is None:
                continue
            t = getattr(msg, "iTOW", None)
            if t is not None and t != itow:
                if cur:
                    epochs.append((itow, cur))
                cur, itow = [], t
            cur.append((raw, msg))
    if cur:
        epochs.append((itow, cur))
    return epochs


def _shift(kw, north_m, east_m):
    kw["lat"] += math.degrees(north_m / EARTH_R)
    kw["lon"] += math.degrees(east_m / (EARTH_R * math.cos(math.radians(kw["lat"]))))


def _sat_keys(kw):
    return [f"{i:02d}" for i in range(1, kw["numSvs"] + 1)]


def _lose_lock(kw):
    for k in _sat_keys(kw):
        kw[f"cno_{k}"], kw[f"svUsed_{k}"], kw[f"prRes_{k}"] = 0, 0, 0.0


def attack_epoch(msgs, attack, p, t, state, rng):
    """Modify one epoch's message fields in place. msgs: {identity: kw}; t: seconds since attack start."""
    sat, pvt, clk, hw, st = (msgs.get(k) for k in ("NAV-SAT", "NAV-PVT", "NAV-CLOCK", "MON-HW", "NAV-STATUS"))
    lost = attack in ("spoof_takeover", "meaconing") and t < p["loss_s"]

    if sat:
        if lost:
            _lose_lock(sat)
        elif attack == "jam_ramp":
            drop = p["rate_db_s"] * t
            for k in _sat_keys(sat):
                if sat[f"cno_{k}"] == 0:
                    continue
                c = round(sat[f"cno_{k}"] - drop)
                sat[f"cno_{k}"] = c if c >= TRACK_MIN_CNO else 0
                if c < SV_USED_MIN_CNO:
                    sat[f"svUsed_{k}"], sat[f"prRes_{k}"] = 0, 0.0
        elif attack == "spoof_takeover":
            keys = [k for k in _sat_keys(sat) if sat[f"cno_{k}"] > 0]
            if keys:
                # One transmitter: every satellite near the same strong level, unrelated to elevation.
                level = np.mean([sat[f"cno_{k}"] for k in keys]) + p["delta_db"]
                for k in keys:
                    sv = (sat[f"gnssId_{k}"], sat[f"svId_{k}"])
                    off = state.setdefault(sv, rng.normal(0, p["spread_db"]))
                    sat[f"cno_{k}"] = int(np.clip(round(level + off + rng.normal(0, 0.3)), 1, MAX_CNO))
        elif attack == "meaconing":
            for k in _sat_keys(sat):
                if sat[f"cno_{k}"] > 0:
                    sat[f"cno_{k}"] = int(np.clip(round(sat[f"cno_{k}"] + p["cno_offset_db"]), 1, MAX_CNO))
        if attack == "jam_ramp" or lost:
            n_used = sum(sat[f"svUsed_{k}"] for k in _sat_keys(sat))
            if pvt:
                pvt["numSV"] = min(pvt["numSV"], n_used)
            if n_used < MIN_SATS_FOR_FIX:
                if pvt:
                    pvt["fixType"], pvt["gnssFixOk"] = 0, 0
                if st:
                    st["gpsFix"], st["gpsFixOk"] = 0, 0

    if pvt:
        if attack == "spoof_pos_push":
            d = p["speed_m_s"] * t  # velocity fields untouched: the push is not in the reported motion
            b = math.radians(p["bearing_deg"])
            _shift(pvt, d * math.cos(b), d * math.sin(b))
        elif attack == "meaconing":
            b = math.radians(p["bearing_deg"])
            _shift(pvt, p["offset_m"] * math.cos(b), p["offset_m"] * math.sin(b))

    if clk:
        if attack == "spoof_time_push":
            clk["clkB"] += round(p["rate_ns_s"] * t)  # clkD untouched: drift does not explain the push
        elif attack == "meaconing":
            clk["clkB"] += round(p["delay_us"] * 1000)

    if hw and attack == "jam_ramp":
        # Noise up and AGC gain down, saturating at 30 dB of C/N0 loss. Uncalibrated and kept
        # deliberately mild, so jamming results do not lean on an invented MON-HW response.
        x = min(p["rate_db_s"] * t, 30) / 30
        hw["noisePerMS"] = round(hw["noisePerMS"] * (1 + 3 * x))
        hw["agcCnt"] = round(hw["agcCnt"] * (1 - 0.5 * x))


def inject(src, out, attack, seed, params=None, window=None):
    """Write an attacked copy of src to out (+ .json). params / window override the seeded draws."""
    rng = np.random.default_rng(seed)
    epochs = read_epochs(src)
    itows = [t for t, _ in epochs if t is not None]
    params = params or sample_params(attack, rng)
    start, end = window or sample_window(itows, rng)
    state = {}
    with open(out, "wb") as fh:
        for itow, group in epochs:
            if itow is None or not start <= itow < end:
                fh.write(b"".join(raw for raw, _ in group))
                continue
            fields = [{k: v for k, v in vars(m).items() if not k.startswith("_")} for _, m in group]
            attack_epoch({m.identity: kw for (_, m), kw in zip(group, fields)}, attack, params,
                         (itow - start) / 1000, state, rng)
            fh.write(b"".join(UBXMessage(m.msg_cls, m.msg_id, GET, **kw).serialize()
                              for (_, m), kw in zip(group, fields)))
    meta = {"source": os.path.basename(src), "attack": attack, "seed": seed, "params": params,
            "start_itow": start, "end_itow": end}
    with open(os.path.splitext(out)[0] + ".json", "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def labels(df, meta):
    """Per-epoch attack label for a feature DataFrame of an injected log."""
    return (df["iTOW"] >= meta["start_itow"]) & (df["iTOW"] < meta["end_itow"])


def _seeds(spec):
    lo, _, hi = spec.partition("-")
    return range(int(lo), int(hi or lo) + 1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("logs", nargs="+")
    p.add_argument("--attack", required=True, choices=ATTACKS + ("all",))
    p.add_argument("--seeds", default="1", help="one seed or a range, e.g. 1-5")
    p.add_argument("--out-dir", default="data/synthetic")
    args = p.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    for src in args.logs:
        stem = os.path.splitext(os.path.basename(src))[0]
        for attack in ATTACKS if args.attack == "all" else (args.attack,):
            for seed in _seeds(args.seeds):
                out = os.path.join(args.out_dir, f"{stem}__{attack}_s{seed}.ubx")
                meta = inject(src, out, attack, seed)
                print(f"{out}: {attack} {meta['start_itow']}-{meta['end_itow']} {meta['params']}")
