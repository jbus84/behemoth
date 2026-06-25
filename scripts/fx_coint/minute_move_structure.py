"""Minute-resolution move structure: are moves instantaneous or multi-bar?
And does order flow predict / characterise the unfolding?

True 1-min time bars (data/tick_bars/{sym}_1m_flow.parquet), 6 pairs x 2018-2026.
Weekend/holiday gaps masked (only contiguous 1-min steps used).

Measures (per pair + pooled, with cross-pair sign agreement = breadth):
  1. Variance ratio VR(k)=Var(k-min ret)/(k*Var(1-min)).  ~1 random walk (instant);
     >1 trending (moves unfold); <1 mean-reverting.
  2. Return continuation IC: corr(r_t, r_{t+k}) decay.  Momentum vs reversal.
  3. Flow IC: contemporaneous (impact) and PREDICTIVE IC(flow_t, r_{t+1..k}) for
     OFI and tick-rule.  (Hourly flow was dead; minute is where impact lives.)
  4. Impulse response: large-move bars -> mean sign-aligned cumulative return over
     next k min.  Flat after 0 = instantaneous; rising = continuation.
     Split by flow-backed (sign(OFI)==sign(move)) vs flow-opposed.
  5. Flow impulse: large-|OFI| bars -> cumulative flow-aligned return.
  6. Move-completion fraction (share of 15-min move realised in minute 1).

Usage:  uv run python scripts/fx_coint/minute_move_structure.py
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

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
KS = [1, 2, 3, 5, 10, 15, 30, 60]
IR_KS = [1, 2, 3, 5, 10, 15]


def load_minute(sym: str):
    d = pl.read_parquet(f"data/tick_bars/{sym}_1m_flow.parquet").sort("bucket")
    mid = d["mid"].to_numpy().astype(np.float64)
    t = d["bucket"].to_numpy().astype("datetime64[m]").astype(np.int64)  # minutes
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4  # bps
    contig = np.empty(len(mid), dtype=bool)
    contig[0] = False
    contig[1:] = (t[1:] - t[:-1]) == 1  # true 1-min step (no weekend gap)
    r[~contig] = np.nan
    ofi = d["flow_ofi"].to_numpy().astype(np.float64)
    tick = d["flow_tick"].to_numpy().astype(np.float64)
    return r, ofi, tick, contig


def _ic(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 100:
        return np.nan
    ra = np.argsort(np.argsort(a[m])).astype(float)
    rb = np.argsort(np.argsort(b[m])).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def fwd_cum(r, k):
    """sum of r over (t+1..t+k); NaN if any element missing/gap (np.sum propagates)."""
    n = len(r)
    cols = np.full((k, n), np.nan)
    for i in range(1, k + 1):
        cols[i - 1, : n - i] = r[i:]
    return cols.sum(axis=0)  # NaN propagates if any of the k forward bars is NaN


def variance_ratio(r, k):
    base = r[np.isfinite(r)]
    if k == 1:
        return 1.0
    ck = fwd_cum(r, k)
    ck = ck[np.isfinite(ck)]
    if len(ck) < 1000:
        return np.nan
    return float(np.var(ck) / (k * np.var(base)))


def main():
    print("=== MINUTE MOVE STRUCTURE  (6 pairs x 2018-2026, 1-min time bars) ===\n")
    data = {p: load_minute(p) for p in PAIRS}

    # cost / scale reference
    print("1-min |return| (bps): pair  mean  median")
    for p in PAIRS:
        r = data[p][0]
        ar = np.abs(r[np.isfinite(r)])
        print(f"   {p}  {ar.mean():.3f}  {np.median(ar):.3f}")

    # 1. Variance ratio
    print("\n[1] VARIANCE RATIO  VR(k)  (>1 trend / <1 revert / ~1 random-walk)")
    print("   k    " + "  ".join(f"{p[:6]:>6}" for p in PAIRS) + "   pooledMean")
    for k in KS:
        vrs = [variance_ratio(data[p][0], k) for p in PAIRS]
        print(f"   {k:>3}  " + "  ".join(f"{v:6.3f}" for v in vrs) + f"   {np.nanmean(vrs):.3f}")

    # 2. Return continuation IC
    print("\n[2] RETURN CONTINUATION  IC(r_t, r_t+k)  (per-pair; +momentum / -reversal)")
    print("   k    " + "  ".join(f"{p[:6]:>6}" for p in PAIRS) + "   signAgree")
    for k in [1, 2, 3, 5, 10]:
        ics = []
        for p in PAIRS:
            r = data[p][0]
            fwd = np.full(len(r), np.nan)
            fwd[: len(r) - k] = r[k:]
            ics.append(_ic(r, fwd))
        sgn = np.sign(np.nanmean(ics))
        agree = np.mean([np.sign(x) == sgn for x in ics if np.isfinite(x)])
        print(f"   {k:>3}  " + "  ".join(f"{v:+6.3f}" for v in ics) + f"   {agree:.2f}")

    # 3. Flow IC: contemporaneous (impact) + predictive
    print("\n[3] FLOW IC   contemp=IC(flow_t,r_t)  pred_k=IC(flow_t, r_t+1..k)")
    for fname, idx in [("OFI", 1), ("tick", 2)]:
        print(f"   --- flow={fname} ---")
        for label, k in [("contemp", 0), ("pred1", 1), ("pred3", 3), ("pred5", 5)]:
            ics = []
            for p in PAIRS:
                r = data[p][0]
                f = data[p][idx]
                tgt = r if k == 0 else fwd_cum(r, k)
                ics.append(_ic(f, tgt))
            sgn = np.sign(np.nanmean(ics))
            agree = np.mean([np.sign(x) == sgn for x in ics if np.isfinite(x)])
            print(f"     {label:>7}  " + "  ".join(f"{v:+6.3f}" for v in ics) +
                  f"   mean={np.nanmean(ics):+.3f} agree={agree:.2f}")

    # 4. Impulse response (price moves) + flow split
    print("\n[4] IMPULSE RESPONSE  large move (top-decile |r_t|) -> mean sign-aligned")
    print("    cumulative return (bps) over next k min.  pooled across pairs.")
    # pool
    allr = np.concatenate([data[p][0] for p in PAIRS])
    allofi = np.concatenate([data[p][1] for p in PAIRS])
    thr = np.nanquantile(np.abs(allr), 0.9)
    big = np.isfinite(allr) & (np.abs(allr) >= thr)
    sgn_move = np.sign(allr)
    flow_backed = big & (np.sign(allofi) == sgn_move)
    flow_opp = big & (np.sign(allofi) == -sgn_move)
    print(f"    threshold |r|>={thr:.2f} bps,  n_big={big.sum()}")
    print(f"    {'k':>3}  {'all':>8}  {'flowBacked':>10}  {'flowOpp':>8}")
    for k in IR_KS:
        cum = fwd_cum(allr, k)
        # sign-align to the triggering move
        for_all = (sgn_move * cum)
        def cond(mask):
            v = for_all[mask & np.isfinite(for_all)]
            return v.mean() if len(v) else np.nan
        print(f"    {k:>3}  {cond(big):>8.3f}  {cond(flow_backed):>10.3f}  {cond(flow_opp):>8.3f}")

    # 5. Flow impulse response
    print("\n[5] FLOW IMPULSE  large |OFI| (top-decile) -> mean OFI-aligned cum return (bps)")
    thrf = np.nanquantile(np.abs(allofi), 0.9)
    bigf = np.isfinite(allofi) & (np.abs(allofi) >= thrf) & np.isfinite(allr)
    sgn_f = np.sign(allofi)
    print(f"    threshold |OFI|>={thrf:.3f},  n={bigf.sum()}")
    print(f"    {'k':>3}  {'cumRet(OFI-aligned)':>20}")
    for k in [0, 1, 2, 3, 5, 10, 15]:
        if k == 0:
            v = (sgn_f * allr)[bigf]
        else:
            cum = fwd_cum(allr, k)
            v = (sgn_f * cum)[bigf & np.isfinite(cum)]
        print(f"    {k:>3}  {np.nanmean(v):>20.3f}")

    # 6. Move-completion fraction
    cum15 = fwd_cum(allr, 15)
    m = big & np.isfinite(cum15)
    bar1 = allr[m]                      # the trigger bar itself
    frac = np.abs(bar1).sum() / (np.abs(bar1).sum() + np.abs(sgn_move[m] * cum15[m]).sum())
    print(f"\n[6] MOVE COMPLETION: share of (bar0 + next15) magnitude in the trigger "
          f"minute = {frac*100:.1f}%")


if __name__ == "__main__":
    main()
