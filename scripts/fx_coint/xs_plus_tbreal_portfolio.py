"""Does XS reversion complement the REAL TB method (1000-tick + fractional-diff)?

The canonical TB book (pnl_walkforward.py): on 1000-tick bars, fade ffd_zvol20 (the
fractional-diff reversion feature), payoff = triple-barrier first-touch return,
top-decile magnitude selection, non-overlapping, expanding walk-forward, real cost.
That is the directional reversion edge the program actually validated — NOT the daily
weekly fade I combined earlier.

Here we reconstruct that TB book's trade-level PnL (with entry timestamps), bucket it
to daily bps, and combine it with the market-neutral XS reversion (xs_reversion, L=20,
full cost). Reports correlation and each-alone vs combined Sharpe / maxDD / Calmar /
per-year — the actual "does it complement?" answer.

Usage: uv run python scripts/fx_coint/xs_plus_tbreal_portfolio.py [N_TB]
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
SIGNAL = "ffd_zvol20"
N_TB = int(sys.argv[1]) if len(sys.argv) > 1 else 50
N_FOLDS = 5
COST = 1.0
Q_MAG = 0.90
XS_L = 20


def _timestamps(sym):
    import polars as pl
    df = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.to_datetime(df["timestamp"].to_numpy()).tz_localize(None).to_numpy().astype("datetime64[ns]")
    return t[np.argsort(t.astype("int64"))]


def tb_trades():
    """Reconstruct the canonical TB book: per-trade (timestamp, pnl) across pairs."""
    cache = {s: build_all(s) for s in POOL}
    ts = {s: _timestamps(s) for s in POOL}
    sym = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        ev = np.arange(warm, n - N_TB - 3)
        ev = ev[np.isfinite(vol[ev + 1]) & (vol[ev + 1] > 0)]
        entry = ev + 1
        t1, y, _, _ = triple_barrier_core(
            logp, entry, np.minimum(entry + N_TB, len(logp) - 1),
            1.0 * vol[entry] * np.sqrt(N_TB))
        sig = f[SIGNAL][ev]
        pnl = -np.sign(sig) * y                       # fade
        sym[s] = dict(entry=entry, t1=t1, sig=sig, pnl=pnl, ts=ts[s])

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
            thr = np.nanquantile(np.abs(d["sig"][tr]), Q_MAG)        # causal top-decile mag
            sel = (np.abs(d["sig"]) >= thr) & te & np.isfinite(d["pnl"])
            o = np.argsort(d["entry"][sel])
            e_sel, t_sel, p_sel = d["entry"][sel][o], d["t1"][sel][o], d["pnl"][sel][o]
            ko = greedy_nonoverlap(e_sel, t_sel)
            for idx, p in zip(e_sel[ko], p_sel[ko] - COST):
                recs.append({"date": pd.Timestamp(d["ts"][idx]).normalize(), "pnl": float(p)})
    return pd.DataFrame(recs)


def daily_from_trades(trades):
    return trades.groupby("date")["pnl"].sum()


def xs_daily():
    xsr.TURN_COST_FRAC = 1.0
    p = xsr.backtest(xsr.residualise(xsr.daily_returns()), XS_L)
    p.index = pd.to_datetime(p.index)
    return p


def _unit(s):
    return s / (s.std() + 1e-9)


def rep(name, s):
    sh = s.mean() / (s.std() + 1e-9) * np.sqrt(252)
    cum = s.cumsum()
    dd = (cum - cum.cummax()).min()
    cal = (s.mean() * 252) / (abs(dd) + 1e-9)
    yr = s.groupby(s.index.year).sum()
    print(f"{name:16s} Sharpe={sh:5.2f}  maxDD={dd:8.2f}  Calmar={cal:5.2f}  pos={int((yr > 0).sum())}/{len(yr)}")
    return yr


def main():
    tb = daily_from_trades(tb_trades())
    tb.index = pd.to_datetime(tb.index)
    xs = xs_daily()
    df = pd.concat([tb.rename("TB"), xs.rename("XS")], axis=1).dropna(how="all").fillna(0.0)
    print(f"TB = 1000-tick ffd_zvol20 fade, triple-barrier N={N_TB}, top-decile, non-overlap\n")
    print(f"Daily-PnL correlation TB vs XS: {df['TB'].corr(df['XS']):+.3f}\n")
    tb_u, xs_u = _unit(df["TB"]), _unit(df["XS"])
    comb = 0.5 * tb_u + 0.5 * xs_u
    yt = rep("TB (unit-vol)", tb_u)
    yx = rep("XS (unit-vol)", xs_u)
    yc = rep("COMBINED", comb)
    print("\nPer-year (unit-vol bps):")
    print(f"  {'year':>5s} {'TB':>8s} {'XS':>8s} {'COMB':>8s}")
    for y in sorted(set(yt.index) | set(yx.index)):
        print(f"  {y:>5d} {yt.get(y, 0):>+8.1f} {yx.get(y, 0):>+8.1f} {yc.get(y, 0):>+8.1f}")
    cum = comb.cumsum()
    dd = abs((cum - cum.cummax()).min())
    print(f"\nCombined Calmar {(comb.mean() * 252) / (dd + 1e-9):.2f}  "
          f"(TB raw Calmar {(tb.mean() * 252) / (abs((tb.cumsum() - tb.cumsum().cummax()).min()) + 1e-9):.2f})")


if __name__ == "__main__":
    main()
