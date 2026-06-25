"""3-factor PCA probe: can removing PC3 save USDCHF?

Adds PC3 (10% variance) to the 2-factor model and tests if USDCHF residual
becomes tradeable. Also tests explicit EUR-proxy factor removal.
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


def rolling_pca_3factor(R: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Rolling 3-factor PCA residual (look-ahead free).

    Returns (residuals_2f, residuals_3f).
    """
    T, n_pairs = R.shape
    res_2f = np.zeros_like(R)
    res_3f = np.zeros_like(R)

    for t in range(T):
        start = max(0, t - window)
        window_data = R[start:t]
        if len(window_data) < max(20, n_pairs * 3):
            ew = R[max(0, t - 1)].mean() if t > 0 else 0.0
            res_2f[t] = R[t] - ew
            res_3f[t] = R[t] - ew
            continue

        mean_w = window_data.mean(axis=0)
        std_w = window_data.std(axis=0) + 1e-12
        X = (window_data - mean_w) / std_w
        _, _, Vt = np.linalg.svd(X, full_matrices=False)

        curr_std = (R[t] - mean_w) / std_w

        # 2-factor
        pc1_t = curr_std @ Vt[0]
        pc2_t = curr_std @ Vt[1]
        expected_std_2f = Vt[0] * pc1_t + Vt[1] * pc2_t
        expected_2f = expected_std_2f * std_w + mean_w
        res_2f[t] = R[t] - expected_2f

        # 3-factor
        pc3_t = curr_std @ Vt[2]
        expected_std_3f = Vt[0] * pc1_t + Vt[1] * pc2_t + Vt[2] * pc3_t
        expected_3f = expected_std_3f * std_w + mean_w
        res_3f[t] = R[t] - expected_3f

    return res_2f, res_3f


def explicit_eur_proxy_residual(R: np.ndarray, syms: list[str]) -> np.ndarray:
    """Explicit 3-factor: USD + EUR-proxy + PC3.

    Factor 1: USD strength = mean of USDJPY, USDCAD, AUDUSD (non-European)
    Factor 2: EUR proxy = EURUSD residual after removing USD factor
    Factor 3: PC3 from all 6 (commodity / risk)

    Then residual_i = R_i - beta1*F1 - beta2*F2 - beta3*F3
    """
    T, n_pairs = R.shape
    eur_idx = syms.index("EURUSD")
    syms.index("GBPUSD")
    non_eur_idx = [syms.index(s) for s in ["USDJPY", "USDCAD", "AUDUSD"]]
    syms.index("USDCHF")

    residuals = np.zeros_like(R)

    for t in range(T):
        start = max(0, t - PCA_WINDOW_BARS)
        window_data = R[start:t]
        if len(window_data) < 50:
            residuals[t] = R[t] - R[t].mean()
            continue

        # Factor 1: USD strength (non-European pairs)
        f1 = window_data[:, non_eur_idx].mean(axis=1)

        # Factor 2: EUR proxy = EURUSD minus its USD beta*F1
        # Regress EURUSD on F1
        beta_eur_usd = np.cov(window_data[:, eur_idx], f1)[0, 1] / np.var(f1)
        f2 = window_data[:, eur_idx] - beta_eur_usd * f1

        # Factor 3: PC3 from standardized all-6
        mean_w = window_data.mean(axis=0)
        std_w = window_data.std(axis=0) + 1e-12
        X = (window_data - mean_w) / std_w
        _, _, Vt = np.linalg.svd(X, full_matrices=False)
        scores = X @ Vt.T
        f3 = scores[:, 2]  # PC3

        # Current bar
        curr_f1 = R[t, non_eur_idx].mean()
        curr_f2 = R[t, eur_idx] - beta_eur_usd * curr_f1
        # Need to project current bar onto PC3
        curr_std = (R[t] - mean_w) / std_w
        curr_f3 = curr_std @ Vt[2]

        # Regress each pair on [F1, F2, F3] in window
        F = np.column_stack([f1, f2, f3])
        for i in range(n_pairs):
            beta = np.linalg.lstsq(F, window_data[:, i], rcond=None)[0]
            pred = beta[0] * curr_f1 + beta[1] * curr_f2 + beta[2] * curr_f3
            residuals[t, i] = R[t, i] - pred

    return residuals


def test_pair(res_entry: np.ndarray, fwd: np.ndarray, i: int, s: str,
              liquid_fwd: np.ndarray, hours: np.ndarray) -> None:
    """Print reversion stats for one pair."""
    absb = np.abs(res_entry) * 1e4
    band = (absb >= 6) & (absb < 12) & liquid_fwd
    cap = (-np.sign(res_entry[band, i]) * fwd[band, i]) * 1e4
    net = cap - PEPPERSTONE_COST_BPS[s]

    if len(cap) > 50:
        print(f"  {s:<10} n={len(cap):>5}  gross={cap.mean():+.3f}  net={net.mean():+.3f}  win%={(cap>0).mean()*100:5.1f}  t={net.mean()/(net.std()+1e-12)*np.sqrt(len(net)):+.1f}")
    else:
        print(f"  {s:<10} n={len(cap):>5}  (too few)")


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
    liquid_fwd = liquid_mask[:-1]

    # 2-factor vs 3-factor PCA
    res_2f, res_3f = rolling_pca_3factor(R, PCA_WINDOW_BARS)

    # Explicit EUR-proxy model
    res_eur = explicit_eur_proxy_residual(R, syms)

    # Variance explained
    Rc = R - R.mean(axis=0)
    std_w = Rc.std(axis=0) + 1e-12
    X = Rc / std_w
    _, S, Vt = np.linalg.svd(X, full_matrices=False)
    var_expl = S**2 / (S**2).sum()
    print("=== PCA Variance Explained (full sample) ===")
    for i in range(min(4, len(var_expl))):
        print(f"  PC{i+1}: {var_expl[i]*100:.1f}%")

    # Loadings
    print("\n=== PC3 Loadings ===")
    for i, s in enumerate(syms):
        print(f"  {s:<10} PC3={Vt[2, i]:+.4f}")

    # Reversion tests
    print("\n=== 6-12 bps REVERSION: 2-factor vs 3-factor vs EUR-proxy ===")
    for i, s in enumerate(syms):
        print(f"\n  {s}:")
        for label, res in [("2-factor", res_2f), ("3-factor", res_3f), ("EUR-proxy", res_eur)]:
            res_entry = res[:-1]
            fwd = R[1:]
            absb = np.abs(res_entry) * 1e4
            band = (absb >= 6) & (absb < 12) & liquid_fwd[:, None]
            cap = (-np.sign(res_entry[band[:, i], i]) * fwd[band[:, i], i]) * 1e4
            net = cap - PEPPERSTONE_COST_BPS[s]
            if len(cap) > 30:
                t = net.mean() / (net.std() + 1e-12) * np.sqrt(len(net))
                print(f"    {label:<12} n={len(cap):>5}  gross={cap.mean():+.3f}  net={net.mean():+.3f}  win%={(cap>0).mean()*100:5.1f}  t={t:+.1f}")
            else:
                print(f"    {label:<12} n={len(cap):>5}  (too few)")

    # Correlation: USDCHF residual vs EURUSD residual
    print("\n=== RESIDUAL CORRELATIONS (2-factor, liquid hours) ===")
    chf_idx = syms.index("USDCHF")
    eur_idx = syms.index("EURUSD")
    m = liquid_mask
    corr_1f = np.corrcoef((R - R.mean(axis=1, keepdims=True))[m, chf_idx],
                           (R - R.mean(axis=1, keepdims=True))[m, eur_idx])[0, 1]
    corr_2f = np.corrcoef(res_2f[m, chf_idx], res_2f[m, eur_idx])[0, 1]
    corr_3f = np.corrcoef(res_3f[m, chf_idx], res_3f[m, eur_idx])[0, 1]
    corr_eur = np.corrcoef(res_eur[m, chf_idx], res_eur[m, eur_idx])[0, 1]
    print(f"  Raw returns:   USDCHF-EURUSD corr = {corr_1f:+.3f}")
    print(f"  1-factor res:  USDCHF-EURUSD corr = {corr_1f:+.3f}")
    print(f"  2-factor res:  USDCHF-EURUSD corr = {corr_2f:+.3f}")
    print(f"  3-factor res:  USDCHF-EURUSD corr = {corr_3f:+.3f}")
    print(f"  EUR-proxy res: USDCHF-EURUSD corr = {corr_eur:+.3f}")


if __name__ == "__main__":
    main()
