"""Assign recorded sessions to evaluation splits, by session and never by row.

Usage: python tools/split.py data/features/*.csv

Updates data/splits.json (committed). A session keeps its split forever once
assigned; new sessions are added, balanced by hours within each scenario so
every split sees every kind of recording. Rules from docs/EVALUATION.md:

  clean_*     train / val / test-clean, 70 / 15 / 15 by hours
  degraded_*  test-clean (hard negatives, never trained or tuned on)
  attack_*    test-real

Injected logs (`<session>__<attack>_s<seed>`) are not sessions and are skipped;
inject attacks only from sessions of the split they will be used in.
"""
import argparse
import json
import os
import sys

import pandas as pd

TARGETS = {"train": 0.70, "val": 0.15, "test-clean": 0.15}
SPLITS_PATH = "data/splits.json"


def scenario(stem):
    """'20261101_101500_clean_static' -> 'clean_static'."""
    parts = stem.split("_", 2)
    if len(parts) < 3 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise ValueError(f"not a session name (YYYYMMDD_HHMMSS_<scenario>): {stem}")
    return parts[2]


def assign(existing, new_hours):
    """existing: {session: {"split", "hours"}}; new_hours: {session: hours}. Returns the updated mapping."""
    out = dict(existing)
    for stem in sorted(new_hours):
        if stem in out:
            continue
        sc = scenario(stem)
        if sc.startswith("degraded_"):
            split = "test-clean"
        elif sc.startswith("attack_"):
            split = "test-real"
        elif sc.startswith("clean_"):
            have = {s: 0.0 for s in TARGETS}
            for other, rec in out.items():
                if scenario(other) == sc:
                    have[rec["split"]] += rec["hours"]
            empty = [s for s in TARGETS if have[s] == 0]
            if empty:
                split = empty[0]  # first sessions of a scenario seed every split
            else:
                total = sum(have.values()) + new_hours[stem]
                split = max(TARGETS, key=lambda s: TARGETS[s] * total - have[s])
        else:
            raise ValueError(f"unknown scenario '{sc}' in {stem}; see docs/DATA_COLLECTION.md")
        out[stem] = {"split": split, "hours": round(new_hours[stem], 4)}
    return out


def load(path=SPLITS_PATH):
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)["sessions"]


def sessions_in(split, path=SPLITS_PATH):
    return sorted(s for s, rec in load(path).items() if rec["split"] == split)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csvs", nargs="+", help="feature CSVs, one per session")
    p.add_argument("--out", default=SPLITS_PATH)
    args = p.parse_args()
    new = {}
    for csv in args.csvs:
        stem = os.path.splitext(os.path.basename(csv))[0]
        if "__" in stem:
            print(f"skipping injected log {stem}", file=sys.stderr)
            continue
        new[stem] = len(pd.read_csv(csv, usecols=["iTOW"])) / 3600  # 1 Hz epochs
    before = load(args.out)
    sessions = assign(before, new)
    with open(args.out, "w") as fh:
        json.dump({"targets": TARGETS, "sessions": sessions}, fh, indent=2, sort_keys=True)
        fh.write("\n")
    for stem in sorted(set(sessions) - set(before)):
        print(f"{stem}: {sessions[stem]['split']}")
    totals = pd.DataFrame(sessions.values()).groupby("split")["hours"].agg(["count", "sum"])
    print(totals.rename(columns={"count": "sessions", "sum": "hours"}).round(2).to_string())
