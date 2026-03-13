#!/usr/bin/env python3
"""Manage one-command cTrader debug sessions backed by HistData and DuckDB.

This wraps the existing HistData export flow plus API startup into a single
session manifest so cTrader backtests can target an isolated runtime DB.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_ctrader_debug_bundle import build_bundle as build_debug_bundle
from scripts.export_ctrader_custom_data import run as export_custom_data_run


DEFAULT_TICK_ROOT = Path("/Users/danielfisher/Desktop/tick")
ARTIFACT_ROOT = REPO_ROOT / "data" / "analysis" / "backtest_reconcile"
SESSIONS_ROOT = ARTIFACT_ROOT / "ctrader_debug_sessions"
PACKAGE_ROOT = ARTIFACT_ROOT / "ctrader_custom_data"
ACTIVE_SESSION_PATH = ARTIFACT_ROOT / "ctrader_active_debug_session.json"
ACTIVE_PACKAGE_POINTER_PATH = ARTIFACT_ROOT / "ctrader_active_custom_data_package.txt"
DEBUG_DB_ROOT = REPO_ROOT / "data" / "db" / "debug"
DEBUG_LOG_ROOT = REPO_ROOT / "data" / "logs" / "ctrader_debug"
DEBUG_BUNDLE_ROOT = ARTIFACT_ROOT / "ctrader_debug_runs"
CTRADER_CBOT_ROOT = Path("/Users/danielfisher/cAlgo/Data/cBots/BehemothTradeManager")
CTRADER_JOURNAL_ROOT = Path("/Users/danielfisher/cTrader/Journals/Spotware")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bool_arg(raw: str | bool) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def _parse_ts(name: str, raw: str) -> datetime:
    txt = str(raw).strip()
    if not txt:
        raise ValueError(f"{name} is required")
    dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware: {raw!r}")
    return dt.astimezone(timezone.utc)


def _default_run_id(symbol: str, source: str, start_ts: str, end_ts: str) -> str:
    start = _parse_ts("start_ts", start_ts).strftime("%Y%m%dT%H%M%S")
    end = _parse_ts("end_ts", end_ts).strftime("%Y%m%dT%H%M%S")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{str(symbol).lower()}_{str(source).lower()}_{start}_{end}_{stamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_active_session() -> dict[str, Any] | None:
    if not ACTIVE_SESSION_PATH.exists():
        return None
    try:
        return _read_json(ACTIVE_SESSION_PATH)
    except Exception:
        return None


def _write_active_session(session: dict[str, Any]) -> None:
    _write_json(ACTIVE_SESSION_PATH, session)
    ACTIVE_PACKAGE_POINTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_PACKAGE_POINTER_PATH.write_text(
        str(session["package_dir"]).strip() + "\n",
        encoding="utf-8",
    )


def _clear_active_session() -> None:
    if ACTIVE_SESSION_PATH.exists():
        ACTIVE_SESSION_PATH.unlink()
    if ACTIVE_PACKAGE_POINTER_PATH.exists():
        ACTIVE_PACKAGE_POINTER_PATH.unlink()


def _session_file(run_id: str) -> Path:
    return SESSIONS_ROOT / f"{run_id}.json"


def _bundle_dir(run_id: str) -> Path:
    return DEBUG_BUNDLE_ROOT / str(run_id)


def _load_session(run_id: str) -> dict[str, Any]:
    path = _session_file(run_id)
    if not path.exists():
        raise FileNotFoundError(f"session not found: {path}")
    return _read_json(path)


def _pid_is_running(pid: Any) -> bool:
    try:
        pid_i = int(pid)
    except Exception:
        return False
    if pid_i <= 0:
        return False
    try:
        os.kill(pid_i, 0)
    except OSError:
        return False
    return True


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, int(port))) == 0


def _tail_file(path: Path, max_bytes: int = 4000) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(size - max_bytes, 0))
        data = f.read().decode("utf-8", errors="replace")
    return data[-max_bytes:]


def _copy_if_exists(src: Path | None, dst: Path) -> str | None:
    if src is None or not src.exists():
        return None
    try:
        if src.resolve() == dst.resolve():
            return str(src)
    except Exception:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst)


def _parse_session_ts(raw: Any) -> datetime | None:
    txt = str(raw or "").strip()
    if not txt:
        return None
    try:
        return datetime.fromisoformat(txt.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _discover_best_file(
    *,
    paths: list[Path],
    start_ts: datetime | None,
    end_ts: datetime | None,
) -> tuple[Path | None, list[str]]:
    if not paths:
        return None, []

    def _score(path: Path) -> tuple[int, float]:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except Exception:
            mtime = datetime.min.replace(tzinfo=timezone.utc)
        in_window = 0
        if start_ts is not None and end_ts is not None and start_ts <= mtime <= end_ts + timedelta(minutes=30):
            in_window = 1
        return (in_window, mtime.timestamp())

    ranked = sorted(paths, key=_score, reverse=True)
    return ranked[0], [str(p) for p in ranked]


def _discover_ctrader_artifacts(session: dict[str, Any]) -> dict[str, Any]:
    started = _parse_session_ts(session.get("created_at_utc")) or _parse_ts("start_ts", str(session.get("start_ts")))
    stopped = _parse_session_ts(session.get("stopped_at_utc")) or datetime.now(timezone.utc)

    events, events_candidates = _discover_best_file(
        paths=sorted(CTRADER_CBOT_ROOT.glob("*/Backtesting/events.json")),
        start_ts=started,
        end_ts=stopped,
    )
    cbot_log, cbot_log_candidates = _discover_best_file(
        paths=sorted(CTRADER_CBOT_ROOT.glob("*/Backtesting/log.txt")),
        start_ts=started,
        end_ts=stopped,
    )
    params, params_candidates = _discover_best_file(
        paths=sorted(CTRADER_CBOT_ROOT.glob("*/Backtesting/parameters.cbotset")),
        start_ts=started,
        end_ts=stopped,
    )
    report_html, report_candidates = _discover_best_file(
        paths=sorted(CTRADER_CBOT_ROOT.glob("*/Backtesting/report.html")),
        start_ts=started,
        end_ts=stopped,
    )
    journal, journal_candidates = _discover_best_file(
        paths=sorted(CTRADER_JOURNAL_ROOT.glob("Journal-*.txt")),
        start_ts=started,
        end_ts=stopped,
    )
    return {
        "events_json": str(events) if events is not None else None,
        "cbot_log": str(cbot_log) if cbot_log is not None else None,
        "parameters_cbotset": str(params) if params is not None else None,
        "report_html": str(report_html) if report_html is not None else None,
        "journal_log": str(journal) if journal is not None else None,
        "candidates": {
            "events_json": events_candidates,
            "cbot_log": cbot_log_candidates,
            "parameters_cbotset": params_candidates,
            "report_html": report_candidates,
            "journal_log": journal_candidates,
        },
    }


def _wait_for_http(url: str, *, timeout_sec: float, pid: int | None = None) -> bool:
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        if pid is not None and not _pid_is_running(pid):
            return False
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if 200 <= int(resp.status) < 500:
                    return True
        except urllib.error.HTTPError as exc:
            if 200 <= int(exc.code) < 500:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _stop_pid(pid: int, *, timeout_sec: float = 10.0) -> bool:
    if not _pid_is_running(pid):
        return True
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            return True
        time.sleep(0.2)
    if _pid_is_running(pid):
        os.kill(pid, signal.SIGKILL)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            return True
        time.sleep(0.1)
    return not _pid_is_running(pid)


def _ensure_no_conflicting_listener(
    *,
    host: str,
    port: int,
    replace_active: bool,
) -> None:
    active = _read_active_session()
    if active is not None:
        active_pid = active.get("api_pid")
        active_host = str(active.get("api_host", "127.0.0.1"))
        active_port = int(active.get("api_port", 8000))
        if _pid_is_running(active_pid) and active_host == host and active_port == int(port):
            if not replace_active:
                raise RuntimeError(
                    f"active debug session already using {host}:{port}: run_id={active.get('run_id')}"
                )
            run_down(run_id=str(active.get("run_id", "")), clear_active=True)
    if _port_is_open(host, port):
        raise RuntimeError(
            f"port already in use by a non-session process: {host}:{port}. "
            "Stop it or choose another PORT."
        )


def _start_api(
    *,
    run_id: str,
    host: str,
    port: int,
    db_path: Path,
    http_trace_path: Path,
    models_dir: Path,
    history_dir: Path,
    missing_month_policy: str,
    historical_preflight_mode: str,
    historical_prediction_universe_mode: str,
    record_raw_ticks: bool,
    start_timeout_sec: float,
) -> tuple[int, Path]:
    DEBUG_LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = DEBUG_LOG_ROOT / f"{run_id}.log"
    env = os.environ.copy()
    env["BEHEMOTH_GOVERNANCE_MODE"] = "historical_auto"
    env["BEHEMOTH_GOVERNANCE_HISTORY_DIR"] = str(history_dir)
    env["BEHEMOTH_GOVERNANCE_MISSING_MONTH_POLICY"] = str(missing_month_policy)
    env["BEHEMOTH_HISTORICAL_PREFLIGHT_MODE"] = str(historical_preflight_mode)
    env["BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE"] = str(historical_prediction_universe_mode)
    env["BEHEMOTH_MODELS_DIR"] = str(models_dir)
    env["BEHEMOTH_RECORD_RAW_TICKS"] = "true" if record_raw_ticks else "false"
    env["BEHEMOTH_STATE_DB"] = str(db_path)
    env["BEHEMOTH_DEBUG_RUN_ID"] = str(run_id)
    env["BEHEMOTH_DEBUG_HTTP_TRACE"] = "true"
    env["BEHEMOTH_DEBUG_HTTP_TRACE_PATH"] = str(http_trace_path)
    cmd = [
        "uv",
        "run",
        "uvicorn",
        "src.behemoth.api.server:app",
        "--host",
        str(host),
        "--port",
        str(port),
    ]
    with log_path.open("ab") as log_handle:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    health_url = f"http://{host}:{port}/health"
    if not _wait_for_http(health_url, timeout_sec=start_timeout_sec, pid=proc.pid):
        _stop_pid(proc.pid, timeout_sec=2.0)
        tail = _tail_file(log_path)
        raise RuntimeError(
            f"API failed to become healthy on {health_url}. "
            f"log_tail={tail!r}"
        )
    return int(proc.pid), log_path


def _build_package(
    *,
    source: str,
    symbol: str,
    tick_root: Path,
    start_ts: str,
    end_ts: str,
    package_dir: Path,
    overwrite_package: bool,
    comparison_anchor_ts: str | None,
    ticks_before_anchor: int,
    ticks_after_anchor: int,
) -> tuple[Path, Path]:
    if str(source).lower() != "histdata":
        raise NotImplementedError("Only SOURCE=histdata is implemented in this session manager.")
    manifest_path, summary_path, _ = export_custom_data_run(
        symbol=str(symbol),
        tick_root=tick_root,
        start_ts=str(start_ts),
        end_ts=str(end_ts),
        out_dir=package_dir,
        overwrite=bool(overwrite_package),
        anchor_ts=(str(comparison_anchor_ts).strip() or None),
        ticks_before_anchor=int(ticks_before_anchor),
        ticks_after_anchor=int(ticks_after_anchor),
    )
    return manifest_path, summary_path


def run_up(
    *,
    source: str,
    symbol: str,
    start_ts: str,
    end_ts: str,
    run_id: str | None = None,
    tick_root: Path = DEFAULT_TICK_ROOT,
    host: str = "127.0.0.1",
    port: int = 8000,
    start_api: bool = True,
    replace_active: bool = True,
    reset_db: bool = True,
    overwrite_package: bool = True,
    record_raw_ticks: bool = True,
    start_timeout_sec: float = 20.0,
    models_dir: Path = REPO_ROOT / "models" / "oco",
    history_dir: Path = REPO_ROOT / "configs" / "research" / "governance" / "oco_history",
    missing_month_policy: str = "error",
    historical_preflight_mode: str = "warn",
    historical_prediction_universe_mode: str = "tolerant",
    comparison_anchor_ts: str | None = None,
    ticks_before_anchor: int = 0,
    ticks_after_anchor: int = 0,
) -> dict[str, Any]:
    sym = str(symbol).upper().strip()
    if not sym:
        raise ValueError("symbol is required")
    start_dt = _parse_ts("start_ts", start_ts)
    end_dt = _parse_ts("end_ts", end_ts)
    if not (start_dt < end_dt):
        raise ValueError("start_ts must be earlier than end_ts")
    anchor_ts_effective = (
        str(comparison_anchor_ts).strip() if str(comparison_anchor_ts or "").strip() else str(start_ts)
    )
    sid = str(run_id).strip() if str(run_id or "").strip() else _default_run_id(sym, source, start_ts, end_ts)
    _ensure_no_conflicting_listener(host=host, port=int(port), replace_active=bool(replace_active))

    package_dir = PACKAGE_ROOT / sid
    manifest_path, summary_path = _build_package(
        source=source,
        symbol=sym,
        tick_root=tick_root,
        start_ts=start_ts,
        end_ts=end_ts,
        package_dir=package_dir,
        overwrite_package=bool(overwrite_package),
        comparison_anchor_ts=anchor_ts_effective,
        ticks_before_anchor=int(ticks_before_anchor),
        ticks_after_anchor=int(ticks_after_anchor),
    )
    package_manifest = _read_json(manifest_path)

    DEBUG_DB_ROOT.mkdir(parents=True, exist_ok=True)
    bundle_dir = _bundle_dir(sid)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    db_path = DEBUG_DB_ROOT / f"{sid}.db"
    http_trace_path = bundle_dir / "http_trace.ndjson"
    if bool(reset_db) and db_path.exists():
        db_path.unlink()
    if http_trace_path.exists():
        http_trace_path.unlink()

    session: dict[str, Any] = {
        "run_id": sid,
        "source": str(source).lower(),
        "symbol": sym,
        "start_ts": str(start_ts),
        "end_ts": str(end_ts),
        "tick_root": str(tick_root),
        "package_dir": str(package_dir),
        "package_manifest": str(manifest_path),
        "package_summary_csv": str(summary_path),
        "package_actual_start_ts": str(package_manifest.get("start_ts", "")),
        "package_actual_end_ts": str(package_manifest.get("end_ts", "")),
        "runtime_db": str(db_path),
        "bundle_dir": str(bundle_dir),
        "http_trace_path": str(http_trace_path),
        "api_host": str(host),
        "api_port": int(port),
        "api_base_url": f"http://{host}:{port}",
        "models_dir": str(models_dir),
        "history_dir": str(history_dir),
        "missing_month_policy": str(missing_month_policy),
        "historical_preflight_mode": str(historical_preflight_mode),
        "historical_prediction_universe_mode": str(historical_prediction_universe_mode),
        "record_raw_ticks": bool(record_raw_ticks),
        "recommended_cbot": {
            "api_base_url": f"http://{host}:{port}",
            "enable_tick_batch": True,
            "tick_batch_size": 20,
            "tick_flush_ms": 100,
            "tick_queue_cap": 20000,
            "warmup_ticks": 30000,
        },
        "recommended_backtest": {
            "start_ts": str(anchor_ts_effective),
            "end_ts": str(end_ts),
            "ticks_before_anchor": int(ticks_before_anchor),
            "ticks_after_anchor": int(ticks_after_anchor),
        },
        "status": "prepared",
        "created_at_utc": _utcnow(),
        "updated_at_utc": _utcnow(),
        "session_file": str(_session_file(sid)),
    }

    if start_api:
        pid, log_path = _start_api(
            run_id=sid,
            host=host,
            port=int(port),
            db_path=db_path,
            http_trace_path=http_trace_path,
            models_dir=models_dir,
            history_dir=history_dir,
            missing_month_policy=missing_month_policy,
            historical_preflight_mode=historical_preflight_mode,
            historical_prediction_universe_mode=historical_prediction_universe_mode,
            record_raw_ticks=bool(record_raw_ticks),
            start_timeout_sec=float(start_timeout_sec),
        )
        session["api_pid"] = int(pid)
        session["api_log"] = str(log_path)
        session["status"] = "running"
        session["api_running"] = True
        session["api_started_at_utc"] = _utcnow()
    else:
        session["api_pid"] = None
        session["api_log"] = str(DEBUG_LOG_ROOT / f"{sid}.log")
        session["api_running"] = False

    session["updated_at_utc"] = _utcnow()
    _write_json(_session_file(sid), session)
    _write_active_session(session)
    return session


def _finalize_debug_bundle(session: dict[str, Any]) -> dict[str, Any]:
    run_id = str(session.get("run_id", "")).strip()
    if not run_id:
        return session

    bundle_dir = Path(str(session.get("bundle_dir", _bundle_dir(run_id))))
    bundle_dir.mkdir(parents=True, exist_ok=True)

    discovered = _discover_ctrader_artifacts(session)
    session["discovered_ctrader_artifacts"] = discovered

    runtime_db = Path(str(session.get("runtime_db", "")))
    api_log = Path(str(session.get("api_log", "")))
    http_trace = Path(str(session.get("http_trace_path", "")))

    session["bundle_runtime_db"] = _copy_if_exists(runtime_db, bundle_dir / "runtime.db")
    session["bundle_api_log"] = _copy_if_exists(api_log, bundle_dir / "api.log")
    session["bundle_http_trace"] = _copy_if_exists(http_trace, bundle_dir / "http_trace.ndjson")
    session["bundle_cbot_log"] = _copy_if_exists(
        Path(discovered["cbot_log"]) if discovered.get("cbot_log") else None,
        bundle_dir / "cbot.log",
    )
    session["bundle_ctrader_events"] = _copy_if_exists(
        Path(discovered["events_json"]) if discovered.get("events_json") else None,
        bundle_dir / "events.json",
    )
    session["bundle_cbot_parameters"] = _copy_if_exists(
        Path(discovered["parameters_cbotset"]) if discovered.get("parameters_cbotset") else None,
        bundle_dir / "parameters.cbotset",
    )
    session["bundle_report_html"] = _copy_if_exists(
        Path(discovered["report_html"]) if discovered.get("report_html") else None,
        bundle_dir / "report.html",
    )
    session["bundle_journal_log"] = _copy_if_exists(
        Path(discovered["journal_log"]) if discovered.get("journal_log") else None,
        bundle_dir / "journal.txt",
    )

    session["updated_at_utc"] = _utcnow()
    _write_json(_session_file(run_id), session)
    bundle_session_path = bundle_dir / "session.json"
    _write_json(bundle_session_path, session)

    outputs = build_debug_bundle(session_path=bundle_session_path, bundle_dir=bundle_dir)
    session.update(outputs)
    session["bundle_session_json"] = str(bundle_session_path)
    session["status"] = "finalized"
    session["updated_at_utc"] = _utcnow()
    _write_json(_session_file(run_id), session)
    _write_json(bundle_session_path, session)
    return session


def run_down(*, run_id: str | None = None, clear_active: bool = True) -> dict[str, Any]:
    if str(run_id or "").strip():
        session = _load_session(str(run_id).strip())
    else:
        session = _read_active_session()
        if session is None:
            raise FileNotFoundError("no active cTrader debug session")

    pid = session.get("api_pid")
    was_running = _pid_is_running(pid)
    if was_running:
        _stop_pid(int(pid))

    session["status"] = "stopped"
    session["api_running"] = False
    session["stopped_at_utc"] = _utcnow()
    session["updated_at_utc"] = _utcnow()
    _write_json(_session_file(str(session["run_id"])), session)
    session = _finalize_debug_bundle(session)

    active = _read_active_session()
    if (
        bool(clear_active)
        and active is not None
        and str(active.get("run_id", "")) == str(session.get("run_id", ""))
    ):
        _clear_active_session()
    return session


def run_status(*, run_id: str | None = None) -> dict[str, Any]:
    if str(run_id or "").strip():
        session = _load_session(str(run_id).strip())
    else:
        session = _read_active_session()
        if session is None:
            return {
                "status": "no_active_session",
                "active_session_path": str(ACTIVE_SESSION_PATH),
                "active_package_pointer_path": str(ACTIVE_PACKAGE_POINTER_PATH),
            }

    pid = session.get("api_pid")
    host = str(session.get("api_host", "127.0.0.1"))
    port = int(session.get("api_port", 8000))
    active = _read_active_session()
    session["api_running"] = _pid_is_running(pid)
    session["port_open"] = _port_is_open(host, port)
    session["active_session"] = bool(
        active is not None
        and str(active.get("run_id", "")) == str(session.get("run_id", ""))
    )
    session["updated_at_utc"] = _utcnow()
    return session


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage cTrader debug sessions")
    sub = p.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="Export HistData package and start isolated API runtime")
    up.add_argument("--source", default="histdata")
    up.add_argument("--symbol", required=True)
    up.add_argument("--start-ts", required=True)
    up.add_argument("--end-ts", required=True)
    up.add_argument("--run-id", default="")
    up.add_argument("--tick-root", default=str(DEFAULT_TICK_ROOT))
    up.add_argument("--host", default="127.0.0.1")
    up.add_argument("--port", type=int, default=8000)
    up.add_argument("--start-api", default="true", choices=["true", "false"])
    up.add_argument("--replace-active", default="true", choices=["true", "false"])
    up.add_argument("--reset-db", default="true", choices=["true", "false"])
    up.add_argument("--overwrite-package", default="true", choices=["true", "false"])
    up.add_argument("--record-raw-ticks", default="true", choices=["true", "false"])
    up.add_argument("--start-timeout-sec", type=float, default=20.0)
    up.add_argument("--models-dir", default=str(REPO_ROOT / "models" / "oco"))
    up.add_argument(
        "--history-dir",
        default=str(REPO_ROOT / "configs" / "research" / "governance" / "oco_history"),
    )
    up.add_argument("--missing-month-policy", default="error")
    up.add_argument("--historical-preflight-mode", default="warn")
    up.add_argument("--historical-prediction-universe-mode", default="tolerant")
    up.add_argument("--comparison-anchor-ts", default="")
    up.add_argument("--ticks-before-anchor", type=int, default=0)
    up.add_argument("--ticks-after-anchor", type=int, default=0)

    down = sub.add_parser("down", help="Stop API for an existing debug session")
    down.add_argument("--run-id", default="")
    down.add_argument("--clear-active", default="true", choices=["true", "false"])

    status = sub.add_parser("status", help="Show the current debug session")
    status.add_argument("--run-id", default="")

    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "up":
        out = run_up(
            source=str(args.source),
            symbol=str(args.symbol),
            start_ts=str(args.start_ts),
            end_ts=str(args.end_ts),
            run_id=str(args.run_id).strip() or None,
            tick_root=Path(str(args.tick_root)),
            host=str(args.host),
            port=int(args.port),
            start_api=_bool_arg(str(args.start_api)),
            replace_active=_bool_arg(str(args.replace_active)),
            reset_db=_bool_arg(str(args.reset_db)),
            overwrite_package=_bool_arg(str(args.overwrite_package)),
            record_raw_ticks=_bool_arg(str(args.record_raw_ticks)),
            start_timeout_sec=float(args.start_timeout_sec),
            models_dir=Path(str(args.models_dir)),
            history_dir=Path(str(args.history_dir)),
            missing_month_policy=str(args.missing_month_policy),
            historical_preflight_mode=str(args.historical_preflight_mode),
            historical_prediction_universe_mode=str(args.historical_prediction_universe_mode),
            comparison_anchor_ts=(str(args.comparison_anchor_ts).strip() or None),
            ticks_before_anchor=int(args.ticks_before_anchor),
            ticks_after_anchor=int(args.ticks_after_anchor),
        )
    elif args.command == "down":
        out = run_down(
            run_id=str(args.run_id).strip() or None,
            clear_active=_bool_arg(str(args.clear_active)),
        )
    else:
        out = run_status(run_id=str(args.run_id).strip() or None)

    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
