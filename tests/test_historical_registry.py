from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.behemoth.core.historical_registry import HistoricalCandidateRegistry


def _write_lock(
    root: Path,
    *,
    symbol: str,
    month: str,
    model_month: str | None = None,
    include_hashes: bool = True,
) -> Path:
    import hashlib

    month_dir = root / month
    month_dir.mkdir(parents=True, exist_ok=True)
    lock_path = month_dir / f"{symbol.lower()}_oco_first_touch_live_lock.json"

    # Create model files in bundle-relative models/ directory
    models_dir = month_dir / "models"
    models_dir.mkdir(exist_ok=True)
    cbm_file = models_dir / f"{symbol}_model_{model_month or month}.cbm"
    json_file = models_dir / f"{symbol}_model_{model_month or month}.json"
    cbm_file.write_bytes(b"fake-cbm-" + symbol.encode())
    json_file.write_text('{"threshold": 0.5}')

    # Compute sha256s
    cbm_sha = hashlib.sha256(cbm_file.read_bytes()).hexdigest() if include_hashes else ""
    json_sha = hashlib.sha256(json_file.read_bytes()).hexdigest() if include_hashes else ""

    artifacts = {
        "model_cbm": {"path": f"models/{symbol}_model_{model_month or month}.cbm", "sha256": cbm_sha},
        "model_threshold_json": {"path": f"models/{symbol}_model_{model_month or month}.json", "sha256": json_sha},
    }

    payload = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {
            "month": month,
            "dir_relpath": ".",
            "family": "oco_first_touch",
        },
        "artifacts": artifacts,
        "deployability": {"live_deployable": True, "model_month": model_month or month},
        "locked_runtime": {"production_cap_pips": 1.1},
        "state_universe": {
            "rows": [
                {
                    "symbol": symbol,
                    "bar_ticks": 100,
                    "horizon": 3,
                    "barrier_pips": 8.0,
                    "state_id": "oco_first_touch__all__k2",
                    "regime_desc": "all",
                }
            ]
        },
    }
    lock_path.write_text(json.dumps(payload), encoding="utf-8")
    return lock_path


def test_historical_registry_loads_month_scoped_entries(tmp_path: Path) -> None:
    _write_lock(tmp_path, symbol="EURUSD", month="2025-07")
    _write_lock(tmp_path, symbol="EURUSD", month="2025-08")
    _write_lock(tmp_path, symbol="GBPUSD", month="2025-08")

    reg = HistoricalCandidateRegistry.load(tmp_path)

    assert reg.symbols == ["EURUSD", "GBPUSD"]
    assert reg.months_for_symbol("eurusd") == ["2025-07", "2025-08"]
    assert len(reg.get_candidates("EURUSD", "2025-07")) == 1
    assert reg.get_cap_pips("EURUSD", "2025-07") == pytest.approx(1.1)
    bundle_paths = reg.get_bundle_paths("EURUSD", "2025-07")
    assert bundle_paths is not None
    assert bundle_paths.model_month == "2025-07"
    cbm_path = bundle_paths.model_cbm()
    assert "EURUSD_model_2025-07.cbm" in cbm_path.name
    assert len(reg.all_candidates()) == 3


def test_historical_registry_skips_invalid_lock_entries(tmp_path: Path) -> None:
    _write_lock(
        tmp_path,
        symbol="EURUSD",
        month="2025-07",
        model_month="2025-06",  # mismatched with folder month
    )
    _write_lock(
        tmp_path,
        symbol="GBPUSD",
        month="2025-07",
        include_hashes=False,  # missing required hash fields
    )

    reg = HistoricalCandidateRegistry.load(tmp_path)

    assert reg.symbols == []
    assert reg.all_candidates() == []


def test_historical_registry_missing_dir_raises() -> None:
    with pytest.raises(FileNotFoundError):
        HistoricalCandidateRegistry.load("configs/research/governance/does_not_exist")
