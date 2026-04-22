from __future__ import annotations

import sys
from pathlib import Path

import pytest

import scripts.run_jforex_live as run_jforex_live
from src.behemoth.live_restart.reconciliation import write_runtime_session_metadata


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

    def fake_start_live_runner(cfg: run_jforex_live.RunConfig) -> _FakeProc:
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
        run_jforex_live, "_start_live_runner", lambda cfg: _FakeProc(returncode=0, pid=20002)
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
        run_jforex_live, "_start_live_runner", lambda cfg: _FakeProc(returncode=0, pid=20002)
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

    assert active_state.exists()
    assert live_state.exists()
    assert (runtime_dir / "live_runtime_session.json").exists()
    assert (runtime_dir / "live_restart_reconciliation.json").exists()


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
        run_jforex_live, "_start_live_runner", lambda cfg: _FakeProc(returncode=0, pid=20002)
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
