"""2025 performance + drawdown for the two VALIDATED signals:
  - 2h momentum: EUR/GBP/JPY, expanding-WFO Ridge top-5% long, net realistic Razor cost.
  - 2-3d reversion: fade past-10d extended move, hold 2 days, causal expanding-q90 thresholds.

Pools the tight majors; reports 2025 trades, total/mean net (bps), win%, max drawdown, and the
monthly cumulative path. Reads 1m flow bars from the tail-wfo data dir.

Usage:
    uv run python scripts/fx_coint/perf_2025.py
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"2h": 120, "1d": 1440})
DATA = _Path("/Users/danielfisher/repositories/behemoth-tail-wfo/data/tick_bars")
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
COST = {"EURUSD": 0.69, "GBPUSD": 0.76, "USDJPY": 0.67}  # realistic Razor bps


def mom_2h_trades(sym):
    """Expanding 5-fold WFO Ridge, top-5% long; per-trade net (bps) + bucket."""
    bars = rsh.build_freq_bars(pl.read_parquet(DATA / f"{sym}_1m_flow.parquet"), "2h", session=(7, 21))
    p = build_panel(bars, vol_lookback=24)
    n = len(p)
    edges = np.linspace(int(n * 0.5), n, 6).astype(int)
    X = p[FEATURE_COLS].to_numpy()
    yz = p["target_z"].to_numpy()
    act = p["ret_next_bps"].to_numpy()
    bk = pd.to_datetime(p["bucket"].to_numpy())
    rows = []
    for k in range(5):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        pred = Ridge(alpha=1.0).fit(sc.transform(X[:split]), yz[:split]).predict(sc.transform(X[lo:hi]))
        sel = pred >= np.quantile(pred, 0.95)
        rows.append(pd.DataFrame({"net": act[lo:hi][sel] - COST[sym], "bucket": bk[lo:hi][sel]}))
    return pd.concat(rows, ignore_index=True)


def rev_trades(sym, L=10, H=2, q=0.90, warmup=60):
    """Causal fade of past-L extended move, hold H days, non-overlapping; per-trade net + bucket."""
    bars = rsh.build_freq_bars(pl.read_parquet(DATA / f"{sym}_1m_flow.parquet"), "1d", session=(0, 24))
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)
    sig = (rs.rolling(L, min_periods=L // 2).sum() / (rs.rolling(20, min_periods=10).std() * np.sqrt(L))).to_numpy()
    n = len(mid)
    fwd = np.full(n, np.nan)
    fwd[:n - H] = (np.log(mid[H:]) - np.log(mid[:n - H])) * 1e4
    bk = pd.to_datetime(bars["bucket"].to_numpy())
    grid = np.arange(0, n, H)
    grid = grid[np.isfinite(sig[grid]) & np.isfinite(fwd[grid])]
    c = COST[sym]
    hist, nets, bks = [], [], []
    for gi in grid:
        s = sig[gi]
        if len(hist) >= warmup:
            hi_t, lo_t = np.quantile(hist, q), np.quantile(hist, 1 - q)
            if s >= hi_t:
                nets.append(-fwd[gi] - c)
                bks.append(bk[gi])
            elif s <= lo_t:
                nets.append(fwd[gi] - c)
                bks.append(bk[gi])
        hist.append(s)
    return pd.DataFrame({"net": nets, "bucket": pd.to_datetime(bks)})


def report(name, trades):
    d = trades[trades["bucket"].dt.year == 2025].sort_values("bucket").reset_index(drop=True)
    if d.empty:
        print(f"\n{name}: no 2025 trades")
        return
    net = d["net"].to_numpy()
    cum = np.cumsum(net)
    dd = cum - np.maximum.accumulate(cum)
    maxdd = dd.min()
    print(f"\n=== {name} — 2025 (pooled EUR/GBP/JPY) ===")
    print(f"  trades={len(net)}  total={cum[-1]:+.1f} bps  mean/trade={net.mean():+.3f}  "
          f"win={(net>0).mean()*100:.0f}%  maxDD={maxdd:+.1f} bps  "
          f"finalDD={dd[-1]:+.1f}  ret/DD={abs(cum[-1]/maxdd) if maxdd<0 else float('nan'):.2f}")
    # monthly cumulative
    d["mon"] = d["bucket"].dt.to_period("M")
    mon = d.groupby("mon")["net"].sum()
    print("  monthly net (bps): " + "  ".join(f"{str(m)[2:]}:{v:+.1f}" for m, v in mon.items()))


def main():
    mom = pd.concat([mom_2h_trades(s) for s in TIGHT], ignore_index=True)
    rev = pd.concat([rev_trades(s) for s in TIGHT], ignore_index=True)
    report("2h MOMENTUM (top-5% long)", mom)
    report("2-3d REVERSION (fade extended move)", rev)


if __name__ == "__main__":
    main()
