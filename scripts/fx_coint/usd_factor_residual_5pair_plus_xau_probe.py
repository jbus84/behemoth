"""5-pair USD-factor residual + XAUUSD trading assessment.

Drops USDCHF (structurally broken). Tests:
1. 5-pair Tight-3 + Tight-5 portfolio (EUR, GBP, AUD, JPY, CAD).
2. XAUUSD as 6th instrument — does gold have independent residual edge?
3. Pepperstone Razor cost, liquid hours, 6-12 bps band, 15m bars.

If XAUUSD data is missing, reports what is needed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

TICK = "1000tick"
LIQUID_HOURS = list(range(7, 17))
PCA_WINDOW_BARS = 480

# 5 USD majors + XAUUSD
PAIRS: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCAD": +1.0,
}

# Pepperstone Razor round-trip cost (bps)
PEPPERSTONE_COST_BPS: dict[str, float] = {
    "EURUSD": 0.40,
    "GBPUSD": 0.50,
    "AUDUSD": 0.55,
    "USDJPY": 0.45,
    "USDCAD": 0.55,
    "XAUUSD": 0.80,  # gold spread is wider
}


def bar_mid(sym: str, freq: str = "15m") -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_{TICK}.parquet")
    df = df.with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        ((pl.col("close_ask") - pl.col("close_bid"))
         / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("rel_spread"),
        pl.col("timestamp").dt.truncate(freq).alias("bar_time"),
    )
    g = (
        df.sort("timestamp")
        .group_by("bar_time")
        .agg(
            pl.col("mid").last().alias(f"mid_{sym}"),
            pl.col("rel_spread").median().alias(f"spr_{sym}"),
        )
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


def run_pair_analysis(res: np.ndarray, fwd: np.ndarray, liquid_fwd: np.ndarray,
                       syms: list[str], label: str) -> dict:
    """Run 6-12 bps band analysis per pair."""
    absb = np.abs(res) * 1e4
    results = {}
    print(f"\n=== {label} ===")
    print("  pair       gross(bps)  net(bps)   win%     n       t")
    for i, s in enumerate(syms):
        band = (absb[:, i] >= 6) & (absb[:, i] < 12) & liquid_fwd
        cap = (-np.sign(res[band, i]) * fwd[band, i]) * 1e4
        net = cap - PEPPERSTONE_COST_BPS[s]
        if len(cap) > 50:
            t = net.mean() / (net.std() + 1e-12) * np.sqrt(len(net))
            print(f"  {s:<10} {cap.mean():+.3f}      {net.mean():+.3f}   {(cap>0).mean()*100:5.1f}  {len(cap):>6}  {t:+5.1f}")
            results[s] = {"gross": cap.mean(), "net": net.mean(), "win": (cap>0).mean()*100, "n": len(cap), "t": t}
        else:
            print(f"  {s:<10} (too few: {len(cap)})")
            results[s] = None
    return results


def run_portfolio(res: np.ndarray, fwd: np.ndarray, liquid_fwd: np.ndarray,
                  syms: list[str], subset: list[str], label: str) -> None:
    """Run equal-weight portfolio: trade only pairs individually in 6-12 bps band."""
    len(syms)
    absb = np.abs(res) * 1e4
    idx = [syms.index(s) for s in subset]
    costs = np.array([PEPPERSTONE_COST_BPS[s] for s in subset]) / 1e4

    # Per-pair band mask for subset pairs only
    band = (absb[:, idx] >= 6) & (absb[:, idx] < 12) & liquid_fwd[:, None]

    # Per-bar: only trade pairs in band; equal-weight across active pairs
    ret_bars = []
    for t in range(len(liquid_fwd)):
        active_idx = [i for i, j in enumerate(idx) if band[t, i]]
        if not active_idx:
            continue
        # Equal weight across active pairs this bar
        w = 1.0 / len(active_idx)
        bar_ret = 0.0
        for i in active_idx:
            j = idx[i]
            cap = (-np.sign(res[t, j]) * fwd[t, j])
            net = cap - costs[i]
            bar_ret += net * w
        ret_bars.append(bar_ret * 1e4)

    ret = np.array(ret_bars)
    if len(ret) > 10:
        t = ret.mean() / (ret.std() + 1e-12) * np.sqrt(len(ret))
        print(f"\n[{label}]  bars={len(ret)}  net={ret.mean():+.3f}bps  win%={(ret>0).mean()*100:.1f}  t={t:+.1f}")
    else:
        print(f"\n[{label}]  (too few active bars)")


def main() -> None:
    # Load 5-pair data
    print("Loading FX data...")
    fx_frames = [bar_mid(s) for s in PAIRS]
    df = fx_frames[0]
    for f in fx_frames[1:]:
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
    liquid_mask = np.isin(hours, LIQUID_HOURS)
    liquid_fwd = liquid_mask[:-1]

    # 2-factor PCA
    R_res = rolling_pca_2factor(R, PCA_WINDOW_BARS)

    # Align
    res = R_res[:-1]
    fwd = R[1:]

    # Per-pair 5-pair analysis
    run_pair_analysis(res, fwd, liquid_fwd, syms, "5-PAIR ANALYSIS (6-12 bps band)")

    # Tight-3 portfolio
    run_portfolio(res, fwd, liquid_fwd, syms, ["EURUSD", "GBPUSD", "USDJPY"], "Tight-3 (EUR/GBP/JPY)")

    # Tight-5 portfolio
    run_portfolio(res, fwd, liquid_fwd, syms, ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD"], "Tight-5 (all)")

    # ---- XAUUSD section ----
    print(f"\n{'='*60}")
    print("  XAUUSD ASSESSMENT")
    print(f"{'='*60}")

    xau_path = Path(f"data/tick_bars/XAUUSD_{TICK}.parquet")
    if not xau_path.exists():
        print(f"\n  XAUUSD data NOT FOUND at {xau_path}")
        print("  To add XAUUSD to the assessment:")
        print("    1. Download from HistData: https://www.histdata.com/download-free-forex-historical-data/")
        print("    2. Or run: uv run python scripts/download_histdata_ticks.py --symbols XAUUSD --start-month 2018-01 --end-month 2026-05")
        print("    3. Convert to parquet in data/tick_bars/")
        print("\n  XAUUSD is expected to load on PC1 (USD strength) + PC3 (risk-off).")
        print("  It may have independent mean-reversion in the 6-12 bps residual band,")
        print("  but gold's spread (~0.8 bps RT on Pepperstone) is wider than FX majors.")
        return

    # Load XAUUSD and merge
    print("  Loading XAUUSD data...")
    xau_df = bar_mid("XAUUSD")
    df6 = df.join(xau_df, on="bar_time", how="inner")
    df6 = df6.drop_nulls().sort("bar_time")

    syms6 = syms + ["XAUUSD"]
    rets6 = rets.copy()
    mid_xau = df6["mid_XAUUSD"].to_numpy()
    dlog_xau = np.diff(np.log(mid_xau))
    # XAUUSD is USD-denominated: gold price in USD per ounce
    # USD strength means higher USD = lower XAUUSD
    # Oriented: +dlog(XAUUSD) = gold strength = USD weakness
    # Wait — in our framework, USD-strength oriented returns are:
    #   EURUSD (USD per EUR): usd_ret = -dlog(EURUSD)
    #   USDJPY (JPY per USD): usd_ret = +dlog(USDJPY)
    #   XAUUSD (USD per oz): usd_ret = -dlog(XAUUSD)  [higher gold price = weaker USD]
    rets6["XAUUSD"] = -1.0 * dlog_xau

    R6 = np.column_stack([rets6[s] for s in syms6])
    bar_times6 = df6["bar_time"].to_numpy()[1:]
    hours6 = np.array([int(str(bt)[11:13]) for bt in bar_times6])
    liquid_mask6 = np.isin(hours6, LIQUID_HOURS)
    liquid_fwd6 = liquid_mask6[:-1]

    # 2-factor PCA on 6 instruments
    R6_res = rolling_pca_2factor(R6, PCA_WINDOW_BARS)
    res6 = R6_res[:-1]
    fwd6 = R6[1:]

    run_pair_analysis(res6, fwd6, liquid_fwd6, syms6, "6-INSTRUMENT ANALYSIS (FX + XAUUSD)")

    # Tight-3 + XAU
    run_portfolio(res6, fwd6, liquid_fwd6, syms6, ["EURUSD", "GBPUSD", "USDJPY"], "Tight-3 FX")
    run_portfolio(res6, fwd6, liquid_fwd6, syms6, ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"], "Tight-3 + XAU")

    # All FX + XAU
    run_portfolio(res6, fwd6, liquid_fwd6, syms6, ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD"], "Tight-5 FX")
    run_portfolio(res6, fwd6, liquid_fwd6, syms6, ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "XAUUSD"], "Tight-5 + XAU")


if __name__ == "__main__":
    main()
