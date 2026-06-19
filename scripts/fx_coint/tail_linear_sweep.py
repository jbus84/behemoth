"""Within the LINEAR family, does anything beat Ridge(alpha=1) on the 2h tail basket?

Same WFO, top-5% long basket, net realistic Razor cost, day-clustered significance.
Candidates: Ridge shrinkage sweep, OLS, Lasso, ElasticNet, and the 3-feature
momentum core (mom_short+mom_long+rvol_24) the ablation flagged as most significant,
plus an equal-weight momentum composite (no fitting at all).

Usage:
    uv run python scripts/fx_coint/tail_linear_sweep.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
CORE3 = ["mom_short", "mom_long", "rvol_24"]
MOM2 = ["mom_short", "mom_long"]
warnings.filterwarnings("ignore")

COMMISSION_BPS = 0.60
_SPREAD_PIP = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2}
_PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27}


def razor_cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMMISSION_BPS + (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4


def load_panel(sym, freq):
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    panel = build_panel(rsh.build_freq_bars(pl.read_parquet(src), freq))
    return panel if len(panel) >= 200 else None


# each spec: (feature_cols, model factory or None for equal-weight composite)
SPECS = {
    "ridge_a0.1": (FEATURE_COLS, lambda: Ridge(alpha=0.1)),
    "ridge_a1": (FEATURE_COLS, lambda: Ridge(alpha=1.0)),
    "ridge_a10": (FEATURE_COLS, lambda: Ridge(alpha=10.0)),
    "ridge_a100": (FEATURE_COLS, lambda: Ridge(alpha=100.0)),
    "ols": (FEATURE_COLS, lambda: LinearRegression()),
    "lasso_a0.01": (FEATURE_COLS, lambda: Lasso(alpha=0.01, max_iter=5000)),
    "enet_.01_.5": (FEATURE_COLS, lambda: ElasticNet(alpha=0.01, l1_ratio=0.5, max_iter=5000)),
    "ridge_core3": (CORE3, lambda: Ridge(alpha=1.0)),
    "ridge_mom2": (MOM2, lambda: Ridge(alpha=1.0)),
    "eqw_mom2": (MOM2, None),   # standardized mom_short+mom_long, no fitting
}


def wfo_rank(panel, cols, make, q=0.95, n_folds=5):
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[cols].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    bk = panel["bucket"].to_numpy()
    rows = []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        Xte = sc.transform(X[lo:hi])
        if make is None:
            pred = Xte.sum(axis=1)   # equal-weight composite of standardized features
        else:
            pred = make().fit(sc.transform(X[:split]), yz[:split]).predict(Xte)
        df = pd.DataFrame({"pred": pred, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])})
        rows.append(df[df["pred"] >= df["pred"].quantile(q)])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def day_clustered(d):
    daily = d.groupby(d["bucket"].dt.date)["net"].mean().to_numpy()
    if len(daily) < 3:
        return np.nan, np.nan
    t, p = ttest_1samp(daily, 0)
    return float(t), float(p)


def main():
    print("Linear-family sweep — top-5% 2h basket (EUR/GBP/JPY, net Razor cost)\n")
    print(f"{'spec':>13} {'n':>5} {'net':>8} {'naive_p':>8} {'dayT':>6} {'dayP':>7} "
          f"{'hit':>5} {'posYrs':>7}")
    for name, (cols, make) in SPECS.items():
        frames = []
        for sym in TIGHT:
            p = load_panel(sym, "2h")
            if p is None:
                continue
            d = wfo_rank(p, cols, make)
            d["net"] = d["act"] - razor_cost(sym)
            frames.append(d)
        d = pd.concat(frames, ignore_index=True)
        d["year"] = d["bucket"].dt.year
        _, pp = ttest_1samp(d["net"], 0)
        dt, dp = day_clustered(d)
        yr = d.groupby("year")["net"].mean()
        print(f"{name:>13} {len(d):>5} {d['net'].mean():>+8.3f} {pp:>8.3f} "
              f"{dt:>+6.2f} {dp:>7.3f} {(d['act']>0).mean()*100:>4.0f}% {(yr>0).sum()}/{len(yr)}")


if __name__ == "__main__":
    main()
