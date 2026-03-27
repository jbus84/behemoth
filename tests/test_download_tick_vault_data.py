from __future__ import annotations

import sys
import types
from datetime import UTC, datetime


def _install_tick_vault_stubs() -> None:
    if "tick_vault" in sys.modules:
        return

    package = types.ModuleType("tick_vault")
    package.__path__ = []  # type: ignore[attr-defined]

    config = types.ModuleType("tick_vault.config")
    config.reload_config = lambda **_: None
    config.CONFIG = object()

    download_worker = types.ModuleType("tick_vault.download_worker")
    download_worker.AsyncClient = object

    fetcher = types.ModuleType("tick_vault.fetcher")
    fetcher._fetch = lambda *args, **kwargs: None
    fetcher.RetryableError = RuntimeError
    fetcher.FetchError = RuntimeError

    def _download_range(*args, **kwargs):
        raise RuntimeError("download_range stub should not be used in helper tests")

    def _read_tick_data(*args, **kwargs):
        raise RuntimeError("read_tick_data stub should not be used in helper tests")

    package.config = config
    package.download_worker = download_worker
    package.fetcher = fetcher
    package.download_range = _download_range
    package.read_tick_data = _read_tick_data

    sys.modules["tick_vault"] = package
    sys.modules["tick_vault.config"] = config
    sys.modules["tick_vault.download_worker"] = download_worker
    sys.modules["tick_vault.fetcher"] = fetcher


_install_tick_vault_stubs()

from scripts.download_tick_vault_data import (  # noqa: E402
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
