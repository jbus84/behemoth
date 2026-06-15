"""USD-factor residual mean-reversion probe — 2-factor PCA + band filter + Pepperstone Razor.

Corrects prior versions:
1. 2-factor PCA (rolling, causal) — not single EW.
2. Band-filtered: only trade |residual| in 6–12 bps sweet spot.
3. Pepperstone Razor cost (raw spread + commission).
4. Liquid hours only (7–16 UTC).
5. Tests both 15m and 30m bars.
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

# Pepperstone Razor: round-trip bps per pair in liquid hours
PEPPERSTONE_COST_BPS: dict[str, float] = {
    "EURUSD": 0.40,
    "GBPUSD": 0.50,
    "AUDUSD": 0.55,
    "USDJPY": 0.45,
    "USDCHF": 0.55,
    "USDCAD": 0.55,
}

LIQUID_HOURS = list(range(7, 17))
PCA_WINDOW_BARS = 480  # 5 days at 15m, 2.5 days at 30m — same wall-clock

# Dislocation bands in bps
BANDS = [(0, 6), (6, 12), (12, 20), (20, 999)]


def bar_mid(sym: str, freq: str) -> pl.DataFrame:
    """Resample tick bars to {freq} mid close."""
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
    """Rolling 2-factor PCA residual (look-ahead free)."""
    T, n_pairs = R.shape
    residuals = np.zeros_like(R)

    for t in range(T):
        start = max(0, t - window)
        window_data = R[start:t]
        if len(window_data) < max(20, n_pairs * 3):
            # Expanding fallback — last-bar EW factor
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

        # Reconstruct expected standardized return
        expected_std = Vt[0] * pc1_t + Vt[1] * pc2_t
        expected = expected_std * std_w + mean_w
        residuals[t] = R[t] - expected

    return residuals


def run_probe(freq: str) -> None:
    print(f"\n{'='*60}")
    print(f"  FREQUENCY: {freq}")
    print(f"{'='*60}")

    frames = [bar_mid(s, freq) for s in PAIRS]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bar_time", how="inner")
    df = df.drop_nulls().sort("bar_time")
    print(f"  bars: {df.height}  span: {df['bar_time'][0]} -> {df['bar_time'][-1]}")

    syms = list(PAIRS)
    n_pairs = len(syms)

    # Oriented USD-strength log returns
    rets = {}
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        dlog = np.diff(np.log(mid))
        rets[s] = PAIRS[s] * dlog
    R = np.column_stack([rets[s] for s in syms])
    bar_times = df["bar_time"].to_numpy()[1:]

    # 2-factor PCA
    R_res = rolling_pca_2factor(R, PCA_WINDOW_BARS)

    # Align
    res = R_res[:-1]
    fwd = R[1:]
    hrs = bar_times[1:]
    hours = np.array([int(str(bt)[11:13]) for bt in hrs])
    liquid_mask = np.isin(hours, LIQUID_HOURS)
    print(f"  liquid hours: {liquid_mask.sum()} / {len(liquid_mask)} ({liquid_mask.mean()*100:.1f}%)")

    cost_bps_arr = np.array([PEPPERSTONE_COST_BPS[s] for s in syms])
    cost_rel = cost_bps_arr / 1e4

    # Signal and capture
    sig = -np.sign(res)
    cap = sig * fwd
    net = cap - cost_rel[None, :]

    # Per-band, per-pair
    absbps = np.abs(res) * 1e4

    print("\n  === PER-PAIR BY DISLOCATION BAND (liquid hours) ===")
    for lo, hi in BANDS:
        band_mask = (absbps >= lo) & (absbps < hi) & liquid_mask[:, None]
        print(f"\n  --- Band |res| = {lo}-{hi} bps ---")
        print("    pair       gross(bps)  net(bps)   win%     n       t")
        for i, s in enumerate(syms):
            m = band_mask[:, i]
            if m.sum() < 50:
                print(f"    {s:<10}  (too few obs: {m.sum()})")
                continue
            cap_i = cap[m, i] * 1e4
            net_i = net[m, i] * 1e4
            n = len(cap_i)
            t = net_i.mean() / (net_i.std() + 1e-12) * np.sqrt(n)
            print(f"    {s:<10}  {cap_i.mean():+.3f}      {net_i.mean():+.3f}   {(cap_i>0).mean()*100:5.1f}  {n:>6}  {t:+5.1f}")

    # Portfolio: Tight-3 (EUR, GBP, JPY), 6-12 bps band
    print("\n  === PORTFOLIO: Tight-3 (EURUSD/GBPUSD/USDJPY), 6-12 bps band ===")
    tight_idx = [syms.index(s) for s in ("EURUSD", "GBPUSD", "USDJPY")]
    band_6_12 = (absbps >= 6) & (absbps < 12) & liquid_mask[:, None]
    w3 = np.zeros((len(liquid_mask), n_pairs))
    w3[:, tight_idx] = 1.0 / 3.0

    # Only trade when at least one tight-3 pair is in band
    active = band_6_12[:, tight_idx].any(axis=1)
    cap_t3 = (cap[active] * w3[active]).sum(axis=1) * 1e4
    net_t3 = (net[active] * w3[active]).sum(axis=1) * 1e4
    if len(net_t3) > 0:
        t_t3 = net_t3.mean() / (net_t3.std() + 1e-12) * np.sqrt(len(net_t3))
        print(f"    active bars: {active.sum()} / {len(active)} ({active.mean()*100:.1f}%)")
        print(f"    gross={cap_t3.mean():+.3f}bps  net={net_t3.mean():+.3f}bps  win%={(cap_t3>0).mean()*100:.1f}  t={t_t3:+.1f}")
    else:
        print("    (no active bars)")

    # ---- Variance explained (last window) ----
    if len(R) >= PCA_WINDOW_BARS:
        X = (R[-PCA_WINDOW_BARS:] - R[-PCA_WINDOW_BARS:].mean(axis=0)) / (R[-PCA_WINDOW_BARS:].std(axis=0) + 1e-12)
        _, S, _ = np.linalg.svd(X, full_matrices=False)
        var_expl = S**2 / (S**2).sum()
        print(f"\n  PCA var-expl: PC1={var_expl[0]*100:.1f}% PC2={var_expl[1]*100:.1f}% PC3={var_expl[2]*100:.1f}%")


def main() -> None:
    for freq in ("15m", "30m"):
        run_probe(freq)


if __name__ == "__main__":
    main()
