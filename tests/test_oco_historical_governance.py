from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.legacy.freeze_oco_historical_governance import (
    _filter_months,
    _model_valid_through,
    _state_universe_for_month,
    run,
)


def test_state_universe_for_month_hash_stable_under_row_order(tmp_path: Path) -> None:
    rows = [
        {
            "test_month": "2025-08",
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "horizon": 5,
            "state_id": "s1",
            "family": "oco_first_touch",
            "barrier_pips": 2.0,
            "regime_desc": "r1",
        },
        {
            "test_month": "2025-08",
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "horizon": 6,
            "state_id": "s2",
            "family": "oco_first_touch",
            "barrier_pips": 3.0,
            "regime_desc": "r2",
        },
    ]
    a = pd.DataFrame(rows)
    b = a.iloc[::-1].reset_index(drop=True)
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    a.to_csv(p1, index=False)
    b.to_csv(p2, index=False)

    _, h1 = _state_universe_for_month(p1, "EURUSD", "2025-08")
    _, h2 = _state_universe_for_month(p2, "EURUSD", "2025-08")
    assert h1 == h2


def test_state_universe_for_month_requires_rows(tmp_path: Path) -> None:
    p = tmp_path / "states.csv"
    pd.DataFrame(
        [
            {
                "test_month": "2025-07",
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            }
        ]
    ).to_csv(p, index=False)

    with pytest.raises(ValueError):
        _state_universe_for_month(p, "EURUSD", "2025-08")


def test_filter_months_applies_explicit_and_bounds() -> None:
    out = _filter_months(
        months=["2025-07", "2025-08", "2025-09", "2025-10"],
        explicit_months=["2025-08", "2025-10"],
        start_month="2025-08",
        end_month="2025-09",
    )
    assert out == ["2025-08"]


def test_model_valid_through_is_end_of_deployment_month() -> None:
    # Models are named by training-data-end month and deployed the following
    # month, so a 2026-04 model's validity runs to the end of May.
    assert _model_valid_through("2026-04") == "2026-05-31"
    assert _model_valid_through("2026-02") == "2026-03-31"
    # Year rollover: a December model deploys in January of the next year.
    assert _model_valid_through("2026-12") == "2027-01-31"
    # Deployment month with 30 / 28 days.
    assert _model_valid_through("2026-03") == "2026-04-30"
    assert _model_valid_through("2026-01") == "2026-02-28"
    # Malformed input degrades to empty string, not a crash.
    assert _model_valid_through("") == ""
    assert _model_valid_through("not-a-month") == ""


def test_run_writes_explicit_non_deployable_lock_for_no_gate_states_month(tmp_path: Path) -> None:
    symbol = "USDCAD"
    sl = symbol.lower()
    config_dir = tmp_path / "configs"
    analysis_dir = tmp_path / "analysis"
    models_dir = tmp_path / "models"
    out_dir = tmp_path / "history"
    config_dir.mkdir(parents=True)

    (config_dir / f"{sl}_tick_opportunity_monthly_wfo_oco_fullcap.yaml").write_text(
        "threshold_mode: rolling_days\nrolling_threshold_days: 20\n"
        "rolling_threshold_min_history: 300\nproduction_cap_pips: 1.2\n"
        "oco_hold_mode: from_touch\noco_include_no_touch: true\nexecution_quantile: 0.9\n",
        encoding="utf-8",
    )
    (config_dir / f"{sl}_oco_reduced_core_rolling.yaml").write_text(
        "locked_quantile: 0.9\nselection_mode: auto\nfamily_keep: oco_first_touch\n",
        encoding="utf-8",
    )

    reduced_core_rolling = analysis_dir / "reduced_core_rolling"
    reduced_core_rolling.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "test_month": "2026-01",
                "symbol": symbol,
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_a",
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "all",
            }
        ]
    ).to_csv(reduced_core_rolling / f"{symbol}_oco_reduced_state_schedule.csv", index=False)
    pd.DataFrame(
        [
            {"symbol": symbol, "test_month": "2026-01", "states_selected": 1, "status": "ok"},
            {
                "symbol": symbol,
                "test_month": "2026-02",
                "states_selected": 0,
                "status": "no_gate_states",
            },
        ]
    ).to_csv(reduced_core_rolling / f"{symbol}_oco_reduced_monthly.csv", index=False)
    pd.DataFrame([{"capacity_pass_monthly_or_annual": True}]).to_csv(
        reduced_core_rolling / f"{symbol}_oco_reduced_summary.csv", index=False
    )

    reduced_core = analysis_dir / "reduced_core"
    reduced_core.mkdir(parents=True)
    pd.DataFrame([{"overall_pass": True}]).to_csv(
        reduced_core / f"{symbol}_oco_tick_exact_summary.csv", index=False
    )

    stop_limit_dir = analysis_dir / "stop_limit_tickfill_fullcap"
    stop_limit_dir.mkdir(parents=True)
    pd.DataFrame([{"cap_pips": 1.2, "mean_per_signal_full_overshoot": 0.5}]).to_csv(
        stop_limit_dir / f"{symbol}_stop_limit_tickfill_caps.csv", index=False
    )

    pred_dir = analysis_dir / "wfo_m3to1_oco_fullcap"
    pred_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "test_month": "2026-01",
                "close_ts": pd.Timestamp("2026-01-07T00:00:00Z"),
                "candidate_uid": "oco|USDCAD|100|h5|state_a",
                "pred_prob": 0.7,
                "target_gross_pips": 1.0,
                "target_gross_pos": 1,
                "selected_exec": 1,
                "event_ordinal": 0,
            }
        ]
    ).to_parquet(pred_dir / f"{symbol}_oco_monthly_predictions.parquet", index=False)

    models_dir.mkdir(parents=True)
    (models_dir / f"{symbol}_model_2026-02.cbm").write_text("dummy model", encoding="utf-8")
    (models_dir / f"{symbol}_model_2026-02.json").write_text(
        '{"model_month":"2026-02","rolling_threshold_min_history":1000}', encoding="utf-8"
    )

    _, index_df = run(
        symbols=[symbol],
        out_dir=out_dir,
        models_dir=models_dir,
        config_dir=config_dir,
        analysis_dir=analysis_dir,
        months=["2026-02"],
        start_month=None,
        end_month=None,
        cadence_days=30,
        anchor_day_utc=1,
        window_days=3,
        allow_dirty=True,
    )

    month_dir = out_dir / "2026-02"
    lock_path = month_dir / f"{sl}_oco_live_lock.json"
    states_path = month_dir / f"{sl}_oco_allowed_states.csv"
    preds_path = month_dir / f"{sl}_oco_locked_predictions.parquet"

    assert lock_path.exists()
    assert states_path.exists()
    assert not preds_path.exists()

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    threshold_json = json.loads(
        (models_dir / f"{symbol}_model_2026-02.json").read_text(encoding="utf-8")
    )
    assert lock["schema_version"] == 2
    assert lock["historical_backtest"]["deployable"] is False
    assert lock["historical_backtest"]["non_deployable_reason"] == "no_gate_states"
    assert lock["state_universe"]["count"] == 0
    assert lock["state_universe"]["rows"] == []
    assert "predictions" not in lock["artifacts"]
    assert threshold_json["rolling_threshold_min_history"] == 300
    assert (
        lock["artifacts"]["model_threshold_json"]["sha256"]
        == hashlib.sha256((models_dir / f"{symbol}_model_2026-02.json").read_bytes()).hexdigest()
    )

    states_df = pd.read_csv(states_path)
    assert states_df.empty

    assert index_df.to_dict(orient="records") == [
        {
            "symbol": symbol,
            "month": "2026-02",
            "lock_path": str(lock_path),
            "allowed_states_path": str(states_path),
            "model_cbm_path": str(models_dir / f"{symbol}_model_2026-02.cbm"),
            "threshold_json_path": str(models_dir / f"{symbol}_model_2026-02.json"),
            "candidates_count": 0,
            "production_cap_pips": 1.2,
            "live_deployable": False,
        }
    ]
