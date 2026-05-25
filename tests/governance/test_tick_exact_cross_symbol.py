from __future__ import annotations

import pandas as pd
import pytest

from src.behemoth.governance.tick_exact_cross_symbol import (
    simulate_state_cross_symbol,
)
from src.behemoth.governance.tick_exact_shared import TickStreamProvider


class _FreshnessCheckingCrossSymbolAdapter:
    """Synthetic adapter: long-only payoff with a cross-symbol freshness gate."""

    def simulate_one_entry(self, tick_stream, entry_bar, params, cs_frame=None):
        if tick_stream.empty or cs_frame is None or cs_frame.empty:
            return 0.0

        last_cs = pd.Timestamp(cs_frame["close_ts"].iloc[-1])
        entry_ts = pd.Timestamp(entry_bar["entry_ts"])
        if (entry_ts - last_cs).total_seconds() > 60:
            return 0.0

        entry_price = float(tick_stream.iloc[0]["ask"])
        exit_price = float(tick_stream.iloc[-1]["bid"])
        return (exit_price - entry_price) / 0.0001


def test_cross_symbol_simulator_drops_stale_cs_frame(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
            "bid": [1.1000] * 5,
            "ask": [1.1001] * 5,
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")
    cs_frame = pd.DataFrame(
        {
            "close_ts": [pd.Timestamp("2025-12-31T22:00:00", tz="UTC")],
        }
    )
    entries = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
                "horizon_seconds": 4,
                "symbol": "EURUSD",
            }
        ]
    )

    fills = simulate_state_cross_symbol(
        entries=entries,
        adapter=_FreshnessCheckingCrossSymbolAdapter(),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
        cs_frame=cs_frame,
    )

    assert fills["realized_pips"].iloc[0] == 0.0


def test_cross_symbol_simulator_delegates_fresh_cs_frame_to_adapter(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
            "bid": [1.1000, 1.1001, 1.1002, 1.1003, 1.1004],
            "ask": [1.1001, 1.1002, 1.1003, 1.1004, 1.1005],
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")
    cs_frame = pd.DataFrame(
        {
            "close_ts": [pd.Timestamp("2025-12-31T23:59:30", tz="UTC")],
        }
    )
    entries = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
                "horizon_seconds": 4,
                "symbol": "EURUSD",
            }
        ]
    )

    fills = simulate_state_cross_symbol(
        entries=entries,
        adapter=_FreshnessCheckingCrossSymbolAdapter(),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
        cs_frame=cs_frame,
    )

    assert fills.to_dict(orient="records") == [
        {
            "state_id": "s1",
            "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
            "entry_month": "2026-01",
            "realized_pips": pytest.approx(3.0),
        }
    ]
