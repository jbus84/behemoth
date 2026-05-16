"""Tests for bar-level microstructure pre-aggregates in build_global_tick_bars."""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from scripts.build_global_tick_bars import _aggregate_from_base, _bars_from_ticks, _build_bar


def test_bar_includes_microstructure_columns():
    """Tick bars must include microstructure pre-aggregates."""
    ticks = pl.DataFrame(
        {
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:01Z",
                "2026-01-01T00:00:02Z",
                "2026-01-01T00:00:03Z",
                "2026-01-01T00:00:04Z",
            ],
            "bid": [1.1000, 1.1001, 1.1000, 1.0999, 1.1000],
            "ask": [1.1002, 1.1003, 1.1002, 1.1001, 1.1002],
        }
    )
    bar = _build_bar(ticks, bar_ticks=5, prev_close_bid=1.1000)
    assert "bar_return_sign" in bar.columns
    assert "tick_burst" in bar.columns
    assert "quote_revisions" in bar.columns
    assert "intra_bar_momentum" in bar.columns


def test_bar_microstructure_values():
    """Verify microstructure pre-aggregate values for a known tick stream."""
    ticks = pl.DataFrame(
        {
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:01Z",
                "2026-01-01T00:00:02Z",
                "2026-01-01T00:00:03Z",
                "2026-01-01T00:00:04Z",
            ],
            "bid": [1.1000, 1.1001, 1.1000, 1.0999, 1.1000],
            "ask": [1.1002, 1.1003, 1.1002, 1.1001, 1.1002],
        }
    )
    bar = _build_bar(ticks, bar_ticks=5, prev_close_bid=1.1000)

    # close (1.1000) == prev_close_bid (1.1000) -> 0
    assert bar["bar_return_sign"][0] == 0

    # tick_burst == bar_ticks
    assert bar["tick_burst"][0] == 5

    # bid changes: 1.1000 -> 1.1001 -> 1.1000 -> 1.0999 -> 1.1000 = 4 changes
    assert bar["quote_revisions"][0] == 4

    # hl_first: high (1.1001 at pos 1) before low (1.0999 at pos 3) -> +1
    # range = 1.1001 - 1.0999 = 0.0002
    # pip for EURUSD = 0.0001
    # intra_bar_momentum = 1 * 0.0002 / 0.0001 = 2.0
    assert bar["intra_bar_momentum"][0] == pytest.approx(2.0)


def test_bar_return_sign_positive():
    """bar_return_sign = +1 when close > prev_close."""
    ticks = pl.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"],
            "bid": [1.1000, 1.1001],
            "ask": [1.1002, 1.1003],
        }
    )
    bar = _build_bar(ticks, bar_ticks=2, prev_close_bid=1.1000)
    assert bar["bar_return_sign"][0] == 1


def test_bar_return_sign_negative():
    """bar_return_sign = -1 when close < prev_close."""
    ticks = pl.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"],
            "bid": [1.1000, 1.0999],
            "ask": [1.1002, 1.1001],
        }
    )
    bar = _build_bar(ticks, bar_ticks=2, prev_close_bid=1.1000)
    assert bar["bar_return_sign"][0] == -1


def test_bar_return_sign_zero_when_no_prev():
    """bar_return_sign = 0 when prev_close_bid is None."""
    ticks = pl.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"],
            "bid": [1.1000, 1.1001],
            "ask": [1.1002, 1.1003],
        }
    )
    bar = _build_bar(ticks, bar_ticks=2, prev_close_bid=None)
    assert bar["bar_return_sign"][0] == 0


def test_quote_revisions_zero_for_single_tick():
    """quote_revisions = 0 when there's only 1 tick."""
    ticks = pl.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z"],
            "bid": [1.1000],
            "ask": [1.1002],
        }
    )
    bar = _build_bar(ticks, bar_ticks=1)
    assert bar["quote_revisions"][0] == 0


def test_empty_bar_frame_has_microstructure_columns():
    """Empty bar frame must include all microstructure columns."""
    bar = _build_bar(pl.DataFrame(), bar_ticks=5)
    assert "bar_return_sign" in bar.columns
    assert "tick_burst" in bar.columns
    assert "quote_revisions" in bar.columns
    assert "intra_bar_momentum" in bar.columns


def test_bars_from_ticks_cross_bar_return_sign():
    """Two complete bars: first uses prev_close_bid, second uses first bar's close_bid."""
    ticks = pl.DataFrame(
        {
            "timestamp": [
                datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
            ],
            "price": [1.1000, 1.1001, 1.1001, 1.1000],
            "ask": [1.1002, 1.1003, 1.1003, 1.1002],
            "spread": [0.0002, 0.0002, 0.0002, 0.0002],
        },
        schema_overrides={"timestamp": pl.Datetime("ns", "UTC")},
    )

    bars, tick_idx, remainder = _bars_from_ticks(
        ticks,
        symbol="EURUSD",
        bar_ticks=2,
        start_tick_index=0,
        prev_close_bid=1.1000,
    )

    assert bars.height == 2
    assert tick_idx == 4
    assert remainder.height == 0

    # Bar 0: close_bid = 1.1001 > prev_close_bid = 1.1000 -> +1
    assert bars["bar_return_sign"][0] == 1
    # Bar 1: close_bid = 1.1000 < bar 0 close_bid = 1.1001 -> -1
    assert bars["bar_return_sign"][1] == -1

    # New microstructure fields must be present
    assert "tick_burst" in bars.columns
    assert "quote_revisions" in bars.columns
    assert "intra_bar_momentum" in bars.columns

    # Bar 0 has two ticks with different prices (1.1000 -> 1.1001) -> 1 revision
    assert bars["quote_revisions"][0] == 1
    # Bar 1 has two ticks with different prices (1.1001 -> 1.1000) -> 1 revision
    assert bars["quote_revisions"][1] == 1
    # tick_burst == bar_ticks for each bar
    assert bars["tick_burst"][0] == 2
    assert bars["tick_burst"][1] == 2


def test_aggregate_from_base_preserves_microstructure_fields():
    """New fields survive aggregation from base bars correctly."""
    base = pl.DataFrame(
        {
            "timestamp": [
                datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
            ],
            "close_ts": [
                datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 4, tzinfo=timezone.utc),
            ],
            "open_bid": [1.1000, 1.1001, 1.1002, 1.1003],
            "high_bid": [1.1001, 1.1002, 1.1003, 1.1004],
            "low_bid": [1.0999, 1.1000, 1.1001, 1.1002],
            "close_bid": [1.1001, 1.1002, 1.1003, 1.1004],
            "high_ask": [1.1003, 1.1004, 1.1005, 1.1006],
            "close_ask": [1.1003, 1.1004, 1.1005, 1.1006],
            "spread": [0.0002, 0.0002, 0.0002, 0.0002],
            "tick_volume": [2, 2, 2, 2],
            "high_pos_tick": [1, 1, 1, 1],
            "low_pos_tick": [0, 0, 0, 0],
            "hl_first": [1, 1, 1, 1],
            "hl_pos_delta_tick": [-1, -1, -1, -1],
            "hl_pos_frac": [-0.5, -0.5, -0.5, -0.5],
            "bar_return_sign": [1, 1, 1, 1],
            "tick_burst": [2, 2, 2, 2],
            "quote_revisions": [2, 3, 2, 3],
            "intra_bar_momentum": [2.0, 2.0, 2.0, 2.0],
        },
        schema_overrides={
            "timestamp": pl.Datetime("ns", "UTC"),
            "close_ts": pl.Datetime("ns", "UTC"),
        },
    )

    bars, dropped = _aggregate_from_base(
        base, symbol="EURUSD", target_ticks=4, base_ticks=2
    )

    assert dropped == 0
    assert bars.height == 2

    # tick_volume and tick_burst should sum over the aggregated bars
    assert bars["tick_volume"].to_list() == [4, 4]
    assert bars["tick_burst"].to_list() == [4, 4]
    # quote_revisions should sum
    assert bars["quote_revisions"].to_list() == [5, 5]

    # All microstructure columns must be present
    assert "bar_return_sign" in bars.columns
    assert "tick_burst" in bars.columns
    assert "quote_revisions" in bars.columns
    assert "intra_bar_momentum" in bars.columns

    # Intra-bar momentum should be recomputed from aggregated OHLC
    for i in range(bars.height):
        assert bars["intra_bar_momentum"][i] is not None
