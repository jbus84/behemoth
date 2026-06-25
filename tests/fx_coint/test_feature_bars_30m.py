from datetime import datetime

import polars as pl

from scripts.fx_coint.feature_bars_30m import aggregate_30m


def test_aggregate_30m_rolls_up_one_bucket():
    flow_1m = pl.DataFrame(
        {
            "bucket": [datetime(2020, 1, 1, 0, m) for m in (0, 1, 2)],
            "mid": [1.0000, 1.0010, 1.0005],
            "bid": [0.9999, 1.0009, 1.0004],
            "ask": [1.0001, 1.0011, 1.0006],
            "flow_tick": [0.5, 1.0, -1.0],
            "flow_ofi": [0.2, 0.4, -0.2],
            "n_ticks": [10, 20, 30],
        }
    )
    out = aggregate_30m(flow_1m)
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["mid"] == 1.0005
    assert row["n_ticks"] == 60
    assert abs(row["flow_ofi"] - (0.2 + 0.4 - 0.2) / 3) < 1e-12
    assert row["rvol_bps"] > 0
    assert row["spread_bps"] > 0
