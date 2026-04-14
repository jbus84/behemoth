from __future__ import annotations

import sys

import pytest

import scripts.run_jforex_live as run_jforex_live


class _FakeProc:
    def __init__(self, returncode: int | None = None, pid: int = 12345) -> None:
        self._returncode = returncode
        self.returncode = returncode
        self.pid = pid

    def poll(self) -> int | None:
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        return 0


def test_main_starts_live_runner_before_warmup(monkeypatch, tmp_path, capsys) -> None:
    order: list[str] = []

    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_jforex_live, "_resolve_model_month", lambda cfg: "2026-03")
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
