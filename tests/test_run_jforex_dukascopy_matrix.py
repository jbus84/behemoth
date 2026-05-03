"""Tests for JForex dukascopy matrix runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from scripts.run_jforex_dukascopy_matrix import (
    RunConfig,
    _load_aligned_warmup_ticks,
    main,
    _next_available_port,
    _parse_args,
    _prediction_path,
    _run_jforex_tester,
    _stage14_artifact_paths,
    _wait_for_artifacts_then_kill,
    _with_mise_trusted_paths,
)


def test_cli_help_runs_when_executed_as_script() -> None:
    repo = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "run_jforex_dukascopy_matrix.py"), "--help"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--warmup-ticks" in result.stdout


def test_parse_args_auto_computes_warmup_ticks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    warmup_calls: dict[str, object] = {}
    align_calls: dict[str, object] = {}

    def fake_compute_required_warmup_ticks(**kwargs: object) -> int:
        warmup_calls.update(kwargs)
        return 346800

    def fake_compute_bar_align_ticks(**kwargs: object) -> int:
        align_calls.update(kwargs)
        return 1000

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_dukascopy_matrix.py",
            "--symbols",
            "EURUSD,USDJPY",
            "--model-month",
            "2026-04",
            "--history-dir",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix.compute_required_warmup_ticks",
        fake_compute_required_warmup_ticks,
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix.compute_bar_align_ticks",
        fake_compute_bar_align_ticks,
    )

    cfg = _parse_args()

    assert cfg.warmup_ticks == 346800
    assert cfg.bar_align_ticks == 1000
    assert cfg.universe_mode == "exact"
    expected_calls = {
        "symbols": ("EURUSD", "USDJPY"),
        "locked_predictions_dir": tmp_path,
        "model_month": "2026-04",
    }
    assert warmup_calls == expected_calls
    assert align_calls == expected_calls


def _make_proc(returncode: int | None = None) -> MagicMock:
    """Create a mock Popen-like process."""
    proc = MagicMock()
    proc.pid = 99999
    proc.returncode = returncode
    proc.poll.return_value = returncode
    return proc


def _cfg(tmp_path: Path) -> RunConfig:
    return RunConfig(
        symbols=("EURUSD",),
        start_ts="2026-02-04T00:00:00Z",
        end_ts="2026-02-09T00:00:00Z",
        model_month="2026-02",
        models_dir="models/oco_dukascopy_candidate",
        history_dir=str(tmp_path / "history"),
        predictions_dir=str(tmp_path / "predictions"),
        tick_root=str(tmp_path / "ticks"),
        report_dir="data/analysis/backtest_reconcile",
        api_host="127.0.0.1",
        api_port=8000,
        requested_volume_units=10000,
        tick_batch_size=200,
        order_ttl_seconds=900,
        api_timeout_seconds=60,
        metrics_enabled=True,
        metrics_host="127.0.0.1",
        metrics_port_base=9464,
        risk_enabled=False,
        universe_mode="exact",
        ordinal_tolerance=0,
        warmup_ticks=30000,
        lookback_days=31,
        bar_align_ticks=1000,
        tester_completion_timeout_seconds=14400,
    )


def test_prediction_path_prefers_locked_archive(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    locked = Path(cfg.history_dir) / cfg.model_month / "eurusd_oco_locked_predictions.parquet"
    locked.parent.mkdir(parents=True, exist_ok=True)
    locked.write_text("stub")

    assert _prediction_path(cfg, "EURUSD") == str(locked)


def test_prediction_path_falls_back_to_monthly_predictions(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    assert _prediction_path(cfg, "EURUSD") == str(
        Path(cfg.predictions_dir) / "EURUSD_oco_monthly_predictions.parquet"
    )


def test_artifacts_appear_kills_process_and_returns(tmp_path: Path) -> None:
    """When the full Stage 14 artifact set appears, process is killed and function returns."""
    paths = _stage14_artifact_paths(tmp_path, "EURUSD")
    proc = _make_proc(returncode=None)  # still running

    for path in paths:
        path.write_text("symbol,value\nEURUSD,1\n")

    with patch("os.killpg") as mock_kill:
        _wait_for_artifacts_then_kill(
            proc=proc,
            artifact_paths=paths,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=5.0,
        )
    mock_kill.assert_called_once()


def test_process_exits_nonzero_before_csv_raises(tmp_path: Path) -> None:
    """If process exits with non-zero before CSV appears, CalledProcessError is raised."""
    paths = _stage14_artifact_paths(tmp_path, "EURUSD")
    proc = _make_proc(returncode=1)  # already exited with error

    with pytest.raises(subprocess.CalledProcessError):
        _wait_for_artifacts_then_kill(
            proc=proc,
            artifact_paths=paths,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=5.0,
        )


def test_process_exits_zero_before_csv_raises(tmp_path: Path) -> None:
    """A clean process exit without the full artifact set is still a failed replay."""
    paths = _stage14_artifact_paths(tmp_path, "EURUSD")
    proc = _make_proc(returncode=0)  # exited cleanly

    with pytest.raises(RuntimeError, match="did not produce complete Stage 14 artifacts"):
        _wait_for_artifacts_then_kill(
            proc=proc,
            artifact_paths=paths,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=5.0,
        )


def test_timeout_raises_if_csv_never_appears(tmp_path: Path) -> None:
    """If CSV never appears within timeout, TimeoutError is raised."""
    paths = _stage14_artifact_paths(tmp_path, "EURUSD")
    proc = _make_proc(returncode=None)  # still running, never writes CSV

    with pytest.raises(TimeoutError):
        _wait_for_artifacts_then_kill(
            proc=proc,
            artifact_paths=paths,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=0.3,  # short timeout for test speed
        )


def test_missing_summary_file_is_not_treated_as_complete(tmp_path: Path) -> None:
    """A lone runtime events CSV is not enough; all Stage 14 artifacts must be fresh."""
    paths = _stage14_artifact_paths(tmp_path, "EURUSD")
    paths[0].write_text("event_ts_utc,symbol,category,event_name,pass,detail\n")
    proc = _make_proc(returncode=None)

    with pytest.raises(TimeoutError):
        _wait_for_artifacts_then_kill(
            proc=proc,
            artifact_paths=paths,
            poll_interval_sec=0.05,
            settle_sec=0.0,
            timeout_sec=0.3,
        )


def test_run_jforex_tester_clears_stale_stage14_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)
    cfg = RunConfig(**{**cfg.__dict__, "report_dir": "reports"})
    report_dir = tmp_path / "reports"
    report_dir.mkdir(parents=True)
    runtime_dir = report_dir / "runtime"
    runtime_dir.mkdir(parents=True)

    stale_paths = _stage14_artifact_paths(report_dir, "EURUSD")
    for path in stale_paths:
        path.write_text("stale\n")
    (runtime_dir / "active_oco_state.json").write_text("{}\n")

    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")
    monkeypatch.setattr("scripts.run_jforex_dukascopy_matrix._repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix.subprocess.Popen",
        lambda *args, **kwargs: _make_proc(returncode=None),
    )
    waited: dict[str, object] = {}

    def fake_wait(proc, artifact_paths, **kwargs):
        waited["paths"] = artifact_paths

    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._wait_for_artifacts_then_kill", fake_wait
    )

    _run_jforex_tester(cfg, "EURUSD", api_port=8000, metrics_port=9464)

    assert waited["paths"] == stale_paths
    for path in stale_paths:
        assert not path.exists()
    assert not (runtime_dir / "active_oco_state.json").exists()


def test_with_mise_trusted_paths_adds_repo_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._repo_root",
        lambda: Path("/repo/.worktrees/branch"),
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._repo_common_root",
        lambda: Path("/repo"),
    )

    env = _with_mise_trusted_paths({})

    assert env["MISE_TRUSTED_CONFIG_PATHS"].split(":") == ["/repo", "/repo/.worktrees/branch"]


def test_next_available_port_skips_bound_port(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake_available(_host: str, port: int) -> bool:
        seen.append(port)
        return port != 9464

    monkeypatch.setattr("scripts.run_jforex_dukascopy_matrix._is_port_available", fake_available)

    assert _next_available_port("127.0.0.1", 9464, max_attempts=3) == 9465
    assert seen == [9464, 9465]


def test_main_uses_available_api_port_per_symbol(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    cfg = RunConfig(
        symbols=("EURUSD",),
        start_ts="2025-04-07T00:00:00Z",
        end_ts="2025-04-09T00:00:00Z",
        model_month="2025-07",
        models_dir="models/oco",
        history_dir="configs/research/governance/oco_history_dukascopy_candidate",
        predictions_dir="data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap",
        tick_root="/tmp/ticks",
        report_dir="data/analysis/backtest_reconcile",
        api_host="127.0.0.1",
        api_port=8000,
        requested_volume_units=10000,
        tick_batch_size=200,
        order_ttl_seconds=900,
        api_timeout_seconds=60,
        metrics_enabled=True,
        metrics_host="127.0.0.1",
        metrics_port_base=9464,
        risk_enabled=False,
        universe_mode="exact",
        ordinal_tolerance=0,
        warmup_ticks=30000,
        lookback_days=31,
        bar_align_ticks=1000,
        tester_completion_timeout_seconds=14400,
    )
    proc = _make_proc(returncode=None)
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._parse_args",
        lambda: cfg,
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._next_available_port",
        lambda host, port, max_attempts=100: 8001 if port == 8000 else port,
    )
    def fake_start_api(cfg, symbol, api_port):
        calls["start_api"] = (symbol, api_port)
        return proc

    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._start_api",
        fake_start_api,
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._poll_health",
        lambda proc, base_url, timeout_sec: calls.setdefault("poll_health", base_url),
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._prime_api_with_warmup",
        lambda cfg, symbol, api_port: calls.setdefault("warmup", (symbol, api_port)),
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._run_jforex_tester",
        lambda cfg, symbol, api_port, metrics_port: calls.setdefault(
            "run_tester", (symbol, api_port, metrics_port)
        ),
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._stop_process",
        lambda proc: calls.setdefault("stopped", True),
    )
    monkeypatch.setattr(
        "scripts.run_jforex_dukascopy_matrix._read_process_tail",
        lambda proc: "",
    )

    main()

    assert calls["start_api"] == ("EURUSD", 8001)
    assert calls["poll_health"] == "http://127.0.0.1:8001"
    assert calls["warmup"] == ("EURUSD", 8001)
    assert calls["run_tester"] == ("EURUSD", 8001, 9464)
    assert "starting API on port 8001" in capsys.readouterr().out


def test_load_aligned_warmup_ticks_uses_full_history_modulo(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg = RunConfig(
        **{
            **cfg.__dict__,
            "start_ts": "2025-07-07T00:00:00Z",
            "end_ts": "2025-07-08T00:00:00Z",
            "tick_root": str(tmp_path / "ticks"),
            "warmup_ticks": 5,
            "lookback_days": 1,
            "bar_align_ticks": 4,
        }
    )
    symbol_dir = Path(cfg.tick_root) / "EURUSD"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = symbol_dir / "aligned.parquet"

    con = duckdb.connect()
    con.execute(
        """
        COPY (
            SELECT * FROM (VALUES
                (TIMESTAMPTZ '2025-07-05T00:00:01Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:02Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:03Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:04Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-05T00:00:05Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:01Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:02Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:03Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:04Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:05Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:06Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:07Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:08Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:09Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-06T00:00:10Z', 1.1000, 1.1001),
                (TIMESTAMPTZ '2025-07-07T00:00:01Z', 1.1000, 1.1001)
            ) AS t(timestamp, bid, ask)
        ) TO ? (FORMAT PARQUET)
        """,
        [str(parquet_path)],
    )
    con.close()

    ticks = _load_aligned_warmup_ticks(cfg, "EURUSD")

    assert [tick["timestamp"] for tick in ticks] == [
        "2025-07-06T00:00:04Z",
        "2025-07-06T00:00:05Z",
        "2025-07-06T00:00:06Z",
        "2025-07-06T00:00:07Z",
        "2025-07-06T00:00:08Z",
        "2025-07-06T00:00:09Z",
        "2025-07-06T00:00:10Z",
    ]
    assert len(ticks) % cfg.bar_align_ticks == 15 % cfg.bar_align_ticks
    assert len(ticks) >= cfg.warmup_ticks
