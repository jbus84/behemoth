from __future__ import annotations

import pandas as pd

from scripts.verify_oco_tick_exact_shortlist import (
    _normalize_shortlist_states,
    _resolve_shortlist_state_csv,
)


def test_normalize_shortlist_states_filters_symbol_and_latest_month() -> None:
    states = pd.DataFrame(
        [
            {"symbol": "EURUSD", "test_month": "2025-12", "state_id": "legacy"},
            {"symbol": "EURUSD", "test_month": "2026-01", "state_id": "s1"},
            {"symbol": "EURUSD", "test_month": "2026-01", "state_id": "s2"},
            {"symbol": "GBPUSD", "test_month": "2026-01", "state_id": "other_symbol"},
        ]
    )
    out = _normalize_shortlist_states(states, symbol="EURUSD")
    assert sorted(out["state_id"].astype(str).tolist()) == ["s1", "s2"]
    assert set(out["symbol"].astype(str).str.upper()) == {"EURUSD"}
    assert set(out["test_month"].astype(str)) == {"2026-01"}


def test_normalize_shortlist_states_without_test_month_keeps_symbol_rows() -> None:
    states = pd.DataFrame(
        [
            {"symbol": "USDJPY", "state_id": "a"},
            {"symbol": "USDJPY", "state_id": "b"},
            {"symbol": "EURUSD", "state_id": "c"},
        ]
    )
    out = _normalize_shortlist_states(states, symbol="USDJPY")
    assert sorted(out["state_id"].astype(str).tolist()) == ["a", "b"]
    assert set(out["symbol"].astype(str).str.upper()) == {"USDJPY"}


def test_resolve_shortlist_prefers_symbol_schedule_over_default(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    schedule = (
        tmp_path
        / "data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCHF_oco_reduced_state_schedule.csv"
    )
    schedule.parent.mkdir(parents=True, exist_ok=True)
    schedule.write_text("symbol,test_month,bar_ticks,horizon,state_id\n", encoding="utf-8")
    picked = _resolve_shortlist_state_csv(
        "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv",
        symbol="USDCHF",
    )
    assert picked.resolve() == schedule.resolve()
