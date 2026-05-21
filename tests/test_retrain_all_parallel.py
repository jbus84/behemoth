"""Tests for the parallel retrain orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.retrain_all_parallel import (
    WorkerResult,
    collect_outcomes,
    run_orchestrator,
)


def _stub_schedule(path: Path, n_rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if n_rows == 0:
        path.write_text("")
    else:
        pd.DataFrame({"state_id": [f"s{i}" for i in range(n_rows)]}).to_csv(path, index=False)


def test_collect_outcomes_orders_results_and_summarises(tmp_path):
    """Worker results may arrive in any order; the summary must be in
    REBUILD_SYMBOLS order with the right outcome per symbol."""
    ad = tmp_path / "analysis"
    (ad / "reduced_core_rolling").mkdir(parents=True)
    _stub_schedule(ad / "reduced_core_rolling" / "EURUSD_oco_reduced_state_schedule.csv", 3)
    _stub_schedule(ad / "reduced_core_rolling" / "GBPUSD_oco_reduced_state_schedule.csv", 0)
    # USDJPY: no schedule file at all

    results = [
        WorkerResult(symbol="GBPUSD", exit_code=0, log_path=tmp_path / "g.log", elapsed_s=10.0),
        WorkerResult(symbol="EURUSD", exit_code=0, log_path=tmp_path / "e.log", elapsed_s=20.0),
        WorkerResult(symbol="USDJPY", exit_code=1, log_path=tmp_path / "u.log", elapsed_s=5.0),
    ]
    summary = collect_outcomes(
        results,
        symbols_order=["EURUSD", "GBPUSD", "USDJPY"],
        analysis_dir=ad,
    )
    assert [s.symbol for s in summary] == ["EURUSD", "GBPUSD", "USDJPY"]
    assert [s.outcome for s in summary] == ["DEPLOY", "NO_TRADE", "FAILED"]


def test_orchestrator_isolates_worker_failure(tmp_path):
    """One worker failing must not cancel siblings; final exit is 1."""
    ad = tmp_path / "analysis"
    (ad / "reduced_core_rolling").mkdir(parents=True)
    _stub_schedule(ad / "reduced_core_rolling" / "EURUSD_oco_reduced_state_schedule.csv", 1)
    _stub_schedule(ad / "reduced_core_rolling" / "GBPUSD_oco_reduced_state_schedule.csv", 1)

    def fake_run_worker(symbol: str, *, eval_end_month, log_dir):
        if symbol == "GBPUSD":
            return WorkerResult(symbol=symbol, exit_code=1, log_path=log_dir / f"{symbol}.log", elapsed_s=1.0)
        return WorkerResult(symbol=symbol, exit_code=0, log_path=log_dir / f"{symbol}.log", elapsed_s=1.0)

    with patch("scripts.retrain_all_parallel.run_worker", side_effect=fake_run_worker):
        exit_code, summary = run_orchestrator(
            symbols=["EURUSD", "GBPUSD"],
            max_workers=2,
            eval_end_month=None,
            log_dir=tmp_path,
            analysis_dir=ad,
        )
    assert exit_code == 1
    by_sym = {s.symbol: s.outcome for s in summary}
    assert by_sym["EURUSD"] == "DEPLOY"
    assert by_sym["GBPUSD"] == "FAILED"
