"""Full IC breakdown: features vs forward returns across horizons + the
over-differencing hypothesis (are returns too stationary to predict?).

Tiny ICs are expected in FX; what matters is SIGN CONSISTENCY across the 5
poolable symbols and a pooled t-stat, not magnitude. We also test whether
predictability lives at LONGER horizons (less noise) and in LEVEL-type
features/targets (less differenced) rather than 1-bar returns.

Features (all per-symbol standardized):
  mom1,mom3,mom6,mom12  : differenced (return momentum)
  px_dev_24, px_dev_96  : LEVEL z-score = (mid - rollmean)/rollstd  (mean-reversion)
  rvol, flow_tick, flow_ofi, spread, n_ticks : microstructure
Targets:
  fwd return over h = 1,3,6,12,24,48 bars (cumulative), per-symbol standardized.

For each (feature, horizon): pooled Spearman IC over the 5 non-JPY majors,
HAC-style t via per-symbol IC mean / se, and #symbols with matching sign.

Usage: uv run python scripts/fx_coint/ic_breakdown_horizons.py
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
from scipy import stats

BARS = sorted(glob.glob("data/tick_bars/*_1h_flow.parquet"))
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]  # ex-JPY (heterogeneous)
HORIZONS = [1, 3, 6, 12, 24, 48]


def build(sym_file: str) -> pd.DataFrame:
    df = pd.read_parquet(sym_file)
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.set_index("bucket").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4)
    r = r.where(r.abs() < 500)
    z = (r - r.mean()) / r.std()
    d = pd.DataFrame(index=df.index)
    # differenced momentum features (strictly lagged)
    for k in (1, 3, 6, 12):
        d[f"mom{k}"] = z.rolling(k).sum().shift(1)
    # LEVEL features: price z-score vs its own rolling window (mean-reversion signal)
    for w in (24, 96):
        m = logp.rolling(w).mean()
        s = logp.rolling(w).std()
        d[f"px_dev_{w}"] = ((logp - m) / s).shift(1)
    # microstructure
    df["spread_bps"] = (df["ask"] - df["bid"]) / df["mid"] * 1e4
    for f in ("rvol_bps", "flow_tick", "flow_ofi", "spread_bps", "n_ticks"):
        d[f] = df[f].shift(1)
    # forward cumulative returns (targets)
    for h in HORIZONS:
        fwd = (logp.shift(-h) - logp) * 1e4
        d[f"y{h}"] = fwd
    return d


def main() -> None:
    pd.set_option("display.width", 240, "display.float_format", lambda x: f"{x:8.4f}")
    data = {os.path.basename(f).split("_")[0]: build(f) for f in BARS}

    feats = ["mom1", "mom3", "mom6", "mom12", "px_dev_24", "px_dev_96",
             "rvol_bps", "flow_tick", "flow_ofi", "spread_bps", "n_ticks"]

    # collect per-symbol Spearman IC for each (feat, horizon)
    print("=" * 110)
    print("POOLED SPEARMAN IC (5 non-JPY majors)  —  ic = mean per-symbol IC;  "
          "t = mean/se(6? no,5);  sgn = #symbols sign-matching pooled")
    print("=" * 110)
    header = f"{'feature':11s}" + "".join(f"  h{h:<3d}            " for h in HORIZONS)
    print(header)
    for f in feats:
        cells = []
        for h in HORIZONS:
            ics = []
            for s in POOL:
                d = data[s][[f, f"y{h}"]].dropna()
                if len(d) < 500:
                    ics.append(np.nan)
                    continue
                ics.append(stats.spearmanr(d[f], d[f"y{h}"])[0])
            ics = np.array(ics)
            ic = np.nanmean(ics)
            se = np.nanstd(ics, ddof=1) / np.sqrt(np.isfinite(ics).sum())
            t = ic / se if se > 0 else np.nan
            sgn = int((np.sign(ics) == np.sign(ic)).sum())
            star = "*" if abs(t) > 2.5 and sgn >= 4 else " "
            cells.append(f"{ic:+.4f} t{t:+4.1f} {sgn}/5{star}")
        print(f"{f:11s} " + " ".join(f"{c:18s}" for c in cells))

    print("\n  * = |t|>2.5 AND >=4/5 symbols agree on sign (a real common signal).")

    # Over-differencing check: predictability of the TARGET itself by horizon.
    # Variance ratio of cumulative return vs h*var(1-bar): >1 trending, <1 mean-reverting.
    print("\n" + "=" * 110)
    print("OVER-DIFFERENCING / STATIONARITY CHECK")
    print("=" * 110)
    print("Variance ratio VR(h)=Var(r_h)/(h*Var(r_1)) per symbol "
          "(=1 random walk, <1 mean-revert, >1 trend):")
    rows = []
    for s in POOL + ["USDJPY"]:
        logp = np.log(pd.read_parquet(dict(zip([os.path.basename(f).split('_')[0] for f in BARS], BARS))[s])["mid"])
        r1 = logp.diff().dropna()
        v1 = r1.var()
        row = {"sym": s}
        for h in HORIZONS:
            rh = (logp.shift(-h) - logp).dropna()
            row[f"VR{h}"] = rh.var() / (h * v1)
        rows.append(row)
    print(pd.DataFrame(rows).set_index("sym"))
    print("\n  If VR<1 at some h, levels mean-revert => a LEVEL target (px_dev) should")
    print("  predict better than 1-bar return. If VR~1 everywhere, returns are a")
    print("  random walk at 1h and NO feature transform restores 1-bar predictability.")


if __name__ == "__main__":
    main()
