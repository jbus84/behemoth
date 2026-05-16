from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from behemoth.core.features import _extract_core_series
from scripts.build_tick_opportunity_ml_dataset import run
from scripts.run_tick_opportunity_mining import (
    CANDIDATE_SCHEMA_VERSION,
    QUALITY_TIER_BASIS,
    SELECTION_PASS_BASIS,
)


def _synth_tick_velocity(path: Path, *, symbol: str) -> None:
    rng = np.random.default_rng(11)
    chunks: list[pd.DataFrame] = []
    for year in [2022, 2023, 2024, 2025]:
        ts = pd.date_range(f"{year}-01-01", periods=1200, freq="15min", tz="UTC")
        step = rng.normal(0.0, 0.00004, size=len(ts))
        close = 1.10 + np.cumsum(step)
        open_ = np.r_[close[0], close[:-1]]
        # Keep ranges wide enough to trigger 2-3 pip OCO barriers often.
        high = np.maximum(open_, close) + np.abs(rng.normal(0.0003, 0.00005, size=len(ts)))
        low = np.minimum(open_, close) - np.abs(rng.normal(0.0003, 0.00005, size=len(ts)))
        d = pd.DataFrame(
            {
                "symbol": symbol,
                "bar_ticks": 1000,
                "timestamp": ts - pd.to_timedelta(15, unit="m"),
                "close_ts": ts,
                "open_bid": open_,
                "high_bid": high,
                "low_bid": low,
                "close_bid": close,
                "high_ask": high + 0.0001,
                "close_ask": close + 0.0001,
                "spread": 0.0001,
                "cost_est_pips": 0.3 + np.abs(rng.normal(0.0, 0.05, size=len(ts))),
                "range_pips": (high - low) / 0.0001,
                "hour_utc": ts.hour.astype(int),
                "spread_z": rng.normal(0.0, 1.0, size=len(ts)),
                "tick_rate_z": rng.normal(0.0, 1.0, size=len(ts)),
                "vel_cost_units_h1": rng.normal(0.0, 1.0, size=len(ts)),
                "vel_pips_h1": (close - pd.Series(close).shift(1).fillna(close[0])) / 0.0001,
                "vel_z_h1": rng.normal(0.8, 0.5, size=len(ts)),
                "hl_first": rng.choice([-1.0, 1.0], size=len(ts)),
                "hl_first_mean_24": rng.normal(0.1, 0.3, size=len(ts)),
                "hl_pos_frac_mean_24": rng.normal(0.0, 0.2, size=len(ts)),
            }
        )
        chunks.append(d)
    pd.concat(chunks, ignore_index=True).to_parquet(path, index=False)


def test_build_tick_opportunity_ml_dataset(tmp_path: Path) -> None:
    symbol = "EURUSD"
    dataset_dir = tmp_path / "tick_velocity"
    cand_dir = tmp_path / "candidates"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    cand_dir.mkdir(parents=True, exist_ok=True)

    data_path = dataset_dir / f"{symbol}_1000tick_velocity.parquet"
    _synth_tick_velocity(data_path, symbol=symbol)

    pd.DataFrame(
        [
            {
                "symbol": symbol,
                "bar_ticks": 1000,
                "horizon": 2,
                "family": "path_follow",
                "state_id": "path_follow__all",
                "regime_desc": "all",
                "annualized_test_fills": 10000.0,
                "mean_gross_pips_test": 0.15,
                "train_count": 50000,
                "mean_gross_pips_train": 0.18,
                "selection_pass": True,
                "quality_tier": "B",
                "quality_score": 2,
                "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
                "selection_pass_basis": SELECTION_PASS_BASIS,
                "quality_tier_basis": QUALITY_TIER_BASIS,
            }
        ]
    ).to_csv(cand_dir / f"{symbol}_directional_candidates.csv", index=False)

    pd.DataFrame(
        [
            {
                "symbol": symbol,
                "bar_ticks": 1000,
                "horizon": 2,
                "family": "oco_first_touch",
                "state_id": "oco_first_touch__all__k2",
                "regime_desc": "all;barrier=2.0",
                "annualized_test_fills": 10000.0,
                "mean_gross_pips_test": 0.4,
                "train_count": 52000,
                "mean_gross_pips_train": 0.45,
                "selection_pass": True,
                "quality_tier": "B",
                "quality_score": 2,
                "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
                "selection_pass_basis": SELECTION_PASS_BASIS,
                "quality_tier_basis": QUALITY_TIER_BASIS,
            }
        ]
    ).to_csv(cand_dir / f"{symbol}_oco_candidates.csv", index=False)

    cfg = {
        "symbol": symbol,
        "dataset_dir": str(dataset_dir),
        "candidate_dir": str(cand_dir),
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "selection_required": True,
        "min_quality_tier": "C",
        "max_candidates_per_library": 10,
        "max_events_per_candidate": 1000,
    }
    directional, oco, summary = run(cfg)

    assert not directional.empty
    assert not oco.empty
    assert not summary.empty
    assert {"candidate_uid", "target_gross_pips", "target_gross_pos", "split"}.issubset(
        directional.columns
    )
    assert {"candidate_uid", "barrier_pips", "target_gross_pips", "target_gross_pos"}.issubset(
        oco.columns
    )
    assert "first_touch_side" not in oco.columns
    assert "both_window_event" not in oco.columns
    assert "touch_step" not in oco.columns


def test_build_tick_opportunity_ml_dataset_rejects_stale_candidate_schema(tmp_path: Path) -> None:
    symbol = "EURUSD"
    dataset_dir = tmp_path / "tick_velocity"
    cand_dir = tmp_path / "candidates"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    cand_dir.mkdir(parents=True, exist_ok=True)
    _synth_tick_velocity(dataset_dir / f"{symbol}_1000tick_velocity.parquet", symbol=symbol)

    # Missing candidate_schema_version and train-only basis metadata.
    pd.DataFrame(
        [
            {
                "symbol": symbol,
                "bar_ticks": 1000,
                "horizon": 2,
                "family": "path_follow",
                "state_id": "path_follow__all",
                "regime_desc": "all",
                "annualized_test_fills": 10000.0,
                "mean_gross_pips_test": 0.15,
                "train_count": 50000,
                "mean_gross_pips_train": 0.18,
                "selection_pass": True,
                "quality_tier": "B",
                "quality_score": 2,
            }
        ]
    ).to_csv(cand_dir / f"{symbol}_directional_candidates.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol": symbol,
                "bar_ticks": 1000,
                "horizon": 2,
                "family": "oco_first_touch",
                "state_id": "oco_first_touch__all__k2",
                "regime_desc": "all;barrier=2.0",
                "annualized_test_fills": 10000.0,
                "mean_gross_pips_test": 0.4,
                "train_count": 52000,
                "mean_gross_pips_train": 0.45,
                "selection_pass": True,
                "quality_tier": "B",
                "quality_score": 2,
            }
        ]
    ).to_csv(cand_dir / f"{symbol}_oco_candidates.csv", index=False)

    cfg = {
        "symbol": symbol,
        "dataset_dir": str(dataset_dir),
        "candidate_dir": str(cand_dir),
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "selection_required": True,
        "min_quality_tier": "C",
        "max_candidates_per_library": 10,
        "max_events_per_candidate": 1000,
    }
    with pytest.raises(ValueError, match="candidate_schema_version"):
        run(cfg)


def test_extract_core_series_requires_explicit_bid_columns() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-01-01T00:00:00Z"]),
            "close_ts": pd.to_datetime(["2025-01-01T00:15:00Z"]),
            "open_bid": [1.0],
            "high_bid": [1.1],
            "low_bid": [0.9],
            "close_bid": [1.0],
        }
    )

    close_bid, open_bid, high_bid, low_bid, *_ = _extract_core_series(df)

    assert float(close_bid.iloc[0]) == 1.0
    assert float(open_bid.iloc[0]) == 1.0
    assert float(high_bid.iloc[0]) == 1.1
    assert float(low_bid.iloc[0]) == 0.9


def test_extract_core_series_rejects_legacy_ambiguous_columns() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-01-01T00:00:00Z"]),
            "close_ts": pd.to_datetime(["2025-01-01T00:15:00Z"]),
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.0],
        }
    )

    with pytest.raises(ValueError, match="legacy ambiguous bar schema unsupported"):
        _extract_core_series(df)


def test_ml_dataset_preserves_microstructure_columns() -> None:
    """ML parquet must include microstructure columns even though model doesn't consume them."""
    from scripts.build_tick_opportunity_ml_dataset import _build_oco_events, _feature_cols
    from scripts.run_tick_opportunity_mining import _quantiles

    n = 300
    ts = pd.date_range("2026-01-01", periods=n, freq="1min")
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "close_ts": ts,
            "close_bid": np.linspace(1.1000, 1.1050, n),
            "high_bid": np.linspace(1.1005, 1.1055, n),
            "low_bid": np.linspace(1.0995, 1.1045, n),
            "high_ask": np.linspace(1.1007, 1.1057, n),
            "close_ask": np.linspace(1.1002, 1.1052, n),
            "hl_first": [1, -1, 0] * (n // 3),
            "cost_est_pips": np.full(n, 0.3),
            "range_pips": np.full(n, 5.0),
            "hour_utc": ts.hour.astype(int),
            "spread_z": np.zeros(n),
            "tick_rate_z": np.zeros(n),
            "vel_cost_units_h1": np.zeros(n),
            "vel_abs_cost_units_h1": np.zeros(n),
            "ret1_pips": np.zeros(n),
            "ret_z": np.zeros(n),
            "ret_abs_z": np.zeros(n),
            "hl_first_mean_24": np.zeros(n),
            "hl_pos_frac_mean_24": np.zeros(n),
            "tick_burst_score": [0.0] * n,
            "quote_revision_rate_z": [0.0] * n,
            "directional_persistence_8": [0.0] * n,
            "signed_flow_24": [0.0] * n,
            "vol_cluster_score": [1.0] * n,
            "session_marker": ["london"] * n,
        }
    )

    cands = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "family": "oco_first_touch",
                "state_id": "oco_first_touch__all__k5",
                "regime_desc": "all;barrier=2.0",
                "quality_tier": "A",
                "quality_score": 3,
                "selection_pass": True,
                "annualized_test_fills": 1000.0,
                "mean_gross_pips_test": 1.5,
                "train_count": 5000,
            }
        ]
    )

    # Phase 1 constraint: microstructure columns must NOT be in canonical feature set
    for col in [
        "tick_burst_score",
        "quote_revision_rate_z",
        "directional_persistence_8",
        "signed_flow_24",
        "vol_cluster_score",
        "session_marker",
    ]:
        assert col not in _feature_cols(df)

    q_fit = _quantiles(df)
    events = _build_oco_events(
        split_name="train",
        df=df,
        q_fit=q_fit,
        cands=cands,
        max_events_per_candidate=1000,
        symbol="EURUSD",
        hold_mode="from_touch",
        include_no_touch=True,
    )
    assert "tick_burst_score" in events.columns
    assert "quote_revision_rate_z" in events.columns
    assert "directional_persistence_8" in events.columns
    assert "signed_flow_24" in events.columns
    assert "vol_cluster_score" in events.columns
    assert "session_marker" in events.columns


def test_ml_dataset_preserves_microstructure_columns_directional() -> None:
    """Directional ML events must also include microstructure columns."""
    from scripts.build_tick_opportunity_ml_dataset import _build_directional_events, _feature_cols
    from scripts.run_tick_opportunity_mining import _quantiles

    n = 300
    ts = pd.date_range("2026-01-01", periods=n, freq="1min")
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "close_ts": ts,
            "close_bid": np.linspace(1.1000, 1.1050, n),
            "high_bid": np.linspace(1.1005, 1.1055, n),
            "low_bid": np.linspace(1.0995, 1.1045, n),
            "high_ask": np.linspace(1.1007, 1.1057, n),
            "close_ask": np.linspace(1.1002, 1.1052, n),
            "hl_first": [1, -1, 0] * (n // 3),
            "cost_est_pips": np.full(n, 0.3),
            "range_pips": np.full(n, 5.0),
            "hour_utc": ts.hour.astype(int),
            "spread_z": np.zeros(n),
            "tick_rate_z": np.zeros(n),
            "vel_cost_units_h1": np.zeros(n),
            "vel_abs_cost_units_h1": np.zeros(n),
            "ret1_pips": np.zeros(n),
            "ret_z": np.zeros(n),
            "ret_abs_z": np.zeros(n),
            "hl_first_mean_24": np.zeros(n),
            "hl_pos_frac_mean_24": np.zeros(n),
            "tick_burst_score": [0.0] * n,
            "quote_revision_rate_z": [0.0] * n,
            "directional_persistence_8": [0.0] * n,
            "signed_flow_24": [0.0] * n,
            "vol_cluster_score": [1.0] * n,
            "session_marker": ["london"] * n,
            "y_fwd_pips_h5": np.zeros(n),
        }
    )

    cands = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "family": "path_follow",
                "state_id": "path_follow__all",
                "regime_desc": "all",
                "quality_tier": "A",
                "quality_score": 3,
                "selection_pass": True,
                "annualized_test_fills": 1000.0,
                "mean_gross_pips_test": 1.5,
                "train_count": 5000,
            }
        ]
    )

    # Phase 1 constraint: microstructure columns must NOT be in canonical feature set
    for col in [
        "tick_burst_score",
        "quote_revision_rate_z",
        "directional_persistence_8",
        "signed_flow_24",
        "vol_cluster_score",
        "session_marker",
    ]:
        assert col not in _feature_cols(df)

    q_fit = _quantiles(df)
    events = _build_directional_events(
        split_name="train",
        df=df,
        q_fit=q_fit,
        cands=cands,
        max_events_per_candidate=1000,
    )
    assert "tick_burst_score" in events.columns
    assert "quote_revision_rate_z" in events.columns
    assert "directional_persistence_8" in events.columns
    assert "signed_flow_24" in events.columns
    assert "vol_cluster_score" in events.columns
    assert "session_marker" in events.columns
