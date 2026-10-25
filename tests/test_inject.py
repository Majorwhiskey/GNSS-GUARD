"""Attack injection tests: each attack leaves its intended signature and nothing else."""
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import features  # noqa: E402
import inject  # noqa: E402
from synth import T0, write_log  # noqa: E402

N = 300
START, END = T0 + 100_000, T0 + 200_000  # epochs 100-199


@pytest.fixture
def clean(tmp_path):
    return write_log(tmp_path / "clean.ubx", n_epochs=N, noise_seed=0)


def run(clean, tmp_path, attack, params):
    out = tmp_path / f"{attack}.ubx"
    meta = inject.inject(str(clean), str(out), attack, seed=1, params=params, window=(START, END))
    return features.extract(clean), features.extract(out), meta


def window(df):
    return df[(df["iTOW"] >= START) & (df["iTOW"] < END)].reset_index(drop=True)


@pytest.mark.parametrize("attack", inject.ATTACKS)
def test_only_the_window_changes_and_vendor_flags_pass_through(clean, tmp_path, attack):
    base, df, _ = run(clean, tmp_path, attack, None)
    # Epoch END still diffs against an attacked epoch. Dtypes may widen to float
    # when the window drops a column on some epochs, so compare values only.
    before, after = base["iTOW"] < START, base["iTOW"] > END
    pd.testing.assert_frame_equal(df[before], base[before], check_dtype=False)
    pd.testing.assert_frame_equal(df[after], base[after], check_dtype=False)
    for col in ("ublox_spoof_state", "jam_ind", "jam_state"):
        assert (window(df)[col] == window(base)[col]).all()


def test_source_untouched_and_seeds_reproducible(clean, tmp_path):
    digest = hashlib.sha256(clean.read_bytes()).hexdigest()
    a, b, c = (tmp_path / n for n in ("a.ubx", "b.ubx", "c.ubx"))
    inject.inject(str(clean), str(a), "spoof_takeover", seed=7)
    inject.inject(str(clean), str(b), "spoof_takeover", seed=7)
    inject.inject(str(clean), str(c), "spoof_takeover", seed=8)
    assert hashlib.sha256(clean.read_bytes()).hexdigest() == digest
    assert a.read_bytes() == b.read_bytes() != c.read_bytes()
    assert json.loads(a.with_suffix(".json").read_text())["seed"] == 7


def test_labels_cover_exactly_the_window(clean, tmp_path):
    _, df, meta = run(clean, tmp_path, "spoof_time_push", {"rate_ns_s": 20})
    lab = inject.labels(df, meta)
    assert lab.sum() == 100
    assert df["iTOW"][lab].min() == START


def test_jam_ramp_fades_all_satellites_until_fix_is_lost(clean, tmp_path):
    base, df, _ = run(clean, tmp_path, "jam_ramp", {"rate_db_s": 0.5})
    w, wb = window(df), window(base)
    assert w["cno_mean"][10] == pytest.approx(wb["cno_mean"][10] - 5)
    assert w["n_tracked"].iloc[-1] == 0
    assert w["fix"].iloc[-1] == 0
    assert w["noise"].iloc[-1] > 3 * wb["noise"].iloc[-1]


def test_spoof_takeover_raises_and_flattens_cno(clean, tmp_path):
    base, df, _ = run(clean, tmp_path, "spoof_takeover", {"delta_db": 8, "spread_db": 1, "loss_s": 0})
    w, wb = window(df), window(base)
    assert w["cno_delta_mean"][0] > 5  # seamless capture: every satellite jumps together
    assert w["cno_elev_corr"].median() < 0.5 < wb["cno_elev_corr"].median()
    assert (w["cno_std"] < wb["cno_std"]).all()


def test_spoof_takeover_with_loss_of_lock(clean, tmp_path):
    _, df, _ = run(clean, tmp_path, "spoof_takeover", {"delta_db": 8, "spread_db": 1, "loss_s": 2})
    w = window(df)
    assert list(w["n_tracked"][:2]) == [0, 0]
    assert list(w["fix"][:3]) == [0, 0, 3]


def test_spoof_time_push_moves_clock_beyond_drift(clean, tmp_path):
    base, df, _ = run(clean, tmp_path, "spoof_time_push", {"rate_ns_s": 20})
    w, wb = window(df), window(base)
    assert (w["clk_jump"][1:] - wb["clk_jump"][1:]).mean() == pytest.approx(20, abs=0.5)
    assert (w["clk_drift"] == wb["clk_drift"]).all()


def test_spoof_pos_push_moves_position_not_velocity(clean, tmp_path):
    base, df, _ = run(clean, tmp_path, "spoof_pos_push", {"speed_m_s": 3, "bearing_deg": 90})
    w, wb = window(df), window(base)
    assert w["pos_jump"][1:].mean() == pytest.approx(3, abs=0.3)
    assert (w["vel_n"] == wb["vel_n"]).all() and (w["vel_e"] == wb["vel_e"]).all()


def test_meaconing_steps_clock_position_and_power(clean, tmp_path):
    base, df, _ = run(clean, tmp_path, "meaconing",
                      {"delay_us": 50, "offset_m": 1000, "bearing_deg": 0, "cno_offset_db": 4, "loss_s": 0})
    w, wb = window(df), window(base)
    assert w["clk_jump"][0] == pytest.approx(50_000, abs=10)
    assert w["pos_jump"][0] == pytest.approx(1000, abs=2)
    assert (w["cno_mean"] - wb["cno_mean"]).abs().max() == pytest.approx(4)
