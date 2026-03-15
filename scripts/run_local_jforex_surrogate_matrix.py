#!/usr/bin/env python3
"""Run the local JForex surrogate sequentially across a symbol set."""

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
DEFAULT_START = "2025-07-07T00:00:00Z"
DEFAULT_END = "2025-07-09T00:00:00Z"
DEFAULT_MODELS_DIR = "models/oco_dukascopy_candidate"
DEFAULT_HISTORY_DIR = "configs/research/governance/oco_history_dukascopy_candidate"
DEFAULT_PREDICTIONS_DIR = "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap"
DEFAULT_TICK_ROOT = "/Users/danielfisher/Desktop/dukascopy_ticks"
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
    tick_root: str
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
    warmup_ticks: int
    lookback_days: int
    phase_bar_ticks: int
    starting_balance: int
    risk_enabled: bool


def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--start-ts", default=DEFAULT_START)
    parser.add_argument("--end-ts", default=DEFAULT_END)
    parser.add_argument("--model-month", default="2025-07")
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--history-dir", default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--predictions-dir", default=DEFAULT_PREDICTIONS_DIR)
    parser.add_argument("--tick-root", default=DEFAULT_TICK_ROOT)
    parser.add_argument("--report-dir", default="data/analysis/backtest_reconcile")
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--requested-volume-units", type=int, default=10000)
    parser.add_argument("--tick-batch-size", type=int, default=16)
    parser.add_argument("--order-ttl-seconds", type=int, default=900)
    parser.add_argument("--api-timeout-seconds", type=int, default=60)
    parser.add_argument("--metrics-enabled", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--metrics-host", default="127.0.0.1")
    parser.add_argument("--metrics-port-base", type=int, default=9465)
    parser.add_argument("--warmup-ticks", type=int, default=30000)
    parser.add_argument("--lookback-days", type=int, default=31)
    parser.add_argument("--phase-bar-ticks", type=int, default=100)
    parser.add_argument("--starting-balance", type=int, default=100000)
    parser.add_argument("--risk-enabled", action=argparse.BooleanOptionalAction, default=False)
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
        tick_root=args.tick_root,
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
        warmup_ticks=args.warmup_ticks,
        lookback_days=args.lookback_days,
        phase_bar_ticks=args.phase_bar_ticks,
        starting_balance=args.starting_balance,
        risk_enabled=bool(args.risk_enabled),
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
    return _repo_root() / cfg.report_dir / "runtime" / f"{symbol.lower()}_local_jforex_state.db"


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
            "BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE": "tolerant",
            "BEHEMOTH_HISTORICAL_PREDICTION_PAYLOAD_MODE": "locked",
            "BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC": "60",
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
    return subprocess.Popen(
        cmd,
        cwd=_repo_root(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
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


def _run_surrogate(cfg: RunConfig, symbol: str, metrics_port: int) -> None:
    env = os.environ.copy()
    env.update(
        {
            "BEHEMOTH_LOCAL_JFOREX_INSTRUMENTS": symbol,
            "BEHEMOTH_LOCAL_JFOREX_START_UTC": cfg.start_ts,
            "BEHEMOTH_LOCAL_JFOREX_END_UTC": cfg.end_ts,
            "BEHEMOTH_LOCAL_JFOREX_TICK_ROOT": cfg.tick_root,
            "BEHEMOTH_LOCAL_JFOREX_REPORT_DIR": cfg.report_dir,
            "BEHEMOTH_LOCAL_JFOREX_RUN_ID": f"local_jforex_surrogate_{symbol.lower()}",
            "BEHEMOTH_LOCAL_JFOREX_RISK_ENABLED": str(cfg.risk_enabled).lower(),
            "BEHEMOTH_LOCAL_JFOREX_REQUESTED_VOLUME_UNITS": str(cfg.requested_volume_units),
            "BEHEMOTH_LOCAL_JFOREX_TICK_BATCH_SIZE": str(cfg.tick_batch_size),
            "BEHEMOTH_LOCAL_JFOREX_ORDER_TTL_SECONDS": str(cfg.order_ttl_seconds),
            "BEHEMOTH_LOCAL_JFOREX_API_TIMEOUT_SECONDS": str(cfg.api_timeout_seconds),
            "BEHEMOTH_LOCAL_JFOREX_METRICS_ENABLED": str(cfg.metrics_enabled).lower(),
            "BEHEMOTH_LOCAL_JFOREX_METRICS_HOST": cfg.metrics_host,
            "BEHEMOTH_LOCAL_JFOREX_METRICS_PORT": str(metrics_port),
            "BEHEMOTH_LOCAL_JFOREX_WARMUP_TICKS": str(cfg.warmup_ticks),
            "BEHEMOTH_LOCAL_JFOREX_LOOKBACK_DAYS": str(cfg.lookback_days),
            "BEHEMOTH_LOCAL_JFOREX_PHASE_BAR_TICKS": str(cfg.phase_bar_ticks),
            "BEHEMOTH_LOCAL_JFOREX_STARTING_BALANCE": str(cfg.starting_balance),
            "BEHEMOTH_API_BASE_URI": f"http://{cfg.api_host}:{cfg.api_port}",
        }
    )
    subprocess.run(
        ["mise", "exec", "--", "gradle", ":jforex-adapter:runLocalJForexTester"],
        cwd=_repo_root(),
        env=env,
        check=True,
    )


def main() -> None:
    cfg = _parse_args()
    failures: list[str] = []
    for index, symbol in enumerate(cfg.symbols):
        metrics_port = cfg.metrics_port_base + index
        print(f"[local-jforex] {symbol}: starting API", flush=True)
        api_proc = _start_api(cfg, symbol)
        try:
            _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
            print(f"[local-jforex] {symbol}: running surrogate", flush=True)
            _run_surrogate(cfg, symbol, metrics_port)
            print(f"[local-jforex] {symbol}: complete", flush=True)
        except Exception as exc:  # pragma: no cover - orchestration path
            failures.append(f"{symbol}: {exc}")
            print(f"[local-jforex] {symbol}: failed: {exc}", file=sys.stderr, flush=True)
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
