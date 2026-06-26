"""Hour-of-day USD seasonality — a calendar-driven, orthogonal directional edge.

The orthogonal screen found an OOS-stable diurnal pattern: USD-oriented forward returns
are negative in London morning (h8-9) and positive in US afternoon/evening (h19-22).
This is a SESSION/calendar driver, independent of price reversion.

Strategy (causal, walk-forward): one entry per (pair, day, hour) at the first bar of
each UTC hour, hold N_FWD bars. The traded DIRECTION for each hour is the sign of that
hour's mean USD-oriented return learned on TRAIN only. Optionally restrict to the
strongest hours (|train mean| above a threshold) for selectivity. Pooled over 6 majors,
real cost, non-overlapping within pair. Reports net/accuracy/per-year/folds and
correlation to the TB (ffd_zvol20) and XS reversion books.

Usage: uv run python scripts/fx_coint/hour_seasonality.py
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
from scripts.fx_coint.feature_ic_definitive import DATA, SUFFIX

PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
N_FWD = 10
N_FOLDS = 5
COST = 1.0
STRONG_Q = 0.0        # 0 = trade all hours; >0 = only hours whose |train mean| >= quantile


def load(sym):
    import polars as pl
    df = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.to_datetime(df["timestamp"].to_numpy()).tz_localize(None)
    o = np.argsort(t.to_numpy().astype("datetime64[ns]").astype("int64"))
    mid = ((df["close_bid"].to_numpy() + df["close_ask"].to_numpy()) / 2)[o]
    return np.log(mid), pd.DatetimeIndex(t.to_numpy()[o])


def build():
    rows = []
    for sym, sgn in PAIRS.items():
        logp, t = load(sym)
        n = len(logp)
        fwd = np.full(n, np.nan)
        fwd[:n - N_FWD] = (logp[N_FWD:] - logp[:n - N_FWD]) * 1e4 * sgn
        hour = t.hour.to_numpy()
        day = t.normalize().to_numpy()
        # first bar of each (day,hour) block = one entry
        key = pd.Series(pd.factorize(pd.Series(day).astype(str) + "_" + pd.Series(hour).astype(str))[0])
        first = key.ne(key.shift()).to_numpy()
        idx = np.where(first & np.isfinite(fwd))[0]
        rows.append(pd.DataFrame({
            "sym": sym, "t": t[idx], "hour": hour[idx], "fwd": fwd[idx],
            "entry": idx, "exit": idx + N_FWD,
        }))
    return pd.concat(rows, ignore_index=True)


def evaluate(df, strong_q):
    edges = df["entry"].quantile(np.linspace(0, 1, N_FOLDS + 1)).to_numpy()
    fold_net, fold_acc, recs = [], [], []
    sym_pos = {s: 0 for s in PAIRS}
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        tr = df[df["entry"] < lo]
        te = df[(df["entry"] >= lo) & (df["entry"] < hi)]
        if len(tr) < 500 or len(te) < 100:
            continue
        hour_dir = tr.groupby("hour")["fwd"].mean()
        sign = np.sign(hour_dir)
        keep_hours = set(hour_dir.index)
        if strong_q > 0:
            thr = hour_dir.abs().quantile(strong_q)
            keep_hours = set(hour_dir[hour_dir.abs() >= thr].index)
        te = te[te["hour"].isin(keep_hours)].copy()
        if not len(te):
            continue
        te["pnl"] = te["hour"].map(sign) * te["fwd"] - COST
        fold_net.append(te["pnl"].mean())
        fold_acc.append((te["hour"].map(sign) * te["fwd"] > 0).mean())
        for s, g in te.groupby("sym"):
            if g["pnl"].mean() > 0:
                sym_pos[s] += 1
        recs.append(te[["t", "pnl"]])
    fn = np.array(fold_net)
    daily = None
    if recs:
        allr = pd.concat(recs)
        allr["date"] = pd.DatetimeIndex(allr["t"]).normalize()
        daily = allr.groupby("date")["pnl"].sum()
    return dict(net=fn.mean() if len(fn) else np.nan, acc=np.mean(fold_acc) if fold_acc else np.nan,
                folds_pos=int((fn > 0).sum()), nf=len(fn),
                sym_pos=int(sum(v >= (N_FOLDS - 1) / 2 for v in sym_pos.values())),
                daily=daily)


def main():
    df = build()
    print(f"Hour-of-day USD seasonality | pooled 6 majors | {len(df):,} hourly entries | "
          f"hold {N_FWD} bars | cost {COST}bps")
    print(f"{'strongQ':>8s} {'nFoldsNet':>9s} {'accuracy':>9s} {'folds+':>7s} {'sym+':>5s}")
    daily_keep = None
    for sq in (0.0, 0.5, 0.7, 0.8):
        r = evaluate(df, sq)
        print(f"{sq:>8.2f} {r['net']:>+9.3f} {r['acc']:>9.4f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/6")
        if sq == 0.7:
            daily_keep = r["daily"]

    # correlation to reversion books
    if daily_keep is not None:
        xsr.TURN_COST_FRAC = 1.0
        xs = xsr.backtest(xsr.residualise(xsr.daily_returns()), 20)
        xs.index = pd.to_datetime(xs.index)
        j = pd.concat([daily_keep.rename("hour"), xs.rename("xs")], axis=1).dropna()
        if len(j) > 30:
            print(f"\nstrongQ=0.7 daily-PnL correlation to XS reversion: {j['hour'].corr(j['xs']):+.2f}  (n={len(j)})")


if __name__ == "__main__":
    main()
