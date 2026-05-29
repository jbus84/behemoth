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


def test_recompute_directional_run_uses_label_side_for_reversion() -> None:
    """directional_run reversion bets must verify via the label side.

    The legacy path hardcoded continuation (+run_sign), so reversion-bet
    candidates mismatched every row (~0%). With label_gross provided, the side
    follows the label, so a reversion event (label sign opposite the recent run)
    verifies. Regression guard for the directional_run catastrophic-FAIL case.
    """
    from scripts.verify_tick_exact_shortlist import _recompute_directional

    horizon = 1
    bars = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(
                ["2025-01-01 00:00:00", "2025-01-01 01:00:00"], utc=True
            ),
            "ret1_pips": [3.0, 1.0],  # recent up-run → continuation would bet long
            f"y_fwd_pips_h{horizon}": [4.4, np.nan],
        }
    )
    idx = np.array([0], dtype=np.int64)
    label_gross = np.array([-4.4], dtype=float)  # reversion bet (short) despite up-run

    out = _recompute_directional(
        bars=bars,
        idx=idx,
        horizon=horizon,
        family="directional_run",
        symbol="EURUSD",
        label_gross=label_gross,
    )

    # Side follows the label (short), so expected == label, not +4.4 (continuation).
    assert out["expected_gross_pips"][0] == pytest.approx(-4.4, abs=1e-9)
    assert out["expected_decided"][0]


def test_recompute_barrier_path_parses_double_touch_state_id() -> None:
    """Verify _recompute_barrier_path correctly parses double_touch state_id params.

    This test verifies that the state_id regex correctly extracts sweep_dir,
    a_pips, b_pips, window_A, window_B, h2 from the canonical state_id format.
    """
    from scripts.verify_tick_exact_shortlist import _DOUBLE_TOUCH_STATE_RX

    # Event with double_touch state_id encoding sweep_dir=up, a=10, b=5, wA=20, wB=20, h=10
    state_id = "double_touch__london__up_a10_b5_wA20_wB20_h10"

    # Verify the regex parsed the state_id correctly
    m = _DOUBLE_TOUCH_STATE_RX.search(state_id)
    assert m is not None
    assert m.group(1) == "up"  # sweep_dir
    assert float(m.group(2)) == 10.0  # a_pips
    assert float(m.group(3)) == 5.0  # b_pips
    assert int(m.group(4)) == 20  # wA
    assert int(m.group(5)) == 20  # wB
    assert int(m.group(6)) == 10  # h2

    # Also test with decimal values (e.g., from :g formatting)
    state_id_decimal = "double_touch__london__down_a15.5_b2.3_wA10_wB10_h5"
    m2 = _DOUBLE_TOUCH_STATE_RX.search(state_id_decimal)
    assert m2 is not None
    assert m2.group(1) == "down"
    assert float(m2.group(2)) == 15.5
    assert float(m2.group(3)) == 2.3


def test_recompute_barrier_path_parses_pullback_state_id() -> None:
    """Verify _recompute_barrier_path correctly parses pullback state_id params."""
    from scripts.verify_tick_exact_shortlist import _PULLBACK_STATE_RX

    # Event with pullback state_id: impulse_dir=down, M=25, R=0.618, wI=15, wP=15, wR=15, h=20
    state_id = "pullback__london__down_M25_R0.618_wI15_wP15_wR15_h20"

    # Verify the regex parsed the state_id correctly
    m = _PULLBACK_STATE_RX.search(state_id)
    assert m is not None
    assert m.group(1) == "down"  # impulse_dir
    assert float(m.group(2)) == 25.0  # m_pips
    assert float(m.group(3)) == 0.618  # r_frac
    assert int(m.group(4)) == 15  # wI
    assert int(m.group(5)) == 15  # wP
    assert int(m.group(6)) == 15  # wR
    assert int(m.group(7)) == 20  # h

    # Also test with decimal M values
    state_id_decimal = "pullback__london__up_M10.5_R0.382_wI10_wP10_wR10_h15"
    m2 = _PULLBACK_STATE_RX.search(state_id_decimal)
    assert m2 is not None
    assert m2.group(1) == "up"
    assert float(m2.group(2)) == 10.5
    assert float(m2.group(3)) == 0.382


def test_double_touch_state_rx_matches_underscore_regimes() -> None:
    """Regime segments contain underscores (low_cost_q30, high_abs_vel_q70, …);
    the regex must still parse the trailing params. Regression for a prefix-based
    regex that only matched single-token regimes like 'london'."""
    from scripts.verify_tick_exact_shortlist import _DOUBLE_TOUCH_STATE_RX, _PULLBACK_STATE_RX

    m = _DOUBLE_TOUCH_STATE_RX.search(
        "double_touch__low_cost_q30_and_high_range_q70__up_a10_b2_wA10_wB10_h3"
    )
    assert m is not None and m.group(1) == "up" and int(m.group(6)) == 3
    m2 = _PULLBACK_STATE_RX.search(
        "pullback__low_cost_q30_and_high_range_q70__down_M2_R0.382_wI10_wP10_wR10_h1"
    )
    assert m2 is not None and m2.group(1) == "down" and float(m2.group(3)) == 0.382


def test_recompute_barrier_path_maps_events_to_engine_gross(monkeypatch) -> None:
    """End-to-end mapping guard: an event whose close_ts matches a frame bar must
    receive the engine's gross for that bar index. Regression for the tz-stripping
    `.values` bug that made every event fail to map (all-NaN)."""
    import scripts.verify_tick_exact_shortlist as vmod

    frame = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(
                ["2025-01-01 00:00:00", "2025-01-01 01:00:00", "2025-01-01 02:00:00"],
                utc=True,
            ),
            "close_bid": [1.10, 1.10, 1.10],
            "low_bid": [1.10, 1.10, 1.10],
            "high_ask": [1.10, 1.10, 1.10],
            "close_ask": [1.10, 1.10, 1.10],
        }
    )
    # Event maps to frame bar index 1; engine returns gross 3.5 for i0==1.
    events = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(["2025-01-01 01:00:00"], utc=True),
            "state_id": ["double_touch__low_cost_q30__up_a10_b2_wA10_wB10_h1"],
            "target_gross_pips": [3.5],
        }
    )

    def fake_engine(frame, **kwargs):
        return {
            "i0": np.array([0, 1, 2], dtype=np.int64),
            "gross": np.array([np.nan, 3.5, np.nan], dtype=float),
            "decided": np.array([False, True, False]),
        }

    monkeypatch.setattr(vmod, "_double_touch_precompute", fake_engine)
    out = vmod._recompute_barrier_path(
        frame=frame, events=events, family="double_touch", symbol="EURUSD"
    )
    assert out["expected_gross_pips"][0] == pytest.approx(3.5, abs=1e-9)
    assert out["expected_decided"][0]
    assert out["map_ok"][0]


def test_recompute_barrier_path_handles_non_zero_based_event_index(monkeypatch) -> None:
    """The caller passes events sliced from the `d` frame, whose index is NOT
    0-based. The returned arrays are positional (length len(events)); indexing
    them with a raw index label (e.g. 188) on a short leg raised IndexError.
    Regression: a single event carrying a large index label must still map."""
    import scripts.verify_tick_exact_shortlist as vmod

    frame = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(
                ["2025-01-01 00:00:00", "2025-01-01 01:00:00"], utc=True
            ),
            "close_bid": [1.10, 1.10],
            "low_bid": [1.10, 1.10],
            "high_ask": [1.10, 1.10],
            "close_ask": [1.10, 1.10],
        }
    )
    # One event, but its pandas index label is 188 (as in a real `d` slice) —
    # far larger than len(events)==1.
    events = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(["2025-01-01 01:00:00"], utc=True),
            "state_id": ["double_touch__high_abs_vel_q70__up_a10_b2_wA10_wB10_h1"],
            "target_gross_pips": [2.0],
        },
        index=[188],
    )

    def fake_engine(frame, **kwargs):
        return {
            "i0": np.array([0, 1], dtype=np.int64),
            "gross": np.array([np.nan, 2.0], dtype=float),
            "decided": np.array([False, True]),
        }

    monkeypatch.setattr(vmod, "_double_touch_precompute", fake_engine)
    out = vmod._recompute_barrier_path(
        frame=frame, events=events, family="double_touch", symbol="EURUSD"
    )
    # Positional array of length 1; must not raise and must map the event.
    assert len(out["expected_gross_pips"]) == 1
    assert out["expected_gross_pips"][0] == pytest.approx(2.0, abs=1e-9)
    assert out["expected_decided"][0]
