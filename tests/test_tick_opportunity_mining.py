from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from behemoth.core.features import _extract_core_series
from scripts.analyze_oco_stop_limit_tickfill import _rebuild_touch_events
from scripts.run_tick_opportunity_mining import _oco_candidates, _oco_precompute_candidates, run


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
            "candidate_uid": [f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_clean_k2"],
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
            "candidate_uid": [f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_clean_k2"],
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
    assert events.loc[0, "candidate_uid"] == f"oco|{symbol}|{bar_ticks}|h3|oco_first_touch_clean_k2"


def _build_oco_semantics_frame(
    *,
    rows: int = 140,
    trigger_gap: float = 0.00025,
    step: float = 0.00025,
) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=rows, freq="30min", tz="UTC")
    close_bid = 1.1000 + np.arange(rows) * step
    close_ask = close_bid + 0.0001
    high_bid = close_bid + 0.00005
    high_ask = close_ask + trigger_gap
    low_bid = close_bid - 0.00005
    return pd.DataFrame(
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
    frame = _build_oco_semantics_frame(trigger_gap=0.00025)

    out = _oco_candidates(
        train=frame,
        test=frame,
        symbol="EURUSD",
        bar_ticks=100,
        horizons=[1],
        barrier_grid_pips=[2.0],
        min_annual_fills=50.0,
        gross_metric="mean",
    )

    row = out.loc[out["state_id"] == "oco_first_touch_clean__all__k2"].iloc[0]
    assert row["test_count"] > 100
    assert row["p_up_first"] == pytest.approx(1.0)
    assert row["mean_gross_pips_test"] == pytest.approx(1.5)
