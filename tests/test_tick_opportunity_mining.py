from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from behemoth.core.features import _extract_core_series
from scripts.analyze_oco_stop_limit_tickfill import _rebuild_touch_events
from scripts.run_tick_opportunity_mining import (
    _assign_quality_tier,
    _double_touch_precompute,
    _oco_precompute_candidates,
    run,
)

# Captured from pre-refactor `run()` — see test_mining_run_output_is_stable.
_PARITY: dict = {
    "directional_rows": 45,
    "oco_rows": 8,
    "directional_cols": [
        "annualized_test_fills",
        "bar_ticks",
        "both_window_rate",
        "both_window_rate_train",
        "candidate_schema_version",
        "family",
        "gross_std_test",
        "hit_rate_gross_test",
        "horizon",
        "mean_flow_persistence_train",
        "mean_gross_pips_test",
        "mean_gross_pips_train",
        "mean_tick_burst_train",
        "mean_vol_cluster_train",
        "median_gross_pips_test",
        "median_gross_pips_train",
        "ml_ready_target_type",
        "p_up_first",
        "quality_score",
        "quality_tier",
        "quality_tier_basis",
        "random_baseline_control_mean",
        "random_baseline_p",
        "random_baseline_z",
        "regime_desc",
        "selection_pass",
        "selection_pass_basis",
        "session_coverage",
        "state_id",
        "symbol",
        "test_count",
        "train_count",
    ],
    "oco_cols": [
        "annualized_test_fills",
        "bar_ticks",
        "both_window_rate",
        "both_window_rate_train",
        "candidate_schema_version",
        "family",
        "gross_std_test",
        "hit_rate_gross_test",
        "horizon",
        "mean_flow_persistence_train",
        "mean_gross_pips_test",
        "mean_gross_pips_train",
        "mean_tick_burst_train",
        "mean_vol_cluster_train",
        "median_gross_pips_test",
        "median_gross_pips_train",
        "ml_ready_target_type",
        "p_up_first",
        "quality_score",
        "quality_tier",
        "quality_tier_basis",
        "random_baseline_control_mean",
        "random_baseline_p",
        "random_baseline_z",
        "regime_desc",
        "selection_pass",
        "selection_pass_basis",
        "session_coverage",
        "state_id",
        "symbol",
        "test_count",
        "train_count",
    ],
}


def _build_synth_tick_velocity(path: Path, *, symbol: str) -> None:
    rng = np.random.default_rng(7)
    chunks: list[pd.DataFrame] = []
    for year in [2022, 2023, 2024, 2025]:
        ts = pd.date_range(f"{year}-01-01", periods=420, freq="30min", tz="UTC")
        drift = 0.00002 if year == 2025 else 0.00001
        step = drift + rng.normal(0.0, 0.00003, size=len(ts))
        close = 1.10 + np.cumsum(step)
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) + np.abs(rng.normal(0.00002, 0.00001, size=len(ts)))
        low = np.minimum(open_, close) - np.abs(rng.normal(0.00002, 0.00001, size=len(ts)))
        d = pd.DataFrame(
            {
                "symbol": symbol,
                "bar_ticks": 1000,
                "timestamp": ts - pd.to_timedelta(30, unit="m"),
                "close_ts": ts,
                "open_bid": open_,
                "high_bid": high,
                "low_bid": low,
                "close_bid": close,
                "high_ask": high + 0.0001,
                "close_ask": close + 0.0001,
                "spread": 0.0001,
                "cost_est_pips": 0.25 + np.abs(rng.normal(0.0, 0.03, size=len(ts))),
                "range_pips": (high - low) / 0.0001,
                "hour_utc": ts.hour.astype(int),
                "spread_z": rng.normal(0.0, 1.0, size=len(ts)),
                "tick_rate_z": rng.normal(0.0, 1.0, size=len(ts)),
                "vel_cost_units_h1": rng.normal(0.0, 1.0, size=len(ts)),
                "vel_pips_h1": (close - pd.Series(close).shift(1).fillna(close[0])) / 0.0001,
                "vel_z_h1": rng.normal(0.0, 1.0, size=len(ts)),
                "hl_first": rng.choice([-1.0, 1.0], size=len(ts)),
                "hl_first_mean_24": rng.normal(0.0, 0.25, size=len(ts)),
            }
        )
        chunks.append(d)
    out = pd.concat(chunks, ignore_index=True)
    out.to_parquet(path, index=False)


def _build_legacy_velocity_bars(path: Path, *, symbol: str, bar_ticks: int) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=240, freq="30min", tz="UTC")
    close = 1.10 + np.linspace(0.0, 0.003, len(ts))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.0002
    low = np.minimum(open_, close) - 0.0002
    bars = pd.DataFrame(
        {
            "symbol": symbol,
            "bar_ticks": bar_ticks,
            "timestamp": ts - pd.to_timedelta(30, unit="m"),
            "close_ts": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "ask": close + 0.0001,
            "hl_first": np.where(np.arange(len(ts)) % 2 == 0, 1.0, -1.0),
        }
    )
    bars.to_parquet(path, index=False)
    return bars


def _build_explicit_velocity_bars(path: Path, *, symbol: str, bar_ticks: int) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=240, freq="30min", tz="UTC")
    close = 1.10 + np.linspace(0.0, 0.003, len(ts))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.0002
    low = np.minimum(open_, close) - 0.0002
    bars = pd.DataFrame(
        {
            "symbol": symbol,
            "bar_ticks": bar_ticks,
            "timestamp": ts - pd.to_timedelta(30, unit="m"),
            "close_ts": ts,
            "open_bid": open_,
            "high_bid": high,
            "low_bid": low,
            "close_bid": close,
            "high_ask": high + 0.0001,
            "close_ask": close + 0.0001,
            "spread": 0.0001,
            "hl_first": np.where(np.arange(len(ts)) % 2 == 0, 1.0, -1.0),
        }
    )
    bars.to_parquet(path, index=False)
    return bars


def test_tick_opportunity_mining_outputs(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    symbol = "EURUSD"
    data_path = dataset_dir / f"{symbol}_1000tick_velocity.parquet"
    _build_synth_tick_velocity(data_path, symbol=symbol)

    cfg = {
        "symbol": symbol,
        "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000",
        "horizons": "1,2,3",
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "min_annual_fills": 50.0,
        "gross_metric": "mean",
        "library_type": "separate",
        "barrier_grid_pips": "2,3",
    }
    directional, oco, summary = run(cfg)

    assert not directional.empty
    assert not oco.empty
    assert not summary.empty
    assert {"state_id", "mean_gross_pips_test", "annualized_test_fills", "selection_pass"}.issubset(
        directional.columns
    )
    assert {"state_id", "both_window_rate", "p_up_first", "selection_pass"}.issubset(oco.columns)
    assert directional["selection_pass"].isin([True, False]).all()
    assert oco["selection_pass"].isin([True, False]).all()


def test_extract_core_series_rejects_legacy_mining_shape() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-01-01T00:00:00Z"]),
            "close_ts": pd.to_datetime(["2025-01-01T00:30:00Z"]),
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.0],
        }
    )

    with pytest.raises(ValueError, match="legacy ambiguous bar schema unsupported"):
        _extract_core_series(df)


def test_stop_limit_tickfill_rejects_legacy_ambiguous_bar_schema(tmp_path: Path) -> None:
    symbol = "EURUSD"
    bar_ticks = 1000
    velocity_dir = tmp_path / "tick_velocity"
    velocity_dir.mkdir(parents=True, exist_ok=True)
    bars = _build_legacy_velocity_bars(
        velocity_dir / f"{symbol}_{bar_ticks}tick_velocity.parquet",
        symbol=symbol,
        bar_ticks=bar_ticks,
    )
    pred_path = tmp_path / "predictions.parquet"
    pd.DataFrame(
        {
            "close_ts": [bars.loc[150, "close_ts"]],
            "candidate_uid": [f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_k2"],
            "target_gross_pips": [2.0],
            "pred_prob": [0.95],
        }
    ).to_parquet(pred_path, index=False)

    with pytest.raises(ValueError, match="legacy ambiguous bar schema unsupported"):
        _rebuild_touch_events(
            symbol=symbol,
            pred_path=pred_path,
            velocity_dir=velocity_dir,
            use_exec_selected=False,
            quantile=0.9,
        )


def test_stop_limit_tickfill_accepts_partial_read_from_explicit_schema_velocity(tmp_path: Path) -> None:
    symbol = "EURUSD"
    bar_ticks = 1000
    velocity_dir = tmp_path / "tick_velocity"
    velocity_dir.mkdir(parents=True, exist_ok=True)
    bars = _build_explicit_velocity_bars(
        velocity_dir / f"{symbol}_{bar_ticks}tick_velocity.parquet",
        symbol=symbol,
        bar_ticks=bar_ticks,
    )
    pred_path = tmp_path / "predictions.parquet"
    pd.DataFrame(
        {
            "close_ts": [bars.loc[150, "close_ts"]],
            "candidate_uid": [f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_k2"],
            "target_gross_pips": [2.0],
            "pred_prob": [0.95],
        }
    ).to_parquet(pred_path, index=False)

    events = _rebuild_touch_events(
        symbol=symbol,
        pred_path=pred_path,
        velocity_dir=velocity_dir,
        use_exec_selected=False,
        quantile=0.9,
    )

    assert not events.empty
    assert events.loc[0, "candidate_uid"] == f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_k2"


def _build_oco_semantics_frame(
    *,
    rows: int = 140,
    trigger_gap: float = 0.00025,
    step: float = 0.00025,
    seed: int | None = None,
) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=rows, freq="30min", tz="UTC")
    close_bid = 1.1000 + np.arange(rows) * step
    close_ask = close_bid + 0.0001
    high_bid = close_bid + 0.00005
    high_ask = close_ask + trigger_gap
    low_bid = close_bid - 0.00005
    out = pd.DataFrame(
        {
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "timestamp": ts - pd.to_timedelta(30, unit="m"),
            "close_ts": ts,
            "open_bid": np.r_[close_bid[0], close_bid[:-1]],
            "high_bid": high_bid,
            "low_bid": low_bid,
            "close_bid": close_bid,
            "high_ask": high_ask,
            "close_ask": close_ask,
            "spread": 0.0001,
            "cost_est_pips": 0.2,
            "range_pips": (high_bid - low_bid) / 0.0001,
            "hour_utc": 8,
            "spread_z": 0.0,
            "tick_rate_z": 0.0,
            "vel_cost_units_h1": 1.0,
            "vel_abs_cost_units_h1": 1.0,
            "ret1_pips": 0.0,
            "ret_z": 0.0,
            "ret_abs_z": 0.0,
            "hl_first": 1.0,
            "hl_first_mean_24": 0.5,
            "hl_pos_frac_mean_24": 1.0,
        }
    )
    if seed is not None:
        rng = np.random.default_rng(seed)
        out["tick_burst_score"] = rng.normal(0.0, 1.0, size=rows)
        out["quote_revision_rate_z"] = rng.normal(0.0, 1.0, size=rows)
        out["directional_persistence_8"] = rng.integers(-10, 11, size=rows).astype(float)
        out["signed_flow_24"] = rng.normal(0.0, 1.0, size=rows)
        out["vol_cluster_score"] = rng.exponential(2.0, size=rows)
        out["session_marker"] = rng.choice(["london", "ny", "asia"], size=rows)
    return out


def test_oco_precompute_candidates_uses_signal_close_ask_for_buy_trigger() -> None:
    frame = _build_oco_semantics_frame(trigger_gap=0.00015, step=0.0)

    prep = _oco_precompute_candidates(
        frame,
        symbol="EURUSD",
        horizon=1,
        barrier_pips=2.0,
    )

    assert prep
    assert int(prep["decided"].sum()) == 0


def test_oco_precompute_candidates_uses_touch_bar_close_for_gross() -> None:
    frame = _build_oco_semantics_frame(trigger_gap=0.00025)

    prep = _oco_precompute_candidates(
        frame,
        symbol="EURUSD",
        horizon=1,
        barrier_pips=2.0,
    )

    assert prep
    gross = prep["gross"][prep["decided"]]
    assert len(gross) > 100
    np.testing.assert_allclose(gross[:5], 1.5)


def test_oco_candidates_follow_touch_bar_close_contract() -> None:
    from scripts.mining_family import FAMILY_REGISTRY

    frame = _build_oco_semantics_frame(trigger_gap=0.00025)
    fam = FAMILY_REGISTRY["oco_first_touch"]
    params = {"horizon": 1, "barrier_pips": 2.0, "symbol": "EURUSD"}
    entries = fam.entry_indices(frame, np.full(len(frame), True), params)
    gross = fam.measure_gross(frame, entries, params)
    assert len(entries) > 100
    assert np.mean(gross) == pytest.approx(1.5)
    prep = fam._precompute(frame, "EURUSD", params)
    assert prep is not None
    decided = np.asarray(prep["decided"], dtype=bool)
    side = np.asarray(prep["side"], dtype=np.int8)
    p_up = float(np.mean(side[decided] > 0.0))
    assert p_up == pytest.approx(1.0)


def test_mining_emits_only_first_touch_family() -> None:
    """The mining pipeline must not emit any look-ahead-conditioned family.

    The old clean variant was conditioned on ~both (both barriers touched
    within the horizon — future information). Only oco_first_touch, whose
    universe is decided & reg_mask, is look-ahead-free.
    """
    from scripts.mining_family import FAMILY_REGISTRY, resolve_families

    assert resolve_families("oco") == ["oco_first_touch"]
    assert "oco_first_touch" in FAMILY_REGISTRY
    assert FAMILY_REGISTRY["oco_first_touch"].name == "oco_first_touch"
    assert "oco_first_touch_clean" not in FAMILY_REGISTRY


def test_quality_tier_does_not_condition_on_both() -> None:
    """Quality tiers must not gate on both_window_rate (look-ahead).

    A candidate with strong train metrics but a high both-touch rate must
    still be eligible for tier A — the both rate is not knowable per-trade.
    """
    df = pd.DataFrame([{
        "mean_gross_pips_train": 2.0,
        "median_gross_pips_train": 0.5,
        "train_count": 50000,
        "both_window_rate_train": 0.95,   # high whipsaw — previously blocked tier A
        "selection_pass": True,
    }])
    out = _assign_quality_tier(df, library="oco")
    assert out.loc[0, "quality_tier"] == "A"


def test_precompute_labels_lookahead_field_explicitly():
    """The both-touch field must be named to make its look-ahead nature
    self-evident, so it cannot be used as a filter by mistake."""
    frame = _build_oco_semantics_frame(rows=4000)
    prep = _oco_precompute_candidates(frame, symbol="EURUSD", horizon=6, barrier_pips=2.0)
    assert "both_touched_lookahead" in prep
    assert "both" not in prep


def test_mining_produces_microstructure_regime_candidates():
    """Mining must emit candidates for microstructure regimes."""
    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.run_tick_opportunity_mining import _quantiles, _regime_masks

    train = _build_oco_semantics_frame(rows=4000, seed=1)
    test = _build_oco_semantics_frame(rows=4000, seed=2)
    # Inject microstructure columns with enough variance (fallback)
    for col in [
        "tick_burst_score",
        "quote_revision_rate_z",
        "directional_persistence_8",
        "signed_flow_24",
        "vol_cluster_score",
        "session_marker",
    ]:
        if col not in train.columns:
            rng = np.random.default_rng(42)
            train[col] = rng.normal(0.0, 1.0, size=len(train))
            test[col] = rng.normal(0.0, 1.0, size=len(test))

    fam = FAMILY_REGISTRY["oco_first_touch"]
    q = _quantiles(train)
    masks = _regime_masks(test, q)
    params = {"horizon": 6, "barrier_pips": 2.0, "symbol": "EURUSD"}
    found_regimes = set()
    for name, mask in masks:
        entries = fam.entry_indices(test, np.asarray(mask, bool), params)
        if len(entries) > 0:
            found_regimes.add(name)
    expected_regimes = {
        "all",
        "high_intensity",
        "high_activity",
        "persistent_flow",
        "negative_flow",
        "high_vol_cluster",
    }
    assert expected_regimes <= found_regimes, f"missing regimes: {expected_regimes - found_regimes}"


def test_mining_raises_when_dataset_dir_missing(tmp_path: Path) -> None:
    cfg = {
        "symbol": "EURUSD",
        "dataset_dir": str(tmp_path / "does_not_exist"),
        "bar_ticks_grid": "1000",
        "horizons": "1,2,3",
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "min_annual_fills": 50.0,
        "gross_metric": "mean",
        "library_type": "separate",
        "barrier_grid_pips": "2,3",
    }
    with pytest.raises(FileNotFoundError, match="rebuild-all"):
        run(cfg)


def test_mining_raises_when_no_velocity_files_for_symbol(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "symbol": "EURUSD",
        "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000",
        "horizons": "1,2,3",
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "min_annual_fills": 50.0,
        "gross_metric": "mean",
        "library_type": "separate",
        "barrier_grid_pips": "2,3",
    }
    with pytest.raises(FileNotFoundError, match="no velocity files"):
        run(cfg)


def test_mining_run_output_is_stable(tmp_path: Path) -> None:
    """Post-refactor stability guard: the directional and oco candidate
    frames produced by run() must stay stable going forward. The _PARITY
    snapshot was re-captured after the family-framework refactor (Task 5).
    Future tasks must keep this green."""
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _build_synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                         symbol="EURUSD")
    cfg = {
        "symbol": "EURUSD",
        "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000",
        "horizons": "1,2,3",
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "min_annual_fills": 50.0,
        "gross_metric": "mean",
        "library_type": "separate",
        "barrier_grid_pips": "2,3",
    }
    directional, oco, summary = run(cfg)
    # Shape + key columns are stable; exact row counts depend on the synthetic
    # fixture and must not change across the refactor.
    snapshot = {
        "directional_rows": len(directional),
        "oco_rows": len(oco),
        "directional_cols": sorted(directional.columns.tolist()),
        "oco_cols": sorted(oco.columns.tolist()),
    }
    # Pin the snapshot: capture once on pre-refactor main, paste below.
    assert snapshot["directional_rows"] == _PARITY["directional_rows"]
    assert snapshot["oco_rows"] == _PARITY["oco_rows"]
    assert snapshot["directional_cols"] == _PARITY["directional_cols"]
    assert snapshot["oco_cols"] == _PARITY["oco_cols"]
    assert "random_baseline_z" in snapshot["directional_cols"] or directional.empty
    assert "random_baseline_z" in snapshot["oco_cols"] or oco.empty


def test_run_emits_random_baseline_columns(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _build_synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                         symbol="EURUSD")
    cfg = {
        "symbol": "EURUSD", "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000", "horizons": "1,2,3",
        "train_years": "2022,2023,2024", "test_year": 2025,
        "min_annual_fills": 50.0, "gross_metric": "mean",
        "library_type": "separate", "barrier_grid_pips": "2,3",
        "baseline_seed": 12345, "baseline_draws": 50,
    }
    directional, oco, summary = run(cfg)
    for df in (directional, oco):
        if not df.empty:
            for col in ("random_baseline_z", "random_baseline_p",
                        "random_baseline_control_mean"):
                assert col in df.columns


def _build_sweep_frame(n: int = 600) -> pd.DataFrame:
    """Steady downtrend with single-bar up-blips every 25 bars. A regime bar
    just before a blip sees an up-A barrier touched (the blip), then price
    drops back through the down-B barrier on the next bar, and the downtrend
    is the continuation. Deterministic — used to assert a sweep is detected."""
    pip = 0.0001
    drift = 1.20000 - 0.5 * pip * np.arange(n)
    blip = np.where(np.arange(n) % 25 == 1, 5.0 * pip, 0.0)
    close = drift + blip
    spread = 0.2 * pip
    return pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.3 * pip,
        "high_ask": close + spread + 0.3 * pip,
    })


def _build_flat_frame(n: int = 300) -> pd.DataFrame:
    """Constant price — no barrier is ever touched, so no sweep completes."""
    pip = 0.0001
    close = np.full(n, 1.20000)
    spread = 0.2 * pip
    return pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + spread + 0.1 * pip,
    })


def test_double_touch_precompute_detects_up_sweep() -> None:
    frame = _build_sweep_frame()
    out = _double_touch_precompute(
        frame, symbol="EURUSD", sweep_dir="up",
        a_pips=3.0, b_pips=3.0, window_A=5, window_B=5, h2=5,
    )
    assert out, "engine should return a populated dict for a long-enough frame"
    decided = np.asarray(out["decided"], dtype=bool)
    gross = np.asarray(out["gross"], dtype=float)
    assert decided.sum() > 0, "at least one A->B sweep should complete"
    # Up-sweep bets short; the downtrend continuation makes that profitable.
    assert np.nanmean(gross) > 0.0
    # Diagnostics are -1 where the leg did not fire, >=1 where it did.
    t_a = np.asarray(out["t_a_step"], dtype=np.int64)
    t_b = np.asarray(out["t_b_step"], dtype=np.int64)
    assert (t_a[decided] >= 1).all() and (t_b[decided] >= 1).all()


def test_double_touch_precompute_no_sweep_on_flat_frame() -> None:
    frame = _build_flat_frame()
    out = _double_touch_precompute(
        frame, symbol="EURUSD", sweep_dir="up",
        a_pips=3.0, b_pips=3.0, window_A=5, window_B=5, h2=5,
    )
    assert out, "engine should still return a dict for a long-enough frame"
    decided = np.asarray(out["decided"], dtype=bool)
    gross = np.asarray(out["gross"], dtype=float)
    assert decided.sum() == 0, "a flat frame touches no barrier"
    assert np.isnan(gross).all()


def test_double_touch_precompute_empty_when_frame_too_short() -> None:
    frame = _build_flat_frame(n=110)
    out = _double_touch_precompute(
        frame, symbol="EURUSD", sweep_dir="up",
        a_pips=3.0, b_pips=3.0, window_A=5, window_B=5, h2=5,
    )
    assert out == {}
