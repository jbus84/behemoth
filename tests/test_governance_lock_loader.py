import json
from pathlib import Path

import pytest

from src.behemoth.core.governance_lock_loader import (
    GovernanceLockLoader,
    LockSource,
)


class FakeLiveSource(LockSource):
    def __init__(self, path: Path) -> None:
        self._path = path

    def find_lock(self, symbol: str, month: str | None = None) -> Path | None:
        return self._path if symbol.upper() == "EURUSD" else None


def test_load_contract(tmp_path: Path) -> None:
    import hashlib

    lock = tmp_path / "EURUSD_oco_live_lock.json"

    # Create model files
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    cbm_file = models_dir / "EURUSD_model_2026-01.cbm"
    json_file = models_dir / "EURUSD_model_2026-01.json"
    cbm_file.write_bytes(b"fake-cbm-data")
    json_file.write_text('{"threshold": 0.5}')

    # Compute sha256s
    cbm_sha = hashlib.sha256(cbm_file.read_bytes()).hexdigest()
    json_sha = hashlib.sha256(json_file.read_bytes()).hexdigest()

    # Write v3 lock
    lock.write_text(json.dumps({
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {
            "month": "2026-01",
            "dir_relpath": ".",
            "family": "oco_first_touch_clean",
        },
        "artifacts": {
            "model_cbm": {"path": "models/EURUSD_model_2026-01.cbm", "sha256": cbm_sha},
            "model_threshold_json": {"path": "models/EURUSD_model_2026-01.json", "sha256": json_sha},
        },
        "deployability": {"live_deployable": True, "model_month": "2026-01"},
        "locked_runtime": {"production_cap_pips": 1.5},
        "state_universe": {
            "rows": [
                {"symbol": "EURUSD", "bar_ticks": 100, "horizon": 6, "barrier_pips": 2.0, "state_id": "s1", "regime_desc": "r1"}
            ]
        },
    }))
    loader = GovernanceLockLoader(FakeLiveSource(lock))
    contract = loader.load_contract("EURUSD")
    assert contract.symbol == "EURUSD"
    assert contract.cap_pips == pytest.approx(1.5)
    assert len(contract.candidates) == 1
    assert contract.candidates[0].candidate_uid == "s1"


def _write_v3_lock(tmp_path: Path, locked_runtime: dict | None = None) -> Path:
    """Helper to create a v3 lock file with required model files."""
    import hashlib

    lock = tmp_path / "EURUSD_oco_live_lock.json"

    # Create model files
    models_dir = tmp_path / "models"
    models_dir.mkdir(exist_ok=True)
    cbm_file = models_dir / "EURUSD_model_2026-01.cbm"
    json_file = models_dir / "EURUSD_model_2026-01.json"
    cbm_file.write_bytes(b"fake-cbm-data")
    json_file.write_text('{"threshold": 0.5}')

    # Compute sha256s
    cbm_sha = hashlib.sha256(cbm_file.read_bytes()).hexdigest()
    json_sha = hashlib.sha256(json_file.read_bytes()).hexdigest()

    lock_data = {
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {
            "month": "2026-01",
            "dir_relpath": ".",
            "family": "oco_first_touch_clean",
        },
        "artifacts": {
            "model_cbm": {"path": "models/EURUSD_model_2026-01.cbm", "sha256": cbm_sha},
            "model_threshold_json": {"path": "models/EURUSD_model_2026-01.json", "sha256": json_sha},
        },
        "deployability": {"live_deployable": True, "model_month": "2026-01"},
        "locked_runtime": locked_runtime or {"production_cap_pips": 1.5},
        "state_universe": {
            "rows": [
                {"symbol": "EURUSD", "bar_ticks": 100, "horizon": 6, "barrier_pips": 2.0, "state_id": "s1", "regime_desc": "r1"}
            ]
        },
    }
    lock.write_text(json.dumps(lock_data))
    return lock


def test_load_contract_exposes_bundle_paths(tmp_path: Path) -> None:
    """CandidateContract surfaces BundlePaths so consumers don't need model_binding."""
    from src.behemoth.core.bundle_paths import BundlePaths

    lock = _write_v3_lock(tmp_path)  # the existing v3 fixture helper
    loader = GovernanceLockLoader(FakeLiveSource(lock))
    contract = loader.load_contract("EURUSD")

    assert isinstance(contract.bundle_paths, BundlePaths)
    assert contract.bundle_paths.model_cbm().name == "EURUSD_model_2026-01.cbm"
    assert contract.bundle_paths.model_month == "2026-01"


def test_load_contract_exposes_locked_runtime_overrides(tmp_path: Path) -> None:
    """The locked_runtime block becomes its own field; it does NOT live on model_binding."""
    lock = _write_v3_lock(tmp_path, locked_runtime={
        "production_cap_pips": 1.5,
        "threshold_mode": "rolling_days",
        "rolling_threshold_days": 20,
        "rolling_threshold_min_history": 300,
        "execution_quantile": 0.9,
    })
    loader = GovernanceLockLoader(FakeLiveSource(lock))
    contract = loader.load_contract("EURUSD")

    assert contract.locked_runtime["threshold_mode"] == "rolling_days"
    assert contract.locked_runtime["rolling_threshold_days"] == 20
