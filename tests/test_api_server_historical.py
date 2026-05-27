from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.behemoth.api import server
from src.behemoth.core.bundle_paths import BundlePaths
from src.behemoth.core.historical_registry import HistoricalCandidateRegistry, HistoricalLockEntry
from src.behemoth.core.registry import CandidateSpec


def _mk_entry(symbol: str, month: str) -> HistoricalLockEntry:
    lock_path = Path(
        f"configs/research/governance/oco_history/{month}/{symbol.lower()}_oco_first_touch_live_lock.json"
    )
    bp = BundlePaths(
        lock_path=lock_path,
        bundle_dir=lock_path.parent,
        symbol=symbol,
        model_month=month,
        family="oco_first_touch",
        _artifacts={},
        _deployability={"live_deployable": True, "model_month": month},
        cross_symbol_scope={},
    )
    return HistoricalLockEntry(
        symbol=symbol,
        month=month,
        family="oco_first_touch",
        lock_path=str(lock_path),
        candidates=[
            CandidateSpec(
                symbol=symbol,
                bar_ticks=100,
                horizon=4,
                barrier_pips=10.0,
                candidate_uid="oco_first_touch__all__k2",
                family="oco_first_touch",
            )
        ],
        cap_pips=1.2,
        bundle_paths=bp,
    )


def test_resolve_runtime_contract_historical_uses_close_ts_month() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-08", "oco_first_touch")] = _mk_entry("EURUSD", "2025-08")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = ""

        contract = server._resolve_runtime_contract_for_family(
            "EURUSD",
            "oco_first_touch",
            datetime(2025, 8, 15, tzinfo=timezone.utc),
        )
        assert contract.source == "historical"
        assert contract.model_month == "2025-08"
        assert contract.cache_key == "EURUSD|2025-08|oco_first_touch"
        assert contract.cap_pips == pytest.approx(1.2)
        assert len(contract.candidates) == 1
    finally:
        server._config.governance_mode = original_mode
        server._config.governance_missing_month_policy = original_policy
        server._config.force_model_month = original_force
        server._historical_registry = original_hist
        server._registry = original_reg


def test_app_config_honors_behemoth_symbols_env(monkeypatch) -> None:
    monkeypatch.setenv("BEHEMOTH_SYMBOLS", "GBPUSD, USDJPY")
    cfg = server.AppConfig()
    assert cfg.symbols == ["GBPUSD", "USDJPY"]


def test_app_config_historical_defaults_use_exact_locked(monkeypatch) -> None:
    monkeypatch.setenv("BEHEMOTH_GOVERNANCE_MODE", "historical_auto")
    monkeypatch.delenv("BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE", raising=False)
    monkeypatch.delenv("BEHEMOTH_HISTORICAL_PREDICTION_PAYLOAD_MODE", raising=False)
    monkeypatch.delenv("BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC", raising=False)
    cfg = server.AppConfig()
    assert cfg.historical_prediction_universe_mode == "exact"
    assert cfg.historical_prediction_payload_mode == "locked"
    assert cfg.historical_prediction_tolerance_sec == pytest.approx(120.0)


def test_app_config_live_defaults_keep_exact_model(monkeypatch) -> None:
    monkeypatch.setenv("BEHEMOTH_GOVERNANCE_MODE", "live")
    monkeypatch.delenv("BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE", raising=False)
    monkeypatch.delenv("BEHEMOTH_HISTORICAL_PREDICTION_PAYLOAD_MODE", raising=False)
    monkeypatch.delenv("BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC", raising=False)
    cfg = server.AppConfig()
    assert cfg.historical_prediction_universe_mode == "exact"
    assert cfg.historical_prediction_payload_mode == "model"
    assert cfg.historical_prediction_tolerance_sec == pytest.approx(30.0)


def test_resolve_runtime_contract_historical_falls_back_to_previous_month() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-07", "oco_first_touch")] = _mk_entry("EURUSD", "2025-07")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "nearest_previous"
        server._config.force_model_month = ""

        contract = server._resolve_runtime_contract_for_family(
            "EURUSD",
            "oco_first_touch",
            datetime(2025, 8, 1, tzinfo=timezone.utc),
        )
        assert contract.model_month == "2025-07"
        assert contract.cache_key == "EURUSD|2025-07|oco_first_touch"
    finally:
        server._config.governance_mode = original_mode
        server._config.governance_missing_month_policy = original_policy
        server._config.force_model_month = original_force
        server._historical_registry = original_hist
        server._registry = original_reg


def test_resolve_runtime_contract_historical_missing_month_errors() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-07", "oco_first_touch")] = _mk_entry("EURUSD", "2025-07")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = ""

        with pytest.raises(HTTPException) as exc:
            server._resolve_runtime_contract_for_family(
                "EURUSD",
                "oco_first_touch",
                datetime(2025, 8, 1, tzinfo=timezone.utc),
            )
        assert exc.value.status_code == 422
        assert "No historical lock" in str(exc.value.detail)
    finally:
        server._config.governance_mode = original_mode
        server._config.governance_missing_month_policy = original_policy
        server._config.force_model_month = original_force
        server._historical_registry = original_hist
        server._registry = original_reg


def test_resolve_runtime_contract_historical_force_month_override() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-07", "oco_first_touch")] = _mk_entry("EURUSD", "2025-07")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = "202507"

        contract = server._resolve_runtime_contract_for_family(
            "EURUSD",
            "oco_first_touch",
            datetime(2025, 8, 1, tzinfo=timezone.utc),
        )
        assert contract.model_month == "2025-07"
        assert contract.cache_key == "EURUSD|2025-07|oco_first_touch"
    finally:
        server._config.governance_mode = original_mode
        server._config.governance_missing_month_policy = original_policy
        server._config.force_model_month = original_force
        server._historical_registry = original_hist
        server._registry = original_reg


def test_resolve_runtime_contract_historical_switches_at_month_boundary() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-08", "oco_first_touch")] = _mk_entry("EURUSD", "2025-08")
        hist._entries[("EURUSD", "2025-09", "oco_first_touch")] = _mk_entry("EURUSD", "2025-09")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = ""

        aug = server._resolve_runtime_contract_for_family(
            "EURUSD",
            "oco_first_touch",
            datetime(2025, 8, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
        sep = server._resolve_runtime_contract_for_family(
            "EURUSD",
            "oco_first_touch",
            datetime(2025, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        assert aug.model_month == "2025-08"
        assert sep.model_month == "2025-09"
    finally:
        server._config.governance_mode = original_mode
        server._config.governance_missing_month_policy = original_policy
        server._config.force_model_month = original_force
        server._historical_registry = original_hist
        server._registry = original_reg


def test_resolve_runtime_contract_rejects_invalid_force_month_format() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-08", "oco_first_touch")] = _mk_entry("EURUSD", "2025-08")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = "2025/08"

        with pytest.raises(HTTPException) as exc:
            server._resolve_runtime_contract(
                "EURUSD",
                datetime(2025, 8, 1, tzinfo=timezone.utc),
            )
        assert exc.value.status_code == 422
        assert "BEHEMOTH_FORCE_MODEL_MONTH" in str(exc.value.detail)
    finally:
        server._config.governance_mode = original_mode
        server._config.governance_missing_month_policy = original_policy
        server._config.force_model_month = original_force
        server._historical_registry = original_hist
        server._registry = original_reg


def _mk_contract(symbol: str = "EURUSD", month: str = "2025-07") -> server._ResolvedRuntimeContract:
    lock_path = Path(
        f"configs/research/governance/oco_history/{month}/{symbol.lower()}_oco_first_touch_live_lock.json"
    )
    bp = BundlePaths(
        lock_path=lock_path,
        bundle_dir=lock_path.parent,
        symbol=symbol,
        model_month=month,
        family="oco_first_touch",
        _artifacts={},
        _deployability={"live_deployable": True, "model_month": month},
        cross_symbol_scope={},
    )
    return server._ResolvedRuntimeContract(
        symbol=symbol,
        model_month=month,
        cache_key=f"{symbol}|{month}",
        candidates=[],
        bundle_paths=bp,
        cap_pips=1.2,
        source="historical",
    )
