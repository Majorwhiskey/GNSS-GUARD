"""Event-level evaluation of detectors, as defined in docs/EVALUATION.md.

An alarm is one contiguous run of alarmed epochs. A run overlapping an attack
window, or the 5 s before it, is a detection; any other run is a false alarm.

Usage:
  python tools/evaluate.py models/baselines.json \\
      --clean data/features/<test-clean sessions>.csv \\
      --attacked data/features/<session>__<attack>_s<seed>.csv

Prints Markdown tables. Before copying them into docs/RESULTS.md, note the
command and data they came from (see CLAUDE.md).
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

import baselines

EARLY_MS = 5000  # alarms this long before the labelled start still count (label timing is approximate)
MAX_GAP_MS = 1500  # a longer gap between alarmed epochs starts a new event (1 Hz epochs)
# Synthetic injection passes vendor flags through, so these cannot be scored on it.
VENDOR = ("B0", "B1")


def detectors(model):
    return {
        "B0": baselines.b0,
        "B1": lambda df: baselines.b1(df, model),
        "B2": lambda df: baselines.b2(df, model)["any"],
    }


def events(itow, alarm):
    """[(first_itow, last_itow)] for each run of alarmed epochs."""
    runs = []
    for t, a in zip(itow, alarm):
        if not a:
            continue
        if runs and t - runs[-1][1] <= MAX_GAP_MS:
            runs[-1][1] = t
        else:
            runs.append([t, t])
    return [tuple(r) for r in runs]


def score_session(itow, alarm, window=None):
    """Detection, time to detect (s) and false alarms for one session. window: (start, end) iTOW or None if clean."""
    itow, alarm = np.asarray(itow), np.asarray(alarm, bool)
    ev = events(itow, alarm)
    if window is None:
        return {"false_alarms": len(ev), "hours": len(itow) / 3600}
    lo, end = window[0] - EARLY_MS, window[1]
    in_win = (itow >= lo) & (itow < end)
    hit = alarm & in_win
    return {
        "detected": bool(hit.any()),
        "ttd_s": (itow[hit][0] - window[0]) / 1000 if hit.any() else None,
        "false_alarms": sum(1 for a, b in ev if b < lo or a >= end),
        "hours": int((~in_win).sum()) / 3600,
    }


def _label_path(csv, labels_dir):
    return os.path.join(labels_dir, os.path.splitext(os.path.basename(csv))[0] + ".json")


def _window(csv, labels_dir):
    with open(_label_path(csv, labels_dir)) as fh:
        meta = json.load(fh)
    return meta["attack"], (meta["start_itow"], meta["end_itow"])


def evaluate(model, clean_csvs, attacked_csvs, labels_dir="data/synthetic"):
    """(detection rows, false-alarm rows) as lists of dicts."""
    dets = detectors(model)
    fa = {(name, group): [0, 0.0] for name in dets for group in ("clean", "degraded")}
    for csv in clean_csvs:
        # Injected CSVs share their source session's name, so a loose glob picks them up.
        if os.path.exists(_label_path(csv, labels_dir)):
            raise ValueError(f"{csv} has attack labels; pass it with --attacked, not --clean")
        df = pd.read_csv(csv)
        group = "degraded" if "degraded_" in os.path.basename(csv) else "clean"
        for name, fn in dets.items():
            r = score_session(df["iTOW"], fn(df), None)
            fa[name, group][0] += r["false_alarms"]
            fa[name, group][1] += r["hours"]

    by_attack = {}
    for csv in attacked_csvs:
        df = pd.read_csv(csv)
        attack, window = _window(csv, labels_dir)
        for name, fn in dets.items():
            if name not in VENDOR:
                by_attack.setdefault((name, attack), []).append(score_session(df["iTOW"], fn(df), window))

    det_rows = []
    for (name, attack), rs in sorted(by_attack.items()):
        ttd = [r["ttd_s"] for r in rs if r["detected"]]
        det_rows.append({
            "detector": name, "attack": attack, "sessions": len(rs), "detected": len(ttd),
            "missed": len(rs) - len(ttd),
            "ttd_median_s": float(np.median(ttd)) if ttd else None,
            "ttd_p90_s": float(np.percentile(ttd, 90)) if ttd else None,
        })
    fa_rows = [{"detector": name, "group": group, "hours": h, "false_alarms": n,
                "per_hour": n / h if h else None}
               for (name, group), (n, h) in fa.items() if h]
    return det_rows, fa_rows


def _fmt(v):
    return "–" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)


def markdown(rows, cols):
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(_fmt(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("--clean", nargs="*", default=[], help="test-clean and degraded_* feature CSVs")
    p.add_argument("--attacked", nargs="*", default=[], help="feature CSVs of injected logs")
    p.add_argument("--labels-dir", default="data/synthetic")
    args = p.parse_args()
    with open(args.model) as fh:
        model = json.load(fh)
    det_rows, fa_rows = evaluate(model, args.clean, args.attacked, args.labels_dir)
    if det_rows:
        print(markdown(det_rows, ["detector", "attack", "sessions", "detected", "missed", "ttd_median_s", "ttd_p90_s"]))
        print(f"\n{', '.join(VENDOR)} not scored on synthetic attacks: vendor flags are not simulated.\n")
    if fa_rows:
        print(markdown(fa_rows, ["detector", "group", "hours", "false_alarms", "per_hour"]))
