"""Smoke test for the daily tick-coverage operator script."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from scripts.check_daily_tick_coverage import check_symbol


def _write_monthly_parquet(
    path: Path, *, year: int, month: int, days: int,
) -> None:
    """Write a synthetic monthly tick parquet covering the first `days`
    days of the month (one tick per hour to keep the fixture tiny)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    base = datetime(year, month, 1, tzinfo=timezone.utc)
    for d in range(days):
        for h in range(24):
            rows.append({"timestamp": base + timedelta(days=d, hours=h)})
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_complete_month_reports_no_issues(tmp_path: Path):
    sym_dir = tmp_path / "EURUSD"
    # January 2025 has 31 days.
    _write_monthly_parquet(
        sym_dir / "EURUSD_202501_ticks.parquet", year=2025, month=1, days=31,
    )
    issues = check_symbol("EURUSD", tmp_path)
    assert issues == []


def test_partial_month_is_flagged(tmp_path: Path):
    sym_dir = tmp_path / "EURUSD"
    # February 2025 has 28 days; we ship only 20.
    _write_monthly_parquet(
        sym_dir / "EURUSD_202502_ticks.parquet", year=2025, month=2, days=20,
    )
    issues = check_symbol("EURUSD", tmp_path)
    assert len(issues) == 1
    issue = issues[0]
    assert issue["expected_days"] == 28
    assert issue["actual_days"] == 20
    assert issue["missing_days"] == 8


def test_no_files_returns_no_issues(tmp_path: Path):
    (tmp_path / "EURUSD").mkdir()
    assert check_symbol("EURUSD", tmp_path) == []
