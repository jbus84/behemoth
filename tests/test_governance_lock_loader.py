import json
import pytest
from pathlib import Path

from src.behemoth.core.governance_lock_loader import GovernanceLockLoader, LockSource, CandidateContract


class FakeLiveSource(LockSource):
    def __init__(self, path: Path) -> None:
        self._path = path

    def find_lock(self, symbol: str, month: str | None = None) -> Path | None:
        return self._path if symbol.upper() == "EURUSD" else None


def test_load_contract(tmp_path: Path) -> None:
    lock = tmp_path / "EURUSD_oco_live_lock.json"
    lock.write_text(json.dumps({
        "symbol": "EURUSD",
        "artifacts": {
            "model_cbm_path": "models/EURUSD.cbm",
            "model_cbm_sha256": "abc",
            "model_threshold_json_path": "models/EURUSD.json",
            "model_threshold_json_sha256": "def",
            "model_month": "2026-01",
        },
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
