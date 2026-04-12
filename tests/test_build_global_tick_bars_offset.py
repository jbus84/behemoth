from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from scripts.build_global_tick_bars_offset import _build_offset_bars


def _write_ticks(path: Path, prices: list[float]) -> None:
    ts = pd.date_range("2025-01-01T00:00:00Z", periods=len(prices), freq="1s", tz="UTC")
    pl.DataFrame(
        {
            "timestamp": ts.to_pydatetime().tolist(),
            "bid": prices,
            "ask": [p + 0.0002 for p in prices],
            "spread": [0.0002 for _ in prices],
        },
        schema_overrides={"timestamp": pl.Datetime("ns", "UTC")},
    ).write_parquet(path)


def test_build_offset_bars_shifts_first_completed_bar(tmp_path: Path) -> None:
    tick_root = tmp_path / "tick"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True, exist_ok=True)
    _write_ticks(sym_dir / "EURUSD_202501_ticks.parquet", [1.0 + 0.001 * i for i in range(6)])

    bars0, dropped0, skipped0 = _build_offset_bars(
        tick_root=tick_root,
        symbol="EURUSD",
        bar_ticks=2,
        tick_offset=0,
        price_source="bid",
        timestamp_mode="as_utc",
    )
    bars1, dropped1, skipped1 = _build_offset_bars(
        tick_root=tick_root,
        symbol="EURUSD",
        bar_ticks=2,
        tick_offset=1,
        price_source="bid",
        timestamp_mode="as_utc",
    )

    assert bars0.height == 3
    assert bars1.height == 2
    assert dropped0 == 0
    assert dropped1 == 1
    assert skipped0 == 0
    assert skipped1 == 1
    assert str(bars0["timestamp"][0]).startswith("2025-01-01 00:00:00")
    assert str(bars1["timestamp"][0]).startswith("2025-01-01 00:00:01")


def test_build_offset_bars_uses_explicit_bid_ask_schema(tmp_path: Path) -> None:
    tick_root = tmp_path / "tick"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True, exist_ok=True)
    _write_ticks(sym_dir / "EURUSD_202501_ticks.parquet", [1.0 + 0.001 * i for i in range(4)])

    bars, _, _ = _build_offset_bars(
        tick_root=tick_root,
        symbol="EURUSD",
        bar_ticks=2,
        tick_offset=0,
        price_source="bid",
        timestamp_mode="as_utc",
    )

    assert "open_bid" in bars.columns
    assert "high_bid" in bars.columns
    assert "low_bid" in bars.columns
    assert "close_bid" in bars.columns
    assert "high_ask" in bars.columns
    assert "close_ask" in bars.columns
    assert "open" not in bars.columns
    assert "high" not in bars.columns
    assert "low" not in bars.columns
    assert "close" not in bars.columns
    assert "ask" not in bars.columns
    assert "close_EURUSD" not in bars.columns
    assert "ask_EURUSD" not in bars.columns
    assert "spread_EURUSD" not in bars.columns


def test_build_offset_bars_rejects_mid_price_source(tmp_path: Path) -> None:
    tick_root = tmp_path / "tick"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True, exist_ok=True)
    _write_ticks(sym_dir / "EURUSD_202501_ticks.parquet", [1.0, 1.001])

    with pytest.raises(ValueError, match="mid.*canonical bid"):
        _build_offset_bars(
            tick_root=tick_root,
            symbol="EURUSD",
            bar_ticks=2,
            tick_offset=0,
            price_source="mid",
            timestamp_mode="as_utc",
        )
