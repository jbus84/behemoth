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
    month_dir = root / month
    month_dir.mkdir(parents=True, exist_ok=True)
    lock_path = month_dir / f"{symbol.lower()}_oco_live_lock.json"

    artifacts = {
        "model_cbm_path": f"models/oco/{symbol}_model_{model_month or month}.cbm",
        "model_threshold_json_path": f"models/oco/{symbol}_model_{model_month or month}.json",
        "model_month": model_month or month,
    }
    if include_hashes:
        artifacts["model_cbm_sha256"] = "cbm_sha"
        artifacts["model_threshold_json_sha256"] = "thr_sha"

    payload = {
        "symbol": symbol,
        "artifacts": artifacts,
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
    binding = reg.get_model_binding("EURUSD", "2025-07")
    assert binding is not None
    assert binding["model_month"] == "2025-07"
    assert "EURUSD_model_2025-07.cbm" in binding["model_cbm_path"]
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
