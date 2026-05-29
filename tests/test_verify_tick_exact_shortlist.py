from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from scripts.build_tick_opportunity_ml_dataset import _oco_precompute
from scripts.run_tick_opportunity_mining import _pip_size
from scripts.verify_tick_exact_shortlist import (
    _merge_config,
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
        / "data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCHF_oco_first_touch_reduced_state_schedule.csv"
    )
    schedule.parent.mkdir(parents=True, exist_ok=True)
    schedule.write_text("symbol,test_month,bar_ticks,horizon,state_id\n", encoding="utf-8")
    picked = _resolve_shortlist_state_csv(
        "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_first_touch_reduced_states.csv",
        symbol="USDCHF",
    )
    assert picked.resolve() == schedule.resolve()


def test_merge_config_derives_symbol_specific_outputs_when_not_explicit() -> None:
    import argparse

    cfg = _merge_config(
        argparse.Namespace(
            config=None,
            symbol="GBPUSD",
            dataset_dir=None,
            pred_path=None,
            shortlist_state_csv=None,
            locked_quantile=None,
            selection_mode=None,
            family_required=None,
            oco_hold_mode=None,
            oco_include_no_touch=None,
            sample_rows_per_combo=None,
            abs_tol_pips=None,
            min_exact_match_rate=None,
            min_pos_label_match_rate=None,
            out_summary_csv=None,
            out_monthly_csv=None,
            out_state_csv=None,
            report_out=None,
        )
    )

    assert cfg["pred_path"].endswith(
        "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/GBPUSD_oco_first_touch_monthly_predictions.parquet"
    )
    assert cfg["shortlist_state_csv"].endswith(
        "data/analysis/tick_opportunity_mining/reduced_core/GBPUSD_oco_first_touch_reduced_states.csv"
    )
    assert cfg["out_summary_csv"].endswith(
        "data/analysis/tick_opportunity_mining/reduced_core/GBPUSD_oco_first_touch_tick_exact_summary.csv"
    )
    assert cfg["out_monthly_csv"].endswith(
        "data/analysis/tick_opportunity_mining/reduced_core/GBPUSD_oco_first_touch_tick_exact_monthly.csv"
    )
    assert cfg["out_state_csv"].endswith(
        "data/analysis/tick_opportunity_mining/reduced_core/GBPUSD_oco_first_touch_tick_exact_state.csv"
    )
    assert cfg["report_out"].endswith("docs/analysis/gbpusd_oco_first_touch_tick_exact_shortlist_report.md")


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

    shortlist_state_csv = tmp_path / "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_first_touch_reduced_states.csv"
    shortlist_state_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "bar_ticks": bar_ticks,
                "horizon": 3,
                "state_id": "oco_first_touch_k2",
                "barrier_pips": 2.0,
            }
        ]
    ).to_csv(shortlist_state_csv, index=False)

    pred_path = tmp_path / "predictions.parquet"
    pd.DataFrame(
        [
            {
                "candidate_uid": f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_k2",
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
        "family_required": "oco_first_touch",
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
        low_bid=pd.Series([1.1000, 1.0999, 1.1000, 1.1000]).to_numpy(dtype=float),
        high_ask=pd.Series([1.1000, 1.1004, 1.1000, 1.1000]).to_numpy(dtype=float),
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
    assert out["expected_gross_pips"][0] == pytest.approx(-1.5, abs=1e-9)

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
    assert sell["expected_gross_pips"][0] == pytest.approx(-3.0, abs=1e-9)


def test_family_required_directional_is_accepted() -> None:
    from scripts.verify_tick_exact_shortlist import _normalise_family_required

    assert _normalise_family_required("directional") == "directional"


def test_recompute_first_touch_matches_oco_precompute_from_touch_contract() -> None:
    rows = 140
    close_bid = 1.1000 + np.arange(rows) * 0.00025
    close_ask = close_bid + 0.0001
    df = pd.DataFrame(
        {
            "close_bid": close_bid,
            "high_bid": close_bid + 0.00005,
            "low_bid": close_bid - 0.00005,
            "high_ask": close_ask + 0.00025,
            "close_ask": close_ask,
            "hl_first": np.ones(rows),
        }
    )
    prep = _oco_precompute(
        df,
        horizon=1,
        barrier_pips=2.0,
        pip=_pip_size("EURUSD"),
        hold_mode="from_touch",
    )

    out = _recompute_first_touch(
        close_bid=df["close_bid"].to_numpy(dtype=float),
        high_bid=df["high_bid"].to_numpy(dtype=float),
        low_bid=df["low_bid"].to_numpy(dtype=float),
        high_ask=df["high_ask"].to_numpy(dtype=float),
        close_ask=df["close_ask"].to_numpy(dtype=float),
        hlf=df["hl_first"].to_numpy(dtype=float),
        idx=prep["i0"],
        horizon=1,
        barrier_pips=2.0,
        pip=_pip_size("EURUSD"),
        hold_mode="from_touch",
        include_no_touch=True,
    )

    np.testing.assert_allclose(out["expected_gross_pips"], np.nan_to_num(prep["gross"], nan=0.0))
    np.testing.assert_array_equal(out["expected_side"], prep["side"])
    np.testing.assert_array_equal(out["expected_decided"], prep["decided"])
    np.testing.assert_array_equal(out["expected_both_window"], prep["both_touched_lookahead"])


def test_recompute_directional_uses_label_side_not_quantile_recompute() -> None:
    """Directional/directional_inverse verify tick-exact return magnitude against label side.

    This test demonstrates the fix for the quantile-boundary sign-flip issue:
    when the tick-exact return magnitude matches the label magnitude but the
    recomputed quantile side flips, the verification should still PASS because
    it verifies the price path (magnitude) against the label, not the regime side.
    """
    from scripts.verify_tick_exact_shortlist import _recompute_directional

    # Create a minimal bars frame with forward returns
    horizon = 1
    bars = pd.DataFrame(
        {
            "close_ts": pd.to_datetime([
                "2025-01-01 00:00:00",
                "2025-01-01 01:00:00",
                "2025-01-01 02:00:00",
                "2025-01-01 03:00:00",
            ], utc=True),
            f"y_fwd_pips_h{horizon}": [5.1, -3.2, 2.5, np.nan],
        }
    )

    # Event at index 0: label is -5.1 (short), tick-exact y is 5.1 (magnitude matches)
    # The quantile-recomputed side would be +1 (long), but label_gross sign is -5.1 (short).
    # With the fix, we expect expected_gross_pips = sign(-5.1) * sign(5.1) * 5.1 = -5.1 (matches label)
    idx = np.array([0], dtype=np.int64)
    label_gross = np.array([-5.1], dtype=float)

    out = _recompute_directional(
        bars=bars,
        idx=idx,
        horizon=horizon,
        family="directional",
        symbol="EURUSD",
        label_gross=label_gross,
    )

    # With the fix: expected_gross_pips should match label_gross in sign and magnitude
    assert np.isfinite(out["expected_gross_pips"][0])
    assert out["expected_gross_pips"][0] == pytest.approx(-5.1, abs=1e-9)
    assert out["expected_decided"][0]


def test_recompute_directional_detects_magnitude_mismatch() -> None:
    """Directional verification should FAIL when tick-exact magnitude differs from label."""
    from scripts.verify_tick_exact_shortlist import _recompute_directional

    horizon = 1
    bars = pd.DataFrame(
        {
            "close_ts": pd.to_datetime([
                "2025-01-01 00:00:00",
                "2025-01-01 01:00:00",
            ], utc=True),
            f"y_fwd_pips_h{horizon}": [5.1, np.nan],
        }
    )

    # Event at index 0: label is 3.2, but tick-exact y is 5.1 (magnitude mismatch)
    idx = np.array([0], dtype=np.int64)
    label_gross = np.array([3.2], dtype=float)

    out = _recompute_directional(
        bars=bars,
        idx=idx,
        horizon=horizon,
        family="directional",
        symbol="EURUSD",
        label_gross=label_gross,
    )

    # Should compute expected as sign(3.2) * 5.1 = 5.1, which does NOT match label 3.2
    assert np.isfinite(out["expected_gross_pips"][0])
    assert out["expected_gross_pips"][0] == pytest.approx(5.1, abs=1e-9)
    assert out["expected_gross_pips"][0] != pytest.approx(label_gross[0], abs=1e-9)


def test_recompute_directional_inverse_uses_label_sign_without_extra_inversion() -> None:
    """directional_inverse must NOT re-invert the side.

    The stored label already bakes in the inverse convention (mining wrote
    (-side)*y), so sign(label) is the realised inverse bias. expected_gross must
    be sign(label) * |y| for directional_inverse too — applying an extra
    negation would yield -label and mismatch every row (regression guard).
    """
    from scripts.verify_tick_exact_shortlist import _recompute_directional

    horizon = 1
    bars = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(
                ["2025-01-01 00:00:00", "2025-01-01 01:00:00"], utc=True
            ),
            f"y_fwd_pips_h{horizon}": [2.6, np.nan],
        }
    )
    idx = np.array([0], dtype=np.int64)
    label_gross = np.array([-2.6], dtype=float)  # inverse label, magnitude matches |y|

    out = _recompute_directional(
        bars=bars,
        idx=idx,
        horizon=horizon,
        family="directional_inverse",
        symbol="EURUSD",
        label_gross=label_gross,
    )

    # Must equal the label (-2.6), NOT +2.6 (which an extra inversion would give).
    assert out["expected_gross_pips"][0] == pytest.approx(-2.6, abs=1e-9)
    assert out["expected_decided"][0]
