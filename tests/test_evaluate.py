"""Evaluation harness tests: event merging, scoring rules, and an end-to-end run on synthetic logs."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import baselines  # noqa: E402
import evaluate  # noqa: E402
import features  # noqa: E402
import inject  # noqa: E402
from synth import T0, write_log  # noqa: E402

ITOW = [i * 1000 for i in range(20)]


def alarms(*idx):
    return [i in idx for i in range(20)]


def test_contiguous_alarms_merge_and_gaps_split():
    assert evaluate.events(ITOW, alarms(2, 3, 4, 7, 8)) == [(2000, 4000), (7000, 8000)]


def test_alarm_shortly_before_attack_counts_as_detection():
    r = evaluate.score_session(ITOW, alarms(7), window=(10_000, 15_000))
    assert r["detected"] and r["ttd_s"] == -3 and r["false_alarms"] == 0


def test_alarm_outside_window_is_false_alarm():
    r = evaluate.score_session(ITOW, alarms(1, 12, 18), window=(10_000, 15_000))
    assert r["detected"] and r["ttd_s"] == 2
    assert r["false_alarms"] == 2
    assert r["hours"] == pytest.approx(10 / 3600)  # 20 epochs minus 5 s early margin and 5 s window


def test_missed_attack():
    r = evaluate.score_session(ITOW, alarms(1), window=(10_000, 15_000))
    assert not r["detected"] and r["ttd_s"] is None


def test_end_to_end_on_synthetic_logs(tmp_path):
    def csv(ubx):
        out = ubx.with_suffix(".csv")
        features.extract(ubx).to_csv(out, index=False)
        return out

    val = [features.extract(write_log(tmp_path / f"val{s}.ubx", n_epochs=300, noise_seed=s)) for s in (1, 2)]
    model = baselines.fit(val, quantile=1.0)
    test_clean = write_log(tmp_path / "clean_static_test.ubx", n_epochs=300, noise_seed=3)
    attacked = tmp_path / "clean_static_test__spoof_time_push_s1.ubx"
    inject.inject(str(test_clean), str(attacked), "spoof_time_push", seed=1,
                  params={"rate_ns_s": 30}, window=(T0 + 100_000, T0 + 200_000))

    det, fa = evaluate.evaluate(model, [csv(test_clean)], [csv(attacked)], labels_dir=tmp_path)
    b2 = next(r for r in det if r["detector"] == "B2")
    assert b2["attack"] == "spoof_time_push" and b2["detected"] == 1
    assert b2["ttd_median_s"] <= 2
    assert not any(r["detector"] in evaluate.VENDOR for r in det)
    assert {r["group"] for r in fa} == {"clean"}
    with pytest.raises(ValueError, match="attack labels"):
        evaluate.evaluate(model, [csv(attacked)], [], labels_dir=tmp_path)
