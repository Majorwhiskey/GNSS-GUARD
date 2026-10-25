"""Session split tests: rules per scenario, balance by hours, and assignments that never move."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import split  # noqa: E402


def name(i, sc="clean_static"):
    return f"20261101_{100000 + i:06d}_{sc}"


def test_first_sessions_of_a_scenario_seed_every_split():
    out = split.assign({}, {name(i): 1.0 for i in range(3)})
    assert [out[name(i)]["split"] for i in range(3)] == ["train", "val", "test-clean"]


def test_degraded_and_attack_sessions_are_test_only():
    out = split.assign({}, {name(0, "degraded_foliage"): 0.5, name(1, "attack_texbat_ds2"): 0.2})
    assert out[name(0, "degraded_foliage")]["split"] == "test-clean"
    assert out[name(1, "attack_texbat_ds2")]["split"] == "test-real"


def test_hours_converge_to_targets():
    out = split.assign({}, {name(i): 0.5 + (i % 3) * 0.25 for i in range(60)})
    hours = {s: sum(r["hours"] for r in out.values() if r["split"] == s) for s in split.TARGETS}
    total = sum(hours.values())
    for s, frac in split.TARGETS.items():
        assert hours[s] / total == pytest.approx(frac, abs=0.03)


def test_existing_assignments_never_move():
    first = split.assign({}, {name(i): 1.0 for i in range(5)})
    later = split.assign(first, {name(i): 1.0 for i in range(40)})
    assert all(later[s] == first[s] for s in first)


def test_scenarios_are_balanced_separately():
    out = split.assign({}, {**{name(i): 1.0 for i in range(3)}, **{name(i, "clean_walk"): 1.0 for i in range(3, 6)}})
    walk = [out[name(i, "clean_walk")]["split"] for i in range(3, 6)]
    assert walk == ["train", "val", "test-clean"]


def test_unknown_scenario_or_bad_name_rejected():
    with pytest.raises(ValueError, match="unknown scenario"):
        split.assign({}, {name(0, "balcony"): 1.0})
    with pytest.raises(ValueError, match="not a session name"):
        split.assign({}, {"clean_static": 1.0})


def test_cli_skips_injected_logs_and_writes_splits(tmp_path):
    import pandas as pd
    for i in range(4):
        pd.DataFrame({"iTOW": range(0, 3_600_000, 1000)}).to_csv(tmp_path / f"{name(i)}.csv", index=False)
    pd.DataFrame({"iTOW": [0]}).to_csv(tmp_path / f"{name(0)}__jam_ramp_s1.csv", index=False)
    out = tmp_path / "splits.json"
    subprocess.run([sys.executable, split.__file__, *map(str, tmp_path.glob("*.csv")), "--out", str(out)], check=True)
    sessions = split.load(out)
    assert len(sessions) == 4 and sessions[name(0)]["hours"] == 1.0
    assert split.sessions_in("val", out) == [name(1)]
