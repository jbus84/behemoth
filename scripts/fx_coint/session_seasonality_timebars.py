"""Session/hour-of-day USD edge on HOURLY TIME BARS (correct wall-clock).

The 1000-tick version smeared the diurnal effect (10 tick-bars = variable hours). Calendar
effects are wall-clock specific, so we redo it on hourly time bars with a fixed-HOUR hold.

Per (pair, hour-of-day) the direction = sign of TRAIN mean USD-oriented H-hour-forward
return; trade it OOS, one entry per hour bar, hold H hours, non-overlap via greedy, real
cost, pooled 6 majors, expanding walk-forward. Sweep H and a selectivity threshold on the
strongest hours. Reports net/accuracy/per-year/folds + correlation to XS reversion.

Usage: uv run python scripts/fx_coint/session_seasonality_timebars.py
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
from scripts.fx_coint.feature_ic_definitive import DATA
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap

PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
N_FOLDS = 5
COST = 1.0
H_GRID = [1, 3, 6, 12]


def load(sym):
    import polars as pl
    df = pl.read_parquet(f"{DATA}/{sym}_1h_flow.parquet").sort("bucket")
    mid = df["mid"].to_numpy()
    t = pd.DatetimeIndex(pd.to_datetime(df["bucket"].to_numpy()))
    return np.log(mid), t


def build(H):
    rows = []
    for sym, sgn in PAIRS.items():
        logp, t = load(sym)
        n = len(logp)
        fwd = np.full(n, np.nan)
        fwd[:n - H] = (logp[H:] - logp[:n - H]) * 1e4 * sgn
        rows.append(pd.DataFrame({"sym": sym, "t": t, "hour": t.hour, "fwd": fwd,
                                  "entry": np.arange(n), "exit": np.arange(n) + H}))
    return pd.concat(rows, ignore_index=True).dropna(subset=["fwd"])


def evaluate(df, strong_q):
    edges = df["entry"].quantile(np.linspace(0, 1, N_FOLDS + 1)).to_numpy()
    fnet, facc, recs = [], [], []
    sym_pos = {s: 0 for s in PAIRS}
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        tr = df[df["entry"] < lo]
        te = df[(df["entry"] >= lo) & (df["entry"] < hi)]
        if len(tr) < 500 or len(te) < 100:
            continue
        hd = tr.groupby("hour")["fwd"].mean()
        sign = np.sign(hd)
        keep = set(hd.index)
        if strong_q > 0:
            keep = set(hd[hd.abs() >= hd.abs().quantile(strong_q)].index)
        pnls_all = []
        for s, g in te[te["hour"].isin(keep)].groupby("sym"):
            g = g.sort_values("entry")
            ko = greedy_nonoverlap(g["entry"].to_numpy(), g["exit"].to_numpy())
            gg = g.iloc[ko]
            pnl = gg["hour"].map(sign).to_numpy() * gg["fwd"].to_numpy() - COST
            if len(pnl):
                pnls_all.append(pd.DataFrame({"t": gg["t"].to_numpy(), "pnl": pnl}))
                if np.mean(pnl) > 0:
                    sym_pos[s] += 1
        if pnls_all:
            allp = pd.concat(pnls_all)
            fnet.append(allp["pnl"].mean())
            facc.append((allp["pnl"] + COST > 0).mean())
            recs.append(allp)
    fn = np.array(fnet)
    daily = None
    if recs:
        a = pd.concat(recs)
        a["date"] = pd.DatetimeIndex(a["t"]).normalize()
        daily = a.groupby("date")["pnl"].sum()
    return dict(net=fn.mean() if len(fn) else np.nan, acc=np.mean(facc) if facc else np.nan,
                folds_pos=int((fn > 0).sum()), nf=len(fn),
                sym_pos=int(sum(v >= (N_FOLDS - 1) / 2 for v in sym_pos.values())), daily=daily)


def main():
    print("Session hour-of-day on HOURLY TIME BARS | pooled 6 majors | cost 1.0bps")
    print(f"{'H(hrs)':>6s} {'strongQ':>8s} {'net':>8s} {'accuracy':>9s} {'folds+':>7s} {'sym+':>5s}")
    keep_daily = None
    for H in H_GRID:
        df = build(H)
        for sq in (0.0, 0.5, 0.7):
            r = evaluate(df, sq)
            print(f"{H:>6d} {sq:>8.2f} {r['net']:>+8.3f} {r['acc']:>9.4f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/6")
            if H == 6 and sq == 0.7:
                keep_daily = r["daily"]
        print()
    if keep_daily is not None:
        xsr.TURN_COST_FRAC = 1.0
        xs = xsr.backtest(xsr.residualise(xsr.daily_returns()), 20)
        xs.index = pd.to_datetime(xs.index)
        j = pd.concat([keep_daily.rename("h"), xs.rename("xs")], axis=1).dropna()
        if len(j) > 30:
            print(f"H=6,strongQ=0.7 daily-PnL corr to XS reversion: {j['h'].corr(j['xs']):+.2f} (n={len(j)})")


if __name__ == "__main__":
    main()
