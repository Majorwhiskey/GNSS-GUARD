"""Baseline detector tests on synthetic clean and injected logs."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import baselines  # noqa: E402
import features  # noqa: E402
import inject  # noqa: E402
from synth import T0, write_log  # noqa: E402

N = 300
WINDOW = (T0 + 100_000, T0 + 200_000)


@pytest.fixture
def model(tmp_path):
    clean = [features.extract(write_log(tmp_path / f"val{s}.ubx", n_epochs=N, noise_seed=s)) for s in (10, 11)]
    return baselines.fit(clean, quantile=1.0)


@pytest.fixture
def test_log(tmp_path):
    return write_log(tmp_path / "test.ubx", n_epochs=N, noise_seed=12)


def attacked(src, tmp_path, attack, params):
    out = tmp_path / f"{attack}.ubx"
    meta = inject.inject(str(src), str(out), attack, seed=1, params=params, window=WINDOW)
    df = features.extract(out)
    return df, inject.labels(df, meta)


def test_few_false_alarms_on_unseen_clean_log(model, test_log):
    assert baselines.b2(features.extract(test_log), model)["any"].mean() < 0.02


@pytest.mark.parametrize("attack, params, rule", [
    ("spoof_time_push", {"rate_ns_s": 20}, "clk_jump"),
    ("spoof_pos_push", {"speed_m_s": 3, "bearing_deg": 90}, "pos_jump"),
    ("spoof_takeover", {"delta_db": 8, "spread_db": 1, "loss_s": 0}, "cno_elev_corr"),
])
def test_b2_rule_fires_on_matching_attack(model, test_log, tmp_path, attack, params, rule):
    df, lab = attacked(test_log, tmp_path, attack, params)
    rules = baselines.b2(df, model)
    assert rules[rule][lab].mean() > 0.9


def test_vendor_baselines():
    df = pd.DataFrame({"ublox_spoof_state": [1, 2, 3, np.nan], "jam_state": [1, 2, 1, 1], "jam_ind": [5, 5, 50, 5]})
    model = {"thresholds": {"jam_ind": 20}}
    assert list(baselines.b0(df)) == [False, True, True, False]
    assert list(baselines.b1(df, model)) == [False, True, True, False]


def test_missing_features_never_alarm():
    df = pd.DataFrame({"iTOW": [0, 1000], "clk_jump": [np.nan, np.nan]})
    model = {"thresholds": {"cno_elev_corr": 0.5, "cno_delta_mean": 3, "clk_jump": 10, "pos_jump": None}}
    assert not baselines.b2(df, model)["any"].any()
