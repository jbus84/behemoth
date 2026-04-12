from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from scripts.verify_oco_tick_exact_shortlist import (
    _normalize_shortlist_states,
    _recompute_first_touch,
    _resolve_shortlist_state_csv,
    run,
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


def test_run_accepts_partial_read_from_explicit_schema_velocity(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    symbol = "EURUSD"
    bar_ticks = 1000
    dataset_dir = tmp_path / "data/analysis/tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    velocity_path = dataset_dir / f"{symbol}_{bar_ticks}tick_velocity.parquet"
    close_ts = pd.Timestamp(datetime(2025, 1, 1, 0, 30, tzinfo=timezone.utc))
    pd.DataFrame(
        [
            {
                "timestamp": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
                "close_ts": close_ts.to_pydatetime(),
                "close_bid": 1.1000,
                "high_bid": 1.1010,
                "low_bid": 1.0990,
                "high_ask": 1.1012,
                "close_ask": 1.1002,
                "hl_first": 1.0,
            },
            {
                "timestamp": datetime(2025, 1, 1, 0, 30, tzinfo=timezone.utc),
                "close_ts": datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc),
                "close_bid": 1.1005,
                "high_bid": 1.1015,
                "low_bid": 1.1000,
                "high_ask": 1.1017,
                "close_ask": 1.1007,
                "hl_first": -1.0,
            },
        ]
    ).to_parquet(velocity_path, index=False)

    shortlist_state_csv = tmp_path / "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv"
    shortlist_state_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "bar_ticks": bar_ticks,
                "horizon": 3,
                "state_id": "oco_first_touch_clean_k2",
                "barrier_pips": 2.0,
            }
        ]
    ).to_csv(shortlist_state_csv, index=False)

    pred_path = tmp_path / "predictions.parquet"
    pd.DataFrame(
        [
            {
                "candidate_uid": f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_clean_k2",
                "close_ts": close_ts.to_pydatetime(),
                "test_month": "2025-01",
                "pred_prob": 0.95,
                "target_gross_pips": 0.0,
            }
        ]
    ).to_parquet(pred_path, index=False)

    cfg = {
        "symbol": symbol,
        "dataset_dir": str(dataset_dir),
        "pred_path": str(pred_path),
        "shortlist_state_csv": str(shortlist_state_csv),
        "out_summary_csv": str(tmp_path / "summary.csv"),
        "out_monthly_csv": str(tmp_path / "monthly.csv"),
        "out_state_csv": str(tmp_path / "state.csv"),
        "report_out": str(tmp_path / "report.md"),
        "locked_quantile": 0.9,
        "selection_mode": "monthly_quantile",
        "family_required": "oco_first_touch_clean",
        "oco_hold_mode": "from_touch",
        "oco_include_no_touch": True,
    }

    summary, state, monthly = run(cfg)

    assert not summary.empty
    assert not state.empty
    assert not monthly.empty


def test_recompute_first_touch_uses_ask_side_for_buy_touch_and_sell_exit() -> None:
    out = _recompute_first_touch(
        close_bid=pd.Series([1.1000, 1.1000, 1.10015, 1.1000]).to_numpy(dtype=float),
        high_bid=pd.Series([1.1000, 1.1001, 1.1000, 1.1000]).to_numpy(dtype=float),
        low_bid=pd.Series([1.1000, 1.0995, 1.1000, 1.1000]).to_numpy(dtype=float),
        high_ask=pd.Series([1.1000, 1.1002, 1.1000, 1.1000]).to_numpy(dtype=float),
        close_ask=pd.Series([1.1002, 1.1003, 1.1004, 1.1005]).to_numpy(dtype=float),
        hlf=pd.Series([0.0, 1.0, 0.0, 0.0]).to_numpy(dtype=float),
        idx=pd.Series([0]).to_numpy(dtype="int64"),
        horizon=1,
        barrier_pips=1.5,
        pip=0.0001,
        hold_mode="from_touch",
        include_no_touch=False,
    )

    assert out["expected_side"][0] == 1
    assert out["expected_decided"][0]
    assert out["expected_gross_pips"][0] == pytest.approx(0.0, abs=1e-9)

    sell = _recompute_first_touch(
        close_bid=pd.Series([1.1000, 1.1000, 1.1000, 1.1000]).to_numpy(dtype=float),
        high_bid=pd.Series([1.1000, 1.1000, 1.1000, 1.1000]).to_numpy(dtype=float),
        low_bid=pd.Series([1.1000, 1.0998, 1.1000, 1.1000]).to_numpy(dtype=float),
        high_ask=pd.Series([1.1002, 1.1002, 1.1002, 1.1002]).to_numpy(dtype=float),
        close_ask=pd.Series([1.1002, 1.1003, 1.1003, 1.1005]).to_numpy(dtype=float),
        hlf=pd.Series([0.0, -1.0, 0.0, 0.0]).to_numpy(dtype=float),
        idx=pd.Series([0]).to_numpy(dtype="int64"),
        horizon=1,
        barrier_pips=1.5,
        pip=0.0001,
        hold_mode="from_touch",
        include_no_touch=False,
    )

    assert sell["expected_side"][0] == -1
    assert sell["expected_decided"][0]
    assert sell["expected_gross_pips"][0] == pytest.approx(-4.5, abs=1e-9)
