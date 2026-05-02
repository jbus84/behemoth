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
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_REPO_ROOT))

from scripts._matrix_warmup import (
    WARMUP_TICKS_AUTO,
    align_keep,
    compute_bar_align_ticks,
    compute_required_warmup_ticks,
)

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_START = "2025-07-04T00:00:00Z"
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
    risk_enabled: bool
    universe_mode: str
    ordinal_tolerance: int
    warmup_ticks: int
    lookback_days: int
    bar_align_ticks: int
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
    parser.add_argument("--metrics-port-base", type=int, default=9464)
    parser.add_argument("--risk-enabled", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--universe-mode", choices=["tolerant", "nearest", "ordinal"], default="tolerant"
    )
    parser.add_argument("--ordinal-tolerance", type=int, default=0)
    parser.add_argument(
        "--warmup-ticks",
        type=int,
        default=WARMUP_TICKS_AUTO,
        help=(
            "Warmup ticks to pre-load before matrix start. Default 0 = "
            "auto-compute as full_warmup_bars * max(candidate bar_ticks) * 1.2 "
            "from the locked predictions for --model-month."
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
    warmup_ticks = int(args.warmup_ticks)
    if warmup_ticks <= WARMUP_TICKS_AUTO:
        warmup_ticks = compute_required_warmup_ticks(
            symbols=symbols,
            locked_predictions_dir=Path(args.history_dir),
            model_month=str(args.model_month),
        )
        print(
            f"[matrix] auto-computed --warmup-ticks={warmup_ticks} "
            f"(model_month={args.model_month})",
            flush=True,
        )
    bar_align_ticks = int(args.bar_align_ticks)
    if bar_align_ticks <= 0:
        bar_align_ticks = compute_bar_align_ticks(
            symbols=symbols,
            locked_predictions_dir=Path(args.history_dir),
            model_month=str(args.model_month),
        )
        if bar_align_ticks <= 0:
            raise SystemExit(
                f"bar_align_ticks could not be auto-derived from "
                f"{args.history_dir}/{args.model_month} locked predictions; "
                f"pass --bar-align-ticks explicitly."
            )
        print(
            f"[matrix] auto-computed --bar-align-ticks={bar_align_ticks} "
            f"(model_month={args.model_month})",
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
        risk_enabled=bool(args.risk_enabled),
        universe_mode=args.universe_mode,
        ordinal_tolerance=int(args.ordinal_tolerance),
        warmup_ticks=warmup_ticks,
        lookback_days=int(args.lookback_days),
        bar_align_ticks=bar_align_ticks,
        tester_completion_timeout_seconds=args.tester_completion_timeout_seconds,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_common_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _with_mise_trusted_paths(env: dict[str, str]) -> dict[str, str]:
    trusted = [str(_repo_common_root()), str(_repo_root())]
    existing = [part for part in str(env.get("MISE_TRUSTED_CONFIG_PATHS", "")).split(os.pathsep) if part]
    for path in trusted:
        if path not in existing:
            existing.append(path)
    updated = env.copy()
    updated["MISE_TRUSTED_CONFIG_PATHS"] = os.pathsep.join(existing)
    return updated


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _next_available_port(host: str, start_port: int, max_attempts: int = 100) -> int:
    port = int(start_port)
    for _ in range(max_attempts):
        if _is_port_available(host, port):
            return port
        port += 1
    raise RuntimeError(
        f"Could not find available port for host {host} starting at {start_port} "
        f"within {max_attempts} attempts"
    )


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
    locked = (
        Path(cfg.history_dir) / cfg.model_month / f"{symbol.lower()}_oco_locked_predictions.parquet"
    )
    if locked.exists():
        return str(locked)
    return str(Path(cfg.predictions_dir) / f"{symbol}_oco_monthly_predictions.parquet")


def _state_db_path(cfg: RunConfig, symbol: str) -> Path:
    return _repo_root() / cfg.report_dir / "runtime" / f"{symbol.lower()}_jforex_dukascopy_state.db"


def _parse_utc(ts: str) -> datetime:
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc)


def _parquet_expression(files: list[Path]) -> str:
    quoted = [repr(str(path.resolve())) for path in files]
    if len(quoted) == 1:
        return quoted[0]
    return "[" + ", ".join(quoted) + "]"


def _tick_files(cfg: RunConfig, symbol: str) -> list[Path]:
    symbol_dir = Path(cfg.tick_root) / symbol.upper().strip()
    if not symbol_dir.is_dir():
        return []
    return sorted(path for path in symbol_dir.iterdir() if path.suffix == ".parquet")


def _load_aligned_warmup_ticks(cfg: RunConfig, symbol: str) -> list[dict[str, object]]:
    files = _tick_files(cfg, symbol)
    if cfg.bar_align_ticks <= 0:
        return []
    if not files:
        raise RuntimeError(
            f"No tick parquet files found for {symbol.upper().strip()} under {cfg.tick_root}"
        )
    try:
        import duckdb
    except Exception as exc:  # pragma: no cover - exercised in real runtime
        raise RuntimeError("duckdb is required to prime JForex historical warmup state") from exc

    start_ts = _parse_utc(cfg.start_ts)
    lookback_start = start_ts - timedelta(days=cfg.lookback_days)
    expr = _parquet_expression(files)
    con = duckdb.connect()
    try:
        full_pre_count = int(
            con.execute(
                f"SELECT COUNT(*) FROM read_parquet({expr}) WHERE timestamp < ?",
                [start_ts],
            ).fetchone()[0]
        )
        keep = align_keep(int(cfg.warmup_ticks), int(cfg.bar_align_ticks), full_pre_count)
        if keep <= 0:
            return []
        rows = con.execute(
            f"""
            SELECT timestamp, bid, ask
            FROM read_parquet({expr})
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [lookback_start, start_ts, keep],
        ).fetchall()
        if len(rows) < keep:
            raise RuntimeError(
                f"Insufficient aligned warmup ticks for {symbol.upper().strip()}: "
                f"requested keep={keep}, actual rows={len(rows)}, "
                f"lookback_start={lookback_start.isoformat()}, "
                f"start_ts={start_ts.isoformat()}"
            )
    finally:
        con.close()

    rows.reverse()
    return [
        {
            "symbol": symbol.upper().strip(),
            "timestamp": row[0].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "bid": float(row[1]),
            "ask": float(row[2]),
            "volume": 1.0,
            "client_tick_seq": idx,
            "run_id": f"jforex_dukascopy_{symbol.lower()}_warmup",
        }
        for idx, row in enumerate(rows, start=1)
    ]


def _prime_api_with_warmup(cfg: RunConfig, symbol: str, api_port: int) -> None:
    ticks = _load_aligned_warmup_ticks(cfg, symbol)
    if not ticks:
        return
    payload = {
        "symbol": symbol.upper().strip(),
        "bar_ticks": int(cfg.bar_align_ticks),
        "ticks": ticks,
        "run_id": f"jforex_dukascopy_{symbol.lower()}_warmup",
    }
    req = urllib.request.Request(
        f"http://{cfg.api_host}:{api_port}/backfill",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60.0) as response:
        if response.status != 201:
            raise RuntimeError(f"Warmup backfill failed for {symbol}: status={response.status}")


def _start_api(cfg: RunConfig, symbol: str, api_port: int) -> subprocess.Popen[str]:
    state_db_path = _state_db_path(cfg, symbol)
    state_db_path.parent.mkdir(parents=True, exist_ok=True)
    if state_db_path.exists():
        state_db_path.unlink()
    env = _with_mise_trusted_paths(os.environ.copy())
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
            "BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC": "600",
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
        str(api_port),
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


def _stage14_artifact_paths(report_dir: Path, symbol: str) -> list[Path]:
    return [
        report_dir / f"{symbol}_jforex_runtime_events.csv",
        report_dir / f"{symbol}_jforex_signal_parity_summary.csv",
        report_dir / f"{symbol}_jforex_execution_parity_summary.csv",
        report_dir / f"{symbol}_jforex_execution_lifecycle_summary.csv",
        report_dir / f"{symbol}_jforex_operational_ready_summary.csv",
    ]


def _wait_for_artifacts_then_kill(
    proc: subprocess.Popen,
    artifact_paths: list[Path],
    poll_interval_sec: float = 5.0,
    settle_sec: float = 5.0,
    timeout_sec: float = 14400.0,
) -> None:
    """Poll until the Stage 14 artifact set exists and is non-empty, then kill the process.

    The JForex framework hangs in thread cleanup after onStop writes the CSV.
    Once all expected artifacts are present and non-empty we have all the data we need, so we
    kill the process group rather than waiting for the JVM to exit cleanly.

    Args:
        proc: The running Gradle/Java subprocess.
        artifact_paths: Paths written by the strategy on completion.
        poll_interval_sec: How often to check for the CSV (seconds).
        settle_sec: Extra wait after CSV appears before killing, to let the file flush.
        timeout_sec: Maximum total wait time before raising TimeoutError.

    Raises:
        subprocess.CalledProcessError: If process exits non-zero before CSV appears.
        TimeoutError: If the artifact set does not appear within timeout_sec.
    """
    deadline = time.monotonic() + timeout_sec
    while True:
        rc = proc.poll()
        if rc is not None:
            if rc == 0:
                missing = [str(path) for path in artifact_paths if not (path.exists() and path.stat().st_size > 0)]
                if not missing:
                    return
                raise RuntimeError(
                    "JForex tester exited cleanly but did not produce complete Stage 14 artifacts: "
                    + ", ".join(missing)
                )
            raise subprocess.CalledProcessError(rc, "JForexTesterRunner")

        artifacts_ready = all(path.exists() and path.stat().st_size > 0 for path in artifact_paths)
        if artifacts_ready:
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
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=10)
            return

        if time.monotonic() >= deadline:
            # Kill the process before raising so it doesn't become an orphan.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=10)
            raise TimeoutError(
                "JForex tester did not produce complete Stage 14 artifacts within "
                f"{timeout_sec:.0f}s: {', '.join(str(path) for path in artifact_paths)}"
            )
        time.sleep(poll_interval_sec)


def _run_jforex_tester(cfg: RunConfig, symbol: str, api_port: int, metrics_port: int) -> None:
    """Run the real Dukascopy JForex tester for a single symbol."""
    for required in (
        "BEHEMOTH_JFOREX_JNLP_URI",
        "BEHEMOTH_JFOREX_USERNAME",
        "BEHEMOTH_JFOREX_PASSWORD",
    ):
        if not os.environ.get(required):
            raise RuntimeError(f"Missing required env var: {required}")

    selected_metrics_port = _next_available_port(cfg.metrics_host, metrics_port)
    env = _with_mise_trusted_paths(os.environ.copy())
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
            "BEHEMOTH_JFOREX_METRICS_PORT": str(selected_metrics_port),
            "BEHEMOTH_API_BASE_URI": f"http://{cfg.api_host}:{api_port}",
        }
    )
    report_dir = _repo_root() / cfg.report_dir
    artifact_paths = _stage14_artifact_paths(report_dir, symbol)
    # Delete stale per-symbol Stage 14 artifacts so the poll loop doesn't
    # mistake previous-run output for fresh completion.
    for artifact_path in artifact_paths:
        if artifact_path.exists():
            artifact_path.unlink()
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
    _wait_for_artifacts_then_kill(
        proc=proc,
        artifact_paths=artifact_paths,
        poll_interval_sec=5.0,
        settle_sec=5.0,
        timeout_sec=float(cfg.tester_completion_timeout_seconds),
    )


def main() -> None:
    cfg = _parse_args()
    failures: list[str] = []
    for index, symbol in enumerate(cfg.symbols):
        api_port = _next_available_port(cfg.api_host, cfg.api_port + index)
        metrics_port = cfg.metrics_port_base + index
        print(f"[jforex-dukascopy] {symbol}: starting API on port {api_port}", flush=True)
        api_proc = _start_api(cfg, symbol, api_port)
        try:
            _poll_health(api_proc, f"http://{cfg.api_host}:{api_port}", timeout_sec=60.0)
            _prime_api_with_warmup(cfg, symbol, api_port)
            print(f"[jforex-dukascopy] {symbol}: running JForex tester", flush=True)
            _run_jforex_tester(cfg, symbol, api_port, metrics_port)
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
