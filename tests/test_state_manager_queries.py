from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.behemoth.runtime.state import StateManager
from src.behemoth.core.schemas import IncomingTickBar


@pytest.fixture
def sm():
    state = StateManager()
    yield state
    state.close()


def _make_bar(symbol: str, bar_ticks: int, row_num: int, close_bid: float = 1.1000) -> IncomingTickBar:
    """Helper: build a minimal IncomingTickBar for test data insertion."""
    ts = datetime(2026, 1, 1, 0, row_num, tzinfo=timezone.utc)
    return IncomingTickBar(
        symbol=symbol,
        bar_ticks=bar_ticks,
        timestamp=ts,
        close_ts=ts,
        open_bid=close_bid,
        high_bid=close_bid + 0.001,
        low_bid=close_bid - 0.001,
        close_bid=close_bid,
        spread=0.0001,
        tick_volume=100.0,
        high_ask=close_bid + 0.0001,
        close_ask=close_bid + 0.0001,
    )


def test_get_open_trade_entry_price_returns_price(sm):
    sm.open_trade(
        symbol="EURUSD",
        candidate_uid="cand-001",
        broker_pos_id="broker-001",
        side="BUY",
        entry_price=1.2345,
        entry_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        horizon=50,
        reservation_id="res-001",
    )
    result = sm.get_open_trade_entry_price("res-001")
    assert result == pytest.approx(1.2345)


def test_get_open_trade_entry_price_returns_none_when_not_found(sm):
    result = sm.get_open_trade_entry_price("nonexistent-res")
    assert result is None


def test_get_latest_bar_id_returns_max_row_id(sm):
    sm.append_bar(_make_bar("EURUSD", 100, 1))
    sm.append_bar(_make_bar("EURUSD", 100, 2))
    sm.append_bar(_make_bar("EURUSD", 100, 3))
    result = sm.get_latest_bar_id("EURUSD")
    assert result == 2  # row_id is 0-indexed: rows 0, 1, 2


def test_get_latest_bar_id_returns_zero_when_no_rows(sm):
    result = sm.get_latest_bar_id("NOSYMBOL")
    assert result == 0


def test_get_latest_tick_snapshot_returns_most_recent_bar(sm):
    sm.append_bar(_make_bar("EURUSD", 100, 1, close_bid=1.1000))
    sm.append_bar(_make_bar("EURUSD", 200, 2, close_bid=1.2000))  # different bar_ticks, later row
    result = sm.get_latest_tick_snapshot("EURUSD")
    assert result is not None
    price, ts = result
    assert price == pytest.approx(1.2000)
    assert ts.tzinfo is not None


def test_get_latest_tick_snapshot_returns_none_when_no_rows(sm):
    result = sm.get_latest_tick_snapshot("NOSYMBOL")
    assert result is None


def test_get_latest_bar_id_is_max_across_all_bar_ticks(sm):
    # 100-tick bars: row_ids 0, 1, 2
    sm.append_bar(_make_bar("EURUSD", 100, 1))
    sm.append_bar(_make_bar("EURUSD", 100, 2))
    sm.append_bar(_make_bar("EURUSD", 100, 3))
    # 200-tick bar: row_id 0 (resets per bar_ticks)
    sm.append_bar(_make_bar("EURUSD", 200, 4))
    result = sm.get_latest_bar_id("EURUSD")
    # MAX(row_id) across all bar_ticks = 2 (from 100-tick bars), not 0 (from 200-tick)
    assert result == 2
