"""retrain-all per-symbol outcome classification.

DEPLOY  — symbol exited 0 and its reduced state schedule has >=1 row.
NO_TRADE — symbol exited 0 and its reduced state schedule has 0 rows.
FAILED  — symbol exited non-zero.
"""
from __future__ import annotations

import pandas as pd

from scripts.classify_retrain_outcome import classify_outcome


def test_failed_when_exit_nonzero(tmp_path):
    assert classify_outcome(exit_code=1, schedule_csv=tmp_path / "missing.csv") == "FAILED"


def test_no_trade_when_schedule_empty(tmp_path):
    sched = tmp_path / "sched.csv"
    pd.DataFrame(columns=["symbol", "state_id"]).to_csv(sched, index=False)
    assert classify_outcome(exit_code=0, schedule_csv=sched) == "NO_TRADE"


def test_deploy_when_schedule_has_rows(tmp_path):
    sched = tmp_path / "sched.csv"
    pd.DataFrame([{"symbol": "EURUSD", "state_id": "oco_first_touch__all__k2"}]).to_csv(
        sched, index=False
    )
    assert classify_outcome(exit_code=0, schedule_csv=sched) == "DEPLOY"


def test_failed_when_exit_zero_but_schedule_missing(tmp_path):
    """Exit 0 but no schedule artifact at all means the stage did not run —
    a bug, not a no-trade."""
    assert classify_outcome(exit_code=0, schedule_csv=tmp_path / "missing.csv") == "FAILED"
