"""Does EURUSD lead GBPUSD? Pairwise lagged cross-correlation + tradeability.

EUR and GBP co-move (both USD-driven), so contemporaneous corr is high. The lead-lag question:
does EUR's return at t predict GBP's return at t+1 (EUR leads), more than the reverse? And is
that predictive lag tradeable net of cost?

  c0           = corr(eur[t], gbp[t])           contemporaneous
  eur_leads_k  = corr(eur[t-k], gbp[t])         EUR leads GBP by k bars
  gbp_leads_k  = corr(gbp[t-k], eur[t])         GBP leads EUR by k bars  (asymmetry test)
  trade        = predict sign(gbp[t]) from eur[t-1]; tail net @ GBP taker cost

Usage:
    uv run python scripts/fx_coint/scalp_leadlag_probe.py --year 2024 --freqs 1m 5m 15m
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scripts.fx_coint.phase0_scalp_common import DEFAULT_COST_BPS, load_raw_ticks  # noqa: E402
from scripts.fx_coint.scalp_offset_probe import mid_bars  # noqa: E402


def aligned_returns(year: int, every_min: int, a: str, b: str):
    """Returns of a and b on a shared bucket grid (bps)."""
    ba = mid_bars(load_raw_ticks(a, year), every_min, 0).set_index("bucket")
    bb = mid_bars(load_raw_ticks(b, year), every_min, 0).set_index("bucket")
    idx = ba.index.union(bb.index)
    ra = np.log(ba["mid"].reindex(idx).astype(float)).diff() * 1e4
    rb = np.log(bb["mid"].reindex(idx).astype(float)).diff() * 1e4
    df = pd.DataFrame({"a": ra, "b": rb, "hour": idx.hour}, index=idx).dropna()
    return df


def corr(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 200 or np.std(x[m]) == 0 or np.std(y[m]) == 0:
        return float("nan")
    return float(np.corrcoef(x[m], y[m])[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--freqs", nargs="+", default=["1m", "5m", "15m"])
    ap.add_argument("--lead", default="EURUSD")
    ap.add_argument("--lag", default="GBPUSD")
    args = ap.parse_args()
    A, B = args.lead, args.lag
    cost = DEFAULT_COST_BPS[B] / 10_000

    print(f"LEAD-LAG: does {A} lead {B}? pooled-year {args.year}\n")
    for freq in args.freqs:
        em = int(freq.replace("m", ""))
        d = aligned_returns(args.year, em, A, B)
        a, b = d["a"].to_numpy(), d["b"].to_numpy()
        c0 = corr(a, b)
        # k>0: A[t-k] vs B[t]  -> A leads B
        eur_leads = {k: corr(np.roll(a, k), b) for k in (1, 2, 3)}  # roll k = a shifted forward
        gbp_leads = {k: corr(np.roll(b, k), a) for k in (1, 2, 3)}
        print(f"  {freq}: contemp corr={c0:+.3f}")
        print(f"     {A} leads {B}:  lag1={eur_leads[1]:+.4f} lag2={eur_leads[2]:+.4f} lag3={eur_leads[3]:+.4f}")
        print(f"     {B} leads {A}:  lag1={gbp_leads[1]:+.4f} lag2={gbp_leads[2]:+.4f} lag3={gbp_leads[3]:+.4f}")
        # tradeable: predict sign(b[t]) from a[t-1]; whole + extreme tail; liquid only
        liq = (d["hour"] >= 7).to_numpy() & (d["hour"] < 16).to_numpy()
        a1 = np.r_[np.nan, a[:-1]]  # a[t-1], no wrap
        sign = np.sign(a1)
        gross = sign * b
        for tag, mask in (("all", np.ones(len(d), bool)), ("liq", liq)):
            mm = mask & np.isfinite(a1) & np.isfinite(b)
            net = gross[mm] - cost * 1e4
            hit = (gross[mm] > 0).mean() * 100
            thr = np.quantile(np.abs(a1[mm]), 0.90)
            tmask = mm & (np.abs(a1) >= thr)
            tail = gross[tmask] - cost * 1e4
            print(f"     trade {B}|sign({A}[t-1]) [{tag}]: netAll={net.mean():+.3f} hit={hit:.0f}% "
                  f"tailNet={tail.mean():+.3f} (n={tmask.sum()})")
        print()


if __name__ == "__main__":
    main()
