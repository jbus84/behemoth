"""Stage 2f input-classification contract.

A genuinely empty input artifact (candidate CSV or predictions parquet with
0 rows) is a legitimate no-trade outcome: Stage 2f writes empty outputs and
exits 0. Non-empty inputs that fail to join are a bug and still raise.
See docs/superpowers/specs/2026-05-16-graceful-no-trade-pipeline-design.md.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.select_oco_reduced_core_rolling import run

CANDIDATE_COLS = [
    "symbol", "bar_ticks", "horizon", "family", "state_id",
    "regime_desc", "barrier_pips",
]
PRED_COLS = ["candidate_uid", "pred_prob", "target_gross_pips", "test_month"]


def _cfg(tmp_path, candidate_csv, pred_path):
    return {
        "symbol": "EURUSD",
        "candidate_csv": str(candidate_csv),
        "pred_path": str(pred_path),
        "family_keep": "oco_first_touch",
        "barrier_keep": "2,3",
        "horizon_keep": "5,6",
        "locked_quantile": 0.9,
        "selection_mode": "auto",
        "execution_mode": "gross",
        "state_train_months": 3,
        "min_train_months": 3,
        "overlap_corr_max": 0.85,
        "max_states": 12,
        "min_states": 4,
        "min_state_avg_rows": 200,
        "min_positive_months_train": 2,
        "require_lb95_trade_gt0": True,
        "require_lb95_month_gt0": True,
        "bootstrap_paths": 10,
        "seed": 42,
        "capacity_floor_monthly": 3000,
        "capacity_floor_annual": 3000,
        "out_state_schedule_csv": str(tmp_path / "sched.csv"),
        "out_state_csv": str(tmp_path / "states.csv"),
        "out_monthly_csv": str(tmp_path / "reduced_monthly.csv"),
        "out_summary_csv": str(tmp_path / "summary.csv"),
        "report_out": str(tmp_path / "report.md"),
    }


def test_empty_candidate_csv_is_no_trade(tmp_path):
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"
    pd.DataFrame(columns=CANDIDATE_COLS).to_csv(cand, index=False)
    pd.DataFrame(columns=PRED_COLS).to_parquet(pred, index=False)

    schedule, monthly, summary = run(_cfg(tmp_path, cand, pred))

    assert schedule.empty
    sched_csv = pd.read_csv(tmp_path / "sched.csv")
    assert sched_csv.empty
    summ_csv = pd.read_csv(tmp_path / "summary.csv")
    assert summ_csv.iloc[0]["status"] == "NO_TRADE"


def test_empty_predictions_parquet_is_no_trade(tmp_path):
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"
    pd.DataFrame(
        [{
            "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 5,
            "family": "oco_first_touch", "state_id": "oco_first_touch__all__k2",
            "regime_desc": "all;barrier=2.0", "barrier_pips": 2.0,
        }]
    ).to_csv(cand, index=False)
    pd.DataFrame(columns=PRED_COLS).to_parquet(pred, index=False)

    schedule, monthly, summary = run(_cfg(tmp_path, cand, pred))
    assert schedule.empty
    assert pd.read_csv(tmp_path / "summary.csv").iloc[0]["status"] == "NO_TRADE"


def test_nonempty_predictions_that_do_not_join_still_raise(tmp_path):
    """Candidates and predictions both have rows but the candidate_uid state
    ids do not match — a mismatch bug, must stay a hard error."""
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"
    pd.DataFrame(
        [{
            "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 5,
            "family": "oco_first_touch", "state_id": "oco_first_touch__all__k2",
            "regime_desc": "all;barrier=2.0", "barrier_pips": 2.0,
        }]
    ).to_csv(cand, index=False)
    pd.DataFrame(
        [{
            "candidate_uid": "oco|EURUSD|1000|h5|oco_first_touch_clean__all__k2",
            "pred_prob": 0.6, "target_gross_pips": 1.0, "test_month": "2025-01",
        }]
    ).to_parquet(pred, index=False)

    with pytest.raises(RuntimeError, match="no predictions left"):
        run(_cfg(tmp_path, cand, pred))
