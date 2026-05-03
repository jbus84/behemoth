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


def _mk_contract(symbol: str = "EURUSD", month: str = "2025-07") -> server._ResolvedRuntimeContract:
    return server._ResolvedRuntimeContract(
        symbol=symbol,
        model_month=month,
        cache_key=f"{symbol}|{month}",
        candidates=[],
        model_binding={},
        cap_pips=1.2,
        source="historical",
    )


def _mk_candidate(
    bar_ticks: int = 100, horizon: int = 4, uid: str = "oco_first_touch_clean__all__k2"
):
    from src.behemoth.core.registry import CandidateSpec

    return CandidateSpec(
        symbol="EURUSD",
        bar_ticks=bar_ticks,
        horizon=horizon,
        barrier_pips=10.0,
        candidate_uid=uid,
    )


def test_ordinal_gate_exact_match_returns_candidate() -> None:
    contract = _mk_contract()
    cand = _mk_candidate(bar_ticks=100, horizon=4, uid="oco_first_touch_clean__all__k2")
    canonical = "oco|EURUSD|100|h4|oco_first_touch_clean__all__k2"
    ordinal_index = {canonical: [5, 10, 15]}

    original_mode = server._config.historical_prediction_universe_mode
    original_tolerance = server._config.historical_prediction_ordinal_tolerance
    original_cursor = server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)
    original_is_hist = server._is_historical_mode

    try:
        server._config.historical_prediction_universe_mode = "ordinal"
        server._config.historical_prediction_ordinal_tolerance = 0
        server._is_historical_mode = lambda: True

        with mock.patch(
            "src.behemoth.api.server._load_historical_prediction_candidate_ordinal_index",
            return_value=ordinal_index,
        ):
            result = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, tzinfo=timezone.utc),
                candidates=[cand],
                bar_ordinals={"100": 5},
            )
        assert result == [cand]
    finally:
        server._config.historical_prediction_universe_mode = original_mode
        server._config.historical_prediction_ordinal_tolerance = original_tolerance
        server._is_historical_mode = original_is_hist
        if original_cursor is not None:
            server._historical_prediction_candidate_cursor[contract.cache_key] = original_cursor
        else:
            server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)


def test_ordinal_gate_exact_no_match_excludes_candidate() -> None:
    contract = _mk_contract()
    cand = _mk_candidate(bar_ticks=100, horizon=4, uid="oco_first_touch_clean__all__k2")
    canonical = "oco|EURUSD|100|h4|oco_first_touch_clean__all__k2"
    ordinal_index = {canonical: [5, 10, 15]}

    original_mode = server._config.historical_prediction_universe_mode
    original_tolerance = server._config.historical_prediction_ordinal_tolerance
    original_cursor = server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)
    original_is_hist = server._is_historical_mode

    try:
        server._config.historical_prediction_universe_mode = "ordinal"
        server._config.historical_prediction_ordinal_tolerance = 0
        server._is_historical_mode = lambda: True

        with mock.patch(
            "src.behemoth.api.server._load_historical_prediction_candidate_ordinal_index",
            return_value=ordinal_index,
        ):
            result = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, tzinfo=timezone.utc),
                candidates=[cand],
                bar_ordinals={"100": 7},
            )
        assert result == []
    finally:
        server._config.historical_prediction_universe_mode = original_mode
        server._config.historical_prediction_ordinal_tolerance = original_tolerance
        server._is_historical_mode = original_is_hist
        if original_cursor is not None:
            server._historical_prediction_candidate_cursor[contract.cache_key] = original_cursor
        else:
            server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)


def test_ordinal_gate_tolerance_1_matches_adjacent() -> None:
    contract = _mk_contract()
    cand = _mk_candidate(bar_ticks=100, horizon=4, uid="oco_first_touch_clean__all__k2")
    canonical = "oco|EURUSD|100|h4|oco_first_touch_clean__all__k2"
    ordinal_index = {canonical: [5, 10, 15]}

    original_mode = server._config.historical_prediction_universe_mode
    original_tolerance = server._config.historical_prediction_ordinal_tolerance
    original_cursor = server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)
    original_is_hist = server._is_historical_mode

    try:
        server._config.historical_prediction_universe_mode = "ordinal"
        server._config.historical_prediction_ordinal_tolerance = 1
        server._is_historical_mode = lambda: True

        with mock.patch(
            "src.behemoth.api.server._load_historical_prediction_candidate_ordinal_index",
            return_value=ordinal_index,
        ):
            # ordinal 6 is within ±1 of 5
            result = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, tzinfo=timezone.utc),
                candidates=[cand],
                bar_ordinals={"100": 6},
            )
        assert result == [cand]
    finally:
        server._config.historical_prediction_universe_mode = original_mode
        server._config.historical_prediction_ordinal_tolerance = original_tolerance
        server._is_historical_mode = original_is_hist
        if original_cursor is not None:
            server._historical_prediction_candidate_cursor[contract.cache_key] = original_cursor
        else:
            server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)


def test_ordinal_gate_missing_bar_ordinals_returns_empty() -> None:
    contract = _mk_contract()
    cand = _mk_candidate(bar_ticks=100, horizon=4, uid="oco_first_touch_clean__all__k2")
    canonical = "oco|EURUSD|100|h4|oco_first_touch_clean__all__k2"
    ordinal_index = {canonical: [5, 10]}

    original_mode = server._config.historical_prediction_universe_mode
    original_tolerance = server._config.historical_prediction_ordinal_tolerance
    original_cursor = server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)
    original_is_hist = server._is_historical_mode

    try:
        server._config.historical_prediction_universe_mode = "ordinal"
        server._config.historical_prediction_ordinal_tolerance = 0
        server._is_historical_mode = lambda: True

        with mock.patch(
            "src.behemoth.api.server._load_historical_prediction_candidate_ordinal_index",
            return_value=ordinal_index,
        ):
            result = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, tzinfo=timezone.utc),
                candidates=[cand],
                bar_ordinals=None,
            )
        assert result == []
    finally:
        server._config.historical_prediction_universe_mode = original_mode
        server._config.historical_prediction_ordinal_tolerance = original_tolerance
        server._is_historical_mode = original_is_hist
        if original_cursor is not None:
            server._historical_prediction_candidate_cursor[contract.cache_key] = original_cursor
        else:
            server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)


def test_ordinal_gate_empty_ordinal_index_falls_through_to_candidates() -> None:
    contract = _mk_contract()
    cand = _mk_candidate(bar_ticks=100, horizon=4, uid="oco_first_touch_clean__all__k2")

    original_mode = server._config.historical_prediction_universe_mode
    original_tolerance = server._config.historical_prediction_ordinal_tolerance
    original_cursor = server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)
    original_is_hist = server._is_historical_mode

    try:
        server._config.historical_prediction_universe_mode = "ordinal"
        server._config.historical_prediction_ordinal_tolerance = 0
        server._is_historical_mode = lambda: True

        with mock.patch(
            "src.behemoth.api.server._load_historical_prediction_candidate_ordinal_index",
            return_value={},
        ):
            result = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, tzinfo=timezone.utc),
                candidates=[cand],
                bar_ordinals={"100": 5},
            )
        # empty ordinal index → falls through (returns candidates unchanged)
        assert result == [cand]
    finally:
        server._config.historical_prediction_universe_mode = original_mode
        server._config.historical_prediction_ordinal_tolerance = original_tolerance
        server._is_historical_mode = original_is_hist
        if original_cursor is not None:
            server._historical_prediction_candidate_cursor[contract.cache_key] = original_cursor
        else:
            server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)


def test_ordinal_gate_string_key_lookup_from_java_json() -> None:
    """Java sends Map<Integer,Long> → JSON keys are strings; verify str key lookup works."""
    contract = _mk_contract()
    cand = _mk_candidate(bar_ticks=100, horizon=4, uid="oco_first_touch_clean__all__k2")
    canonical = "oco|EURUSD|100|h4|oco_first_touch_clean__all__k2"
    ordinal_index = {canonical: [3]}

    original_mode = server._config.historical_prediction_universe_mode
    original_tolerance = server._config.historical_prediction_ordinal_tolerance
    original_cursor = server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)
    original_is_hist = server._is_historical_mode

    try:
        server._config.historical_prediction_universe_mode = "ordinal"
        server._config.historical_prediction_ordinal_tolerance = 0
        server._is_historical_mode = lambda: True

        with mock.patch(
            "src.behemoth.api.server._load_historical_prediction_candidate_ordinal_index",
            return_value=ordinal_index,
        ):
            # bar_ordinals keys are strings (as deserialized from JSON)
            result = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, tzinfo=timezone.utc),
                candidates=[cand],
                bar_ordinals={"100": 3},
            )
        assert result == [cand]
    finally:
        server._config.historical_prediction_universe_mode = original_mode
        server._config.historical_prediction_ordinal_tolerance = original_tolerance
        server._is_historical_mode = original_is_hist
        if original_cursor is not None:
            server._historical_prediction_candidate_cursor[contract.cache_key] = original_cursor
        else:
            server._historical_prediction_candidate_cursor.pop(contract.cache_key, None)


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
