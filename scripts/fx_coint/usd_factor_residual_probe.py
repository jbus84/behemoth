"""Hourly USD-factor residual mean-reversion probe (strategy (a)).

Question: at hourly frequency, does removing a common USD factor leave a
pair-specific residual that mean-reverts cross-sectionally, dollar-neutral?

Design (look-ahead-guarded):
  * Resample tick bars -> hourly mid close per pair.
  * Orient each pair to USD-STRENGTH log return:
        xxxUSD (EUR/GBP/AUD): usd_ret = -dlog(pair)
        USDxxx (JPY/CHF/CAD): usd_ret = +dlog(pair)
  * Factor = equal-weighted mean of the 6 oriented returns (NO estimated beta
    -> fully known at time t, no look-ahead leakage via betas).
  * Residual_i,t = usd_ret_i,t - factor_t.  (Residuals sum to ~0 across pairs.)
  * Reversion test: pooled OLS of residual_{t+h} on residual_t for h=1..6.
  * XS strategy: each hour rank pairs by residual_t; short top / long bottom
    (dollar-neutral by construction); PnL = forward 1h oriented return of the
    book. Report gross, net of measured spread, and positive-month %.
"""

from __future__ import annotations

import numpy as np
import polars as pl

PAIRS: dict[str, float] = {
    # symbol -> sign to convert pair dlog into USD-strength return
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCHF": +1.0,
    "USDCAD": +1.0,
}
TICK = "1000tick"  # plenty of resolution for hourly closes, smaller than 100tick


def hourly_mid(sym: str) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_{TICK}.parquet")
    df = df.with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        ((pl.col("close_ask") - pl.col("close_bid")) / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("rel_spread"),
        pl.col("timestamp").dt.truncate("1h").alias("hour"),
    )
    # last tick-bar within each hour = hourly close
    g = (
        df.sort("timestamp")
        .group_by("hour")
        .agg(
            pl.col("mid").last().alias(f"mid_{sym}"),
            pl.col("rel_spread").median().alias(f"spr_{sym}"),
        )
        .sort("hour")
    )
    return g


def main() -> None:
    frames = [hourly_mid(s) for s in PAIRS]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="hour", how="inner")
    df = df.drop_nulls().sort("hour")
    print(f"aligned hourly rows: {df.height}  span: {df['hour'][0]} -> {df['hour'][-1]}")

    # oriented USD-strength log returns
    syms = list(PAIRS)
    rets = {}
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        dlog = np.diff(np.log(mid))
        rets[s] = PAIRS[s] * dlog
    R = np.column_stack([rets[s] for s in syms])  # (T-1, 6) oriented returns
    hours = df["hour"].to_numpy()[1:]
    spreads = np.array([df[f"spr_{s}"].median() for s in syms])
    # time-varying spread aligned to the ENTRY hour (signal hour t -> spread at t)
    Spr = np.column_stack([df[f"spr_{s}"].to_numpy()[1:] for s in syms])  # (T-1, 6)
    print("median rel spread (bps):", dict(zip(syms, np.round(spreads * 1e4, 2))))

    # ---- factor: equal-weighted (known) + PC1 robustness ----
    factor_ew = R.mean(axis=1)
    Rc = R - R.mean(axis=0)
    U, S, Vt = np.linalg.svd(Rc / R.std(axis=0), full_matrices=False)
    pc1 = (Rc / R.std(axis=0)) @ Vt[0]
    var_expl = (S**2 / (S**2).sum())
    # align PC1 sign with EW
    if np.corrcoef(pc1, factor_ew)[0, 1] < 0:
        pc1 = -pc1
    print(f"\nPC1 variance explained: {var_expl[0]*100:.1f}%  (PC2 {var_expl[1]*100:.1f}%)")
    print(f"corr(EW factor, PC1): {np.corrcoef(factor_ew, pc1)[0,1]:.3f}")
    print(f"mean |factor| share of pair var: factor std {factor_ew.std()*1e4:.2f}bps vs pair std {R.std():.6f}")

    # ---- residuals (EW factor, unit beta -> no look-ahead) ----
    R_res = R - factor_ew[:, None]

    def reversion(X: np.ndarray, label: str) -> None:
        print(f"\n[{label}] pooled OLS slope of value_{{t+h}} on value_t (neg = reversion):")
        for h in range(1, 7):
            x = X[:-h].ravel()
            y = X[h:].ravel()
            m = np.isfinite(x) & np.isfinite(y)
            x, y = x[m], y[m]
            b = np.cov(x, y)[0, 1] / np.var(x)
            r = np.corrcoef(x, y)[0, 1]
            t = r * np.sqrt((len(x) - 2) / max(1e-12, 1 - r**2))
            print(f"  h={h}: slope {b:+.4f}  corr {r:+.4f}  t {t:+.1f}")

    reversion(R, "RAW oriented returns")
    reversion(R_res, "RESIDUALS (factor removed)")

    # ---- XS dollar-neutral reversion strategy on residuals ----
    hrs = hours[1:]
    ym = np.array([str(h)[:7] for h in hrs])

    def run_xs(idx: list[int], thr: float, label: str) -> None:
        # recompute factor/residual on the chosen subset (factor = EW of subset)
        Rs = R[:, idx]
        fac = Rs.mean(axis=1)
        res = Rs - fac[:, None]
        spr = spreads[idx]
        sig = res[:-1]
        fwd = Rs[1:]
        w = -(sig - sig.mean(axis=1, keepdims=True))
        if thr > 0:  # only act on dislocations beyond thr * rolling std of residual
            sd_res = res.std()
            w = np.where(np.abs(sig - sig.mean(axis=1, keepdims=True)) > thr * sd_res, w, 0.0)
        gross_exp = np.abs(w).sum(axis=1, keepdims=True)
        w = np.divide(w, gross_exp, out=np.zeros_like(w), where=gross_exp > 0)
        pnl_gross = (w * fwd).sum(axis=1)
        dW = np.abs(np.diff(w, axis=0, prepend=0))
        cost = (dW * spr[None, :]).sum(axis=1)  # per-pair spread cost
        pnl_net = pnl_gross - cost

        def line(p: np.ndarray, tag: str) -> None:
            mu, sd = p.mean(), p.std()
            t = mu / sd * np.sqrt(len(p)) if sd > 0 else 0.0
            print(f"    {tag}: mean/hr {mu*1e4:+.3f}bps  t {t:+.1f}  sharpe(h) {mu/sd if sd>0 else 0:+.4f}")

        active = (np.abs(w).sum(axis=1) > 0).mean()
        print(f"\n[XS {label}] pairs={[syms[i] for i in idx]} thr={thr} active={active*100:.0f}% turn={dW.sum(axis=1).mean():.2f} cost/hr={cost.mean()*1e4:.3f}bps")
        line(pnl_gross, "GROSS")
        line(pnl_net, "NET  ")
        for arr, tag in [(pnl_gross, "gross"), (pnl_net, "net")]:
            months: dict[str, list[float]] = {}
            for m, v in zip(ym, arr):
                months.setdefault(m, []).append(v)
            pos = np.mean([np.sum(v) > 0 for v in months.values()])
            print(f"    pos-month% ({tag}): {pos*100:.0f}%")

    all_idx = list(range(len(syms)))
    tight_idx = [syms.index(s) for s in ("EURUSD", "USDJPY", "GBPUSD")]  # 0.27/0.34/0.68 bps
    run_xs(all_idx, 0.0, "all-6 every-hour")
    run_xs(tight_idx, 0.0, "tight-3 every-hour")
    run_xs(tight_idx, 1.5, "tight-3 dislocation>1.5sd")
    run_xs(all_idx, 1.5, "all-6 dislocation>1.5sd")

    # ---- time-varying spread / session analysis ----
    print("\n=== HOUR-OF-DAY: reversion edge vs spread (tight-3) ===")
    res_t3 = R[:, tight_idx] - R[:, tight_idx].mean(axis=1, keepdims=True)
    sig = res_t3[:-1]
    fwd = R[1:, :][:, tight_idx]
    w = -(sig - sig.mean(axis=1, keepdims=True))
    w = w / np.maximum(np.abs(w).sum(axis=1, keepdims=True), 1e-12)
    g = (w * fwd).sum(axis=1)  # gross pnl per hour
    dW = np.abs(np.diff(w, axis=0, prepend=0))
    spr_entry = Spr[:-1][:, tight_idx]
    cost_tv = (dW * spr_entry).sum(axis=1)  # actual-spread cost
    hod = np.array([int(str(h)[11:13]) for h in hrs])  # UTC hour
    print("  UTC  gross(bps)  cost_tv(bps)  net(bps)   n")
    for hh in range(24):
        m = hod == hh
        if m.sum() < 50:
            continue
        gm, cm = g[m].mean() * 1e4, cost_tv[m].mean() * 1e4
        print(f"   {hh:02d}    {gm:+.3f}      {cm:.3f}       {gm-cm:+.3f}   {m.sum()}")

    # restrict to liquid hours (London-NY overlap) with ACTUAL hourly spread
    liquid = (hod >= 7) & (hod <= 16)
    for tag, mask in [("ALL hrs, true spread", np.ones_like(hod, bool)), ("LIQUID 7-16 UTC, true spread", liquid)]:
        gg = g[mask]
        nn = (g[mask] - cost_tv[mask])
        print(f"\n[{tag}] tight-3 every-hour")
        print(f"  GROSS {gg.mean()*1e4:+.3f}bps t{gg.mean()/gg.std()*np.sqrt(len(gg)):+.1f}   NET {nn.mean()*1e4:+.3f}bps t{nn.mean()/nn.std()*np.sqrt(len(nn)):+.1f}")
        mym = ym[mask]
        months: dict[str, float] = {}
        for mm, v in zip(mym, nn):
            months[mm] = months.get(mm, 0.0) + v
        print(f"  net pos-month%: {np.mean([v>0 for v in months.values()])*100:.0f}%")


if __name__ == "__main__":
    main()
