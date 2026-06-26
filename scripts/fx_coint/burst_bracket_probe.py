"""Ride the burst with ORDER MANAGEMENT — a stop/TP bracket, not a fixed hold.

You can't predict the next burst's direction, but you don't have to: position in the
last burst's direction with a bracket, and let the fast one-bar continuation burst FILL
your take-profit while a stop caps the reversion cases. Payoff asymmetry (a continuation
burst is a top-1% ~19bp move; reversions are small/stoppable) can make hit<0.5 profitable.

Per pair on 1000-tick bars (own-price, not oriented): burst = top-1% |bar return|. Enter
at the burst bar close in the burst's direction. Walk forward up to MAX_HOLD bars,
detecting touches with bar high/low (bid proxy); stop-first on same-bar ambiguity
(conservative). Sweep TP / SL / MAX_HOLD in units of the entry-bar vol. Net of cost,
with folds+/sym+ breadth so a winner isn't one lucky cell.

Usage: uv run python scripts/fx_coint/burst_bracket_probe.py
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

from scripts.fx_coint.feature_ic_definitive import DATA

PAIRS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
SUFFIX = "1000tick"
COST = 1.0
N_FOLDS = 5
# bracket grid in bps (absolute), TP must exceed cost to net positive
GRID = [
    (tp, sl, mh)
    for tp in (5, 10, 20, 40)
    for sl in (3, 5, 10)
    for mh in (5, 20, 50)
]


def load(sym):
    d = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet").sort("timestamp")
    mid = (d["close_bid"].to_numpy() + d["close_ask"].to_numpy()) / 2
    hi = d["high_bid"].to_numpy()
    lo = d["low_bid"].to_numpy()
    return mid, hi, lo


def bracket_pnl(mid, hi, lo, entries, dirs, tp, sl, mh):
    """For each entry (idx, direction) simulate a tp/sl/max-hold bracket; return bps array."""
    out = []
    n = len(mid)
    for i, dr in zip(entries, dirs):
        e = mid[i]
        tp_px = e * (1 + dr * tp / 1e4)
        sl_px = e * (1 - dr * sl / 1e4)
        ret = None
        end = min(i + mh, n - 1)
        for j in range(i + 1, end + 1):
            if dr > 0:
                hit_sl = lo[j] <= sl_px
                hit_tp = hi[j] >= tp_px
            else:
                hit_sl = hi[j] >= sl_px
                hit_tp = lo[j] <= tp_px
            if hit_sl:                      # stop-first (conservative)
                ret = -sl
                break
            if hit_tp:
                ret = tp
                break
        if ret is None:
            ret = dr * (mid[end] - e) / e * 1e4
        out.append(ret - COST)
    return np.array(out)


def run(data, bursts, mode):
    print(f"\n=== {mode.upper()} THE BURST (bracket) ===")
    print(f"  {'tp':>3s} {'sl':>3s} {'mh':>3s} {'n':>7s} {'net':>7s} {'hit':>6s} {'folds+':>7s} {'sym+':>5s}")
    results = []
    for tp, sl, mh in GRID:
        # per-symbol pnl with timestamps(=entry idx) for walk-forward folds
        sym_pnl, sym_idx = {}, {}
        for s in PAIRS:
            mid, hi, lo = data[s]
            idx, dirs = bursts[s]
            d2 = dirs if mode == "ride" else -dirs
            sym_pnl[s] = bracket_pnl(mid, hi, lo, idx, d2, tp, sl, mh)
            sym_idx[s] = idx
        all_idx = np.concatenate([sym_idx[s] for s in PAIRS])
        edges = np.quantile(all_idx, np.linspace(0, 1, N_FOLDS + 1))
        fold_net, sym_pos = [], np.zeros(len(PAIRS))
        allp = []
        for k in range(1, N_FOLDS):
            lo_e, hi_e = edges[k], edges[k + 1]
            fp = []
            for si, s in enumerate(PAIRS):
                m = (sym_idx[s] >= lo_e) & (sym_idx[s] < hi_e)
                if m.sum() < 10:
                    continue
                pn = sym_pnl[s][m]
                fp.append(pn)
                if pn.mean() > 0:
                    sym_pos[si] += 1
            if fp:
                fold_net.append(np.mean(np.concatenate(fp)))
        allp = np.concatenate([sym_pnl[s] for s in PAIRS])
        fn = np.array(fold_net)
        results.append((tp, sl, mh, len(allp), allp.mean(), np.mean(allp + COST > 0),
                        int((fn > 0).sum()), len(fn), int((sym_pos >= (N_FOLDS - 1) / 2).sum())))

    print(f"  {'tp':>3s} {'sl':>3s} {'mh':>3s} {'n':>7s} {'net':>7s} {'hit':>6s} {'folds+':>7s} {'sym+':>5s}")
    for tp, sl, mh, n, net, hit, fp, nf, sp in sorted(results, key=lambda x: -x[4])[:8]:
        flag = "  <==" if (net > 0 and fp >= nf - 1 and sp >= 4) else ""
        print(f"  {tp:>3d} {sl:>3d} {mh:>3d} {n:>7d} {net:>+7.2f} {hit:>6.3f} {fp:>4d}/{nf} {sp:>3d}/6{flag}")


def main():
    data = {s: load(s) for s in PAIRS}
    bursts = {}
    for s in PAIRS:
        mid, hi, lo = data[s]
        r = np.append(np.nan, np.diff(np.log(mid))) * 1e4
        thr = np.nanquantile(np.abs(r[np.isfinite(r)]), 0.99)
        idx = np.where(np.abs(r) >= thr)[0]
        idx = idx[(idx > 20) & (idx < len(mid) - 51)]
        bursts[s] = (idx, np.sign(r[idx]))
    print(f"BURST BRACKET ({SUFFIX}, top-1% bursts, own-price) cost={COST}bps")
    run(data, bursts, "ride")
    run(data, bursts, "fade")


if __name__ == "__main__":
    main()
