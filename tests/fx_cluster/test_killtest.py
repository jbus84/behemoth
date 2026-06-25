from datetime import datetime, timedelta

import numpy as np
import polars as pl

from scripts.fx_cluster.killtest import add_block_index, assemble_points


def _bars(seed):
    rng = np.random.default_rng(seed)
    n = 400
    t0 = datetime(2020, 1, 1)
    mid = 1.0 + np.cumsum(rng.normal(0, 1e-4, n))
    return pl.DataFrame({
        "bucket": [t0 + timedelta(hours=i) for i in range(n)],
        "mid": mid, "mid_high": mid + 1e-4, "mid_low": mid - 1e-4,
        "bid": mid - 5e-5, "ask": mid + 5e-5, "n_ticks": np.full(n, 100),
    })


def test_assemble_points_joins_features_and_labels():
    bars = {p: _bars(i) for i, p in enumerate(["EURUSD", "GBPUSD", "AUDUSD"])}
    pts = assemble_points(bars)
    assert {"pair", "bucket", "ret_long", "ret_short"}.issubset(pts.columns)
    assert pts.height > 0


def test_add_block_index_is_stable_and_integer():
    df = pl.DataFrame({"bucket": [datetime(2020, 1, 1) + timedelta(days=d) for d in range(20)]})
    out = add_block_index(df, block_days=5)
    assert out["block"].dtype == pl.Int64 or out["block"].dtype == pl.Int32
    assert out["block"].n_unique() == 4
