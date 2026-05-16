"""Tests for build_tick_velocity_dataset.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.build_tick_velocity_dataset import _build_symbol_dataset


def test_velocity_dataset_includes_microstructure_signals(tmp_path):
    """Velocity dataset must include lagged microstructure signals."""

    # Minimal bar frame with required columns
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=30, freq="1min", tz="UTC"),
        "close_ts": pd.date_range("2026-01-01", periods=30, freq="1min", tz="UTC"),
        "open_bid": np.linspace(1.1000, 1.1050, 30),
        "close_bid": np.linspace(1.1000, 1.1050, 30),
        "high_bid": np.linspace(1.1005, 1.1055, 30),
        "low_bid": np.linspace(1.0995, 1.1045, 30),
        "high_ask": np.linspace(1.1007, 1.1057, 30),
        "close_ask": np.linspace(1.1002, 1.1052, 30),
        "spread": [0.0002] * 30,
        "tick_volume": [100] * 30,
        "bar_return_sign": [1, -1, 1, 1, -1, 1, 1, 1, -1, -1] * 3,
        "tick_burst": [100] * 30,
        "quote_revisions": [5] * 30,
        "intra_bar_momentum": [0.5] * 30,
        "range_pips": [5.0] * 30,
        "ret1_pips": [0.5] * 30,
    })
    bar_path = tmp_path / "EURUSD_100tick.parquet"
    bars.to_parquet(bar_path, index=False)

    out = _build_symbol_dataset(
        symbol="EURUSD",
        bar_path=bar_path,
        bar_ticks=100,
        vel_horizons=[1, 2],
        target_horizons=[1, 2],
        vol_window=24,
        cost_window=24,
    )
    assert "tick_burst_score" in out.columns
    assert "quote_revision_rate_z" in out.columns
    assert "directional_persistence_8" in out.columns
    assert "signed_flow_24" in out.columns
    assert "vol_cluster_score" in out.columns
    assert "session_marker" in out.columns

    # Lagged signals: first row must be NaN / 0 because of .shift(1)
    assert out["tick_burst_score"].iloc[0] == 0.0
    assert out["quote_revision_rate_z"].iloc[0] == 0.0
    assert out["directional_persistence_8"].iloc[0] == 0
    assert out["signed_flow_24"].iloc[0] == 0
    assert out["vol_cluster_score"].iloc[0] == 1.0

    # session_marker maps to correct label for the fixture's hour (00:00 UTC → asia)
    assert out["session_marker"].iloc[0] == "asia"

    # directional_persistence_8 equals rolling sum of signs shifted by 1
    signs = out["bar_return_sign"].to_numpy()
    for i in range(1, len(out)):
        window_start = max(0, i - 8)
        expected = int(signs[window_start:i].sum())
        assert out["directional_persistence_8"].iloc[i] == expected
