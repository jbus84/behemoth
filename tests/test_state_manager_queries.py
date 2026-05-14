from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.behemoth.core.schemas import IncomingTickBar
from src.behemoth.runtime.state import StateManager


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


def _insert_audit_row(sm: StateManager, symbol: str, run_id: str) -> None:
    """Insert a minimal audit_logs row via the public batch API."""
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sm.log_audit_event_batch([
        (ts, symbol.upper(), "cand-001", 0.8, 0.5, "{}", "2026-01", run_id)
    ])


def test_count_audit_logs_returns_correct_count(sm):
    _insert_audit_row(sm, "EURUSD", "run-a")
    _insert_audit_row(sm, "EURUSD", "run-a")
    _insert_audit_row(sm, "EURUSD", "run-b")
    assert sm.count_audit_logs("EURUSD", "run-a") == 2
    assert sm.count_audit_logs("EURUSD", "run-b") == 1
    assert sm.count_audit_logs("EURUSD", "run-c") == 0


def test_clear_audit_logs_by_run_id_removes_matching_rows(sm):
    _insert_audit_row(sm, "EURUSD", "threshold_seed")
    _insert_audit_row(sm, "EURUSD", "threshold_seed")
    _insert_audit_row(sm, "EURUSD", "other_run")
    sm.clear_audit_logs_by_run_id("threshold_seed")
    assert sm.count_audit_logs("EURUSD", "threshold_seed") == 0
    assert sm.count_audit_logs("EURUSD", "other_run") == 1


def test_clear_audit_logs_by_run_id_no_op_when_nothing_matches(sm):
    sm.clear_audit_logs_by_run_id("nonexistent")  # must not raise


def test_atomic_audit_replace_purges_and_writes(sm):
    # Seed existing rows for (EURUSD, run-x)
    _insert_audit_row(sm, "EURUSD", "run-x")
    _insert_audit_row(sm, "EURUSD", "run-x")
    assert sm.count_audit_logs("EURUSD", "run-x") == 2

    ts = datetime(2026, 2, 1, tzinfo=timezone.utc)
    new_events = [
        (ts, "EURUSD", "cand-new", 0.9, 0.5, "{}", "2026-02", "run-x"),
    ]
    purged = sm.atomic_audit_replace("EURUSD", "run-x", new_events)
    assert purged == 2
    assert sm.count_audit_logs("EURUSD", "run-x") == 1


def test_atomic_audit_replace_rolls_back_on_error(sm):
    _insert_audit_row(sm, "EURUSD", "run-y")

    # Pass a malformed event tuple (wrong column count) to trigger an error
    bad_events = [("not", "enough")]
    with pytest.raises(Exception):
        sm.atomic_audit_replace("EURUSD", "run-y", bad_events)

    # Original row must still be present — rollback happened
    assert sm.count_audit_logs("EURUSD", "run-y") == 1


def test_atomic_audit_replace_returns_zero_when_nothing_purged(sm):
    ts = datetime(2026, 2, 1, tzinfo=timezone.utc)
    events = [(ts, "EURUSD", "cand-001", 0.8, 0.5, "{}", "2026-02", "run-new")]
    purged = sm.atomic_audit_replace("EURUSD", "run-new", events)
    assert purged == 0
    assert sm.count_audit_logs("EURUSD", "run-new") == 1


def test_export_warmup_bars_writes_parquet_and_returns_row_count(sm, tmp_path):
    import polars as pl

    sm.append_bar(_make_bar("EURUSD", 100, 1, close_bid=1.1000))
    sm.append_bar(_make_bar("EURUSD", 100, 2, close_bid=1.1010))
    sm.append_bar(_make_bar("EURUSD", 200, 3, close_bid=1.2000))  # different bar_ticks, excluded

    out_path = tmp_path / "warmup.parquet"
    count = sm.export_warmup_bars("EURUSD", 100, out_path)

    assert count == 2
    assert out_path.exists()
    df = pl.read_parquet(out_path)
    assert len(df) == 2
    assert "row_id" in df.columns
    assert "close_bid" in df.columns


def test_export_warmup_bars_returns_zero_when_no_rows(sm, tmp_path):
    out_path = tmp_path / "empty.parquet"
    count = sm.export_warmup_bars("NOSYMBOL", 100, out_path)
    assert count == 0


def test_checkpoint_does_not_raise(sm):
    sm.append_bar(_make_bar("EURUSD", 100, 1))
    sm.checkpoint()  # must not raise
