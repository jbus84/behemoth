from __future__ import annotations

import unittest.mock as mock
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.behemoth.api import server
from src.behemoth.core.historical_governance_validation import HistoricalGovernanceCheck
from src.behemoth.core.historical_registry import HistoricalCandidateRegistry, HistoricalLockEntry
from src.behemoth.core.registry import CandidateSpec


def _mk_entry(symbol: str, month: str) -> HistoricalLockEntry:
    return HistoricalLockEntry(
        symbol=symbol,
        month=month,
        lock_path=f"configs/research/governance/oco_history/{month}/{symbol.lower()}_oco_live_lock.json",
        candidates=[
            CandidateSpec(
                symbol=symbol,
                bar_ticks=100,
                horizon=4,
                barrier_pips=10.0,
                candidate_uid="oco_first_touch_clean__all__k2",
            )
        ],
        cap_pips=1.2,
        model_binding={
            "model_cbm_path": f"models/oco/{symbol}_model_{month}.cbm",
            "model_cbm_sha256": "cbm_sha",
            "model_threshold_json_path": f"models/oco/{symbol}_model_{month}.json",
            "model_threshold_json_sha256": "thr_sha",
            "model_month": month,
        },
    )


def test_resolve_runtime_contract_historical_uses_close_ts_month() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-08")] = _mk_entry("EURUSD", "2025-08")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = ""

        contract = server._resolve_runtime_contract(
            "EURUSD",
            datetime(2025, 8, 15, tzinfo=timezone.utc),
        )
        assert contract.source == "historical"
        assert contract.model_month == "2025-08"
        assert contract.cache_key == "EURUSD|2025-08"
        assert contract.cap_pips == pytest.approx(1.2)
        assert len(contract.candidates) == 1
    finally:
        server._config.governance_mode = original_mode
        server._config.governance_missing_month_policy = original_policy
        server._config.force_model_month = original_force
        server._historical_registry = original_hist
        server._registry = original_reg


def test_resolve_runtime_contract_historical_falls_back_to_previous_month() -> None:
    original_mode = server._config.governance_mode
    original_policy = server._config.governance_missing_month_policy
    original_force = server._config.force_model_month
    original_hist = server._historical_registry
    original_reg = server._registry

    try:
        hist = HistoricalCandidateRegistry()
        hist._entries[("EURUSD", "2025-07")] = _mk_entry("EURUSD", "2025-07")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "nearest_previous"
        server._config.force_model_month = ""

        contract = server._resolve_runtime_contract(
            "EURUSD",
            datetime(2025, 8, 1, tzinfo=timezone.utc),
        )
        assert contract.model_month == "2025-07"
        assert contract.cache_key == "EURUSD|2025-07"
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
        hist._entries[("EURUSD", "2025-07")] = _mk_entry("EURUSD", "2025-07")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = ""

        with pytest.raises(HTTPException) as exc:
            server._resolve_runtime_contract(
                "EURUSD",
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
        hist._entries[("EURUSD", "2025-07")] = _mk_entry("EURUSD", "2025-07")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = "202507"

        contract = server._resolve_runtime_contract(
            "EURUSD",
            datetime(2025, 8, 1, tzinfo=timezone.utc),
        )
        assert contract.model_month == "2025-07"
        assert contract.cache_key == "EURUSD|2025-07"
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
        hist._entries[("EURUSD", "2025-08")] = _mk_entry("EURUSD", "2025-08")
        hist._entries[("EURUSD", "2025-09")] = _mk_entry("EURUSD", "2025-09")
        server._historical_registry = hist
        server._registry = None
        server._config.governance_mode = "historical_auto"
        server._config.governance_missing_month_policy = "error"
        server._config.force_model_month = ""

        aug = server._resolve_runtime_contract(
            "EURUSD",
            datetime(2025, 8, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
        sep = server._resolve_runtime_contract(
            "EURUSD",
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
        hist._entries[("EURUSD", "2025-08")] = _mk_entry("EURUSD", "2025-08")
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


def test_run_historical_preflight_raises_on_failed_checks() -> None:
    original_failed = server._historical_preflight_failed_checks
    original_summary = server._historical_preflight_summary
    bad = [
        HistoricalGovernanceCheck(
            name="index_covers_exact_lock_set",
            ok=False,
            detail="lock_only=[('EURUSD', '2025-08')]",
        )
    ]
    with mock.patch.object(server, "validate_historical_governance", return_value=bad):
        with pytest.raises(RuntimeError):
            server._run_historical_preflight(Path("configs/research/governance/oco_history"))
        assert server._historical_preflight_failed_checks == 1
        assert "index_covers_exact_lock_set" in server._historical_preflight_summary
    server._historical_preflight_failed_checks = original_failed
    server._historical_preflight_summary = original_summary
