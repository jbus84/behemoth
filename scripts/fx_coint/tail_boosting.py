"""Does gradient boosting beat Ridge on the EUR/GBP/JPY 2h tail basket?

The diagnosed mechanism is regime-dependent payoff convexity (momentum pays in
trend, whipsaws in chop) — a nonlinear momentum x regime INTERACTION that a linear
Ridge cannot represent but a tree CAN split on natively.  Linear interaction terms
already failed (multicollinearity); trees are the proper test.

Like-for-like: identical features, walk-forward, top-5% long basket, net realistic
Razor cost, day-clustered significance.  Discipline: top-5% of ~660 trades is small,
trees overfit heavy tails — so SHALLOW trees, strong regularization, and we read the
day-clustered p (not naive) and positive-year count, not a single mean.

Usage:
    uv run python scripts/fx_coint/tail_boosting.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
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


def models():
    return {
        "ridge": lambda: Ridge(alpha=1.0),
        # shallow, regularized GBM — squared error (over-weights big moves, where edge lives)
        "gbr_d2": lambda: GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.03, max_depth=2,
            subsample=0.7, min_samples_leaf=40),
        "gbr_d3": lambda: GradientBoostingRegressor(
            n_estimators=300, learning_rate=0.03, max_depth=3,
            subsample=0.7, min_samples_leaf=40),
        # absolute-error GBM — robust, mirrors the heavy-tail story (expect worse)
        "gbr_lad": lambda: GradientBoostingRegressor(
            loss="absolute_error", n_estimators=200, learning_rate=0.03,
            max_depth=2, subsample=0.7, min_samples_leaf=40),
        "hgb": lambda: HistGradientBoostingRegressor(
            max_depth=3, learning_rate=0.03, max_iter=300,
            min_samples_leaf=40, l2_regularization=1.0),
    }


def wfo_rank(panel, make, q=0.95, n_folds=5):
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
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
        pred = make().fit(sc.transform(X[:split]), yz[:split]).predict(sc.transform(X[lo:hi]))
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
    print("Boosting vs Ridge — identical top-5% 2h basket (EUR/GBP/JPY, net Razor cost)\n")
    print(f"{'model':>9} {'n':>5} {'net':>8} {'naive_p':>8} {'dayT':>6} {'dayP':>7} "
          f"{'hit':>5} {'posYrs':>7}")
    for name, make in models().items():
        frames = []
        for sym in TIGHT:
            p = load_panel(sym, "2h")
            if p is None:
                continue
            d = wfo_rank(p, make)
            d["net"] = d["act"] - razor_cost(sym)
            frames.append(d)
        d = pd.concat(frames, ignore_index=True)
        d["year"] = d["bucket"].dt.year
        _, pp = ttest_1samp(d["net"], 0)
        dt, dp = day_clustered(d)
        yr = d.groupby("year")["net"].mean()
        print(f"{name:>9} {len(d):>5} {d['net'].mean():>+8.3f} {pp:>8.3f} "
              f"{dt:>+6.2f} {dp:>7.3f} {(d['act']>0).mean()*100:>4.0f}% {(yr>0).sum()}/{len(yr)}")


if __name__ == "__main__":
    main()
