"""Weekly return-distribution shape per FX symbol + same-distribution tests.

Questions answered:
  1. Shape of each symbol's 1h log-return distribution (moments, tails).
  2. INTRA-symbol: are weeks drawn from the same distribution week-to-week,
     or does each week look different? (KS of each week vs symbol pooled.)
  3. INTER-symbol: are the symbols drawn from the same distribution?
     (Pairwise KS on pooled returns AND week-by-week.)
  4. Do symbols share structure (vol-regime co-movement) even if their
     marginal shapes differ?

Usage: uv run python scripts/fx_coint/dist_shape_weekly.py
"""
from __future__ import annotations

import glob
import os
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

BARS = sorted(glob.glob("data/tick_bars/*_1h_flow.parquet"))


def load() -> dict[str, pd.DataFrame]:
    out = {}
    for f in BARS:
        sym = os.path.basename(f).split("_")[0]
        df = pd.read_parquet(f, columns=["bucket", "mid"])
        df["bucket"] = pd.to_datetime(df["bucket"])
        df = df.set_index("bucket").sort_index()
        # 1h log returns in bps
        df["ret"] = np.log(df["mid"]).diff() * 1e4
        df = df.dropna(subset=["ret"])
        # drop weekend gaps / absurd jumps via simple clip on |ret|>500bps (data glitch)
        df = df[df["ret"].abs() < 500]
        df["week"] = df.index.to_period("W")
        out[sym] = df
    return out


def shape_table(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for sym, df in data.items():
        r = df["ret"].to_numpy()
        rows.append(
            dict(
                sym=sym,
                n=len(r),
                mean=r.mean(),
                std=r.std(),
                skew=stats.skew(r),
                kurt=stats.kurtosis(r),  # excess
                q01=np.percentile(r, 1),
                q99=np.percentile(r, 99),
                jb_p=stats.jarque_bera(r)[1],
            )
        )
    return pd.DataFrame(rows).set_index("sym")


def intra_symbol_stability(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """For each symbol, std of weekly moments (how much shape drifts week to week)
    and fraction of weeks whose STANDARDIZED returns reject KS vs the symbol's
    own pooled standardized distribution."""
    rows = []
    for sym, df in data.items():
        wk = df.groupby("week")["ret"]
        wmean = wk.mean()
        wstd = wk.std()
        wskew = wk.apply(lambda x: stats.skew(x) if len(x) > 5 else np.nan)
        # standardize each week by its OWN mean/std, compare shape vs pooled standardized
        pooled_z = ((df["ret"] - df["ret"].mean()) / df["ret"].std()).to_numpy()
        rej = 0
        tot = 0
        for _, g in df.groupby("week"):
            if len(g) < 20:
                continue
            z = (g["ret"] - g["ret"].mean()) / g["ret"].std()
            p = stats.ks_2samp(z.to_numpy(), pooled_z)[1]
            tot += 1
            rej += p < 0.05
        rows.append(
            dict(
                sym=sym,
                n_weeks=df["week"].nunique(),
                wk_mean_std=wmean.std(),     # dispersion of weekly mean (drift instability)
                wk_vol_std=wstd.std(),       # dispersion of weekly vol (vol clustering)
                wk_vol_cv=wstd.std() / wstd.mean(),
                wk_skew_std=wskew.std(),
                pct_weeks_shape_differs=100 * rej / max(tot, 1),
            )
        )
    return pd.DataFrame(rows).set_index("sym")


def inter_symbol_pooled(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pairwise KS on STANDARDIZED pooled returns: are the SHAPES the same?
    (Standardize first so we test shape, not just that JPY has bigger bps vol.)"""
    syms = list(data)
    z = {s: ((data[s]["ret"] - data[s]["ret"].mean()) / data[s]["ret"].std()).to_numpy() for s in syms}
    rows = []
    for a, b in combinations(syms, 2):
        ks_stat, ks_p = stats.ks_2samp(z[a], z[b])
        rows.append(dict(pair=f"{a}/{b}", ks_stat=ks_stat, ks_p=ks_p, same_shape=ks_p > 0.05))
    return pd.DataFrame(rows).set_index("pair")


def inter_symbol_comovement(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Even if marginals differ, do symbols share a common VOL REGIME?
    Align weekly realized vol across symbols and correlate."""
    wvol = pd.DataFrame({s: data[s].groupby("week")["ret"].std() for s in data}).dropna()
    corr = wvol.corr()
    # also correlate weekly MEAN return (do they drift together = USD factor)
    wmean = pd.DataFrame({s: data[s].groupby("week")["ret"].mean() for s in data}).dropna()
    mcorr = wmean.corr()
    return corr, mcorr


def main() -> None:
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.3f}")
    data = load()

    print("=" * 80)
    print("1. MARGINAL SHAPE — each symbol's 1h log-return distribution (bps)")
    print("=" * 80)
    print(shape_table(data))
    print("\n  kurt = EXCESS kurtosis (0 = normal). jb_p<0.05 => non-normal.")

    print("\n" + "=" * 80)
    print("2. INTRA-SYMBOL — is each symbol stationary week-to-week?")
    print("=" * 80)
    print(intra_symbol_stability(data))
    print("\n  wk_vol_cv high => strong vol clustering (weeks NOT iid in scale).")
    print("  pct_weeks_shape_differs => after standardizing, how often a week's")
    print("  SHAPE still rejects vs the symbol's own pooled shape.")

    print("\n" + "=" * 80)
    print("3. INTER-SYMBOL — same SHAPE across symbols? (standardized pooled KS)")
    print("=" * 80)
    print(inter_symbol_pooled(data))

    print("\n" + "=" * 80)
    print("4. INTER-SYMBOL — week-by-week SHAPE divergence (fraction of weeks")
    print("   where the pair's standardized returns reject same-dist, KS p<0.05)")
    print("=" * 80)
    syms = list(data)
    # align on common weeks, standardize per week within symbol
    rows = []
    for a, b in combinations(syms, 2):
        wa = {w: g["ret"].to_numpy() for w, g in data[a].groupby("week")}
        wb = {w: g["ret"].to_numpy() for w, g in data[b].groupby("week")}
        common = [w for w in wa if w in wb and len(wa[w]) >= 20 and len(wb[w]) >= 20]
        rej = 0
        for w in common:
            za = (wa[w] - wa[w].mean()) / wa[w].std()
            zb = (wb[w] - wb[w].mean()) / wb[w].std()
            rej += stats.ks_2samp(za, zb)[1] < 0.05
        rows.append(dict(pair=f"{a}/{b}", n_weeks=len(common), pct_weeks_differ=100 * rej / max(len(common), 1)))
    print(pd.DataFrame(rows).set_index("pair"))

    print("\n" + "=" * 80)
    print("5. SHARED STRUCTURE — weekly realized-vol correlation across symbols")
    print("=" * 80)
    vcorr, mcorr = inter_symbol_comovement(data)
    print("Weekly VOL correlation (common vol regime?):")
    print(vcorr)
    print("\nWeekly MEAN-return correlation (common USD drift factor?):")
    print(mcorr)


if __name__ == "__main__":
    main()
