from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.run_stage12_stage13_certification import (
    _resolve_lock_dir,
    _resolve_model_json,
    _resolve_model_month,
    _run_stage13_matrix_replay,
    main,
    run_stage12_stage13_certification,
)


def test_orchestrator_skips_stage13_when_stage12_fails(tmp_path: Path) -> None:
    result = run_stage12_stage13_certification(
        symbols=["EURUSD"],
        stage12_runner=lambda symbol: {"certification_outcome": "FAIL", "go_decision": "NO_GO"},
        stage13_runner=lambda symbol: (_ for _ in ()).throw(AssertionError("should not run")),
        out_dir=tmp_path,
    )

    assert result[0]["symbol"] == "EURUSD"
    assert result[0]["stage12_certification_outcome"] == "FAIL"
    assert result[0]["stage13_attempted"] is False
    assert result[0]["certification_outcome"] == "FAIL"
    assert result[0]["go_decision"] == "NO_GO"
    summary = pd.read_csv(tmp_path / "stage12_stage13_certification_summary.csv")
    assert summary.loc[0, "certification_outcome"] == "FAIL"
    assert summary.loc[0, "go_decision"] == "NO_GO"


def test_orchestrator_resolves_final_outputs_without_unknown(tmp_path: Path) -> None:
    result = run_stage12_stage13_certification(
        symbols=["GBPUSD"],
        stage12_runner=lambda symbol: {"certification_outcome": "PASS", "go_decision": "GO"},
        stage13_runner=lambda symbol: {"certification_outcome": "PASS", "go_decision": "NO_GO"},
        out_dir=tmp_path,
    )

    row = result[0]
    assert row["certification_outcome"] in {"PASS", "FAIL"}
    assert row["go_decision"] in {"GO", "NO_GO"}
    assert row["go_decision"] == "NO_GO"
    summary = pd.read_csv(tmp_path / "stage12_stage13_certification_summary.csv")
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "NO_GO"


def test_orchestrator_preserves_stage13_nogo_when_certified(tmp_path: Path) -> None:
    result = run_stage12_stage13_certification(
        symbols=["USDCAD"],
        stage12_runner=lambda symbol: {"certification_outcome": "PASS", "go_decision": "GO"},
        stage13_runner=lambda symbol: {"certification_outcome": "PASS", "go_decision": "NO_GO"},
        out_dir=tmp_path,
    )

    row = result[0]
    assert row["certification_outcome"] == "PASS"
    assert row["go_decision"] == "NO_GO"
    summary = pd.read_csv(tmp_path / "stage12_stage13_certification_summary.csv")
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "NO_GO"


def test_resolve_lock_dir_defaults_to_history_dir_and_model_month(tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    resolved = _resolve_lock_dir(None, history_dir, "2025-08")
    assert resolved == history_dir / "2025-08"


def test_stage13_matrix_replay_forwards_models_dir(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "jnlp://example")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, check, capture_output, text):
        captured["cmd"] = cmd
        signal_path = tmp_path / "EURUSD_jforex_signal_parity_summary.csv"
        execution_path = tmp_path / "EURUSD_jforex_execution_parity_summary.csv"
        runtime_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
        pd.DataFrame([{"symbol": "EURUSD", "jforex_signal_parity_pass": True}]).to_csv(signal_path, index=False)
        pd.DataFrame([{"symbol": "EURUSD", "jforex_execution_parity_pass": True}]).to_csv(
            execution_path, index=False
        )
        pd.DataFrame([{"event_name": "predict_cycle", "pass": True}]).to_csv(runtime_path, index=False)
        return _Completed()

    monkeypatch.setattr("scripts.run_stage12_stage13_certification.subprocess.run", _fake_run)

    result = _run_stage13_matrix_replay(
        symbol="EURUSD",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-09T00:00:00Z",
        model_month="2025-08",
        models_dir=Path("models/custom"),
        history_dir=Path("history"),
        predictions_dir=Path("predictions"),
        tick_root=Path("ticks"),
        report_dir=tmp_path,
    )

    assert "--models-dir" in captured["cmd"]
    models_dir_index = captured["cmd"].index("--models-dir")
    assert captured["cmd"][models_dir_index + 1] == "models/custom"
    assert result["signal_pass"] is True
    assert result["execution_pass"] is True


def test_stage13_matrix_replay_forwards_port_overrides(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "jnlp://example")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")
    monkeypatch.setenv("API_PORT", "8012")
    monkeypatch.setenv("METRICS_PORT_BASE", "9480")

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, check, capture_output, text):
        captured["cmd"] = cmd
        pd.DataFrame([{"symbol": "EURUSD", "jforex_signal_parity_pass": True}]).to_csv(
            tmp_path / "EURUSD_jforex_signal_parity_summary.csv", index=False
        )
        pd.DataFrame([{"symbol": "EURUSD", "jforex_execution_parity_pass": True}]).to_csv(
            tmp_path / "EURUSD_jforex_execution_parity_summary.csv", index=False
        )
        pd.DataFrame([{"event_name": "predict_cycle", "pass": True}]).to_csv(
            tmp_path / "EURUSD_jforex_runtime_events.csv", index=False
        )
        return _Completed()

    monkeypatch.setattr("scripts.run_stage12_stage13_certification.subprocess.run", _fake_run)

    _run_stage13_matrix_replay(
        symbol="EURUSD",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-09T00:00:00Z",
        model_month="2025-08",
        models_dir=Path("models/custom"),
        history_dir=Path("history"),
        predictions_dir=Path("predictions"),
        tick_root=Path("ticks"),
        report_dir=tmp_path,
    )

    assert captured["cmd"][captured["cmd"].index("--api-port") + 1] == "8012"
    assert captured["cmd"][captured["cmd"].index("--metrics-port-base") + 1] == "9480"


def test_resolve_model_json_prefers_requested_model_month(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    older = models_dir / "EURUSD_model_2025-07.json"
    newer = models_dir / "EURUSD_model_2026-02.json"
    older.write_text("{}\n")
    newer.write_text("{}\n")

    resolved = _resolve_model_json(models_dir, "EURUSD", "2025-07")

    assert resolved == older


def test_resolve_model_month_uses_latest_available_model_month(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "EURUSD_model_2025-07.json").write_text("{}\n")
    (models_dir / "EURUSD_model_2026-02.json").write_text("{}\n")
    (models_dir / "GBPUSD_model_2026-02.json").write_text("{}\n")

    resolved = _resolve_model_month(None, models_dir, ["EURUSD", "GBPUSD"])

    assert resolved == "2026-02"


def test_stage13_matrix_replay_fails_fast_without_jforex_credentials(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BEHEMOTH_JFOREX_JNLP_URI", raising=False)
    monkeypatch.delenv("BEHEMOTH_JFOREX_USERNAME", raising=False)
    monkeypatch.delenv("BEHEMOTH_JFOREX_PASSWORD", raising=False)

    called = {"subprocess": False}

    def _fake_run(*args, **kwargs):
        called["subprocess"] = True
        raise AssertionError("subprocess.run should not be called without credentials")

    monkeypatch.setattr("scripts.run_stage12_stage13_certification.subprocess.run", _fake_run)

    result = _run_stage13_matrix_replay(
        symbol="EURUSD",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-09T00:00:00Z",
        model_month="2025-08",
        models_dir=Path("models/custom"),
        history_dir=Path("history"),
        predictions_dir=Path("predictions"),
        tick_root=Path("ticks"),
        report_dir=tmp_path,
    )

    assert called["subprocess"] is False
    assert result["signal_pass"] is False
    assert result["execution_pass"] is False
    assert "BEHEMOTH_JFOREX_JNLP_URI" in result["details"]


def test_main_returns_nonzero_when_final_certification_fails(monkeypatch, tmp_path: Path) -> None:
    def _stage12_fail(**kwargs):
        out_dir = kwargs["out_dir"]
        symbol = kwargs["symbol"]
        pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "stage12_api_parity_pass": False,
                    "certification_outcome": "FAIL",
                    "go_decision": "NO_GO",
                }
            ]
        ).to_csv(out_dir / f"{symbol}_stage12_api_parity_summary.csv", index=False)
        return {"certification_outcome": "FAIL", "go_decision": "NO_GO"}

    def _stage13_empty(**kwargs):
        return pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(
        "scripts.run_stage12_stage13_certification._stage12_default_runner",
        _stage12_fail,
    )
    monkeypatch.setattr(
        "scripts.run_stage12_stage13_certification._stage13_default_runner",
        _stage13_empty,
    )

    exit_code = main(
        [
            "--symbols",
            "EURUSD",
            "--models-dir",
            str(tmp_path / "models"),
            "--predictions-dir",
            str(tmp_path / "predictions"),
            "--reconcile-dir",
            str(tmp_path),
            "--out-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 1


def test_main_uses_lock_bundle_predictions_for_stage12(monkeypatch, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "EURUSD_model_2026-02.json").write_text("{}\n")
    missing_predictions_dir = tmp_path / "missing-active-predictions"
    lock_dir = tmp_path / "bundle" / "2026-02"
    lock_dir.mkdir(parents=True)
    locked_predictions = lock_dir / "eurusd_oco_locked_predictions.parquet"
    pd.DataFrame([{"symbol": "EURUSD", "test_month": "2026-02"}]).to_parquet(
        locked_predictions,
        index=False,
    )
    (lock_dir / "eurusd_oco_live_lock.json").write_text(
        json.dumps({"artifacts": {"predictions_path": str(locked_predictions)}}) + "\n"
    )
    captured: dict[str, Path] = {}

    def _fake_validate_api_parity_run(**kwargs):
        captured["predictions_parquet"] = kwargs["predictions_parquet"]
        pd.DataFrame(
            [
                {
                    "symbol": kwargs["symbol"],
                    "stage12_api_parity_pass": True,
                    "certification_outcome": "PASS",
                    "go_decision": "GO",
                }
            ]
        ).to_csv(kwargs["out_summary"], index=False)
        return True

    def _stage13_pass(**kwargs):
        return (
            pd.DataFrame(
                [
                    {
                        "symbol": "EURUSD",
                        "stage13_dukascopy_testclient_pass": True,
                        "certification_outcome": "PASS",
                        "go_decision": "GO",
                    }
                ]
            ),
            pd.DataFrame(),
        )

    monkeypatch.setattr(
        "scripts.run_stage12_stage13_certification.validate_api_parity_run",
        _fake_validate_api_parity_run,
    )
    monkeypatch.setattr(
        "scripts.run_stage12_stage13_certification._generate_stage13_replay_artifacts",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(
        "scripts.run_stage12_stage13_certification._stage13_default_runner",
        _stage13_pass,
    )

    exit_code = main(
        [
            "--symbols",
            "EURUSD",
            "--models-dir",
            str(models_dir),
            "--model-month",
            "2026-02",
            "--predictions-dir",
            str(missing_predictions_dir),
            "--lock-dir",
            str(lock_dir),
            "--reconcile-dir",
            str(tmp_path / "reconcile"),
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    assert captured["predictions_parquet"] == locked_predictions
