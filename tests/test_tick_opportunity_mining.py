from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.run_tick_opportunity_mining import run


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
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
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
