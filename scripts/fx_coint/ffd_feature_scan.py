"""Fractionally-differentiated features (Lopez de Prado AFML ch.5) + big IC scan.

Manages over-differencing: instead of d=0 (levels, max memory, non-stationary)
or d=1 (returns, stationary, no memory), find the MIN d in (0,1) whose ADF
passes, preserving maximum predictive memory.

Steps:
  1. FFD via fixed-width window weights (AFML 5.3).
  2. Per symbol: ADF over a d-grid -> minimum stationary d on log price.
  3. Feature library (FFD at several d, momentum, level z, vol, accel, flow)
     scanned vs forward returns h={1,6,24,48}, pooled over 5 non-JPY majors,
     with per-symbol sign consistency + pooled t + BH-FDR across the whole scan.

Usage: uv run python scripts/fx_coint/ffd_feature_scan.py
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller

BARS = sorted(glob.glob("data/tick_bars/*_1h_flow.parquet"))
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]  # ex-JPY
HORIZONS = [1, 6, 24, 48]
D_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7]


# ---------- Fractional differencing (fixed-width window) ----------
def ffd_weights(d: float, thres: float = 1e-4) -> np.ndarray:
    w = [1.0]
    k = 1
    while True:
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thres:
            break
        w.append(w_)
        k += 1
    return np.array(w[::-1])  # oldest..newest


def frac_diff_ffd(series: pd.Series, d: float, thres: float = 1e-4) -> pd.Series:
    w = ffd_weights(d, thres)
    width = len(w)
    vals = series.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    for i in range(width - 1, len(vals)):
        out[i] = np.dot(w, vals[i - width + 1 : i + 1])
    return pd.Series(out, index=series.index)


def min_stationary_d(logp: pd.Series) -> tuple[float, int]:
    """Smallest d in D_GRID whose ADF rejects unit root at 5%. Returns (d, window)."""
    sample = logp.dropna()
    for d in D_GRID:
        fd = frac_diff_ffd(sample, d).dropna()
        if len(fd) < 1000:
            continue
        # subsample for ADF speed
        s = fd.iloc[:: max(1, len(fd) // 8000)]
        p = adfuller(s, maxlag=10, autolag=None)[1]
        if p < 0.05:
            return d, len(ffd_weights(d))
    return 1.0, 1


# ---------- Feature library ----------
def build_features(sym_file: str, d_star: float) -> pd.DataFrame:
    df = pd.read_parquet(sym_file)
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.set_index("bucket").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)
    z = (r - r.mean()) / r.std()
    d = pd.DataFrame(index=df.index)

    # FFD at several d (the over-differencing sweep) — standardized, lagged
    for dd in (0.2, 0.3, 0.4, round(d_star, 2)):
        fd = frac_diff_ffd(logp, dd)
        d[f"ffd_{dd}"] = ((fd - fd.mean()) / fd.std()).shift(1)
    # classic momentum (d=1 family)
    for k in (1, 6, 24):
        d[f"mom{k}"] = z.rolling(k).sum().shift(1)
    # level z (d=0 family)
    for w in (24, 96):
        d[f"pxdev{w}"] = ((logp - logp.rolling(w).mean()) / logp.rolling(w).std()).shift(1)
    # vol / accel / range
    d["rvol"] = df["rvol_bps"].shift(1)
    d["accel"] = (z - z.shift(6)).shift(1)
    d["absmom6"] = z.rolling(6).sum().abs().shift(1)
    # flow
    d["flow_tick"] = df["flow_tick"].shift(1)
    d["flow_ofi"] = df["flow_ofi"].shift(1)

    for h in HORIZONS:
        d[f"y{h}"] = (logp.shift(-h) - logp) * 1e4
    return d


def main() -> None:
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.4f}")
    files = {os.path.basename(f).split("_")[0]: f for f in BARS}

    print("=" * 80)
    print("1. MIN STATIONARY d (ADF<0.05) per symbol on log-price")
    print("=" * 80)
    dstar = {}
    for s in POOL + ["USDJPY"]:
        logp = np.log(pd.read_parquet(files[s], columns=["mid"])["mid"])
        d_, width = min_stationary_d(logp)
        dstar[s] = d_
        print(f"  {s}: min d* = {d_:.2f}  (window {width} bars)")
    d_use = float(np.median([dstar[s] for s in POOL]))
    print(f"\n  pooled d* (median ex-JPY) = {d_use:.2f}  -> used as ffd_{round(d_use,2)} feature")

    # build features for the 5 pooled symbols
    data = {s: build_features(files[s], d_use) for s in POOL}
    feats = [c for c in next(iter(data.values())).columns if not c.startswith("y")]

    print("\n" + "=" * 80)
    print("2. BIG IC SCAN — pooled Spearman over 5 non-JPY majors, BH-FDR controlled")
    print("=" * 80)
    results = []
    for f in feats:
        for h in HORIZONS:
            ics = []
            for s in POOL:
                dd = data[s][[f, f"y{h}"]].dropna()
                if len(dd) < 500:
                    ics.append(np.nan); continue
                ics.append(stats.spearmanr(dd[f], dd[f"y{h}"])[0])
            ics = np.array(ics)
            ic = np.nanmean(ics)
            se = np.nanstd(ics, ddof=1) / np.sqrt(np.isfinite(ics).sum())
            t = ic / se if se > 0 else np.nan
            # two-sided p from t with df=4
            p = 2 * stats.t.sf(abs(t), df=4) if np.isfinite(t) else 1.0
            sgn = int((np.sign(ics) == np.sign(ic)).sum())
            results.append(dict(feature=f, h=h, ic=ic, t=t, p=p, sign=f"{sgn}/5"))
    res = pd.DataFrame(results)
    # BH-FDR across the entire scan
    res = res.sort_values("p").reset_index(drop=True)
    m = len(res)
    res["bh_thresh"] = (res.index + 1) / m * 0.10
    res["bh_sig"] = res["p"] <= res["bh_thresh"]
    # report survivors (BH 10% AND >=4/5 sign agreement)
    res["robust"] = res["bh_sig"] & (res["sign"].isin(["5/5", "4/5"]))
    print(f"  scanned {m} (feature x horizon) cells; BH-FDR q=0.10\n")
    show = res.sort_values(["robust", "t"], key=lambda c: c if c.name != "t" else c.abs(),
                           ascending=[False, False])
    print(show[["feature", "h", "ic", "t", "p", "sign", "bh_sig", "robust"]].head(25).to_string(index=False))
    n_robust = int(res["robust"].sum())
    print(f"\n  ROBUST survivors (BH-sig AND >=4/5 sign-consistent): {n_robust}")
    if n_robust:
        top = res[res["robust"]].sort_values("t", key=lambda c: c.abs(), ascending=False)
        print(top[["feature", "h", "ic", "t", "sign"]].to_string(index=False))


if __name__ == "__main__":
    main()
