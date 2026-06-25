"""Cross-symbol distributional homogeneity of the EXOGENOUS FEATURES.

dist_shape_weekly.py covered the target (returns). This covers the features the
real models actually feed in: spread, realized vol, order flow, tick count.
Question: are feature distributions common across symbols (so a pooled model
sees the same feature meaning per pair), and does per-symbol standardization
fix scale mismatches the way it did for returns?

Two levels per feature:
  RAW         pairwise KS on raw feature  -> native-scale comparability
  STANDARDIZED per-symbol z-score, pairwise KS -> shape comparability after scaling
Also: does the feature->next-return SIGN agree across symbols (is the feature's
predictive meaning common)?

Usage: uv run python scripts/fx_coint/feature_homogeneity.py
"""
from __future__ import annotations

import glob
import os
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

BARS = sorted(glob.glob("data/tick_bars/*_1h_flow.parquet"))
FEATS = ["spread_bps", "rvol_bps", "flow_tick", "flow_ofi", "n_ticks"]


def load() -> dict[str, pd.DataFrame]:
    out = {}
    for f in BARS:
        sym = os.path.basename(f).split("_")[0]
        df = pd.read_parquet(f)
        df["bucket"] = pd.to_datetime(df["bucket"])
        df = df.set_index("bucket").sort_index()
        df["spread_bps"] = (df["ask"] - df["bid"]) / df["mid"] * 1e4
        df["ret_next"] = (np.log(df["mid"]).diff() * 1e4).shift(-1)
        df = df[np.isfinite(df["spread_bps"])]
        out[sym] = df
    return out


def marginal_scale(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for sym, df in data.items():
        row = {"sym": sym}
        for f in FEATS:
            row[f + "_med"] = df[f].median()
        rows.append(row)
    return pd.DataFrame(rows).set_index("sym")


def ks_grid(data: dict[str, pd.DataFrame], feat: str, standardize: bool) -> float:
    """Mean pairwise KS statistic across symbol pairs (sampled for speed)."""
    syms = list(data)
    vecs = {}
    for s in syms:
        v = data[s][feat].dropna().to_numpy()
        if standardize:
            v = (v - v.mean()) / (v.std() + 1e-12)
        # sample to 8000 for KS speed/stability
        if len(v) > 8000:
            v = np.random.default_rng(0).choice(v, 8000, replace=False)
        vecs[s] = v
    stats_ = [stats.ks_2samp(vecs[a], vecs[b])[0] for a, b in combinations(syms, 2)]
    return float(np.mean(stats_))


def feature_sign_agreement(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per-symbol univariate corr(feature_standardized, next standardized return).
    Tests whether the feature's PREDICTIVE meaning is common across symbols."""
    rows = []
    for sym, df in data.items():
        d = df.dropna(subset=FEATS + ["ret_next"])
        yz = (d["ret_next"] - d["ret_next"].mean()) / d["ret_next"].std()
        row = {"sym": sym}
        for f in FEATS:
            xz = (d[f] - d[f].mean()) / d[f].std()
            row[f] = np.corrcoef(xz, yz)[0, 1]
        rows.append(row)
    return pd.DataFrame(rows).set_index("sym")


def main() -> None:
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:9.4f}")
    data = load()

    print("=" * 80)
    print("A. RAW FEATURE SCALE per symbol (medians) — native comparability")
    print("=" * 80)
    print(marginal_scale(data))
    print("\n  Big spreads across rows => raw features NOT poolable; need per-symbol scaling.")

    print("\n" + "=" * 80)
    print("B. CROSS-SYMBOL KS — mean pairwise KS stat (0=identical, 1=disjoint)")
    print("=" * 80)
    print(f"{'feature':12s} {'RAW':>10s} {'STANDARDIZED':>14s}")
    for f in FEATS:
        print(f"{f:12s} {ks_grid(data, f, False):10.3f} {ks_grid(data, f, True):14.3f}")
    print("\n  RAW high + STD low  => scale differs but SHAPE common (standardize-then-pool OK).")
    print("  STD still high      => shape genuinely differs => feature not poolable even scaled.")

    print("\n" + "=" * 80)
    print("C. FEATURE PREDICTIVE SIGN across symbols (corr feat_z vs next ret_z)")
    print("=" * 80)
    sa = feature_sign_agreement(data)
    print(sa)
    print()
    for f in FEATS:
        signs = np.sign(sa[f].to_numpy())
        npos = int((signs > 0).sum())
        print(f"  {f:12s}: {npos}/6 positive, mean corr {sa[f].mean():+.4f}, "
              f"ex-JPY mean {sa.drop('USDJPY')[f].mean():+.4f}")


if __name__ == "__main__":
    main()
