from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.select_oco_reduced_core_rolling import run


def _uid(state: str) -> str:
    return f"oco|EURUSD|100|h5|{state}"


def test_rolling_core_uses_train_months_only(tmp_path: Path):
    cand = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_a",
                "family": "oco_first_touch_clean",
                "regime_desc": "a;barrier=2.0",
                "barrier_pips": 2.0,
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_b",
                "family": "oco_first_touch_clean",
                "regime_desc": "b;barrier=2.0",
                "barrier_pips": 2.0,
            },
        ]
    )
    cpath = tmp_path / "candidates.csv"
    cand.to_csv(cpath, index=False)

    months = ["2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09"]
    rows: list[dict] = []
    for m in months:
        # State A: stable positive.
        rows.append(
            {
                "candidate_uid": _uid("state_a"),
                "pred_prob": 0.95,
                "target_gross_pips": 1.0,
                "test_month": m,
                "selected_exec": 1,
                "threshold_exec": 0.9,
            }
        )
        # State B: negative in first 3 months, then very positive (future-only lift).
        rows.append(
            {
                "candidate_uid": _uid("state_b"),
                "pred_prob": 0.95,
                "target_gross_pips": -1.0 if m in {"2025-04", "2025-05", "2025-06"} else 5.0,
                "test_month": m,
                "selected_exec": 1,
                "threshold_exec": 0.9,
            }
        )
    p = pd.DataFrame(rows)
    ppath = tmp_path / "pred.parquet"
    p.to_parquet(ppath, index=False)

    cfg = {
        "symbol": "EURUSD",
        "candidate_csv": str(cpath),
        "pred_path": str(ppath),
        "family_keep": "oco_first_touch_clean",
        "barrier_keep": "2",
        "horizon_keep": "5",
        "locked_quantile": 0.9,
        "selection_mode": "exec_flag",
        "state_train_months": 3,
        "min_train_months": 3,
        "overlap_corr_max": 0.85,
        "max_states": 2,
        "min_states": 1,
        "min_state_avg_rows": 1.0,
        "min_positive_months_train": 2,
        "require_lb95_trade_gt0": True,
        "require_lb95_month_gt0": True,
        "bootstrap_paths": 200,
        "seed": 42,
        "capacity_floor_monthly": 1.0,
        "capacity_floor_annual": 1.0,
        "out_state_schedule_csv": str(tmp_path / "schedule.csv"),
        "out_monthly_csv": str(tmp_path / "monthly.csv"),
        "out_summary_csv": str(tmp_path / "summary.csv"),
        "report_out": str(tmp_path / "report.md"),
    }
    schedule, monthly, _ = run(cfg)

    # Jul train window is Apr-May-Jun, where state_b is negative.
    jul = schedule[schedule["test_month"] == "2025-07"]["state_id"].astype(str).tolist()
    assert "state_a" in jul
    assert "state_b" not in jul

    jul_month = monthly[monthly["test_month"] == "2025-07"].iloc[0]
    assert jul_month["status"] == "ok"
    assert float(jul_month["mean_gross_pips"]) > 0.0
    states_path = tmp_path / "EURUSD_oco_reduced_states.csv"
    assert states_path.exists()
    states = pd.read_csv(states_path)
    assert {
        "symbol",
        "bar_ticks",
        "horizon",
        "state_id",
        "family",
        "barrier_pips",
        "regime_desc",
    }.issubset(set(states.columns))


def test_rolling_core_stop_limit_filters_unfilled_state(tmp_path: Path):
    cand = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_fill",
                "family": "oco_first_touch_clean",
                "regime_desc": "f;barrier=2.0",
                "barrier_pips": 2.0,
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_nofill",
                "family": "oco_first_touch_clean",
                "regime_desc": "n;barrier=2.0",
                "barrier_pips": 2.0,
            },
        ]
    )
    cpath = tmp_path / "candidates.csv"
    cand.to_csv(cpath, index=False)

    months = ["2025-04", "2025-05", "2025-06", "2025-07"]
    pred_rows: list[dict] = []
    detail_rows: list[dict] = []
    for _i, m in enumerate(months):
        ts = pd.Timestamp(f"{m}-01 00:00:00+00:00")
        for state in ["state_fill", "state_nofill"]:
            pred_rows.append(
                {
                    "candidate_uid": _uid(state),
                    "close_ts": ts,
                    "pred_prob": 0.95,
                    "target_gross_pips": 2.0,
                    "test_month": m,
                    "selected_exec": 1,
                    "threshold_exec": 0.9,
                }
            )
            if state == "state_fill":
                detail_rows.append(
                    {
                        "candidate_uid": _uid(state),
                        "close_ts": ts,
                        "touch_found_tick": 1,
                        "overshoot_tick_pips": 0.2,
                    }
                )
            else:
                detail_rows.append(
                    {
                        "candidate_uid": _uid(state),
                        "close_ts": ts,
                        "touch_found_tick": 1,
                        "overshoot_tick_pips": 5.0,
                    }
                )

    p = pd.DataFrame(pred_rows)
    ppath = tmp_path / "pred.parquet"
    p.to_parquet(ppath, index=False)

    d = pd.DataFrame(detail_rows)
    dpath = tmp_path / "detail.csv"
    d.to_csv(dpath, index=False)

    cfg = {
        "symbol": "EURUSD",
        "candidate_csv": str(cpath),
        "pred_path": str(ppath),
        "family_keep": "oco_first_touch_clean",
        "barrier_keep": "2",
        "horizon_keep": "5",
        "locked_quantile": 0.9,
        "selection_mode": "exec_flag",
        "execution_mode": "stop_limit",
        "stop_limit_detail_csv": str(dpath),
        "stop_limit_cap_pips": 1.0,
        "stop_limit_slippage_mode": "full_overshoot",
        "stop_limit_min_fill_rate": 0.5,
        "stop_limit_require_match_rate": 1.0,
        "state_train_months": 3,
        "min_train_months": 3,
        "overlap_corr_max": 0.85,
        "max_states": 2,
        "min_states": 1,
        "min_state_avg_rows": 1.0,
        "min_positive_months_train": 1,
        "require_lb95_trade_gt0": True,
        "require_lb95_month_gt0": True,
        "bootstrap_paths": 120,
        "seed": 42,
        "capacity_floor_monthly": 1.0,
        "capacity_floor_annual": 1.0,
        "out_state_schedule_csv": str(tmp_path / "schedule2.csv"),
        "out_monthly_csv": str(tmp_path / "monthly2.csv"),
        "out_summary_csv": str(tmp_path / "summary2.csv"),
        "report_out": str(tmp_path / "report2.md"),
    }
    schedule, monthly, summary = run(cfg)
    jul = schedule[schedule["test_month"] == "2025-07"]["state_id"].astype(str).tolist()
    assert "state_fill" in jul
    assert "state_nofill" not in jul
    jul_month = monthly[monthly["test_month"] == "2025-07"].iloc[0]
    assert float(jul_month["rows"]) >= 1
    assert float(summary.iloc[0]["fill_rate_overall"]) > 0.0


def test_rolling_core_strict_gate_only_blocks_gate_fail_backfill(tmp_path: Path):
    cand = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_a",
                "family": "oco_first_touch_clean",
                "regime_desc": "a;barrier=2.0",
                "barrier_pips": 2.0,
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_b",
                "family": "oco_first_touch_clean",
                "regime_desc": "b;barrier=2.0",
                "barrier_pips": 2.0,
            },
        ]
    )
    cpath = tmp_path / "candidates3.csv"
    cand.to_csv(cpath, index=False)

    months = ["2025-04", "2025-05", "2025-06", "2025-07"]
    rows: list[dict] = []
    for m in months:
        rows.append(
            {
                "candidate_uid": _uid("state_a"),
                "pred_prob": 0.95,
                "target_gross_pips": -0.5 if m != "2025-07" else 1.0,
                "test_month": m,
                "selected_exec": 1,
                "threshold_exec": 0.9,
            }
        )
        rows.append(
            {
                "candidate_uid": _uid("state_b"),
                "pred_prob": 0.95,
                "target_gross_pips": -0.8 if m != "2025-07" else 1.0,
                "test_month": m,
                "selected_exec": 1,
                "threshold_exec": 0.9,
            }
        )
    p = pd.DataFrame(rows)
    ppath = tmp_path / "pred3.parquet"
    p.to_parquet(ppath, index=False)

    cfg = {
        "symbol": "EURUSD",
        "candidate_csv": str(cpath),
        "pred_path": str(ppath),
        "family_keep": "oco_first_touch_clean",
        "barrier_keep": "2",
        "horizon_keep": "5",
        "locked_quantile": 0.9,
        "selection_mode": "exec_flag",
        "state_train_months": 3,
        "min_train_months": 3,
        "overlap_corr_max": 0.85,
        "max_states": 2,
        "min_states": 2,
        "min_state_avg_rows": 1.0,
        "min_positive_months_train": 2,
        "strict_gate_only": True,
        "require_lb95_trade_gt0": True,
        "require_lb95_month_gt0": True,
        "bootstrap_paths": 120,
        "seed": 42,
        "capacity_floor_monthly": 1.0,
        "capacity_floor_annual": 1.0,
        "out_state_schedule_csv": str(tmp_path / "schedule3.csv"),
        "out_monthly_csv": str(tmp_path / "monthly3.csv"),
        "out_summary_csv": str(tmp_path / "summary3.csv"),
        "report_out": str(tmp_path / "report3.md"),
    }
    schedule, monthly, _ = run(cfg)
    jul_month = monthly[monthly["test_month"] == "2025-07"].iloc[0]
    assert jul_month["status"] == "no_gate_states"
    assert float(jul_month["rows"]) == 0.0
    assert schedule.empty
