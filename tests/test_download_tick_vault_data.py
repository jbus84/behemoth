from __future__ import annotations

from datetime import UTC, datetime

from scripts.download_tick_vault_data import (
    get_session_bounds_utc,
    is_expected_weekend_gap,
    is_fx_market_open,
)


def test_is_fx_market_open_handles_winter_friday_close() -> None:
    assert is_fx_market_open(datetime(2026, 1, 2, 21, 30, tzinfo=UTC)) is True
    assert is_fx_market_open(datetime(2026, 1, 2, 22, 0, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2026, 1, 4, 21, 59, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2026, 1, 4, 22, 0, tzinfo=UTC)) is True


def test_is_fx_market_open_handles_dst_friday_close() -> None:
    assert is_fx_market_open(datetime(2025, 10, 3, 20, 30, tzinfo=UTC)) is True
    assert is_fx_market_open(datetime(2025, 10, 3, 21, 0, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2025, 10, 5, 20, 59, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2025, 10, 5, 21, 0, tzinfo=UTC)) is True


def test_get_session_bounds_utc_matches_new_york_close_reopen() -> None:
    close_utc, reopen_utc = get_session_bounds_utc(datetime(2025, 10, 3, 12, 0, tzinfo=UTC))
    assert close_utc.isoformat() == "2025-10-03T21:00:00+00:00"
    assert reopen_utc.isoformat() == "2025-10-05T21:00:00+00:00"


def test_is_fx_market_open_handles_spring_friday_close() -> None:
    assert is_fx_market_open(datetime(2025, 3, 7, 21, 30, tzinfo=UTC)) is True
    assert is_fx_market_open(datetime(2025, 3, 7, 22, 0, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2025, 3, 9, 20, 59, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2025, 3, 9, 21, 0, tzinfo=UTC)) is True


def test_get_session_bounds_utc_matches_spring_transition() -> None:
    close_utc, reopen_utc = get_session_bounds_utc(datetime(2025, 3, 7, 12, 0, tzinfo=UTC))
    assert close_utc.isoformat() == "2025-03-07T22:00:00+00:00"
    assert reopen_utc.isoformat() == "2025-03-09T21:00:00+00:00"


def test_is_expected_weekend_gap_matches_observed_gap() -> None:
    prev_ts = datetime(2025, 10, 3, 20, 59, 59, 574000, tzinfo=UTC)
    next_ts = datetime(2025, 10, 5, 21, 0, 42, 115000, tzinfo=UTC)
    assert is_expected_weekend_gap(prev_ts, next_ts) is True
