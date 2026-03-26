from __future__ import annotations

from pathlib import Path

from scripts.run_local_jforex_surrogate_matrix import RunConfig, _prediction_path


def _cfg(tmp_path: Path) -> RunConfig:
    return RunConfig(
        symbols=("EURUSD",),
        start_ts="2026-02-04T00:00:00Z",
        end_ts="2026-02-09T00:00:00Z",
        model_month="2026-02",
        models_dir="models/oco_dukascopy_candidate",
        history_dir=str(tmp_path / "history"),
        predictions_dir=str(tmp_path / "predictions"),
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
        metrics_port_base=9465,
        warmup_ticks=30000,
        lookback_days=31,
        phase_bar_ticks=100,
        starting_balance=100000,
        risk_enabled=False,
        universe_mode="tolerant",
        ordinal_tolerance=0,
        prediction_tolerance_sec=120,
        locked_predictions_dir="",
    )


def test_prediction_path_prefers_explicit_locked_predictions_dir(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg = RunConfig(**{**cfg.__dict__, "locked_predictions_dir": str(tmp_path / "explicit_locked")})

    assert _prediction_path(cfg, "EURUSD") == str(
        Path(cfg.locked_predictions_dir) / "eurusd_oco_locked_predictions.parquet"
    )


def test_prediction_path_prefers_history_archive_when_present(tmp_path: Path) -> None:
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
