"""Tests for JForex dukascopy matrix runner — poll-and-kill shutdown logic."""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.run_jforex_dukascopy_matrix import _wait_for_csv_then_kill


def _make_proc(returncode: int | None = None) -> MagicMock:
    """Create a mock Popen-like process."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = 99999
    proc.returncode = returncode
    proc.poll.return_value = returncode
    return proc


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
