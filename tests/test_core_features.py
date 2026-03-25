from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from src.behemoth.core.features import FeatureConfig, compute_feature_matrix_from_bars


def _make_bars(n_rows: int) -> pd.DataFrame:
    base_ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
    close = 1.1000 + np.cumsum(np.full(n_rows, 0.0001))
    high = close + 0.0002
    low = close - 0.0002
    open_ = close - 0.00005
    return pd.DataFrame(
        {
            "timestamp": [base_ts + timedelta(minutes=i) for i in range(n_rows)],
            "close_ts": [base_ts + timedelta(minutes=i, seconds=59) for i in range(n_rows)],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "spread": np.full(n_rows, 0.0002),
            "tick_volume": np.full(n_rows, 100.0),
            "hl_first": np.ones(n_rows),
            "hl_pos_frac": np.zeros(n_rows),
        }
    )


def test_compute_feature_matrix_keeps_prewarmup_rows_invalid() -> None:
    cfg = FeatureConfig()
    bars = _make_bars(cfg.full_warmup_bars + 11)

    matrix = compute_feature_matrix_from_bars(
        bars,
        symbol="EURUSD",
        bar_ticks=100,
        horizon=6,
        barrier_pips=2.0,
        cfg=cfg,
    )

    assert matrix is not None
    valid_mask = matrix.notna().all(axis=1)
    assert valid_mask.sum() == len(bars) - cfg.full_warmup_bars + 1
    assert valid_mask.idxmax() == cfg.full_warmup_bars - 1
    assert not valid_mask.iloc[cfg.full_warmup_bars - 2]
