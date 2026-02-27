from __future__ import annotations

import pandas as pd

from scripts.build_oco_strategy_bible import _stage04_policy_for_metric, _stage04_policy_rollup_rows


def test_stage04_policy_band_boundaries() -> None:
    e11_green = _stage04_policy_for_metric("E11_session_overshoot_dispersion", 0.95)
    e11_amber = _stage04_policy_for_metric("E11_session_overshoot_dispersion", 1.10)
    e11_red = _stage04_policy_for_metric("E11_session_overshoot_dispersion", 1.50)
    assert e11_green["band"] == "green"
    assert e11_amber["band"] == "amber"
    assert e11_red["band"] == "red"

    e12_green = _stage04_policy_for_metric("E12_cap_plateau_width_pips", 0.60)
    e12_amber = _stage04_policy_for_metric("E12_cap_plateau_width_pips", 0.35)
    e12_red = _stage04_policy_for_metric("E12_cap_plateau_width_pips", 0.20)
    assert e12_green["band"] == "green"
    assert e12_amber["band"] == "amber"
    assert e12_red["band"] == "red"


def test_stage04_policy_rollup_uses_worst_action_precedence() -> None:
    rows = pd.DataFrame(
        [
            {"symbol": "EURUSD", "metric_id": "E11_session_overshoot_dispersion", "band": "green", "action_code": "A0_MONITOR", "action_summary": "ok"},
            {"symbol": "EURUSD", "metric_id": "E12_cap_plateau_width_pips", "band": "amber", "action_code": "A1_RECALIBRATE_CAP", "action_summary": "cap"},
            {"symbol": "EURUSD", "metric_id": "E13_nonfill_opportunity_cost_pips", "band": "red", "action_code": "A3_HALT_RECALIBRATE", "action_summary": "halt"},
        ]
    )
    out = _stage04_policy_rollup_rows(rows)
    assert len(out) == 1
    r = out.iloc[0]
    assert r["worst_band"] == "red"
    assert r["recommended_action_code"] == "A3_HALT_RECALIBRATE"
    assert int(r["red_metric_count"]) == 1
    assert int(r["amber_metric_count"]) == 1

