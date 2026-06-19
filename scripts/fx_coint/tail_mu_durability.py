"""Is the deployable basket (top-5% mu, 2h, net of real cost) DURABLE or front-loaded?

The pooled number is +1.30 bps net, p=0.018.  That is real.  The only question
that decides go/no-go is whether it survives year-by-year and in the recent era,
or whether it lives entirely in 2022-2023.

Usage:
    uv run python scripts/fx_coint/tail_mu_durability.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import COST_BPS, FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
WIDE = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "USDCHF"]
warnings.filterwarnings("ignore")


def day_clustered_t(d: pd.DataFrame) -> tuple[float, float, int]:
    """t-test on per-DAY mean net (clusters same-day cross-pair correlation)."""
    daily = d.groupby(d["bucket"].dt.date)["net"].mean().to_numpy()
    if len(daily) < 3:
        return float("nan"), float("nan"), len(daily)
    t, p = ttest_1samp(daily, 0)
    return float(t), float(p), len(daily)


def load_panel(sym, freq):
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    panel = build_panel(rsh.build_freq_bars(pl.read_parquet(src), freq))
    return panel if len(panel) >= 200 else None


def wfo(panel, q=0.95, n_folds=5):
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
        mu = Ridge(alpha=1.0).fit(sc.transform(X[:split]), yz[:split]).predict(sc.transform(X[lo:hi]))
        df = pd.DataFrame({"mu": mu, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])})
        df = df[df["mu"] >= df["mu"].quantile(q)]
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build(universe, freq):
    frames = []
    for sym in universe:
        p = load_panel(sym, freq)
        if p is None:
            continue
        d = wfo(p)
        d["net"] = d["act"] - COST_BPS[sym]
        d["sym"] = sym
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["year"] = d["bucket"].dt.year
    return d


def report(d, label):
    print(f"\n{'='*64}\n{label}\n{'='*64}")
    print(f"{'year':>6} {'n':>5} {'net':>8} {'t':>6} {'p':>7} {'hit':>5}")
    for y, g in d.groupby("year"):
        net = g["net"].to_numpy()
        t, pp = ttest_1samp(net, 0) if len(net) > 2 else (np.nan, np.nan)
        print(f"{y:>6} {len(g):>5} {net.mean():>+8.3f} {t:>+6.2f} {pp:>7.3f} {(g['act']>0).mean()*100:>4.0f}%")
    yr = d.groupby("year")["net"].mean()
    print(f"  positive years: {(yr>0).sum()}/{len(yr)}")
    for hlabel, mask in [("2022-23", d["bucket"] < pd.Timestamp("2024-01-01")),
                         ("2024-26", d["bucket"] >= pd.Timestamp("2024-01-01")),
                         ("ALL", d["bucket"] == d["bucket"])]:
        g = d[mask]
        t, pp = ttest_1samp(g["net"], 0)
        dt, dp, nd = day_clustered_t(g)
        print(f"  {hlabel:<8} n={len(g):<5} net={g['net'].mean():+.3f} "
              f"naive_p={pp:.3f}  day-clustered t={dt:+.2f} p={dp:.3f} (ndays={nd})")


# Realistic Pepperstone-Razor cost: ~0.60 bps RT commission (≈$3.5/side) + tight
# executable liquid-hours spread (NOT the inflated Dukascopy feed spread).
# spread pips: EURUSD .1 USDJPY .1 GBPUSD .2 AUDUSD .1 USDCAD .3 USDCHF .3
COMMISSION_BPS = 0.60
_SPREAD_PIP = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "AUDUSD": .1, "USDCAD": .3, "USDCHF": .3}
_PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "AUDUSD": .65, "USDCAD": 1.36, "USDCHF": .89}


def razor_cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    spr_bps = (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4
    return COMMISSION_BPS + spr_bps


def build_cost(universe, freq, cost_fn):
    frames = []
    for sym in universe:
        p = load_panel(sym, freq)
        if p is None:
            continue
        d = wfo(p)
        d["net"] = d["act"] - cost_fn(sym)
        d["sym"] = sym
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["year"] = d["bucket"].dt.year
    return d


def main():
    print("Razor costs (bps RT):", {s: round(razor_cost(s), 2) for s in WIDE})
    report(build(TIGHT, "2h"), "TIGHT (EUR/GBP/JPY) 2h top-5% mu, net  [repo costs]")
    report(build(WIDE, "2h"), "WIDE (6) 2h top-5% mu, net  [repo costs ~1.0 on wide pairs]")
    report(build_cost(WIDE, "2h", razor_cost),
           "WIDE (6) 2h top-5% mu, net  [REALISTIC Razor commission-dominated cost]")
    # AUDUSD on its own, corrected cost — does it carry the edge?
    for s in ["AUDUSD", "USDCAD", "USDCHF"]:
        report(build_cost([s], "2h", razor_cost), f"{s} alone 2h top-5% mu, net  [Razor cost {razor_cost(s):.2f}]")


if __name__ == "__main__":
    main()
