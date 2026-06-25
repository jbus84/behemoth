"""Magnitude-band map of the 15m liquid-session reversion (fade mom_3).

The feature search found a broad mean-reversion signal (fade recent momentum) in London+Overlap
that is a BODY effect and INVERTS in the extreme tail. This maps the fade net across bands of
recent-move EXTENSION (|mom_3| quantile), pooled across tight majors, at TAKER and MAKER cost —
to find whether a moderate-extension band both reverts AND clears cost.

Signal: fade mom_3 (45-min vol-normalised momentum). pnl = -sign(mom_3) * fwd_ret_1.
Band by |mom_3| quantile. Liquid hours (07-16 UTC). Honest day-block bootstrap on each band.

Caveat (maker): a passive reversion entry is the classic adverse-selection trap — you get filled
when the move CONTINUES against you. The maker column is a gross-signal upper bound, NOT a fill
guarantee; tick-exact maker-fill verification is a separate gate.

Usage:
    uv run python scripts/fx_coint/scalp_magnitude_band.py --year 2024
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

from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    DEFAULT_COST_BPS,
    add_rolling_features,
    compute_forward_returns,
    load_raw_ticks,
)
from scripts.fx_coint.scalp_tf_probe import build_enriched  # noqa: E402

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
LIQUID = (7, 16)
MAKER_BPS = 0.20  # representative maker round-trip cost (commission - partial spread capture)
RNG = np.random.default_rng(0)
BANDS = [(0.0, 0.5), (0.5, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 1.0)]


def boot_ci(net, bucket, n_boot=3000):
    if len(net) < 5:
        return np.nan, np.nan
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for i in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--freq", default="15m")
    args = ap.parse_args()

    # collect per-pair: |mom3| (for banding), fade gross bps, fwd bps, taker cost, bucket
    recs = []
    for sym in TIGHT:
        df = add_rolling_features(build_enriched(load_raw_ticks(sym, args.year), sym, args.freq), sym)
        df = compute_forward_returns(df, [1])
        mid = df["mid"].astype(float)
        r = np.log(mid / mid.shift(1)) * 1e4
        rv = r.rolling(48, min_periods=20).std().shift(1)
        mom3 = (r.rolling(3, min_periods=2).sum() / (rv * np.sqrt(3))).shift(1)
        fwd = np.log(mid.shift(-1) / mid) * 1e4
        hour = df["bucket"].dt.hour
        liq = (hour >= LIQUID[0]) & (hour < LIQUID[1])
        fade_gross = -np.sign(mom3) * fwd  # fade the recent move
        d = pd.DataFrame({"absmom": mom3.abs(), "gross": fade_gross, "fwd": fwd,
                          "taker": DEFAULT_COST_BPS[sym], "bucket": df["bucket"]})[liq]
        d = d[np.isfinite(d["absmom"]) & np.isfinite(d["gross"])]
        # band thresholds from THIS pair's |mom3| distribution
        d["q"] = d["absmom"].rank(pct=True)
        recs.append(d)
    D = pd.concat(recs, ignore_index=True)

    print(f"MAGNITUDE-BAND MAP — fade mom_3, London+Overlap {args.freq} H1, pooled tight majors, {args.year}")
    print(f"  fadeGross = -sign(mom3)*fwd; takerCost~0.7; makerCost~{MAKER_BPS}\n")
    print(f"  {'|mom3| band':>14} {'n':>5} {'mean|fwd|':>9} {'fadeGross':>9} {'hit':>5} "
          f"{'netTaker':>8} {'netMaker':>8} {'makerBootCI':>20}")
    for lo, hi in BANDS:
        b = D[(D["q"] >= lo) & (D["q"] < hi)]
        if len(b) < 20:
            continue
        g = b["gross"].mean()
        net_t = (b["gross"] - b["taker"]).mean()
        net_m = (b["gross"] - MAKER_BPS).mean()
        clo, chi = boot_ci((b["gross"] - MAKER_BPS).to_numpy(), b["bucket"].to_numpy())
        flag = "  <<<" if clo > 0 else ""
        print(f"  {f'P{int(lo*100)}-{int(hi*100)}':>14} {len(b):>5} {b['fwd'].abs().mean():>9.3f} "
              f"{g:>9.3f} {(b['gross'] > 0).mean()*100:>4.0f}% {net_t:>8.3f} {net_m:>8.3f} "
              f"[{clo:>+7.3f},{chi:>+7.3f}]{flag}")
    # whole liquid sample for reference
    g = D["gross"].mean()
    print(f"\n  {'ALL liquid':>14} {len(D):>5} {D['fwd'].abs().mean():>9.3f} {g:>9.3f} "
          f"{(D['gross'] > 0).mean()*100:>4.0f}% {(D['gross']-D['taker']).mean():>8.3f} "
          f"{(D['gross']-MAKER_BPS).mean():>8.3f}")
    print("\n  Read: a band that REVERTS (fadeGross>0) AND clears cost. Top band should invert")
    print("  (fadeGross<0 = momentum continues). Maker col is a gross upper bound, not a fill.")


if __name__ == "__main__":
    main()
