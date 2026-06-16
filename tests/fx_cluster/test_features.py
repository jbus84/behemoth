from datetime import datetime, timedelta

import numpy as np
import polars as pl

from scripts.fx_cluster.features import build_features


def _synth_bars(seed: int) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    n = 600
    t0 = datetime(2020, 1, 1)
    mid = 1.0 + np.cumsum(rng.normal(0, 1e-4, n))
    return pl.DataFrame(
        {
            "bucket": [t0 + timedelta(hours=i) for i in range(n)],
            "mid": mid,
            "mid_high": mid + 1e-4,
            "mid_low": mid - 1e-4,
            "bid": mid - 5e-5,
            "ask": mid + 5e-5,
            "n_ticks": rng.integers(50, 200, n),
        }
    )


def test_build_features_shape_and_no_nan_tail():
    bars = {p: _synth_bars(i) for i, p in enumerate(["EURUSD", "GBPUSD", "AUDUSD"])}
    feats, names = build_features(bars)
    assert "pair" in feats.columns and "bucket" in feats.columns
    assert len(names) >= 15
    # after warmup there should be complete rows for every pair
    tail = feats.drop_nulls()
    assert set(tail["pair"].unique()) == {"EURUSD", "GBPUSD", "AUDUSD"}
    assert tail.height > 0


def test_features_are_causal():
    # mutating the FINAL bar must not change any earlier feature row
    base = {p: _synth_bars(i) for i, p in enumerate(["EURUSD", "GBPUSD", "AUDUSD"])}
    feats_a, names = build_features(base)
    bumped = {p: df.clone() for p, df in base.items()}
    df = bumped["EURUSD"]
    last = df.height - 1
    bumped["EURUSD"] = df.with_columns(
        pl.when(pl.arange(0, df.height) == last).then(pl.col("mid") * 1.05)
        .otherwise(pl.col("mid")).alias("mid")
    )
    feats_b, _ = build_features(bumped)
    a = feats_a.filter(pl.col("pair") == "EURUSD").sort("bucket").head(feats_a.height - 5)
    b = feats_b.filter(pl.col("pair") == "EURUSD").sort("bucket").head(feats_b.height - 5)
    for col in names:
        va, vb = a[col].to_numpy(), b[col].to_numpy()
        assert np.allclose(va, vb, equal_nan=True), f"look-ahead in {col}"
