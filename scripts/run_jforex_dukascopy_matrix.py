#!/usr/bin/env python3
"""Run the real Dukascopy JForex tester sequentially across a symbol set.

Like run_local_jforex_surrogate_matrix.py but uses the real Dukascopy broker
(JForexTesterRunner) instead of the local parquet surrogate. Dukascopy streams
ticks directly — no parquet loading overhead. HTTP tick-batching to the Python
API still occurs; use a large --tick-batch-size (256+) to minimise round-trips.

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
DEFAULT_START = "2025-07-06T00:00:00Z"
DEFAULT_END = "2025-07-09T00:00:00Z"
DEFAULT_MODELS_DIR = "models/oco_dukascopy_candidate"
DEFAULT_HISTORY_DIR = "configs/research/governance/oco_history_dukascopy_candidate"
DEFAULT_PREDICTIONS_DIR = "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap"
DEFAULT_API_PORT = 8000


@dataclass(frozen=True)
class RunConfig:
    symbols: tuple[str, ...]
    start_ts: str
    end_ts: str
    model_month: str
    models_dir: str
    history_dir: str
    predictions_dir: str
    report_dir: str
    api_host: str
    api_port: int
    requested_volume_units: int
    tick_batch_size: int
    order_ttl_seconds: int
    api_timeout_seconds: int
    metrics_enabled: bool
    metrics_host: str
    metrics_port_base: int
    risk_enabled: bool
    universe_mode: str
    ordinal_tolerance: int
    tester_completion_timeout_seconds: int


def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--start-ts", default=DEFAULT_START)
    parser.add_argument("--end-ts", default=DEFAULT_END)
    parser.add_argument("--model-month", default="2025-07")
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--history-dir", default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--predictions-dir", default=DEFAULT_PREDICTIONS_DIR)
    parser.add_argument("--report-dir", default="data/analysis/backtest_reconcile")
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--requested-volume-units", type=int, default=10000)
    parser.add_argument("--tick-batch-size", type=int, default=200)
    parser.add_argument("--order-ttl-seconds", type=int, default=900)
    parser.add_argument("--api-timeout-seconds", type=int, default=60)
    parser.add_argument("--metrics-enabled", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--metrics-host", default="127.0.0.1")
    parser.add_argument("--metrics-port-base", type=int, default=9464)
    parser.add_argument("--risk-enabled", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--universe-mode", choices=["tolerant", "nearest", "ordinal"], default="tolerant")
    parser.add_argument("--ordinal-tolerance", type=int, default=0)
    parser.add_argument(
        "--tester-completion-timeout-seconds",
        type=int,
        default=14400,
        help="Max seconds to wait for JForex tester CSV output before killing (default: 14400 = 4h)",
    )
    args = parser.parse_args()
    symbols = tuple(s.strip().upper() for s in str(args.symbols).split(",") if s.strip())
    if not symbols:
        raise SystemExit("No symbols provided")
    return RunConfig(
        symbols=symbols,
        start_ts=args.start_ts,
        end_ts=args.end_ts,
        model_month=args.model_month,
        models_dir=args.models_dir,
        history_dir=args.history_dir,
        predictions_dir=args.predictions_dir,
        report_dir=args.report_dir,
        api_host=args.api_host,
        api_port=args.api_port,
        requested_volume_units=args.requested_volume_units,
        tick_batch_size=args.tick_batch_size,
        order_ttl_seconds=args.order_ttl_seconds,
        api_timeout_seconds=args.api_timeout_seconds,
        metrics_enabled=bool(args.metrics_enabled),
        metrics_host=args.metrics_host,
        metrics_port_base=args.metrics_port_base,
        risk_enabled=bool(args.risk_enabled),
        universe_mode=args.universe_mode,
        ordinal_tolerance=int(args.ordinal_tolerance),
        tester_completion_timeout_seconds=args.tester_completion_timeout_seconds,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _poll_health(proc: subprocess.Popen[str], base_url: str, timeout_sec: float) -> None:
    deadline = time.time() + timeout_sec
    last_error: str | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = _read_process_tail(proc)
            raise RuntimeError(f"API process exited before becoming healthy: {tail or proc.returncode}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2.0) as response:
                if response.status == 200:
                    return
                last_error = f"status={response.status}"
        except urllib.error.URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"API did not become healthy within {timeout_sec:.0f}s: {last_error}")


def _prediction_path(cfg: RunConfig, symbol: str) -> str:
    return str(Path(cfg.predictions_dir) / f"{symbol}_oco_monthly_predictions.parquet")


def _state_db_path(cfg: RunConfig, symbol: str) -> Path:
    return _repo_root() / cfg.report_dir / "runtime" / f"{symbol.lower()}_jforex_dukascopy_state.db"


def _start_api(cfg: RunConfig, symbol: str) -> subprocess.Popen[str]:
    state_db_path = _state_db_path(cfg, symbol)
    state_db_path.parent.mkdir(parents=True, exist_ok=True)
    if state_db_path.exists():
        state_db_path.unlink()
    env = os.environ.copy()
    env.update(
        {
            "UV_CACHE_DIR": ".uv_cache",
            "BEHEMOTH_GOVERNANCE_MODE": "historical_auto",
            "BEHEMOTH_HISTORICAL_PREFLIGHT_MODE": "warn",
            "BEHEMOTH_GOVERNANCE_HISTORY_DIR": cfg.history_dir,
            "BEHEMOTH_MODELS_DIR": cfg.models_dir,
            "BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE": cfg.universe_mode,
            "BEHEMOTH_HISTORICAL_PREDICTION_ORDINAL_TOLERANCE": str(cfg.ordinal_tolerance),
            "BEHEMOTH_HISTORICAL_PREDICTION_PAYLOAD_MODE": "locked",
            "BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC": "120",
            "BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE": _prediction_path(cfg, symbol),
            "BEHEMOTH_FORCE_MODEL_MONTH": cfg.model_month,
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
    log_path = _repo_root() / "logs" / f"api_{symbol.lower()}.log"
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


def _read_process_tail(proc: subprocess.Popen[str], max_lines: int = 50) -> str:
    if proc.poll() is None:
        return ""
    if proc.stdout is None:
        return ""
    lines = proc.stdout.read().splitlines()
    return "\n".join(lines[-max_lines:])


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
    # Delete the shared OCO state file so the strategy starts with a clean lifecycle
    # registry. The real JForex tester uses a fixed non-symbol-scoped path; without
    # this deletion, groups from a previous symbol's run block new order submissions
    # (LocalJForexTesterRunner explicitly deletes its own state file — match that).
    state_json = _repo_root() / cfg.report_dir / "runtime" / "active_oco_state.json"
    if state_json.exists():
        state_json.unlink()

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


def main() -> None:
    cfg = _parse_args()
    failures: list[str] = []
    for index, symbol in enumerate(cfg.symbols):
        metrics_port = cfg.metrics_port_base + index
        print(f"[jforex-dukascopy] {symbol}: starting API", flush=True)
        api_proc = _start_api(cfg, symbol)
        try:
            _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
            print(f"[jforex-dukascopy] {symbol}: running JForex tester", flush=True)
            _run_jforex_tester(cfg, symbol, metrics_port)
            print(f"[jforex-dukascopy] {symbol}: complete", flush=True)
        except Exception as exc:
            failures.append(f"{symbol}: {exc}")
            print(f"[jforex-dukascopy] {symbol}: failed: {exc}", file=sys.stderr, flush=True)
        finally:
            _stop_process(api_proc)
            tail = _read_process_tail(api_proc)
            if tail:
                print(tail, file=sys.stderr, flush=True)

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()
