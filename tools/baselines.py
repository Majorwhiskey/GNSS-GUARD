"""Baseline detectors B0-B2 from docs/EVALUATION.md, run on feature DataFrames.

B0  u-blox spoofDetState >= 2
B1  u-blox jammingState >= 2, or jamInd above a threshold fitted on clean data
B2  hand rules on cno_elev_corr, cno_delta_mean, clk_jump, pos_jump, each
    threshold fitted on clean sessions only

Usage:
  python tools/baselines.py fit data/features/<clean>.csv ... --out models/baselines.json
  python tools/baselines.py apply models/baselines.json data/features/<session>.csv ...

Fit only on the val split; thresholds are never tuned on test data. For an
injected log, `apply` reads the attack window from data/synthetic/<stem>.json.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

# Feature -> which tail is anomalous.
B2_RULES = {"cno_elev_corr": "low", "cno_delta_mean": "abs", "clk_jump": "abs", "pos_jump": "high"}


def _col(df, name):
    return df[name] if name in df else pd.Series(np.nan, index=df.index)


def fit(clean, quantile=0.999):
    """Thresholds at the given per-epoch quantile of clean data. A rule with no clean data is disabled (None)."""
    df = pd.concat(clean, ignore_index=True)
    thr = {}
    for name, tail in {**B2_RULES, "jam_ind": "high"}.items():
        x = _col(df, name).dropna()
        if x.empty:
            thr[name] = None
        elif tail == "low":
            thr[name] = float(x.quantile(1 - quantile))
        elif tail == "abs":
            thr[name] = float(x.abs().quantile(quantile))
        else:
            thr[name] = float(x.quantile(quantile))
    return {"quantile": quantile, "thresholds": thr}


def b0(df):
    return _col(df, "ublox_spoof_state") >= 2


def b1(df, model):
    alarm = _col(df, "jam_state") >= 2
    thr = model["thresholds"].get("jam_ind")
    if thr is not None:
        alarm |= _col(df, "jam_ind") > thr
    return alarm


def b2(df, model):
    """One boolean column per rule plus `any`. NaN features never alarm."""
    out = pd.DataFrame(index=df.index)
    for name, tail in B2_RULES.items():
        thr, x = model["thresholds"].get(name), _col(df, name)
        if thr is None:
            out[name] = False
        elif tail == "low":
            out[name] = x < thr
        elif tail == "abs":
            out[name] = x.abs() > thr
        else:
            out[name] = x > thr
    out["any"] = out[list(B2_RULES)].any(axis=1)
    return out


def _report(path, model, labels_dir):
    df = pd.read_csv(path)
    alarms = {"B0": b0(df), "B1": b1(df, model), "B2": b2(df, model)["any"]}
    meta_path = os.path.join(labels_dir, os.path.splitext(os.path.basename(path))[0] + ".json")
    print(f"{path}: {len(df)} epochs")
    if os.path.exists(meta_path):
        with open(meta_path) as fh:
            meta = json.load(fh)
        attack = (df["iTOW"] >= meta["start_itow"]) & (df["iTOW"] < meta["end_itow"])
        print(f"  {meta['attack']}, {int(attack.sum())} attack epochs")
        for name, a in alarms.items():
            hits = df["iTOW"][a & attack]
            ttd = f"{(hits.iloc[0] - meta['start_itow']) / 1000:.0f} s" if len(hits) else "missed"
            print(f"  {name}: first alarm {ttd}, {int((a & attack).sum())} attack epochs flagged, "
                  f"{int((a & ~attack).sum())} false-alarm epochs")
    else:
        for name, a in alarms.items():
            print(f"  {name}: {int(a.sum())} alarm epochs")
    rules = b2(df, model)
    print("  B2 rules:", {r: int(rules[r].sum()) for r in B2_RULES})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("csvs", nargs="+")
    f.add_argument("--quantile", type=float, default=0.999)
    f.add_argument("--out", default="models/baselines.json")
    a = sub.add_parser("apply")
    a.add_argument("model")
    a.add_argument("csvs", nargs="+")
    a.add_argument("--labels-dir", default="data/synthetic")
    args = p.parse_args()
    if args.cmd == "fit":
        model = fit([pd.read_csv(c) for c in args.csvs], args.quantile)
        model["fitted_on"] = [os.path.basename(c) for c in args.csvs]
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(model, fh, indent=2)
        print(json.dumps(model["thresholds"], indent=2))
    else:
        with open(args.model) as fh:
            model = json.load(fh)
        for c in args.csvs:
            _report(c, model, args.labels_dir)
