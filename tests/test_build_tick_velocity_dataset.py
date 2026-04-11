from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from scripts.build_tick_velocity_dataset import _build_symbol_dataset


def test_build_symbol_dataset_accepts_explicit_bid_bar_schema(tmp_path):
    bar_path = tmp_path / "EURUSD_100tick.parquet"
    pd.DataFrame(
        [
            {
                "timestamp": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
                "close_ts": datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
                "open_bid": 1.1000,
                "high_bid": 1.1010,
                "low_bid": 1.0990,
                "close_bid": 1.1005,
                "spread": 0.0002,
                "tick_volume": 100.0,
            },
            {
                "timestamp": datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
                "close_ts": datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc),
                "open_bid": 1.1005,
                "high_bid": 1.1015,
                "low_bid": 1.1000,
                "close_bid": 1.1010,
                "spread": 0.0002,
                "tick_volume": 100.0,
                "hl_first": 1.0,
                "hl_pos_frac": 0.6,
            },
        ]
    ).to_parquet(bar_path, index=False)

    dataset = _build_symbol_dataset(
        symbol="EURUSD",
        bar_path=bar_path,
        bar_ticks=100,
        vel_horizons=[1],
        target_horizons=[1],
        vol_window=8,
        cost_window=8,
    )

    assert list(dataset[["open", "high", "low", "close"]].iloc[-1]) == [1.1005, 1.1015, 1.1, 1.101]
    assert dataset["symbol"].tolist() == ["EURUSD", "EURUSD"]
