"""Firmware feature library (firmware/lib/gnss_features) must match tools/features.py.

Builds the library natively with the system C++ compiler and compares its output
column by column on the same UBX logs. Skipped when no compiler is available.
"""
import io
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from pyubx2 import GET, UBX_PROTOCOL, UBXMessage, UBXReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import device_parity  # noqa: E402
import features  # noqa: E402
import inject  # noqa: E402
from synth import CLEAN_CNOS, ELEVS, nav_sat, write_log  # noqa: E402

LIB = ROOT / "firmware" / "lib" / "gnss_features" / "src"
CXX = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
pytestmark = pytest.mark.skipif(CXX is None, reason="no C++ compiler")


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    exe = tmp_path_factory.mktemp("native") / "features_cli"
    subprocess.run([CXX, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", f"-I{LIB}",
                    str(ROOT / "tests" / "native" / "features_cli.cpp"), str(LIB / "gnss_features.cpp"),
                    "-o", str(exe)], check=True)
    return exe


def native(cli, path):
    out = subprocess.run([str(cli), str(path)], check=True, capture_output=True, text=True).stdout
    return pd.read_csv(io.StringIO(out))


def assert_parity(cli, path):
    problems = device_parity.mismatches(features.extract(path), native(cli, path))
    assert not problems, "\n".join(problems)


def messages(path):
    with open(path, "rb") as fh:
        return [raw for raw, m in UBXReader(fh, protfilter=UBX_PROTOCOL, quitonerror=0) if m]


def test_clean_log(cli, tmp_path):
    assert_parity(cli, write_log(tmp_path / "clean.ubx", n_epochs=200, noise_seed=0))


def test_handmade_spoof_and_clock_jump(cli, tmp_path):
    assert_parity(cli, write_log(tmp_path / "spoof.ubx", spoof_from=5))
    assert_parity(cli, write_log(tmp_path / "jump.ubx", clock_jump_at=4))


@pytest.mark.parametrize("attack", inject.ATTACKS)
@pytest.mark.parametrize("seed", [1, 2])
def test_injected_attacks(cli, tmp_path, attack, seed):
    src = write_log(tmp_path / "clean.ubx", n_epochs=300, noise_seed=seed)
    out = tmp_path / f"{attack}.ubx"
    inject.inject(str(src), str(out), attack, seed=seed)
    assert_parity(cli, out)


def test_loss_of_lock_epochs(cli, tmp_path):
    src = write_log(tmp_path / "clean.ubx", n_epochs=60, noise_seed=3)
    out = tmp_path / "takeover.ubx"
    inject.inject(str(src), str(out), "spoof_takeover", seed=1,
                  params={"delta_db": 8, "spread_db": 1, "loss_s": 3}, window=(120_000, 140_000))
    assert_parity(cli, out)


def test_missing_messages_dropped_epoch_and_early_mon_hw(cli, tmp_path):
    msgs = messages(write_log(tmp_path / "clean.ubx", n_epochs=40, noise_seed=4))
    per_epoch = len(msgs) // 40
    kept = []
    for i, raw in enumerate(msgs):
        epoch, ident = i // per_epoch, raw[2:4]
        if epoch == 10:  # whole epoch lost
            continue
        if ident == b"\x01\x22" and epoch % 7 == 3:  # NAV-CLOCK missing now and then
            continue
        if ident == b"\x0a\x09" and epoch in (20, 21):  # MON-HW gap: last value carries forward
            continue
        kept.append(raw)
    mon_hw = next(r for r in msgs if r[2:4] == b"\x0a\x09")
    path = tmp_path / "gappy.ubx"
    path.write_bytes(mon_hw + b"".join(kept))  # MON-HW before the first epoch
    assert_parity(cli, path)


def test_corrupted_message_is_dropped_by_both(cli, tmp_path):
    msgs = messages(write_log(tmp_path / "clean.ubx", n_epochs=20, noise_seed=5))
    bad = bytearray(msgs[30])
    bad[-1] ^= 0xFF  # break the checksum
    msgs[30] = bytes(bad)
    path = tmp_path / "corrupt.ubx"
    path.write_bytes(b"".join(msgs))
    assert_parity(cli, path)


def test_heading_wraps_through_north(cli, tmp_path):
    # Synthetic logs otherwise all head due north, which would hide a wrong wrap (fmod vs Python's %).
    out = bytearray()
    for e in range(30):
        t = 100_000 + e * 1000
        out += UBXMessage("NAV", "NAV-PVT", GET, iTOW=t, fixType=3, gnssFixOk=1, numSV=6, lat=12.97, lon=77.59,
                          headMot=(350 + 4 * e) % 360, gSpeed=1000).serialize()
        out += nav_sat(t, CLEAN_CNOS, ELEVS)
    path = tmp_path / "turn.ubx"
    path.write_bytes(bytes(out))
    assert_parity(cli, path)
