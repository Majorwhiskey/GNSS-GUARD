"""Feature pipeline tests on synthetic UBX logs. Run with: .venv/bin/pytest"""
import math
import sys
from pathlib import Path

import pytest
from pyubx2 import GET, UBXMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import features  # noqa: E402

N_EPOCHS = 10
T0 = 100_000  # iTOW of first epoch, ms


def nav_sat(itow, cnos, elevs):
    kw = dict(iTOW=itow, version=1, numSvs=len(cnos))
    for i, (c, e) in enumerate(zip(cnos, elevs), 1):
        kw.update({f"gnssId_{i:02d}": 0, f"svId_{i:02d}": i, f"cno_{i:02d}": c, f"elev_{i:02d}": e,
                   f"azim_{i:02d}": i * 50, f"prRes_{i:02d}": 1.0, f"svUsed_{i:02d}": 1})
    return UBXMessage("NAV", "NAV-SAT", GET, **kw).serialize()


def write_log(path, clock_jump_at=None, spoof_from=None):
    out = bytearray()
    for e in range(N_EPOCHS):
        t = T0 + e * 1000
        out += UBXMessage("NAV", "NAV-PVT", GET, iTOW=t, fixType=3, gnssFixOk=1, numSV=6,
                          lat=12.97 + e * 1e-5, lon=77.59, height=900_000, hAcc=2500, vAcc=4000,
                          sAcc=300, gSpeed=1112, velN=1112, velE=0, headMot=0, pDOP=1.5).serialize()
        elevs = [15, 25, 40, 55, 70, 85]
        if spoof_from is not None and e >= spoof_from:
            cnos = [48, 47, 48, 49, 48, 47]  # uniform and strong, uncorrelated with elevation
        else:
            cnos = [28, 32, 37, 41, 44, 47]
        out += nav_sat(t, cnos, elevs)
        out += UBXMessage("NAV", "NAV-STATUS", GET, iTOW=t, gpsFix=3, spoofDetState=1).serialize()
        bias = 1000 + e * 50 + (5000 if clock_jump_at is not None and e >= clock_jump_at else 0)
        out += UBXMessage("NAV", "NAV-CLOCK", GET, iTOW=t, clkB=bias, clkD=50, tAcc=20, fAcc=5).serialize()
        out += UBXMessage("MON", "MON-HW", GET, noisePerMS=90, agcCnt=4000, jamInd=10, jammingState=1).serialize()
    path.write_bytes(bytes(out))
    return path


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
