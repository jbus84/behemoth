from __future__ import annotations

import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd


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
    find_first_market_gap,
    get_fetchable_end,
    get_missing_months,
    get_session_bounds_utc,
    is_expected_weekend_gap,
    is_fx_market_open,
    should_clear_stale_lock,
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


def test_is_expected_weekend_gap_rejects_gap_starting_before_friday_close() -> None:
    prev_ts = datetime(2025, 10, 1, 12, 0, tzinfo=UTC)
    next_ts = datetime(2025, 10, 5, 21, 0, 42, 115000, tzinfo=UTC)
    assert is_expected_weekend_gap(prev_ts, next_ts) is False


def _write_gap_parquet(path: Path, timestamps: list[datetime]) -> Path:
    pd.DataFrame({"timestamp": timestamps}).to_parquet(path, index=False)
    return path


def test_find_first_market_gap_ignores_expected_weekend_gap(tmp_path: Path) -> None:
    path = _write_gap_parquet(
        tmp_path / "weekend_gap.parquet",
        [
            datetime(2025, 10, 3, 20, 59, 59, 574000, tzinfo=UTC),
            datetime(2025, 10, 5, 21, 0, 42, 115000, tzinfo=UTC),
        ],
    )

    assert find_first_market_gap(path) is None


def test_find_first_market_gap_returns_weekday_intra_session_gap_start(tmp_path: Path) -> None:
    gap_start = datetime(2025, 10, 1, 12, 0, tzinfo=UTC)
    path = _write_gap_parquet(
        tmp_path / "weekday_gap.parquet",
        [
            gap_start,
            datetime(2025, 10, 1, 15, 30, tzinfo=UTC),
        ],
    )

    assert find_first_market_gap(path) == gap_start


# --- Task 3: get_fetchable_end and current-month scheduling ---


def test_get_fetchable_end_returns_now_when_market_open() -> None:
    # Wednesday mid-session (DST)
    now = datetime(2025, 10, 1, 14, 0, tzinfo=UTC)
    assert get_fetchable_end(now) == now


def test_get_fetchable_end_returns_friday_close_when_market_closed() -> None:
    # Friday after DST close (21:00 UTC), still before Sunday reopen
    now = datetime(2025, 10, 3, 21, 30, tzinfo=UTC)
    result = get_fetchable_end(now)
    assert result == datetime(2025, 10, 3, 21, 0, tzinfo=UTC)


def test_get_fetchable_end_returns_friday_close_on_saturday() -> None:
    now = datetime(2025, 10, 4, 12, 0, tzinfo=UTC)
    result = get_fetchable_end(now)
    assert result == datetime(2025, 10, 3, 21, 0, tzinfo=UTC)


def _write_tick_parquet(path: Path, timestamps: list[datetime]) -> None:
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, utc=True),
            "bid": [1.1] * len(timestamps),
            "ask": [1.1001] * len(timestamps),
        }
    ).to_parquet(path, index=False)


def test_get_missing_months_does_not_refill_after_friday_close(monkeypatch, tmp_path: Path) -> None:
    """After Friday close, current-month should not schedule a refill."""
    out_dir = tmp_path / "ticks"
    symbol_dir = out_dir / "EURUSD"
    symbol_dir.mkdir(parents=True)
    month_path = symbol_dir / "EURUSD_202510_ticks.parquet"
    _write_tick_parquet(
        month_path,
        [datetime(2025, 10, 3, 20, 59, 59, 999000, tzinfo=UTC)],
    )
    # Pretend now is Friday after DST close
    fake_now = datetime(2025, 10, 3, 21, 30, tzinfo=UTC)
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.datetime",
        type("FakeDT", (), {"now": staticmethod(lambda tz=None: fake_now)}),
    )
    # GLOBAL_START_DATE would scan too many months; scope end_date to Oct 2025 only
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.GLOBAL_START_DATE", datetime(2025, 10, 1, tzinfo=UTC)
    )
    ranges = get_missing_months("EURUSD", out_dir, fake_now)
    assert ranges == []


def test_get_missing_months_appends_before_friday_close(monkeypatch, tmp_path: Path) -> None:
    """Before Friday close, current-month should schedule a refill up to now."""
    out_dir = tmp_path / "ticks"
    symbol_dir = out_dir / "EURUSD"
    symbol_dir.mkdir(parents=True)
    month_path = symbol_dir / "EURUSD_202510_ticks.parquet"
    last_ts = datetime(2025, 10, 3, 19, 59, 59, tzinfo=UTC)
    _write_tick_parquet(month_path, [last_ts])
    fake_now = datetime(2025, 10, 3, 20, 30, tzinfo=UTC)
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.datetime",
        type("FakeDT", (), {"now": staticmethod(lambda tz=None: fake_now)}),
    )
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.GLOBAL_START_DATE", datetime(2025, 10, 1, tzinfo=UTC)
    )
    ranges = get_missing_months("EURUSD", out_dir, fake_now)
    expected_start = last_ts + timedelta(microseconds=1000)
    assert len(ranges) == 1
    assert ranges[0][0] == expected_start
    assert ranges[0][1] == fake_now


# --- boundary tolerance for historical months ---


def test_get_missing_months_ignores_file_ending_near_month_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """A file ending seconds before month-end should not trigger a refill."""
    out_dir = tmp_path / "ticks"
    symbol_dir = out_dir / "EURUSD"
    symbol_dir.mkdir(parents=True)
    # Jan 2018 file ends at 23:59:47 on Jan 31 (13s before month end)
    month_path = symbol_dir / "EURUSD_201801_ticks.parquet"
    _write_tick_parquet(month_path, [datetime(2018, 1, 31, 23, 59, 47, 19000, tzinfo=UTC)])
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.GLOBAL_START_DATE", datetime(2018, 1, 1, tzinfo=UTC)
    )
    fake_now = datetime(2026, 3, 27, 17, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.datetime",
        type("FakeDT", (), {"now": staticmethod(lambda tz=None: fake_now)}),
    )
    ranges = get_missing_months("EURUSD", out_dir, datetime(2018, 2, 1, tzinfo=UTC))
    assert ranges == []


def test_get_missing_months_ignores_file_ending_near_friday_close(
    monkeypatch, tmp_path: Path
) -> None:
    """A file ending seconds before Friday close should not trigger a refill."""
    out_dir = tmp_path / "ticks"
    symbol_dir = out_dir / "EURUSD"
    symbol_dir.mkdir(parents=True)
    # Jun 2018 file ends at 20:59:56 on Jun 29 (DST close at 21:00)
    month_path = symbol_dir / "EURUSD_201806_ticks.parquet"
    _write_tick_parquet(month_path, [datetime(2018, 6, 29, 20, 59, 56, 236000, tzinfo=UTC)])
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.GLOBAL_START_DATE", datetime(2018, 6, 1, tzinfo=UTC)
    )
    fake_now = datetime(2026, 3, 27, 17, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.datetime",
        type("FakeDT", (), {"now": staticmethod(lambda tz=None: fake_now)}),
    )
    ranges = get_missing_months("EURUSD", out_dir, datetime(2018, 7, 1, tzinfo=UTC))
    assert ranges == []


def test_get_missing_months_still_flags_genuinely_early_ending(monkeypatch, tmp_path: Path) -> None:
    """A file ending hours before Friday close should still trigger a refill."""
    out_dir = tmp_path / "ticks"
    symbol_dir = out_dir / "EURUSD"
    symbol_dir.mkdir(parents=True)
    # File ends at 15:00 on a Wednesday — genuinely truncated
    month_path = symbol_dir / "EURUSD_201806_ticks.parquet"
    last_ts = datetime(2018, 6, 20, 15, 0, tzinfo=UTC)
    _write_tick_parquet(month_path, [last_ts])
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.GLOBAL_START_DATE", datetime(2018, 6, 1, tzinfo=UTC)
    )
    fake_now = datetime(2026, 3, 27, 17, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.datetime",
        type("FakeDT", (), {"now": staticmethod(lambda tz=None: fake_now)}),
    )
    ranges = get_missing_months("EURUSD", out_dir, datetime(2018, 7, 1, tzinfo=UTC))
    assert len(ranges) == 1
    assert ranges[0][0] == last_ts + timedelta(microseconds=1000)


# --- Task 4: stale-lock cleanup ---


def test_should_clear_stale_lock_when_no_downloader_process(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "download_tick_vault.lock"
    lock_path.touch()
    monkeypatch.setattr(
        "scripts.download_tick_vault_data._list_process_commands",
        lambda: ["python app.py"],
    )
    assert should_clear_stale_lock(lock_path) is True


def test_should_not_clear_lock_when_downloader_running(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "download_tick_vault.lock"
    lock_path.touch()
    monkeypatch.setattr(
        "scripts.download_tick_vault_data._list_process_commands",
        lambda: ["python scripts/download_tick_vault_data.py --symbols EURUSD"],
    )
    assert should_clear_stale_lock(lock_path) is False


def test_should_clear_stale_lock_returns_false_when_no_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "download_tick_vault.lock"
    assert should_clear_stale_lock(lock_path) is False
