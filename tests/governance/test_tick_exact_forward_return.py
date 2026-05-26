from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from src.behemoth.governance.tick_exact_forward_return import (
    simulate_state_forward_return,
)
from src.behemoth.governance.tick_exact_shared import TickStreamProvider


class _LongOnlyForwardReturnAdapter:
    """Synthetic adapter: buy at entry ask, sell at horizon bid."""

    def simulate_one_entry(self, tick_stream, entry_bar, params):
        if tick_stream.empty:
            return 0.0
        entry_price = float(tick_stream.iloc[0]["ask"])
        exit_price = float(tick_stream.iloc[-1]["bid"])
        return (exit_price - entry_price) / 0.0001


def test_forward_return_simulator_delegates_inclusive_ticks_to_adapter(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
            "bid": [1.1000, 1.1001, 1.1002, 1.1003, 1.1004],
            "ask": [1.1001, 1.1002, 1.1003, 1.1004, 1.1005],
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

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

    fills = simulate_state_forward_return(
        entries=entries,
        adapter=_LongOnlyForwardReturnAdapter(),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
    )

    assert fills.drop(columns=["realized_pips"]).to_dict(orient="records") == [
        {
            "state_id": "s1",
            "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
            "entry_month": "2026-01",
        }
    ]
    assert fills["realized_pips"].iloc[0] == pytest.approx(3.0)


def test_forward_return_simulator_returns_zero_when_no_ticks(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=2, freq="1s", tz="UTC"),
            "bid": [1.1000, 1.1001],
            "ask": [1.1001, 1.1002],
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

    entries = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "entry_ts": pd.Timestamp("2026-01-01T00:01:00", tz="UTC"),
                "horizon_seconds": 4,
                "symbol": "EURUSD",
            }
        ]
    )

    fills = simulate_state_forward_return(
        entries=entries,
        adapter=_LongOnlyForwardReturnAdapter(),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
    )

    assert fills["realized_pips"].tolist() == [0.0]


def test_forward_return_simulator_passes_entry_and_params_to_adapter(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=3, freq="1s", tz="UTC"),
            "bid": [1.1000, 1.1001, 1.1002],
            "ask": [1.1001, 1.1002, 1.1003],
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

    entries = pd.DataFrame(
        [
            {
                "state_id": "s2",
                "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
                "horizon_seconds": 2,
                "symbol": "EURUSD",
            }
        ]
    )

    @dataclass
    class RecordingAdapter:
        calls: int = 0

        def simulate_one_entry(self, tick_stream, entry_bar, params):
            self.calls += 1
            assert len(tick_stream) == 3
            assert entry_bar["state_id"] == "s2"
            assert params["symbol"] == "EURUSD"
            return 1.25

    adapter = RecordingAdapter()

    fills = simulate_state_forward_return(
        entries=entries,
        adapter=adapter,
        tick_provider=TickStreamProvider(tick_root=tmp_path),
    )

    assert adapter.calls == 1
    assert fills["realized_pips"].tolist() == [1.25]
