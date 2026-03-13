from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import scripts.manage_ctrader_debug_session as session_mgr


def _write_hist_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def test_run_up_writes_session_and_active_files(tmp_path: Path, monkeypatch) -> None:
    tick_root = tmp_path / "tick"
    _write_hist_parquet(
        tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet",
        [
            {"timestamp": "2025-07-07T00:00:00Z", "bid": 1.1000, "ask": 1.1002},
            {"timestamp": "2025-07-07T00:00:01Z", "bid": 1.1001, "ask": 1.1003},
        ],
    )

    monkeypatch.setattr(session_mgr, "ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(session_mgr, "SESSIONS_ROOT", tmp_path / "artifacts" / "sessions")
    monkeypatch.setattr(session_mgr, "PACKAGE_ROOT", tmp_path / "artifacts" / "packages")
    monkeypatch.setattr(session_mgr, "ACTIVE_SESSION_PATH", tmp_path / "artifacts" / "active_session.json")
    monkeypatch.setattr(
        session_mgr,
        "ACTIVE_PACKAGE_POINTER_PATH",
        tmp_path / "artifacts" / "active_package.txt",
    )
    monkeypatch.setattr(session_mgr, "DEBUG_DB_ROOT", tmp_path / "db")
    monkeypatch.setattr(session_mgr, "DEBUG_LOG_ROOT", tmp_path / "logs")
    monkeypatch.setattr(session_mgr, "DEBUG_BUNDLE_ROOT", tmp_path / "artifacts" / "debug_runs")
    monkeypatch.setattr(session_mgr, "CTRADER_CBOT_ROOT", tmp_path / "ctrader" / "cBots")
    monkeypatch.setattr(session_mgr, "CTRADER_JOURNAL_ROOT", tmp_path / "ctrader" / "journals")

    session = session_mgr.run_up(
        source="histdata",
        symbol="EURUSD",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:02Z",
        run_id="eurusd_debug_case",
        tick_root=tick_root,
        start_api=False,
        replace_active=True,
        reset_db=True,
        overwrite_package=True,
    )

    session_file = Path(session["session_file"])
    assert session_file.exists()
    assert session["status"] == "prepared"
    assert Path(session["package_manifest"]).exists()
    assert Path(session["package_summary_csv"]).exists()
    assert session_mgr.ACTIVE_SESSION_PATH.exists()
    assert session_mgr.ACTIVE_PACKAGE_POINTER_PATH.exists()
    assert session_mgr.ACTIVE_PACKAGE_POINTER_PATH.read_text(encoding="utf-8").strip() == str(
        Path(session["package_dir"])
    )

    active = json.loads(session_mgr.ACTIVE_SESSION_PATH.read_text(encoding="utf-8"))
    assert active["run_id"] == "eurusd_debug_case"
    assert active["runtime_db"].endswith("eurusd_debug_case.db")


def test_run_down_marks_session_stopped_and_clears_active(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_mgr, "ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(session_mgr, "SESSIONS_ROOT", tmp_path / "artifacts" / "sessions")
    monkeypatch.setattr(session_mgr, "PACKAGE_ROOT", tmp_path / "artifacts" / "packages")
    monkeypatch.setattr(session_mgr, "ACTIVE_SESSION_PATH", tmp_path / "artifacts" / "active_session.json")
    monkeypatch.setattr(
        session_mgr,
        "ACTIVE_PACKAGE_POINTER_PATH",
        tmp_path / "artifacts" / "active_package.txt",
    )
    monkeypatch.setattr(session_mgr, "DEBUG_DB_ROOT", tmp_path / "db")
    monkeypatch.setattr(session_mgr, "DEBUG_LOG_ROOT", tmp_path / "logs")
    monkeypatch.setattr(session_mgr, "DEBUG_BUNDLE_ROOT", tmp_path / "artifacts" / "debug_runs")
    monkeypatch.setattr(session_mgr, "CTRADER_CBOT_ROOT", tmp_path / "ctrader" / "cBots")
    monkeypatch.setattr(session_mgr, "CTRADER_JOURNAL_ROOT", tmp_path / "ctrader" / "journals")

    session_mgr.SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    session = {
        "run_id": "eurusd_debug_case",
        "api_pid": None,
        "api_host": "127.0.0.1",
        "api_port": 8000,
        "package_dir": str(tmp_path / "artifacts" / "packages" / "eurusd_debug_case"),
        "runtime_db": str(tmp_path / "db" / "eurusd_debug_case.db"),
        "api_log": str(tmp_path / "logs" / "eurusd_debug_case.log"),
        "http_trace_path": str(tmp_path / "artifacts" / "debug_runs" / "eurusd_debug_case" / "http_trace.ndjson"),
        "bundle_dir": str(tmp_path / "artifacts" / "debug_runs" / "eurusd_debug_case"),
        "symbol": "EURUSD",
        "start_ts": "2025-07-07T00:00:00Z",
        "end_ts": "2025-07-07T00:10:00Z",
        "status": "running",
        "session_file": str(session_mgr.SESSIONS_ROOT / "eurusd_debug_case.json"),
    }
    Path(session["session_file"]).write_text(json.dumps(session), encoding="utf-8")
    Path(session["api_log"]).write_text("api log\n", encoding="utf-8")
    Path(session["http_trace_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(session["http_trace_path"]).write_text("", encoding="utf-8")
    session_mgr._write_active_session(session)

    out = session_mgr.run_down(run_id="eurusd_debug_case", clear_active=True)
    assert out["status"] == "finalized"
    assert "stopped_at_utc" in out
    assert not session_mgr.ACTIVE_SESSION_PATH.exists()
    assert not session_mgr.ACTIVE_PACKAGE_POINTER_PATH.exists()
    assert Path(out["bundle_session_json"]).exists()
    assert Path(out["joined_timeline_csv"]).exists()
    assert Path(out["debug_summary_csv"]).exists()

    saved = json.loads(Path(session["session_file"]).read_text(encoding="utf-8"))
    assert saved["status"] == "finalized"
