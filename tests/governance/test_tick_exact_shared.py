from __future__ import annotations

import pandas as pd
import pytest

from src.behemoth.governance.errors import TickStreamGapError
from src.behemoth.governance.tick_exact_shared import (
    TickStreamProvider,
    aggregate_monthly_summary,
    aggregate_state_summary,
)


def test_tick_stream_provider_returns_ticks_for_inclusive_range(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=10, freq="1s", tz="UTC"),
            "bid": [1.1000] * 10,
            "ask": [1.1001] * 10,
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

    provider = TickStreamProvider(tick_root=tmp_path)
    out = provider.get(
        symbol="EURUSD",
        start_ts=pd.Timestamp("2026-01-01T00:00:02", tz="UTC"),
        end_ts=pd.Timestamp("2026-01-01T00:00:05", tz="UTC"),
    )

    assert len(out) == 4
    assert out["ts"].iloc[0] == pd.Timestamp("2026-01-01T00:00:02", tz="UTC")
    assert out["ts"].iloc[-1] == pd.Timestamp("2026-01-01T00:00:05", tz="UTC")


def test_tick_stream_provider_accepts_naive_range_as_utc(tmp_path):
    ticks = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
            "bid": [1.1000] * 5,
            "ask": [1.1001] * 5,
        }
    )
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

    provider = TickStreamProvider(tick_root=tmp_path)
    out = provider.get(
        symbol="EURUSD",
        start_ts=pd.Timestamp("2026-01-01T00:00:01"),
        end_ts=pd.Timestamp("2026-01-01T00:00:03"),
    )

    assert len(out) == 3


def test_tick_stream_provider_raises_when_symbol_file_is_missing(tmp_path):
    provider = TickStreamProvider(tick_root=tmp_path)

    with pytest.raises(TickStreamGapError, match="EURUSD"):
        provider.get(
            symbol="EURUSD",
            start_ts=pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
            end_ts=pd.Timestamp("2026-01-01T00:00:01", tz="UTC"),
        )


def test_aggregate_state_summary_computes_state_metrics():
    fills = pd.DataFrame(
        [
            {"state_id": "s1", "realized_pips": 0.5},
            {"state_id": "s1", "realized_pips": -0.2},
            {"state_id": "s2", "realized_pips": 1.0},
        ]
    )

    summary = aggregate_state_summary(fills=fills)

    s1 = summary[summary["state_id"] == "s1"].iloc[0]
    assert s1["n_fills"] == 2
    assert abs(s1["mean_realized_pips"] - 0.15) < 1e-9
    assert abs(s1["std_realized_pips"] - fills.iloc[:2]["realized_pips"].std()) < 1e-9
    assert s1["hit_rate"] == 0.5


def test_aggregate_monthly_summary_computes_state_month_metrics():
    fills = pd.DataFrame(
        [
            {"state_id": "s1", "entry_month": "2026-01", "realized_pips": 0.5},
            {"state_id": "s1", "entry_month": "2026-01", "realized_pips": -0.2},
            {"state_id": "s1", "entry_month": "2026-02", "realized_pips": 1.0},
        ]
    )

    summary = aggregate_monthly_summary(fills=fills)

    jan = summary[
        (summary["state_id"] == "s1") & (summary["entry_month"] == "2026-01")
    ].iloc[0]
    assert jan["n_fills"] == 2
    assert abs(jan["mean_realized_pips"] - 0.15) < 1e-9
