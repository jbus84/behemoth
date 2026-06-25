from datetime import datetime

import polars as pl

from scripts.fx_cluster.bars import aggregate_bars


def _ticks():
    # Two hourly buckets; second bucket has a high spike and a low dip between open/close.
    return pl.DataFrame(
        {
            "timestamp": [
                datetime(2020, 1, 1, 0, 5),
                datetime(2020, 1, 1, 0, 55),
                datetime(2020, 1, 1, 1, 1),   # bucket 1 open
                datetime(2020, 1, 1, 1, 20),  # high
                datetime(2020, 1, 1, 1, 40),  # low
                datetime(2020, 1, 1, 1, 59),  # close
            ],
            "bid": [1.0000, 1.0010, 1.0020, 1.0090, 0.9950, 1.0030],
            "ask": [1.0002, 1.0012, 1.0022, 1.0092, 0.9952, 1.0032],
            "mid": [1.0001, 1.0011, 1.0021, 1.0091, 0.9951, 1.0031],
        }
    )


def test_aggregate_bars_uses_last_tick_per_bucket():
    out = aggregate_bars(_ticks(), "1h").sort("bucket")
    assert out.height == 2
    row0 = out.row(0, named=True)
    # last tick of bucket 0 is the 00:55 tick
    assert row0["mid"] == 1.0011
    assert row0["bid"] == 1.0010
    assert row0["ask"] == 1.0012
    assert row0["bucket"] == datetime(2020, 1, 1, 0, 0)


def test_aggregate_bars_captures_intrabar_high_low():
    out = aggregate_bars(_ticks(), "1h").sort("bucket")
    row1 = out.row(1, named=True)
    assert row1["mid"] == 1.0031          # close = last tick
    assert row1["mid_high"] == 1.0091     # the 01:20 spike
    assert row1["mid_low"] == 0.9951      # the 01:40 dip
    assert row1["n_ticks"] == 4
