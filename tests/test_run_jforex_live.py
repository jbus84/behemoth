from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_jforex_live as run_jforex_live
from src.behemoth.live_restart.reconciliation import write_runtime_session_metadata
from src.behemoth.ops.verdicts import RestartEligibility


class _FakeProc:
    def __init__(self, returncode: int | None = None, pid: int = 12345) -> None:
        self._returncode = returncode
        self.returncode = returncode
        self.pid = pid

    def poll(self) -> int | None:
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _write_runtime_files(tmp_path) -> tuple[Path, Path]:
    import duckdb

    runtime_dir = tmp_path / "data/analysis/backtest_reconcile/runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    active_state = runtime_dir / "active_oco_state.json"
    live_state = runtime_dir / "live_state.db"
    active_state.write_text("{}\n", encoding="utf-8")
    con = duckdb.connect(str(live_state))
    con.execute("CREATE TABLE IF NOT EXISTS scratch (id INTEGER)")
    con.close()
    return active_state, live_state


def _ensure_governance_dir(tmp_path: Path) -> Path:
    governance_dir = tmp_path / "configs/research/governance/oco"
    governance_dir.mkdir(parents=True, exist_ok=True)
    return governance_dir


def _write_live_lock(governance_dir: Path, symbol: str, *, model_month: str, live_deployable: bool = True) -> None:
    payload = {
        "symbol": symbol,
        "artifacts": {
            "live_deployable": live_deployable,
            "model_month": model_month,
        },
    }
    (governance_dir / f"{symbol.lower()}_oco_live_lock.json").write_text(
        __import__("json").dumps(payload) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_main_starts_live_runner_before_warmup(monkeypatch, tmp_path, capsys) -> None:
    order: list[str] = []

    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_jforex_live, "_resolve_model_month", lambda cfg: "2026-03")
    monkeypatch.setattr(
        run_jforex_live,
        "_git_metadata",
        lambda repo_root: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_jforex_live, "_has_resume_blocking_git_dirty", lambda repo_root: False)
    _ensure_governance_dir(tmp_path)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")

    api_proc = _FakeProc(returncode=None, pid=20001)
    java_proc = _FakeProc(returncode=0, pid=20002)

    monkeypatch.setattr(
        run_jforex_live.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )

    def fake_start_api(cfg: run_jforex_live.RunConfig) -> _FakeProc:
        order.append("start_api")
        return api_proc

    def fake_poll_health(proc: _FakeProc, base_url: str, timeout_sec: float) -> None:
        order.append("poll_health")

    def fake_start_live_runner(cfg: run_jforex_live.RunConfig, *, allow_new_entries: bool = True) -> _FakeProc:
        order.append("start_live_runner")
        return java_proc

    def fake_warmup(symbols: list[str], base_url: str, timeout_sec: float = 60.0) -> None:
        order.append("warmup")

    def fake_stop_process(proc: _FakeProc | None) -> None:
        order.append(f"stop:{getattr(proc, 'pid', 'none')}")

    monkeypatch.setattr(run_jforex_live, "_start_api", fake_start_api)
    monkeypatch.setattr(run_jforex_live, "_poll_health", fake_poll_health)
    monkeypatch.setattr(run_jforex_live, "_start_live_runner", fake_start_live_runner)
    monkeypatch.setattr(run_jforex_live, "_warmup_symbols", fake_warmup)
    monkeypatch.setattr(run_jforex_live, "_stop_process", fake_stop_process)
    monkeypatch.setattr(run_jforex_live.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_jforex_live.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols",
            "EURUSD,GBPUSD",
            "--report-dir",
            "data/analysis/backtest_reconcile",
        ],
    )

    with pytest.raises(SystemExit, match="1"):
        run_jforex_live.main()

    assert order[:4] == ["start_api", "poll_health", "start_live_runner", "warmup"]
    assert "live runner exited unexpectedly" in capsys.readouterr().err


def test_main_defaults_seed_to_promoted_governance_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    _ensure_governance_dir(tmp_path)
    monkeypatch.setattr(
        run_jforex_live,
        "_git_metadata",
        lambda repo_root: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_jforex_live, "_has_resume_blocking_git_dirty", lambda repo_root: False)
    monkeypatch.delenv("BEHEMOTH_GOVERNANCE_DIR", raising=False)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")

    recorded_run: dict[str, object] = {}

    def fake_run(args, **kwargs):
        recorded_run["args"] = args
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(run_jforex_live.subprocess, "run", fake_run)
    monkeypatch.setattr(run_jforex_live, "_start_api", lambda cfg: _FakeProc(returncode=None, pid=20001))
    monkeypatch.setattr(run_jforex_live, "_poll_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        run_jforex_live, "_start_live_runner", lambda cfg, **kw: _FakeProc(returncode=0, pid=20002)
    )
    monkeypatch.setattr(run_jforex_live, "_warmup_symbols", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_jforex_live, "_stop_process", lambda proc: None)
    monkeypatch.setattr(run_jforex_live.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_jforex_live.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols",
            "EURUSD,GBPUSD",
            "--report-dir",
            "data/analysis/backtest_reconcile",
        ],
    )

    with pytest.raises(SystemExit, match="1"):
        run_jforex_live.main()

    args = recorded_run["args"]
    assert "--governance-dir" in args
    idx = args.index("--governance-dir")
    assert args[idx + 1] == "configs/research/governance/oco"
    model_idx = args.index("--models-dir")
    assert args[model_idx + 1] == "models/oco"
    assert "BEHEMOTH_GOVERNANCE_DIR" not in run_jforex_live.os.environ


def test_build_current_session_metadata_uses_promoted_live_truth(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        run_jforex_live,
        "_git_metadata",
        lambda repo_root: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_jforex_live, "_has_resume_blocking_git_dirty", lambda repo_root: False)
    governance_dir = _ensure_governance_dir(tmp_path)
    _write_live_lock(governance_dir, "EURUSD", model_month="2026-03", live_deployable=True)
    _write_live_lock(governance_dir, "GBPUSD", model_month="2026-03", live_deployable=True)
    _write_live_lock(governance_dir, "AUDUSD", model_month="2026-04", live_deployable=False)

    cfg = run_jforex_live.RunConfig(
        symbols=("EURUSD", "GBPUSD", "AUDUSD"),
        models_dir="models/oco",
        history_dir="configs/research/governance/oco_history_dukascopy_candidate",
        report_dir="data/analysis/backtest_reconcile",
        startup_mode="resume",
        api_host="127.0.0.1",
        api_port=8000,
        requested_volume_units=10000,
        tick_batch_size=200,
        order_ttl_seconds=900,
        api_timeout_seconds=60,
        metrics_enabled=True,
        metrics_host="127.0.0.1",
        metrics_port=9464,
    )

    meta = run_jforex_live._build_current_session_metadata(cfg)

    assert meta.model_month == "2026-03"
    assert meta.symbols == ["EURUSD", "GBPUSD"]


def test_main_resume_preserves_runtime_state(monkeypatch, tmp_path) -> None:
    active_state, live_state = _write_runtime_files(tmp_path)
    runtime_dir = active_state.parent
    governance_dir = _ensure_governance_dir(tmp_path)
    _write_live_lock(governance_dir, "EURUSD", model_month="2026-03", live_deployable=True)
    _write_live_lock(governance_dir, "GBPUSD", model_month="2026-03", live_deployable=True)

    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_jforex_live, "_resolve_model_month", lambda cfg: "2026-03")
    monkeypatch.setattr(
        run_jforex_live,
        "_git_metadata",
        lambda repo_root: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_jforex_live, "_has_resume_blocking_git_dirty", lambda repo_root: False)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")
    monkeypatch.setattr(
        run_jforex_live.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(run_jforex_live, "_start_api", lambda cfg: _FakeProc(returncode=None, pid=20001))
    monkeypatch.setattr(run_jforex_live, "_poll_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        run_jforex_live, "_start_live_runner", lambda cfg, **kw: _FakeProc(returncode=0, pid=20002)
    )
    monkeypatch.setattr(run_jforex_live, "_warmup_symbols", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_jforex_live, "_stop_process", lambda proc: None)
    monkeypatch.setattr(run_jforex_live.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_jforex_live.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols",
            "EURUSD,GBPUSD",
            "--report-dir",
            "data/analysis/backtest_reconcile",
        ],
    )
    write_runtime_session_metadata(
        runtime_dir / "live_runtime_session.json",
        run_jforex_live.RuntimeSessionMetadata(
            git_commit="abc123",
            git_branch="main",
            git_dirty=False,
            repo_root=str(tmp_path),
            model_month="2026-03",
            governance_dir="configs/research/governance/oco",
            lock_fingerprint=run_jforex_live.compute_lock_fingerprint(governance_dir),
            symbols=["EURUSD", "GBPUSD"],
            started_at_utc="2026-04-22T00:00:00Z",
            startup_mode="resume",
        ),
    )

    with pytest.raises(SystemExit, match="1"):
        run_jforex_live.main()


def test_main_fails_before_seed_when_runtime_threshold_json_drifts_from_promoted_lock(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)

    governance_dir = _ensure_governance_dir(tmp_path)
    models_dir = tmp_path / "models/oco"
    models_dir.mkdir(parents=True, exist_ok=True)
    cbm_path = models_dir / "EURUSD_model_2026-03.cbm"
    thr_path = models_dir / "EURUSD_model_2026-03.json"
    cbm_path.write_bytes(b"cbm")
    thr_path.write_text(
        json.dumps(
            {
                "model_month": "2026-03",
                "threshold_source": "rolling_days",
                "rolling_threshold_days": 20,
                "rolling_threshold_min_history": 1000,
                "execution_quantile": 0.9,
                "oco_hold_mode": "from_touch",
                "oco_include_no_touch": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lock_payload = {
        "symbol": "EURUSD",
        "artifacts": {
            "live_deployable": True,
            "model_month": "2026-03",
            "model_cbm_path": "models/oco/EURUSD_model_2026-03.cbm",
            "model_cbm_sha256": _sha(cbm_path),
            "model_threshold_json_path": "models/oco/EURUSD_model_2026-03.json",
            "model_threshold_json_sha256": _sha(thr_path),
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
        },
    }
    (governance_dir / "eurusd_oco_live_lock.json").write_text(
        json.dumps(lock_payload) + "\n",
        encoding="utf-8",
    )

    current_metadata = run_jforex_live.RuntimeSessionMetadata(
        git_commit="abc123",
        git_branch="main",
        git_dirty=False,
        repo_root=str(tmp_path),
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="lockfp",
        symbols=["EURUSD"],
        started_at_utc="2026-04-23T00:00:00Z",
        startup_mode="reset",
    )
    comparison = run_jforex_live.RuntimeContextComparison(
        verdict=run_jforex_live.RestartVerdict.CLEAN_RESUMABLE,
        reasons=[],
    )
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (
            current_metadata,
            None,
            comparison,
            run_jforex_live.RestartEligibilityResult(
                eligibility=RestartEligibility.RESTART_ELIGIBLE,
                allow_new_entries=True,
                reasons=[],
            ),
        ),
    )
    monkeypatch.setattr(run_jforex_live, "write_runtime_session_metadata", lambda *args, **kwargs: None)

    called: list[str] = []

    def fake_run(*args, **kwargs):
        called.append("seed")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(run_jforex_live.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_jforex_live,
        "_start_api",
        lambda cfg: pytest.fail("API should not start when runtime artifacts drift"),
    )
    monkeypatch.setattr(run_jforex_live, "_stop_process", lambda proc: None)
    monkeypatch.setattr(run_jforex_live.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols",
            "EURUSD",
            "--report-dir",
            "data/analysis/backtest_reconcile",
            "--startup-mode",
            "reset",
            "--models-dir",
            "models/oco",
        ],
    )

    with pytest.raises(SystemExit, match="rolling_threshold_min_history"):
        run_jforex_live.main()

    assert called == []


def test_main_reset_runs_archive_cleanup(monkeypatch, tmp_path) -> None:
    _write_runtime_files(tmp_path)
    _ensure_governance_dir(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_jforex_live, "_resolve_model_month", lambda cfg: "2026-03")
    monkeypatch.setattr(
        run_jforex_live,
        "_git_metadata",
        lambda repo_root: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_jforex_live, "_has_resume_blocking_git_dirty", lambda repo_root: False)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")
    monkeypatch.setattr(
        run_jforex_live.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(run_jforex_live, "_consolidate_to_archive", lambda path: calls.append(str(path)))
    monkeypatch.setattr(run_jforex_live, "_start_api", lambda cfg: _FakeProc(returncode=None, pid=20001))
    monkeypatch.setattr(run_jforex_live, "_poll_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        run_jforex_live, "_start_live_runner", lambda cfg, **kw: _FakeProc(returncode=0, pid=20002)
    )
    monkeypatch.setattr(run_jforex_live, "_warmup_symbols", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_jforex_live, "_stop_process", lambda proc: None)
    monkeypatch.setattr(run_jforex_live.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_jforex_live.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols",
            "EURUSD,GBPUSD",
            "--report-dir",
            "data/analysis/backtest_reconcile",
            "--startup-mode",
            "reset",
        ],
    )

    with pytest.raises(SystemExit, match="1"):
        run_jforex_live.main()

    assert calls == [str(tmp_path / "data/analysis/backtest_reconcile/runtime/live_state.db")]


def test_cleanup_runtime_state_force_clears_when_archive_fails(tmp_path, monkeypatch) -> None:
    active_state, live_state = _write_runtime_files(tmp_path)
    paths = {
        "active_state_path": active_state,
        "state_db_path": live_state,
    }

    def fail_archive(path: Path) -> None:
        raise RuntimeError("archive failed")

    monkeypatch.setattr(run_jforex_live, "_consolidate_to_archive", fail_archive)

    run_jforex_live._cleanup_runtime_state(paths)

    assert not active_state.exists()
    assert not live_state.exists()


def test_script_entrypoint_supports_direct_execution_without_pythonpath() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/run_jforex_live.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--startup-mode" in result.stdout


def test_reconcile_startup_captures_broker_snapshot_on_resume(monkeypatch, tmp_path) -> None:
    _ensure_governance_dir(tmp_path)
    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        run_jforex_live,
        "_build_current_session_metadata",
        lambda cfg: run_jforex_live.RuntimeSessionMetadata(
            git_commit="abc123",
            git_branch="main",
            git_dirty=False,
            repo_root=str(tmp_path),
            model_month="2026-03",
            governance_dir="configs/research/governance/oco",
            lock_fingerprint="fp",
            symbols=["EURUSD"],
            started_at_utc="2026-04-22T00:00:00Z",
            startup_mode="resume",
        ),
    )
    monkeypatch.setattr(
        run_jforex_live,
        "inspect_runtime_files",
        lambda *args, **kwargs: run_jforex_live.RuntimeFileSnapshot(
            runtime_dir=str(tmp_path / "runtime"),
            live_state_db_path=str(tmp_path / "runtime/live_state.db"),
            active_oco_state_path=str(tmp_path / "runtime/active_oco_state.json"),
            runtime_session_path=str(tmp_path / "runtime/live_runtime_session.json"),
            live_state_exists=False,
            live_state_readable=False,
            active_oco_state_exists=False,
            active_oco_state_parsed=False,
            runtime_session_exists=False,
            runtime_session_parsed=False,
        ),
    )
    monkeypatch.setattr(
        run_jforex_live,
        "inspect_local_runtime_state",
        lambda *args, **kwargs: run_jforex_live.LocalRuntimeStateSummary(
            active_reservation_count=0,
            active_scan_count=0,
            active_reservation_ids=[],
            active_scan_ids=[],
        ),
    )
    monkeypatch.setattr(
        run_jforex_live,
        "load_runtime_session_metadata",
        lambda path: None,
        raising=False,
    )
    captured: list[str] = []
    monkeypatch.setattr(
        run_jforex_live,
        "_capture_broker_snapshot",
        lambda cfg, paths: captured.append(str(paths["broker_snapshot_path"])),
    )
    monkeypatch.setattr(
        run_jforex_live,
        "load_broker_snapshot",
        lambda path: run_jforex_live.BrokerSnapshot(captured_at_utc="2026-04-22T00:00:01Z", orders=[]),
    )
    monkeypatch.setattr(
        run_jforex_live,
        "compare_runtime_context",
        lambda *args, **kwargs: run_jforex_live.RuntimeContextComparison(
            verdict=run_jforex_live.RestartVerdict.CLEAN_RESUMABLE,
            reasons=[],
        ),
    )
    monkeypatch.setattr(run_jforex_live, "write_reconciliation_report", lambda *args, **kwargs: None)
    cfg = run_jforex_live.RunConfig(
        symbols=("EURUSD",),
        models_dir="models/oco",
        history_dir="configs/research/governance/oco_history_dukascopy_candidate",
        report_dir="data/analysis/backtest_reconcile",
        startup_mode="resume",
        api_host="127.0.0.1",
        api_port=8000,
        requested_volume_units=10000,
        tick_batch_size=200,
        order_ttl_seconds=900,
        api_timeout_seconds=60,
        metrics_enabled=True,
        metrics_host="127.0.0.1",
        metrics_port=9464,
    )

    run_jforex_live._reconcile_startup(cfg, run_jforex_live._runtime_paths(cfg))

    assert captured == [str(tmp_path / "data/analysis/backtest_reconcile/runtime/live_broker_snapshot.json")]


def test_main_resume_incompatible_prints_operator_summary(monkeypatch, tmp_path, capsys) -> None:
    _ensure_governance_dir(tmp_path)
    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (
            run_jforex_live.RuntimeSessionMetadata(
                git_commit="abc123",
                git_branch="main",
                git_dirty=False,
                repo_root=str(tmp_path),
                model_month="2026-03",
                governance_dir="configs/research/governance/oco",
                lock_fingerprint="fp",
                symbols=["EURUSD"],
                started_at_utc="2026-04-22T00:00:00Z",
                startup_mode="resume",
            ),
            None,
            run_jforex_live.RuntimeContextComparison(
                verdict=run_jforex_live.RestartVerdict.INCOMPATIBLE,
                reasons=[
                    "broker-linked symbols do not match broker snapshot symbols",
                    "broker-linked position ids do not match broker snapshot order ids",
                ],
            ),
            run_jforex_live.RestartEligibilityResult(
                eligibility=RestartEligibility.RESTART_BLOCKED,
                allow_new_entries=False,
                reasons=[
                    "broker-linked symbols do not match broker snapshot symbols",
                    "broker-linked position ids do not match broker snapshot order ids",
                ],
            ),
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols",
            "EURUSD",
            "--report-dir",
            "data/analysis/backtest_reconcile",
            "--startup-mode",
            "resume",
        ],
    )

    with pytest.raises(SystemExit, match="1"):
        run_jforex_live.main()

    err = capsys.readouterr().err
    assert "[jforex-live] incompatible live restart metadata; rerun with --startup-mode reset" in err
    assert "[jforex-live] reconciliation report:" in err
    assert "live_restart_reconciliation.json" in err
    assert "[jforex-live] restart summary: startup_mode=resume verdict=incompatible reasons=2" in err
    assert "[jforex-live]   1. broker-linked symbols do not match broker snapshot symbols" in err
    assert "[jforex-live]   2. broker-linked position ids do not match broker snapshot order ids" in err


def test_main_reset_forces_new_entries_true_despite_stale_drain_only_eligibility(
    monkeypatch, tmp_path
) -> None:
    """A reset startup must call _start_live_runner with allow_new_entries=True even
    when the pre-reset eligibility result was DRAIN_ONLY."""
    _write_runtime_files(tmp_path)
    _ensure_governance_dir(tmp_path)
    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_jforex_live, "_resolve_model_month", lambda cfg: "2026-03")
    monkeypatch.setattr(
        run_jforex_live,
        "_git_metadata",
        lambda repo_root: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_jforex_live, "_has_resume_blocking_git_dirty", lambda repo_root: False)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")

    drain_only_eligibility = run_jforex_live.RestartEligibilityResult(
        eligibility=RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY,
        allow_new_entries=False,
        reasons=["stale prior state"],
    )
    current_metadata = run_jforex_live.RuntimeSessionMetadata(
        git_commit="abc123",
        git_branch="main",
        git_dirty=False,
        repo_root=str(tmp_path),
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="lockfp",
        symbols=["EURUSD"],
        started_at_utc="2026-04-25T00:00:00Z",
        startup_mode="reset",
    )
    comparison = run_jforex_live.RuntimeContextComparison(
        verdict=run_jforex_live.RestartVerdict.CLEAN_RESUMABLE,
        reasons=[],
    )
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (current_metadata, None, comparison, drain_only_eligibility),
    )
    monkeypatch.setattr(run_jforex_live, "write_runtime_session_metadata", lambda *args, **kwargs: None)

    captured_allow_new_entries: list[bool] = []

    def fake_start_live_runner(cfg, *, allow_new_entries: bool = True) -> _FakeProc:
        captured_allow_new_entries.append(allow_new_entries)
        return _FakeProc(returncode=0, pid=99999)

    monkeypatch.setattr(run_jforex_live.subprocess, "run", lambda *a, **kw: type("R", (), {"returncode": 0})())
    monkeypatch.setattr(run_jforex_live, "_start_api", lambda cfg: _FakeProc(returncode=None, pid=20001))
    monkeypatch.setattr(run_jforex_live, "_poll_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_jforex_live, "_start_live_runner", fake_start_live_runner)
    monkeypatch.setattr(run_jforex_live, "_warmup_symbols", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_jforex_live, "_stop_process", lambda proc: None)
    monkeypatch.setattr(run_jforex_live.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_jforex_live.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols", "EURUSD",
            "--report-dir", "data/analysis/backtest_reconcile",
            "--startup-mode", "reset",
        ],
    )

    with pytest.raises(SystemExit, match="1"):
        run_jforex_live.main()

    assert captured_allow_new_entries == [True], (
        f"expected allow_new_entries=True for reset startup, got {captured_allow_new_entries}"
    )
