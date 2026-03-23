# JForex Tester Shutdown Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blocking `subprocess.run` in `_run_jforex_tester` with a poll-and-kill loop that terminates the Gradle/Java process as soon as the output CSV appears on disk, eliminating the multi-hour JVM shutdown hang.

**Architecture:** The JForex tester writes `{SYMBOL}_jforex_runtime_events.csv` to the report directory when `onStop` fires — this is the signal that useful work is done. We replace `subprocess.run` with `subprocess.Popen` and a poll loop that checks for the CSV every 5 seconds. Once found (and non-empty, with a 5-second settle delay to flush the file), we kill the process group. If the process exits on its own before the file appears (error path), we raise normally. A configurable `--tester-completion-timeout-seconds` (default 14400 = 4 hours) guards against infinite hangs.

**Tech Stack:** Python 3.11+, `subprocess`, `pathlib`, `pytest`, `unittest.mock`

---

## File Map

- **Modify:** `scripts/run_jforex_dukascopy_matrix.py` — replace `_run_jforex_tester` internals; add `--tester-completion-timeout-seconds` arg and field to `RunConfig`
- **Create:** `tests/test_run_jforex_dukascopy_matrix.py` — unit tests for the new poll-and-kill logic

---

### Task 1: Tests for poll-and-kill tester logic

**Files:**
- Create: `tests/test_run_jforex_dukascopy_matrix.py`

Context: There are no existing tests for this script. The key behaviour to test:
1. CSV appears → process killed → function returns successfully
2. Process exits non-zero before CSV appears → `CalledProcessError` raised
3. Timeout exceeded before CSV appears → `TimeoutError` raised

The functions we need to import from the script:
- `_run_jforex_tester(cfg, symbol, metrics_port)` — but this is hard to unit-test directly because it spawns Gradle
- Instead, extract the inner poll loop into a testable helper: `_wait_for_csv_then_kill(proc, csv_path, poll_interval_sec, settle_sec, timeout_sec)`

We'll write tests for `_wait_for_csv_then_kill` first (TDD), then implement it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_jforex_dukascopy_matrix.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielfisher/repositories/behemoth
uv run pytest tests/test_run_jforex_dukascopy_matrix.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name '_wait_for_csv_then_kill'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_run_jforex_dukascopy_matrix.py
git commit -m "test: add failing tests for JForex tester poll-and-kill shutdown"
```

---

### Task 2: Implement poll-and-kill logic

**Files:**
- Modify: `scripts/run_jforex_dukascopy_matrix.py`

Changes needed:
1. Add `tester_completion_timeout_seconds: int` field to `RunConfig`
2. Add `--tester-completion-timeout-seconds` argparse argument (default 14400)
3. Extract `_wait_for_csv_then_kill(proc, csv_path, poll_interval_sec, settle_sec, timeout_sec)` as a standalone function
4. Rewrite `_run_jforex_tester` to use `Popen` + `_wait_for_csv_then_kill`

The output CSV path for a symbol is: `{report_dir}/{SYMBOL}_jforex_runtime_events.csv`
This matches what `JForexTesterRunner.java` writes (check: `data/analysis/backtest_reconcile/EURUSD_jforex_runtime_events.csv` — confirmed).

- [ ] **Step 1: Add `tester_completion_timeout_seconds` to `RunConfig` and argparse**

In `scripts/run_jforex_dukascopy_matrix.py`:

In the `RunConfig` dataclass, add after the `ordinal_tolerance` field:
```python
    tester_completion_timeout_seconds: int
```

In `_parse_args`, add after the `--ordinal-tolerance` argument:
```python
    parser.add_argument(
        "--tester-completion-timeout-seconds",
        type=int,
        default=14400,
        help="Max seconds to wait for JForex tester CSV output before killing (default: 14400 = 4h)",
    )
```

In the `RunConfig(...)` constructor call inside `_parse_args`, add after `ordinal_tolerance=int(args.ordinal_tolerance)`:
```python
        tester_completion_timeout_seconds=args.tester_completion_timeout_seconds,
```

- [ ] **Step 2: Run existing tests to confirm no regressions yet**

```bash
uv run pytest tests/test_run_jforex_dukascopy_matrix.py -v 2>&1 | head -20
```

Expected: same import error (no change yet to functions)

- [ ] **Step 3: Add `_wait_for_csv_then_kill` function**

Add after `_read_process_tail` (after line 204), before `_run_jforex_tester`:

```python
def _wait_for_csv_then_kill(
    proc: subprocess.Popen,
    csv_path: Path,
    poll_interval_sec: float = 5.0,
    settle_sec: float = 5.0,
    timeout_sec: float = 14400.0,
) -> None:
    """Poll until the output CSV exists and is non-empty, then kill the process.

    The JForex framework hangs in thread cleanup after onStop writes the CSV.
    Once the CSV is present and non-empty we have all the data we need, so we
    kill the process group rather than waiting for the JVM to exit cleanly.

    Args:
        proc: The running Gradle/Java subprocess.
        csv_path: Path where the strategy writes its runtime events CSV on completion.
        poll_interval_sec: How often to check for the CSV (seconds).
        settle_sec: Extra wait after CSV appears before killing, to let the file flush.
        timeout_sec: Maximum total wait time before raising TimeoutError.

    Raises:
        subprocess.CalledProcessError: If process exits non-zero before CSV appears.
        TimeoutError: If CSV does not appear within timeout_sec.
    """
    deadline = time.monotonic() + timeout_sec
    while True:
        rc = proc.poll()
        if rc is not None:
            if rc == 0:
                return  # clean exit — accept even without CSV
            raise subprocess.CalledProcessError(rc, "JForexTesterRunner")

        if csv_path.exists() and csv_path.stat().st_size > 0:
            if settle_sec > 0:
                time.sleep(settle_sec)
            try:
                # start_new_session=True makes the process a session/group leader,
                # so its PGID == PID. os.killpg takes a PGID.
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return  # already gone
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # JVM ignored SIGTERM — escalate to SIGKILL
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            return

        if time.monotonic() >= deadline:
            # Kill the process before raising so it doesn't become an orphan.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            raise TimeoutError(
                f"JForex tester did not produce {csv_path} within {timeout_sec:.0f}s"
            )
        time.sleep(poll_interval_sec)
```

- [ ] **Step 4: Rewrite `_run_jforex_tester` to use `Popen` + `_wait_for_csv_then_kill`**

Replace the entire `_run_jforex_tester` function with:

```python
def _run_jforex_tester(cfg: RunConfig, symbol: str, metrics_port: int) -> None:
    """Run the real Dukascopy JForex tester for a single symbol."""
    for required in ("BEHEMOTH_JFOREX_JNLP_URI", "BEHEMOTH_JFOREX_USERNAME", "BEHEMOTH_JFOREX_PASSWORD"):
        if not os.environ.get(required):
            raise RuntimeError(f"Missing required env var: {required}")

    env = os.environ.copy()
    env.update(
        {
            "BEHEMOTH_JFOREX_INSTRUMENTS": symbol,
            "BEHEMOTH_JFOREX_START_UTC": cfg.start_ts,
            "BEHEMOTH_JFOREX_END_UTC": cfg.end_ts,
            "BEHEMOTH_JFOREX_REPORT_DIR": cfg.report_dir,
            "BEHEMOTH_JFOREX_RUN_ID": f"jforex_dukascopy_{symbol.lower()}",
            "BEHEMOTH_JFOREX_RISK_ENABLED": str(cfg.risk_enabled).lower(),
            "BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS": str(cfg.requested_volume_units),
            "BEHEMOTH_JFOREX_TICK_BATCH_SIZE": str(cfg.tick_batch_size),
            "BEHEMOTH_JFOREX_ORDER_TTL_SECONDS": str(cfg.order_ttl_seconds),
            "BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS": str(cfg.api_timeout_seconds),
            "BEHEMOTH_JFOREX_METRICS_ENABLED": str(cfg.metrics_enabled).lower(),
            "BEHEMOTH_JFOREX_METRICS_HOST": cfg.metrics_host,
            "BEHEMOTH_JFOREX_METRICS_PORT": str(metrics_port),
            "BEHEMOTH_API_BASE_URI": f"http://{cfg.api_host}:{cfg.api_port}",
        }
    )
    csv_path = _repo_root() / cfg.report_dir / f"{symbol}_jforex_runtime_events.csv"
    # Delete any stale CSV from a previous run so the poll loop doesn't
    # mistake old output for fresh completion.
    if csv_path.exists():
        csv_path.unlink()

    proc = subprocess.Popen(
        ["mise", "exec", "--", "gradle", ":jforex-adapter:runJForexTester"],
        cwd=_repo_root(),
        env=env,
        start_new_session=True,
    )
    _wait_for_csv_then_kill(
        proc=proc,
        csv_path=csv_path,
        poll_interval_sec=5.0,
        settle_sec=5.0,
        timeout_sec=float(cfg.tester_completion_timeout_seconds),
    )
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/test_run_jforex_dukascopy_matrix.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_jforex_dukascopy_matrix.py tests/test_run_jforex_dukascopy_matrix.py
git commit -m "fix: kill JForex tester on CSV completion instead of waiting for JVM shutdown

The JForex framework spawns non-daemon threads that never exit after onStop,
causing the process to hang for hours after completing useful work. Poll for
the output CSV, then kill the process group once it appears and is non-empty."
```

---

## Verification

After the commit, the current GBPUSD run will still use the old code. To verify the fix works end-to-end, the next symbol after GBPUSD completes should terminate within ~30 seconds of writing its CSV rather than hanging for hours.

To monitor: watch for `[jforex-dukascopy] USDJPY: complete` appearing in the log shortly after the CSV is written rather than hours later.
