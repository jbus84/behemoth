"""Test: does inverting USDCHF -> CHFUSD help?

USDCHF quote convention: USD per CHF.
CHFUSD quote convention: CHF per USD = 1/USDCHF.

In log terms: log(CHFUSD) = -log(USDCHF), so dlog(CHFUSD) = -dlog(USDCHF).

The oriented return for USDCHF (PAIRS["USDCHF"]=+1.0) is +dlog(USDCHF).
The oriented return for CHFUSD (PAIRS["CHFUSD"]=-1.0) is -dlog(CHFUSD).

Since dlog(CHFUSD) = -dlog(USDCHF), the oriented returns are IDENTICAL.
But let's verify the factor model actually behaves the same way.
"""

from __future__ import annotations

import numpy as np
import polars as pl

PAIRS_USD: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCHF": +1.0,  # original
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


def bar_mid(sym: str, freq: str = "15m", invert: bool = False) -> pl.DataFrame:
    """Read tick bars. If invert=True, treat as 1/price (e.g. CHFUSD from USDCHF)."""
    actual_sym = "USDCHF" if sym == "CHFUSD" else sym
    df = pl.read_parquet(f"data/tick_bars/{actual_sym}_{TICK}.parquet")
    if invert:
        # CHFUSD = 1/USDCHF
        # mid = (1/bid + 1/ask)/2 ≈ 1/mid for small spreads
        df = df.with_columns(
            (1.0 / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("mid"),
            ((pl.col("close_ask") - pl.col("close_bid"))
             / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("rel_spread"),
            pl.col("timestamp").dt.truncate(freq).alias("bar_time"),
        )
    else:
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


def run_probe(pairs: dict[str, float], label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    frames = [bar_mid(s, invert=(s == "CHFUSD")) for s in pairs]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bar_time", how="inner")
    df = df.drop_nulls().sort("bar_time")

    syms = list(pairs)
    len(syms)

    rets = {}
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        dlog = np.diff(np.log(mid))
        rets[s] = pairs[s] * dlog
    R = np.column_stack([rets[s] for s in syms])
    bar_times = df["bar_time"].to_numpy()[1:]
    hours = np.array([int(str(bt)[11:13]) for bt in bar_times])
    liquid_mask = np.isin(hours, LIQUID_HOURS)
    liquid_fwd = liquid_mask[:-1]

    R_res = rolling_pca_2factor(R, PCA_WINDOW_BARS)

    res = R_res[:-1]
    fwd = R[1:]
    absb = np.abs(res) * 1e4

    print("  pair       gross(bps)  net(bps)   win%     n       t")
    for i, s in enumerate(syms):
        cost = PEPPERSTONE_COST_BPS.get(s, 0.55)
        band = (absb[:, i] >= 6) & (absb[:, i] < 12) & liquid_fwd
        cap = (-np.sign(res[band, i]) * fwd[band, i]) * 1e4
        net = cap - cost
        if len(cap) > 50:
            t = net.mean() / (net.std() + 1e-12) * np.sqrt(len(net))
            print(f"  {s:<10} {cap.mean():+.3f}      {net.mean():+.3f}   {(cap>0).mean()*100:5.1f}  {len(cap):>6}  {t:+5.1f}")
        else:
            print(f"  {s:<10} (too few: {len(cap)})")

    # Residual correlations with EURUSD
    eur_idx = syms.index("EURUSD")
    chf_idx = syms.index("USDCHF") if "USDCHF" in syms else syms.index("CHFUSD")
    m = liquid_mask
    corr = np.corrcoef(R_res[m, chf_idx], R_res[m, eur_idx])[0, 1]
    print(f"\n  EURUSD-{syms[chf_idx]} residual corr (liquid hrs): {corr:+.3f}")

    # Factor loadings
    Rc = R - R.mean(axis=0)
    std_w = Rc.std(axis=0) + 1e-12
    X = Rc / std_w
    _, _, Vt = np.linalg.svd(X, full_matrices=False)
    print("\n  PC1/PC2 loadings:")
    for i, s in enumerate(syms):
        print(f"    {s:<10} PC1={Vt[0,i]:+.3f}  PC2={Vt[1,i]:+.3f}")


def main() -> None:
    run_probe(PAIRS_USD, "ORIGINAL: USDCHF (USD per CHF)")

    # Inverted: CHFUSD instead of USDCHF
    PAIRS_INV: dict[str, float] = {
        "EURUSD": -1.0,
        "GBPUSD": -1.0,
        "AUDUSD": -1.0,
        "USDJPY": +1.0,
        "CHFUSD": -1.0,  # inverted: CHF per USD
        "USDCAD": +1.0,
    }
    run_probe(PAIRS_INV, "INVERTED: CHFUSD (CHF per USD)")

    # Direct algebraic proof
    print(f"\n{'='*60}")
    print("  ALGEBRAIC PROOF")
    print(f"{'='*60}")
    print("  Let P = USDCHF price.")
    print("  Then CHFUSD = 1/P.")
    print("  log(CHFUSD) = log(1/P) = -log(P)")
    print("  dlog(CHFUSD) = -dlog(P)")
    print("")
    print("  Oriented return for USDCHF (PAIRS=+1):")
    print("    ret = +1 * dlog(USDCHF) = +dlog(P)")
    print("")
    print("  Oriented return for CHFUSD (PAIRS=-1):")
    print("    ret = -1 * dlog(CHFUSD) = -1 * (-dlog(P)) = +dlog(P)")
    print("")
    print("  IDENTICAL. The factor model sees the same numbers.")
    print("  Inverting the pair does NOT change the residual.")


if __name__ == "__main__":
    main()
