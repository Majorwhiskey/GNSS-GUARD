"""Feature pipeline tests on synthetic UBX logs. Run with: .venv/bin/pytest"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import features  # noqa: E402
from synth import N_EPOCHS, T0, write_log  # noqa: E402


def test_one_row_per_epoch(tmp_path):
    df = features.extract(write_log(tmp_path / "clean.ubx"))
    assert len(df) == N_EPOCHS
    assert list(df["iTOW"]) == [T0 + e * 1000 for e in range(N_EPOCHS)]


def test_clean_sky_has_positive_cno_elevation_correlation(tmp_path):
    df = features.extract(write_log(tmp_path / "clean.ubx"))
    assert (df["cno_elev_corr"] > 0.9).all()


def test_spoofed_sky_breaks_correlation_and_shows_common_mode_jump(tmp_path):
    df = features.extract(write_log(tmp_path / "spoof.ubx", spoof_from=5))
    assert df["cno_elev_corr"].iloc[6] < 0.5
    assert df["cno_delta_mean"].iloc[5] > 5  # every satellite jumped together


def test_clock_jump_detected(tmp_path):
    df = features.extract(write_log(tmp_path / "jump.ubx", clock_jump_at=4))
    assert df["clk_jump"].iloc[4] == pytest.approx(5000)
    assert df["clk_jump"].drop(index=[0, 4]).abs().max() == pytest.approx(0)


def test_position_consistent_with_velocity(tmp_path):
    df = features.extract(write_log(tmp_path / "clean.ubx"))
    # 1e-5 deg latitude per second is about 1.112 m/s, matching velN
    assert df["pos_jump"].iloc[1:].max() < 0.05
    assert math.isnan(df["pos_jump"].iloc[0])
