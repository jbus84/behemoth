"""Is the CONDITIONAL relationship (momentum/reversion) common across symbols?

Marginal shapes are shared once standardized (see dist_shape_weekly.py). The
modeling question is different: does the predictive COEFFICIENT — how past
return predicts next return — agree across symbols, or is each symbol its own?

Method (all on per-symbol VOL-STANDARDIZED 1h log returns, so scale is removed):
  - Features: lagged standardized returns at horizons mom1,mom3,mom6,mom12 bars.
  - Target:   next-bar standardized return.
  - Per-symbol OLS with Newey-West (HAC) t-stats  -> sign + magnitude per symbol.
  - Sign-agreement across symbols per feature.
  - POOLED homogeneity test: pooled OLS vs pooled+symbol-interactions; F-test on
    the interaction block = "do coefficients differ by symbol?" (Chow-style).
  - Leave-JPY-out pooled fit to see if JPY is the lone heterogeneity source.

Usage: uv run python scripts/fx_coint/conditional_homogeneity.py
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm

BARS = sorted(glob.glob("data/tick_bars/*_1h_flow.parquet"))
LAGS = {"mom1": 1, "mom3": 3, "mom6": 6, "mom12": 12}
FEATS = list(LAGS)


def build() -> pd.DataFrame:
    frames = []
    for f in BARS:
        sym = os.path.basename(f).split("_")[0]
        df = pd.read_parquet(f, columns=["bucket", "mid"])
        df["bucket"] = pd.to_datetime(df["bucket"])
        df = df.set_index("bucket").sort_index()
        r = np.log(df["mid"]).diff() * 1e4
        r = r[r.abs() < 500]
        z = (r - r.mean()) / r.std()          # vol-standardize, remove scale
        d = pd.DataFrame(index=z.index)
        for name, k in LAGS.items():
            # past-k cumulative standardized momentum, strictly lagged
            d[name] = z.rolling(k).sum().shift(1)
        d["y"] = z                            # next-bar standardized return (current row)
        d["sym"] = sym
        frames.append(d.dropna())
    return pd.concat(frames)


def per_symbol(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sym, g in df.groupby("sym"):
        X = sm.add_constant(g[FEATS])
        m = sm.OLS(g["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 24})
        row = {"sym": sym, "n": int(m.nobs), "R2_bps": 1e4 * m.rsquared}
        for f in FEATS:
            row[f] = m.params[f]
            row[f + "_t"] = m.tvalues[f]
        rows.append(row)
    return pd.DataFrame(rows).set_index("sym")


def homogeneity_ftest(df: pd.DataFrame, label: str) -> None:
    """Pooled vs pooled+symbol interactions. F-test on interaction block."""
    d = df.copy()
    dummies = pd.get_dummies(d["sym"], prefix="s", drop_first=True).astype(float)
    base = sm.add_constant(d[FEATS])
    # restricted: common coefficients (+ symbol intercept dummies)
    Xr = pd.concat([base, dummies], axis=1)
    mr = sm.OLS(d["y"], Xr).fit()
    # unrestricted: add feature x symbol interactions
    inter = {}
    for f in FEATS:
        for c in dummies.columns:
            inter[f"{f}_{c}"] = d[f].to_numpy() * dummies[c].to_numpy()
    Xu = pd.concat([Xr, pd.DataFrame(inter, index=d.index)], axis=1)
    mu = sm.OLS(d["y"], Xu).fit()
    q = len(inter)  # restrictions
    n = int(mu.nobs)
    k = Xu.shape[1]
    F = ((mr.ssr - mu.ssr) / q) / (mu.ssr / (n - k))
    from scipy.stats import f as fdist
    p = fdist.sf(F, q, n - k)
    print(f"  [{label}] homogeneity F-test (do coeffs differ by symbol?): "
          f"F={F:.2f}, q={q}, p={p:.3g}  ->  {'DIFFER' if p < 0.05 else 'COMMON'}")
    print(f"    pooled R2_bps={1e4*mr.rsquared:.2f}  unrestricted R2_bps={1e4*mu.rsquared:.2f}")


def main() -> None:
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.4f}")
    df = build()

    print("=" * 80)
    print("PER-SYMBOL conditional coefficients (standardized 1h, Newey-West t)")
    print("=" * 80)
    ps = per_symbol(df)
    print(ps[["n", "R2_bps"] + FEATS])
    print("\nNewey-West t-stats:")
    print(ps[[f + "_t" for f in FEATS]])

    print("\n" + "=" * 80)
    print("SIGN AGREEMENT across the 6 symbols (per feature)")
    print("=" * 80)
    for f in FEATS:
        signs = np.sign(ps[f].to_numpy())
        npos = int((signs > 0).sum())
        sig = ps[(ps[f + "_t"].abs() > 2)].index.tolist()
        print(f"  {f:6s}: {npos}/6 positive, mean coef {ps[f].mean():+.4f}, "
              f"|t|>2 in: {sig if sig else 'none'}")

    print("\n" + "=" * 80)
    print("POOLED HOMOGENEITY TESTS")
    print("=" * 80)
    homogeneity_ftest(df, "all 6 symbols")
    homogeneity_ftest(df[df["sym"] != "USDJPY"], "ex-USDJPY")

    print("\nInterpretation:")
    print("  COMMON + sign-agreement => standardize-then-POOL is correct.")
    print("  DIFFER overall but COMMON ex-JPY => pool the 5, treat JPY separately.")
    print("  DIFFER even ex-JPY + sign disagreement => SEPARATE models justified.")


if __name__ == "__main__":
    main()
