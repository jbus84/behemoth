from __future__ import annotations

import pytest

from src.behemoth.core.historical_prediction_stage import (
    HistoricalPredictionStage,
    MissingHistoricalPredictionArtifact,
)


def test_historical_prediction_stage_records_missing_artifact_status(tmp_path) -> None:
    missing = tmp_path / "missing.parquet"
    stage = HistoricalPredictionStage()

    out = stage.load_universe(
        "EURUSD|2026-03",
        "EURUSD",
        "2026-03",
        {"predictions_path": str(missing)},
    )

    status = stage.load_status("EURUSD|2026-03")
    assert out == {}
    assert status is not None
    assert status.status == "missing_artifact"
    assert status.predictions_path == str(missing)


def test_historical_prediction_stage_can_raise_on_missing_artifact(tmp_path) -> None:
    stage = HistoricalPredictionStage(strict_missing=True)

    with pytest.raises(MissingHistoricalPredictionArtifact):
        stage.load_payload_rows(
            "EURUSD|2026-03",
            "EURUSD",
            "2026-03",
            {"predictions_path": str(tmp_path / "missing.parquet")},
        )
