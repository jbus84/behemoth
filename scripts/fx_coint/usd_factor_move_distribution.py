"""Distribution of hourly USD-factor residual moves + conditional reversion.

Answers: how big are typical residual dislocations, and does conditioning on
dislocation SIZE isolate trades whose expected reversion clears the spread?
This is the honest test of confidence-gating: bucket every pair-hour by |residual|
and report E[reversion capture] vs the round-trip spread, per bucket.
"""

from __future__ import annotations

import numpy as np
from usd_factor_residual_probe import PAIRS, hourly_mid


def main() -> None:
    syms = list(PAIRS)
    frames = [hourly_mid(s) for s in syms]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="hour", how="inner")
    df = df.drop_nulls().sort("hour")

    rets, sprs = [], []
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        rets.append(PAIRS[s] * np.diff(np.log(mid)))
        sprs.append(df[f"spr_{s}"].to_numpy()[1:])
    R = np.column_stack(rets)          # oriented returns (T-1, 6)
    Spr = np.column_stack(sprs)        # round-trip rel spread per pair-hour
    fac = R.mean(axis=1)
    Res = R - fac[:, None]             # residual returns

    # per-trade: signal at t, reversion captured over t->t+1, betting -sign(signal)
    s = Res[:-1]                       # dislocation (this-hour residual return)
    fwd = Res[1:]                      # next-hour residual return
    spr = Spr[:-1]                     # spread at entry (round trip)
    cap = -np.sign(s) * fwd           # gross capture per pair-hour (oriented)

    sf = s.ravel()
    capf = cap.ravel()
    sprf = spr.ravel()
    absbps = np.abs(sf) * 1e4

    print(f"pair-hours: {len(sf):,}")
    print("\n=== |residual move| distribution (bps) ===")
    for p in (50, 75, 90, 95, 99, 99.9):
        print(f"  p{p:>4}: {np.percentile(absbps, p):6.2f}")
    print(f"  max  : {absbps.max():6.2f}   mean: {absbps.mean():.2f}   std: {absbps.std():.2f}")

    print("\n=== conditional reversion by |dislocation| bucket (pooled all 6 pairs) ===")
    print("  bucket          n     mean|s|   E[capture]   spread(RT)   net      win%  cap>spr%")
    edges = [0, 50, 75, 90, 95, 99, 100]
    qs = np.percentile(absbps, edges)
    for i in range(len(edges) - 1):
        m = (absbps >= qs[i]) & (absbps < qs[i + 1] if i < len(edges) - 2 else absbps <= qs[i + 1])
        if m.sum() < 50:
            continue
        cb = capf[m] * 1e4
        sb = sprf[m] * 1e4
        lbl = f"p{edges[i]}-{edges[i+1]}"
        print(f"  {lbl:<12} {m.sum():>7}   {absbps[m].mean():6.2f}    {cb.mean():+7.3f}     {sb.mean():6.3f}    {cb.mean()-sb.mean():+7.3f}   {(cb>0).mean()*100:4.0f}   {(cb>sb).mean()*100:5.0f}")

    # EURUSD-only (tightest spread) extreme tail, since cost differs per pair
    eu = syms.index("EURUSD")
    se = np.abs(s[:, eu]) * 1e4
    ce = (-np.sign(s[:, eu]) * fwd[:, eu]) * 1e4
    spe = spr[:, eu] * 1e4
    print(f"\n=== EURUSD only (spread ~{spe.mean():.2f}bps RT), top-decile tail ===")
    thr = np.percentile(se, 90)
    m = se >= thr
    print(f"  |s|>={thr:.2f}bps  n={m.sum()}  E[capture]={ce[m].mean():+.3f}bps  net={ce[m].mean()-spe[m].mean():+.3f}  win%={(ce[m]>0).mean()*100:.0f}")
    thr99 = np.percentile(se, 99)
    m99 = se >= thr99
    print(f"  |s|>={thr99:.2f}bps  n={m99.sum()}  E[capture]={ce[m99].mean():+.3f}bps  net={ce[m99].mean()-spe[m99].mean():+.3f}  win%={(ce[m99]>0).mean()*100:.0f}")

    # --- robustness: break-even spread + temporal stability of EURUSD top-decile ---
    print("\n=== EURUSD top-decile (|s|>=p90) robustness ===")
    capd = ce[m]  # gross capture bps for top-decile trades
    print(f"  break-even spread (RT) = mean gross capture = {capd.mean():.3f} bps")
    print(f"  vs ECN ~0.33  |  retail/IG ~1.2-1.8  -> needs spread < {capd.mean():.2f}bps RT")
    years = df["hour"].dt.year().to_numpy()[1:1+len(s)]  # align to s rows
    ye = years[m]  # years for EURUSD top-decile trades (m indexes the s rows)
    print("  year   n     gross    net(@0.33)   net(@1.5)")
    for y in sorted(set(ye.tolist())):
        ym_ = ye == y
        if ym_.sum() < 20:
            continue
        gc = capd[ym_].mean()
        print(f"  {y}  {ym_.sum():>4}   {gc:+.3f}    {gc-0.33:+.3f}      {gc-1.5:+.3f}")


if __name__ == "__main__":
    main()
