from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_tick_opportunity_ml_dataset import run


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
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
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
    directional, oco, summary = run(cfg)

    assert not directional.empty
    assert not oco.empty
    assert not summary.empty
    assert {"candidate_uid", "target_gross_pips", "target_gross_pos", "split"}.issubset(directional.columns)
    assert {"candidate_uid", "barrier_pips", "target_gross_pips", "target_gross_pos"}.issubset(oco.columns)
    assert "first_touch_side" not in oco.columns
    assert "both_window_event" not in oco.columns
    assert "touch_step" not in oco.columns
