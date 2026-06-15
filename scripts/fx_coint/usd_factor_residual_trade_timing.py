"""Trade timing breakdown: when do Tight-3 (EUR/GBP/JPY) 6-12 bps trades fire?

Reports:
- Hour-of-day distribution
- Day-of-week distribution
- Month-of-year seasonality
- Year-by-year activity
- Consecutive trade gaps (are trades clustered or spread out?)
"""

from __future__ import annotations

import numpy as np
import polars as pl

PAIRS: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCAD": +1.0,
}
TICK = "1000tick"
LIQUID_HOURS = list(range(7, 17))
PCA_WINDOW_BARS = 480


def bar_mid(sym: str, freq: str = "15m") -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_{TICK}.parquet")
    df = df.with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        pl.col("timestamp").dt.truncate(freq).alias("bar_time"),
    )
    g = (
        df.sort("timestamp")
        .group_by("bar_time")
        .agg(pl.col("mid").last().alias(f"mid_{sym}"))
        .sort("bar_time")
    )
    return g


def rolling_pca_2factor(R: np.ndarray, window: int) -> np.ndarray:
    T, n_pairs = R.shape
    residuals = np.zeros_like(R)
    for t in range(T):
        start = max(0, t - window)
        window_data = R[start:t]
        if len(window_data) < max(20, n_pairs * 3):
            ew = R[max(0, t - 1)].mean() if t > 0 else 0.0
            residuals[t] = R[t] - ew
            continue
        mean_w = window_data.mean(axis=0)
        std_w = window_data.std(axis=0) + 1e-12
        X = (window_data - mean_w) / std_w
        _, _, Vt = np.linalg.svd(X, full_matrices=False)
        curr_std = (R[t] - mean_w) / std_w
        pc1_t = curr_std @ Vt[0]
        pc2_t = curr_std @ Vt[1]
        expected_std = Vt[0] * pc1_t + Vt[1] * pc2_t
        expected = expected_std * std_w + mean_w
        residuals[t] = R[t] - expected
    return residuals


def main() -> None:
    frames = [bar_mid(s) for s in PAIRS]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bar_time", how="inner")
    df = df.drop_nulls().sort("bar_time")

    syms = list(PAIRS)
    rets = {}
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        dlog = np.diff(np.log(mid))
        rets[s] = PAIRS[s] * dlog
    R = np.column_stack([rets[s] for s in syms])
    bar_times = df["bar_time"].to_numpy()[1:]

    hours = np.array([int(str(bt)[11:13]) for bt in bar_times])
    dow = np.array([pd.Timestamp(bt).dayofweek for bt in bar_times])  # 0=Mon
    months = np.array([int(str(bt)[5:7]) for bt in bar_times])
    years = np.array([int(str(bt)[:4]) for bt in bar_times])
    np.array([str(bt)[:7] for bt in bar_times])

    R_res = rolling_pca_2factor(R, PCA_WINDOW_BARS)
    res = R_res[:-1]
    absb = np.abs(res) * 1e4

    tight_idx = [syms.index(s) for s in ("EURUSD", "GBPUSD", "USDJPY")]
    band = (absb[:, tight_idx] >= 6) & (absb[:, tight_idx] < 12)
    active = band.any(axis=1)

    print(f"Total bars analyzed: {len(bar_times)-1}")
    print(f"Active bars (Tight-3 in 6-12 bps): {active.sum()}")
    print(f"Activity rate: {active.mean()*100:.1f}%")

    # Hour-of-day
    print("\n=== HOUR OF DAY ===")
    print("  UTC  trades   %ofDay   gross   net    win%")
    for hh in range(24):
        m = active & (hours[:-1] == hh)
        if m.sum() < 10:
            continue
        cap = (-np.sign(res[m]) * R[1:][m])[:, tight_idx] * 1e4
        # Per-bar average across tight-3 pairs
        gross = cap.mean(axis=1).mean()
        print(f"  {hh:02d}   {m.sum():>6}  {m.sum()/(hours[:-1]==hh).sum()*100:5.1f}%   {gross:+.3f}  --     --")

    # Day-of-week
    print("\n=== DAY OF WEEK ===")
    print("  Day        trades   %ofDay")
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for d in range(5):
        m = active & (dow[:-1] == d)
        print(f"  {days[d]:<10} {m.sum():>6}  {m.sum()/(dow[:-1]==d).sum()*100:5.1f}%")

    # Month-of-year
    print("\n=== MONTH OF YEAR ===")
    print("  Month   trades   %ofMon")
    for mo in range(1, 13):
        m = active & (months[:-1] == mo)
        if (months[:-1] == mo).sum() > 0:
            print(f"  {mo:02d}      {m.sum():>6}  {m.sum()/(months[:-1]==mo).sum()*100:5.1f}%")

    # Year
    print("\n=== YEAR ===")
    print("  Year   trades   %ofYear")
    for y in sorted(set(years.tolist())):
        m = active & (years[:-1] == y)
        print(f"  {y}    {m.sum():>6}  {m.sum()/(years[:-1]==y).sum()*100:5.1f}%")

    # Consecutive gaps
    print("\n=== TRADE CLUSTERING ===")
    gaps = []
    last_i = -1
    for i, a in enumerate(active):
        if a:
            if last_i >= 0:
                gaps.append(i - last_i)
            last_i = i
    gaps = np.array(gaps)
    print(f"  Mean gap between trades: {gaps.mean():.1f} bars ({gaps.mean()*15:.0f} minutes)")
    print(f"  Median gap: {np.median(gaps):.0f} bars ({np.median(gaps)*15:.0f} minutes)")
    print(f"  Max gap: {gaps.max()} bars ({gaps.max()*15/60:.1f} hours)")
    print(f"  Trades in consecutive bars: {(gaps==1).sum()} / {len(gaps)} ({(gaps==1).mean()*100:.1f}%)")
    print(f"  Trades within 2 bars: {(gaps<=2).sum()} / {len(gaps)} ({(gaps<=2).mean()*100:.1f}%)")


if __name__ == "__main__":
    import pandas as pd
    main()
