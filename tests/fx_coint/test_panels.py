import numpy as np
import pandas as pd

from scripts.fx_coint.panels import align_panel, resample_fine


def _toy_ticks(start, n, step_s, base):
    ts = pd.date_range(start, periods=n, freq=f"{step_s}s", tz="UTC")
    bid = base + np.linspace(0, 0.001, n)
    return pd.DataFrame({
        "close_ts": ts, "close_bid": bid, "close_ask": bid + 0.0001,
        "spread": np.full(n, 0.0001),
    })


def test_resample_fine_produces_logmid_and_spread():
    df = _toy_ticks("2020-01-06 00:00:00", 600, 10, 1.10)  # 100 min of 10s ticks
    out = resample_fine(df, "5min")
    assert {"logmid", "spread"}.issubset(out.columns)
    # log of mid ~ ln(1.10) ish
    assert abs(out["logmid"].iloc[0] - np.log(1.10005)) < 1e-3
    # empty bins are dropped (no ffill): every row backed by real data
    assert out["logmid"].notna().all()


def test_resample_fine_drops_empty_bins():
    df = _toy_ticks("2020-01-06 00:00:00", 6, 10, 1.10)  # only 1 min of data
    out = resample_fine(df, "5min")
    assert len(out) == 1  # only the bins that actually had ticks survive


def test_align_panel_inner_joins_on_common_grid():
    a = resample_fine(_toy_ticks("2020-01-06 00:00:00", 600, 10, 1.10), "5min")
    b = resample_fine(_toy_ticks("2020-01-06 00:10:00", 600, 10, 1.30), "5min")  # offset
    panel = align_panel({"EURUSD": a, "GBPUSD": b})
    # only overlapping timestamps survive
    assert ("EURUSD", "logmid") in panel.columns
    assert ("GBPUSD", "spread") in panel.columns
    assert len(panel) > 0
    assert panel.index.is_monotonic_increasing
    assert panel.isna().sum().sum() == 0
