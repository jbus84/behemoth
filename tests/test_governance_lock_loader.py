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

    # Write v2 lock
    lock.write_text(json.dumps({
        "schema_version": 2,
        "symbol": "EURUSD",
        "bundle": {"month": "2026-01", "dir_relpath": "."},
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
