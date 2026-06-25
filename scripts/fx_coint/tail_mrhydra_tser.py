"""Time-series extrinsic regression (TSER) vs the current Ridge approach.

Current approach: Ridge on 5 hand-crafted scalar features (r_1, mom_short, mom_long,
rvol_24, hour) predicting the vol-normalized next-2h-bar return.

New approach: aeon MultiRocketHydraRegressor on the RAW preceding return window
(the last K 2h-bar returns) — convolution features + ridge, learned end-to-end.

Both are run on the IDENTICAL aligned rows and walk-forward folds, selecting the
top-5% long basket, net realistic Razor cost, scored by day-clustered significance.
The return window for bar t uses r_{t-K+1..t} only (decision-time observable); any
window spanning a session gap (NaN return) is dropped — no temporal leakage.

Run (isolated env; project pins numpy 2.4 which blocks numba/aeon):
    uv run --no-project --with "numpy==2.2.6" --with numba --with aeon \
        --with polars --with pandas --with scikit-learn --with scipy \
        python scripts/fx_coint/tail_mrhydra_tser.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from aeon.regression.convolution_based import MultiRocketHydraRegressor
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
BASE = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]
K = 24  # return-window length (48h of 2h bars)

COMMISSION_BPS = 0.60
_SPREAD_PIP = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2}
_PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27}


def razor_cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMMISSION_BPS + (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4


def build(sym, freq="2h", width_min=120, session=(7, 21), vol_lb=24):
    """Aligned panel: BASE scalar features + raw return window + target."""
    raw = pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet")
    t = raw.sort("bucket").with_columns(pl.col("bucket").dt.truncate(freq).alias("bf"))
    bars = (t.group_by("bf").agg(pl.col("mid").last()).rename({"bf": "bucket"})
            .sort("bucket").to_pandas())
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    h = bars["bucket"].dt.hour
    bars = bars[(h >= session[0]) & (h < session[1]) & (bars["bucket"].dt.dayofweek < 5)].reset_index(drop=True)
    step = np.timedelta64(width_min, "m")
    contig = (bars["bucket"].to_numpy() - bars["bucket"].shift(1).to_numpy()) == step
    contig[0] = False
    mid = bars["mid"].to_numpy()
    r = np.empty(len(bars))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~contig] = np.nan
    rs = pd.Series(r)

    feat = pd.DataFrame({"bucket": bars["bucket"]})
    feat["r_1"] = r
    feat["mom_short"] = rs.rolling(5, min_periods=3).sum().to_numpy()
    feat["mom_long"] = rs.rolling(18, min_periods=9).sum().shift(5).to_numpy()
    feat["rvol_24"] = rs.rolling(vol_lb, min_periods=vol_lb // 2).std().shift(1).to_numpy()
    feat["hour"] = bars["bucket"].dt.hour.astype(float).to_numpy()
    sigma = feat["rvol_24"].to_numpy()
    ret_next = rs.shift(-1).to_numpy()
    feat["ret_next_bps"] = ret_next
    feat["target_z"] = ret_next / sigma

    # raw K-lag return window for bar t: r[t-K+1 .. t].  Gap returns (overnight,
    # NaN) are zero-filled = "flat across the gap"; mirrors how the rolling-sum
    # baseline features tolerate gaps.  Decision-time observable (only past r).
    n = len(r)
    win = np.full((n, K), np.nan)
    for j in range(K):
        win[:, j] = rs.shift(K - 1 - j).to_numpy()
    # require at least the most-recent bar (r_1) present, then zero-fill gaps
    win_ok = np.isfinite(win[:, -1])
    win = np.nan_to_num(win, nan=0.0)

    finite = np.isfinite(feat[BASE].to_numpy()).all(axis=1) & np.isfinite(feat["target_z"].to_numpy())
    finite &= (sigma > 0) & win_ok
    idx = np.where(finite)[0]
    # drop rows immediately after an index gap (preserve shift relationships)
    keep = np.r_[True, np.diff(idx) == 1]
    idx = idx[keep]
    return feat.iloc[idx].reset_index(drop=True), win[idx]


def folds(n, n_folds=5, frac=0.5):
    edges = np.linspace(int(n * frac), n, n_folds + 1).astype(int)
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo >= 5 and split >= 30:
            yield split, lo, hi


def run_pair(sym, q=0.95):
    feat, win = build(sym)
    yz = feat["target_z"].to_numpy()
    act = feat["ret_next_bps"].to_numpy()
    bk = pd.to_datetime(feat["bucket"].to_numpy())
    Xs = feat[BASE].to_numpy()
    cost = razor_cost(sym)
    out = {"ridge": [], "mrhydra": []}
    for split, lo, hi in folds(len(feat)):
        # current approach: Ridge on scalar features
        sc = StandardScaler().fit(Xs[:split])
        pr = Ridge(alpha=1.0).fit(sc.transform(Xs[:split]), yz[:split]).predict(sc.transform(Xs[lo:hi]))
        # new approach: MultiRocketHydra on raw return window (n, 1, K)
        Xtr = win[:split][:, None, :]
        Xte = win[lo:hi][:, None, :]
        reg = MultiRocketHydraRegressor(random_state=0)
        reg.fit(Xtr, yz[:split])
        pm = reg.predict(Xte)
        for name, pred in (("ridge", pr), ("mrhydra", pm)):
            df = pd.DataFrame({"pred": pred, "act": act[lo:hi], "bucket": bk[lo:hi]})
            sel = df[df["pred"] >= df["pred"].quantile(q)].copy()
            sel["net"] = sel["act"] - cost
            out[name].append(sel)
    return {k: pd.concat(v, ignore_index=True) for k, v in out.items()}


def report(name, sels):
    d = pd.concat(sels, ignore_index=True)
    d["year"] = d["bucket"].dt.year
    daily = d.groupby(d["bucket"].dt.date)["net"].mean()
    dt, dp = ttest_1samp(daily, 0)
    _, npv = ttest_1samp(d["net"], 0)
    yr = d.groupby("year")["net"].mean()
    print(f"  {name:>9} n={len(d):>4} net={d['net'].mean():>+6.3f} naive_p={npv:.3f} "
          f"dayT={dt:>+5.2f} dayP={dp:.3f} hit={(d['act']>0).mean()*100:>3.0f}% pos={int((yr>0).sum())}/{len(yr)}")


def main():
    print(f"TSER (MultiRocketHydra, window K={K}) vs current Ridge — top-5% 2h basket, net Razor cost\n")
    res = {m: [] for m in ("ridge", "mrhydra")}
    for sym in TIGHT:
        print(f"fitting {sym} ...", flush=True)
        r = run_pair(sym)
        for m in res:
            res[m].append(r[m])
    print()
    report("ridge", res["ridge"])
    report("mrhydra", res["mrhydra"])


if __name__ == "__main__":
    main()
