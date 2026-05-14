from datetime import datetime, timezone

from src.behemoth.core.schemas import BarContext, BarPrices
from src.behemoth.runtime.barrier_manager import BarrierManager
from src.behemoth.runtime.state_store import InMemoryStateStore


def _make_bar_context(
    symbol: str = "EURUSD",
    bar_idx: int = 2,
    bid_high: float = 1.1100,
    bid_low: float = 1.0900,
    bid_close: float = 1.1050,
    ask_high: float = 1.1120,
    ask_low: float = 1.0920,
    ask_close: float = 1.1070,
    hl_first: float = 1.0,
) -> BarContext:
    return BarContext(
        symbol=symbol,
        bar_ticks=100,
        bar_idx=bar_idx,
        timestamp=datetime.now(timezone.utc),
        close_ts=datetime.now(timezone.utc),
        spread=0.0002,
        bid=BarPrices(high=bid_high, low=bid_low, close=bid_close),
        ask=BarPrices(high=ask_high, low=ask_low, close=ask_close),
        hl_first=hl_first,
    )


class TestBarrierManagerTransactions:
    def test_scanning_phase_is_atomic(self) -> None:
        store = InMemoryStateStore()
        bm = BarrierManager(store=store)
        scan_id = bm.register_scan(
            symbol="EURUSD", candidate_uid="c1", signal_bar_idx=1,
            barrier_pips=2.0, horizon=6, pip_size=0.0001,
            pred_prob=0.8, threshold=0.5, model_month="2026-01",
            reservation_id="r1", run_id="run1",
            ref_price=1.1, signal_close_ask=1.1002, signal_close_bid=1.1,
        )
        # Bar that triggers upper barrier touch (ask.high >= upper_barrier)
        # upper_barrier = 1.1002 + 2.0 * 0.0001 = 1.1004
        bar = _make_bar_context(bar_idx=2, ask_high=1.1005, ask_close=1.1005)
        result = bm.evaluate_bar_with_result(bar)
        assert len(result.actions) == 1
        assert result.actions[0].type.value == "OPEN_MARKET"
        scan = bm.get_scan(scan_id)
        assert scan is not None
        assert scan["status"] == "HOLDING"
        assert scan["touch_side"] == "BUY"

    def test_holding_phase_is_atomic(self) -> None:
        store = InMemoryStateStore()
        bm = BarrierManager(store=store)
        scan_id = bm.register_scan(
            symbol="EURUSD", candidate_uid="c1", signal_bar_idx=1,
            barrier_pips=2.0, horizon=6, pip_size=0.0001,
            pred_prob=0.8, threshold=0.5, model_month="2026-01",
            reservation_id="r1", run_id="run1",
            ref_price=1.1, signal_close_ask=1.1002, signal_close_bid=1.1,
        )
        # First bar: touch upper barrier -> transition to HOLDING
        bar1 = _make_bar_context(bar_idx=2, ask_high=1.1005, ask_close=1.1005)
        bm.evaluate_bar_with_result(bar1)
        scan = bm.get_scan(scan_id)
        assert scan["status"] == "HOLDING"
        assert scan["hold_bars_remaining"] == 6

        # Second bar: no touch, decrement hold_bars_remaining
        bar2 = _make_bar_context(bar_idx=3, ask_high=1.1003, ask_close=1.1003)
        bm.evaluate_bar_with_result(bar2)
        scan = bm.get_scan(scan_id)
        assert scan["status"] == "HOLDING"
        assert scan["hold_bars_remaining"] == 5
