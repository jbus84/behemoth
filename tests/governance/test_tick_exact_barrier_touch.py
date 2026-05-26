from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.behemoth.governance.families import get_family_adapter
from src.behemoth.governance.tick_exact_barrier_touch import (
    simulate_state_barrier_touch,
)
from src.behemoth.governance.tick_exact_shared import TickStreamProvider


def test_simulate_state_barrier_touch_delegates_each_entry_to_adapter(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
            "bid": [1.1000] * 5,
            "ask": [1.1001] * 5,
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

    entries = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "entry_ts": pd.Timestamp("2026-01-01T00:00:01", tz="UTC"),
                "entry_price": 1.1000,
                "barrier_pips": 2.0,
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
            assert entry_bar["state_id"] == "s1"
            assert params["symbol"] == "EURUSD"
            return 1.25

    adapter = RecordingAdapter()

    fills = simulate_state_barrier_touch(
        entries=entries,
        adapter=adapter,
        tick_provider=TickStreamProvider(tick_root=tmp_path),
    )

    assert adapter.calls == 1
    assert fills.to_dict(orient="records") == [
        {
            "state_id": "s1",
            "entry_ts": pd.Timestamp("2026-01-01T00:00:01", tz="UTC"),
            "entry_month": "2026-01",
            "realized_pips": 1.25,
        }
    ]


def test_oco_simulate_one_entry_returns_positive_for_first_upper_touch(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
            "bid": [1.1000, 1.1001, 1.1003, 1.1003, 1.1003],
            "ask": [1.1001, 1.1002, 1.1004, 1.1004, 1.1004],
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")
    entries = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
                "entry_price": 1.1000,
                "barrier_pips": 2.0,
                "horizon_seconds": 10,
                "symbol": "EURUSD",
            }
        ]
    )

    fills = simulate_state_barrier_touch(
        entries=entries,
        adapter=get_family_adapter("oco_first_touch"),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
    )

    assert fills["realized_pips"].iloc[0] == 2.0


def test_oco_simulate_one_entry_returns_negative_for_first_lower_touch():
    tick_stream = pd.DataFrame(
        {
            "bid": [1.1000, 1.0999, 1.0998],
            "ask": [1.1001, 1.1000, 1.0997],
        }
    )
    entry = pd.Series({"entry_price": 1.1000, "barrier_pips": 2.0})

    realized = get_family_adapter("oco_first_touch").simulate_one_entry(
        tick_stream=tick_stream,
        entry_bar=entry,
        params=entry.to_dict(),
    )

    assert realized == -2.0


def test_oco_simulate_one_entry_returns_zero_for_no_touch_or_no_ticks():
    adapter = get_family_adapter("oco_first_touch")
    entry = pd.Series({"entry_price": 1.1000, "barrier_pips": 2.0})
    tick_stream = pd.DataFrame({"bid": [1.1001], "ask": [1.0999]})

    assert adapter.simulate_one_entry(tick_stream, entry, entry.to_dict()) == 0.0
    assert (
        adapter.simulate_one_entry(pd.DataFrame(), entry, entry.to_dict())
        == 0.0
    )
