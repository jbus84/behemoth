"""Simulate what EURCHF data would do for USDCHF.

Since we don't have EURCHF tick data yet, we SYNTHESIZE it from existing data:
  EURCHF = EURUSD * USDCHF (approximately, ignoring log cross-product terms)
  In log terms: log(EURCHF) ≈ log(EURUSD) + log(USDCHF)
  So dlog(EURCHF) ≈ dlog(EURUSD) + dlog(USDCHF)

This lets us test the concept: if we had EURCHF, could we build a CHF-strength
factor and save USDCHF?
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


def rolling_pca_3factor(R: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rolling 3-factor PCA. Returns (residuals, pc1, pc2, pc3)."""
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
        pc3_t = curr_std @ Vt[2]
        expected_std = Vt[0] * pc1_t + Vt[1] * pc2_t + Vt[2] * pc3_t
        expected = expected_std * std_w + mean_w
        residuals[t] = R[t] - expected
    return residuals


def chf_factor_residual(R: np.ndarray, syms: list[str]) -> np.ndarray:
    """Explicit CHF-strength factor using EURCHF cross.

    Synthesize EURCHF = EURUSD * USDCHF (log addition).
    Then CHF return = -dlog(EURCHF) + dlog(EURUSD) (CHF per EUR, EUR per USD).
    Actually simpler: build a CHF factor from CHF crosses.
    """
    T, n_pairs = R.shape
    eur_idx = syms.index("EURUSD")
    chf_idx = syms.index("USDCHF")

    # Synthesize EURCHF oriented return:
    # EURCHF = EUR per CHF.
    # In oriented terms (USD-strength), EURUSD is -dlog(EURUSD), USDCHF is +dlog(USDCHF).
    # But in raw price terms: log(EURCHF) = log(EURUSD) + log(USDCHF)
    # dlog(EURCHF) = dlog(EURUSD) + dlog(USDCHF)
    # EURCHF oriented (CHF per EUR) = -dlog(EURCHF) = -dlog(EURUSD) - dlog(USDCHF)
    # Wait — this is getting confused. Let's just use the raw returns.
    #
    # Actually, the oriented returns in R are:
    #   EURUSD: -dlog(EURUSD)  [USD strength]
    #   USDCHF: +dlog(USDCHF)  [USD strength]
    # Raw: dlog(EURUSD) = -R[:, eur_idx]
    # Raw: dlog(USDCHF) = +R[:, chf_idx]
    # dlog(EURCHF) = dlog(EURUSD) + dlog(USDCHF) = -R[:, eur_idx] + R[:, chf_idx]
    # EURCHF oriented = CHF strength = -dlog(EURCHF) = R[:, eur_idx] - R[:, chf_idx]

    eurchf_ret = R[:, eur_idx] - R[:, chf_idx]  # CHF-strength proxy

    # Now build a CHF factor using EURCHF + GBPCHF (if we had it)
    # We only have EURCHF synthesized. Use it as the CHF factor.
    chf_factor = eurchf_ret

    # USDCHF residual = USDCHF - beta_USD*USD_factor - beta_CHF*CHF_factor
    # But we already have USD factor from PCA. Let's do explicit:
    # USDCHF = USD factor + CHF factor + residual
    # We can estimate this with OLS on rolling window.

    residuals = np.zeros_like(R)
    for t in range(T):
        start = max(0, t - PCA_WINDOW_BARS)
        window_data = R[start:t]
        chf_f = chf_factor[start:t]
        if len(window_data) < 50:
            residuals[t] = R[t] - R[t].mean()
            continue

        # Factor 1: USD strength = mean of non-CHF USD pairs
        non_chf = [syms.index(s) for s in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]]
        usd_f = window_data[:, non_chf].mean(axis=1)

        # Factor 2: CHF strength (from EURCHF)
        # Regress each pair on [USD_f, CHF_f]
        F = np.column_stack([usd_f, chf_f[:len(usd_f)]])
        for i in range(n_pairs):
            beta = np.linalg.lstsq(F, window_data[:, i], rcond=None)[0]
            pred = beta[0] * usd_f[-1] + beta[1] * chf_f[-1]
            residuals[t, i] = R[t, i] - pred

    return residuals


def main() -> None:
    frames = [bar_mid(s) for s in PAIRS]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bar_time", how="inner")
    df = df.drop_nulls().sort("bar_time")

    syms = list(PAIRS)
    n_pairs = len(syms)

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

    # Synthesize EURCHF
    eur_idx = syms.index("EURUSD")
    chf_idx = syms.index("USDCHF")
    # dlog(EURCHF) = dlog(EURUSD) + dlog(USDCHF)
    # In oriented terms: EURUSD oriented = -dlog(EURUSD), USDCHF oriented = +dlog(USDCHF)
    # So dlog(EURUSD) = -R[:, eur_idx], dlog(USDCHF) = R[:, chf_idx]
    # dlog(EURCHF) = -R[:, eur_idx] + R[:, chf_idx]
    # EURCHF oriented (CHF per EUR) = -dlog(EURCHF) = R[:, eur_idx] - R[:, chf_idx]
    eurchf_oriented = R[:, eur_idx] - R[:, chf_idx]
    print("Synthesized EURCHF oriented return stats:")
    print(f"  mean={eurchf_oriented.mean()*1e4:.3f}bps  std={eurchf_oriented.std()*1e4:.3f}bps")
    print(f"  corr with USDCHF: {np.corrcoef(eurchf_oriented, R[:, chf_idx])[0,1]:+.3f}")
    print(f"  corr with EURUSD: {np.corrcoef(eurchf_oriented, R[:, eur_idx])[0,1]:+.3f}")

    # Add EURCHF as 7th pair
    R7 = np.column_stack([R, eurchf_oriented])
    syms + ["EURCHF"]

    # 2-factor PCA on 7 pairs
    res_2f = rolling_pca_3factor(R7, PCA_WINDOW_BARS)[:, :n_pairs]

    # Explicit CHF-factor model
    res_chf = chf_factor_residual(R, syms)

    # Test USDCHF under each model
    print("\n=== USDCHF REVERSION (6-12 bps band) ===")
    for label, res in [("2-factor (6-pair)", res_2f), ("2-factor+EURCHF (7-pair)", res_2f), ("Explicit CHF factor", res_chf)]:
        res_entry = res[:-1]
        fwd = R[1:]
        absb = np.abs(res_entry) * 1e4
        band = (absb[:, chf_idx] >= 6) & (absb[:, chf_idx] < 12) & liquid_fwd
        cap = (-np.sign(res_entry[band, chf_idx]) * fwd[band, chf_idx]) * 1e4
        net = cap - PEPPERSTONE_COST_BPS["USDCHF"]
        if len(cap) > 50:
            t = net.mean() / (net.std() + 1e-12) * np.sqrt(len(net))
            print(f"  {label:<25} n={len(cap):>5}  gross={cap.mean():+.3f}  net={net.mean():+.3f}  win%={(cap>0).mean()*100:5.1f}  t={t:+.1f}")
        else:
            print(f"  {label:<25} n={len(cap):>5}  (too few)")

    # Also test correlation: USDCHF res vs EURUSD res under explicit CHF model
    m = liquid_mask
    corr_chf = np.corrcoef(res_chf[m, chf_idx], res_chf[m, eur_idx])[0, 1]
    corr_2f = np.corrcoef(res_2f[m, chf_idx], res_2f[m, eur_idx])[0, 1]
    print("\n=== USDCHF-EURUSD residual correlation ===")
    print(f"  2-factor (6-pair):        {corr_2f:+.3f}")
    print(f"  Explicit CHF factor:        {corr_chf:+.3f}")


if __name__ == "__main__":
    main()
