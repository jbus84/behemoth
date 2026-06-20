"""Is the 'mu carries ~zero signal' result an artifact of the L2 (Gaussian) loss?

Ridge = MLE of location ONLY under a Gaussian likelihood.  With kurtosis ~91 the
squared-error objective is dominated by tail outliers, which can bury conditional
LOCATION signal.  A heavy-tailed/robust location estimator down-weights those
outliers — exactly what a real GAMLSS location submodel (Student-t / Johnson SU)
would do.  So we compare RANKING ESTIMATORS on the identical walk-forward top-5%
basket (EUR/GBP/JPY, 2h, net of realistic Razor cost):

  ridge      : L2 / Gaussian-MLE location (current)
  huber      : robust location, down-weights tails
  quantile50 : median (L1) location, tail-insensitive

If huber/median rank a better net basket than ridge, the heavy tails were hiding
directional signal and a true GAMLSS is justified.

Usage:
    uv run python scripts/fx_coint/tail_robust_location.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import HuberRegressor, QuantileRegressor, Ridge
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


def razor_cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMMISSION_BPS + (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4


def load_panel(sym, freq):
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    panel = build_panel(rsh.build_freq_bars(pl.read_parquet(src), freq))
    return panel if len(panel) >= 200 else None


def estimators():
    return {
        "ridge": lambda: Ridge(alpha=1.0),
        "huber": lambda: HuberRegressor(epsilon=1.35, alpha=1e-3, max_iter=500),
        "quantile50": lambda: QuantileRegressor(quantile=0.5, alpha=1e-3, solver="highs"),
    }


def wfo_rank(panel, make_model, q=0.95, n_folds=5):
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
        pred = make_model().fit(sc.transform(X[:split]), yz[:split]).predict(sc.transform(X[lo:hi]))
        df = pd.DataFrame({"pred": pred, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])})
        rows.append(df[df["pred"] >= df["pred"].quantile(q)])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def day_clustered(d):
    daily = d.groupby(d["bucket"].dt.date)["net"].mean().to_numpy()
    if len(daily) < 3:
        return float("nan"), float("nan")
    t, p = ttest_1samp(daily, 0)
    return float(t), float(p)


def main():
    print("Comparison of RANKING ESTIMATOR on identical top-5% 2h basket "
          "(EUR/GBP/JPY, net realistic Razor cost)\n")
    print(f"{'estimator':>11} {'n':>5} {'net':>8} {'naive_p':>8} {'dayT':>6} {'dayP':>7} "
          f"{'hit':>5} {'posYrs':>7}")
    for name, make in estimators().items():
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
        t, pp = ttest_1samp(d["net"], 0)
        dt, dp = day_clustered(d)
        yr = d.groupby("year")["net"].mean()
        print(f"{name:>11} {len(d):>5} {d['net'].mean():>+8.3f} {pp:>8.3f} "
              f"{dt:>+6.2f} {dp:>7.3f} {(d['act']>0).mean()*100:>4.0f}% "
              f"{(yr>0).sum()}/{len(yr)}")


if __name__ == "__main__":
    main()
