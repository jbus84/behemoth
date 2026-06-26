"""EXTEND-burst reversion entry + bracket order management vs fixed exit.

Entry: fade a top-1% |return| burst that EXTENDS the ffd_zvol20 deviation
(direction = -sign(ffd_zvol20 at entry)). Baseline exit = fixed max-hold. Test whether a
TP/SL/max-hold BRACKET (let the reversion run to target, cut the adverse-selection tail
where the burst was information and keeps going) beats the fixed exit. Intrabar touches
via bar high/low (bid proxy), stop-first on ambiguity. Pooled 5 majors, 1000-tick,
walk-forward, non-overlap, real cost.

Usage: uv run python scripts/fx_coint/extend_burst_bracket.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import DATA, build_all
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_FOLDS = 5
COST = 1.0
MAX_HOLD = 50
FIXED_N = 30
GRID = [(tp, sl) for tp in (5, 10, 15, 20, 30) for sl in (3, 5, 10, 20)]


def load_px(sym):
    d = pl.read_parquet(f"{DATA}/{sym}_1000tick.parquet")
    t = d["timestamp"].to_numpy().astype("datetime64[ns]").astype("int64")
    o = np.argsort(t)
    mid = ((d["close_bid"].to_numpy() + d["close_ask"].to_numpy()) / 2)[o]
    hi = d["high_bid"].to_numpy()[o]
    lo = d["low_bid"].to_numpy()[o]
    return mid, hi, lo


def build(sym):
    logp, f, vol, bph = build_all(sym)
    mid, hi, lo = load_px(sym)
    n = min(len(logp), len(mid))
    logp, mid, hi, lo = logp[:n], mid[:n], hi[:n], lo[:n]
    ext = f["ffd_zvol20"][:n]
    warm = int(96 * bph) + 60
    r = np.append(np.nan, np.diff(logp)) * 1e4
    ar = np.abs(r)
    bthr = np.nanquantile(ar[np.isfinite(ar)], 0.99)
    idx = np.arange(warm, n - MAX_HOLD - 1)
    is_burst = ar[idx] >= bthr
    extend = np.sign(r[idx]) == np.sign(ext[idx - 1])
    sel = is_burst & extend & np.isfinite(ext[idx]) & (ext[idx] != 0)
    entry = idx[sel]
    direction = -np.sign(ext[entry])             # fade the extension
    return dict(entry=entry, direction=direction, mid=mid, hi=hi, lo=lo)


def fixed_pnl(d, N):
    e = d["entry"]
    ret = (d["mid"][e + N] - d["mid"][e]) / d["mid"][e] * 1e4
    return d["direction"] * ret - COST, e + N


def bracket_pnl(d, tp, sl):
    mid, hi, lo = d["mid"], d["hi"], d["lo"]
    out, exitidx = [], []
    n = len(mid)
    for i, dr in zip(d["entry"], d["direction"]):
        e = mid[i]
        tp_px = e * (1 + dr * tp / 1e4)
        sl_px = e * (1 - dr * sl / 1e4)
        end = min(i + MAX_HOLD, n - 1)
        res, xi = None, end
        for j in range(i + 1, end + 1):
            hit_sl = (lo[j] <= sl_px) if dr > 0 else (hi[j] >= sl_px)
            hit_tp = (hi[j] >= tp_px) if dr > 0 else (lo[j] <= tp_px)
            if hit_sl:
                res, xi = -sl, j
                break
            if hit_tp:
                res, xi = tp, j
                break
        if res is None:
            res = dr * (mid[end] - e) / e * 1e4
        out.append(res - COST)
        exitidx.append(xi)
    return np.array(out), np.array(exitidx)


def walk(data, pnl_fn):
    syms = list(data)
    all_e = np.concatenate([data[s]["entry"] for s in syms])
    edges = np.quantile(all_e, np.linspace(0, 1, N_FOLDS + 1))
    per = {s: pnl_fn(data[s]) for s in syms}
    fnet, n_tr = [], 0
    sym_pos = np.zeros(len(syms))
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = data[s]
            pnl, xidx = per[s]
            m = (d["entry"] >= lo) & (d["entry"] < hi)
            if m.sum() < 10:
                continue
            ent, t1, p = d["entry"][m], xidx[m], pnl[m]
            o = np.argsort(ent)
            keep = greedy_nonoverlap(ent[o], t1[o])
            pk = p[o][keep]
            if len(pk):
                fold.append(pk)
                n_tr += len(pk)
                if np.mean(pk) > 0:
                    sym_pos[si] += 1
        if fold:
            fnet.append(np.mean(np.concatenate(fold)))
    fn = np.array(fnet)
    return (fn.mean() if len(fn) else np.nan, n_tr,
            int((fn > 0).sum()), len(fn), int((sym_pos >= (N_FOLDS - 1) / 2).sum()))


def main():
    data = {s: build(s) for s in POOL}
    print(f"EXTEND-burst entry + exit method (pooled 5 majors, 1000-tick, cost={COST}, max_hold={MAX_HOLD})")
    net, n, fp, nf, sp = walk(data, lambda d: fixed_pnl(d, FIXED_N))
    print(f"\n  BASELINE fixed N={FIXED_N}: net={net:+.2f} n={n} folds+={fp}/{nf} sym+={sp}/5")
    print("\n  BRACKET tp/sl sweep:")
    print(f"  {'tp':>3s} {'sl':>3s} {'net':>7s} {'n':>6s} {'folds+':>7s} {'sym+':>5s}")
    res = []
    for tp, sl in GRID:
        r = walk(data, lambda d, tp=tp, sl=sl: bracket_pnl(d, tp, sl))
        res.append((tp, sl, *r))
    for tp, sl, net, n, fp, nf, sp in sorted(res, key=lambda x: -x[2])[:10]:
        flag = "  <==" if (net > 0 and fp >= nf - 1 and sp >= 4) else ""
        print(f"  {tp:>3d} {sl:>3d} {net:>+7.2f} {n:>6d} {fp:>4d}/{nf} {sp:>3d}/5{flag}")


if __name__ == "__main__":
    main()
