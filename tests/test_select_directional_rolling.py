"""Directional rolling selection contract tests.

A directional state passes gates when: bootstrap lb95 of per-trade gross pips > 0
and average signal rows per training month >= min threshold.
Empty predictions -> NO_TRADE (not crash).

Family names mirror real mined directional candidates (shock_revert,
shock_extreme_revert, path_follow, ...) — not the placeholder
directional_long/short the original plan assumed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.select_directional_rolling import run

PRED_COLS = ["candidate_uid", "pred_prob", "target_gross_pips", "target_gross_pos", "test_month"]
CAND_COLS = ["symbol", "bar_ticks", "horizon", "family", "state_id", "regime_desc"]


def _cfg(tmp_path, candidate_csv, pred_path):
    return {
        "symbol": "EURUSD",
        "candidate_csv": str(candidate_csv),
        "pred_path": str(pred_path),
        "family_keep": "shock_extreme_revert,shock_revert",
        "horizon_keep": "5,6",
        "locked_quantile": 0.9,
        "state_train_months": 2,
        "min_train_months": 1,
        "min_state_avg_rows": 20,
        "min_positive_months_train": 1,
        "require_lb95_trade_gt0": True,
        "bootstrap_paths": 200,
        "seed": 42,
        "capacity_floor_monthly": 200,
        "capacity_floor_annual": 500,
        "out_state_schedule_csv": str(tmp_path / "sched.csv"),
        "out_monthly_csv": str(tmp_path / "monthly.csv"),
        "out_summary_csv": str(tmp_path / "summary.csv"),
        "report_out": str(tmp_path / "report.md"),
    }


def _pred_rows(uid, *, mean, std, n, months, seed):
    rng = np.random.default_rng(seed)
    rows = []
    for month in months:
        probs = rng.uniform(0.3, 0.99, n)
        gross = rng.normal(mean, std, n)
        for prob, g in zip(probs, gross):
            rows.append({
                "candidate_uid": uid,
                "pred_prob": float(prob),
                "target_gross_pips": float(g),
                "target_gross_pos": 1 if g > 0 else 0,
                "test_month": month,
            })
    return rows


def test_empty_predictions_is_no_trade(tmp_path):
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"
    pd.DataFrame(columns=CAND_COLS).to_csv(cand, index=False)
    pd.DataFrame(columns=PRED_COLS).to_parquet(pred, index=False)

    sched, monthly, summary = run(_cfg(tmp_path, cand, pred))

    assert sched.empty
    assert pd.read_csv(tmp_path / "summary.csv").iloc[0]["status"] == "NO_TRADE"


def test_positive_signal_state_is_scheduled(tmp_path):
    """A state with consistently positive gross signal in training gets scheduled."""
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"

    pd.DataFrame([{
        "symbol": "EURUSD", "bar_ticks": 2000, "horizon": 5,
        "family": "shock_revert",
        "state_id": "shock_revert__high_abs_vel_q80",
        "regime_desc": "high_abs_vel_q80",
    }]).to_csv(cand, index=False)

    rows = _pred_rows(
        "directional|EURUSD|2000|h5|shock_revert__high_abs_vel_q80",
        mean=8.0, std=5.0, n=200, months=["2025-01", "2025-03"], seed=42,
    )
    pd.DataFrame(rows).to_parquet(pred, index=False)

    sched, monthly, summary = run(_cfg(tmp_path, cand, pred))

    assert not sched.empty, "expected at least one state scheduled"
    assert sched.iloc[0]["train_lb95_trade_mean_gross_pips"] > 0


def test_negative_signal_state_not_scheduled(tmp_path):
    """A state with negative gross signal in training produces empty schedule."""
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"

    pd.DataFrame([{
        "symbol": "EURUSD", "bar_ticks": 2000, "horizon": 5,
        "family": "shock_revert",
        "state_id": "shock_revert__all",
        "regime_desc": "all",
    }]).to_csv(cand, index=False)

    rows = _pred_rows(
        "directional|EURUSD|2000|h5|shock_revert__all",
        mean=-5.0, std=3.0, n=200, months=["2025-01", "2025-03"], seed=99,
    )
    pd.DataFrame(rows).to_parquet(pred, index=False)

    sched, monthly, summary = run(_cfg(tmp_path, cand, pred))

    assert sched.empty


def test_family_keep_excludes_non_kept_family(tmp_path):
    """A positive state in a family outside family_keep is filtered out before scoring."""
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"

    pd.DataFrame([
        {
            "symbol": "EURUSD", "bar_ticks": 2000, "horizon": 5,
            "family": "path_follow",
            "state_id": "path_follow__high_abs_vel_q80",
            "regime_desc": "high_abs_vel_q80",
        },
        {
            "symbol": "EURUSD", "bar_ticks": 2000, "horizon": 5,
            "family": "shock_revert",
            "state_id": "shock_revert__high_abs_vel_q80",
            "regime_desc": "high_abs_vel_q80",
        },
    ]).to_csv(cand, index=False)

    rows = _pred_rows(
        "directional|EURUSD|2000|h5|path_follow__high_abs_vel_q80",
        mean=8.0, std=5.0, n=200, months=["2025-01", "2025-03"], seed=42,
    )
    rows += _pred_rows(
        "directional|EURUSD|2000|h5|shock_revert__high_abs_vel_q80",
        mean=8.0, std=5.0, n=200, months=["2025-01", "2025-03"], seed=7,
    )
    pd.DataFrame(rows).to_parquet(pred, index=False)

    sched, monthly, summary = run(_cfg(tmp_path, cand, pred))

    assert not sched.empty
    assert set(sched["family"]) == {"shock_revert"}, "path_follow must be filtered out"
