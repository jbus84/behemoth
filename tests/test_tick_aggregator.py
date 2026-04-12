"""TDD tests for the real-time tick-to-bar aggregator.

Verifies that the aggregator produces bars with identical OHLC, spread,
and microstructure fields (hl_first, hl_pos_frac) to the Polars-based
``build_global_tick_bars.py::_bars_from_ticks()``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from src.behemoth.core.schemas import IncomingTick
from scripts.build_global_tick_bars import _bars_from_ticks, _build_symbol

# ── Helpers ───────────────────────────────────────────────────────────


def _make_ticks(
    n: int,
    symbol: str = "EURUSD",
    base_price: float = 1.10000,
    spread: float = 0.00012,
    seed: int = 42,
) -> list[IncomingTick]:
    """Generate deterministic synthetic ticks."""
    rng = np.random.default_rng(seed)
    ticks: list[IncomingTick] = []
    t = datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc)
    price = base_price
    for _ in range(n):
        price += rng.normal(0, 0.00005)
        bid = round(price, 5)
        ask = round(bid + spread, 5)
        ticks.append(
            IncomingTick(
                symbol=symbol,
                timestamp=t,
                bid=bid,
                ask=ask,
            )
        )
        t += timedelta(milliseconds=int(rng.integers(50, 500)))
    return ticks


# ── Tests ─────────────────────────────────────────────────────────────


class TestTickAggregatorBarCount:
    """Verify correct number of bars emitted."""

    def test_exact_100_ticks_produces_1_bar(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=100)
        ticks = _make_ticks(100)
        bars = agg.add_ticks(ticks)
        assert len(bars) == 1

    def test_250_ticks_produces_2_bars(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=100)
        ticks = _make_ticks(250)
        bars = agg.add_ticks(ticks)
        assert len(bars) == 2

    def test_50_ticks_produces_0_bars(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=100)
        ticks = _make_ticks(50)
        bars = agg.add_ticks(ticks)
        assert len(bars) == 0

    def test_remainder_carries_forward(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=100)
        # Feed 80, then 40 → should get 1 bar (100 ticks) + 20 remainder
        bars1 = agg.add_ticks(_make_ticks(80, seed=1))
        assert len(bars1) == 0
        bars2 = agg.add_ticks(_make_ticks(40, seed=2))
        assert len(bars2) == 1
        assert agg.remainder_count("EURUSD") == 20


class TestTickAggregatorOHLC:
    """Verify OHLC values are correct."""

    def test_open_bid_is_first_tick_mid(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=5)
        ticks = _make_ticks(5)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        expected_open = round(ticks[0].bid, 5)
        assert abs(bar.open_bid - expected_open) < 1e-5

    def test_close_bid_is_last_tick_mid(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=5)
        ticks = _make_ticks(5)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        expected_close = round(ticks[4].bid, 5)
        assert abs(bar.close_bid - expected_close) < 1e-5

    def test_high_bid_is_max_mid(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=5)
        ticks = _make_ticks(5)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        bids = [t.bid for t in ticks]
        assert abs(bar.high_bid - max(bids)) < 1e-5

    def test_low_bid_is_min_mid(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=5)
        ticks = _make_ticks(5)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        bids = [t.bid for t in ticks]
        assert abs(bar.low_bid - min(bids)) < 1e-5


class TestTickAggregatorMicrostructure:
    """Verify hl_first and hl_pos_frac match build_global_tick_bars logic."""

    def test_hl_first_correct(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=10)
        ticks = _make_ticks(10)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        # hl_first: +1 if high tick before low tick, -1 if low before high
        mids = [(t.bid + t.ask) / 2 for t in ticks]
        high_pos = mids.index(max(mids))
        low_pos = mids.index(min(mids))
        if high_pos < low_pos:
            expected = 1.0
        elif high_pos > low_pos:
            expected = -1.0
        else:
            expected = 0.0
        assert bar.hl_first == expected

    def test_hl_pos_frac_correct(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=10)
        ticks = _make_ticks(10)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        mids = [(t.bid + t.ask) / 2 for t in ticks]
        high_pos = mids.index(max(mids))
        low_pos = mids.index(min(mids))
        expected = (low_pos - high_pos) / max(1, 10 - 1)
        assert abs(bar.hl_pos_frac - expected) < 1e-6

    def test_spread_is_mean(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=5)
        ticks = _make_ticks(5)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        expected_spread = sum(t.ask - t.bid for t in ticks) / len(ticks)
        assert abs(bar.spread - expected_spread) < 1e-6

    def test_tick_volume_equals_bar_ticks(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=100)
        ticks = _make_ticks(100)
        bars = agg.add_ticks(ticks)
        assert bars[0].tick_volume == 100.0

    def test_timestamps_correct(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=5)
        ticks = _make_ticks(5)
        bars = agg.add_ticks(ticks)
        bar = bars[0]
        assert bar.timestamp == ticks[0].timestamp
        assert bar.close_ts == ticks[4].timestamp


class TestTickAggregatorMultiSymbol:
    """Verify per-symbol isolation."""

    def test_two_symbols_independent(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        agg = TickAggregator(bar_ticks=5)
        eu_ticks = _make_ticks(5, symbol="EURUSD", seed=1)
        gb_ticks = _make_ticks(3, symbol="GBPUSD", seed=2)
        bars = agg.add_ticks(eu_ticks + gb_ticks)
        eu_bars = [b for b in bars if b.symbol == "EURUSD"]
        gb_bars = [b for b in bars if b.symbol == "GBPUSD"]
        assert len(eu_bars) == 1
        assert len(gb_bars) == 0
        assert agg.remainder_count("GBPUSD") == 3


class TestAskColumns:
    """Verify high_ask and close_ask are correctly computed from ask prices."""

    def test_high_ask_is_max_ask_per_bar(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        ticks = _make_ticks(100, spread=0.00012)
        # Manually record the expected max ask
        expected_high_ask = max(float(t.ask) for t in ticks)

        agg = TickAggregator(bar_ticks=100)
        bars = agg.add_ticks(ticks)

        assert len(bars) == 1
        assert bars[0].high_ask == pytest.approx(expected_high_ask)

    def test_close_ask_is_last_ask_per_bar(self):
        from src.behemoth.runtime.tick_aggregator import TickAggregator

        ticks = _make_ticks(100, spread=0.00012)
        expected_close_ask = float(ticks[-1].ask)

        agg = TickAggregator(bar_ticks=100)
        bars = agg.add_ticks(ticks)

        assert len(bars) == 1
        assert bars[0].close_ask == pytest.approx(expected_close_ask)


class TestOfflineBarSchema:
    """Verify offline bar builders emit the explicit bid/ask schema."""

    def test_bars_from_ticks_uses_explicit_bid_ask_columns(self):
        ticks = pl.DataFrame(
            {
                "timestamp": [
                    datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                    datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                ],
                "bid": [1.1, 1.2],
                "price": [1.1, 1.2],
                "ask": [1.1002, 1.2002],
                "spread": [0.0002, 0.0002],
            },
            schema_overrides={"timestamp": pl.Datetime("ns", "UTC")},
        )

        bars, _, _ = _bars_from_ticks(
            ticks,
            symbol="EURUSD",
            bar_ticks=2,
            start_tick_index=0,
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


def test_build_symbol_aggregates_base_bars_from_files(tmp_path) -> None:
    tick_root = tmp_path / "tick"
    output_dir = tmp_path / "bars"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True, exist_ok=True)

    ticks = pl.DataFrame(
        {
            "timestamp": [
                datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
            ],
            "bid": [1.1, 1.2, 1.0, 1.3],
            "ask": [1.1002, 1.2002, 1.0002, 1.3002],
            "spread": [0.0002, 0.0002, 0.0002, 0.0002],
        },
        schema_overrides={"timestamp": pl.Datetime("ns", "UTC")},
    )
    ticks.write_parquet(sym_dir / "EURUSD_202501_ticks.parquet")

    msgs = _build_symbol(
        tick_root=tick_root,
        output_dir=output_dir,
        symbol="EURUSD",
        base_ticks=2,
        target_ticks=[2, 4],
        price_source="bid",
        timestamp_mode="as_utc",
        overwrite=True,
    )

    out_path = output_dir / "EURUSD_4tick.parquet"
    assert out_path.exists()
    assert any(msg.startswith("ok EURUSD 4tick: 1 bars") for msg in msgs)

    bars = pl.read_parquet(out_path)
    assert bars.height == 1
    assert bars["timestamp"][0] == datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert bars["close_ts"][0] == datetime(2025, 1, 1, 0, 0, 3, tzinfo=timezone.utc)
    assert bars["open_bid"][0] == pytest.approx(1.1)
    assert bars["high_bid"][0] == pytest.approx(1.3)
    assert bars["low_bid"][0] == pytest.approx(1.0)
    assert bars["close_bid"][0] == pytest.approx(1.3)
