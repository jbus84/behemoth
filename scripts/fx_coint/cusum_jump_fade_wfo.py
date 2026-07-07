"""Causal walk-forward check on the 120min jump-fade cell found in eurusd_cusum_probe.py.

The probe found: fading Lee-Mykland-flagged jump bars over the next 120min (24x 5m bars)
clears 0.6bps ECN round-trip cost, in-sample, full 8yr history, for EURUSD/GBPUSD/AUDUSD/EURGBP
(not USDJPY). All rule parameters (z-thresh=4.0, K=0.5, bipower window=24) are fixed constants,
not fit to this data -- so there's nothing to "train" in the ML sense. What we haven't checked
is whether the effect is TIME-STABLE or a full-sample artifact that's actually concentrated in
one era (the exact failure mode that killed the 2h-tail-momentum and 55%-challenge candidates
in this project -- first-half t=3.50, second-half t=0.59, see project_fx_tail_wfo_forking_paths_verdict).

This does two honest, non-overlapping-in-time reads, no parameter re-fitting:
  1. year-by-year gross/net/t for the jump-fade-120min cell
  2. first-half vs second-half of the 8yr sample

Cost is still the flat 0.6bps placeholder -- real-spread correction for AUDUSD/EURGBP is a
separate, still-open caveat, not addressed here.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_coint.eurusd_cusum_probe import add_features, load_5m

H = 24  # 120min, the cell of interest
COMMISSION_RT_BPS = 0.60  # $3.00/side x2 / 100k notional, Pepperstone Razor

# Real Razor avg raw spread in pips (from usd_factor_pepperstone_cost.py -- the
# user's actual verified broker figures). EURGBP has no verified figure anywhere
# in this repo -- swept across a plausible range instead of asserted as fact.
RAZOR_SPREAD_PIPS = {
    "EURUSD": 0.1, "GBPUSD": 0.2, "AUDUSD": 0.1, "USDJPY": 0.3,
}
EURGBP_SPREAD_SWEEP_PIPS = (0.3, 0.6, 1.0)  # optimistic / plausible / conservative, UNVERIFIED
SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY"]  # EURGBP handled separately below


def fade_stats(fwd: np.ndarray, ret_sign: np.ndarray, cost_bps: float) -> tuple[float, float, float, int]:
    fade = fwd * ret_sign * -1
    n = len(fade)
    if n < 5:
        return float("nan"), float("nan"), float("nan"), n
    gross_bps = float(fade.mean()) * 1e4
    net_bps = gross_bps - cost_bps
    se = fade.std() / np.sqrt(n)
    t = float(fade.mean() / se) if se > 0 else float("nan")
    return gross_bps, net_bps, t, n


def real_cost_bps(symbol: str, avg_mid: float, spread_pips: float) -> float:
    pip_size = 0.01 if symbol == "USDJPY" else 0.0001
    spread_bps = spread_pips * pip_size / avg_mid * 1e4
    return spread_bps + COMMISSION_RT_BPS


def run(symbol: str, spread_pips: float | None = None) -> None:
    df = load_5m(symbol)
    df = add_features(df)
    valid = df.filter(
        pl.col("bp_sigma").is_not_null()
        & pl.col("is_jump")
        & pl.col(f"fwd_{H}").is_not_null()
    ).with_columns(pl.col("bucket").dt.year().alias("year"))

    sp = spread_pips if spread_pips is not None else RAZOR_SPREAD_PIPS[symbol]
    cost_bps = real_cost_bps(symbol, float(valid["mid"].mean()), sp)
    print(f"  [real cost: {sp}pip spread + {COMMISSION_RT_BPS}bps commission = {cost_bps:.3f}bps RT]")

    print(f"\n=== {symbol}: jump-fade @120min, year-by-year (causal, non-overlapping) ===")
    years = sorted(valid["year"].unique().to_list())
    for y in years:
        sub = valid.filter(pl.col("year") == y)
        fwd = sub[f"fwd_{H}"].to_numpy()
        sgn = sub["ret"].sign().to_numpy()
        gross, net, t, n = fade_stats(fwd, sgn, cost_bps)
        flag = "" if n < 30 else ("  <-- net+" if net > 0 else "")
        print(f"  {y}  n={n:5d}  gross={gross:+7.3f}bps  net={net:+7.3f}bps  t={t:+6.2f}{flag}")

    mid_year = years[len(years) // 2]
    first = valid.filter(pl.col("year") < mid_year)
    second = valid.filter(pl.col("year") >= mid_year)
    print(f"  -- half-split at {mid_year} --")
    for label, sub in [("first half", first), ("second half", second)]:
        fwd = sub[f"fwd_{H}"].to_numpy()
        sgn = sub["ret"].sign().to_numpy()
        gross, net, t, n = fade_stats(fwd, sgn, cost_bps)
        print(f"  {label:12s} n={n:5d}  gross={gross:+7.3f}bps  net={net:+7.3f}bps  t={t:+6.2f}")


def main() -> None:
    for sym in SYMBOLS:
        run(sym)

    print("\n=== EURGBP: no verified real spread in this repo -- sweeping plausible pip values ===")
    for sp in EURGBP_SPREAD_SWEEP_PIPS:
        print(f"\n--- EURGBP @ {sp}pip spread assumption ---")
        run("EURGBP", spread_pips=sp)


if __name__ == "__main__":
    main()
