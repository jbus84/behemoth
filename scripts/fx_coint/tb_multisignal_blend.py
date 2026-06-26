"""Does an ffd_0.1 TB leg add value beyond ffd_zvol20 + XS (despite corr +0.67)?

Builds daily-PnL for several TB books (signal x N) plus XS reversion, prints the
correlation matrix, and compares candidate blends by Calmar:
  - 2-leg current best:  TB(ffd_zvol20, N=50) + XS
  - swap:                TB(ffd_0.1, N=50) + XS
  - 3-leg:               TB(ffd_zvol20,50) + TB(ffd_0.1,20) + XS
A correlated leg only "adds value" if a blend including it beats the best blend
without it; otherwise ffd_0.1 should replace, not augment.

Usage: uv run python scripts/fx_coint/tb_multisignal_blend.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.xs_reversion as xsr
from scripts.fx_coint.feature_ic_definitive import DATA, SUFFIX, build_all
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap
from scripts.fx_coint.triple_barrier import triple_barrier_core

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_EVENTS = 40000
N_FOLDS = 5
COST = 1.0
Q_MAG = 0.90
BOOKS = [("ffd_zvol20", 50), ("ffd_0.1", 50), ("ffd_0.1", 20)]


def _ts(sym):
    import polars as pl
    df = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.to_datetime(df["timestamp"].to_numpy()).tz_localize(None).to_numpy().astype("datetime64[ns]")
    return t[np.argsort(t.astype("int64"))]


def tb_daily(signal, n_tb):
    cache = {s: build_all(s) for s in POOL}
    ts = {s: _ts(s) for s in POOL}
    sym = {}
    for s in POOL:
        logp, f, vol, bph = build_all(s)
        n = len(logp)
        warm = int(96 * bph) + 60
        ev = np.arange(warm, n - n_tb - 3)
        ev = ev[np.isfinite(vol[ev + 1]) & (vol[ev + 1] > 0)]
        rng = np.random.default_rng(0)
        ev = np.sort(rng.choice(ev, min(N_EVENTS, len(ev)), replace=False))
        entry = ev + 1
        t1, y, _, _ = triple_barrier_core(logp, entry, np.minimum(entry + n_tb, len(logp) - 1),
                                          1.0 * vol[entry] * np.sqrt(n_tb))
        sym[s] = dict(entry=entry, t1=t1, y=y, sig=f[signal][ev], ts=ts[s])
    all_entry = np.concatenate([sym[s]["entry"] for s in POOL])
    edges = np.quantile(all_entry, np.linspace(0, 1, N_FOLDS + 1))
    recs = []
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        for s in POOL:
            d = sym[s]
            tr = d["entry"] < lo
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if tr.sum() < 200 or te.sum() < 20:
                continue
            thr = np.nanquantile(np.abs(d["sig"][tr]), Q_MAG)
            sel = (np.abs(d["sig"]) >= thr) & te & np.isfinite(d["y"])
            o = np.argsort(d["entry"][sel])
            e_s, t_s = d["entry"][sel][o], d["t1"][sel][o]
            p_s = (-np.sign(d["sig"][sel]) * d["y"][sel])[o]
            ko = greedy_nonoverlap(e_s, t_s)
            for idx, p in zip(e_s[ko], p_s[ko] - COST):
                recs.append((pd.Timestamp(d["ts"][idx]).normalize(), float(p)))
    df = pd.DataFrame(recs, columns=["date", "pnl"])
    return df.groupby("date")["pnl"].sum()


def _u(s):
    return s / (s.std() + 1e-9)


def calmar(s):
    cum = s.cumsum()
    dd = (cum - cum.cummax()).min()
    yr = s.groupby(s.index.year).sum()
    return (s.mean() * 252) / (abs(dd) + 1e-9), dd, int((yr > 0).sum()), len(yr)


def main():
    series = {}
    for sig, n in BOOKS:
        s = tb_daily(sig, n)
        s.index = pd.to_datetime(s.index)
        series[f"{sig}@{n}"] = _u(s)
    xs = xsr.__dict__.setdefault("TURN_COST_FRAC", 1.0)
    xsr.TURN_COST_FRAC = 1.0
    x = xsr.backtest(xsr.residualise(xsr.daily_returns()), 20)
    x.index = pd.to_datetime(x.index)
    series["XS@20"] = _u(x)

    M = pd.concat(series, axis=1).dropna(how="all").fillna(0.0)
    print("Correlation matrix (unit-vol daily PnL):")
    print(M.corr().round(2).to_string())

    def blend(cols, label):
        w = 1.0 / len(cols)
        comb = sum(w * M[c] for c in cols)
        cal, dd, pos, ny = calmar(comb)
        print(f"  {label:42s} Calmar={cal:5.2f}  maxDD={dd:7.1f}  pos={pos}/{ny}")

    print("\nEqual-weight blends:")
    blend(["ffd_zvol20@50", "XS@20"], "zvol20@50 + XS              (current 2-leg)")
    blend(["ffd_0.1@50", "XS@20"], "ffd_0.1@50 + XS             (swap)")
    blend(["ffd_zvol20@50", "ffd_0.1@20", "XS@20"], "zvol20@50 + ffd_0.1@20 + XS (3-leg)")
    blend(["ffd_zvol20@50", "ffd_0.1@50", "XS@20"], "zvol20@50 + ffd_0.1@50 + XS (3-leg)")


if __name__ == "__main__":
    main()
