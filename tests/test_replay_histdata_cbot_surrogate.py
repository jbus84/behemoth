from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import replay_histdata_cbot_surrogate as surrogate


def test_default_surrogate_paths_use_symbol_convention() -> None:
    fallback = surrogate._default_predictions_path(
        "EURUSD",
        start_ts="2025-07-07T00:00:00Z",
        history_dir=Path("/path/that/does/not/exist"),
    )
    assert fallback.name == "EURUSD_oco_monthly_predictions.parquet"
    assert surrogate._default_stoplimit_detail_path("EURUSD").name == "EURUSD_stop_limit_tickfill_detail.csv"
    assert surrogate._default_reduced_core_schedule_path("EURUSD").name == "EURUSD_oco_reduced_state_schedule.csv"


def test_default_predictions_path_uses_historical_lock(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    month_dir = history_dir / "2025-07"
    month_dir.mkdir(parents=True)
    (month_dir / "eurusd_oco_live_lock.json").write_text(
        """
        {
          "symbol": "EURUSD",
          "month": "2025-07",
          "cap_pips": 1.2,
          "candidates": [],
          "model_binding": {
            "predictions_path": "data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet",
            "model_month": "2025-07"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    out = surrogate._default_predictions_path(
        "EURUSD",
        start_ts="2025-07-07T00:00:00Z",
        history_dir=history_dir,
    )
    assert out.as_posix().endswith(
        "/data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet"
    )


def test_run_surrogate_writes_session_bundle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(surrogate, "SURROGATE_ROOT", tmp_path / "surrogate_runs")
    captured: dict[str, object] = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        Path(kwargs["runtime_db"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["runtime_db"]).write_text("", encoding="utf-8")
        Path(kwargs["events_json"]).write_text("[]", encoding="utf-8")
        for key in [
            "out_summary_csv",
            "out_checks_csv",
            "out_mismatches_csv",
            "report_out",
            "local_summary_csv",
            "local_selected_mismatches_csv",
            "local_signal_gap_analysis_csv",
            "local_signal_feature_diff_csv",
            "local_runtime_selected_csv",
            "stage12_summary_csv",
            "stage12_checks_csv",
            "stage12_mismatches_csv",
            "stage12_report_out",
        ]:
            Path(kwargs[key]).parent.mkdir(parents=True, exist_ok=True)
            Path(kwargs[key]).write_text("", encoding="utf-8")
        return (
            pd.DataFrame([{"ok": True}]),
            pd.DataFrame([{"ok": True}]),
            pd.DataFrame([{"check": "x"}]),
            pd.DataFrame([{"mismatch": "y"}]),
        )

    monkeypatch.setattr(surrogate, "run_testclient_replay", _fake_run)
    monkeypatch.setattr(
        surrogate,
        "evaluate_ftmo_session",
        lambda **kwargs: {
            "ftmo_challenge_summary_csv": str(tmp_path / "surrogate_runs" / "ftmo_challenge_summary.csv"),
            "ftmo_challenge_timeline_csv": str(tmp_path / "surrogate_runs" / "ftmo_challenge_timeline.csv"),
            "ftmo_daily_ledger_csv": str(tmp_path / "surrogate_runs" / "ftmo_daily_ledger.csv"),
            "ftmo_phase_report_md": str(tmp_path / "surrogate_runs" / "ftmo_phase_report.md"),
        },
    )

    out = surrogate.run_surrogate(
        symbol="EURUSD",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-09T00:00:00Z",
        source="histdata",
    )

    session_json = Path(out["surrogate_session_json"])
    assert session_json.exists()
    assert Path(out["runtime_db"]).exists()
    assert Path(out["events_json"]).exists()
    assert out["historical_preflight_mode"] == "warn"
    assert out["historical_prediction_universe_mode"] == "tolerant"
    assert out["selected_parity_mode"] == "event_aligned"
    assert out["ftmo_enabled"] is True
    assert out["ftmo_enabled_override"] is True
    assert out["ftmo_profile_id"] == "ftmo_10k_challenge_2step"
    assert out["ftmo_phase_mode"] == "full_lifecycle"
    assert out["ftmo_economics_mode"] == "repo_overlay"
    assert out["ftmo_trade_cost_gate_mode"] == "warn"
    assert out["http_trace"].endswith("/http_trace.ndjson")
    assert out["signal_gap_analysis_csv"].endswith("/surrogate_signal_gap_analysis.csv")
    assert out["signal_feature_diff_csv"].endswith("/surrogate_signal_feature_diff.csv")
    assert out["ftmo_challenge_summary_csv"].endswith("/ftmo_challenge_summary.csv")
    assert captured["source"] == "histdata"


def test_run_surrogate_supports_dukascopy_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(surrogate, "SURROGATE_ROOT", tmp_path / "surrogate_runs")
    captured: dict[str, object] = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        Path(kwargs["runtime_db"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["runtime_db"]).write_text("", encoding="utf-8")
        Path(kwargs["events_json"]).write_text("[]", encoding="utf-8")
        for key in [
            "out_summary_csv",
            "out_checks_csv",
            "out_mismatches_csv",
            "report_out",
            "local_summary_csv",
            "local_selected_mismatches_csv",
            "local_signal_gap_analysis_csv",
            "local_signal_feature_diff_csv",
            "local_runtime_selected_csv",
            "stage12_summary_csv",
            "stage12_checks_csv",
            "stage12_mismatches_csv",
            "stage12_report_out",
        ]:
            Path(kwargs[key]).parent.mkdir(parents=True, exist_ok=True)
            Path(kwargs[key]).write_text("", encoding="utf-8")
        return (
            pd.DataFrame([{"ok": True}]),
            pd.DataFrame([{"ok": True}]),
            pd.DataFrame([{"check": "x"}]),
            pd.DataFrame([{"mismatch": "y"}]),
        )

    monkeypatch.setattr(surrogate, "run_testclient_replay", _fake_run)
    monkeypatch.setattr(
        surrogate,
        "evaluate_ftmo_session",
        lambda **kwargs: {
            "ftmo_challenge_summary_csv": str(tmp_path / "surrogate_runs" / "ftmo_challenge_summary.csv"),
            "ftmo_challenge_timeline_csv": str(tmp_path / "surrogate_runs" / "ftmo_challenge_timeline.csv"),
            "ftmo_daily_ledger_csv": str(tmp_path / "surrogate_runs" / "ftmo_daily_ledger.csv"),
            "ftmo_phase_report_md": str(tmp_path / "surrogate_runs" / "ftmo_phase_report.md"),
        },
    )

    dukascopy_root = tmp_path / "dukascopy_ticks"
    out = surrogate.run_surrogate(
        symbol="EURUSD",
        source="dukascopy",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-09T00:00:00Z",
        tick_root=tmp_path / "tick",
        dukascopy_root=dukascopy_root,
    )

    assert out["source"] == "dukascopy"
    assert out["source_root"] == str(dukascopy_root)
    assert captured["source"] == "dukascopy"
    assert captured["tick_root"] == dukascopy_root
