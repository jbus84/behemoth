"""Short-term edge in FADING bursts — separate liquidity (revert) from info (continue).

Raw burst-fade is breakeven because it mixes bursts that revert (liquidity overshoot)
with bursts that continue (information jump). Condition the fade on discriminators that
theory says mark a liquidity overshoot, and look for a short-term (N<=10) net-positive
cell, pooled 5 majors, 1000-tick, walk-forward, real cost.

Discriminators (all causal, known at/just-before the burst):
  MAG      : burst magnitude bucket among bursts (moderate q0.99-0.995 vs extreme q0.999+)
             -> expect moderate revert, extreme continue.
  EXTEND   : does the burst push FURTHER from fair value? sign(burst)==sign(ffd_zvol20
             just before) = overshoot-of-an-overshoot -> strong reversion candidate;
             opposite = burst toward fair / possibly information.
  SPREAD   : wide vs tight spread at the burst -> wide = liquidity-driven -> revert.
  EXHAUST  : burst bar closed near its extreme (hl_pos_frac) = exhaustion -> revert.

Fade = trade against the burst, hold N bars (short), net of cost. Report by condition.

Usage: uv run python scripts/fx_coint/conditional_burst_fade.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import build_all
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [1, 3, 5, 10]
N_FOLDS = 5
COST = 1.0


def build(sym):
    logp, f, vol, bph = build_all(sym)
    n = len(logp)
    warm = int(96 * bph) + 60
    r = np.append(np.nan, np.diff(logp)) * 1e4
    ar = np.abs(r)
    valid = np.arange(warm, n - max(N_GRID) - 1)
    thr = np.nanquantile(ar[np.isfinite(ar)], 0.99)
    burst = valid[ar[valid] >= thr]
    fwd = {N: (logp[burst + N] - logp[burst]) * 1e4 for N in N_GRID}
    return dict(
        burst=burst, bdir=np.sign(r[burst]), bmag=ar[burst], fwd=fwd,
        pre_ext=f["ffd_zvol20"][burst - 1],          # extension just before burst (causal)
        spread=f["spread"][burst], hlpos=f["hl_pos_frac"][burst],
    )


def fade_net(data, mask_fn, N):
    """Fade bursts passing mask, hold N bars, non-overlap, walk-forward. net/hit/folds/sym."""
    syms = list(data)
    all_b = np.concatenate([data[s]["burst"] for s in syms])
    edges = np.quantile(all_b, np.linspace(0, 1, N_FOLDS + 1))
    fnet, n_tr = [], 0
    sym_pos = np.zeros(len(syms))
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = data[s]
            te = (d["burst"] >= lo) & (d["burst"] < hi)
            m = te & mask_fn(d)
            if m.sum() < 10:
                continue
            ent = d["burst"][m]
            t1 = ent + N
            o = np.argsort(ent)
            keep = greedy_nonoverlap(ent[o], t1[o])
            pnl = (-d["bdir"][m] * d["fwd"][N][m])[o][keep] - COST     # fade
            if len(pnl):
                fold.append(pnl)
                n_tr += len(pnl)
                if np.mean(pnl) > 0:
                    sym_pos[si] += 1
        if fold:
            fnet.append(np.mean(np.concatenate(fold)))
    fn = np.array(fnet)
    return (fn.mean() if len(fn) else np.nan, n_tr,
            int((fn > 0).sum()), len(fn), int((sym_pos >= (N_FOLDS - 1) / 2).sum()))


def main():
    data = {s: build(s) for s in POOL}
    # global thresholds for conditions (pooled)
    allmag = np.concatenate([data[s]["bmag"] for s in POOL])
    allspr = np.concatenate([data[s]["spread"] for s in POOL])
    mag995 = np.nanquantile(allmag, 0.5)        # within-burst median (q0.995 of full)
    spr_med = np.nanmedian(allspr)

    conds = {
        "ALL bursts": lambda d: np.ones(len(d["burst"]), bool),
        "EXTEND (burst pushes further out)": lambda d: np.sign(d["bdir"]) == np.sign(d["pre_ext"]),
        "TOWARD fair (opposite)": lambda d: np.sign(d["bdir"]) != np.sign(d["pre_ext"]),
        "MODERATE mag (<median burst)": lambda d: d["bmag"] < mag995,
        "EXTREME mag (>=median burst)": lambda d: d["bmag"] >= mag995,
        "WIDE spread": lambda d: d["spread"] >= spr_med,
        "TIGHT spread": lambda d: d["spread"] < spr_med,
        "EXTEND & WIDE & moderate": lambda d: (np.sign(d["bdir"]) == np.sign(d["pre_ext"])) & (d["spread"] >= spr_med) & (d["bmag"] < mag995),
    }

    print("FADE-THE-BURST short-term, net bps by condition x hold (pooled 5 majors, cost=1.0)")
    print(f"  {'condition':>34s} " + " ".join(f"N{N:>2d}(net/sym+)" for N in N_GRID))
    for label, fn_mask in conds.items():
        cells = []
        for N in N_GRID:
            net, ntr, fp, nf, sp = fade_net(data, fn_mask, N)
            cells.append(f"{net:>+5.2f}/{sp}")
        print(f"  {label:>34s} " + "   ".join(f"{c:>11s}" for c in cells))


if __name__ == "__main__":
    main()
