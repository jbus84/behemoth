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


def _seed_audit_history(symbols: list[str], base_url: str, days_back: int = 20) -> None:
    """Call /state/seed_audit_history to populate audit_logs from Dukascopy parquets.

    This seeds the rolling threshold distribution so that get_rolling_threshold()
    returns a calibrated value on the first live predict call.
    Must be called after _poll_health() but before time.sleep(30) / _warmup_symbols().
    """
    import requests

    print(f"[seed] seeding audit_logs from last {days_back} days of parquet data...", flush=True)
    try:
        r = requests.post(
            f"{base_url}/state/seed_audit_history",
            json={"symbols": symbols, "days_back": days_back, "run_id": "audit_seed"},
            timeout=600,  # replay can take several minutes for 20 days × 6 symbols
        )
        body = r.json()
        if body.get("ok"):
            print(f"[seed] done — total events: {body['total_events']}", flush=True)
            for sym, count in body.get("events_by_symbol", {}).items():
                print(f"[seed]   {sym}: {count} events", flush=True)
        else:
            print(f"[seed] WARNING: unexpected response: {body}", flush=True)
    except Exception as exc:
        print(f"[seed] WARNING: seed_audit_history failed: {exc}", flush=True)
        print("[seed] continuing without historical seed — first predict calls may block", flush=True)


def _warmup_symbols(symbols: list[str], base_url: str, timeout_sec: float = 60.0) -> None:
    """Call /predict/warmup for each symbol to seed audit_logs.

    Retries until all symbols return audit_events_written > 0, or timeout.
    This must be called AFTER backfill has populated tick_bars.
    """
    import requests

    deadline = time.monotonic() + timeout_sec
    pending = list(symbols)
    while pending and time.monotonic() < deadline:
        still_pending = []
        for sym in pending:
            try:
                r = requests.post(
                    f"{base_url}/predict/warmup",
                    json={"symbol": sym, "run_id": "warmup"},
                    timeout=10,
                )
                body = r.json()
                written = body.get("audit_events_written", 0)
                if written > 0:
                    print(f"[warmup] {sym}: {written} audit events seeded", flush=True)
                else:
                    still_pending.append(sym)
                    print(f"[warmup] {sym}: 0 events (bars not ready yet), retrying...", flush=True)
            except Exception as exc:
                still_pending.append(sym)
                print(f"[warmup] {sym}: error {exc}, retrying...", flush=True)
        pending = still_pending
        if pending:
            time.sleep(5)
    if pending:
        print(f"[warmup] WARNING: warmup incomplete for {pending} after {timeout_sec}s", flush=True)


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
        print("[jforex-live] API healthy", flush=True)
        _seed_audit_history(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
        print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
        # Give JForex time to complete initial backfill before warmup scoring
        time.sleep(30)
        _warmup_symbols(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
        print("[jforex-live] warmup complete, starting JForex runner", flush=True)
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
