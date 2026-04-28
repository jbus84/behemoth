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
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_REPO_ROOT))

from src.behemoth.live_restart.reconciliation import (
    BrokerSnapshot,
    LocalRuntimeStateSummary,
    ReconciliationReport,
    RestartEligibilityResult,
    RuntimeContextComparison,
    RuntimeFileSnapshot,
    RuntimeSessionMetadata,
    compare_runtime_context,
    compute_lock_fingerprint,
    derive_restart_eligibility,
    inspect_local_runtime_state,
    inspect_runtime_files,
    load_broker_snapshot,
    load_promoted_model_month,
    load_promoted_symbols,
    load_runtime_session_metadata,
    write_reconciliation_report,
    write_runtime_session_metadata,
)
from src.behemoth.ops.verdicts import RestartEligibility

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_MODELS_DIR = "models/oco"
DEFAULT_HISTORY_DIR = "configs/research/governance/oco_history_dukascopy_candidate"
DEFAULT_API_PORT = 8000


@dataclass(frozen=True)
class RunConfig:
    symbols: tuple[str, ...]
    models_dir: str
    history_dir: str
    report_dir: str
    startup_mode: str
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
    parser.add_argument("--startup-mode", choices=("resume", "reset"), default="resume")
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
        startup_mode=str(args.startup_mode),
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


def _governance_dir_raw() -> str:
    return str(os.environ.get("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"))


def _governance_dir_path(repo_root: Path) -> Path:
    raw = Path(_governance_dir_raw())
    return raw if raw.is_absolute() else repo_root / raw


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_repo_path(path_txt: str, repo_root: Path) -> Path:
    path = Path(path_txt)
    return path if path.is_absolute() else repo_root / path


def _expected_threshold_runtime(lock_payload: dict[str, object]) -> dict[str, object]:
    locked_runtime = lock_payload.get("locked_runtime", {})
    if not isinstance(locked_runtime, dict):
        return {}
    return {
        "threshold_source": locked_runtime.get("threshold_mode"),
        "rolling_threshold_days": locked_runtime.get("rolling_threshold_days"),
        "rolling_threshold_min_history": locked_runtime.get("rolling_threshold_min_history"),
        "execution_quantile": locked_runtime.get("execution_quantile"),
        "oco_hold_mode": locked_runtime.get("oco_hold_mode"),
        "oco_include_no_touch": locked_runtime.get("oco_include_no_touch"),
    }


_TICK_STALENESS_MAX_DAYS = 3


def _validate_tick_data_freshness(cfg: RunConfig) -> None:
    ticks_dir = Path(os.getenv("BEHEMOTH_DUKASCOPY_TICKS_DIR", "/Users/danielfisher/Desktop/dukascopy_ticks"))
    max_age_days = _TICK_STALENESS_MAX_DAYS
    now = datetime.now(tz=timezone.utc)
    cutoff = now - __import__("datetime").timedelta(days=max_age_days)
    stale: list[str] = []

    for symbol in cfg.symbols:
        sym_dir = ticks_dir / symbol
        if not sym_dir.exists():
            stale.append(f"{symbol}: tick directory not found ({sym_dir})")
            continue
        parquets = sorted(sym_dir.glob("*.parquet"))
        if not parquets:
            stale.append(f"{symbol}: no parquet files in {sym_dir}")
            continue
        latest_mtime = max(p.stat().st_mtime for p in parquets)
        latest_dt = datetime.fromtimestamp(latest_mtime, tz=timezone.utc)
        age_days = (now - latest_dt).days
        if latest_dt < cutoff:
            stale.append(f"{symbol}: tick data is {age_days} days old (last file: {parquets[-1].name})")

    if stale:
        print("[jforex-live] PREFLIGHT FAILED: tick data is stale", file=sys.stderr, flush=True)
        for msg in stale:
            print(f"[jforex-live]   {msg}", file=sys.stderr, flush=True)
        print(
            "[jforex-live] Update tick data first:\n"
            "  uv run python scripts/download_tick_vault_data.py --help\n"
            "Then re-seed the rolling threshold:\n"
            "  make seed-threshold",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)


def _validate_promoted_runtime_artifacts(cfg: RunConfig) -> None:
    repo_root = _repo_root()
    governance_dir = _governance_dir_path(repo_root)
    models_dir = _resolve_repo_path(cfg.models_dir, repo_root)
    requested_symbols = {symbol.upper() for symbol in cfg.symbols}
    failures: list[str] = []

    for lock_path in sorted(governance_dir.glob("*_oco_live_lock.json")):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        symbol = str(payload.get("symbol", "")).upper().strip()
        if not symbol or symbol not in requested_symbols:
            continue
        artifacts = payload.get("artifacts", {})
        if not isinstance(artifacts, dict) or bool(artifacts.get("live_deployable", True)) is False:
            continue

        runtime_model_path = models_dir / Path(str(artifacts.get("model_cbm_path", "")).strip()).name
        runtime_thr_path = models_dir / Path(
            str(artifacts.get("model_threshold_json_path", "")).strip()
        ).name
        expected_model_sha = str(artifacts.get("model_cbm_sha256", "")).strip()
        expected_thr_sha = str(artifacts.get("model_threshold_json_sha256", "")).strip()

        if not runtime_model_path.exists():
            failures.append(f"{symbol}: missing runtime model {runtime_model_path}")
            continue
        if not runtime_thr_path.exists():
            failures.append(f"{symbol}: missing runtime threshold json {runtime_thr_path}")
            continue
        if _sha256(runtime_model_path) != expected_model_sha:
            failures.append(f"{symbol}: runtime model sha mismatch for {runtime_model_path.name}")
        if _sha256(runtime_thr_path) != expected_thr_sha:
            failures.append(f"{symbol}: runtime threshold sha mismatch for {runtime_thr_path.name}")

        thr_cfg = json.loads(runtime_thr_path.read_text(encoding="utf-8"))
        expected_runtime = _expected_threshold_runtime(payload)
        for key, expected_value in expected_runtime.items():
            if thr_cfg.get(key) != expected_value:
                failures.append(
                    f"{symbol}: {key} drift runtime={thr_cfg.get(key)!r} lock={expected_value!r}"
                )

        expected_month = str(artifacts.get("model_month", "")).strip()
        if expected_month and str(thr_cfg.get("model_month", "")).strip() != expected_month:
            failures.append(
                f"{symbol}: model_month drift runtime={thr_cfg.get('model_month')!r} lock={expected_month!r}"
            )

    if failures:
        raise SystemExit(
            "Promoted runtime artifact preflight failed:\n- " + "\n- ".join(failures)
        )


def _git_metadata(repo_root: Path) -> tuple[str, str, bool]:
    commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, branch, dirty


def _has_resume_blocking_git_dirty(repo_root: Path) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "status",
            "--porcelain",
            "--untracked-files=no",
            "--",
            "scripts/run_jforex_live.py",
            "src/behemoth/live_restart",
            "Makefile",
            "configs/research/governance/oco",
            "data/analysis/backtest_reconcile/runtime",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _runtime_paths(cfg: RunConfig) -> dict[str, Path]:
    runtime_dir = _repo_root() / cfg.report_dir / "runtime"
    return {
        "runtime_dir": runtime_dir,
        "state_db_path": runtime_dir / "live_state.db",
        "active_state_path": runtime_dir / "active_oco_state.json",
        "session_metadata_path": runtime_dir / "live_runtime_session.json",
        "broker_snapshot_path": runtime_dir / "live_broker_snapshot.json",
        "reconciliation_report_path": runtime_dir / "live_restart_reconciliation.json",
    }


def _build_current_session_metadata(cfg: RunConfig) -> RuntimeSessionMetadata:
    repo_root = _repo_root()
    git_commit, git_branch, _git_dirty = _git_metadata(repo_root)
    governance_dir_raw = _governance_dir_raw()
    governance_dir = _governance_dir_path(repo_root)
    promoted_symbols = load_promoted_symbols(governance_dir)
    model_month = load_promoted_model_month(governance_dir) or _resolve_model_month(cfg) or ""
    lock_fingerprint = compute_lock_fingerprint(governance_dir)
    started_at_utc = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return RuntimeSessionMetadata(
        git_commit=git_commit,
        git_branch=git_branch,
        git_dirty=_has_resume_blocking_git_dirty(repo_root),
        repo_root=str(repo_root),
        model_month=model_month,
        governance_dir=governance_dir_raw,
        lock_fingerprint=lock_fingerprint,
        symbols=promoted_symbols,
        started_at_utc=started_at_utc,
        startup_mode=cfg.startup_mode,
    )


def _cleanup_runtime_state(paths: dict[str, Path]) -> None:
    active_state = paths["active_state_path"]
    if active_state.exists():
        active_state.unlink()
    state_db = paths["state_db_path"]
    if state_db.exists():
        try:
            _consolidate_to_archive(state_db)
        except Exception as exc:
            print(
                f"[jforex-live] archive failed during reset; force-clearing runtime state: {exc}",
                flush=True,
            )
            state_db.unlink(missing_ok=True)
            wal = state_db.with_suffix(".db.wal")
            wal.unlink(missing_ok=True)


def _print_incompatible_restart_summary(
    cfg: RunConfig,
    paths: dict[str, Path],
    comparison: RuntimeContextComparison,
) -> None:
    print(
        "[jforex-live] incompatible live restart metadata; rerun with --startup-mode reset",
        file=sys.stderr,
        flush=True,
    )
    print(
        f"[jforex-live] reconciliation report: {paths['reconciliation_report_path']}",
        file=sys.stderr,
        flush=True,
    )
    print(
        "[jforex-live] restart summary: "
        f"startup_mode={cfg.startup_mode} "
        f"verdict={comparison.verdict.value} "
        f"reasons={len(comparison.reasons)}",
        file=sys.stderr,
        flush=True,
    )
    for index, reason in enumerate(comparison.reasons, start=1):
        print(f"[jforex-live]   {index}. {reason}", file=sys.stderr, flush=True)


def _reconcile_startup(
    cfg: RunConfig,
    paths: dict[str, Path],
) -> tuple[
    RuntimeSessionMetadata,
    RuntimeSessionMetadata | None,
    RuntimeContextComparison,
    RestartEligibilityResult,
]:
    current_metadata = _build_current_session_metadata(cfg)
    session_path = paths["session_metadata_path"]
    persisted_metadata = load_runtime_session_metadata(session_path) if session_path.exists() else None
    local_state = inspect_runtime_files(
        paths["runtime_dir"],
        paths["state_db_path"],
        paths["active_state_path"],
        session_path,
    )
    broker_snapshot: BrokerSnapshot | None = None
    local_runtime: LocalRuntimeStateSummary | None = None
    if cfg.startup_mode == "resume":
        _capture_broker_snapshot(cfg, paths)
        broker_snapshot = load_broker_snapshot(paths["broker_snapshot_path"])
        local_runtime = inspect_local_runtime_state(paths["state_db_path"])
    comparison = compare_runtime_context(
        persisted_metadata,
        current_metadata,
        local_state=local_state,
        broker_snapshot=broker_snapshot,
        local_runtime=local_runtime,
    )
    restart_eligibility = derive_restart_eligibility(comparison)
    report = ReconciliationReport(
        startup_mode=cfg.startup_mode,
        verdict=comparison.verdict,
        reasons=list(comparison.reasons),
        repaired_items=[],
        current=current_metadata,
        persisted=persisted_metadata,
        local_state=local_state,
        local_runtime=local_runtime,
        broker_snapshot=broker_snapshot,
        promoted_symbols=load_promoted_symbols(_governance_dir_path(_repo_root())),
        restart_eligibility=restart_eligibility,
    )
    write_reconciliation_report(paths["reconciliation_report_path"], report)
    return current_metadata, persisted_metadata, comparison, restart_eligibility


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
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"API did not become healthy within {timeout_sec:.0f}s: {last_error}")


def _resolve_model_month(cfg) -> str | None:
    """Resolve the model month from the promoted history directory."""
    history_dir = Path(cfg.history_dir)
    if not history_dir.exists():
        return None
    months = sorted(d.name for d in history_dir.iterdir() if d.is_dir() and d.name != "__pycache__")
    return months[-1] if months else None


def _seed_audit_history(
    symbols: list[str],
    base_url: str,
    days_back: int = 20,
    train_predictions_dir: str | None = None,
    model_month: str | None = None,
) -> None:
    """Call /state/seed_audit_history to populate audit_logs.

    Phase 1: Load exported training predictions (WFO-equivalent pool).
    Phase 2: Replay test-month parquet to bridge any gap since month start.
    """
    import requests

    # Determine test month start from model_month (test month = month after model_month)
    test_month_start = None
    if model_month:
        from datetime import datetime as dt

        from dateutil.relativedelta import relativedelta

        mm = dt.strptime(model_month, "%Y-%m")
        test_month_start = (mm + relativedelta(months=1)).strftime("%Y-%m-%dT00:00:00")

    print(
        f"[seed] seeding audit_logs (train_pred_dir={train_predictions_dir}, "
        f"test_month_start={test_month_start})...",
        flush=True,
    )
    try:
        r = requests.post(
            f"{base_url}/state/seed_audit_history",
            json={
                "symbols": symbols,
                "days_back": days_back,
                "run_id": "audit_seed",
                "train_predictions_dir": train_predictions_dir,
                "test_month_start": test_month_start,
            },
            timeout=600,
        )
        body = r.json()
        if body.get("ok"):
            p1 = sum(body.get("phase1_events", {}).values())
            p2 = sum(body.get("phase2_events", {}).values())
            print(
                f"[seed] done — phase1: {p1}, phase2: {p2}, total: {body['total_events']}",
                flush=True,
            )
            for sym, count in body.get("phase1_events", {}).items():
                print(f"[seed]   {sym} phase1: {count} events", flush=True)
            for sym, count in body.get("phase2_events", {}).items():
                print(f"[seed]   {sym} phase2: {count} events", flush=True)
        else:
            print(f"[seed] WARNING: unexpected response: {body}", flush=True)
    except Exception as exc:
        print(f"[seed] WARNING: seed_audit_history failed: {exc}", flush=True)
        print(
            "[seed] continuing without historical seed — first predict calls may block", flush=True
        )


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
            "BEHEMOTH_GOVERNANCE_DIR": _governance_dir_raw(),
            "BEHEMOTH_GOVERNANCE_HISTORY_DIR": cfg.history_dir,
            "BEHEMOTH_MODELS_DIR": cfg.models_dir,
            "BEHEMOTH_STATE_DB": str(state_db_path),
            "BEHEMOTH_SEED_DIR": str(_repo_root() / "data" / "runtime" / "seed"),
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


def _start_live_runner(cfg: RunConfig, *, allow_new_entries: bool = True) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update(
        {
            "BEHEMOTH_JFOREX_INSTRUMENTS": ",".join(cfg.symbols),
            "BEHEMOTH_JFOREX_RISK_ENABLED": "true",
            "BEHEMOTH_JFOREX_NATIVE_OCO_ENABLED": "false",
            "BEHEMOTH_JFOREX_RUN_ID": "jforex_live",
            "BEHEMOTH_JFOREX_LIVE_STARTUP_MODE": cfg.startup_mode,
            "BEHEMOTH_JFOREX_REPORT_DIR": cfg.report_dir,
            "BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS": str(cfg.requested_volume_units),
            "BEHEMOTH_JFOREX_TICK_BATCH_SIZE": str(cfg.tick_batch_size),
            "BEHEMOTH_JFOREX_ORDER_TTL_SECONDS": str(cfg.order_ttl_seconds),
            "BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS": str(cfg.api_timeout_seconds),
            "BEHEMOTH_JFOREX_METRICS_ENABLED": str(cfg.metrics_enabled).lower(),
            "BEHEMOTH_JFOREX_METRICS_HOST": cfg.metrics_host,
            "BEHEMOTH_JFOREX_METRICS_PORT": str(cfg.metrics_port),
            "BEHEMOTH_API_BASE_URI": f"http://{cfg.api_host}:{cfg.api_port}",
            "BEHEMOTH_JFOREX_NEW_ENTRIES_ENABLED": str(bool(allow_new_entries)).lower(),
        }
    )
    return subprocess.Popen(
        ["mise", "exec", "--", "gradle", "--no-daemon", ":jforex-adapter:runJForexLive"],
        cwd=_repo_root(),
        env=env,
        start_new_session=True,
    )


def _capture_broker_snapshot(cfg: RunConfig, paths: dict[str, Path]) -> None:
    snapshot_path = paths["broker_snapshot_path"]
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot_path.exists():
        snapshot_path.write_text('{"captured_at_utc":"", "orders":[]}\n', encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "BEHEMOTH_JFOREX_INSTRUMENTS": ",".join(cfg.symbols),
            "BEHEMOTH_JFOREX_REPORT_DIR": cfg.report_dir,
            "BEHEMOTH_JFOREX_BROKER_SNAPSHOT_PATH": str(snapshot_path),
            "BEHEMOTH_JFOREX_RUN_ID": "jforex_broker_snapshot",
            "BEHEMOTH_JFOREX_METRICS_ENABLED": "false",
        }
    )
    subprocess.run(
        ["mise", "exec", "--", "gradle", "--no-daemon", ":jforex-adapter:runJForexBrokerSnapshot"],
        cwd=_repo_root(),
        env=env,
        check=True,
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


# Tables consolidated into the archive. audit_logs are seed-only and
# reproducible; tick_bars / raw_ticks are too large to carry forward.
_ARCHIVE_TABLES = [
    "trades",
    "predict_evaluations",
    "account_risk_allocator_events",
    "account_risk_reservations",
    "account_risk_snapshots",
]


def _consolidate_to_archive(state_db_path: Path) -> None:
    """Append live_state.db into a single consolidated archive DB, then delete it.

    A ``session_started_at`` column is stamped on every inserted row so
    sessions remain distinguishable without needing separate files.
    """
    import duckdb

    archive_dir = state_db_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_db = archive_dir / "live_state_archive.db"
    session_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    src = duckdb.connect(str(state_db_path), read_only=True)
    src_tables = {row[0] for row in src.execute("SHOW TABLES").fetchall()}
    src.close()

    arc = duckdb.connect(str(archive_db))
    arc.execute(f"ATTACH '{state_db_path}' AS src (READ_ONLY)")

    total_rows = 0
    for table in _ARCHIVE_TABLES:
        if table not in src_tables:
            continue
        # Bootstrap archive table from source schema + session column
        arc.execute(
            f"CREATE TABLE IF NOT EXISTS {table} AS "
            f"SELECT *, CAST(NULL AS VARCHAR) AS session_started_at "
            f"FROM src.{table} WHERE 1=0"
        )
        n = arc.execute(
            f"INSERT INTO {table} "
            f"SELECT *, '{session_ts}' AS session_started_at FROM src.{table}"
        ).rowcount
        total_rows += n

    arc.close()

    # Remove the source DB now that it's consolidated
    state_db_path.unlink()
    wal = state_db_path.with_suffix(".db.wal")
    if wal.exists():
        wal.unlink()

    print(
        f"[jforex-live] consolidated {total_rows} rows into {archive_db.name} "
        f"(session={session_ts})",
        flush=True,
    )


def main() -> None:
    cfg = _parse_args()

    # Pre-flight: validate credentials before starting any process
    for required in (
        "BEHEMOTH_JFOREX_JNLP_URI",
        "BEHEMOTH_JFOREX_USERNAME",
        "BEHEMOTH_JFOREX_PASSWORD",
    ):
        if not os.environ.get(required):
            raise SystemExit(f"Missing required env var: {required}")

    _validate_tick_data_freshness(cfg)
    _validate_promoted_runtime_artifacts(cfg)

    paths = _runtime_paths(cfg)
    paths["runtime_dir"].mkdir(parents=True, exist_ok=True)

    current_metadata, _persisted_metadata, comparison, restart_eligibility = _reconcile_startup(
        cfg,
        paths,
    )
    if cfg.startup_mode == "resume" and not restart_eligibility.allow_new_entries:
        if restart_eligibility.eligibility.value == "RESTART_BLOCKED":
            _print_incompatible_restart_summary(cfg, paths, comparison)
            raise SystemExit(1)
        print(
            "[jforex-live] restart eligible in drain-only mode; new entries disabled",
            flush=True,
        )

    if comparison.verdict is RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY:
        print(
            "[jforex-live] startup reconciliation is reconcilable; continuing with startup",
            flush=True,
        )
    if cfg.startup_mode == "reset":
        _cleanup_runtime_state(paths)

    write_runtime_session_metadata(paths["session_metadata_path"], current_metadata)

    # Run offline seed BEFORE starting the API
    print("[jforex-live] running offline threshold seed (timeout=300s)", flush=True)
    try:
        seed_result = subprocess.run(
            [
                sys.executable,
                "scripts/seed_rolling_threshold.py",
                "--symbols", ",".join(cfg.symbols),
                "--governance-dir", os.environ.get("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"),
                "--models-dir", cfg.models_dir,
                "--ticks-dir", os.getenv("BEHEMOTH_DUKASCOPY_TICKS_DIR", "/Users/danielfisher/Desktop/dukascopy_ticks"),
                "--seed-dir", str(_repo_root() / "data" / "runtime" / "seed"),
            ],
            cwd=_repo_root(),
            timeout=300,
        )
        if seed_result.returncode != 0:
            print("[jforex-live] WARNING: offline seed failed — API will start without historical thresholds", flush=True)
    except subprocess.TimeoutExpired:
        print("[jforex-live] WARNING: offline seed timed out after 300s — API will start without historical thresholds", flush=True)

    print("[jforex-live] starting API", flush=True)
    api_proc = _start_api(cfg)
    java_proc: subprocess.Popen[str] | None = None

    def _shutdown(_signum: int, frame: object) -> None:
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
        print("[jforex-live] starting JForex runner", flush=True)
        effective_allow_new_entries = (
            True if cfg.startup_mode == "reset"
            else restart_eligibility.allow_new_entries
        )
        java_proc = _start_live_runner(
            cfg,
            allow_new_entries=effective_allow_new_entries,
        )
        print(f"[jforex-live] running (symbols={','.join(cfg.symbols)})", flush=True)
        print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
        # Give JForex time to complete initial backfill before warmup scoring
        time.sleep(30)
        _warmup_symbols(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
        print("[jforex-live] warmup complete", flush=True)

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
