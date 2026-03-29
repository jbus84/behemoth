"""Tests for JForex coverage gap diagnostic functions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from scripts.diagnose_jforex_coverage_gaps import (
    load_audit_log_timestamps,
    post_warmup_coverage,
    warmup_gap_count,
)


def _make_audit_db(tmp_path: Path, close_timestamps_utc: list[str]) -> Path:
    """Create a minimal audit_logs DuckDB at tmp_path/state.db."""
    db_path = tmp_path / "state.db"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE audit_logs ("
        "  event_ts TIMESTAMPTZ,"
        "  close_ts TIMESTAMPTZ,"
        "  symbol VARCHAR,"
        "  candidate_uid VARCHAR,"
        "  pred_prob DOUBLE,"
        "  threshold DOUBLE,"
        "  features_json VARCHAR,"
        "  model_month VARCHAR,"
        "  run_id VARCHAR"
        ")"
    )
    for ts in close_timestamps_utc:
        con.execute(
            "INSERT INTO audit_logs(event_ts, close_ts) VALUES (NOW(), ?::TIMESTAMPTZ)",
            [ts],
        )
    con.close()
    return db_path


def test_load_audit_log_timestamps_returns_utc_datetimes(tmp_path: Path) -> None:
    db = _make_audit_db(
        tmp_path,
        ["2025-07-07T08:30:00Z", "2025-07-07T10:00:00Z", "2025-07-08T12:00:00Z"],
    )
    result = load_audit_log_timestamps(db, eval_end="2025-07-09T00:00:00Z")
    assert len(result) == 3
    assert all(ts.tzinfo is not None for ts in result)
    assert min(result) == datetime(2025, 7, 7, 8, 30, tzinfo=timezone.utc)


def test_load_audit_log_timestamps_excludes_entries_after_eval_end(tmp_path: Path) -> None:
    db = _make_audit_db(
        tmp_path,
        ["2025-07-07T08:30:00Z", "2025-07-09T01:00:00Z"],
    )
    result = load_audit_log_timestamps(db, eval_end="2025-07-09T00:00:00Z")
    assert len(result) == 1


def test_load_audit_log_timestamps_empty_db(tmp_path: Path) -> None:
    db = _make_audit_db(tmp_path, [])
    result = load_audit_log_timestamps(db, eval_end="2025-07-09T00:00:00Z")
    assert result == []


def test_warmup_gap_count_counts_predictions_before_cutoff() -> None:
    locked = [
        datetime(2025, 7, 7, 0, 0, tzinfo=timezone.utc),
        datetime(2025, 7, 7, 5, 0, tzinfo=timezone.utc),
        datetime(2025, 7, 7, 9, 0, tzinfo=timezone.utc),
    ]
    cutoff = datetime(2025, 7, 7, 8, 30, tzinfo=timezone.utc)
    assert warmup_gap_count(locked, cutoff) == 2


def test_warmup_gap_count_zero_when_all_after_cutoff() -> None:
    locked = [datetime(2025, 7, 7, 10, 0, tzinfo=timezone.utc)]
    cutoff = datetime(2025, 7, 7, 8, 30, tzinfo=timezone.utc)
    assert warmup_gap_count(locked, cutoff) == 0


def test_post_warmup_coverage_exact_match() -> None:
    assert post_warmup_coverage(jforex_selected_total=79, locked_after_cutoff=79) == pytest.approx(
        1.0
    )


def test_post_warmup_coverage_ratio_above_one_is_valid() -> None:
    ratio = post_warmup_coverage(jforex_selected_total=79, locked_after_cutoff=69)
    assert ratio > 1.0


def test_post_warmup_coverage_zero_locked_returns_zero() -> None:
    assert post_warmup_coverage(jforex_selected_total=5, locked_after_cutoff=0) == 0.0
