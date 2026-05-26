# tests/test_validate_bundle.py
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _sha256(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _make_valid_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "2026-04"
    (bundle / "models").mkdir(parents=True)
    pred = b"p"
    states = b"s"
    cbm = b"c"
    thr = b"t"
    (bundle / "eurusd_oco_locked_predictions.parquet").write_bytes(pred)
    (bundle / "eurusd_oco_allowed_states.csv").write_bytes(states)
    (bundle / "models" / "EURUSD_model_2026-04.cbm").write_bytes(cbm)
    (bundle / "models" / "EURUSD_model_2026-04.json").write_bytes(thr)
    lock = {
        "schema_version": 2,
        "symbol": "EURUSD",
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle)},
        "artifacts": {
            "predictions": {
                "path": "eurusd_oco_locked_predictions.parquet",
                "sha256": _sha256(pred),
            },
            "allowed_states_csv": {
                "path": "eurusd_oco_allowed_states.csv",
                "sha256": _sha256(states),
            },
            "model_cbm": {"path": "models/EURUSD_model_2026-04.cbm", "sha256": _sha256(cbm)},
            "model_threshold_json": {
                "path": "models/EURUSD_model_2026-04.json",
                "sha256": _sha256(thr),
            },
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    (bundle / "eurusd_oco_live_lock.json").write_text(json.dumps(lock, indent=2))
    return bundle


def _run(bundle: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/validate_bundle.py", str(bundle)],
        capture_output=True,
        text=True,
    )


def test_passes_for_valid_bundle(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    result = _run(bundle)
    assert result.returncode == 0, result.stderr


def test_fails_when_artifact_missing(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    (bundle / "eurusd_oco_locked_predictions.parquet").unlink()
    result = _run(bundle)
    assert result.returncode != 0
    assert "missing artifact" in result.stderr


def test_fails_when_sha_drifts(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    (bundle / "eurusd_oco_allowed_states.csv").write_bytes(b"drift")
    result = _run(bundle)
    assert result.returncode != 0
    assert "sha256 mismatch" in result.stderr


def test_fails_for_v1_lock(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    lock_path = bundle / "eurusd_oco_live_lock.json"
    data = json.loads(lock_path.read_text())
    data["schema_version"] = 1
    lock_path.write_text(json.dumps(data))
    result = _run(bundle)
    assert result.returncode != 0
    assert "schema_version=2" in result.stderr
