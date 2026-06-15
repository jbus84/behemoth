"""Diagnostic: why AUDUSD, USDJPY, USDCHF, USDCAD underperform in 2-factor residual fade.

Breaks down:
1. Factor loadings per pair (PC1 vs PC2 sensitivity).
2. Residual volatility after 1-factor vs 2-factor removal.
3. Cost-to-gross ratio per pair.
4. Session effects (which hours each pair works).
5. Dislocation size distribution per pair.
6. Reversion half-life per pair.
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
PEPPERSTONE_COST_BPS: dict[str, float] = {
    "EURUSD": 0.40,
    "GBPUSD": 0.50,
    "AUDUSD": 0.55,
    "USDJPY": 0.45,
    "USDCHF": 0.55,
    "USDCAD": 0.55,
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


def main() -> None:
    frames = [bar_mid(s) for s in PAIRS]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bar_time", how="inner")
    df = df.drop_nulls().sort("bar_time")

    syms = list(PAIRS)
    len(syms)

    rets = {}
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        dlog = np.diff(np.log(mid))
        rets[s] = PAIRS[s] * dlog
    R = np.column_stack([rets[s] for s in syms])
    bar_times = df["bar_time"].to_numpy()[1:]
    hours = np.array([int(str(bt)[11:13]) for bt in bar_times])
    liquid_mask = np.isin(hours, LIQUID_HOURS)

    # Standardize for PCA
    Rc = R - R.mean(axis=0)
    std_w = Rc.std(axis=0) + 1e-12
    X = Rc / std_w
    _, S, Vt = np.linalg.svd(X, full_matrices=False)
    var_expl = S**2 / (S**2).sum()

    # Factor loadings (betas of each pair on PC1/PC2)
    loadings = np.column_stack([Vt[0], Vt[1]])  # (n_pairs, 2)

    print("=== FACTOR LOADINGS (standardized returns) ===")
    print("  pair       PC1        PC2        |PC2|/|PC1|   R²(PC1+PC2)")
    for i, s in enumerate(syms):
        pc1_l = loadings[i, 0]
        pc2_l = loadings[i, 1]
        r2 = (pc1_l**2 + pc2_l**2)
        print(f"  {s:<10} {pc1_l:+.4f}    {pc2_l:+.4f}    {abs(pc2_l)/max(abs(pc1_l),1e-12):.2f}         {r2:.3f}")

    print(f"\n  Variance explained: PC1={var_expl[0]*100:.1f}%  PC2={var_expl[1]*100:.1f}%")

    # ---- 1-factor vs 2-factor residual comparison ----
    print("\n=== RESIDUAL VOLATILITY: 1-factor vs 2-factor ===")
    factor_1 = R.mean(axis=1, keepdims=True)
    res_1f = R - factor_1
    # 2-factor: project on first 2 PCs
    scores = X @ Vt[:2].T  # (T, 2)
    pred_2f = (scores @ Vt[:2]) * std_w[None, :] + R.mean(axis=0)[None, :]
    res_2f = R - pred_2f

    print("  pair       raw_vol    1f_res_vol  2f_res_vol  improvement")
    for i, s in enumerate(syms):
        raw_v = R[:, i].std()
        r1 = res_1f[:, i].std()
        r2 = res_2f[:, i].std()
        print(f"  {s:<10} {raw_v*1e4:6.3f}     {r1*1e4:6.3f}      {r2*1e4:6.3f}      {(r1-r2)/r1*100:.1f}%")

    # ---- Dislocation distribution per pair ----
    absbps_1f = np.abs(res_1f) * 1e4
    absbps_2f = np.abs(res_2f) * 1e4

    print("\n=== DISLOCATION SIZE: 1-factor vs 2-factor (liquid hours) ===")
    for i, s in enumerate(syms):
        m = liquid_mask
        q_1f = np.percentile(absbps_1f[m, i], [50, 75, 90, 95])
        q_2f = np.percentile(absbps_2f[m, i], [50, 75, 90, 95])
        print(f"\n  {s}:")
        print(f"    1f:  p50={q_1f[0]:.2f}  p75={q_1f[1]:.2f}  p90={q_1f[2]:.2f}  p95={q_1f[3]:.2f}")
        print(f"    2f:  p50={q_2f[0]:.2f}  p75={q_2f[1]:.2f}  p90={q_2f[2]:.2f}  p95={q_2f[3]:.2f}")

    # ---- Reversion by pair: 1f vs 2f in 6-12 bps band ----
    print("\n=== REVERSION TEST: 6-12 bps band, 1-factor vs 2-factor ===")
    liquid_fwd = liquid_mask[:-1]  # align to fwd bars
    for i, s in enumerate(syms):
        for label, res in [("1-factor", res_1f), ("2-factor", res_2f)]:
            res_entry = res[:-1]
            fwd = R[1:]
            absb = np.abs(res_entry) * 1e4
            band = (absb >= 6) & (absb < 12) & liquid_fwd[:, None]
            cap = (-np.sign(res_entry) * fwd)[band[:, i], i] * 1e4
            net = cap - PEPPERSTONE_COST_BPS[s]
            if len(cap) > 50:
                print(f"  {s:<10} {label:<10}  n={len(cap):>5}  gross={cap.mean():+.3f}  net={net.mean():+.3f}  win%={(cap>0).mean()*100:5.1f}  t={net.mean()/(net.std()+1e-12)*np.sqrt(len(net)):+.1f}")
            else:
                print(f"  {s:<10} {label:<10}  n={len(cap):>5}  (too few)")

    # ---- Hour-of-day breakdown for weak pairs ----
    print("\n=== HOUR-OF-DAY: 6-12 bps band reversion (2-factor) ===")
    weak_pairs = ["AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
    res_entry = res_2f[:-1]
    fwd = R[1:]
    absb = np.abs(res_entry) * 1e4
    hours_fwd = hours[:-1]  # align to forward bars
    liquid_fwd = liquid_mask[:-1]
    for s in weak_pairs:
        i = syms.index(s)
        print(f"\n  {s}:")
        print("    UTC    gross      net        win%     n")
        for hh in range(24):
            m = (absb[:, i] >= 6) & (absb[:, i] < 12) & (hours_fwd == hh) & liquid_fwd
            if m.sum() < 20:
                continue
            cap_h = (-np.sign(res_entry[m, i]) * fwd[m, i]) * 1e4
            net_h = cap_h - PEPPERSTONE_COST_BPS[s]
            print(f"    {hh:02d}    {cap_h.mean():+.3f}    {net_h.mean():+.3f}   {(cap_h>0).mean()*100:5.1f}   {len(cap_h):>4}")

    # ---- Correlation with factor regime: does PC2 regime matter? ----
    print("\n=== PC2 REGIME EFFECT on weak pairs ===")
    pc2_ts = scores[:, 1]
    pc2_z = (pc2_ts - pc2_ts.mean()) / pc2_ts.std()
    for s in weak_pairs:
        i = syms.index(s)
        # High PC2 vs low PC2
        hi_pc2 = pc2_z > 1.0
        lo_pc2 = pc2_z < -1.0
        for label, mask in [("PC2>+1σ", hi_pc2), ("PC2<-1σ", lo_pc2)]:
            res_e = res_2f[:-1]
            fwd_m = R[1:]
            m = (np.abs(res_e[:, i]) * 1e4 >= 6) & (np.abs(res_e[:, i]) * 1e4 < 12) & mask[:-1] & liquid_fwd
            if m.sum() < 30:
                print(f"  {s:<10} {label:<10}  n={m.sum():>4}  (too few)")
                continue
            cap_m = (-np.sign(res_e[m, i]) * fwd_m[m, i]) * 1e4
            net_m = cap_m - PEPPERSTONE_COST_BPS[s]
            print(f"  {s:<10} {label:<10}  n={m.sum():>5}  gross={cap_m.mean():+.3f}  net={net_m.mean():+.3f}  win%={(cap_m>0).mean()*100:5.1f}")


if __name__ == "__main__":
    main()
