from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.behemoth.core.bundle_paths import BundlePaths
from src.behemoth.core.historical_prediction_stage import (
    HistoricalPredictionStage,
    MissingHistoricalPredictionArtifact,
)


def _write_v3_lock_with_predictions(tmp_path: Path, predictions_path: Path | str | None = None) -> BundlePaths:
    """Helper to create a v3 lock file with predictions artifact."""
    import hashlib

    lock = tmp_path / "EURUSD_oco_first_touch_live_lock.json"
    models_dir = tmp_path / "models"
    models_dir.mkdir(exist_ok=True)

    # Create minimal model files
    cbm_file = models_dir / "EURUSD_model_2026-01.cbm"
    json_file = models_dir / "EURUSD_model_2026-01.json"
    cbm_file.write_bytes(b"fake-cbm-data")
    json_file.write_text('{"threshold": 0.5}')

    # Create predictions parquet file
    if predictions_path is None:
        predictions_path = tmp_path / "EURUSD_oco_locked_predictions.parquet"
    pred_file = Path(predictions_path)
    pred_file.parent.mkdir(exist_ok=True, parents=True)
    pred_file.write_bytes(b"fake-parquet-data")

    # Compute sha256s
    cbm_sha = hashlib.sha256(cbm_file.read_bytes()).hexdigest()
    json_sha = hashlib.sha256(json_file.read_bytes()).hexdigest()
    pred_sha = hashlib.sha256(pred_file.read_bytes()).hexdigest()

    lock_data = {
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {
            "month": "2026-01",
            "dir_relpath": ".",
            "family": "oco_first_touch",
        },
        "artifacts": {
            "predictions": {"path": pred_file.name if pred_file.parent == tmp_path else str(pred_file.relative_to(tmp_path)), "sha256": pred_sha},
            "model_cbm": {"path": f"models/{cbm_file.name}", "sha256": cbm_sha},
            "model_threshold_json": {"path": f"models/{json_file.name}", "sha256": json_sha},
        },
        "deployability": {"live_deployable": True, "model_month": "2026-01"},
        "locked_runtime": {"production_cap_pips": 1.5},
        "state_universe": {"rows": []},
    }
    lock.write_text(json.dumps(lock_data))
    return BundlePaths.from_lock(lock)


def test_historical_prediction_stage_records_missing_artifact_status(tmp_path) -> None:
    # Create a bundle_paths with a predictions file that we'll then delete
    bundle_paths = _write_v3_lock_with_predictions(tmp_path)

    # Delete the predictions file to trigger missing_artifact
    pred_path = bundle_paths.bundle_dir / bundle_paths._artifacts["predictions"].relpath
    pred_path.unlink()

    stage = HistoricalPredictionStage()

    out = stage.load_universe(
        "EURUSD|2026-01",
        "EURUSD",
        "2026-01",
        bundle_paths,
    )

    status = stage.load_status("EURUSD|2026-01")
    assert out == {}
    assert status is not None
    assert status.status == "missing_artifact"


def test_historical_prediction_stage_can_raise_on_missing_artifact(tmp_path) -> None:
    # Create a bundle_paths with a predictions file that we'll then delete
    bundle_paths = _write_v3_lock_with_predictions(tmp_path)

    # Delete the predictions file to trigger missing_artifact
    pred_path = bundle_paths.bundle_dir / bundle_paths._artifacts["predictions"].relpath
    pred_path.unlink()

    stage = HistoricalPredictionStage(strict_missing=True)

    with pytest.raises(MissingHistoricalPredictionArtifact):
        stage.load_payload_rows(
            "EURUSD|2026-01",
            "EURUSD",
            "2026-01",
            bundle_paths,
        )
