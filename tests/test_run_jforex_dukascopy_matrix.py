"""Tests for JForex dukascopy matrix runner."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from scripts.run_jforex_dukascopy_matrix import (
    RunConfig,
    _load_phase_aligned_warmup_ticks,
    _prediction_path,
    _wait_for_csv_then_kill,
)


def _make_proc(returncode: int | None = None) -> MagicMock:
    """Create a mock Popen-like process."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = 99999
    proc.returncode = returncode
    proc.poll.return_value = returncode
    return proc


def _cfg(tmp_path: Path) -> RunConfig:
    return RunConfig(
        symbols=("EURUSD",),
        start_ts="2026-02-04T00:00:00Z",
        end_ts="2026-02-09T00:00:00Z",
        model_month="2026-02",
        models_dir="models/oco_dukascopy_candidate",
        history_dir=str(tmp_path / "history"),
        predictions_dir=str(tmp_path / "predictions"),
        tick_root=str(tmp_path / "ticks"),
        report_dir="data/analysis/backtest_reconcile",
        api_host="127.0.0.1",
        api_port=8000,
        requested_volume_units=10000,
        tick_batch_size=200,
        order_ttl_seconds=900,
        api_timeout_seconds=60,
        metrics_enabled=True,
        metrics_host="127.0.0.1",
        metrics_port_base=9464,
        risk_enabled=False,
        universe_mode="tolerant",
        ordinal_tolerance=0,
        warmup_ticks=30000,
        lookback_days=31,
        phase_bar_ticks=100,
        tester_completion_timeout_seconds=14400,
    )


def test_prediction_path_prefers_locked_archive(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    locked = Path(cfg.history_dir) / cfg.model_month / "eurusd_oco_locked_predictions.parquet"
    locked.parent.mkdir(parents=True, exist_ok=True)
    locked.write_text("stub")

    assert _prediction_path(cfg, "EURUSD") == str(locked)


def test_prediction_path_falls_back_to_monthly_predictions(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    assert _prediction_path(cfg, "EURUSD") == str(
        Path(cfg.predictions_dir) / "EURUSD_oco_monthly_predictions.parquet"
    )


def test_csv_appears_kills_process_and_returns(tmp_path: Path) -> None:
    """When CSV appears and is non-empty, process is killed and function returns."""
    csv_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
    proc = _make_proc(returncode=None)  # still running

    # Write CSV before calling — simulates it appearing during poll
    csv_path.write_text("event_name,detail\npredict_cycle,foo\n")

    with patch("os.killpg") as mock_kill:
        _wait_for_csv_then_kill(
            proc=proc,
            csv_path=csv_path,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=5.0,
        )
    mock_kill.assert_called_once()


def test_process_exits_nonzero_before_csv_raises(tmp_path: Path) -> None:
    """If process exits with non-zero before CSV appears, CalledProcessError is raised."""
    csv_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
    proc = _make_proc(returncode=1)  # already exited with error

    with pytest.raises(subprocess.CalledProcessError):
        _wait_for_csv_then_kill(
            proc=proc,
            csv_path=csv_path,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=5.0,
        )


def test_process_exits_zero_before_csv_returns_cleanly(tmp_path: Path) -> None:
    """If process exits 0 before CSV appears, function returns without error (graceful exit)."""
    csv_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
    proc = _make_proc(returncode=0)  # exited cleanly

    # Should not raise — clean exit is acceptable even without CSV
    _wait_for_csv_then_kill(
        proc=proc,
        csv_path=csv_path,
        poll_interval_sec=0.05,
        settle_sec=0.0,
        timeout_sec=5.0,
    )


def test_timeout_raises_if_csv_never_appears(tmp_path: Path) -> None:
    """If CSV never appears within timeout, TimeoutError is raised."""
    csv_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
    proc = _make_proc(returncode=None)  # still running, never writes CSV

    with pytest.raises(TimeoutError):
        _wait_for_csv_then_kill(
            proc=proc,
            csv_path=csv_path,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=0.3,  # short timeout for test speed
        )


def test_empty_csv_is_not_treated_as_complete(tmp_path: Path) -> None:
    """An empty CSV file (truncated write) is not treated as completion."""
    csv_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
    csv_path.write_text("")  # empty file
    proc = _make_proc(returncode=None)

    with pytest.raises(TimeoutError):
        _wait_for_csv_then_kill(
            proc=proc,
            csv_path=csv_path,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=0.3,
        )


def test_load_phase_aligned_warmup_ticks_uses_full_history_modulo(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg = RunConfig(
        **{
            **cfg.__dict__,
            "start_ts": "2025-07-07T00:00:00Z",
            "end_ts": "2025-07-08T00:00:00Z",
            "tick_root": str(tmp_path / "ticks"),
            "warmup_ticks": 0,
            "lookback_days": 1,
            "phase_bar_ticks": 4,
        }
    )
    symbol_dir = Path(cfg.tick_root) / "EURUSD"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = symbol_dir / "phase.parquet"

    con = duckdb.connect()
    con.execute(
        """
        COPY (
            SELECT * FROM (VALUES
                (TIMESTAMPTZ '2025-07-05T00:00:01Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:02Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:03Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:04Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:05Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:01Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:02Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:03Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:04Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:05Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:06Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:07Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:08Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:09Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:10Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-07T00:00:01Z', 1.1000, 1.1001)
            ) AS t(timestamp, bid, ask)
        ) TO ? (FORMAT PARQUET)
        """,
        [str(parquet_path)],
    )
    con.close()

    ticks = _load_phase_aligned_warmup_ticks(cfg, "EURUSD")

    assert [tick["timestamp"] for tick in ticks] == [
        "2025-07-06T00:00:08Z",
        "2025-07-06T00:00:09Z",
        "2025-07-06T00:00:10Z",
    ]
