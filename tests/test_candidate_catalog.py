from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.behemoth.core.candidate_catalog import CandidateCatalog
from src.behemoth.core.historical_registry import HistoricalCandidateRegistry, HistoricalLockEntry
from src.behemoth.core.registry import CandidateRegistry, CandidateSpec


def _candidate(symbol: str = "EURUSD", bar_ticks: int = 100) -> CandidateSpec:
    return CandidateSpec(
        symbol=symbol,
        bar_ticks=bar_ticks,
        horizon=6,
        barrier_pips=2.0,
        candidate_uid=f"library|{symbol}|{bar_ticks}|h6|b2",
    )


def test_candidate_catalog_resolves_live_contract() -> None:
    registry = CandidateRegistry()
    registry._candidates_by_symbol["EURUSD"] = [_candidate(bar_ticks=200)]
    registry._caps_by_symbol["EURUSD"] = 1.5
    registry._model_bindings_by_symbol["EURUSD"] = {
        "model_month": "2026-04",
        "model_cbm_path": "model.cbm",
    }
    catalog = CandidateCatalog(
        live_registry=registry,
        historical_registry=None,
        historical_mode=False,
    )

    contract = catalog.resolve_contract("eurusd", datetime(2026, 5, 1, tzinfo=timezone.utc))

    assert contract.source == "live"
    assert contract.cache_key == "EURUSD"
    assert contract.model_month == "2026-04"
    assert contract.cap_pips == 1.5
    assert catalog.active_bar_ticks("EURUSD") == [200]


def test_candidate_catalog_resolves_historical_fallback_month() -> None:
    historical = HistoricalCandidateRegistry()
    historical._entries[("EURUSD", "2026-03")] = HistoricalLockEntry(
        symbol="EURUSD",
        month="2026-03",
        lock_path="locks/2026-03/EURUSD_oco_live_lock.json",
        candidates=[_candidate()],
        cap_pips=1.2,
        model_binding={"model_month": "2026-03", "predictions_path": "pred.parquet"},
    )
    catalog = CandidateCatalog(
        live_registry=None,
        historical_registry=historical,
        historical_mode=True,
        missing_month_policy="nearest_previous",
        latest_loaded_month=lambda _symbol: "2026-03",
    )

    contract = catalog.resolve_contract("EURUSD", datetime(2026, 4, 2, tzinfo=timezone.utc))

    assert contract.source == "historical"
    assert contract.cache_key == "EURUSD|2026-03"
    assert contract.lock_path == "locks/2026-03/EURUSD_oco_live_lock.json"
    assert catalog.active_bar_ticks("EURUSD") == [100]


def test_candidate_catalog_reports_missing_historical_months() -> None:
    catalog = CandidateCatalog(
        live_registry=None,
        historical_registry=HistoricalCandidateRegistry(),
        historical_mode=True,
    )

    with pytest.raises(KeyError, match="No historical lock for EURUSD month 2026-04"):
        catalog.resolve_contract("EURUSD", datetime(2026, 4, 2, tzinfo=timezone.utc))
