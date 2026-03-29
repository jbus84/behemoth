from __future__ import annotations

import numpy as np
import pandas as pd

from src.behemoth.runtime.state import StateManager


def test_seed_training_predictions_populates_audit_logs(tmp_path) -> None:
    """Phase 1 seeding loads training predictions parquet into audit_logs."""
    sm = StateManager(vol_window=20, cost_window=20)
    try:
        # Create a training predictions parquet
        train_df = pd.DataFrame(
            {
                "day": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-02"], utc=True).date,
                "pred_prob": [0.3, 0.4, 0.7],
            }
        )
        pq_path = tmp_path / "EURUSD_train_predictions_2025-02.parquet"
        train_df.to_parquet(pq_path, index=False)

        sm.seed_training_predictions(
            parquet_path=pq_path,
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|200|h6|test",
            model_month="2025-02",
            run_id="seed_test",
        )

        # Verify audit_logs was populated
        row = sm._con.execute(
            "SELECT COUNT(*), quantile_cont(pred_prob, 0.9) FROM audit_logs WHERE symbol = 'EURUSD'"
        ).fetchone()
        assert row[0] == 3
        assert np.isclose(row[1], float(np.quantile([0.3, 0.4, 0.7], 0.9)))
    finally:
        sm.close()


def test_seed_training_predictions_sets_close_ts_from_day(tmp_path) -> None:
    """Each row's close_ts should be derived from the day column so
    the rolling window lookback works correctly."""
    sm = StateManager(vol_window=20, cost_window=20)
    try:
        train_df = pd.DataFrame(
            {
                "day": pd.to_datetime(["2025-01-15", "2025-01-16"], utc=True).date,
                "pred_prob": [0.5, 0.6],
            }
        )
        pq_path = tmp_path / "train.parquet"
        train_df.to_parquet(pq_path, index=False)

        sm.seed_training_predictions(
            parquet_path=pq_path,
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|200|h6|test",
            model_month="2025-02",
            run_id="seed_test",
        )

        rows = sm._con.execute("SELECT close_ts FROM audit_logs ORDER BY close_ts").fetchall()
        assert len(rows) == 2
        # close_ts should be midnight UTC of the day
        assert rows[0][0].date().isoformat() == "2025-01-15"
        assert rows[1][0].date().isoformat() == "2025-01-16"
    finally:
        sm.close()
