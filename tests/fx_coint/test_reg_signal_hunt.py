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


def test_build_freq_bars_overnight_gap_not_contiguous():
    # Full 24h for day 1 and day 2 so we test the overnight gap properly.
    # Day 1 (Monday 2025-01-06): 00:00-23:59 -> 24 hourly bars, but session [7,21) keeps hours 7-20 (14 bars)
    day1_start = datetime(2025, 1, 6, 0, 0)
    df_day1 = _synthetic_1m(day1_start, 24 * 60, seed=0)

    # Day 2 (Tuesday 2025-01-07): 00:00-23:59 -> 24 hourly bars, but session [7,21) keeps hours 7-20 (14 bars)
    day2_start = datetime(2025, 1, 7, 0, 0)
    df_day2 = _synthetic_1m(day2_start, 24 * 60, seed=1)

    df_combined = pl.concat([df_day1, df_day2])
    bars = build_freq_bars(df_combined, "1h", session=(7, 21))

    # Should have 28 bars total: 14 from day1 (07-20), 14 from day2 (07-20)
    assert len(bars) == 28

    # Verify day1 ends at 20:00 and day2 starts at 07:00
    assert bars.iloc[13]["bucket"].hour == 20  # Last bar of day1
    assert bars.iloc[14]["bucket"].hour == 7   # First bar of day2

    # Within day1 (indices 1-13), consecutive bars are contiguous
    assert bars["contig"].iloc[1:14].all()

    # Day1's first bar (index 0) is not contiguous (no prior bar in filtered frame)
    assert not bars.loc[0, "contig"]

    # BUG CHECK: Day2's first bar (index 14) MUST be marked not contiguous.
    # Its true predecessor in the filtered frame is day1's 20:00 bar (index 13),
    # which is 11 hours earlier, NOT 1 hour. The bug is that the code computes
    # contig on the unfiltered series where day2's 07:00 follows day2's 06:00 (1h apart).
    # After filtering out 06:00, the label is stale.
    assert not bars.loc[14, "contig"], "Day2's first bar (07:00) should NOT be contiguous; its true predecessor is 11h earlier (day1's 20:00)"

    # Within day2 (indices 15-27), consecutive bars are contiguous
    assert bars["contig"].iloc[15:28].all()
