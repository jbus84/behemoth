import pytest
from datetime import datetime, timezone

from src.behemoth.core.schemas import IncomingTickBar
from src.behemoth.runtime.bar_store import BarStore
from src.behemoth.runtime.state_store import InMemoryStateStore


class TestBarStore:
    def test_append_and_count(self) -> None:
        store = InMemoryStateStore()
        bar_store = BarStore(store)
        bar = IncomingTickBar(
            symbol="EURUSD", bar_ticks=100, timestamp=datetime.now(timezone.utc),
            close_ts=datetime.now(timezone.utc), open_bid=1.1, high_bid=1.11,
            low_bid=1.09, close_bid=1.105, spread=0.0002, tick_volume=100.0,
            hl_first=1.0, hl_pos_frac=0.5, high_ask=1.112, close_ask=1.107,
        )
        bar_store.append_bar(bar)
        assert bar_store.bar_count("EURUSD", 100) == 1

    def test_get_latest_bar_context(self) -> None:
        store = InMemoryStateStore()
        bar_store = BarStore(store)
        bar = IncomingTickBar(
            symbol="EURUSD", bar_ticks=100, timestamp=datetime.now(timezone.utc),
            close_ts=datetime.now(timezone.utc), open_bid=1.1, high_bid=1.11,
            low_bid=1.09, close_bid=1.105, spread=0.0002, tick_volume=100.0,
            hl_first=1.0, hl_pos_frac=0.5, high_ask=1.112, close_ask=1.107,
        )
        bar_store.append_bar(bar)
        ctx = bar_store.get_latest_bar_context("EURUSD", 100)
        assert ctx is not None
        assert ctx.symbol == "EURUSD"
        assert ctx.bar_ticks == 100
        assert ctx.bid.close == pytest.approx(1.105)
