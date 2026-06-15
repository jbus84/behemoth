"""Correlation analysis: 15m vs 30m USD-factor residual signals.

Answers:
1. How correlated are 15m and 30m residuals?
2. How often do both signals fire simultaneously?
3. What is the correlation of strategy returns (15m vs 30m)?
4. Does running both together improve Sharpe, or just scale variance?
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
LIQUID_HOURS = list(range(7, 17))
PCA_WINDOW_BARS = 480

# Pepperstone Razor cost (bps RT)
PEPPERSTONE_COST_BPS: dict[str, float] = {
    "EURUSD": 0.40,
    "GBPUSD": 0.50,
    "AUDUSD": 0.55,
    "USDJPY": 0.45,
    "USDCHF": 0.55,
    "USDCAD": 0.55,
}


def bar_mid(sym: str, freq: str) -> pl.DataFrame:
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


def compute_signals(freq: str) -> dict:
    """Compute signals and returns for a given frequency."""
    frames = [bar_mid(s, freq) for s in PAIRS]
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

    # 2-factor PCA
    R_res = rolling_pca_2factor(R, PCA_WINDOW_BARS)

    # Align: entry at t, capture at t+1
    res = R_res[:-1]
    fwd = R[1:]
    times = bar_times[1:]

    # Liquid hours (aligned to signal bars)
    hours = np.array([int(str(bt)[11:13]) for bt in times])
    liquid_mask = np.isin(hours, LIQUID_HOURS)

    # Signal: fade residual
    sig = -np.sign(res)
    cap = sig * fwd
    cost_bps_arr = np.array([PEPPERSTONE_COST_BPS[s] for s in syms])
    net = cap - cost_bps_arr[None, :] / 1e4

    # Band: 6-12 bps
    absbps = np.abs(res) * 1e4
    band_mask = (absbps >= 6) & (absbps < 12)

    return {
        "times": times,
        "liquid": liquid_mask,
        "residuals": res,
        "signals": sig,
        "capture": cap,
        "net": net,
        "band_mask": band_mask,
        "absbps": absbps,
    }


def align_to_15m(t15: np.ndarray, t30: np.ndarray, vals30: np.ndarray, default=np.nan):
    """Map 30m values to 15m timestamps."""
    out = np.full(len(t15), default)
    idx = 0
    for i, t in enumerate(t15):
        while idx < len(t30) and t30[idx] < t:
            idx += 1
        if idx < len(t30) and t30[idx] == t:
            out[i] = vals30[idx]
        elif idx > 0:
            # Map to previous 30m bar (the 30m bar that contains this 15m bar)
            out[i] = vals30[idx - 1]
    return out


def main() -> None:
    print("Computing 15m signals...")
    s15 = compute_signals("15m")
    print("Computing 30m signals...")
    s30 = compute_signals("30m")

    # Align 30m to 15m timestamps
    t15 = s15["times"]
    t30 = s30["times"]

    print(f"\n15m bars: {len(t15)}  30m bars: {len(t30)}")

    # For each pair, align 30m residuals and signals to 15m
    syms = list(PAIRS)
    n_pairs = len(syms)

    # Correlation of residuals (15m vs aligned 30m)
    print("\n=== Residual correlation: 15m vs 30m (liquid hours) ===")
    print("  pair       corr      n")
    for i, s in enumerate(syms):
        res30_aligned = align_to_15m(t15, t30, s30["residuals"][:, i])
        mask = s15["liquid"] & np.isfinite(res30_aligned)
        if mask.sum() > 100:
            corr = np.corrcoef(s15["residuals"][mask, i], res30_aligned[mask])[0, 1]
            print(f"  {s:<10}  {corr:+.3f}  {mask.sum()}")

    # Correlation of strategy returns (15m vs 30m, when both are in band)
    print("\n=== Strategy return correlation: 15m vs 30m (both in 6-12 bps band) ===")
    print("  pair       corr      n")
    for i, s in enumerate(syms):
        cap30_aligned = align_to_15m(t15, t30, s30["capture"][:, i])
        net30_aligned = align_to_15m(t15, t30, s30["net"][:, i])
        band30_aligned = align_to_15m(t15, t30, s30["band_mask"][:, i].astype(float), default=0)

        # Both in band and liquid
        both_band = s15["band_mask"][:, i] & (band30_aligned > 0.5) & s15["liquid"]
        if both_band.sum() > 30:
            corr_cap = np.corrcoef(s15["capture"][both_band, i], cap30_aligned[both_band])[0, 1]
            corr_net = np.corrcoef(s15["net"][both_band, i], net30_aligned[both_band])[0, 1]
            print(f"  {s:<10}  cap={corr_cap:+.3f}  net={corr_net:+.3f}  n={both_band.sum()}")
        else:
            print(f"  {s:<10}  (too few overlapping trades: {both_band.sum()})")

    # Overlap: how often does 30m signal fire within the same 30m window as 15m?
    print("\n=== Trade overlap: 15m vs 30m ===")
    for i, s in enumerate(syms):
        # 15m trades in band
        m15 = s15["band_mask"][:, i] & s15["liquid"]
        # 30m trades in band, aligned to 15m
        band30_aligned = align_to_15m(t15, t30, s30["band_mask"][:, i].astype(float), default=0)
        m30 = band30_aligned > 0.5

        # Overlap: both in band at same aligned time
        both = m15 & m30
        if m15.sum() > 0 and m30.sum() > 0:
            overlap_pct = both.sum() / m15.sum() * 100
            overlap_pct30 = both.sum() / m30.sum() * 100
            print(f"  {s:<10}  15m trades: {m15.sum():>6}  30m trades: {m30.sum():>6}  overlap: {both.sum():>6} ({overlap_pct:.1f}% of 15m, {overlap_pct30:.1f}% of 30m)")

    # Portfolio-level: Tight-3, equal-weight
    print("\n=== Portfolio Tight-3: correlation of returns ===")
    tight_idx = [syms.index(s) for s in ("EURUSD", "GBPUSD", "USDJPY")]
    w = np.zeros((len(t15), n_pairs))
    w[:, tight_idx] = 1.0 / 3.0

    # 15m portfolio returns (in band)
    active15 = s15["band_mask"][:, tight_idx].any(axis=1) & s15["liquid"]
    ret15 = (s15["net"][active15] * w[active15]).sum(axis=1) * 1e4

    # 30m portfolio returns (aligned)
    band30_tight = np.zeros((len(t30), n_pairs))
    for i in tight_idx:
        band30_tight[:, i] = s30["band_mask"][:, i]
    active30 = band30_tight[:, tight_idx].any(axis=1) & s30["liquid"]
    ret30_raw = (s30["net"][active30] * (1.0/3.0)).sum(axis=1) * 1e4

    # Build full-length 30m return array (NaN where inactive)
    ret30_full = np.full(len(t30), np.nan)
    ret30_full[active30] = ret30_raw

    # Align 30m returns to 15m for correlation
    ret30_aligned = align_to_15m(t15, t30, ret30_full, default=np.nan)
    common_mask = active15 & np.isfinite(ret30_aligned)

    if common_mask.sum() > 30:
        corr_port = np.corrcoef(ret15[common_mask[active15]], ret30_aligned[common_mask])[0, 1]
        print(f"  Correlation of Tight-3 returns (15m vs 30m aligned): {corr_port:+.3f}")
        print(f"  Common active bars: {common_mask.sum()}")
    else:
        print(f"  (too few overlapping bars: {common_mask.sum()})")

    # Combined: 15m + 30m portfolio
    print("\n=== Combined strategy: 15m + 30m Tight-3 ===")
    combined_ret = np.full(len(t15), np.nan)
    # 15m signal takes priority
    combined_ret[active15] = ret15
    # 30m fills gaps where 15m not active but 30m is
    band30_tight_15m = np.zeros((len(t15), n_pairs))
    for i in tight_idx:
        band30_tight_15m[:, i] = align_to_15m(t15, t30, s30["band_mask"][:, i].astype(float), default=0)
    active30_aligned = band30_tight_15m[:, tight_idx].any(axis=1) & s15["liquid"]
    gap = active30_aligned & ~active15
    ret30_gap = align_to_15m(t15, t30, ret30_full, default=np.nan)
    combined_ret[gap] = ret30_gap[gap]

    valid = np.isfinite(combined_ret)
    if valid.sum() > 10:
        r = combined_ret[valid]
        t = r.mean() / (r.std() + 1e-12) * np.sqrt(len(r))
        print(f"  Combined bars: {len(r)}  mean={r.mean():+.3f}bps  t={t:+.1f}  win%={(r>0).mean()*100:.1f}")
    else:
        print("  (no combined trades)")


if __name__ == "__main__":
    main()
