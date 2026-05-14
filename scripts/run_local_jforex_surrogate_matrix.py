#!/usr/bin/env python3
"""Run the local JForex surrogate sequentially across a symbol set."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_REPO_ROOT))

from scripts._matrix_warmup import (  # noqa: E402 — sys.path setup above
    WARMUP_TICKS_AUTO,
    compute_bar_align_ticks,
    compute_required_warmup_ticks,
)

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_START = "2025-07-07T00:00:00Z"
DEFAULT_END = "2025-07-09T00:00:00Z"
DEFAULT_MODELS_DIR = "models/oco_dukascopy_candidate"
DEFAULT_HISTORY_DIR = "configs/research/governance/oco_history_dukascopy_candidate"
DEFAULT_PREDICTIONS_DIR = (
    "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap"
)
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
    bar_align_ticks: int
    starting_balance: int
    risk_enabled: bool
    universe_mode: str
    ordinal_tolerance: int
    prediction_tolerance_sec: int
    locked_predictions_dir: str


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
    parser.add_argument("--tick-batch-size", type=int, default=200)
    parser.add_argument("--order-ttl-seconds", type=int, default=900)
    parser.add_argument("--api-timeout-seconds", type=int, default=60)
    parser.add_argument("--metrics-enabled", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--metrics-host", default="127.0.0.1")
    parser.add_argument("--metrics-port-base", type=int, default=9465)
    parser.add_argument(
        "--warmup-ticks",
        type=int,
        default=WARMUP_TICKS_AUTO,
        help=(
            "Warmup ticks to pre-load before matrix start. Default 0 = "
            "auto-compute as full_warmup_bars * max(candidate bar_ticks) * 1.2 "
            "from the locked predictions for --model-month or "
            "--locked-predictions-dir."
        ),
    )
    parser.add_argument("--lookback-days", type=int, default=31)
    parser.add_argument(
        "--bar-align-ticks",
        type=int,
        default=0,
        help=(
            "Tick-count modulus for warmup load alignment. Default 0 = auto-derive "
            "from max(candidate bar_ticks) in --model-month locked predictions."
        ),
    )
    parser.add_argument("--starting-balance", type=int, default=100000)
    parser.add_argument("--risk-enabled", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--universe-mode", choices=["exact", "tolerant", "nearest", "ordinal"], default="exact"
    )
    parser.add_argument("--ordinal-tolerance", type=int, default=0)
    parser.add_argument("--prediction-tolerance-sec", type=int, default=120)
    parser.add_argument("--locked-predictions-dir", default="")
    args = parser.parse_args()
    symbols = tuple(s.strip().upper() for s in str(args.symbols).split(",") if s.strip())
    if not symbols:
        raise SystemExit("No symbols provided")
    warmup_ticks = int(args.warmup_ticks)
    if warmup_ticks <= WARMUP_TICKS_AUTO:
        flat_dir = str(args.locked_predictions_dir).strip()
        if flat_dir:
            warmup_ticks = compute_required_warmup_ticks(
                symbols=symbols,
                locked_predictions_dir=Path(flat_dir),
                model_month="",
            )
        else:
            warmup_ticks = compute_required_warmup_ticks(
                symbols=symbols,
                locked_predictions_dir=Path(args.history_dir),
                model_month=str(args.model_month),
            )
        print(
            f"[surrogate] auto-computed --warmup-ticks={warmup_ticks} "
            f"(model_month={args.model_month})",
            flush=True,
        )
    bar_align_ticks = int(args.bar_align_ticks)
    if bar_align_ticks <= 0:
        flat_dir = str(args.locked_predictions_dir).strip()
        if flat_dir:
            bar_align_model_month = ""
            bar_align_ticks = compute_bar_align_ticks(
                symbols=symbols,
                locked_predictions_dir=Path(flat_dir),
                model_month=bar_align_model_month,
            )
        else:
            bar_align_model_month = str(args.model_month)
            bar_align_ticks = compute_bar_align_ticks(
                symbols=symbols,
                locked_predictions_dir=Path(args.history_dir),
                model_month=bar_align_model_month,
            )
        if bar_align_ticks <= 0:
            raise SystemExit(
                "bar_align_ticks could not be auto-derived from locked predictions; "
                "pass --bar-align-ticks explicitly."
            )
        print(
            f"[surrogate] auto-computed --bar-align-ticks={bar_align_ticks} "
            f"(model_month={bar_align_model_month})",
            flush=True,
        )
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
        warmup_ticks=warmup_ticks,
        lookback_days=args.lookback_days,
        bar_align_ticks=bar_align_ticks,
        starting_balance=args.starting_balance,
        risk_enabled=bool(args.risk_enabled),
        universe_mode=args.universe_mode,
        ordinal_tolerance=int(args.ordinal_tolerance),
        prediction_tolerance_sec=int(args.prediction_tolerance_sec),
        locked_predictions_dir=str(args.locked_predictions_dir).strip(),
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _pick_free_port(host: str, preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, preferred_port))
            return preferred_port
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def _poll_health(proc: subprocess.Popen[str], base_url: str, timeout_sec: float) -> None:
    deadline = time.time() + timeout_sec
    last_error: str | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = _read_process_tail(proc)
            raise RuntimeError(
                f"API process exited before becoming healthy: {tail or proc.returncode}"
            )
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
    if cfg.locked_predictions_dir:
        return str(
            Path(cfg.locked_predictions_dir) / f"{symbol.lower()}_oco_locked_predictions.parquet"
        )
    locked = (
        Path(cfg.history_dir) / cfg.model_month / f"{symbol.lower()}_oco_locked_predictions.parquet"
    )
    if locked.exists():
        return str(locked)
    return str(Path(cfg.predictions_dir) / f"{symbol}_oco_monthly_predictions.parquet")


def _state_db_path(cfg: RunConfig, symbol: str) -> Path:
    return _repo_root() / cfg.report_dir / "runtime" / f"{symbol.lower()}_local_jforex_state.db"


def _start_api(
    cfg: RunConfig, symbol: str, api_port: int
) -> tuple[subprocess.Popen[str], deque[str]]:
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
            "BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC": str(cfg.prediction_tolerance_sec),
            "BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE": _prediction_path(cfg, symbol),
            "BEHEMOTH_FORCE_MODEL_MONTH": cfg.model_month,
            # Use in-memory DuckDB (empty string) to avoid file-backed WAL
            # checkpointing blocking the asyncio event loop mid-run.
            # State is wiped at the start of each symbol run anyway, so
            # persistence across restarts provides no benefit here.
            "BEHEMOTH_STATE_DB": "",
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
        str(api_port),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=_repo_root(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    log_lines: deque[str] = deque(maxlen=200)

    def _drain() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))

    threading.Thread(target=_drain, daemon=True).start()
    return proc, log_lines


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


def _read_process_tail(log_lines: deque[str], max_lines: int = 50) -> str:
    lines = list(log_lines)
    return "\n".join(lines[-max_lines:])


def _run_surrogate(cfg: RunConfig, symbol: str, metrics_port: int, api_port: int) -> None:
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
            "BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS": str(cfg.bar_align_ticks),
            "BEHEMOTH_LOCAL_JFOREX_STARTING_BALANCE": str(cfg.starting_balance),
            "BEHEMOTH_API_BASE_URI": f"http://{cfg.api_host}:{api_port}",
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
        api_port = _pick_free_port(cfg.api_host, cfg.api_port + index)
        metrics_port = _pick_free_port(cfg.metrics_host, cfg.metrics_port_base + index)
        print(
            f"[local-jforex] {symbol}: starting API "
            f"(api_port={api_port} metrics_port={metrics_port})",
            flush=True,
        )
        api_proc, api_log = _start_api(cfg, symbol, api_port)
        try:
            _poll_health(api_proc, f"http://{cfg.api_host}:{api_port}", timeout_sec=60.0)
            print(f"[local-jforex] {symbol}: running surrogate", flush=True)
            _run_surrogate(cfg, symbol, metrics_port, api_port)
            print(f"[local-jforex] {symbol}: complete", flush=True)
        except Exception as exc:  # pragma: no cover - orchestration path
            failures.append(f"{symbol}: {exc}")
            print(f"[local-jforex] {symbol}: failed: {exc}", file=sys.stderr, flush=True)
        finally:
            _stop_process(api_proc)
            tail = _read_process_tail(api_log)
            if tail:
                print(tail, file=sys.stderr, flush=True)

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()
