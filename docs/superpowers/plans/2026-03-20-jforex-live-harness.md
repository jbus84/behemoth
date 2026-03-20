# JForex Live Session Harness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `scripts/run_jforex_live.py` and a `make jforex-live` Makefile target that start the Python API in live governance mode and the JForexLiveRunner for all 6 symbols simultaneously, monitoring both processes and shutting down cleanly on failure or Ctrl+C.

**Architecture:** A Python orchestration script modelled on `scripts/run_jforex_dukascopy_matrix.py`, but with a single API instance and a single Java process (all 6 symbols at once), an indefinite monitor loop instead of a CSV-poll completion check, and live-mode environment variables (no historical prediction overrides). A `make jforex-live` Makefile target wraps it.

**Tech Stack:** Python 3 (stdlib only: `argparse`, `subprocess`, `signal`, `os`, `time`, `urllib`), `uvicorn`, `mise exec -- gradle`.

---

## File Map

| File | Change |
|------|--------|
| `scripts/run_jforex_live.py` | Create — live session orchestrator |
| `Makefile` | Add `jforex-live` target; add `jforex-live` to `.PHONY` line (line 16); add help entry |

---

## Task 1: Create `scripts/run_jforex_live.py`

**Files:**
- Create: `scripts/run_jforex_live.py`

Reference file for patterns: `scripts/run_jforex_dukascopy_matrix.py`

- [ ] **Step 1: Create the script**

Create `scripts/run_jforex_live.py` with the following complete contents:

```python
#!/usr/bin/env python3
"""Run the Dukascopy JForex live/demo session for all symbols simultaneously.

Starts the Python prediction API in live governance mode, waits for it to
become healthy, then starts the JForexLiveRunner (IClient-based) subscribing
to all instruments in a single session. Monitors both processes; if either
exits unexpectedly the other is killed and the script exits non-zero.
SIGINT (Ctrl+C) triggers a clean shutdown of both.

Requires BEHEMOTH_JFOREX_JNLP_URI, BEHEMOTH_JFOREX_USERNAME, and
BEHEMOTH_JFOREX_PASSWORD in the environment (typically loaded from .env).
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_MODELS_DIR = "models/oco_dukascopy_candidate"
DEFAULT_HISTORY_DIR = "configs/research/governance/oco_history_dukascopy_candidate"
DEFAULT_API_PORT = 8000


@dataclass(frozen=True)
class RunConfig:
    symbols: tuple[str, ...]
    models_dir: str
    history_dir: str
    report_dir: str
    api_host: str
    api_port: int
    requested_volume_units: int
    tick_batch_size: int
    order_ttl_seconds: int
    api_timeout_seconds: int
    metrics_enabled: bool
    metrics_host: str
    metrics_port: int


def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--history-dir", default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--report-dir", default="data/analysis/backtest_reconcile")
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--requested-volume-units", type=int, default=10000)
    parser.add_argument("--tick-batch-size", type=int, default=200)
    parser.add_argument("--order-ttl-seconds", type=int, default=900)
    parser.add_argument("--api-timeout-seconds", type=int, default=60)
    parser.add_argument("--metrics-enabled", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--metrics-host", default="127.0.0.1")
    parser.add_argument("--metrics-port", type=int, default=9464)
    args = parser.parse_args()
    symbols = tuple(s.strip().upper() for s in str(args.symbols).split(",") if s.strip())
    if not symbols:
        raise SystemExit("No symbols provided")
    return RunConfig(
        symbols=symbols,
        models_dir=args.models_dir,
        history_dir=args.history_dir,
        report_dir=args.report_dir,
        api_host=args.api_host,
        api_port=args.api_port,
        requested_volume_units=args.requested_volume_units,
        tick_batch_size=args.tick_batch_size,
        order_ttl_seconds=args.order_ttl_seconds,
        api_timeout_seconds=args.api_timeout_seconds,
        metrics_enabled=bool(args.metrics_enabled),
        metrics_host=args.metrics_host,
        metrics_port=args.metrics_port,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _poll_health(proc: subprocess.Popen[str], base_url: str, timeout_sec: float) -> None:
    deadline = time.time() + timeout_sec
    last_error: str | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"API process exited before becoming healthy: {proc.returncode}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2.0) as response:
                if response.status == 200:
                    return
                last_error = f"status={response.status}"
        except urllib.error.URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"API did not become healthy within {timeout_sec:.0f}s: {last_error}")


def _start_api(cfg: RunConfig) -> subprocess.Popen[str]:
    state_db_path = _repo_root() / cfg.report_dir / "runtime" / "live_state.db"
    state_db_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "UV_CACHE_DIR": ".uv_cache",
            "BEHEMOTH_GOVERNANCE_MODE": "live",
            "BEHEMOTH_GOVERNANCE_HISTORY_DIR": cfg.history_dir,
            "BEHEMOTH_MODELS_DIR": cfg.models_dir,
            "BEHEMOTH_STATE_DB": str(state_db_path),
        }
    )
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.behemoth.api.server:app",
        "--host",
        cfg.api_host,
        "--port",
        str(cfg.api_port),
    ]
    log_path = _repo_root() / "logs" / "api_live.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w")  # noqa: SIM115 — kept open for subprocess lifetime
    return subprocess.Popen(
        cmd,
        cwd=_repo_root(),
        env=env,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )


def _start_live_runner(cfg: RunConfig) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update(
        {
            "BEHEMOTH_JFOREX_INSTRUMENTS": ",".join(cfg.symbols),
            "BEHEMOTH_JFOREX_RISK_ENABLED": "true",
            "BEHEMOTH_JFOREX_NATIVE_OCO_ENABLED": "false",
            "BEHEMOTH_JFOREX_RUN_ID": "jforex_live",
            "BEHEMOTH_JFOREX_REPORT_DIR": cfg.report_dir,
            "BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS": str(cfg.requested_volume_units),
            "BEHEMOTH_JFOREX_TICK_BATCH_SIZE": str(cfg.tick_batch_size),
            "BEHEMOTH_JFOREX_ORDER_TTL_SECONDS": str(cfg.order_ttl_seconds),
            "BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS": str(cfg.api_timeout_seconds),
            "BEHEMOTH_JFOREX_METRICS_ENABLED": str(cfg.metrics_enabled).lower(),
            "BEHEMOTH_JFOREX_METRICS_HOST": cfg.metrics_host,
            "BEHEMOTH_JFOREX_METRICS_PORT": str(cfg.metrics_port),
            "BEHEMOTH_API_BASE_URI": f"http://{cfg.api_host}:{cfg.api_port}",
        }
    )
    return subprocess.Popen(
        ["mise", "exec", "--", "gradle", ":jforex-adapter:runJForexLive"],
        cwd=_repo_root(),
        env=env,
        start_new_session=True,
    )


def _stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(timeout=10)


def main() -> None:
    cfg = _parse_args()

    # Pre-flight: validate credentials before starting any process
    for required in ("BEHEMOTH_JFOREX_JNLP_URI", "BEHEMOTH_JFOREX_USERNAME", "BEHEMOTH_JFOREX_PASSWORD"):
        if not os.environ.get(required):
            raise SystemExit(f"Missing required env var: {required}")

    # Delete shared OCO state file so the lifecycle registry starts clean
    state_json = _repo_root() / cfg.report_dir / "runtime" / "active_oco_state.json"
    if state_json.exists():
        state_json.unlink()

    print("[jforex-live] starting API", flush=True)
    api_proc = _start_api(cfg)
    java_proc: subprocess.Popen[str] | None = None

    def _shutdown(signum: int, frame: object) -> None:
        print("\n[jforex-live] shutting down", flush=True)
        if java_proc is not None:
            _stop_process(java_proc)
        _stop_process(api_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
        print("[jforex-live] API healthy — starting live runner", flush=True)
        java_proc = _start_live_runner(cfg)
        print(f"[jforex-live] running (symbols={','.join(cfg.symbols)})", flush=True)

        # Monitor loop: exit non-zero if either process dies unexpectedly
        while True:
            time.sleep(5)
            if api_proc.poll() is not None:
                print(
                    f"[jforex-live] API exited unexpectedly (rc={api_proc.returncode})",
                    file=sys.stderr,
                    flush=True,
                )
                _stop_process(java_proc)
                raise SystemExit(1)
            if java_proc.poll() is not None:
                print(
                    f"[jforex-live] live runner exited unexpectedly (rc={java_proc.returncode})",
                    file=sys.stderr,
                    flush=True,
                )
                _stop_process(api_proc)
                raise SystemExit(1)

    except SystemExit:
        raise
    except Exception as exc:
        print(f"[jforex-live] failed: {exc}", file=sys.stderr, flush=True)
        if java_proc is not None:
            _stop_process(java_proc)
        _stop_process(api_proc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script is syntactically valid**

```bash
UV_CACHE_DIR=.uv_cache uv run python -c "import py_compile; py_compile.compile('scripts/run_jforex_live.py', doraise=True); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify `--help` works**

```bash
UV_CACHE_DIR=.uv_cache uv run python scripts/run_jforex_live.py --help
```

Expected: usage output listing `--symbols`, `--api-port`, `--report-dir`, `--metrics-port`, etc.

- [ ] **Step 4: Verify pre-flight check works without credentials**

```bash
env -i HOME=$HOME PATH=$PATH UV_CACHE_DIR=.uv_cache uv run python scripts/run_jforex_live.py 2>&1
```

Expected: exits immediately with `Missing required env var: BEHEMOTH_JFOREX_JNLP_URI` (no processes started).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_jforex_live.py
git commit -m "feat: add run_jforex_live.py live session orchestrator"
```

---

## Task 2: Add `jforex-live` Makefile target

**Files:**
- Modify: `Makefile` (line 16 for `.PHONY`, after line 165 for the target, after line 730 for the help entry)

- [ ] **Step 1: Add `jforex-live` to the `.PHONY` line**

The `.PHONY` line is line 16. It currently ends with `reconcile-account-risk-reservations`. Add `jforex-live` to the end of that line:

Find:
```
.PHONY: test test-java docs ... reconcile-account-risk-reservations
```

Add `jforex-live` to the end (it's one long line — append before the newline):

The exact old string to replace is the end of the `.PHONY` line:
```
 reconcile-account-risk-reservations
```

Replace with:
```
 reconcile-account-risk-reservations jforex-live
```

- [ ] **Step 2: Add the `jforex-live` target after `jforex-dukascopy-matrix`**

The `jforex-dukascopy-matrix` target ends at line 165 (the `--metrics-port-base` line followed by a blank line). Insert the new target after that blank line, before `jforex-outcome-parity`:

Find this exact block in the Makefile:
```
		--metrics-port-base $(or $(METRICS_PORT_BASE),9464)

jforex-outcome-parity:
```

Replace with:
```
		--metrics-port-base $(or $(METRICS_PORT_BASE),9464)

jforex-live:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_jforex_live.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
		--api-port $(or $(API_PORT),8000) \
		--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),200) \
		--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
		--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
		--metrics-port $(or $(METRICS_PORT),9464)

jforex-outcome-parity:
```

**Important:** Makefile recipes must use a tab character (not spaces) for indentation. Each line starting with `UV_CACHE_DIR=...` and the continuation lines must be indented with a real tab.

- [ ] **Step 3: Add the help entry**

Find the help entry for `jforex-dukascopy-matrix` (near line 729):
```
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage14-jforex-cert" "Build Stage 14 JForex certification summary, checks, report, and snapshot"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "full-stage14-cert" "Run outcome-parity → local-jforex-cert → stage14-jforex-cert in order (monthly recert command)"
```

Add a new entry after the `full-stage14-cert` line:
```
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-live" "Start the JForex live/demo session for all symbols (IClient-based, live governance mode)"
```

- [ ] **Step 4: Verify `make --dry-run jforex-live` parses correctly**

```bash
make --dry-run jforex-live 2>&1 | head -5
```

Expected: shows the `uv run python scripts/run_jforex_live.py ...` command without actually running it. No `missing separator` or parse errors.

- [ ] **Step 5: Verify `make help` shows the new target**

```bash
make help 2>&1 | grep jforex-live
```

Expected: one line showing `jforex-live` with its description.

- [ ] **Step 6: Commit**

```bash
git add Makefile
git commit -m "feat: add jforex-live Makefile target for live/demo session"
```

---

## Manual verification checklist (requires Dukascopy credentials)

These steps cannot be automated. Run them once you have credentials available:

1. `make jforex-live` → confirm `logs/api_live.log` contains `Application startup complete`
2. Confirm Gradle stdout contains `subscribed` for all 6 instruments
3. Kill the API process (`kill <pid>`) → confirm Java exits and script exits non-zero
4. Kill the Java/Gradle process → confirm API exits and script exits non-zero
5. Press Ctrl+C → confirm both processes shut down cleanly, script exits 0
6. Run without `BEHEMOTH_JFOREX_JNLP_URI` → confirm immediate error, no processes started
