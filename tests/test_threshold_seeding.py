from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.behemoth.runtime.state import StateManager
from scripts.seed_rolling_threshold import _is_fresh


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


def _write_seed_with_meta(path, candidates: list[str]) -> None:
    """Helper: write a minimal parquet with a recent close_ts and given governance metadata."""
    df = pd.DataFrame(
        {"close_ts": [pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)]}
    )
    table = pa.Table.from_pandas(df, preserve_index=False)
    meta = {b"governance_candidates": json.dumps(candidates).encode()}
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **meta})
    pq.write_table(table, path)


def test_is_fresh_returns_false_on_governance_mismatch(tmp_path) -> None:
    """A fresh-by-recency seed with old governance candidates is not fresh."""
    path = tmp_path / "GBPUSD_threshold_seed.parquet"
    _write_seed_with_meta(path, ["oco|GBPUSD|100|h6|old__k2"])
    assert _is_fresh(path, expected_candidates=["oco|GBPUSD|100|h6|new__k2"]) is False


def test_is_fresh_returns_true_on_governance_match(tmp_path) -> None:
    """A fresh-by-recency seed whose governance fingerprint matches is fresh."""
    path = tmp_path / "GBPUSD_threshold_seed.parquet"
    _write_seed_with_meta(path, ["oco|GBPUSD|100|h6|match__k2"])
    assert _is_fresh(path, expected_candidates=["oco|GBPUSD|100|h6|match__k2"]) is True
