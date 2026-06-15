"""Hourly USD-factor residual mean-reversion probe — 2-factor PCA + Pepperstone Razor.

Corrects the original probe in four ways:
1. 2-factor PCA (not single EW factor) — captures PC2 (risk-on/risk-off axis).
2. Pepperstone Razor cost model (raw spread + commission) — not retail spread-betting.
3. Liquid hours only (7–16 UTC) — where spreads are tightest and edge concentrates.
4. Per-pair independent fades — not forced dollar-neutral turnover.
"""

from __future__ import annotations

import numpy as np
import polars as pl

PAIRS: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCHF": +1.0,
    "USDCAD": +1.0,
}
TICK = "1000tick"
BAR_FREQ = "15m"  # 15m or 30m — edge found at 15–30m

# Pepperstone Razor cost: round-trip bps per pair in liquid hours
# (raw spread + commission converted to bps of price)
PEPPERSTONE_COST_BPS: dict[str, float] = {
    "EURUSD": 0.40,
    "GBPUSD": 0.50,
    "AUDUSD": 0.55,
    "USDJPY": 0.45,
    "USDCHF": 0.55,
    "USDCAD": 0.55,
}

LIQUID_HOURS = list(range(7, 17))  # 7–16 UTC inclusive

# Rolling PCA window (number of bars).  At 15m: 96 bars = 1 day.
# Using 5 days (480 bars) for stability.
PCA_WINDOW_BARS = 480


def bar_mid(sym: str, freq: str = BAR_FREQ) -> pl.DataFrame:
    """Resample 1000tick bars to {freq} mid close with measured spread."""
    df = pl.read_parquet(f"data/tick_bars/{sym}_{TICK}.parquet")
    df = df.with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        ((pl.col("close_ask") - pl.col("close_bid")) / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("rel_spread"),
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
    """Rolling 2-factor PCA residual (look-ahead free).

    For each bar t, estimates 2-factor model from past `window` bars,
    subtracts predicted return from actual, returns residual.
    """
    T, n_pairs = R.shape
    residuals = np.zeros_like(R)

    for t in range(T):
        start = max(0, t - window)
        window_data = R[start:t]  # causal: strictly before t
        if len(window_data) < max(20, n_pairs * 3):
            # Expanding window fallback — single equal-weight factor
            ew = window_data.mean(axis=1).mean() if len(window_data) > 0 else 0.0
            residuals[t] = R[t] - ew
            continue

        # Standardize within window
        mean_w = window_data.mean(axis=0)
        std_w = window_data.std(axis=0) + 1e-12
        X = (window_data - mean_w) / std_w

        # PCA via SVD on standardized returns
        _, _, Vt = np.linalg.svd(X, full_matrices=False)

        # Current bar in standardized space
        curr_std = (R[t] - mean_w) / std_w

        # Project current bar onto first 2 PCs
        pc1_t = curr_std @ Vt[0]
        pc2_t = curr_std @ Vt[1]

        # Reconstruct expected return for each pair:
        # expected_std_i = loading_PC1_i * pc1_t + loading_PC2_i * pc2_t
        expected_std = Vt[0] * pc1_t + Vt[1] * pc2_t

        # Denormalize to original return scale
        expected = expected_std * std_w + mean_w
        residuals[t] = R[t] - expected

    return residuals


def main() -> None:
    # Load and resample
    frames = [bar_mid(s) for s in PAIRS]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bar_time", how="inner")
    df = df.drop_nulls().sort("bar_time")
    print(f"aligned {BAR_FREQ} bars: {df.height}  span: {df['bar_time'][0]} -> {df['bar_time'][-1]}")

    syms = list(PAIRS)
    n_pairs = len(syms)

    # Oriented USD-strength log returns
    rets = {}
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        dlog = np.diff(np.log(mid))
        rets[s] = PAIRS[s] * dlog
    R = np.column_stack([rets[s] for s in syms])  # (T-1, 6)
    bar_times = df["bar_time"].to_numpy()[1:]

    # ---- 2-factor PCA (rolling, causal) ----
    R_res = rolling_pca_2factor(R, PCA_WINDOW_BARS)

    # Align to entry bars (drop last bar for forward return)
    res = R_res[:-1]       # dislocation at t
    fwd = R[1:]            # next bar return
    hrs = bar_times[1:]

    # Liquid hours mask aligned to fwd/res
    hours = np.array([int(str(bt)[11:13]) for bt in hrs])
    liquid_mask = np.isin(hours, LIQUID_HOURS)
    print(f"liquid hours (7-16 UTC): {liquid_mask.sum()} / {len(liquid_mask)} bars ({liquid_mask.mean()*100:.1f}%)")

    # Cost model: Pepperstone Razor (fixed per-pair RT cost in bps)
    cost_bps_arr = np.array([PEPPERSTONE_COST_BPS[s] for s in syms])

    # ---- Per-pair fade: sign(residual) -> fade ----
    sig = -np.sign(res)    # fade direction: opposite to residual
    cap = sig * fwd        # gross capture (oriented)

    # Net: gross - cost (cost applies when we enter)
    # Cost is in bps, cap is in relative terms
    cost_rel = cost_bps_arr / 1e4
    net = cap - cost_rel[None, :]  # subtract cost for each pair

    print("\n=== PER-PAIR FADE (2-factor residual, liquid hours only) ===")
    print("  pair       gross(bps)  net(bps)   win%    n     t-stat")
    for i, s in enumerate(syms):
        cap_i = cap[liquid_mask, i] * 1e4
        net_i = net[liquid_mask, i] * 1e4
        n = len(cap_i)
        cap_i.mean() / (cap_i.std() + 1e-12) * np.sqrt(n)
        t_net = net_i.mean() / (net_i.std() + 1e-12) * np.sqrt(n)
        print(f"  {s:<10}  {cap_i.mean():+.3f}      {net_i.mean():+.3f}   {(cap_i>0).mean()*100:5.1f}  {n:>6}  {t_net:+5.1f}")

    # ---- Portfolio: equal-weight all 6 pairs ----
    w = np.ones((liquid_mask.sum(), n_pairs)) / n_pairs
    cap_port = (cap[liquid_mask] * w).sum(axis=1) * 1e4
    net_port = (net[liquid_mask] * w).sum(axis=1) * 1e4
    n_port = len(cap_port)
    t_net_port = net_port.mean() / (net_port.std() + 1e-12) * np.sqrt(n_port)
    print(f"\n[Portfolio EW-6]  gross={cap_port.mean():+.3f}bps  net={net_port.mean():+.3f}bps  win%={(cap_port>0).mean()*100:.1f}  t={t_net_port:+.1f}")

    # ---- Tight-3 portfolio (EURUSD, GBPUSD, USDJPY) ----
    tight_idx = [syms.index(s) for s in ("EURUSD", "GBPUSD", "USDJPY")]
    w3 = np.zeros((liquid_mask.sum(), n_pairs))
    w3[:, tight_idx] = 1.0 / 3.0
    cap_t3 = (cap[liquid_mask] * w3).sum(axis=1) * 1e4
    net_t3 = (net[liquid_mask] * w3).sum(axis=1) * 1e4
    t_t3 = net_t3.mean() / (net_t3.std() + 1e-12) * np.sqrt(len(net_t3))
    print(f"[Portfolio Tight-3]  gross={cap_t3.mean():+.3f}bps  net={net_t3.mean():+.3f}bps  win%={(cap_t3>0).mean()*100:.1f}  t={t_t3:+.1f}")

    # ---- Monthly positive % ----
    ym = np.array([str(h)[:7] for h in hrs[liquid_mask]])
    for label, arr in [("EW-6", net_port), ("Tight-3", net_t3)]:
        months: dict[str, list[float]] = {}
        for m, v in zip(ym, arr):
            months.setdefault(m, []).append(v)
        pos_frac = np.mean([np.sum(v) > 0 for v in months.values()])
        print(f"  {label} pos-month%: {pos_frac*100:.0f}% ({len(months)} months)")

    # ---- Year-by-year breakdown ----
    years = np.array([str(h)[:4] for h in hrs[liquid_mask]])
    print("\n=== YEAR-BY-YEAR (Tight-3 net, bps) ===")
    for y in sorted(set(years.tolist())):
        mask_y = years == y
        if mask_y.sum() < 10:
            continue
        net_y = net_t3[mask_y]
        print(f"  {y}  n={len(net_y):>5}  mean={net_y.mean():+.3f}  t={net_y.mean()/(net_y.std()+1e-12)*np.sqrt(len(net_y)):+.1f}  pos-month={np.mean([np.sum(net_y[ym[mask_y]==m])>0 for m in set(ym[mask_y])])*100:.0f}%")

    # ---- Variance explained by PC1 vs PC2 ----
    print("\n=== PCA variance explained (last window) ===")
    if len(R) >= PCA_WINDOW_BARS:
        X = (R[-PCA_WINDOW_BARS:] - R[-PCA_WINDOW_BARS:].mean(axis=0)) / (R[-PCA_WINDOW_BARS:].std(axis=0) + 1e-12)
        _, S, _ = np.linalg.svd(X, full_matrices=False)
        var_expl = S**2 / (S**2).sum()
        for i in range(min(4, len(var_expl))):
            print(f"  PC{i+1}: {var_expl[i]*100:.1f}%")


if __name__ == "__main__":
    main()
