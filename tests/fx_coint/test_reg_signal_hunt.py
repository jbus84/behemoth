import polars as pl
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scripts.fx_coint.reg_signal_hunt import build_freq_bars


def _synthetic_1m(start: datetime, n: int, seed: int = 0) -> pl.DataFrame:
    ts = [start + timedelta(minutes=i) for i in range(n)]
    rng = np.random.default_rng(seed)
    # random walk with tiny drift so bar-return variance is non-zero (sigma_h > 0)
    steps = 1e-5 + rng.normal(0.0, 5e-5, n)
    mid = 1.10 + np.cumsum(steps)
    return pl.DataFrame({
        "bucket": ts,
        "mid": mid,
        "bid": mid - 5e-5,
        "ask": mid + 5e-5,
        "n_ticks": np.ones(n, dtype=np.int64),
        "flow_tick": np.zeros(n),
        "flow_ofi": np.zeros(n),
    })


def test_build_freq_bars_session_and_contiguity():
    # Monday 06:00 UTC, 6 hours of 1-min bars -> spans 06,07,08,09,10,11
    df = _synthetic_1m(datetime(2025, 1, 6, 6, 0), 6 * 60)
    bars = build_freq_bars(df, "1h", session=(7, 21))
    # 06:00 bar excluded by session; 07..11 kept -> 5 bars
    assert list(bars["bucket"].dt.hour) == [7, 8, 9, 10, 11]
    # first kept bar's predecessor (07:00) follows 06:00 which was dropped only by
    # session filter, but contiguity is computed on the full freq series before filtering:
    # 08..11 are contiguous with their predecessor -> contig True; 07:00 predecessor 06:00
    # is exactly 1h earlier -> contig True too.
    assert bars["contig"].iloc[1:].all()
